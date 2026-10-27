"""Public research files and a bounded local sign-in proxy; no lab control API."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self' https://press.relcom.com; object-src 'none'; base-uri 'none'; form-action 'self' https://github.com https://id.relcom.com; frame-ancestors 'none'"
AUTH_PATHS = {'/auth/login', '/auth/callback', '/auth/session', '/auth/logout'}
COMMUNITY_PATH = re.compile(r'/community/v1/(?:session|moderation|audit|roles|rfcs/rfc-000[1-7]/entries|entries/[1-9][0-9]{0,8}(?:/vote|/moderation)?)')


class PublicFiles(BaseHTTPRequestHandler):
    server_version = 'IPvXResearch'
    sys_version = ''

    def log_message(self, *args):
        pass  # No visitor addresses or request contents in the service journal.

    def end_headers(self):
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer' if getattr(self, 'auth_response', False)
                         else 'strict-origin-when-cross-origin')
        self.send_header('X-IPvX-Revision', self.server.revision)
        super().end_headers()

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        try:
            path = unquote(urlsplit(self.path).path, errors='strict')
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        if path in AUTH_PATHS or COMMUNITY_PATH.fullmatch(path):
            if path != urlsplit(self.path).path:
                self.send_error(404)
                return
            self.proxy_auth('HEAD' if head else 'GET')
            return
        if path == '/healthz':
            data = json.dumps({'status': 'ok', 'revision': self.server.revision}).encode()
            content_type = 'application/json'
        else:
            relative = 'index.html' if path == '/' else path.lstrip('/')
            parts = Path(relative).parts
            candidate = self.server.root / relative
            if (not parts or any(p.startswith('.') for p in parts) or '\\' in path
                    or candidate.resolve() not in self.server.public_files):
                self.send_error(404)
                return
            data = candidate.read_bytes()
            content_type = mimetypes.guess_type(relative)[0] or 'application/octet-stream'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != '/auth/logout' and not COMMUNITY_PATH.fullmatch(path):
            self.send_error(404)
            return
        self.proxy_auth('POST')

    def proxy_auth(self, method):
        """Only the fixed, loopback authentication process receives these requests."""
        if not self.server.auth_port:
            self.send_error(503, 'Sign-in is available on the public production portal')
            return
        try:
            lengths = self.headers.get_all('Content-Length', [])
            size = int(lengths[0]) if lengths else 0
            maximum = 12000 if self.path.startswith('/community/') else 1024
            if len(lengths) > 1 or size < 0 or size > maximum or self.headers.get('Transfer-Encoding'):
                raise ValueError('Unsupported body')
        except ValueError:
            self.send_error(400)
            return
        host = self.headers.get('Host', '').lower()
        if host not in ('ipvx.org', 'www.ipvx.org'):
            self.send_error(400, 'Unexpected portal host')
            return
        body = self.rfile.read(size) if size else b''
        headers = {name: self.headers[name] for name in
                   ('Cookie', 'Content-Type', 'Origin', 'Sec-Fetch-Site', 'Idempotency-Key') if name in self.headers}
        headers['Host'] = host
        conn = HTTPConnection('127.0.0.1', self.server.auth_port, timeout=35)
        try:
            conn.request(method, self.path, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read(131073)
            if len(data) > 131072:
                raise ValueError('Authentication response exceeds its bound')
            self.auth_response = True
            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() in ('content-type', 'set-cookie', 'location', 'cache-control', 'pragma',
                                    'vary', 'retry-after', 'allow'):
                    self.send_header(name, value)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            if method != 'HEAD':
                self.wfile.write(data)
        except (OSError, ValueError):
            self.send_error(503, 'Sign-in temporarily unavailable')
        finally:
            conn.close()


def make_server(root, bind, port, revision, auth_port=None):
    root = Path(root).resolve()
    files = set()
    for file in root.rglob('*'):
        if file.is_symlink():
            raise ValueError('Public release contains a symbolic link')
        if file.is_file():
            files.add(file.resolve())
    if root / 'index.html' not in files or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Incomplete or unversioned public release')
    server = ThreadingHTTPServer((bind, port), PublicFiles)
    server.root, server.public_files, server.revision = root, files, revision
    server.auth_port = auth_port
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--bind', default='10.10.50.131', choices=['10.10.50.131', '127.0.0.1'])
    parser.add_argument('--port', type=int, default=8092)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--auth-port', type=int, choices=[8094])
    args = parser.parse_args()
    make_server(args.root, args.bind, args.port, args.revision, args.auth_port).serve_forever()
