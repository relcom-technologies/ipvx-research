"""Source scope of the runner: what is pinned and what triggers its CI. Reads files only."""
import re
import unittest

from runners.bcp02.common import ROOT, in_scope, read_json

MANIFEST = read_json(ROOT / 'runners/bcp02/manifest.json')


class Scope(unittest.TestCase):
    def test_every_pin_is_inside_the_scope(self):
        outside = [name for name in MANIFEST['files'] if not in_scope(name, MANIFEST['scope'])]
        self.assertEqual(outside, [])

    def test_site_and_forum_files_are_not_pinned(self):
        for name in MANIFEST['files']:
            self.assertFalse(name.startswith(('assets/', 'infra/', 'scripts/', 'services/', 'data/')), name)

    def test_the_run_depends_on_pinned_sources(self):
        for name in ('runners/bcp02/cli.py', 'runners/bcp02/admission.py', 'bcp/core.py', 'bcp/wire.py',
                     'adapters/bcp02/binding.py', 'integration/bcp02/runtime.py',
                     'contracts/bcp02/src/NodeRegistry.sol', 'experiments/bcp02-net-001/protocol.json',
                     '.github/workflows/bcp-runner.yml'):
            self.assertIn(name, MANIFEST['files'])

    def test_a_change_to_any_pinned_file_runs_the_runner_checks(self):
        workflow = (ROOT / '.github/workflows/bcp-runner.yml').read_text()
        paths = re.search(r"pull_request:\s*\n\s*paths: \[(.*?)\]", workflow).group(1)
        self.assertEqual([p.strip().strip("'") for p in paths.split(',')], MANIFEST['scope'])

    def test_scope_matching(self):
        scope = MANIFEST['scope']
        self.assertTrue(in_scope('runners/bcp02/tests/test_scope.py', scope))
        self.assertTrue(in_scope('.github/workflows/bcp-runner.yml', scope))
        self.assertFalse(in_scope('.github/workflows/browser.yml', scope))
        self.assertFalse(in_scope('assets/portal.css', scope))
        self.assertFalse(in_scope('docs/proposals/bcp-minimal-0.1.md', scope))


if __name__ == '__main__':
    unittest.main()
