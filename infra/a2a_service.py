"""A2A 1.0 research liaison using the official SDK. No LLM or code execution."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from a2a.auth.user import User
from a2a.server.agent_execution import AgentExecutor
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import DatabaseTaskStore
from a2a.types import a2a_pb2 as pb
from a2a.utils.errors import InvalidParamsError, TaskNotCancelableError
from a2a_store import IntakeError, IntakeStore, canonical, digest

ORIGIN='https://ipvx.org'
MAX_BODY=16384
CARD={
 'name':'IPvX Research Liaison',
 'description':'Project evidence and private research-proposal intake. Deterministic service; no autonomous researcher, model execution or native IPvX admission. Owner approval is separate from receipt.',
 'supportedInterfaces':[{'url':ORIGIN+'/a2a','protocolBinding':'JSONRPC','protocolVersion':'1.0'}],
 'provider':{'url':ORIGIN,'organization':'IPvX Research'},'version':'0.1.0',
 'documentationUrl':ORIGIN+'/agents.html','capabilities':{'streaming':False,'pushNotifications':False,'extendedAgentCard':False},
 'securitySchemes':{'intakeBearer':{'httpAuthSecurityScheme':{'scheme':'bearer','bearerFormat':'opaque; obtain a scoped token at POST /a2a/register'}}},
 'securityRequirements':[{'schemes':{'intakeBearer':[]}}],
 'defaultInputModes':['application/json'],'defaultOutputModes':['application/json'],
 'skills':[
  {'id':'project-evidence','name':'Read project evidence','description':'Send a DataPart with action=get_project to obtain links and the current published record.','tags':['research','evidence'],'examples':['{"action":"get_project"}']},
  {'id':'research-proposal','name':'Submit a research proposal','description':'Send action=submit_proposal with kind, title, summary and optional references/rfc. A completed intake task confirms receipt only.','tags':['rfc','experiment','code','compute'],'examples':['{"action":"submit_proposal","kind":"experiment","title":"Independent reproduction","summary":"Reproduce a published experiment and report results."}']},
  {'id':'proposal-status','name':'Read own proposal status','description':'Send action=get_proposal_status and proposalId; only the bearer account that submitted it can read it.','tags':['review','owner-decision'],'examples':['{"action":"get_proposal_status","proposalId":"proposal_..."}']}
 ]}

def strict_json(raw):
 def pairs(items):
  value={}
  for k,v in items:
   if k in value:raise ValueError('duplicate key')
   value[k]=v
  return value
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('constant')))

class IntakeUser(User):
 def __init__(self,client):self.client=client
 @property
 def is_authenticated(self):return True
 @property
 def user_name(self):return self.client

class ContextBuilder(DefaultServerCallContextBuilder):
 def build_user(self,request):return IntakeUser(request.state.intake_client)

class Executor(AgentExecutor):
 def __init__(self,store,public_dir):self.store,self.public_dir=store,Path(public_dir)
 def project(self):
  directory=json.loads((self.public_dir/'data/agent-discovery.json').read_text())
  manifest=json.loads((self.public_dir/'data/strict-agent-manifest.json').read_text())
  return {'project':directory,'recordingManifest':manifest,'service':'deterministic A2A research liaison','ownerApprovalRequired':True,'nativeTransport':'This HTTPS service is separate from the experimental native Ethernet transport.'}
 async def execute(self,context,event_queue):
  message=context.message;client=context.call_context.user.user_name
  data=MessageToDict(message.parts[0])['data'];action=data.get('action')
  try:
   if action=='get_project':
    result=self.project()
   elif action=='get_proposal_status':
    if set(data)!={'action','proposalId'}:raise IntakeError(400,'invalid_status_request')
    result=self.store.own_proposal(client,data['proposalId'])
   elif action=='submit_proposal':
    proposal=self.store.submit(client,message.message_id,data)
    status=pb.TaskStatus(state=pb.TASK_STATE_COMPLETED);status.timestamp.GetCurrentTime()
    task=pb.Task(id=context.task_id,context_id=context.context_id,status=status)
    artifact=task.artifacts.add(artifact_id=str(uuid.uuid4()),name='proposal-receipt',description='Intake completed; contribution is pending separate owner review.')
    ParseDict({'data':proposal},artifact.parts.add())
    await event_queue.enqueue_event(task);return
   else:raise IntakeError(400,'unknown_action')
  except IntakeError as exc:raise InvalidParamsError(message=exc.code) from None
  response=pb.Message(message_id=str(uuid.uuid4()),role=pb.ROLE_AGENT,context_id=context.context_id)
  ParseDict({'data':result},response.parts.add());await event_queue.enqueue_event(response)
 async def cancel(self,context,event_queue):raise TaskNotCancelableError(message='Intake tasks complete immediately; no work is executing.')

class GuardedApplication:
 def __init__(self,app,store,key):self.app,self.store,self.key=app,store,key;self.locks={}
 async def reply(self,scope,receive,send,status,data,extra=None):
  headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',**(extra or {})}
  await JSONResponse(data,status_code=status,headers=headers)(scope,receive,send)
 async def __call__(self,scope,receive,send):
  if scope['type']!='http':return await self.app(scope,receive,send)
  path=scope['path'];method=scope['method'];headers={k.decode().lower():v.decode() for k,v in scope.get('headers',[])}
  if path=='/.well-known/agent-card.json' and method in ('GET','HEAD'):
   return await self.app(scope,receive,send)
  if path=='/healthz' and method=='GET':return await self.app(scope,receive,send)
  if scope.get('query_string'):return await self.reply(scope,receive,send,400,{'error':'query_not_supported'})
  try:
   if len(headers.get('authorization',''))>256:raise IntakeError(401,'invalid_token')
   if method not in ('GET','POST'):raise IntakeError(405,'method_not_allowed')
   raw=b''
   if method=='POST':
    if headers.get('content-type','').split(';',1)[0]!='application/json':raise IntakeError(415,'json_required')
    while True:
     item=await asyncio.wait_for(receive(),10)
     if item['type']=='http.disconnect':return
     raw+=item.get('body',b'')
     if len(raw)>MAX_BODY:raise IntakeError(413,'request_too_large')
     if not item.get('more_body',False):break
    data=strict_json(raw)
    if not isinstance(data,dict):raise IntakeError(400,'object_required')
   else:data={}
   if path=='/a2a/register' and method=='POST':
    result=self.store.register(data)
    return await self.reply(scope,receive,send,201,result)
   if path.startswith('/internal/'):
    self.store.verify_admin(self.key,method,path,raw,headers)
    if path=='/internal/proposals' and method=='GET':result=self.store.owner_list()
    elif re.fullmatch(r'/internal/proposals/page/[0-9]{1,4}',path) and method=='GET':result=self.store.owner_list(int(path.rsplit('/',1)[1]))
    elif re.fullmatch(r'/internal/proposals/proposal_[a-f0-9]{24}/decision',path) and method=='POST':result=self.store.decide(path.split('/')[3],data)
    else:raise IntakeError(404,'not_found')
    return await self.reply(scope,receive,send,200,result)
   if path!='/a2a' or method!='POST':raise IntakeError(404,'not_found')
   client=self.store.authenticate(headers.get('authorization'))
   scope.setdefault('state',{})['intake_client']=client['id']
   if data.get('jsonrpc')!='2.0' or not isinstance(data.get('id'),(str,int)) or isinstance(data.get('id'),bool) or len(str(data['id']))>128:raise IntakeError(400,'invalid_jsonrpc_request')
   supported={'SendMessage','GetTask','ListTasks','CancelTask','SendStreamingMessage','SubscribeToTask','GetExtendedAgentCard','CreateTaskPushNotificationConfig','GetTaskPushNotificationConfig','ListTaskPushNotificationConfigs','DeleteTaskPushNotificationConfig'}
   if data.get('method') not in supported:raise IntakeError(400,'unsupported_method')
   message_id=fingerprint=None
   if data['method']=='SendMessage':
    params=data.get('params',{});message=params.get('message',{});parts=message.get('parts',[])
    # Every intake is a new completed receipt; continuations and callbacks are not supported.
    if message.get('taskId') or message.get('contextId') or params.get('configuration',{}).get('pushNotificationConfig'):raise IntakeError(400,'continuations_and_callbacks_not_supported')
    if not isinstance(message.get('messageId'),str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{8,128}',message['messageId']):raise IntakeError(400,'message_id_required')
    if message.get('role')!='ROLE_USER' or not isinstance(parts,list) or len(parts)!=1 or not isinstance(parts[0],dict) or set(parts[0])!={'data'} or not isinstance(parts[0]['data'],dict):raise IntakeError(400,'one_json_data_part_required')
    payload=parts[0]['data']
    if payload.get('action') not in ('get_project','submit_proposal','get_proposal_status'):raise IntakeError(400,'unknown_action')
    if payload['action']=='get_project' and set(payload)!={'action'}:raise IntakeError(400,'invalid_project_request')
    message_id=message['messageId'];fingerprint=digest(canonical(params))
    cached=self.store.cached(client['id'],message_id,fingerprint)
    if cached is not None:
     cached['id']=data['id'];return await self.reply(scope,receive,send,200,cached)
    if len(self.locks)>=1000:raise IntakeError(503,'intake_busy')
   lock_key=(client['id'],message_id) if message_id else None
   lock=self.locks.setdefault(lock_key,asyncio.Lock()) if lock_key else asyncio.Lock()
   async with lock:
    if message_id:
     cached=self.store.cached(client['id'],message_id,fingerprint)
     if cached is not None:
      cached['id']=data['id'];return await self.reply(scope,receive,send,200,cached)
    sent=[];delivered=False
    async def replay():
     nonlocal delivered
     if delivered:return {'type':'http.disconnect'}
     delivered=True;return {'type':'http.request','body':raw,'more_body':False}
    async def capture(item):sent.append(item)
    await self.app(scope,replay,capture)
    body=b''.join(x.get('body',b'') for x in sent if x['type']=='http.response.body')
    if len(body)>131072:raise IntakeError(503,'response_too_large')
    if message_id:
     result=json.loads(body)
     if 'result' in result:self.store.save_receipt(client['id'],message_id,fingerprint,result)
    for item in sent:
     if item['type']=='http.response.start':item['headers']=[(k,v)for k,v in item['headers']if k.lower()!=b'cache-control']+[(b'cache-control',b'no-store')]
     await send(item)

  except IntakeError as exc:
   await self.reply(scope,receive,send,exc.status,{'error':exc.code}, {'WWW-Authenticate':'Bearer'} if exc.status==401 else None)
  except (ValueError,TypeError,KeyError,AttributeError,RecursionError,UnicodeError,TimeoutError):
   await self.reply(scope,receive,send,400,{'error':'invalid_request'})
  except (sqlite3.Error,OSError):
   await self.reply(scope,receive,send,503,{'error':'intake_temporarily_unavailable'})
  finally:
   if 'lock_key' in locals() and lock_key and not lock.locked() and not getattr(lock,'_waiters',None):self.locks.pop(lock_key,None)


def create_app(state_dir,public_dir,key,revision='development'):
 if not isinstance(key,bytes) or len(key)!=32:raise ValueError('A private 32-byte administrative key is required')
 store=IntakeStore(state_dir);tasks_file=store.root/'tasks.sqlite3'
 if tasks_file.is_symlink():raise ValueError('Task database cannot be a symbolic link')
 fd=os.open(tasks_file,os.O_WRONLY|os.O_CREAT,0o600);os.close(fd);tasks_file.chmod(0o600)
 engine=create_async_engine('sqlite+aiosqlite:///'+str(tasks_file))
 task_store=DatabaseTaskStore(engine)
 card=ParseDict(CARD,pb.AgentCard())
 handler=DefaultRequestHandler(agent_executor=Executor(store,public_dir),task_store=task_store,agent_card=card)
 @asynccontextmanager
 async def lifespan(app):
  yield
  await engine.dispose()
 async def health(request):return JSONResponse({'status':'ok','revision':revision,'protocol':'A2A/1.0','execution':'none'})
 app=Starlette(routes=[*create_agent_card_routes(card,cache_control='public, max-age=300'),*create_jsonrpc_routes(handler,'/a2a',context_builder=ContextBuilder()),Route('/healthz',health)],lifespan=lifespan)
 return GuardedApplication(app,store,key)

if __name__=='__main__':
 import uvicorn
 credential=Path(os.environ['CREDENTIALS_DIRECTORY'])/'ipvx-a2a-admin'
 application=create_app(os.environ['IPVX_A2A_STATE_DIR'],os.environ['IPVX_PUBLIC_DIR'],credential.read_bytes(),os.environ['IPVX_RELEASE_REVISION'])
 uvicorn.run(application,host='127.0.0.1',port=8095,access_log=False,log_level='critical',limit_concurrency=24,limit_max_requests=50000,timeout_keep_alive=2)
