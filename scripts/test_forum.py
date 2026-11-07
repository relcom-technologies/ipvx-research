"""Forum threads, posts, automatic and human moderation; no network, model or account."""
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ipvx_forum_community', ROOT / 'infra/community.py')
c = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = c
SPEC.loader.exec_module(c)


class Forum(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 2_000_000_000
        self.service = c.CommunityService(self.tmp.name, bootstrap_admin_sub='verified-owner', clock=lambda: self.now)
        self.owner = {'sub': 'verified-owner', 'emailVerified': True}
        self.alice = {'sub': 'verified-alice', 'emailVerified': True}
        self.bob = {'sub': 'verified-bob', 'emailVerified': True}
        self.counter = 0

    def tearDown(self):
        self.tmp.cleanup()

    def get(self, path, user=None):
        return self.service.handle('GET', c.PREFIX + '/forum' + path, user)

    def post(self, path, body, user=None, key=None):
        self.counter += 1
        return self.service.handle('POST', c.PREFIX + '/forum' + path, user, body,
                                   request_id=key or 'forum-%08d' % self.counter)

    def open_thread(self, user=None, category='bcp', title='Runner on x86_64', text='First post', **extra):
        response = self.post('/categories/%s/threads' % category, {'title': title, 'text': text, **extra}, user or self.alice)
        self.assertEqual(response.status, 201, response.data)
        return response.data['thread']['id'], response.data['post']['id']

    def thread(self, thread_id, user=None):
        return self.get('/threads/%d' % thread_id, user)

    def test_reading_is_public_and_writing_needs_a_verified_account(self):
        listing = self.get('/categories')
        self.assertEqual(listing.status, 200)
        self.assertEqual([item['id'] for item in listing.data['categories']], list(c.FORUM_CATEGORIES))
        body = {'title': 'Hello there', 'text': 'Text'}
        self.assertEqual(self.post('/categories/bcp/threads', body).status, 401)
        self.assertEqual(self.post('/categories/bcp/threads', body, {'sub': 'x', 'emailVerified': False}).status, 403)
        self.assertEqual(self.post('/categories/elsewhere/threads', body, self.alice).status, 404)
        self.assertEqual(self.post('/categories/bcp/threads', {**body, 'status': 'published'}, self.alice).status, 400)

    def test_participant_post_waits_for_review_then_publishes(self):
        thread_id, post_id = self.open_thread(text='<script>literal text</script>')
        self.assertEqual(self.thread(thread_id).status, 404)
        self.assertEqual(self.thread(thread_id, self.bob).status, 404)
        own = self.thread(thread_id, self.alice)
        self.assertEqual(own.status, 200)
        self.assertEqual(own.data['posts'][0]['status'], 'pending')
        self.assertNotIn('review', own.data['posts'][0])
        self.assertEqual(self.get('/categories/bcp/threads').data['threads'], [])
        queue = self.service.forum_review_queue()
        self.assertEqual([(item['id'], item['opening']) for item in queue], [(post_id, True)])
        self.assertTrue(self.service.forum_review(post_id, 'publish', 'On topic, no private data', 'claude-opus-5-5'))
        self.assertFalse(self.service.forum_review(post_id, 'hide', 'Second verdict', 'claude-opus-5-5'))
        public = self.thread(thread_id)
        self.assertEqual(public.data['thread']['status'], 'published')
        self.assertEqual(public.data['posts'][0]['text'], '<script>literal text</script>')
        self.assertEqual(self.get('/categories').data['categories'][0]['threads'], 1)
        found = self.get('/search?q=literal').data['results']
        self.assertEqual([(item['thread'], item['post']) for item in found], [(thread_id, post_id)])

    def test_moderator_posts_are_published_at_once(self):
        thread_id, _ = self.open_thread(self.owner)
        self.assertEqual(self.thread(thread_id).data['thread']['status'], 'published')
        self.assertEqual(self.service.forum_review_queue(), [])
        self.assertTrue(self.get('/profile', self.owner).data['publishesDirectly'])
        self.assertFalse(self.get('/profile', self.alice).data['publishesDirectly'])

    def test_hidden_reply_leaves_thread_and_search_until_a_person_restores_it(self):
        thread_id, _ = self.open_thread(self.owner)
        reply = self.post('/threads/%d/posts' % thread_id, {'text': 'spamword offer'}, self.bob)
        self.assertEqual(reply.status, 201, reply.data)
        reply_id = reply.data['post']['id']
        self.assertTrue(self.service.forum_review(reply_id, 'hide', 'Advertising', 'claude-opus-5-5'))
        self.assertEqual([p['id'] for p in self.thread(thread_id, self.alice).data['posts']], [reply_id - 1])
        self.assertEqual(self.thread(thread_id, self.bob).data['posts'][-1]['status'], 'hidden')
        self.assertEqual(self.get('/search?q=spamword').data['results'], [])
        hidden = self.get('/moderation?queue=hidden', self.owner)
        self.assertEqual([p['id'] for p in hidden.data['posts']], [reply_id])
        self.assertEqual(hidden.data['posts'][0]['review'], {'queue': 'automatic', 'note': 'Advertising'})
        self.assertEqual(self.get('/moderation?queue=hidden', self.alice).status, 403)
        restored = self.post('/posts/%d/moderation' % reply_id, {'action': 'publish', 'reason': 'Not advertising'}, self.owner)
        self.assertEqual(restored.status, 200, restored.data)
        self.assertEqual(self.thread(thread_id).data['thread']['replies'], 1)
        self.assertEqual(len(self.get('/search?q=spamword').data['results']), 1)

    def test_escalated_post_waits_for_people(self):
        thread_id, post_id = self.open_thread()
        self.assertTrue(self.service.forum_review(post_id, 'escalate', 'Unsure: names a person', 'claude-opus-5-5'))
        self.assertEqual(self.service.forum_review_queue(), [])
        self.assertEqual([p['id'] for p in self.get('/moderation', self.owner).data['posts']], [post_id])
        self.assertEqual(self.get('/moderation?queue=automatic', self.owner).data['posts'], [])
        self.assertEqual(self.thread(thread_id).status, 404)
        for verdict, reviewer in (('maybe', 'claude-opus-5-5'), ('publish', 'Bad Name'), ('publish', '')):
            with self.assertRaises(ValueError):
                self.service.forum_review(post_id, verdict, 'reason text', reviewer)

    def test_hiding_the_opening_post_hides_the_thread(self):
        thread_id, post_id = self.open_thread(self.owner, title='Opening topic')
        self.assertEqual(len(self.get('/search?q=Opening').data['results']), 1)
        hidden = self.post('/posts/%d/moderation' % post_id, {'action': 'hide', 'reason': 'Off topic'}, self.owner)
        self.assertEqual(hidden.status, 200, hidden.data)
        self.assertEqual(self.thread(thread_id, self.alice).status, 404)
        self.assertEqual(self.get('/categories/bcp/threads', self.alice).data['threads'], [])
        self.assertEqual(self.get('/search?q=Opening').data['results'], [])
        self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': 'Reply'}, self.alice).status, 404)

    def test_locked_thread_takes_replies_from_moderators_only(self):
        thread_id, _ = self.open_thread(self.owner)
        self.assertEqual(self.post('/threads/%d/moderation' % thread_id, {'action': 'lock', 'reason': 'Settled'}, self.alice).status, 403)
        self.assertEqual(self.post('/threads/%d/moderation' % thread_id, {'action': 'lock', 'reason': 'Settled'}, self.owner).status, 200)
        self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': 'More'}, self.alice).status, 409)
        self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': 'Closing note'}, self.owner).status, 201)
        self.assertTrue(self.thread(thread_id).data['thread']['locked'])

    def test_reply_target_must_be_a_published_post_of_the_same_thread(self):
        first, first_post = self.open_thread(self.owner)
        second, second_post = self.open_thread(self.owner, title='Second topic')
        pending = self.post('/threads/%d/posts' % first, {'text': 'Pending'}, self.alice).data['post']['id']
        for target in (second_post, pending, 999, '1', True):
            self.assertEqual(self.post('/threads/%d/posts' % first, {'text': 'Re', 'replyTo': target}, self.bob).status, 400, target)
        ok = self.post('/threads/%d/posts' % first, {'text': 'Re', 'replyTo': first_post}, self.bob)
        self.assertEqual(ok.data['post']['replyTo'], first_post)

    def test_subject_links_threads_to_project_objects(self):
        self.open_thread(self.owner, category='rfc', title='Section 3 wording', subject='rfc-0005.s3')
        self.open_thread(self.owner, category='experiments', title='About H5', subject='h5')
        listed = self.get('/subjects/rfc-0005.s3/threads')
        self.assertEqual([t['title'] for t in listed.data['threads']], ['Section 3 wording'])
        for subject in ('RFC-5', '../x', 'a' * 81, 5):
            self.assertEqual(self.post('/categories/rfc/threads', {'title': 'Bad subject', 'text': 'x', 'subject': subject}, self.owner).status, 400)

    def test_threads_page_by_last_activity(self):
        ids = []
        for n in range(5):
            self.now += 10
            ids.append(self.open_thread(self.owner, title='Topic number %d' % n)[0])
        self.now += 10
        self.post('/threads/%d/posts' % ids[0], {'text': 'Bump'}, self.owner)
        first = self.get('/categories/bcp/threads?limit=2').data
        self.assertEqual([t['id'] for t in first['threads']], [ids[0], ids[4]])
        rest = self.get('/categories/bcp/threads?limit=10&before=' + first['nextBefore']).data
        self.assertEqual([t['id'] for t in rest['threads']], [ids[3], ids[2], ids[1]])
        self.assertIsNone(rest['nextBefore'])
        for bad in ('1', 'x-1', '1-0', '1-1&before=2-2'):
            self.assertEqual(self.get('/categories/bcp/threads?before=' + bad).status, 400, bad)

    def test_public_name_is_opt_in_unique_and_not_an_impersonation(self):
        self.assertEqual(self.get('/profile').status, 401)
        self.assertTrue(self.get('/profile', self.alice).data['author']['label'].startswith('Участник '))
        self.assertEqual(self.post('/profile', {'name': '  Alice   Novak '}, self.alice).data['author'],
                         {'id': self.get('/profile', self.alice).data['author']['id'], 'label': 'Alice Novak', 'named': True})
        self.assertEqual(self.post('/profile', {'name': 'alice novak'}, self.bob).status, 409)
        for name in ('Admin', 'Модератор', 'Участник 123456', 'member_abc', 'x', '<b>', 'a' * 41, '_lead', 5):
            self.assertEqual(self.post('/profile', {'name': name}, self.bob).status, 400, name)
        thread_id, _ = self.open_thread(self.owner)
        self.post('/threads/%d/posts' % thread_id, {'text': 'Named reply'}, self.alice)
        self.assertEqual(self.post('/profile', {'name': ''}, self.alice).data['author']['named'], False)

    def test_blocked_participant_cannot_post_and_limits_hold(self):
        thread_id, _ = self.open_thread(self.owner)
        alice_id = self.service.handle('GET', c.PREFIX + '/session', self.alice).data['author']['id']
        self.assertEqual(self.service.handle('POST', c.PREFIX + '/members/%s/access' % alice_id, self.owner,
                         {'action': 'block', 'reason': 'Spam run'}, request_id='block-alice-1').status, 200)
        self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': 'Again'}, self.alice).status, 403)
        for n in range(c.FORUM_PENDING):
            self.now += c.RATE_SECONDS
            self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': 'Post %d' % n}, self.bob).status, 201)
        self.now += c.RATE_SECONDS
        self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': 'One too many'}, self.bob).status, 429)
        self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': ''}, self.owner).status, 400)
        self.assertEqual(self.post('/threads/%d/posts' % thread_id, {'text': 'x' * 8001}, self.owner).status, 400)

    def test_search_treats_the_query_as_words(self):
        self.open_thread(self.owner, title='Routing tables', text='Prefix aggregation at scale')
        for q in ('" OR *', 'NEAR(a b)', 'title:x', '*'):
            response = self.get('/search?q=' + q.replace(' ', '+').replace('"', '%22').replace('*', '%2A'))
            self.assertIn(response.status, (200, 400), q)
            if response.status == 200:
                self.assertEqual(response.data['results'], [], q)
        self.assertEqual(len(self.get('/search?q=aggregation+prefix').data['results']), 1)

    def test_revoked_moderator_cannot_replay_a_cached_decision(self):
        thread_id, post_id = self.open_thread()
        bob_id = self.service.handle('GET', c.PREFIX + '/session', self.bob).data['author']['id']
        grant = {'authorId': bob_id, 'role': 'moderator', 'reason': 'Trusted reviewer'}
        self.service.handle('POST', c.PREFIX + '/roles', self.owner, {**grant, 'action': 'grant'}, request_id='grant-bob-1')
        body = {'action': 'publish', 'reason': 'Reviewed'}
        self.assertEqual(self.post('/posts/%d/moderation' % post_id, body, self.bob, key='bob-decision-1').status, 200)
        self.service.handle('POST', c.PREFIX + '/roles', self.owner, {**grant, 'action': 'revoke'}, request_id='revoke-bob-1')
        self.assertEqual(self.post('/posts/%d/moderation' % post_id, body, self.bob, key='bob-decision-1').status, 403)


class Routes(unittest.TestCase):
    def test_both_allowlists_name_the_same_forum_routes(self):
        patterns = []
        for name in ('server.py', 'auth.py'):
            text = (ROOT / 'infra' / name).read_text()
            patterns.append(re.compile(re.search(r"re\.compile\(r'(/community/v1/[^']+)'\)", text)[1]))
        self.assertEqual(patterns[0].pattern, patterns[1].pattern)
        for path in ('/community/v1/forum/categories', '/community/v1/forum/categories/meta/threads',
                     '/community/v1/forum/threads/12', '/community/v1/forum/threads/12/posts',
                     '/community/v1/forum/threads/12/moderation', '/community/v1/forum/posts/3/moderation',
                     '/community/v1/forum/subjects/rfc-0005.s3/threads', '/community/v1/forum/search',
                     '/community/v1/forum/moderation', '/community/v1/forum/profile'):
            self.assertTrue(patterns[0].fullmatch(path), path)
        for path in ('/community/v1/forum/categories/evil/threads', '/community/v1/forum/threads/0',
                     '/community/v1/forum/threads/12/posts/3', '/community/v1/forum/subjects/A/threads',
                     '/community/v1/forum/admin'):
            self.assertFalse(patterns[0].fullmatch(path), path)


if __name__ == '__main__':
    unittest.main()
