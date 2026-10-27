"""Permission and persistence checks; no production account, mail or network."""
import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('ipvx_community', Path(__file__).resolve().parents[1] / 'infra/community.py')
c = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = c
SPEC.loader.exec_module(c)


class Community(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 2_000_000_000
        self.service = c.CommunityService(self.tmp.name, bootstrap_admin_sub='verified-owner', clock=lambda: self.now)
        self.owner = {'sub': 'verified-owner', 'emailVerified': True, 'email': 'private@example.invalid'}
        self.alice = {'sub': 'verified-alice', 'emailVerified': True, 'email': 'alice@example.invalid'}
        self.bob = {'sub': 'verified-bob', 'emailVerified': True}
        self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, path, user=None):
        return self.service.handle('GET', c.PREFIX + path, user)

    def post(self, path, body, user=None, key=None):
        self.counter += 1
        return self.service.handle('POST', c.PREFIX + path, user, body,
                                   request_id=key or 'fixture-%08d' % self.counter)

    def submit(self, user=None, kind='comment', key=None):
        response = self.post('/rfcs/rfc-0005/entries', {'kind': kind, 'title': 'Proposal',
                             'text': '<script>literal text</script>'}, user or self.alice, key)
        self.assertEqual(response.status, 201, response.data)
        return response.data['entry']['id']

    def publish(self, entry_id):
        response = self.post('/entries/%s/moderation' % entry_id,
                             {'action': 'publish', 'reason': 'Reviewed content'}, self.owner)
        self.assertEqual(response.status, 200, response.data)

    def test_verified_user_required_and_no_role_from_client(self):
        body = {'text': 'Comment'}
        self.assertEqual(self.post('/rfcs/rfc-0005/entries', body).status, 401)
        for user in ({'sub': 'bad', 'emailVerified': False}, {'sub': 'bad', 'emailVerified': 'true'}, {}):
            self.assertEqual(self.post('/rfcs/rfc-0005/entries', body, user).status, 403)
        fake_admin = {**self.alice, 'roles': ['admin'], 'admin': True}
        self.assertEqual(self.post('/roles', {'authorId': 'member_' + 'a'*24, 'role': 'admin',
                         'action': 'grant', 'reason': 'Injected claim'}, fake_admin).status, 403)
        self.assertEqual(self.post('/rfcs/rfc-0005/entries', {**body, 'role': 'admin'}, self.alice).status, 400)

    def test_first_login_never_admin_and_bootstrap_not_email(self):
        with tempfile.TemporaryDirectory() as directory:
            service = c.CommunityService(directory)
            result = service.handle('GET', c.PREFIX + '/session', self.owner)
            self.assertEqual(result.data['roles'], ['participant'])
        other = {**self.bob, 'email': 'private@example.invalid'}
        self.assertEqual(self.get('/session', other).data['roles'], ['participant'])
        with self.assertRaises(ValueError):
            c.CommunityService(self.tmp.name, bootstrap_admin_sub='different-owner')

    def test_bootstrap_pins_existing_verified_pseudonym_without_raw_subject(self):
        with tempfile.TemporaryDirectory() as directory:
            initial = c.CommunityService(directory)
            actor = initial.handle('GET', c.PREFIX+'/session', self.owner).data['author']['id']
            configured = c.CommunityService(directory, bootstrap_admin_author_id=actor)
            self.assertIn('admin', configured.handle('GET', c.PREFIX+'/session', self.owner).data['roles'])
            self.assertNotIn(b'verified-owner', configured.database.read_bytes())
            self.assertIn('admin', c.CommunityService(directory, bootstrap_admin_author_id=actor)
                          .handle('GET', c.PREFIX+'/session', self.owner).data['roles'])
            for wrong in ('member_'+'f'*24, 'owner@example.invalid', 'bad'):
                with self.assertRaises(ValueError):c.CommunityService(directory, bootstrap_admin_author_id=wrong)
            with self.assertRaises(ValueError):
                c.CommunityService(directory, bootstrap_admin_author_id=actor, bootstrap_admin_sub='verified-owner')

    def test_pending_private_publish_hide_and_plain_text(self):
        entry = self.submit()
        self.assertEqual(self.get('/rfcs/rfc-0005/entries').data['entries'], [])
        self.assertEqual(self.get('/entries/%s' % entry, self.bob).status, 404)
        own = self.get('/rfcs/rfc-0005/entries?mine=1', self.alice)
        self.assertEqual(own.data['entries'][0]['text'], '<script>literal text</script>')
        self.assertEqual(self.get('/moderation', self.alice).status, 403)
        self.publish(entry)
        public = self.get('/entries/%s' % entry)
        self.assertEqual(public.status, 200)
        serialized = json.dumps(public.data)
        for secret in ('verified-alice', 'alice@example.invalid', 'private@example.invalid'):
            self.assertNotIn(secret, serialized)
        hidden = self.post('/entries/%s/moderation' % entry, {'action': 'hide', 'reason': 'Further review'}, self.owner)
        self.assertEqual(hidden.status, 200)
        self.assertEqual(self.get('/entries/%s' % entry).status, 404)
        self.assertEqual(self.get('/entries/%s' % entry, self.alice).status, 200)

    def test_idempotency_survives_restart_and_conflict(self):
        entry = self.submit(key='same-key-123')
        again = c.CommunityService(self.tmp.name, bootstrap_admin_sub='verified-owner', clock=lambda: self.now)
        body = {'kind': 'comment', 'title': 'Proposal', 'text': '<script>literal text</script>'}
        response = again.handle('POST', c.PREFIX + '/rfcs/rfc-0005/entries', self.alice, body, request_id='same-key-123')
        self.assertEqual(response.status, 201)
        self.assertEqual(response.data['entry']['id'], entry)
        conflict = self.post('/rfcs/rfc-0005/entries', {**body, 'text': 'Changed'}, self.alice, 'same-key-123')
        self.assertEqual(conflict.status, 409)
        self.assertEqual(len(self.get('/rfcs/rfc-0005/entries?mine=1', self.alice).data['entries']), 1)
        with closing(sqlite3.connect(self.service.database)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='submit_comment'").fetchone()[0], 1)

    def test_concurrent_same_request_creates_one_entry(self):
        results = []
        def call():
            results.append(self.service.handle('POST', c.PREFIX + '/rfcs/rfc-0005/entries', self.alice,
                            {'text': 'Concurrent'}, request_id='concurrent-key-1'))
        threads = [threading.Thread(target=call) for _ in range(6)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertTrue(all(r.status == 201 for r in results))
        self.assertEqual(len({r.data['entry']['id'] for r in results}), 1)

    def test_roles_audited_moderator_revoked_and_no_github_authority(self):
        alice = self.get('/session', self.alice).data['author']['id']
        response = self.post('/roles', {'authorId': alice, 'role': 'moderator', 'action': 'grant', 'reason': 'Appointed reviewer'}, self.owner)
        self.assertEqual(response.status, 200)
        self.assertIn('no GitHub', response.data['notice'])
        entry = self.submit(self.bob)
        self.assertEqual(self.post('/entries/%s/moderation' % entry,
                         {'action': 'publish', 'reason': 'Checked content'}, self.alice, 'moderator-key-1').status, 200)
        self.assertEqual(self.post('/roles', {'authorId': alice, 'role': 'admin',
                         'action': 'grant', 'reason': 'Self escalation'}, self.alice).status, 403)
        self.post('/roles', {'authorId': alice, 'role': 'moderator', 'action': 'revoke', 'reason': 'Term ended'}, self.owner)
        self.assertEqual(self.get('/moderation', self.alice).status, 403)
        self.assertEqual(self.post('/entries/%s/moderation' % entry,
                         {'action': 'publish', 'reason': 'Checked content'}, self.alice, 'moderator-key-1').status, 403)
        self.assertEqual(self.post('/entries/%s/moderation' % entry,
                         {'action': 'hide', 'reason': 'Attempt after revoke'}, self.alice).status, 403)
        self.assertEqual(self.get('/audit', self.alice).status, 403)
        actions = [x['action'] for x in self.get('/audit', self.owner).data['events']]
        self.assertIn('grant_role', actions);self.assertIn('revoke_role', actions)

    def test_votes_one_per_subject_nonbinding_and_withdraw(self):
        entry = self.submit(kind='proposal');self.publish(entry)
        path = '/entries/%s/vote' % entry
        first = self.post(path, {'value': 'yes'}, self.alice)
        self.assertFalse(first.data['binding'])
        second = self.post(path, {'value': 'no'}, self.alice)
        self.assertEqual(second.data['entry']['votes']['counts'], {'yes': 0, 'no': 1, 'abstain': 0})
        self.post(path, {'value': 'yes'}, self.bob)
        public = self.get('/entries/%s' % entry).data['entry']
        self.assertEqual(public['votes']['counts'], {'yes': 1, 'no': 1, 'abstain': 0})
        withdrawn = self.post(path, {'value': 'withdraw'}, self.alice)
        self.assertEqual(withdrawn.data['entry']['votes']['counts']['no'], 0)
        self.assertEqual(self.get('/session', self.alice).data['governance']['votesBinding'], False)
        self.assertIsNone(self.service.handle('POST', '/auth/login', self.alice, {}))

    def test_hidden_proposal_not_exposed_by_cached_vote_response(self):
        entry = self.submit(kind='proposal');self.publish(entry)
        path = '/entries/%s/vote' % entry
        self.assertEqual(self.post(path, {'value':'yes'}, self.bob, 'vote-cache-key-1').status, 200)
        self.post('/entries/%s/moderation' % entry, {'action':'hide','reason':'Privacy review'}, self.owner)
        self.assertEqual(self.post(path, {'value':'yes'}, self.bob, 'vote-cache-key-1').status, 404)

    def test_utf8_page_budget_and_cursor_do_not_skip_entries(self):
        wanted = set()
        for i in range(15):
            result = self.post('/rfcs/rfc-0005/entries', {'text':'я'*5000}, self.alice)
            self.assertEqual(result.status, 201)
            wanted.add(result.data['entry']['id'])
        seen, before = set(), None
        while True:
            path = '/rfcs/rfc-0005/entries?mine=1&limit=50' + ('&before='+str(before) if before else '')
            response = self.get(path, self.alice)
            self.assertLess(len(json.dumps(response.data,ensure_ascii=False).encode()),131072)
            self.assertFalse(seen & {x['id'] for x in response.data['entries']})
            seen.update(x['id'] for x in response.data['entries'])
            before = response.data['nextBefore']
            if before is None:break
        self.assertEqual(seen, wanted)

    def test_pending_not_voteable_and_bounds(self):
        entry = self.submit(kind='proposal')
        self.assertEqual(self.post('/entries/%s/vote' % entry, {'value': 'yes'}, self.bob).status, 404)
        self.assertEqual(self.post('/entries/%s/vote' % entry, {'value': 'yes'}, self.bob).data,
                         self.post('/entries/999999/vote', {'value': 'yes'}, self.bob).data)
        self.assertEqual(self.post('/rfcs/rfc-0005/entries', {'text': 'a'*8001}, self.alice).status, 400)
        self.assertEqual(self.post('/rfcs/rfc-0005/entries', {'text': 'a'*13000}, self.alice).status, 413)
        self.assertEqual(self.get('/rfcs/rfc-0005/entries?limit=1000').status, 400)
        self.assertEqual(self.get('/rfcs/rfc-0005/entries?limit=2&limit=3').status, 400)
        self.assertEqual(self.get('/rfcs/rfc-0005/entries?mine=1').status, 401)
        self.assertEqual(self.service.handle('POST', c.PREFIX+'/rfcs/rfc-0005/entries', self.alice, {'text':'x'}).status, 400)

    def test_rate_and_capacity_fail_without_partial_write(self):
        entry = self.submit(kind='proposal');self.publish(entry)
        with patch.object(c, 'RATE_WRITES', 2):
            self.assertEqual(self.post('/entries/%s/vote' % entry, {'value':'yes'}, self.bob).status, 200)
            self.assertEqual(self.post('/entries/%s/vote' % entry, {'value':'no'}, self.bob).status, 200)
            self.assertEqual(self.post('/entries/%s/vote' % entry, {'value':'yes'}, self.bob).status, 429)
        with patch.object(c, 'MAX_ENTRIES', 1):
            self.assertEqual(self.post('/rfcs/rfc-0005/entries', {'text':'Over capacity'}, self.bob).status, 503)
        with patch.object(c, 'MAX_AUDIT', 1):
            self.assertEqual(self.post('/rfcs/rfc-0005/entries', {'text':'No audit space'}, self.bob).status, 503)
        self.assertEqual(self.get('/rfcs/rfc-0005/entries?mine=1', self.bob).data['entries'], [])

    def test_private_files_and_stable_project_pseudonyms(self):
        first = self.get('/session', self.alice).data['author']['id']
        restart = c.CommunityService(self.tmp.name)
        self.assertEqual(restart.handle('GET', c.PREFIX+'/session', self.alice).data['author']['id'], first)
        with tempfile.TemporaryDirectory() as directory:
            other = c.CommunityService(directory)
            self.assertNotEqual(other.handle('GET', c.PREFIX+'/session', self.alice).data['author']['id'], first)
        self.assertEqual(self.service.database.stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(self.tmp.name).stat().st_mode & 0o777, 0o700)
        raw = self.service.database.read_bytes()
        self.assertNotIn(b'verified-alice', raw)
        self.assertNotIn(b'alice@example.invalid', raw)


if __name__ == '__main__':
    unittest.main()
