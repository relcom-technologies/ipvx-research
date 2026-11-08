"""Owner signing and stand launch steps with temp files and a recorded fake executor only."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runners.bcp02 import owner, stand_launch
from runners.bcp02.admission import verify_permit, source_revision
from runners.bcp02.common import Blocked, sha

T0 = 1_800_000_000
SCOPE = 'a' * 64
DATASET = dict(run_id='bcp-net001-run-0001', dataset_sha256='b' * 64, bundle_sha256='c' * 64,
               created_at=T0, expires_at=T0 + 1776, max_state_age_seconds=1800)


def payload(**changes):
    p = dict(version=2, scope_sha256=SCOPE, run_id=DATASET['run_id'], host_image_sha256='d' * 64,
             not_before=T0 + 60, not_after=T0 + 1776, launch=True, transactions=0, production=False, dataset=dict(DATASET))
    p.update(changes)
    return p


class Owner(unittest.TestCase):
    def test_signed_request_is_accepted_by_the_runner(self):
        with tempfile.TemporaryDirectory() as d:
            public = owner.keygen(Path(d, 'k.pem'), 'correct horse battery')
            self.assertEqual(os.stat(Path(d, 'k.pem')).st_mode & 0o777, 0o600)
            key = owner.load_key(Path(d, 'k.pem'), 'correct horse battery')
            doc = owner.sign(key, owner.check_request(payload(), now=T0))
            with patch('runners.bcp02.dataset.fresh'):
                checked = verify_permit(doc, public, scope=SCOPE, now=T0 + 120)
            self.assertEqual(checked['run_id'], DATASET['run_id'])

    def test_key_file_is_encrypted_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            owner.keygen(Path(d, 'k.pem'), 'correct horse battery')
            self.assertIn(b'ENCRYPTED', Path(d, 'k.pem').read_bytes())
            with self.assertRaises(Blocked):owner.keygen(Path(d, 'k.pem'), 'correct horse battery')
            with self.assertRaises(Blocked):owner.keygen(Path(d, 'short.pem'), 'short')

    def test_requests_outside_the_v2_contract_are_refused(self):
        bad = [payload(transactions=1), payload(production=True), payload(launch=False), payload(version=1),
               payload(not_after=T0 + 1777), payload(not_before=T0 - 1), payload(run_id='bcp-net001-run-0002'),
               dict(payload(), extra=1), payload(scope_sha256='A' * 64)]
        for p in bad:
            with self.subTest(p=p), self.assertRaises(Blocked):owner.check_request(p, now=T0)
        with self.assertRaises(Blocked):owner.check_request(payload(), now=T0 + 1776)


class Window(unittest.TestCase):
    def test_window_starts_after_a_lead_and_ends_at_the_dataset_deadline(self):
        self.assertEqual(stand_launch.window(DATASET, T0 + 5), [T0 + 65, T0 + 1776])
        with self.assertRaises(Blocked):stand_launch.window(DATASET, T0 + 1776)


class Record(unittest.TestCase):
    def static(self, manifest, name, **changes):
        c = json.loads(Path(stand_launch.HERE, 'launch-config.json').read_text())
        c.update(owner_public_key='e' * 64, review_evidence='https://example.invalid/pr',
                 owner_scope_ack={'reviewed_pins_sha256': stand_launch.reviewed_pins(manifest, name), 'owner_statement': 'unit test'},
                 run_dataset=None, accepted_window=None, owner_launch_decision=None)
        c.update(changes)
        return c

    def files(self, d, **changes):
        cfg, man = Path(d, 'launch-config.json'), Path(d, 'manifest.json')
        name = str(cfg.resolve().relative_to(stand_launch.ROOT))
        manifest = {'files': {name: '0' * 64, 'runners/bcp02/cli.py': '1' * 64}}
        man.write_text(json.dumps(manifest))
        cfg.write_text(json.dumps(self.static(manifest, name, **changes)))
        return cfg, man

    def test_record_fills_only_the_run_slots_and_repins_the_config(self):
        with tempfile.TemporaryDirectory(dir=stand_launch.ROOT) as d:
            cfg, man = self.files(d)
            name = str(cfg.resolve().relative_to(stand_launch.ROOT))
            out = stand_launch.record(cfg, man, dict(DATASET), [T0 + 60, T0 + 1776])
            self.assertEqual(out['run_dataset'], DATASET)
            self.assertEqual(out['owner_launch_decision']['run_id'], DATASET['run_id'])
            self.assertEqual(json.loads(man.read_text())['files'][name], sha(cfg.read_bytes()))
            with self.assertRaises(Blocked):stand_launch.record(cfg, man, dict(DATASET), [T0 + 60, T0 + 1776])

    def test_record_refuses_without_reviewed_static_pins(self):
        bad = [dict(owner_public_key=None), dict(owner_public_key='E' * 64), dict(owner_public_key='e' * 63),
               dict(owner_scope_ack=None), dict(owner_scope_ack={'reviewed_pins_sha256': '0' * 64, 'owner_statement': 'x'})]
        for changes in bad:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory(dir=stand_launch.ROOT) as d:
                cfg, man = self.files(d, **changes)
                with self.assertRaises(Blocked):stand_launch.record(cfg, man, dict(DATASET), [T0 + 60, T0 + 1776])

    def test_any_other_pin_change_voids_the_owner_ack(self):
        with tempfile.TemporaryDirectory(dir=stand_launch.ROOT) as d:
            cfg, man = self.files(d)
            manifest = json.loads(man.read_text());manifest['files']['runners/bcp02/cli.py'] = '2' * 64
            man.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(Blocked, 'acknowledged'):stand_launch.record(cfg, man, dict(DATASET), [T0 + 60, T0 + 1776])

    def test_committed_ack_covers_the_current_runner_pins(self):
        config = json.loads(Path(stand_launch.HERE, 'launch-config.json').read_text())
        self.assertEqual(config['owner_scope_ack']['reviewed_pins_sha256'], stand_launch.reviewed_pins())
        stand_launch.ready(config)


class Network(unittest.TestCase):
    def fake(self, up):
        calls = []
        def run(args, check=True):
            calls.append(args)
            if args[:3] == ['ip', 'link', 'set'] and args[-1] in ('down', 'up'):up[args[4]] = args[-1] == 'up'
            if args[:3] == ['ip', '-j', 'link']:
                return SimpleNamespace(stdout=json.dumps([{'ifname': 'lo', 'flags': ['UP']}] +
                                       [{'ifname': n, 'flags': ['UP'] if v else []} for n, v in up.items()]))
            if args[:3] == ['ip', '-j', 'route']:
                return SimpleNamespace(stdout=json.dumps([{'dev': n} for n, v in up.items() if v]))
            return SimpleNamespace(stdout='')
        return run, calls

    def test_take_down_then_restore(self):
        up = {'eth0': True};run, calls = self.fake(up)
        state = stand_launch.links(run)
        self.assertEqual(state, {'links': ['eth0'], 'default_devices': ['eth0']})
        stand_launch.take_down(state, run);self.assertFalse(up['eth0'])
        self.assertIn(['systemctl', 'stop', 'systemd-networkd.socket', 'systemd-networkd'], calls)
        self.assertEqual(stand_launch.restore(state, run, wait=1)['default_devices'], ['eth0'])
        self.assertIn(['networkctl', 'reconfigure', 'eth0'], calls)

    def test_start_checks_the_permit_before_touching_the_network(self):
        up = {'eth0': True};run, calls = self.fake(up)
        with patch('runners.bcp02.admission.authorize', side_effect=Blocked('no permit')), \
             patch('runners.bcp02.stand_launch.os.geteuid', return_value=0):
            with self.assertRaises(Blocked):stand_launch.start('p', 'd', '/tmp/x', run)
        self.assertEqual(calls, []);self.assertTrue(up['eth0'])


class Revision(unittest.TestCase):
    def test_source_revision_comes_from_a_file_not_git(self):
        with tempfile.TemporaryDirectory() as d, patch('runners.bcp02.admission.ROOT', Path(d)):
            with self.assertRaises(Blocked):source_revision()
            Path(d, 'SOURCE_REVISION').write_text('f' * 40 + '\n');self.assertEqual(source_revision(), 'f' * 40)
            Path(d, 'SOURCE_REVISION').write_text('HEAD');self.assertRaises(Blocked, source_revision)


if __name__ == '__main__':
    unittest.main()
