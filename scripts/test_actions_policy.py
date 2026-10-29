"""Actions validate pull requests without production access or merge hooks."""
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate(value, source):
    triggers = value.get('on', value.get(True))
    if isinstance(triggers, str):
        triggers = [triggers]
    assert set(triggers) == {'pull_request'}, 'Actions may only check pull requests'
    if isinstance(triggers, dict):
        config = triggers.get('pull_request') or {}
        assert set(config.get('types', ['opened', 'synchronize', 'reopened'])) <= {'opened', 'synchronize', 'reopened'}, 'No closed/merged PR production hook'
    assert value.get('permissions') == {'contents': 'read'}, 'No write-capable workflow'
    assert not re.search(r'secrets\.|\b(?:ssh|scp|ansible-playbook)\s|terraform\s+apply|gh\s+workflow\s+run|gh\s+release\s+', source), 'Production operation is forbidden'
    for job in value['jobs'].values():
        assert not job.get('environment'), 'No production environment'
        assert isinstance(job['runs-on'], str) and job['runs-on'].startswith('ubuntu-'), 'Isolated hosted development runner required'


class ActionsPolicy(unittest.TestCase):
    def test_all_workflows_are_isolated_readonly_pr_checks(self):
        files = list((ROOT / '.github/workflows').glob('*.yml'))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.name):
                source = path.read_text()
                validate(yaml.safe_load(source), source)

    def test_rejects_all_other_triggers_and_merge_events(self):
        for trigger in ['push', 'schedule', 'workflow_dispatch', 'workflow_run', 'issues', 'issue_comment', 'pull_request_target']:
            value = {'on': [trigger], 'permissions': {'contents': 'read'}, 'jobs': {}}
            with self.assertRaises(AssertionError):
                validate(value, '')
        with self.assertRaises(AssertionError):
            validate({'on': {'pull_request': {'types': ['closed']}}, 'permissions': {'contents': 'read'}, 'jobs': {}}, '')
