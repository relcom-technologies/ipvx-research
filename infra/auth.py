"""Relcom ID sign-in for the research portal; no governance or lab permissions.

The public file server may call AuthService.handle before its static dispatch.
No password, provider token or private identity is exposed by the session endpoint.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from authlib.integrations.requests_client import OAuth2Session
from authlib.oidc.core import CodeIDToken
from cryptography.fernet import Fernet, InvalidToken
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, MissingKeyError
from joserfc.jwk import KeySet
import requests

ISSUER = 'https://id.relcom.com'
ORIGIN = 'https://ipvx.org'
POST_LOGOUT_URI = ORIGIN + '/account.html'
ORG_CLAIM = 'urn:zitadel:iam:user:resourceowner:id'
TX_COOKIE = '__Host-ipvx_login'
SESSION_COOKIE = '__Host-ipvx_session'
TX_SECONDS = 600
SESSION_SECONDS = 3600
RECHECK_SECONDS = 600
MAX_JSON = 131072
COMMUNITY_ROUTE = re.compile(r'/community/v1/(?:session|moderation|audit|roles|members(?:/member_[a-f0-9]{24}/access)?|rfcs/rfc-000[1-7]/entries|entries/[1-9][0-9]{0,8}(?:/vote|/moderation)?)')


class AuthFailure(Exception):
    """Expected rejected authentication, without including provider responses."""


class ProviderUnavailable(Exception):
    """Temporary upstream problem; never return token/provider error details."""


@dataclass
class AuthResponse:
    status: int
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b''


def _response(status, value=None, headers=()):
    body = b'' if value is None else json.dumps(value, ensure_ascii=False).encode()
    return AuthResponse(status, [
        ('Content-Type', 'application/json; charset=utf-8'),
        ('Cache-Control', 'private, no-store'),
        ('Pragma', 'no-cache'),
        ('Referrer-Policy', 'no-referrer'),
        ('Vary', 'Cookie'),
        *headers,
    ], body)


def _cookie(name, value, seconds):
    return ('Set-Cookie', f'{name}={value}; Max-Age={seconds}; Path=/; Secure; HttpOnly; SameSite=Lax')


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _local_path(value):
    if (not isinstance(value, str) or len(value) > 1000 or not value.startswith('/')
            or value.startswith('//') or any(ord(c) <= 32 or ord(c) == 127 or c == '\\' for c in value)):
        return '/'
    u = urlsplit(value)
    return value if not u.scheme and not u.netloc else '/'


class RelcomProvider:
    """Pinned issuer with standard Authlib PKCE and JOSE verification."""

    def __init__(self, client_id, org_id):
        self.client_id, self.org_id = client_id, org_id
        self._keys = None
        self._keys_at = 0
        self._key_lock = threading.Lock()

    def authorization(self, state, nonce, verifier, register=False):
        client = OAuth2Session(
            self.client_id, token_endpoint_auth_method='none',
            redirect_uri=ORIGIN + '/auth/callback', code_challenge_method='S256',
            scope=f'openid profile email urn:zitadel:iam:org:id:{self.org_id} '
                  'urn:zitadel:iam:user:resourceowner',
        )
        try:
            url, _ = client.create_authorization_url(
                ISSUER + '/oauth/v2/authorize', state=state, nonce=nonce,
                code_verifier=verifier, **({'prompt': 'create'} if register else {}),
            )
            return url
        finally:
            client.close()

    def _json(self, response):
        if response.status_code >= 500 or response.status_code == 429:
            raise ProviderUnavailable()
        if not response.ok:
            raise AuthFailure()
        raw = response.raw.read(MAX_JSON + 1, decode_content=True)
        if len(raw) > MAX_JSON:
            raise ProviderUnavailable()
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError) as exc:
            raise ProviderUnavailable() from exc

    def _get_json(self, path, token=None):
        try:
            with requests.get(
                ISSUER + path, headers={'Authorization': 'Bearer ' + token} if token else {},
                timeout=(4, 6), allow_redirects=False, stream=True,
            ) as response:
                return self._json(response)
        except requests.RequestException as exc:
            raise ProviderUnavailable() from exc
        except (AuthFailure, ProviderUnavailable):
            raise
        except Exception as exc:
            raise ProviderUnavailable() from exc

    def _jwks(self, force=False):
        with self._key_lock:
            if force or self._keys is None or time.time() - self._keys_at > 300:
                try:
                    self._keys = KeySet.import_key_set(self._get_json('/oauth/v2/keys'))
                    self._keys_at = time.time()
                except (AuthFailure, ValueError) as exc:
                    raise ProviderUnavailable() from exc
            return self._keys

    def validate_id_token(self, encoded, nonce, access_token, *, now=None):
        if not isinstance(encoded, str) or len(encoded) > 16384:
            raise AuthFailure()
        # No algorithm is taken from untrusted token content outside this allowlist.
        try:
            try:
                verified = jwt.decode(encoded, self._jwks(), algorithms=['RS256', 'ES256', 'EdDSA'])
            except (InvalidKeyIdError, MissingKeyError):
                verified = jwt.decode(encoded, self._jwks(force=True), algorithms=['RS256', 'ES256', 'EdDSA'])
            claims = CodeIDToken(
                verified.claims, verified.header,
                options={'iss': {'essential': True, 'value': ISSUER},
                         'aud': {'essential': True, 'value': self.client_id}},
                params={'client_id': self.client_id, 'nonce': nonce, 'access_token': access_token},
            )
            claims.validate(now=now, leeway=15)
            if (claims.get(ORG_CLAIM) != self.org_id or claims.get('email_verified') is not True
                    or not isinstance(claims.get('sub'), str) or not claims['sub']
                    or not isinstance(claims.get('email'), str) or not claims['email']):
                raise AuthFailure()
            return {'sub': claims['sub'], 'email': claims['email'][:320],
                    'name': str(claims.get('name') or '')[:200], 'emailVerified': True}
        except ProviderUnavailable:
            raise
        except Exception as exc:
            # JOSE exceptions must never leak token strings or claim values into a response.
            raise AuthFailure() from exc

    def exchange(self, code, verifier, nonce):
        client = OAuth2Session(self.client_id, token_endpoint_auth_method='none',
                               redirect_uri=ORIGIN + '/auth/callback', default_timeout=(4, 6))
        def check_response(response):
            if response.status_code >= 500 or response.status_code == 429 or len(response.content) > MAX_JSON:
                raise ProviderUnavailable()
            return response
        client.register_compliance_hook('access_token_response', check_response)
        try:
            tokens = client.fetch_token(ISSUER + '/oauth/v2/token', code=code,
                                        code_verifier=verifier, grant_type='authorization_code', allow_redirects=False)
            if not isinstance(tokens.get('access_token'), str) or len(tokens['access_token']) > 16384:
                raise AuthFailure()
            user = self.validate_id_token(tokens.get('id_token'), nonce, tokens['access_token'])
            lifetime = max(1, min(SESSION_SECONDS, int(tokens.get('expires_in', SESSION_SECONDS))))
            return user, {'access_token': tokens['access_token'], 'id_token': tokens['id_token']}, lifetime
        except requests.RequestException as exc:
            raise ProviderUnavailable() from exc
        except (AuthFailure, ProviderUnavailable):
            raise
        except Exception as exc:
            raise AuthFailure() from exc
        finally:
            client.close()

    def recheck(self, credentials, user):
        info = self._get_json('/oidc/v1/userinfo', credentials['access_token'])
        if (info.get('sub') != user['sub'] or info.get('email_verified') is not True
                or (ORG_CLAIM in info and info[ORG_CLAIM] != self.org_id)):
            raise AuthFailure()

    def logout_url(self, credentials):
        # This is the standard RP-initiated logout hint. It is sent only in a browser redirect,
        # never in the public session JSON, logs or saved research history.
        return ISSUER + '/oidc/v1/end_session?' + urlencode({
            'id_token_hint': credentials['id_token'], 'client_id': self.client_id,
            'post_logout_redirect_uri': POST_LOGOUT_URI,
        })


class AuthService:
    def __init__(self, client_id, org_id, state_dir, *, provider=None, clock=time.time, community=None):
        if not client_id or not org_id or len(client_id) > 150 or len(org_id) > 150:
            raise ValueError('Relcom ID public client and pool IDs are required')
        self.provider = provider or RelcomProvider(client_id, org_id)
        self.binding = _hash(client_id + ':' + org_id)
        self.clock = clock
        self.community = community
        directory = Path(state_dir)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('Authentication state must be a private directory')
        os.chmod(directory, 0o700)
        key_path = directory / 'cookie.key'
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(Fernet.generate_key())
        if (key_path.is_symlink() or not stat.S_ISREG(key_path.stat().st_mode)
                or stat.S_IMODE(key_path.stat().st_mode) != 0o600):
            raise ValueError('Authentication key must be a regular private file')
        self.cipher = Fernet(key_path.read_bytes())
        self.database = directory / 'sessions.sqlite3'
        if self.database.is_symlink():
            raise ValueError('Authentication database must be a regular private file')
        # Create with private permissions before SQLite opens it; WAL files inherit that mode.
        fd = os.open(self.database, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        os.chmod(self.database, 0o600)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS state (kind TEXT, id TEXT PRIMARY KEY, value BLOB, expires INTEGER)')
        self._lock = threading.Lock()
        self._login_times = []

    @classmethod
    def from_environment(cls):
        client, org = os.environ.get('RELCOM_ID_CLIENT_ID'), os.environ.get('RELCOM_ID_ORG_ID')
        if not client and not org:
            return None
        if not client or not org:
            raise ValueError('Incomplete Relcom ID configuration')
        community = None
        if os.environ.get('IPVX_COMMUNITY_STATE_DIR'):
            from community import CommunityService
            community = CommunityService(os.environ['IPVX_COMMUNITY_STATE_DIR'],
                bootstrap_admin_author_id=os.environ.get('IPVX_COMMUNITY_ADMIN_AUTHOR_ID'))
        return cls(client, org, os.environ.get('IPVX_AUTH_STATE_DIR', '/var/lib/ipvx-research/auth'),
                   community=community)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.execute('PRAGMA busy_timeout=5000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _write(self, kind, key, value, expires):
        encoded = self.cipher.encrypt(json.dumps({**value, '_binding': self.binding}).encode())
        with self._db() as db:
            db.execute('DELETE FROM state WHERE expires < ?', (int(self.clock()),))
            if db.execute('SELECT count(*) FROM state').fetchone()[0] >= 10000:
                raise ProviderUnavailable()
            db.execute('INSERT OR REPLACE INTO state VALUES (?,?,?,?)', (kind, _hash(key), encoded, expires))

    def _read(self, kind, key, consume=False):
        if not key or len(key) > 128:
            return None
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT value, expires FROM state WHERE kind=? AND id=?', (kind, _hash(key))).fetchone()
            if consume or (row and row[1] <= self.clock()):
                db.execute('DELETE FROM state WHERE id=?', (_hash(key),))
            if not row or row[1] <= self.clock():
                return None
        try:
            value = json.loads(self.cipher.decrypt(row[0]))
        except (InvalidToken, ValueError, UnicodeError):
            with self._db() as db:
                db.execute('DELETE FROM state WHERE id=?', (_hash(key),))
            return None
        if value.pop('_binding', None) != self.binding:
            with self._db() as db:
                db.execute('DELETE FROM state WHERE id=?', (_hash(key),))
            return None
        return value

    def _cookies(self, headers):
        try:
            raw = headers.get('Cookie', '')
            if len(raw) > 8192:
                return {}
            parsed = SimpleCookie(raw)
            return {key: value.value for key, value in parsed.items()}
        except Exception:
            return {}

    def _session(self, headers):
        key = self._cookies(headers).get(SESSION_COOKIE)
        data = self._read('session', key)
        if data and self.clock() - data['checked'] >= RECHECK_SECONDS:
            try:
                self.provider.recheck(data['credentials'], data['user'])
            except AuthFailure:
                self._read('session', key, consume=True)
                return None, None
            data['checked'] = int(self.clock())
            encoded = self.cipher.encrypt(json.dumps({**data, '_binding': self.binding}).encode())
            with self._db() as db:
                updated = db.execute('UPDATE state SET value=? WHERE kind=? AND id=? AND expires>?',
                                     (encoded, 'session', _hash(key), int(self.clock()))).rowcount
            # A concurrent logout must not be undone by a slower provider recheck.
            if not updated:
                return None, None
        return key, data

    def handle(self, method, path, headers, body=b''):
        target = urlsplit(path)
        if target.path.startswith('/community/'):
            return self.handle_community(method, path, headers, body)
        if target.path not in ('/auth/login', '/auth/callback', '/auth/session', '/auth/logout'):
            return None
        # The front server must pass the request's real Host. It must not use an untrusted
        # X-Forwarded-Host or an Origin-derived host. Only the canonical HTTPS site owns cookies.
        if headers.get('Host', '').lower() != 'ipvx.org':
            return _response(400, {'error': 'canonical_origin_required'})
        allowed = {'/auth/login': 'GET', '/auth/callback': 'GET', '/auth/session': 'GET', '/auth/logout': 'POST'}
        if method != allowed[target.path]:
            return _response(405, {'error': 'method_not_allowed'}, [('Allow', allowed[target.path])])
        try:
            if len(target.query) > 4096:
                raise AuthFailure()
            try:
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=10)
            except ValueError as exc:
                raise AuthFailure() from exc
            if any(len(values) != 1 for values in query.values()):
                raise AuthFailure()
            if target.path == '/auth/login':
                if set(query) - {'returnTo', 'register'}:
                    raise AuthFailure()
                # One process serves this sidecar. Bound state creation without retaining IPs.
                with self._lock:
                    now = self.clock()
                    self._login_times = [stamp for stamp in self._login_times if now - stamp < 60]
                    if len(self._login_times) >= 120:
                        return _response(429, {'error': 'try_again_later'}, [('Retry-After', '60')])
                    self._login_times.append(now)
                state, nonce, verifier, cookie = (secrets.token_urlsafe(32) for _ in range(4))
                pending = {'state': state, 'nonce': nonce, 'verifier': verifier,
                           'returnTo': _local_path(query.get('returnTo', ['/'])[0])}
                self._write('transaction', cookie, pending, int(self.clock()) + TX_SECONDS)
                location = self.provider.authorization(state, nonce, verifier, query.get('register') == ['1'])
                return _response(302, headers=[('Location', location), _cookie(TX_COOKIE, cookie, TX_SECONDS)])
            if target.path == '/auth/callback':
                if set(query) - {'code', 'state', 'iss', 'session_state', 'error', 'error_description'}:
                    raise AuthFailure()
                pending = self._read('transaction', self._cookies(headers).get(TX_COOKIE), consume=True)
                if (not pending or 'error' in query or not secrets.compare_digest(pending['state'], query.get('state', [''])[0])
                        or ('iss' in query and query['iss'] != [ISSUER])):
                    raise AuthFailure()
                code = query.get('code', [''])[0]
                if not code or len(code) > 2000:
                    raise AuthFailure()
                user, credentials, lifetime = self.provider.exchange(code, pending['verifier'], pending['nonce'])
                key = secrets.token_urlsafe(32)
                expires = int(self.clock()) + min(lifetime, SESSION_SECONDS)
                self._write('session', key, {'user': user, 'credentials': credentials,
                                             'checked': int(self.clock()), 'expires': expires}, expires)
                previous = self._cookies(headers).get(SESSION_COOKIE)
                if previous:
                    self._read('session', previous, consume=True)
                return _response(303, headers=[('Location', pending['returnTo']), _cookie(TX_COOKIE, '', 0),
                                               _cookie(SESSION_COOKIE, key, min(lifetime, SESSION_SECONDS))])
            if target.path == '/auth/session':
                if query:
                    raise AuthFailure()
                _, data = self._session(headers)
                return _response(200, {'authenticated': bool(data), 'user': data['user'] if data else None,
                                       'expiresAt': datetime.fromtimestamp(data['expires'], timezone.utc).isoformat() if data else None,
                                       'membership': 'not_granted_by_sign_in'})
            if headers.get('Origin') != ORIGIN or len(body) > 1024 or query:
                return _response(403, {'error': 'origin_required'})
            key = self._cookies(headers).get(SESSION_COOKIE)
            data = self._read('session', key, consume=True)
            location = self.provider.logout_url(data['credentials']) if data else '/'
            return _response(303, headers=[('Location', location), _cookie(SESSION_COOKIE, '', 0), _cookie(TX_COOKIE, '', 0)])
        except AuthFailure:
            if target.path == '/auth/callback':
                return _response(303, headers=[('Location', '/account.html?auth=error'), _cookie(TX_COOKIE, '', 0)])
            return _response(400, {'error': 'sign_in_rejected'}, [_cookie(TX_COOKIE, '', 0)])
        except (ProviderUnavailable, sqlite3.Error):
            if target.path == '/auth/callback':
                return _response(303, headers=[('Location', '/account.html?auth=unavailable'),
                                               _cookie(TX_COOKIE, '', 0), ('Retry-After', '30')])
            return _response(503, {'error': 'authentication_temporarily_unavailable'}, [('Retry-After', '30')])

    def handle_community(self, method, path, headers, body=b''):
        """Only verified server-side identity reaches the bounded discussion store."""
        target = urlsplit(path)
        if not COMMUNITY_ROUTE.fullmatch(target.path) or len(path) > 1500:
            return _response(404, {'error': 'not_found'})
        if headers.get('Host', '').lower() != 'ipvx.org':
            return _response(400, {'error': 'canonical_origin_required'})
        if method not in ('GET', 'POST'):
            return _response(405, {'error': 'method_not_allowed'}, [('Allow', 'GET, POST')])
        if self.community is None:
            return _response(503, {'error': 'community_not_configured'})
        if method == 'POST':
            if (headers.get('Origin') != ORIGIN
                    or headers.get('Sec-Fetch-Site', 'same-origin') != 'same-origin'):
                return _response(403, {'error': 'same_origin_required'})
            if headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                return _response(415, {'error': 'json_required'})
        if len(body) > 12000:
            return _response(413, {'error': 'body_too_large'})
        try:
            # Query/header/body cannot supply the user or roles. A stale/revoked
            # provider session is checked by the same path as /auth/session.
            _, session = self._session(headers)
            user = session['user'] if session else None
            parsed = None
            if method == 'POST':
                def unique_pairs(pairs):
                    value = {}
                    for key, item in pairs:
                        if key in value:
                            raise ValueError('duplicate JSON key')
                        value[key] = item
                    return value
                def reject_constant(value):
                    raise ValueError('non-JSON constant')
                parsed = json.loads(body.decode('utf-8'), object_pairs_hook=unique_pairs,
                                    parse_constant=reject_constant)
                if not isinstance(parsed, dict):
                    raise ValueError('JSON object required')
            elif body:
                return _response(400, {'error': 'unexpected_body'})
            result = self.community.handle(method, path, user, parsed,
                                           request_id=headers.get('Idempotency-Key'))
            return _response(result.status, result.data) if result else _response(404, {'error': 'not_found'})
        except (UnicodeError, ValueError, RecursionError):
            return _response(400, {'error': 'invalid_json'})
        except AuthFailure:
            return _response(401, {'error': 'sign_in_required'})
        except (ProviderUnavailable, sqlite3.Error):
            return _response(503, {'error': 'community_temporarily_unavailable'}, [('Retry-After', '30')])


def make_auth_server(service, port=8094):
    """Loopback-only adapter for the exact auth and community route allowlist.

    Forward the original Host, Cookie and Origin, and return every Set-Cookie separately.
    Neither visitor request URLs nor provider credentials enter the service journal.
    """
    class Handler(BaseHTTPRequestHandler):
        server_version = 'IPvXIdentity'
        sys_version = ''

        def log_message(self, *args):
            pass

        def _handle(self):
            self.close_connection = True
            lengths = self.headers.get_all('Content-Length', [])
            try:
                if self.headers.get('Transfer-Encoding') or len(lengths) > 1:
                    raise ValueError()
                length = int(lengths[0]) if lengths else 0
                maximum = 12000 if self.path.startswith('/community/') else 1024
                if length < 0 or length > maximum or len(self.path) > 5000:
                    raise ValueError()
            except ValueError:
                response = _response(413, {'error': 'request_too_large'})
            else:
                body = self.rfile.read(length) if length else b''
                response = service.handle(self.command, self.path, self.headers, body)
                if response is None:
                    response = _response(404, {'error': 'not_found'})
            self.send_response(response.status)
            for key, value in response.headers:
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(response.body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
            self.send_header('Connection', 'close')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(response.body)

        do_GET = do_POST = do_HEAD = do_PUT = do_DELETE = _handle

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    service = AuthService.from_environment()
    if service is None:
        raise SystemExit('Configure RELCOM_ID_CLIENT_ID and RELCOM_ID_ORG_ID first')
    make_auth_server(service).serve_forever()
