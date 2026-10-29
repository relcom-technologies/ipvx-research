"""Public serving must never expose parent files, links or lab API routes."""
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

spec=importlib.util.spec_from_file_location('public_server',Path(__file__).resolve().parents[1]/'infra/server.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PublicBoundary(unittest.TestCase):
    def test_only_whitelisted_liaison_exports_can_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'public';root.mkdir();(root/'index.html').write_text('published');(root/'data').mkdir()
            (root/'data/liaison-status.json').write_text('{"state":"prepared"}')
            live=Path(directory)/'live';live.mkdir();(live/'liaison-status.json').write_text('{"state":"running"}')
            (live/'ledger.sqlite').write_text('private ledger')
            server=module.make_server(root,'127.0.0.1',0,'a'*40,liaison_public_dir=live)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with urllib.request.urlopen(base+'/data/liaison-status.json') as response:self.assertIn(b'running',response.read())
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'/data/ledger.sqlite')
                (live/'liaison-status.json').unlink();(live/'liaison-status.json').symlink_to(live/'ledger.sqlite')
                with urllib.request.urlopen(base+'/data/liaison-status.json') as response:self.assertIn(b'prepared',response.read())
            finally:server.shutdown();thread.join();server.server_close()

    def test_public_file_and_private_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'public';root.mkdir()
            (root/'index.html').write_text('published')
            (Path(directory)/'private.json').write_text('private')
            server=module.make_server(root,'127.0.0.1',0,'a'*40)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with urllib.request.urlopen(base+'/') as response:
                    self.assertEqual(response.read(),b'published')
                    self.assertEqual(response.headers['X-IPvX-Revision'],'a'*40)
                    self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
                for path in ('/../private.json','/%2e%2e/private.json','/.env','/api/mesh','/data/'):
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+path)
                    self.assertEqual(error.exception.code,404)
            finally:
                server.shutdown();thread.join();server.server_close()

    def test_symlink_release_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'index.html').write_text('published')
            (root/'escape').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):module.make_server(root,'127.0.0.1',0,'a'*40)

if __name__=='__main__':unittest.main()
