import hashlib
from pathlib import Path
import tempfile
import unittest
from build_languages import fingerprint_assets


class ResourceVersions(unittest.TestCase):
    def test_content_change_invalidates_cached_url_without_changing_evidence_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'assets/en').mkdir(parents=True);(root/'data/downloads').mkdir(parents=True)
            script=root/'assets/en/portal.js';script.write_text('old code')
            archive=root/'data/downloads/history.zip';archive.write_bytes(b'old evidence bundle')
            page=root/'example.en.html';page.write_text('<script src="assets/en/portal.js"></script><a href="data/downloads/history.zip">ZIP</a><a href="data/evidence.json">Evidence</a><a href="https://example.org/app.js">External</a>')
            fingerprint_assets(root);before=page.read_text();fingerprint_assets(root)
            self.assertEqual(before,page.read_text())
            self.assertIn('assets/en/portal.js?v='+hashlib.sha256(script.read_bytes()).hexdigest()[:16],before)
            self.assertIn('data/downloads/history.zip?v='+hashlib.sha256(archive.read_bytes()).hexdigest()[:16],before)
            self.assertIn('href="data/evidence.json"',before);self.assertIn('href="https://example.org/app.js"',before)
            script.write_text('new code');fingerprint_assets(root)
            self.assertNotEqual(before,page.read_text())
            self.assertIn('assets/en/portal.js?v='+hashlib.sha256(script.read_bytes()).hexdigest()[:16],page.read_text())

    def test_resource_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'assets').mkdir();(root/'index.html').write_text('<script src="assets/../../outside.js"></script>')
            with self.assertRaises(ValueError):fingerprint_assets(root)


if __name__=='__main__':unittest.main()
