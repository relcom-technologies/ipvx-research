"""Authentication is a fixed local boundary, not an arbitrary reverse proxy."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

spec = importlib.util.spec_from_file_location('public_auth_proxy', Path(__file__).resolve().parents[1] / 'infra/server.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class ProxyBoundary(unittest.TestCase):
    def setUp(self):
        self.calls = []
        calls = self.calls
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                calls.append((self.path, self.headers.get('Host'), self.headers.get('Cookie')))
                self.send_response(302)
                self.send_header('Location', 'https://id.relcom.com/oauth/v2/authorize')
                self.send_header('Set-Cookie', '__Host-first=one; Secure; HttpOnly; Path=/')
                self.send_header('Set-Cookie', '__Host-second=two; Secure; HttpOnly; Path=/')
                self.send_header('Cache-Control', 'private, no-store')
                self.send_header('Vary', 'Cookie')
                self.send_header('Retry-After', '30')
                self.end_headers()
        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        (root / 'index.html').write_text('public research')
        self.front = module.make_server(root, '127.0.0.1', 0, 'b' * 40, self.upstream.server_port)
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (self.upstream, self.front)]
        for thread in self.threads:
            thread.start()
        self.base = 'http://127.0.0.1:' + str(self.front.server_port)
        self.opener = urllib.request.build_opener(NoRedirect)

    def tearDown(self):
        for server, thread in zip((self.upstream, self.front), self.threads):
            server.shutdown()
            thread.join()
            server.server_close()
        self.directory.cleanup()

    def test_redirect_and_cookies_keep_their_security_headers(self):
        req = urllib.request.Request(self.base + '/auth/login?returnTo=%2Faccount.html',
                                     headers={'Host': 'ipvx.org', 'Cookie': 'browser=value'})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.opener.open(req)
        response = error.exception
        self.assertEqual(response.code, 302)
        self.assertEqual(len(response.headers.get_all('Set-Cookie')), 2)
        self.assertEqual(response.headers['Location'], 'https://id.relcom.com/oauth/v2/authorize')
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.headers['Vary'], 'Cookie')
        self.assertEqual(response.headers['Retry-After'], '30')
        self.assertEqual(response.headers.get_all('Referrer-Policy'), ['no-referrer'])
        self.assertEqual(self.calls, [('/auth/login?returnTo=%2Faccount.html', 'ipvx.org', 'browser=value')])
        response.close()

    def test_private_and_unknown_paths_never_reach_auth(self):
        for path, host, code in (('/auth/login', 'attacker.invalid', 400),
                                 ('/auth/unknown', 'ipvx.org', 404),
                                 ('/api/mesh', 'ipvx.org', 404),
                                 ('/.env', 'ipvx.org', 404)):
            with self.subTest(path=path):
                req = urllib.request.Request(self.base + path, headers={'Host': host})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self.opener.open(req)
                self.assertEqual(error.exception.code, code)
                error.exception.close()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
