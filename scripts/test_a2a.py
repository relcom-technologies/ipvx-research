"""A2A SDK interoperability and private proposal boundaries; synthetic local accounts."""
import asyncio
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import httpx
from google.protobuf.json_format import ParseDict, MessageToDict
from a2a.client import ClientFactory, ClientConfig
from a2a.types import a2a_pb2 as pb
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'infra'))
from a2a_service import create_app
from a2a_store import IntakeStore,IntakeError,admin_signature,canonical
from community import CommunityService
from auth import AuthService

PAYLOAD={'action':'submit_proposal','kind':'experiment','title':'Independent reproduction','summary':'Reproduce published delivery results and retain negative outcomes.'}
class StoreTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.now=2_000_000_000
  self.store=IntakeStore(self.temp.name,clock=lambda:self.now)
 def tearDown(self):self.temp.cleanup()
 def test_credentials_expire_and_are_not_stored(self):
  account=self.store.register({'name':'Local fixture'})
  self.assertEqual(self.store.authenticate('Bearer '+account['accessToken'])['id'],account['clientId'])
  self.assertNotIn(account['accessToken'],self.store.database.read_bytes().decode(errors='ignore'))
  self.now+=account['expiresIn']
  with self.assertRaises(IntakeError) as error:self.store.authenticate('Bearer '+account['accessToken'])
  self.assertEqual(error.exception.status,401)
 def test_proposals_idempotent_and_private(self):
  a=self.store.register({'name':'A'});b=self.store.register({'name':'B'})
  first=self.store.submit(a['clientId'],'same-message',PAYLOAD)
  self.assertEqual(first,self.store.submit(a['clientId'],'same-message',PAYLOAD))
  with self.assertRaises(IntakeError):self.store.submit(a['clientId'],'same-message',{**PAYLOAD,'title':'Changed'})
  with self.assertRaises(IntakeError):self.store.own_proposal(b['clientId'],first['id'])
  self.assertEqual(first['status'],'pending_owner')
  restored=IntakeStore(self.temp.name,clock=lambda:self.now)
  self.assertEqual(restored.own_proposal(a['clientId'],first['id'])['id'],first['id'])
 def test_owner_decision_signed_replay_protected_and_no_execution(self):
  a=self.store.register({'name':'A'});p=self.store.submit(a['clientId'],'one-message',PAYLOAD)
  key=b'x'*32;path='/internal/proposals/'+p['id']+'/decision';body={'decision':'approved_for_discussion','reason':'Check reproducibility first','actor':'owner-fixture','requestId':'decision-fixture'}
  raw=canonical(body).encode();stamp=str(self.now);nonce=secrets.token_hex(16)
  headers={'x-ipvx-time':stamp,'x-ipvx-nonce':nonce,'x-ipvx-signature':admin_signature(key,'POST',path,raw,stamp,nonce)}
  with self.assertRaises(IntakeError):self.store.verify_admin(key,'POST',path,raw,{})
  self.store.verify_admin(key,'POST',path,raw,headers)
  with self.assertRaises(IntakeError):self.store.verify_admin(key,'POST',path,raw,headers)
  result=self.store.decide(p['id'],body)
  self.assertFalse(result['executionGranted']);self.assertFalse(result['publicationGranted'])
  self.assertTrue(self.store.decide(p['id'],body)['idempotent'])
  self.assertEqual(self.store.owner_list()['proposals'][0]['status'],'approved_for_discussion')
 def test_limits_and_invalid_reference(self):
  a=self.store.register({'name':'A'})
  with self.assertRaises(IntakeError):self.store.submit(a['clientId'],'invalid-url',{**PAYLOAD,'references':['file:///etc/passwd']})
  for i in range(10):self.store.submit(a['clientId'],'message-'+str(i),PAYLOAD)
  with self.assertRaises(IntakeError) as error:self.store.submit(a['clientId'],'message-excess',PAYLOAD)
  self.assertEqual(error.exception.status,429)
 def test_only_pinned_owner_not_other_admin(self):
  community=CommunityService(Path(self.temp.name)/'community',bootstrap_admin_sub='owner')
  owner={'sub':'owner','emailVerified':True};other={'sub':'other','emailVerified':True}
  with community._db() as db:
   community._enroll(db,community._principal(other));db.execute('INSERT INTO roles VALUES(?,?)',(community._principal(other),'admin'))
  self.assertIsNotNone(community.owner_identity(owner));self.assertIsNone(community.owner_identity(other))
  self.assertIsNone(community.owner_identity(None));self.assertIsNone(community.owner_identity({**owner,'emailVerified':False}))

class ServiceTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.key=b'x'*32
  self.app=create_app(Path(self.temp.name)/'state',ROOT,self.key,'test-revision')
  self.lifespan=self.app.app.router.lifespan_context(self.app.app);await self.lifespan.__aenter__()
  self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='https://ipvx.org',headers={'A2A-Version':'1.0'})
  self.a=(await self.http.post('/a2a/register',json={'name':'Fixture A'})).json()
  self.b=(await self.http.post('/a2a/register',json={'name':'Fixture B'})).json()
 async def asyncTearDown(self):
  await self.http.aclose();await self.lifespan.__aexit__(None,None,None);self.temp.cleanup()
 def rpc(self,payload,message='fixture-message-0001',rpc_id=1):
  return {'jsonrpc':'2.0','id':rpc_id,'method':'SendMessage','params':{'message':{'messageId':message,'role':'ROLE_USER','parts':[{'data':payload}]}}}
 async def call(self,body,account=None):return await self.http.post('/a2a',json=body,headers={'Authorization':'Bearer '+(account or self.a)['accessToken']})
 async def test_official_sdk_client_and_task_isolation(self):
  card=ParseDict((await self.http.get('/.well-known/agent-card.json')).json(),pb.AgentCard())
  self.http.headers['Authorization']='Bearer '+self.a['accessToken']
  client=ClientFactory(ClientConfig(httpx_client=self.http,streaming=False)).create(card)
  events=[e async for e in client.send_message(ParseDict({'message':self.rpc({'action':'get_project'})['params']['message']},pb.SendMessageRequest()))]
  self.assertEqual(len(events),1);self.assertTrue(events[0].HasField('message'))
  self.assertIn('project',MessageToDict(events[0].message.parts[0])['data'])
  request=ParseDict({'message':self.rpc(PAYLOAD,'fixture-sdk-proposal')['params']['message']},pb.SendMessageRequest())
  events=[e async for e in client.send_message(request)]
  task=events[0].task;self.assertEqual(task.status.state,pb.TASK_STATE_COMPLETED)
  receipt=MessageToDict(task.artifacts[0].parts[0])['data'];self.assertEqual(receipt['status'],'pending_owner')
  for account,expected in [(self.a,True),(self.b,False)]:
   response=(await self.call({'jsonrpc':'2.0','id':2,'method':'GetTask','params':{'id':task.id}},account)).json()
   self.assertEqual('result' in response,expected,response)
   response=(await self.call({'jsonrpc':'2.0','id':3,'method':'ListTasks','params':{}},account)).json()
   tasks=response.get('result',{}).get('tasks',[])
   self.assertEqual(any(t['id']==task.id for t in tasks),expected,response)
  foreign=(await self.call(self.rpc({'action':'get_proposal_status','proposalId':receipt['id']},'fixture-status-other'),self.b)).json()
  self.assertIn('error',foreign)
 async def test_retry_restart_and_conflicting_message(self):
  body=self.rpc(PAYLOAD);r1=(await self.call(body)).json();body['id']=2;r2=(await self.call(body)).json()
  self.assertEqual(r1['result'],r2['result']);self.assertEqual(r2['id'],2)
  conflict=self.rpc({**PAYLOAD,'title':'Conflicting contents'})
  self.assertEqual((await self.call(conflict)).status_code,409)
  await self.lifespan.__aexit__(None,None,None)
  self.app=create_app(Path(self.temp.name)/'state',ROOT,self.key,'test-revision')
  self.lifespan=self.app.app.router.lifespan_context(self.app.app);await self.lifespan.__aenter__()
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='https://ipvx.org') as http:
   r=await http.post('/a2a',json=body,headers={'Authorization':'Bearer '+self.a['accessToken'],'A2A-Version':'1.0'})
   self.assertEqual(r.json()['result'],r1['result'])
 async def test_boundary_and_malformed_requests(self):
  self.assertEqual((await self.http.post('/a2a',json=self.rpc(PAYLOAD))).status_code,401)
  self.assertEqual((await self.http.get('/internal/proposals')).status_code,403)
  self.assertEqual((await self.http.post('/a2a/register',content=b'{"name":"A","name":"B"}',headers={'Content-Type':'application/json'})).status_code,400)
  self.assertEqual((await self.http.post('/a2a/register',content=b'x'*17000,headers={'Content-Type':'application/json'})).status_code,413)
  bad=self.rpc(PAYLOAD);bad['params']['message']['parts']=[{'url':'https://example.invalid/'}]
  self.assertEqual((await self.call(bad)).status_code,400)
  bad=self.rpc(PAYLOAD);bad['params']['configuration']={'pushNotificationConfig':{'url':'https://example.invalid/'}}
  self.assertEqual((await self.call(bad)).status_code,400)
 async def test_worst_case_unicode_queue_stays_within_proxy_bound(self):
  for i in range(6):
   payload={**PAYLOAD,'summary':'🧬'*3000}
   r=await self.call(self.rpc(payload,'unicode-message-'+str(i),i))
   self.assertIn('result',r.json())
  stamp=str(int(time.time()));nonce=secrets.token_hex(16);path='/internal/proposals'
  r=await self.http.get(path,headers={'X-IPvX-Time':stamp,'X-IPvX-Nonce':nonce,'X-IPvX-Signature':admin_signature(self.key,'GET',path,b'',stamp,nonce)})
  self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['proposals']),5)
  self.assertEqual(r.json()['nextOffset'],5);self.assertLess(len(r.content),131072)
 async def test_owner_private_queue_and_decision(self):
  response=(await self.call(self.rpc(PAYLOAD))).json();p=response['result']['task']['artifacts'][0]['parts'][0]['data']
  async def admin(method,path,body=None):
   raw=canonical(body).encode() if body else b'';stamp=str(int(time.time()));nonce=secrets.token_hex(16)
   return await self.http.request(method,path,content=raw,headers={'Content-Type':'application/json','X-IPvX-Time':stamp,'X-IPvX-Nonce':nonce,'X-IPvX-Signature':admin_signature(self.key,method,path,raw,stamp,nonce)})
  queue=(await admin('GET','/internal/proposals')).json();self.assertEqual(queue['proposals'][0]['id'],p['id'])
  result=await admin('POST','/internal/proposals/'+p['id']+'/decision',{'decision':'declined','reason':'Need an exact revision','requestId':'decision-one','actor':'owner-fixture'})
  self.assertEqual(result.status_code,200);self.assertEqual(result.json()['status'],'declined')
  status=(await self.call(self.rpc({'action':'get_proposal_status','proposalId':p['id']},'fixture-new-status'))).json()
  self.assertEqual(status['result']['message']['parts'][0]['data']['status'],'declined')

if __name__=='__main__':unittest.main()

class OwnerBridgeTests(unittest.TestCase):
 def test_verified_owner_and_origin_are_required_at_auth_boundary(self):
  with tempfile.TemporaryDirectory() as tmp:
   community=CommunityService(Path(tmp)/'community',bootstrap_admin_sub='owner')
   class Bridge:
    def __init__(self):self.calls=[]
    def handle(self,*args):self.calls.append(args);return 200,{'proposals':[]}
   bridge=Bridge();service=AuthService('fixture-client','fixture-org',Path(tmp)/'auth',community=community,a2a_admin=bridge)
   headers={'Host':'ipvx.org','Origin':'https://ipvx.org','Content-Type':'application/json'};path='/community/v1/agents/proposals'
   for user in (None,{'sub':'reader','emailVerified':True},{'sub':'owner','emailVerified':False}):
    with patch.object(service,'_session',return_value=(None,{'user':user}) if user else (None,None)):
     self.assertEqual(service.handle_community('GET',path,headers).status,403)
   self.assertEqual(bridge.calls,[])
   with patch.object(service,'_session',return_value=(None,{'user':{'sub':'owner','emailVerified':True}})):
    self.assertEqual(service.handle_community('GET',path,headers).status,200)
    self.assertTrue(bridge.calls[-1][2].startswith('member_'))
    self.assertEqual(service.handle_community('POST',path+'/proposal_'+'a'*24+'/decision',{**headers,'Origin':'https://evil.invalid'},b'{}').status,403)
    self.assertEqual(service.handle_community('GET',path+'?actor=owner',headers).status,400)
 def test_bridge_uses_only_fixed_loopback_and_server_actor(self):
  from a2a_admin import A2AAdmin
  adapter=A2AAdmin(b'x'*32)
  with patch('a2a_admin.HTTPConnection') as http:
   http.return_value.getresponse.return_value.status=200
   http.return_value.getresponse.return_value.read.return_value=b'{"proposals":[]}'
   adapter.handle('GET','/community/v1/agents/proposals','verified-owner')
   self.assertEqual(http.call_args.args,('127.0.0.1',8095))
   method,path=http.return_value.request.call_args.args
   self.assertEqual((method,path),('GET','/internal/proposals'))
   status,_=adapter.handle('POST','/community/v1/agents/proposals/proposal_'+'a'*24+'/decision','verified-owner',{'decision':'declined','reason':'fixture reason','requestId':'fixture-1','actor':'forged-owner'})
   self.assertEqual(status,400)
