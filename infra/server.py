"""Read-only public research files; no lab control or model execution endpoints."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action https://github.com; frame-ancestors 'none'"


class PublicFiles(BaseHTTPRequestHandler):
    server_version = 'IPvXResearch'
    sys_version = ''

    def log_message(self, *args):
        pass  # No visitor addresses or request contents in the service journal.

    def end_headers(self):
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
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


def make_server(root, bind, port, revision):
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
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--bind', default='10.10.50.131', choices=['10.10.50.131', '127.0.0.1'])
    parser.add_argument('--port', type=int, default=8092)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    make_server(args.root, args.bind, args.port, args.revision).serve_forever()
