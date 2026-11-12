"""Bounded RFC discussion logic. No HTTP, OAuth, GitHub token or execution client.

Only a server adapter may supply ``user`` after validating the Relcom ID session.
Never deserialize it from a request body. The adapter must check exact HTTPS Host
and Origin/CSRF, body/header bounds, no-store and private response visibility.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from urllib.parse import parse_qs, urlsplit

ISSUER = 'https://id.relcom.com'
PREFIX = '/community/v1'
ROLES = {'moderator', 'maintainer', 'admin'}
MAX_USERS = 10000
MAX_ENTRIES = 20000
MAX_REQUESTS = 100000
MAX_AUDIT = 200000
MAX_VOTES = 200000
PAGE_BYTES = 98304  # Leave room below the existing 128 KiB public proxy bound.
RATE_SECONDS = 600
RATE_WRITES = 30
# Forum: fixed categories, so a route allowlist can name every one of them.
FORUM_CATEGORIES = ('bcp', 'blog', 'rfc', 'experiments', 'architecture', 'questions', 'meta')
FORUM_SUBJECT = r'[a-z0-9][a-z0-9.-]{0,79}'
MAX_THREADS = 20000
MAX_POSTS = 100000
FORUM_PENDING = 20
RESERVED_NAMES = {'admin', 'administrator', 'moderator', 'ipvx', 'relcom', 'system',
                  'automatic-moderator', 'participant', 'участник', 'модератор', 'администратор'}
# The site's language editions. Published posts and thread titles get machine translations
# into each of them (infra/forum_translator.py); the original text is never replaced.
FORUM_LANGUAGES = ('ru', 'en', 'de', 'es')
TRANSLATOR = r'[a-z0-9][a-z0-9.:-]{2,79}'


def _digest(text):
    """Which exact source text a translation belongs to."""
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class CommunityResponse:
    status: int
    data: dict


class Rejected(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def _text(value, minimum=1, maximum=8000):
    if (not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum
            or any(ord(c) < 32 and c not in '\n\t' for c in value) or '\x7f' in value):
        raise Rejected(400, 'invalid_text')
    return value.strip()


def _fields(body, allowed):
    if not isinstance(body, dict) or set(body) - set(allowed):
        raise Rejected(400, 'invalid_fields')


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class CommunityService:
    """SQLite-backed pending submissions, moderated publication and advisory votes.

    ``bootstrap_admin_author_id`` pins an operator-confirmed pseudonym of an
    already enrolled verified account. Legacy ``bootstrap_admin_sub`` is for
    local fixtures; do not put a raw subject in Git, CI inputs or public history.
    There is no first-login or email-based bootstrap.
    An absent bootstrap leaves every new user an ordinary participant. The
    bootstrap subject is stored only as a keyed project pseudonym. Changing an
    existing bootstrap requires an explicit offline migration, not an API call.
    """
    def __init__(self, state_dir, *, bootstrap_admin_sub=None, bootstrap_admin_author_id=None, clock=time.time):
        if bootstrap_admin_sub is not None and bootstrap_admin_author_id is not None:
            raise ValueError('Configure only one bootstrap identity')
        self.clock = clock
        directory = Path(state_dir)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Community state must be a private directory')
        directory.chmod(0o700)
        key = directory / 'author.key'
        try:
            fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(secrets.token_bytes(32))
        if (key.is_symlink() or not stat.S_ISREG(key.stat().st_mode)
                or stat.S_IMODE(key.stat().st_mode) != 0o600 or key.stat().st_size != 32):
            raise ValueError('Community author key must be a private regular 32-byte file')
        self._key = key.read_bytes()
        self.database = directory / 'community.sqlite3'
        if self.database.is_symlink() or (self.database.exists() and not self.database.is_file()):
            raise ValueError('Community database must be a regular private file')
        fd = os.open(self.database, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        self.database.chmod(0o600)
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (actor TEXT PRIMARY KEY, created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS roles (actor TEXT, role TEXT, PRIMARY KEY(actor,role));
                CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfc TEXT, kind TEXT, title TEXT, text TEXT, status TEXT,
                    author TEXT, created INTEGER, updated INTEGER);
                CREATE TABLE IF NOT EXISTS votes (entry INTEGER, actor TEXT, value TEXT,
                    updated INTEGER, PRIMARY KEY(entry,actor));
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT, action TEXT, target TEXT, detail TEXT, at INTEGER);
                CREATE TABLE IF NOT EXISTS requests (actor TEXT, key TEXT, fingerprint TEXT,
                    status INTEGER, response TEXT, PRIMARY KEY(actor,key));
                CREATE TABLE IF NOT EXISTS rates (actor TEXT, window INTEGER, count INTEGER,
                    PRIMARY KEY(actor,window));
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS member_state (actor TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '', last_seen INTEGER,
                    blocked INTEGER NOT NULL DEFAULT 0, access_updated INTEGER);
                CREATE INDEX IF NOT EXISTS entry_listing ON entries(rfc,status,id);
                CREATE INDEX IF NOT EXISTS entry_author ON entries(author,status,id);
                CREATE TABLE IF NOT EXISTS forum_threads (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL, subject TEXT, title TEXT NOT NULL, author TEXT NOT NULL,
                    status TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0,
                    posts INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, bumped INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS forum_posts (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread INTEGER NOT NULL, author TEXT NOT NULL, text TEXT NOT NULL, reply_to INTEGER,
                    status TEXT NOT NULL, review TEXT, review_note TEXT,
                    created INTEGER NOT NULL, updated INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS forum_names (actor TEXT PRIMARY KEY, name TEXT NOT NULL,
                    folded TEXT NOT NULL UNIQUE, updated INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS forum_reads (actor TEXT NOT NULL, thread INTEGER NOT NULL,
                    seen INTEGER NOT NULL, PRIMARY KEY(actor, thread)) WITHOUT ROWID;
                CREATE INDEX IF NOT EXISTS forum_listing ON forum_threads(category,status,bumped,id);
                CREATE INDEX IF NOT EXISTS forum_subject ON forum_threads(subject,status,bumped,id);
                CREATE INDEX IF NOT EXISTS forum_thread_posts ON forum_posts(thread,status,id);
                CREATE INDEX IF NOT EXISTS forum_queue ON forum_posts(status,review,id);
                CREATE INDEX IF NOT EXISTS forum_author ON forum_posts(author,status);
                CREATE INDEX IF NOT EXISTS forum_author_thread ON forum_posts(author,thread,id);
                CREATE TABLE IF NOT EXISTS forum_languages (kind TEXT NOT NULL, item INTEGER NOT NULL,
                    digest TEXT NOT NULL, source TEXT, outcome TEXT NOT NULL, translator TEXT NOT NULL,
                    note TEXT, created INTEGER NOT NULL, PRIMARY KEY(kind, item)) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS forum_translations (kind TEXT NOT NULL, item INTEGER NOT NULL,
                    lang TEXT NOT NULL, text TEXT NOT NULL, PRIMARY KEY(kind, item, lang)) WITHOUT ROWID;
            ''')
            # Full-text search over published posts only. Without FTS5 the forum still
            # works and search answers 503.
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS forum_search USING fts5(title, text, "
                           "post UNINDEXED, thread UNINDEXED, tokenize='unicode61 remove_diacritics 2')")
                self.search_ready = True
            except sqlite3.OperationalError:
                self.search_ready = False
            if bootstrap_admin_sub is not None or bootstrap_admin_author_id is not None:
                if bootstrap_admin_author_id is not None:
                    if (not isinstance(bootstrap_admin_author_id, str)
                            or not re.fullmatch(r'member_[a-f0-9]{24}', bootstrap_admin_author_id)):
                        raise ValueError('Invalid bootstrap author pseudonym')
                    owner = bootstrap_admin_author_id
                    if not db.execute('SELECT 1 FROM users WHERE actor=?', (owner,)).fetchone():
                        raise ValueError('Bootstrap must name an already verified enrolled participant')
                else:
                    owner = self._actor(_text(bootstrap_admin_sub, 1, 250))
                old = db.execute("SELECT value FROM settings WHERE key='bootstrap_admin'").fetchone()
                if old and old[0] != owner:
                    raise ValueError('Changing the configured bootstrap requires an explicit migration')
                if not old:
                    self._enroll(db, owner)
                    db.execute("INSERT INTO settings VALUES ('bootstrap_admin',?)", (owner,))
                    db.execute("INSERT OR IGNORE INTO roles VALUES (?, 'admin')", (owner,))
                    self._audit(db, 'server-bootstrap', 'configure_admin', owner,
                                {'basis': 'server-pinned verified project author; no first-login/email bootstrap'})

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=5000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _actor(self, sub):
        return 'member_' + hmac.new(self._key, (ISSUER + '\x00' + sub).encode(), hashlib.sha256).hexdigest()[:24]

    def _principal(self, user, required=False):
        if user is None:
            if required:
                raise Rejected(401, 'sign_in_required')
            return None
        if (not isinstance(user, dict) or user.get('emailVerified') is not True
                or not isinstance(user.get('sub'), str) or not 1 <= len(user['sub']) <= 250):
            if required:
                raise Rejected(403, 'verified_account_required')
            return None
        return self._actor(user['sub'])

    def _enroll(self, db, actor):
        if not db.execute('SELECT 1 FROM users WHERE actor=?', (actor,)).fetchone():
            if db.execute('SELECT count(*) FROM users').fetchone()[0] >= MAX_USERS:
                raise Rejected(503, 'community_capacity_reached')
            db.execute('INSERT INTO users VALUES (?,?)', (actor, int(self.clock())))

    def _blocked(self, db, actor):
        row = db.execute('SELECT blocked FROM member_state WHERE actor=?', (actor,)).fetchone() if actor else None
        return bool(row and row[0])

    def _observe(self, db, actor, user):
        # Only the validated server session supplies this optional profile label.
        # It remains admin-private; public discussions retain project pseudonyms.
        name = user.get('name', '')
        name = ''.join(c for c in name if ord(c) >= 32 and ord(c) != 127).strip()[:100] if isinstance(name, str) else ''
        db.execute('INSERT INTO member_state(actor,name,last_seen) VALUES(?,?,?) '
                   'ON CONFLICT(actor) DO UPDATE SET name=excluded.name,last_seen=excluded.last_seen',
                   (actor, name, int(self.clock())))

    def _roles(self, db, actor, *, stored=False):
        if not stored and self._blocked(db, actor):
            return set()
        return {row[0] for row in db.execute('SELECT role FROM roles WHERE actor=?', (actor,))} if actor else set()

    def owner_identity(self, user):
        """The pinned, verified project owner only; portal admin is insufficient."""
        actor = self._principal(user)
        if not actor:
            return None
        with self._db() as db:
            owner = db.execute("SELECT value FROM settings WHERE key='bootstrap_admin'").fetchone()
            return actor if owner and owner[0] == actor and 'admin' in self._roles(db, actor) else None

    def _require(self, db, actor, *roles):
        if not self._roles(db, actor).intersection(roles):
            raise Rejected(403, 'role_required')

    def _audit(self, db, actor, action, target, detail):
        if db.execute('SELECT count(*) FROM audit').fetchone()[0] >= MAX_AUDIT:
            raise Rejected(503, 'audit_capacity_reached')
        db.execute('INSERT INTO audit(actor,action,target,detail,at) VALUES(?,?,?,?,?)',
                   (actor, action, str(target), json.dumps(detail, ensure_ascii=False), int(self.clock())))

    def _rate(self, db, actor):
        window = int(self.clock()) // RATE_SECONDS
        db.execute('DELETE FROM rates WHERE window < ?', (window - 1,))
        db.execute('INSERT OR IGNORE INTO rates VALUES (?,?,0)', (actor, window))
        count = db.execute('SELECT count FROM rates WHERE actor=? AND window=?', (actor, window)).fetchone()[0]
        if count >= RATE_WRITES:
            raise Rejected(429, 'write_rate_exceeded')
        db.execute('UPDATE rates SET count=count+1 WHERE actor=? AND window=?', (actor, window))

    def _entry(self, db, entry_id):
        row = db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone()
        if not row:
            raise Rejected(404, 'entry_not_found')
        return row

    def _visible(self, db, row, actor):
        return row['status'] == 'published' or row['author'] == actor or bool(self._roles(db, actor) & {'moderator', 'admin'})

    def _public_entry(self, db, row):
        counts = {value: 0 for value in ('yes', 'no', 'abstain')}
        for vote in db.execute('SELECT value,count(*) FROM votes WHERE entry=? GROUP BY value', (row['id'],)):
            counts[vote[0]] = vote[1]
        return {'id': row['id'], 'rfc': row['rfc'], 'kind': row['kind'], 'title': row['title'],
                'text': row['text'], 'status': row['status'],
                'author': {'id': row['author'], 'label': 'Участник ' + row['author'][-6:]},
                'createdAt': _stamp(row['created']), 'updatedAt': _stamp(row['updated']),
                'votes': {'counts': counts, 'binding': False, 'meaning': 'advisory-only; not RFC ratification'}}

    def _page(self, rows, convert, limit):
        items, used = [], 0
        for row in rows:
            item = convert(row)
            size = len(json.dumps(item, ensure_ascii=False).encode()) + 2
            if used + size > PAGE_BYTES:
                break
            items.append(item)
            used += size
        cursor = items[-1]['id'] if items and (len(items) < len(rows) or len(rows) == limit) else None
        return items, cursor

    def handle(self, method, path, user=None, body=None, *, request_id=None):
        """Return CommunityResponse, or None for a route outside /community/v1.

        ``user`` is trusted server session data, NOT request JSON. All submitted
        text remains plain text; the browser must render it using textContent.
        Every POST requires a stable Idempotency-Key (8..128 safe characters).
        """
        try:
            if not isinstance(path, str) or len(path) > 1500:
                raise Rejected(400, 'invalid_path')
            target = urlsplit(path)
            if not target.path.startswith(PREFIX + '/'):
                return None
            if method not in ('GET', 'POST'):
                raise Rejected(405, 'method_not_allowed')
            query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=5)
            if any(len(v) != 1 for v in query.values()):
                raise Rejected(400, 'duplicate_query')
            if method == 'POST' and query:
                raise Rejected(400, 'unexpected_query')
            actor = self._principal(user, required=method == 'POST')
            body = {} if body is None else body
            serialized = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            if len(serialized.encode()) > 12000:
                raise Rejected(413, 'body_too_large')
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                if actor:
                    self._enroll(db, actor)
                    self._observe(db, actor, user)
                # Blocking applies on every request, before cached mutations can
                # be replayed. Public reading remains available anonymously.
                if self._blocked(db, actor) and target.path != PREFIX + '/session':
                    if method == 'POST':
                        raise Rejected(403, 'access_blocked')
                    actor = None
                if method == 'GET':
                    return self._get(db, target.path, query, actor)
                if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}', request_id):
                    raise Rejected(400, 'idempotency_key_required')
                # Revoked privileged users must not read a previously cached private
                # response by replaying an old successful administrator request.
                if target.path == PREFIX + '/roles' or re.fullmatch(PREFIX + r'/members/member_[a-f0-9]{24}/access', target.path):
                    self._require(db, actor, 'admin')
                elif (re.fullmatch(PREFIX + r'/entries/([1-9][0-9]{0,8})/moderation', target.path)
                      or re.fullmatch(PREFIX + r'/forum/(?:posts|threads)/[1-9][0-9]{0,8}/moderation', target.path)):
                    self._require(db, actor, 'moderator', 'admin')
                elif (vote_match := re.fullmatch(PREFIX + r'/entries/([1-9][0-9]{0,8})/vote', target.path)):
                    row = self._entry(db, int(vote_match[1]))
                    if row['kind'] != 'proposal' or row['status'] != 'published':
                        raise Rejected(404, 'entry_not_found')
                fingerprint = hashlib.sha256((method + '\n' + target.path + '\n' + serialized).encode()).hexdigest()
                old = db.execute('SELECT * FROM requests WHERE actor=? AND key=?', (actor, request_id)).fetchone()
                if old:
                    if old['fingerprint'] != fingerprint:
                        raise Rejected(409, 'idempotency_key_reused_with_different_request')
                    return CommunityResponse(old['status'], json.loads(old['response']))
                if db.execute('SELECT count(*) FROM requests').fetchone()[0] >= MAX_REQUESTS:
                    raise Rejected(503, 'request_capacity_reached')
                self._rate(db, actor)
                response = self._post(db, target.path, actor, body)
                db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',
                           (actor, request_id, fingerprint, response.status, json.dumps(response.data, ensure_ascii=False)))
                return response
        except Rejected as exc:
            return CommunityResponse(exc.status, {'error': exc.code})
        except (ValueError, TypeError, UnicodeError):
            return CommunityResponse(400, {'error': 'invalid_request'})
        except sqlite3.Error:
            return CommunityResponse(503, {'error': 'community_temporarily_unavailable'})

    def _get(self, db, path, query, actor):
        if path == PREFIX + '/members':
            return self._members(db, query, actor)
        if path.startswith(PREFIX + '/forum/'):
            return self._forum_get(db, path[len(PREFIX + '/forum'):], query, actor)
        if set(query) - {'limit', 'before', 'mine', 'kind'}:
            raise Rejected(400, 'unknown_query')
        limit = int(query.get('limit', ['25'])[0])
        before = int(query.get('before', ['9223372036854775807'])[0])
        if not 1 <= limit <= 50 or not 1 <= before <= 9223372036854775807:
            raise Rejected(400, 'invalid_pagination')
        mine = query.get('mine', ['0'])[0]
        if mine not in ('0', '1'):
            raise Rejected(400, 'invalid_visibility')
        if mine == '1' and not actor:
            raise Rejected(401, 'sign_in_required')
        if path == PREFIX + '/session':
            if query:
                raise Rejected(400, 'unexpected_query')
            roles = self._roles(db, actor)
            blocked = self._blocked(db, actor)
            return CommunityResponse(200, {'authenticated': bool(actor),
                'author': {'id': actor, 'label': 'Участник ' + actor[-6:]} if actor else None,
                'roles': sorted({'participant', *roles}) if actor and not blocked else [],
                'access': 'blocked' if blocked else 'active' if actor else 'anonymous',
                'governance': {'votesBinding': False, 'ratification': 'RFC-0003 / pinned GitHub electorate'},
                'capabilities': ['submit_pending', 'advisory_vote', 'forum_post'] if actor and not blocked else []})
        match = re.fullmatch(PREFIX + r'/rfcs/(rfc-\d{4})/entries', path)
        if match:
            kind = query.get('kind', ['comment'])[0]
            if kind not in ('comment', 'proposal'):
                raise Rejected(400, 'invalid_kind')
            clause, values = ('author=?', [actor]) if mine == '1' else ("status='published'", [])
            rows = db.execute(f'SELECT * FROM entries WHERE rfc=? AND kind=? AND {clause} AND id<? ORDER BY id DESC LIMIT ?',
                              [match[1], kind, *values, before, limit]).fetchall()
            items, cursor = self._page(rows, lambda row: self._public_entry(db, row), limit)
            return CommunityResponse(200, {'entries': items, 'nextBefore': cursor,
                'visibility': 'own-private' if mine == '1' else 'published'})
        if path == PREFIX + '/moderation':
            self._require(db, actor, 'moderator', 'admin')
            rows = db.execute("SELECT * FROM entries WHERE status='pending' AND id<? ORDER BY id DESC LIMIT ?", (before, limit)).fetchall()
            items, cursor = self._page(rows, lambda row: self._public_entry(db, row), limit)
            return CommunityResponse(200, {'entries': items, 'nextBefore': cursor, 'visibility': 'moderator-private'})
        if path == PREFIX + '/audit':
            self._require(db, actor, 'admin')
            rows = db.execute('SELECT * FROM audit WHERE id<? ORDER BY id DESC LIMIT ?', (before, limit)).fetchall()
            items, cursor = self._page(rows, dict, limit)
            return CommunityResponse(200, {'events': items, 'nextBefore': cursor, 'visibility': 'admin-private'})
        match = re.fullmatch(PREFIX + r'/entries/([1-9][0-9]{0,8})', path)
        if match:
            row = self._entry(db, int(match[1]))
            if not self._visible(db, row, actor):
                raise Rejected(404, 'entry_not_found')
            return CommunityResponse(200, {'entry': self._public_entry(db, row)})
        raise Rejected(404, 'route_not_found')

    def _member(self, db, row):
        return {'id': row['actor'], 'label': row['name'] or 'Участник ' + row['actor'][-6:],
                'roles': sorted({'participant', *self._roles(db, row['actor'], stored=True)}),
                'access': 'blocked' if row['blocked'] else 'active',
                'joinedAt': _stamp(row['created']),
                'lastSeenAt': _stamp(row['last_seen']) if row['last_seen'] is not None else None,
                'accessUpdatedAt': _stamp(row['access_updated']) if row['access_updated'] is not None else None,
                'protected': bool(db.execute("SELECT 1 FROM settings WHERE key='bootstrap_admin' AND value=?", (row['actor'],)).fetchone())}

    def _members(self, db, query, actor):
        self._require(db, actor, 'admin')
        if set(query) - {'limit', 'after', 'search', 'access'}:
            raise Rejected(400, 'unknown_query')
        limit = int(query.get('limit', ['25'])[0])
        after = query.get('after', [''])[0]
        search = _text(query.get('search', [''])[0], 0, 100)
        access = query.get('access', ['all'])[0]
        if (not 1 <= limit <= 50 or (after and not re.fullmatch(r'member_[a-f0-9]{24}', after))
                or access not in ('all', 'active', 'blocked')):
            raise Rejected(400, 'invalid_pagination')
        clause, values = ['1=1'], []
        if search:
            escaped = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            clause.append("(u.actor LIKE ? ESCAPE '\\' OR COALESCE(s.name,'') LIKE ? ESCAPE '\\')")
            values += [escaped, escaped]
        if access != 'all':
            clause.append('COALESCE(s.blocked,0)=?'); values.append(int(access == 'blocked'))
        where = ' AND '.join(clause)
        source = ' FROM users u LEFT JOIN member_state s ON s.actor=u.actor '
        total = db.execute('SELECT count(*)' + source + 'WHERE ' + where, values).fetchone()[0]
        rows = db.execute("SELECT u.actor,u.created,COALESCE(s.name,'') AS name,s.last_seen,"
                          'COALESCE(s.blocked,0) AS blocked,s.access_updated' + source +
                          'WHERE ' + where + ' AND u.actor>? ORDER BY u.actor LIMIT ?',
                          [*values, after, limit+1]).fetchall()
        items = [self._member(db, row) for row in rows[:limit]]
        return CommunityResponse(200, {'members': items, 'total': total,
            'nextAfter': items[-1]['id'] if len(rows) > limit else None,
            'visibility': 'admin-private', 'scope': 'verified accounts that have visited this portal; not the entire identity-provider pool'})

    def _post(self, db, path, actor, body):
        if path.startswith(PREFIX + '/forum/'):
            return self._forum_post(db, path[len(PREFIX + '/forum'):], actor, body)
        match = re.fullmatch(PREFIX + r'/members/(member_[a-f0-9]{24})/access', path)
        if match:
            self._require(db, actor, 'admin')
            _fields(body, {'action', 'reason'})
            action, reason = body.get('action'), _text(body.get('reason'), 3, 1000)
            if action not in ('block', 'restore'):
                raise Rejected(400, 'invalid_access_change')
            target = match[1]
            if not db.execute('SELECT 1 FROM users WHERE actor=?', (target,)).fetchone():
                raise Rejected(404, 'participant_not_found')
            if action == 'block' and (target == actor or db.execute(
                    "SELECT 1 FROM settings WHERE key='bootstrap_admin' AND value=?", (target,)).fetchone()):
                raise Rejected(409, 'protected_admin')
            before = self._blocked(db, target)
            db.execute('INSERT INTO member_state(actor,blocked,access_updated) VALUES(?,?,?) '
                       'ON CONFLICT(actor) DO UPDATE SET blocked=excluded.blocked,access_updated=excluded.access_updated',
                       (target, int(action == 'block'), int(self.clock())))
            self._audit(db, actor, action + '_access', target, {'reason': reason, 'from': 'blocked' if before else 'active'})
            return CommunityResponse(200, {'authorId': target, 'access': 'blocked' if action == 'block' else 'active'})
        match = re.fullmatch(PREFIX + r'/rfcs/(rfc-\d{4})/entries', path)
        if match:
            _fields(body, {'kind', 'title', 'text'})
            kind = body.get('kind', 'comment')
            if kind not in ('comment', 'proposal'):
                raise Rejected(400, 'invalid_kind')
            title = _text(body.get('title', ''), 0, 200)
            text = _text(body.get('text'), 1, 8000)
            if kind == 'proposal' and not title:
                raise Rejected(400, 'proposal_title_required')
            if db.execute('SELECT count(*) FROM entries').fetchone()[0] >= MAX_ENTRIES:
                raise Rejected(503, 'entry_capacity_reached')
            if db.execute("SELECT count(*) FROM entries WHERE author=? AND status='pending'", (actor,)).fetchone()[0] >= 20:
                raise Rejected(429, 'pending_limit_reached')
            now = int(self.clock())
            cursor = db.execute("INSERT INTO entries(rfc,kind,title,text,status,author,created,updated) VALUES(?,?,?,?, 'pending',?,?,?)",
                                (match[1], kind, title, text, actor, now, now))
            entry_id = cursor.lastrowid
            self._audit(db, actor, 'submit_' + kind, entry_id, {'rfc': match[1], 'status': 'pending'})
            return CommunityResponse(201, {'entry': self._public_entry(db, self._entry(db, entry_id)), 'visibility': 'own-private'})
        match = re.fullmatch(PREFIX + r'/entries/([1-9][0-9]{0,8})/moderation', path)
        if match:
            self._require(db, actor, 'moderator', 'admin')
            _fields(body, {'action', 'reason'})
            action, reason = body.get('action'), _text(body.get('reason'), 3, 1000)
            if action not in ('publish', 'hide'):
                raise Rejected(400, 'invalid_moderation_action')
            row = self._entry(db, int(match[1])); status = 'published' if action == 'publish' else 'hidden'
            db.execute('UPDATE entries SET status=?,updated=? WHERE id=?', (status, int(self.clock()), row['id']))
            self._audit(db, actor, action, row['id'], {'from': row['status'], 'to': status, 'reason': reason})
            return CommunityResponse(200, {'entry': self._public_entry(db, self._entry(db, row['id']))})
        match = re.fullmatch(PREFIX + r'/entries/([1-9][0-9]{0,8})/vote', path)
        if match:
            _fields(body, {'value'})
            value = body.get('value');row = self._entry(db, int(match[1]))
            if row['kind'] != 'proposal' or row['status'] != 'published':
                raise Rejected(404, 'entry_not_found')
            if value not in ('yes', 'no', 'abstain', 'withdraw'):
                raise Rejected(400, 'invalid_vote')
            exists = db.execute('SELECT 1 FROM votes WHERE entry=? AND actor=?', (row['id'], actor)).fetchone()
            if value == 'withdraw':
                db.execute('DELETE FROM votes WHERE entry=? AND actor=?', (row['id'], actor))
            else:
                if not exists and db.execute('SELECT count(*) FROM votes').fetchone()[0] >= MAX_VOTES:
                    raise Rejected(503, 'vote_capacity_reached')
                db.execute('INSERT OR REPLACE INTO votes VALUES (?,?,?,?)', (row['id'], actor, value, int(self.clock())))
            self._audit(db, actor, 'advisory_vote', row['id'], {'value': value, 'binding': False})
            return CommunityResponse(200, {'entry': self._public_entry(db, row), 'binding': False})
        if path == PREFIX + '/roles':
            self._require(db, actor, 'admin')
            _fields(body, {'authorId', 'role', 'action', 'reason'})
            target, role, action = body.get('authorId'), body.get('role'), body.get('action')
            reason = _text(body.get('reason'), 3, 1000)
            if (not isinstance(target, str) or not re.fullmatch(r'member_[a-f0-9]{24}', target)
                    or role not in ROLES or action not in ('grant', 'revoke')):
                raise Rejected(400, 'invalid_role_change')
            if not db.execute('SELECT 1 FROM users WHERE actor=?', (target,)).fetchone():
                raise Rejected(404, 'participant_not_found')
            if action == 'grant' and self._blocked(db, target):
                raise Rejected(409, 'participant_blocked')
            owner = db.execute("SELECT value FROM settings WHERE key='bootstrap_admin'").fetchone()
            if action == 'revoke' and role == 'admin' and owner and target == owner[0]:
                raise Rejected(409, 'bootstrap_admin_requires_operator_migration')
            if action == 'grant':
                db.execute('INSERT OR IGNORE INTO roles VALUES (?,?)', (target, role))
            else:
                db.execute('DELETE FROM roles WHERE actor=? AND role=?', (target, role))
            self._audit(db, actor, action + '_role', target, {'role': role, 'reason': reason})
            return CommunityResponse(200, {'authorId': target, 'roles': sorted(self._roles(db, target)),
                'notice': 'Portal roles grant no GitHub, governance, native network or infrastructure access.'})
        raise Rejected(404, 'route_not_found')

    # Forum: categories of threads, each a sequence of plain-text posts. A post from a
    # participant starts pending; the automatic moderator (forum_review_queue/forum_review,
    # in-process only) publishes it, hides it or passes it to people. Moderators' own posts
    # are published at once. Hiding or publishing the opening post does the same to its thread.

    def _limit(self, query, default, maximum):
        limit = int(query.get('limit', [str(default)])[0])
        if not 1 <= limit <= maximum:
            raise Rejected(400, 'invalid_pagination')
        return limit

    def _moderates(self, db, actor):
        return bool(actor and self._roles(db, actor) & {'moderator', 'admin'})

    def _forum_author(self, db, actor):
        row = db.execute('SELECT name FROM forum_names WHERE actor=?', (actor,)).fetchone()
        return {'id': actor, 'label': row[0] if row else 'Участник ' + actor[-6:], 'named': bool(row)}

    def _thread(self, db, thread_id):
        row = db.execute('SELECT * FROM forum_threads WHERE id=?', (thread_id,)).fetchone()
        if not row:
            raise Rejected(404, 'thread_not_found')
        return row

    def _forum_post_row(self, db, post_id):
        row = db.execute('SELECT * FROM forum_posts WHERE id=?', (post_id,)).fetchone()
        if not row:
            raise Rejected(404, 'post_not_found')
        return row

    def _opening(self, db, thread_id):
        return db.execute('SELECT min(id) FROM forum_posts WHERE thread=?', (thread_id,)).fetchone()[0]

    def _language(self, query):
        lang = query.get('lang', [None])[0]
        if lang is not None and lang not in FORUM_LANGUAGES:
            raise Rejected(400, 'invalid_language')
        return lang

    def _translation(self, db, kind, item, original, status, lang):
        """The machine translation of a published text into ``lang``, or None.

        A translation is served only for the exact text it was made from, so a changed
        source never shows a stale translation.
        """
        if not lang or status != 'published':
            return None
        row = db.execute("SELECT l.digest, l.source, l.translator, t.text FROM forum_languages l "
                         'JOIN forum_translations t ON t.kind=l.kind AND t.item=l.item AND t.lang=? '
                         "WHERE l.kind=? AND l.item=? AND l.outcome='translated'", (lang, kind, item)).fetchone()
        if not row or row['digest'] != _digest(original):
            return None
        return {'lang': lang, 'from': row['source'], 'text': row['text'], 'by': row['translator'], 'machine': True}

    def _forget_translations(self, db, kind, item):
        db.execute('DELETE FROM forum_translations WHERE kind=? AND item=?', (kind, item))
        db.execute('DELETE FROM forum_languages WHERE kind=? AND item=?', (kind, item))

    def _public_thread(self, db, row, lang=None):
        item = {'id': row['id'], 'category': row['category'], 'subject': row['subject'],
                'title': row['title'], 'status': row['status'], 'locked': bool(row['locked']),
                'author': self._forum_author(db, row['author']), 'replies': max(row['posts'] - 1, 0),
                'createdAt': _stamp(row['created']), 'lastActivityAt': _stamp(row['bumped'])}
        translation = self._translation(db, 'title', row['id'], row['title'], row['status'], lang)
        if translation:
            item['translation'] = translation
        return item

    def _public_post(self, db, row, moderator=False, lang=None):
        item = {'id': row['id'], 'thread': row['thread'], 'text': row['text'], 'replyTo': row['reply_to'],
                'status': row['status'], 'author': self._forum_author(db, row['author']),
                'createdAt': _stamp(row['created'])}
        translation = self._translation(db, 'post', row['id'], row['text'], row['status'], lang)
        if translation:
            item['translation'] = translation
        if moderator:
            item['review'] = {'queue': 'people' if row['review'] == 'people' else 'automatic',
                              'note': row['review_note']}
        return item

    def _index(self, db, thread_id):
        """Keep search equal to what an anonymous reader can see in this thread."""
        if not self.search_ready:
            return
        db.execute('DELETE FROM forum_search WHERE thread=?', (thread_id,))
        thread = self._thread(db, thread_id)
        if thread['status'] == 'published':
            db.execute("INSERT INTO forum_search(title,text,post,thread) SELECT ?,text,id,thread "
                       "FROM forum_posts WHERE thread=? AND status='published'", (thread['title'], thread_id))

    def _refresh(self, db, thread_id):
        count, last = db.execute("SELECT count(*),max(created) FROM forum_posts WHERE thread=? AND status='published'",
                                 (thread_id,)).fetchone()
        db.execute('UPDATE forum_threads SET posts=?,bumped=COALESCE(?,created) WHERE id=?', (count, last, thread_id))
        self._index(db, thread_id)

    def _set_post(self, db, row, status, review, note):
        db.execute('UPDATE forum_posts SET status=?,review=?,review_note=?,updated=? WHERE id=?',
                   (status, review, note, int(self.clock()), row['id']))
        opening = self._opening(db, row['thread']) == row['id']
        if opening:
            db.execute('UPDATE forum_threads SET status=? WHERE id=?', (status, row['thread']))
        if status != 'published':
            # A hidden text keeps no copies in other languages; publishing it again
            # puts it back in the translation queue.
            self._forget_translations(db, 'post', row['id'])
            if opening:
                self._forget_translations(db, 'title', row['thread'])
        self._refresh(db, row['thread'])

    def _seen(self, db, actor, thread_id):
        """The last post a participant has seen in a thread they wrote in, or None if they did not.

        Writing a post counts as having read the thread up to it, so a participant's own
        posts and everything before them are never new to them.
        """
        if not actor:
            return None
        own = db.execute('SELECT max(id) FROM forum_posts WHERE author=? AND thread=?', (actor, thread_id)).fetchone()[0]
        if own is None:
            return None
        read = db.execute('SELECT seen FROM forum_reads WHERE actor=? AND thread=?', (actor, thread_id)).fetchone()
        return max(own, read[0] if read else 0)

    def _notifications(self, db, actor, limit, lang=None):
        """New published replies by others in the published threads a participant wrote in."""
        rows = db.execute('''
            WITH mine AS (SELECT thread, max(id) AS own FROM forum_posts WHERE author=? GROUP BY thread),
                 marks AS (SELECT m.thread, max(m.own, COALESCE(r.seen, 0)) AS seen FROM mine m
                           LEFT JOIN forum_reads r ON r.actor=? AND r.thread=m.thread)
            SELECT t.*, count(p.id) AS fresh, min(p.id) AS first FROM marks k
            JOIN forum_threads t ON t.id=k.thread AND t.status='published'
            LEFT JOIN forum_posts p ON p.thread=k.thread AND p.status='published' AND p.author!=? AND p.id>k.seen
            GROUP BY t.id ORDER BY fresh>0 DESC, t.bumped DESC, t.id DESC''', (actor, actor, actor)).fetchall()
        threads = []
        for row in rows[:limit]:
            item = self._public_thread(db, row, lang)
            item.update(newPosts=row['fresh'], firstNew=row['first'])
            threads.append(item)
        return {'unreadThreads': sum(1 for row in rows if row['fresh']),
                'unreadPosts': sum(row['fresh'] for row in rows), 'threads': threads}

    def _thread_page(self, db, where, values, query, actor):
        if set(query) - {'limit', 'before', 'lang'}:
            raise Rejected(400, 'unknown_query')
        limit = self._limit(query, 25, 50)
        lang = self._language(query)
        before = query.get('before', [''])[0]
        if before:
            if not re.fullmatch(r'[0-9]{1,12}-[1-9][0-9]{0,8}', before):
                raise Rejected(400, 'invalid_pagination')
            bumped, last = map(int, before.split('-'))
            where += ' AND (bumped<? OR (bumped=? AND id<?))'
            values = [*values, bumped, bumped, last]
        if not self._moderates(db, actor):
            where += " AND (status='published' OR author=?)"
            values = [*values, actor]
        rows = db.execute('SELECT * FROM forum_threads WHERE ' + where + ' ORDER BY bumped DESC, id DESC LIMIT ?',
                          [*values, limit]).fetchall()
        items, used = [], 0
        for row in rows:
            item = self._public_thread(db, row, lang)
            size = len(json.dumps(item, ensure_ascii=False).encode()) + 2
            if used + size > PAGE_BYTES:
                break
            items.append(item)
            used += size
        last = rows[len(items) - 1] if items else None
        cursor = '%d-%d' % (last['bumped'], last['id']) if last is not None and len(rows) == limit else None
        return {'threads': items, 'nextBefore': cursor}

    def _forum_get(self, db, path, query, actor):
        moderator = self._moderates(db, actor)
        if path == '/categories':
            if query:
                raise Rejected(400, 'unexpected_query')
            counts = {row[0]: (row[1], row[2]) for row in db.execute(
                "SELECT category,count(*),max(bumped) FROM forum_threads WHERE status='published' GROUP BY category")}
            return CommunityResponse(200, {'categories': [
                {'id': c, 'threads': counts.get(c, (0, None))[0],
                 'lastActivityAt': _stamp(counts[c][1]) if c in counts else None} for c in FORUM_CATEGORIES]})
        match = re.fullmatch(r'/categories/([a-z]{2,20})/threads', path)
        if match:
            if match[1] not in FORUM_CATEGORIES:
                raise Rejected(404, 'category_not_found')
            page = self._thread_page(db, "category=? AND status!='hidden'" if not moderator else 'category=?',
                                     [match[1]], query, actor)
            return CommunityResponse(200, {'category': match[1], **page})
        match = re.fullmatch(r'/subjects/(' + FORUM_SUBJECT + ')/threads', path)
        if match:
            page = self._thread_page(db, "subject=? AND status!='hidden'" if not moderator else 'subject=?',
                                     [match[1]], query, actor)
            return CommunityResponse(200, {'subject': match[1], **page})
        match = re.fullmatch(r'/threads/([1-9][0-9]{0,8})', path)
        if match:
            if set(query) - {'limit', 'after', 'lang'}:
                raise Rejected(400, 'unknown_query')
            limit = self._limit(query, 50, 100)
            lang = self._language(query)
            after = int(query.get('after', ['0'])[0])
            if not 0 <= after <= 999999999:
                raise Rejected(400, 'invalid_pagination')
            thread = self._thread(db, int(match[1]))
            if not (thread['status'] == 'published' or thread['author'] == actor or moderator):
                raise Rejected(404, 'thread_not_found')
            clause, values = ('1=1', []) if moderator else ("(status='published' OR author=?)", [actor])
            rows = db.execute('SELECT * FROM forum_posts WHERE thread=? AND id>? AND ' + clause + ' ORDER BY id LIMIT ?',
                              [thread['id'], after, *values, limit]).fetchall()
            items, cursor = self._page(rows, lambda row: self._public_post(db, row, moderator, lang), limit)
            data = {'thread': self._public_thread(db, thread, lang), 'posts': items, 'nextAfter': cursor}
            seen = self._seen(db, actor, thread['id'])
            if seen is not None:
                data['lastSeen'] = seen
                shown = [item['id'] for item in items if item['status'] == 'published']
                if shown and max(shown) > seen:
                    db.execute('INSERT INTO forum_reads(actor,thread,seen) VALUES(?,?,?) '
                               'ON CONFLICT(actor,thread) DO UPDATE SET seen=max(seen,excluded.seen)',
                               (actor, thread['id'], max(shown)))
            return CommunityResponse(200, data)
        if path == '/notifications':
            if not actor:
                raise Rejected(401, 'sign_in_required')
            if set(query) - {'limit', 'lang'}:
                raise Rejected(400, 'unknown_query')
            return CommunityResponse(200, self._notifications(db, actor, self._limit(query, 20, 50),
                                                              self._language(query)))
        if path == '/search':
            if set(query) - {'q', 'limit'}:
                raise Rejected(400, 'unknown_query')
            if not self.search_ready:
                raise Rejected(503, 'search_unavailable')
            words = re.findall(r'\w{2,40}', _text(query.get('q', [''])[0], 2, 200))[:8]
            if not words:
                raise Rejected(400, 'invalid_search')
            limit = self._limit(query, 20, 25)
            rows = db.execute("SELECT post,thread,title,snippet(forum_search,1,'','','…',16) AS excerpt "
                              'FROM forum_search WHERE forum_search MATCH ? ORDER BY rank LIMIT ?',
                              (' '.join('"%s"' % word for word in words), limit)).fetchall()
            return CommunityResponse(200, {'results': [{'post': row['post'], 'thread': row['thread'],
                'title': row['title'], 'excerpt': row['excerpt']} for row in rows]})
        if path == '/moderation':
            self._require(db, actor, 'moderator', 'admin')
            if set(query) - {'queue', 'limit', 'before'}:
                raise Rejected(400, 'unknown_query')
            queue = query.get('queue', ['people'])[0]
            limit = self._limit(query, 25, 50)
            before = int(query.get('before', ['999999999'])[0])
            where = {'people': "p.status='pending' AND p.review='people'",
                     'automatic': "p.status='pending' AND p.review IS NULL",
                     'hidden': "p.status='hidden'"}.get(queue)
            if where is None:
                raise Rejected(400, 'invalid_queue')
            rows = db.execute('SELECT p.* FROM forum_posts p WHERE ' + where + ' AND p.id<? ORDER BY p.id DESC LIMIT ?',
                              (before, limit)).fetchall()
            def convert(row):
                thread = self._thread(db, row['thread'])
                return {**self._public_post(db, row, True), 'threadTitle': thread['title'],
                        'category': thread['category'], 'opening': self._opening(db, row['thread']) == row['id']}
            items, cursor = self._page(rows, convert, limit)
            return CommunityResponse(200, {'queue': queue, 'posts': items, 'nextBefore': cursor,
                                           'visibility': 'moderator-private'})
        if path == '/profile':
            if query:
                raise Rejected(400, 'unexpected_query')
            if not actor:
                raise Rejected(401, 'sign_in_required')
            pending = db.execute("SELECT count(*) FROM forum_posts WHERE author=? AND status='pending'", (actor,)).fetchone()[0]
            return CommunityResponse(200, {'author': self._forum_author(db, actor), 'pendingPosts': pending,
                                           'publishesDirectly': moderator})
        raise Rejected(404, 'route_not_found')

    def _new_post(self, db, thread_id, actor, text, reply_to=None):
        if db.execute('SELECT count(*) FROM forum_posts').fetchone()[0] >= MAX_POSTS:
            raise Rejected(503, 'post_capacity_reached')
        moderator = self._moderates(db, actor)
        if not moderator and db.execute("SELECT count(*) FROM forum_posts WHERE author=? AND status='pending'",
                                        (actor,)).fetchone()[0] >= FORUM_PENDING:
            raise Rejected(429, 'pending_limit_reached')
        now = int(self.clock())
        status = 'published' if moderator else 'pending'
        post_id = db.execute('INSERT INTO forum_posts(thread,author,text,reply_to,status,created,updated) '
                             'VALUES(?,?,?,?,?,?,?)', (thread_id, actor, text, reply_to, status, now, now)).lastrowid
        return post_id, status

    def _forum_post(self, db, path, actor, body):
        match = re.fullmatch(r'/categories/([a-z]{2,20})/threads', path)
        if match:
            if match[1] not in FORUM_CATEGORIES:
                raise Rejected(404, 'category_not_found')
            _fields(body, {'title', 'text', 'subject'})
            title = ' '.join(_text(body.get('title'), 3, 200).split())
            text = _text(body.get('text'), 1, 8000)
            subject = body.get('subject')
            if subject is not None and (not isinstance(subject, str) or not re.fullmatch(FORUM_SUBJECT, subject)):
                raise Rejected(400, 'invalid_subject')
            if db.execute('SELECT count(*) FROM forum_threads').fetchone()[0] >= MAX_THREADS:
                raise Rejected(503, 'thread_capacity_reached')
            now = int(self.clock())
            thread_id = db.execute('INSERT INTO forum_threads(category,subject,title,author,status,created,bumped) '
                                   "VALUES(?,?,?,?,'pending',?,?)", (match[1], subject, title, actor, now, now)).lastrowid
            post_id, status = self._new_post(db, thread_id, actor, text)
            db.execute('UPDATE forum_threads SET status=? WHERE id=?', (status, thread_id))
            self._refresh(db, thread_id)
            self._audit(db, actor, 'forum_open_thread', thread_id, {'category': match[1], 'post': post_id, 'status': status})
            return CommunityResponse(201, {'thread': self._public_thread(db, self._thread(db, thread_id)),
                'post': self._public_post(db, self._forum_post_row(db, post_id)),
                'visibility': 'published' if status == 'published' else 'own-private'})
        match = re.fullmatch(r'/threads/([1-9][0-9]{0,8})/posts', path)
        if match:
            _fields(body, {'text', 'replyTo'})
            thread = self._thread(db, int(match[1]))
            moderator = self._moderates(db, actor)
            if thread['status'] != 'published' and not moderator:
                raise Rejected(404, 'thread_not_found')
            if thread['locked'] and not moderator:
                raise Rejected(409, 'thread_locked')
            text = _text(body.get('text'), 1, 8000)
            reply_to = body.get('replyTo')
            if reply_to is not None:
                if type(reply_to) is not int or not db.execute(
                        "SELECT 1 FROM forum_posts WHERE id=? AND thread=? AND status='published'",
                        (reply_to, thread['id'])).fetchone():
                    raise Rejected(400, 'invalid_reply')
            post_id, status = self._new_post(db, thread['id'], actor, text, reply_to)
            self._refresh(db, thread['id'])
            self._audit(db, actor, 'forum_reply', post_id, {'thread': thread['id'], 'status': status})
            return CommunityResponse(201, {'post': self._public_post(db, self._forum_post_row(db, post_id)),
                'visibility': 'published' if status == 'published' else 'own-private'})
        match = re.fullmatch(r'/posts/([1-9][0-9]{0,8})/moderation', path)
        if match:
            self._require(db, actor, 'moderator', 'admin')
            _fields(body, {'action', 'reason'})
            action, reason = body.get('action'), _text(body.get('reason'), 3, 1000)
            if action not in ('publish', 'hide'):
                raise Rejected(400, 'invalid_moderation_action')
            row = self._forum_post_row(db, int(match[1]))
            status = 'published' if action == 'publish' else 'hidden'
            self._set_post(db, row, status, 'people', reason)
            self._audit(db, actor, 'forum_' + action, row['id'], {'from': row['status'], 'to': status, 'reason': reason})
            return CommunityResponse(200, {'post': self._public_post(db, self._forum_post_row(db, row['id']), True)})
        match = re.fullmatch(r'/threads/([1-9][0-9]{0,8})/moderation', path)
        if match:
            self._require(db, actor, 'moderator', 'admin')
            _fields(body, {'action', 'reason'})
            action, reason = body.get('action'), _text(body.get('reason'), 3, 1000)
            if action not in ('lock', 'unlock'):
                raise Rejected(400, 'invalid_moderation_action')
            thread = self._thread(db, int(match[1]))
            db.execute('UPDATE forum_threads SET locked=? WHERE id=?', (int(action == 'lock'), thread['id']))
            self._audit(db, actor, 'forum_' + action, thread['id'], {'reason': reason})
            return CommunityResponse(200, {'thread': self._public_thread(db, self._thread(db, thread['id']))})
        if path == '/profile':
            _fields(body, {'name'})
            name = body.get('name')
            if not isinstance(name, str):
                raise Rejected(400, 'invalid_name')
            name = ' '.join(name.split())
            if not name:
                db.execute('DELETE FROM forum_names WHERE actor=?', (actor,))
            else:
                folded = name.casefold()
                if (not re.fullmatch(r'[^\W_][\w .\'-]{0,38}[^\W_]', name)
                        or folded in RESERVED_NAMES or folded.startswith(('участник', 'participant', 'member_'))):
                    raise Rejected(400, 'invalid_name')
                taken = db.execute('SELECT actor FROM forum_names WHERE folded=?', (folded,)).fetchone()
                if taken and taken[0] != actor:
                    raise Rejected(409, 'name_taken')
                db.execute('INSERT INTO forum_names VALUES(?,?,?,?) ON CONFLICT(actor) DO UPDATE SET '
                           'name=excluded.name,folded=excluded.folded,updated=excluded.updated',
                           (actor, name, folded, int(self.clock())))
            self._audit(db, actor, 'forum_name', actor, {'name': name or None})
            return CommunityResponse(200, {'author': self._forum_author(db, actor)})
        raise Rejected(404, 'route_not_found')

    def forum_review_queue(self, limit=20):
        """Posts waiting for the automatic moderator, oldest first. In-process only."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('limit must be 1..100')
        with self._db() as db:
            rows = db.execute("SELECT * FROM forum_posts WHERE status='pending' AND review IS NULL ORDER BY id LIMIT ?",
                              (limit,)).fetchall()
            out = []
            for row in rows:
                thread = self._thread(db, row['thread'])
                out.append({'id': row['id'], 'thread': row['thread'], 'category': thread['category'],
                            'title': thread['title'], 'opening': self._opening(db, row['thread']) == row['id'],
                            'text': row['text']})
            return out

    def forum_review(self, post_id, verdict, reason, reviewer):
        """Record the automatic moderator's verdict on one pending post.

        ``publish`` and ``hide`` take effect at once; ``escalate`` leaves the post pending
        in the people queue. A moderator can reverse any verdict. Returns False when the
        post was already decided, so a retried or concurrent worker changes nothing.
        """
        if verdict not in ('publish', 'hide', 'escalate'):
            raise ValueError('verdict must be publish, hide or escalate')
        if not isinstance(reviewer, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.:-]{2,79}', reviewer):
            raise ValueError('reviewer must name the model or rule set')
        reason = _text(reason, 3, 500)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM forum_posts WHERE id=?', (post_id,)).fetchone()
            if not row or row['status'] != 'pending' or row['review'] is not None:
                return False
            if verdict == 'escalate':
                db.execute("UPDATE forum_posts SET review='people',review_note=?,updated=? WHERE id=?",
                           (reason, int(self.clock()), row['id']))
            else:
                self._set_post(db, row, 'published' if verdict == 'publish' else 'hidden', 'automatic', reason)
            self._audit(db, 'automatic-moderator', 'forum_auto_' + verdict, row['id'],
                        {'reviewer': reviewer, 'reason': reason})
            return True

    # Machine translation of the forum (infra/forum_translator.py), in-process only like the
    # automatic moderator. Only published posts and titles of published threads are queued;
    # each translation is tied to the SHA-256 of the exact text it was made from.

    def forum_translation_queue(self, limit=20):
        """Published texts with no translation record yet, newest first."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('limit must be 1..100')
        with self._db() as db:
            rows = db.execute('''
                SELECT 'title' AS kind, t.id AS item, t.title AS text, t.category, t.title, t.created AS at
                FROM forum_threads t LEFT JOIN forum_languages l ON l.kind='title' AND l.item=t.id
                WHERE t.status='published' AND l.item IS NULL
                UNION ALL
                SELECT 'post', p.id, p.text, t.category, t.title, p.created
                FROM forum_posts p JOIN forum_threads t ON t.id=p.thread
                LEFT JOIN forum_languages l ON l.kind='post' AND l.item=p.id
                WHERE p.status='published' AND t.status='published' AND l.item IS NULL
                ORDER BY at DESC, kind DESC, item DESC LIMIT ?''', (limit,)).fetchall()
            return [{'kind': row['kind'], 'id': row['item'], 'category': row['category'],
                     'threadTitle': row['title'], 'text': row['text'], 'digest': _digest(row['text'])}
                    for row in rows]

    def forum_translation_record(self, kind, item, digest, translator, *, source=None, texts=None, note=None):
        """Store the translations of one published text, or why it has none.

        ``texts`` maps site languages to translated text; an empty map records that the
        text was skipped (nothing to translate, an unusable answer) so it is not retried.
        Returns False when the text is no longer published or changed meanwhile.
        """
        if kind not in ('post', 'title'):
            raise ValueError('kind must be post or title')
        if not isinstance(translator, str) or not re.fullmatch(TRANSLATOR, translator):
            raise ValueError('translator must name the model or rule set')
        if source is not None and (not isinstance(source, str) or not re.fullmatch(r'[a-z]{2,3}', source)):
            raise ValueError('source must be a language code')
        texts = dict(texts or {})
        if set(texts) - set(FORUM_LANGUAGES) or source in texts:
            raise ValueError('translations must target other site languages')
        texts = {lang: _text(text, 1, 16000 if kind == 'post' else 400) for lang, text in texts.items()}
        if note is not None:
            note = _text(note, 3, 300)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if kind == 'post':
                row = db.execute('SELECT p.text, p.status, t.status AS thread FROM forum_posts p '
                                 'JOIN forum_threads t ON t.id=p.thread WHERE p.id=?', (item,)).fetchone()
                current = row and row['status'] == 'published' and row['thread'] == 'published' and row['text']
            else:
                row = db.execute('SELECT title, status FROM forum_threads WHERE id=?', (item,)).fetchone()
                current = row and row['status'] == 'published' and row['title']
            if not current or _digest(current) != digest:
                return False
            self._forget_translations(db, kind, item)
            db.execute('INSERT INTO forum_languages(kind,item,digest,source,outcome,translator,note,created) '
                       'VALUES(?,?,?,?,?,?,?,?)', (kind, item, digest, source,
                       'translated' if texts else 'skipped', translator, note, int(self.clock())))
            db.executemany('INSERT INTO forum_translations(kind,item,lang,text) VALUES(?,?,?,?)',
                           [(kind, item, lang, text) for lang, text in sorted(texts.items())])
            return True
