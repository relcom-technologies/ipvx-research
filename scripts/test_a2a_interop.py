"""Joint-protocol preflight must not be mistaken for partner readiness or external traffic."""
import copy,hashlib,importlib.util,json,shutil,subprocess,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];HERE=ROOT/'experiments/a2a-interop'
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,HERE/file);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
preflight=load('ipvx_interop_preflight','preflight.py');readiness=load('ipvx_interop_readiness','readiness.py')
class Interop(unittest.IsolatedAsyncioTestCase):
 async def test_local_preflight_reports_cases_without_joint_execution(self):
  # Execute the immutable candidate against its own hashed source in a fresh
  # interpreter; imports from the current descriptor must not leak into it.
  plan=json.loads((HERE/'protocol.json').read_text())
  with tempfile.TemporaryDirectory(prefix='ipvx-frozen-regression-') as tmp:
   root=Path(tmp);candidate=root/'experiments/a2a-interop';candidate.mkdir(parents=True)
   manifest=json.loads((HERE/'bundle-manifest.json').read_text())
   for name,digest in manifest['files'].items():
    raw=(HERE/name).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
    (candidate/name).write_bytes(raw)
   for name,digest in plan['source_sha256'].items():
    source=HERE/'frozen-source'/plan['server_revision']/name
    self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
    target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
   code='import asyncio,json,runpy,sys; m=runpy.run_path(sys.argv[1]); print(json.dumps(asyncio.run(m["run"]())))'
   process=subprocess.run([sys.executable,'-c',code,str(candidate/'preflight.py')],capture_output=True,text=True,check=True,timeout=60)
   r=json.loads(process.stdout)
  self.assertEqual(r['status'],'passed');self.assertEqual(set(r['cases']),{'A','B','R'})
  self.assertFalse(r['partner_execution']);self.assertFalse(r['ready_to_launch'])
  self.assertEqual(r['cases']['B']['automatic_replacement_requests'],0)
  self.assertTrue(r['cases']['R']['task_receipt_can_outlive_proposal'])
 async def test_original_candidate_rejects_the_new_descriptor(self):
  with self.assertRaisesRegex(ValueError,'Pinned source mismatch: infra/a2a_service.py'):
   preflight.verify_source()
 async def test_guard_rejects_production_discovery_before_transport(self):
  async def must_not_run(scope,receive,send):raise AssertionError('Untrusted endpoint reached app')
  transport=preflight.LocalOnly(must_not_run)
  with self.assertRaises(RuntimeError):await transport.handle_async_request(httpx.Request('GET','https://ipvx.org/.well-known/agent-card.json'))
  self.assertEqual(transport.calls,0)
class Readiness(unittest.TestCase):
 def setUp(self):self.plan=json.loads((HERE/'protocol.json').read_text());self.now=datetime(2026,10,29,tzinfo=timezone.utc)
 def complete_fixture(self):
  p=self.plan;p['partner'].update(role='independent-client-runner',environment={'language':'synthetic','runtime_version':'fixture','os':'fixture'},resource_authority_confirmed=True,agreement_comment_id='synthetic-fixture-only',scope_confirmed=True,retention_confirmed=True,window_confirmed=True)
  p['proposed_window']['accepted']=True;p['local_preflight_passed']=True
  digest=readiness.scope_digest(p);p['protocol_hash_acknowledged']={role:{'scope_sha256':digest,'evidence':'synthetic-test-only'}for role in ['owner','partner']}
 def test_passing_preflight_does_not_imply_partner_readiness(self):
  r=readiness.evaluate(self.plan,self.now);self.assertFalse(r['ready_to_launch']);self.assertIn('partner_environment_missing',r['missing'])
 def test_request_ready_still_requires_owner_launch_decision(self):
  self.complete_fixture();r=readiness.evaluate(self.plan,self.now)
  self.assertTrue(r['ready_to_request_launch']);self.assertFalse(r['ready_to_launch'])
  self.plan['owner_launch_decision']=True;self.assertTrue(readiness.evaluate(self.plan,self.now)['ready_to_launch'])
 def test_scope_change_invalidates_existing_hash_ack(self):
  self.complete_fixture();self.plan['limits']['hours_per_operator']=3
  r=readiness.evaluate(self.plan,self.now);self.assertIn('frozen_protocol_hash_not_acknowledged_by_both',r['missing'])
 def test_reviewer_role_or_expired_window_cannot_count_as_joint_execution(self):
  self.complete_fixture();self.plan['partner']['role']='protocol-reviewer';r=readiness.evaluate(self.plan,self.now);self.assertFalse(r['ready_to_request_launch'])
  self.complete_fixture();r=readiness.evaluate(self.plan,datetime(2026,10,31,tzinfo=timezone.utc));self.assertIn('window_expired',r['missing'])
