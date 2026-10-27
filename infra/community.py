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
            ''')
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
                elif re.fullmatch(PREFIX + r'/entries/([1-9][0-9]{0,8})/moderation', target.path):
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
                'capabilities': ['submit_pending', 'advisory_vote'] if actor and not blocked else []})
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
