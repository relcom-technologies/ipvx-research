"""Portal access must be checked beyond the administration interface."""
from test_community import Community, c
import unittest


class Admin(Community):
    def test_member_inventory_is_private_paged_and_search_is_literal(self):
        self.alice['name'] = '<script>Alice</script> 100%'
        alice = self.get('/session', self.alice).data['author']['id']
        self.get('/session', self.bob)
        self.assertEqual(self.get('/members').status, 403)
        self.assertEqual(self.get('/members', self.alice).status, 403)
        page = self.get('/members?limit=1', self.owner).data
        self.assertEqual(page['total'], 3)
        all_ids = [page['members'][0]['id']]
        while page['nextAfter']:
            page = self.get('/members?limit=1&after='+page['nextAfter'], self.owner).data
            all_ids += [x['id'] for x in page['members']]
        self.assertEqual(len(set(all_ids)), 3)
        found = self.get('/members?search=100%25', self.owner).data['members']
        self.assertEqual([x['id'] for x in found], [alice])
        self.assertIn('<script>', found[0]['label'])  # Plain data, escaped by DOM rendering.
        serialized = str(found)
        for secret in ['verified-alice', 'alice@example.invalid', 'private@example.invalid']:
            self.assertNotIn(secret, serialized)
        self.assertEqual(self.get('/members?limit=51', self.owner).status, 400)

    def test_blocked_participant_cannot_replay_or_read_private_but_can_read_public(self):
        entry = self.submit(key='old-comment-key')
        alice = self.get('/session', self.alice).data['author']['id']
        body = {'action':'block','reason':'Owner reviewed temporary suspension'}
        self.assertEqual(self.post('/members/'+alice+'/access', body, self.owner, 'block-key-1').status, 200)
        self.assertEqual(self.get('/session', self.alice).data['roles'], [])
        self.assertEqual(self.get('/session', self.alice).data['access'], 'blocked')
        self.assertEqual(self.post('/rfcs/rfc-0005/entries', {'kind':'comment','title':'Proposal','text':'<script>literal text</script>'}, self.alice, 'old-comment-key').status, 403)
        self.assertEqual(self.get('/entries/'+str(entry), self.alice).status, 404)
        self.publish(entry)
        self.assertEqual(self.get('/entries/'+str(entry), self.alice).status, 200)
        self.assertEqual(self.post('/members/'+alice+'/access', {'action':'restore','reason':'Suspension reviewed'}, self.owner).status, 200)
        self.assertEqual(self.get('/session', self.alice).data['roles'], ['participant'])

    def test_blocked_admin_loses_inventory_and_cached_privileged_actions(self):
        alice = self.get('/session', self.alice).data['author']['id']
        bob = self.get('/session', self.bob).data['author']['id']
        self.post('/roles', {'authorId':alice,'role':'admin','action':'grant','reason':'Delegate portal administration'}, self.owner)
        saved = {'authorId':bob,'role':'moderator','action':'grant','reason':'Assign reviewer'}
        self.assertEqual(self.post('/roles', saved, self.alice, 'delegated-role-1').status, 200)
        self.assertEqual(self.post('/members/'+alice+'/access', {'action':'block','reason':'Delegation suspended'}, self.owner).status, 200)
        self.assertEqual(self.get('/members', self.alice).status, 403)
        self.assertEqual(self.get('/audit', self.alice).status, 403)
        self.assertEqual(self.post('/roles', saved, self.alice, 'delegated-role-1').status, 403)
        self.assertEqual(self.post('/roles', {'authorId':alice,'role':'moderator','action':'grant','reason':'Blocked grant refused'}, self.owner).status, 409)
        self.assertEqual(self.post('/members/'+alice+'/access', {'action':'restore','reason':'Resume delegation'}, self.owner).status, 200)
        self.assertEqual(self.get('/members', self.alice).status, 200)

    def test_protected_owner_self_block_and_idempotent_access_audit(self):
        owner = self.get('/session', self.owner).data['author']['id']
        alice = self.get('/session', self.alice).data['author']['id']
        self.post('/roles', {'authorId':alice,'role':'admin','action':'grant','reason':'Delegate portal administration'}, self.owner)
        for actor, user in [(owner,self.owner),(owner,self.alice),(alice,self.alice)]:
            self.assertEqual(self.post('/members/'+actor+'/access', {'action':'block','reason':'Forbidden lockout'}, user).status, 409)
        self.post('/roles', {'authorId':alice,'role':'admin','action':'revoke','reason':'End delegation'}, self.owner)
        request = {'action':'block','reason':'Temporary suspension'}
        for _ in range(2):
            self.assertEqual(self.post('/members/'+alice+'/access', request, self.owner, 'durable-access-1').status, 200)
        events = self.get('/audit', self.owner).data['events']
        self.assertEqual(sum(e['action']=='block_access' for e in events), 1)
        self.assertEqual(self.get('/members?access=blocked', self.owner).data['total'], 1)


def load_tests(loader, tests, pattern):
    # Reuse fixtures without rerunning the base class's complete test suite.
    return unittest.TestSuite(Admin(name) for name in Admin.__dict__ if name.startswith('test_'))
