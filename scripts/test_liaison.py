import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import contextlib
import io
from datetime import datetime, timezone

from export_community import sanitize

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('liaison', ROOT/'services/liaison/agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class LiaisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.ledger = agent.Ledger(Path(self.directory.name)/'state.sqlite')

    def test_concurrent_budget_is_shared_and_not_refunded(self):
        results = []
        def reserve(i):
            try:
                self.ledger.reserve(str(i), 1_000_000, 'fixture', 'fixture')
                results.append((str(i),'allowed'))
            except agent.BudgetError:
                results.append((str(i),'blocked'))
        threads = [threading.Thread(target=reserve, args=(i,)) for i in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(state=='allowed' for _,state in results), 3)
        with self.ledger.connect() as db:
            self.assertEqual(db.execute('SELECT SUM(amount) FROM reservations').fetchone()[0], 3_000_000)
        with self.assertRaises(agent.BudgetError):
            self.ledger.reserve(next(identifier for identifier,state in results if state=='allowed'), 0, 'fixture', 'fixture')

    def test_owner_limit_and_berlin_day_boundary(self):
        with self.assertRaises(agent.BudgetError): agent.Ledger(Path(self.directory.name)/'bad.sqlite', 4)
        before = datetime(2026,10,29,22,59,tzinfo=timezone.utc)
        after = datetime(2026,10,29,23,1,tzinfo=timezone.utc)
        self.ledger.reserve('before', 3_000_000, 'fixture', 'fixture', now=before)
        self.ledger.reserve('after', 3_000_000, 'fixture', 'fixture', now=after)

    def test_no_invented_evidence_or_execution_fields(self):
        valid = dict(decision='reply', reply='A retained receipt is needed.', evidence=['profile'], reason='Evidence matches.')
        self.assertEqual(agent.parse_reply(json.dumps(valid), ['profile']), valid)
        for change in [dict(evidence=['made-up']), dict(decision='run'), dict(evidence=[]), dict(tool='shell')]:
            with self.assertRaises(ValueError): agent.parse_reply(json.dumps(valid|change), ['profile'])

    def test_pricing_expiry_stops_before_count_or_generation(self):
        class NeverCalled:
            name='openai';model='fixture';config={'pricing_valid_until':'2000-01-01'}
            def count(self, prompt): raise AssertionError('must not reach provider')
        with self.assertRaises(agent.BudgetError):
            agent.call(NeverCalled(), 'fixture', self.ledger, 'expired', {'max_output_tokens':100})

    def test_budget_deferral_does_not_consume_the_comment_job(self):
        config=json.loads((ROOT/'services/liaison/config.example.json').read_text());config['billing_authorized']=True
        self.ledger.reserve('spent',3_000_000,'fixture','fixture')
        comment=dict(id='not-lost',text='A question',project_account=False)
        with self.assertRaisesRegex(agent.BudgetError,'budget_deferred'):
            agent.draft(comment,{'comments':[],'coverage':{}},{},config,self.ledger)
        with self.ledger.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)

    def test_two_models_make_one_attributed_draft_without_publication(self):
        class Fake:
            def __init__(self, config): self.config=config;self.name=config['provider'];self.model=config['model']
            def count(self, prompt): return 100
            def generate(self, prompt, maximum):
                return json.dumps(dict(decision='reply',reply='The profile has no minimum retention guarantee.',evidence=['profile'],reason='Matches supplied profile.')), self.model, dict(input_tokens=100, output_tokens=30)
        config=json.loads((ROOT/'services/liaison/config.example.json').read_text());config['billing_authorized']=True
        for role in ('writer','reviewer'):config[role]['pricing_valid_until']='2999-01-01'
        comment=dict(id='fixture-comment',text='How long are receipts retained?',project_account=False,source_url='https://www.moltbook.com/post/fixture')
        snapshot=dict(comments=[comment],coverage={'complete':False})
        result=agent.draft(comment,snapshot,{'profile':'No guaranteed minimum.'},config,self.ledger,Fake)
        self.assertEqual([m['provider'] for m in result['models']],['anthropic','openai'])
        self.assertEqual(result['status'],'draft_only');self.assertFalse(result['published'])
        self.assertEqual(len(result['provider_transcripts']),2)
        self.assertIn('How long are receipts retained?',result['provider_transcripts'][0]['input'])
        with self.assertRaises(ValueError):agent.draft(comment,snapshot,{'profile':'No guaranteed minimum.'},config,self.ledger,Fake)
        with self.assertRaises(ValueError):agent.draft(comment|{'project_account':True},snapshot,{},config,self.ledger,Fake)

    def test_operator_retry_has_a_new_record_and_preserves_failed_evidence(self):
        class Invalid:
            def __init__(self,config):self.config=config;self.name=config['provider'];self.model=config['model']
            def count(self,prompt):return 20
            def generate(self,prompt,maximum):return 'invalid-json-output',self.model,dict(input_tokens=20,output_tokens=5)
        config=json.loads((ROOT/'services/liaison/config.example.json').read_text());config['billing_authorized']=True
        for role in ('writer','reviewer'):config[role]['pricing_valid_until']='2999-01-01'
        comment=dict(id='failed-fixture',text='Question',project_account=False,source_url='https://www.moltbook.com/post/fixture')
        snapshot=dict(comments=[comment],coverage={})
        for retry in (None,'a'*32):
            with self.assertRaises(json.JSONDecodeError):agent.draft(comment,snapshot,{'profile':'fixture'},config,self.ledger,Invalid,operator_retry_id=retry)
        with self.ledger.connect() as db:
            rows=db.execute('SELECT result FROM jobs').fetchall();self.assertEqual(len(rows),2)
            self.assertTrue(all(json.loads(row[0])['provider_transcripts'][0]['output']=='invalid-json-output' for row in rows))

    def test_public_mirror_is_not_a2a_intake(self):
        data={'comments':[dict(id='a',author={'name':'prismdeadlines','private':'excluded'},content='<script>untrusted</script>',created_at='2026-10-29',replies=[dict(id='b',author={'name':'ipvxresearchliaison'},content='pending',verification_status='pending')])]}
        snapshot=sanitize(data,11,observed_at='fixture')
        self.assertEqual(snapshot['mirrored_comment_count'],1)
        self.assertEqual(snapshot['returned_comment_count'],2)
        self.assertEqual(snapshot['excluded_comment_ids'],['b'])
        self.assertFalse(snapshot['coverage']['complete'])
        self.assertFalse(snapshot['comments'][0]['a2a_submission'])
        self.assertNotIn('private',snapshot['comments'][0])
        self.assertNotIn('excluded',json.dumps(snapshot['comments']))

    def test_collection_stays_active_without_model_access(self):
        spec=importlib.util.spec_from_file_location('liaison_worker',ROOT/'services/liaison/worker.py')
        worker=importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules',{'agent':agent}):spec.loader.exec_module(worker)
        root=Path(self.directory.name);release=root/'release';release.mkdir()
        (release/'facts.json').write_text('{}');(release/'baseline-snapshot.json').write_text('{"comments":[]}')
        worker.__file__=str(release/'worker.py')
        state=root/'observer';state.mkdir();config=json.loads((ROOT/'services/liaison/config.example.json').read_text())
        config.update(billing_authorized=True,generation_enabled=False);(state/'config.json').write_text(json.dumps(config))
        raw={'comments':[dict(id='observed',author={'name':'external-fixture'},content='A new question',created_at='2026-10-29T08:00:00Z')]}
        def source(url):return raw if '/comments?' in url else {'post':{'comment_count':1}}
        with patch.object(worker,'read',side_effect=source),patch.object(worker,'draft',side_effect=AssertionError('no model call')),contextlib.redirect_stdout(io.StringIO()):
            worker.cycle(state,root/'public');worker.cycle(state,root/'public')
        status=json.loads((root/'public/liaison-status.json').read_text())
        self.assertEqual(status['state'],'reading_only');self.assertFalse(status['generation_enabled'])
        self.assertFalse(status['smoke_verified_current'])
        self.assertEqual(json.loads((root/'public/community-discussions.json').read_text())['mirrored_comment_count'],1)
        with agent.Ledger(state/'ledger.sqlite').connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)


if __name__=='__main__':unittest.main()
