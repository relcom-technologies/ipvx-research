import errno
import html
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from history_sources import render_history_source


REPOSITORY = 'https://github.com/relcom-technologies/ipvx-research'


class HistorySources(unittest.TestCase):
    def test_linux_overlong_unicode_evidence_remains_escaped_plain_text(self):
        source = 'Сохранность проверена ' * 20 + '<evidence>'
        self.assertGreater(len(source.encode()), 255)
        with patch.object(Path, 'is_file', side_effect=OSError(errno.ENAMETOOLONG, 'File name too long')):
            result = render_history_source(Path('/repo'), source, REPOSITORY)
        self.assertEqual(result, '<li>' + html.escape(source) + '</li>')
        self.assertNotIn('<a ', result)

    def test_existing_relative_file_keeps_repository_link(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'record.md').write_text('original evidence')
            self.assertEqual(render_history_source(root, 'record.md', REPOSITORY),
                             '<li><a href="' + REPOSITORY + '/blob/main/record.md">record.md</a></li>')
            self.assertEqual((root / 'record.md').read_text(), 'original evidence')

    def test_supported_web_reference_keeps_escaped_link(self):
        source = REPOSITORY + '/pull/40?a=1&b=2'
        self.assertEqual(render_history_source(Path('/repo'), source, REPOSITORY),
                         '<li><a href="' + html.escape(source, quote=True) + '">' + html.escape(source) + '</a></li>')

    def test_non_path_reference_is_plain_text(self):
        with tempfile.TemporaryDirectory() as folder:
            for source in ['unpublished <note>', 'invalid\0path']:
                with self.subTest(source=source):
                    self.assertEqual(render_history_source(Path(folder), source, REPOSITORY),
                                     '<li>' + html.escape(source) + '</li>')


if __name__ == '__main__':
    unittest.main()
