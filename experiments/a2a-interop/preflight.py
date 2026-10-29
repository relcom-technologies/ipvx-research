"""Local ASGI instrumentation check only. No external network or partner execution."""
import argparse,asyncio,copy,hashlib,importlib.metadata,json,os,platform,shutil,sqlite3,sys,tempfile
from pathlib import Path
import httpx
from google.protobuf.json_format import ParseDict,MessageToDict
from a2a.client import ClientFactory,ClientConfig
from a2a.types import a2a_pb2 as pb
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'protocol.json').read_text())
LOCAL='http://127.0.0.1:8765'

def verify_source():
 for name,expected in PLAN['source_sha256'].items():
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('Pinned source mismatch: '+name)
 for name,expected in PLAN.get('harness_sha256',{}).items():
  if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:raise ValueError('Pinned harness mismatch: '+name)
 if importlib.metadata.version('a2a-sdk')!=PLAN['control_environment']['a2a_sdk']:raise ValueError('SDK version differs from protocol')

def save_outbox(path,account,params):
 raw=json.dumps({'account':account,'params':params},sort_keys=True,separators=(',',':')).encode()
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb')as out:out.write(raw);out.flush();os.fsync(out.fileno())
 return hashlib.sha256(raw).hexdigest()

def reverse_keys(value):
 if isinstance(value,dict):return {k:reverse_keys(v)for k,v in reversed(list(value.items()))}
 if isinstance(value,list):return [reverse_keys(v)for v in value]
 return value

class LocalOnly(httpx.AsyncBaseTransport):
 def __init__(self,app):self.inner=httpx.ASGITransport(app=app);self.calls=0
 async def handle_async_request(self,request):
  if request.url.host!='127.0.0.1' or request.url.port!=8765:raise RuntimeError('Fixture attempted non-local network target')
  self.calls+=1;return await self.inner.handle_async_request(request)
 async def aclose(self):await self.inner.aclose()

def params(identifier,title='synthetic recovery fixture'):
 return {'message':{'messageId':identifier,'role':'ROLE_USER','parts':[{'data':{'action':'submit_proposal','kind':'experiment','title':title,'summary':'Synthetic fixture only; no real participation or resources requested.'}}]}}
async def rpc(http,token,method,body,identifier):
 return await http.post('/a2a',headers={'Authorization':'Bearer '+token,'A2A-Version':'1.0'},json={'jsonrpc':'2.0','id':identifier,'method':method,'params':body})
def receipt(response):
 assert response.status_code==200,response.text
 task=response.json()['result']['task'];return task['artifacts'][0]['parts'][0]['data']['id'],task['id']
def count(store):
 with store.db()as db:return db.execute('SELECT count(*) FROM proposals').fetchone()[0]

async def run():
 verify_source();sys.path.insert(0,str(ROOT/'infra'));import a2a_service
 original_card=copy.deepcopy(a2a_service.CARD);a2a_service.CARD=copy.deepcopy(original_card)
 a2a_service.CARD['supportedInterfaces']=[{'url':LOCAL+'/a2a','protocolBinding':'JSONRPC','protocolVersion':'1.0'}]
 key=b'x'*32
 assert len(key)==32
 result={'schema_version':1,'protocol_id':PLAN['protocol_id'],'protocol_version':PLAN['version'],'classification':'local_preflight_only','transport':'in-process ASGI; no physical/network exchange','operator':'project owner via Codex','partner_execution':False,'joint_experiment_started':False,'server_revision':PLAN['server_revision'],'python':platform.python_version(),'sdk':importlib.metadata.version('a2a-sdk'),'card_override':{'production_original_url':original_card['supportedInterfaces'][0]['url'],'fixture_only_url':LOCAL+'/a2a'},'cases':{}}
 try:
  with tempfile.TemporaryDirectory(prefix='ipvx-interop-')as tmp:
   base=Path(tmp);public=base/'public';(public/'data').mkdir(parents=True)
   (public/'data/agent-discovery.json').write_text(json.dumps({'name':'synthetic local fixture'}));(public/'data/strict-agent-manifest.json').write_text(json.dumps({'status':'fixture'}))
   app=a2a_service.create_app(base/'master',public,key,PLAN['server_revision']);transport=LocalOnly(app)
   async with app.app.router.lifespan_context(app.app):
    async with httpx.AsyncClient(transport=transport,base_url=LOCAL)as http:
     account=(await http.post('/a2a/register',json={'name':'synthetic client A'})).json();other=(await http.post('/a2a/register',json={'name':'synthetic client B'})).json();token=account['accessToken']
     card_data=(await http.get('/.well-known/agent-card.json')).json();assert card_data['supportedInterfaces'][0]['url']==LOCAL+'/a2a'
     # SDK control checks the local fixture, never the production URL.
     http.headers['Authorization']='Bearer '+token
     sdk=ClientFactory(ClientConfig(httpx_client=http,streaming=False)).create(ParseDict(card_data,pb.AgentCard()))
     probe=ParseDict({'message':{'messageId':'sdk-preflight-read','role':'ROLE_USER','parts':[{'data':{'action':'get_project'}}]}},pb.SendMessageRequest())
     events=[event async for event in sdk.send_message(probe)];assert MessageToDict(events[0].message.parts[0])['data']['project']['name']=='synthetic local fixture'
     original=params('interop-A-original');save_outbox(base/'outbox.json',account['clientId'],original)
     first=await rpc(http,token,'SendMessage',original,'oracle-first');oracle_ids=receipt(first)
     # The completed reply is intentionally withheld from the simulated client.
     changed=copy.deepcopy(original);changed['message']['parts'][0]['data']['summary']='Injected accidental change for the conflict test.'
     conflict=await rpc(http,token,'SendMessage',changed,'conflict');assert conflict.status_code==409 and conflict.json()['error']=='message_id_reused'
     persisted=json.loads((base/'outbox.json').read_text())['params'];recovered=[]
     for index in range(5):recovered.append(receipt(await rpc(http,token,'SendMessage',reverse_keys(persisted),'recover-'+str(index))))
     assert all(ids==oracle_ids for ids in recovered)and count(app.store)==1
     forbidden=await rpc(http,other['accessToken'],'GetTask',{'id':oracle_ids[1]},'foreign');assert 'error'in forbidden.json()
     result['cases']['A']={'outbox_saved_before_send':True,'lost_reply_simulated_after_completed_server_response':True,'conflict_http':409,'reordered_key_replay_recovered_original_ids':True,'replays':5,'logical_proposals':1,'foreign_task_read_rejected':True}
     # Two otherwise identical submissions make account-level task enumeration ambiguous.
     b1=params('interop-B-intended');b2=params('interop-B-decoy');b_ids=receipt(await rpc(http,token,'SendMessage',b1,'B1'));receipt(await rpc(http,token,'SendMessage',b2,'B2'))
     before=count(app.store);calls_before=transport.calls
     lost_client_state={'outbox':None,'proposalId':None,'taskId':None,'credentials_retained':True}
     outcome='unknown'if not any(lost_client_state[k]for k in ['outbox','proposalId','taskId'])else'recoverable'
     assert outcome=='unknown'and transport.calls==calls_before and count(app.store)==before==3
     result['cases']['B']={'local_params_and_ids_intentionally_unavailable':True,'ambiguous_same_account_records':2,'client_outcome':outcome,'automatic_replacement_requests':0,'logical_proposals_before':before,'logical_proposals_after':count(app.store)}
   # Copy after closing the first engine. Only the sacrificial proposal row is removed.
   master_digest=hashlib.sha256((base/'master/intake.sqlite3').read_bytes()).hexdigest();shutil.copytree(base/'master',base/'sacrificial')
   with sqlite3.connect(base/'sacrificial/intake.sqlite3')as db:db.execute('DELETE FROM proposals WHERE id=?',(b_ids[0],))
   copied=a2a_service.create_app(base/'sacrificial',public,key,PLAN['server_revision'])
   async with copied.app.router.lifespan_context(copied.app):
    async with httpx.AsyncClient(transport=LocalOnly(copied),base_url=LOCAL)as http:
     q={'message':{'messageId':'retention-current-poll','role':'ROLE_USER','parts':[{'data':{'action':'get_proposal_status','proposalId':b_ids[0]}}]}}
     missing=await rpc(http,token,'SendMessage',q,'missing');assert 'error'in missing.json()
     old_task=await rpc(http,token,'GetTask',{'id':b_ids[1]},'retained-task');assert 'result'in old_task.json()
     assert hashlib.sha256((base/'master/intake.sqlite3').read_bytes()).hexdigest()==master_digest
     result['cases']['R']={'removal_only_in_sacrificial_copy':True,'live_proposal_lookup_error':missing.json()['error'],'task_receipt_can_outlive_proposal':True,'master_database_unchanged':True,'client_required_outcome':'unknown/unavailable; no automatic replacement','automatic_ttl_implementation_claimed':False}
   result['network_requests_outside_fixture']=0;result['status']='passed';result['ready_to_launch']=False
   result['remaining_gates']=[g for g in PLAN['launch_gates']if g!='local_preflight_passed']
   return result
 finally:a2a_service.CARD=original_card

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();report=asyncio.run(run());p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':report['status'],'classification':report['classification'],'cases':list(report['cases']),'ready_to_launch':report['ready_to_launch'],'output':str(p)}))
