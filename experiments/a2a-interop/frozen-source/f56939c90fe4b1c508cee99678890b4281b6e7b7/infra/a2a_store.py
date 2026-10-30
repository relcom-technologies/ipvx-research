"""Private research-intake state. No execution, outbound requests, roles or publication."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from urllib.parse import urlsplit

MAX_CLIENTS=2000
MAX_PROPOSALS=5000
MAX_RECEIPTS=10000
MAX_AUDIT=15000
TOKEN_SECONDS=30*86400
KINDS={'experiment','rfc','code','compute'}

class IntakeError(Exception):
 def __init__(self,status,code): self.status,self.code=status,code

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def text(value,minimum=1,maximum=8000):
 if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum or any(ord(x)<32 and x not in '\n\t' or ord(x)==127 for x in value): raise IntakeError(400,'invalid_text')
 return value.strip()
def private_directory(value):
 path=Path(value)
 if path.is_symlink(): raise ValueError('Private state cannot be a symbolic link')
 path.mkdir(mode=0o700,parents=True,exist_ok=True);path.chmod(0o700)
 return path

def admin_signature(key,method,path,body,stamp,nonce):
 value='\n'.join((method,path,stamp,nonce,hashlib.sha256(body).hexdigest())).encode()
 return hmac.new(key,value,hashlib.sha256).hexdigest()

class IntakeStore:
 def __init__(self,directory,clock=time.time):
  self.root=private_directory(directory);self.clock=clock;self.database=self.root/'intake.sqlite3'
  if self.database.is_symlink() or self.database.exists() and not self.database.is_file(): raise ValueError('Private database must be a regular file')
  fd=os.open(self.database,os.O_WRONLY|os.O_CREAT,0o600);os.close(fd);self.database.chmod(0o600)
  with self.db() as db:
   db.executescript('''
    CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY,name TEXT,token_hash TEXT UNIQUE,created INTEGER,expires INTEGER,blocked INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,client TEXT,message_id TEXT,fingerprint TEXT,kind TEXT,title TEXT,summary TEXT,reference_urls TEXT,rfc TEXT,status TEXT,reason TEXT,created INTEGER,updated INTEGER,UNIQUE(client,message_id));
    CREATE TABLE IF NOT EXISTS receipts(client TEXT,message_id TEXT,fingerprint TEXT,result TEXT,created INTEGER,PRIMARY KEY(client,message_id));
    CREATE TABLE IF NOT EXISTS rates(scope TEXT,window INTEGER,count INTEGER,PRIMARY KEY(scope,window));
    CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY,at INTEGER);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT,proposal TEXT,decision_id TEXT UNIQUE,fingerprint TEXT,reason TEXT,at INTEGER,decision TEXT);
   ''')
   if 'decision' not in {row[1] for row in db.execute('PRAGMA table_info(audit)')}:db.execute('ALTER TABLE audit ADD COLUMN decision TEXT')
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.database,timeout=5);db.row_factory=sqlite3.Row
  db.execute('PRAGMA busy_timeout=5000')
  try:
   with db: yield db
  finally: db.close()
 def _rate(self,db,scope,count,seconds):
  now=int(self.clock());window=now//seconds*seconds
  db.execute('DELETE FROM rates WHERE window<?',(now-172800,))
  db.execute('INSERT OR IGNORE INTO rates VALUES(?,?,0)',(scope,window))
  current=db.execute('SELECT count FROM rates WHERE scope=? AND window=?',(scope,window)).fetchone()[0]
  if current>=count: raise IntakeError(429,'rate_limit')
  db.execute('UPDATE rates SET count=count+1 WHERE scope=? AND window=?',(scope,window))
 def register(self,body):
  if not isinstance(body,dict) or set(body)!={'name'}: raise IntakeError(400,'name_required')
  name=text(body['name'],1,80);now=int(self.clock());token='ipvx_a2a_'+secrets.token_urlsafe(32);client='agent_'+secrets.token_hex(12)
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE');self._rate(db,'registration',30,3600)
   if db.execute('SELECT count(*) FROM clients').fetchone()[0]>=MAX_CLIENTS: raise IntakeError(503,'intake_capacity')
   db.execute('INSERT INTO clients(id,name,token_hash,created,expires) VALUES(?,?,?,?,?)',(client,name,digest(token),now,now+TOKEN_SECONDS))
  return {'clientId':client,'accessToken':token,'tokenType':'Bearer','expiresIn':TOKEN_SECONDS,'identity':'self-asserted agent profile; token proves control of this intake account only','scope':['project.read','proposal.submit','proposal.read_own'],'approval':'No membership, votes, GitHub access, model execution or infrastructure access is granted.'}
 def authenticate(self,header):
  if not isinstance(header,str) or not re.fullmatch(r'Bearer ipvx_a2a_[A-Za-z0-9_-]{40,60}',header): raise IntakeError(401,'bearer_token_required')
  with self.db() as db:
   row=db.execute('SELECT * FROM clients WHERE token_hash=?',(digest(header[7:]),)).fetchone()
   if not row or row['blocked'] or row['expires']<=self.clock(): raise IntakeError(401,'invalid_or_expired_token')
   db.execute('BEGIN IMMEDIATE');self._rate(db,'rpc:'+row['id'],40,60);self._rate(db,'rpc-global',200,60)
  return dict(row)
 def _proposal(self,row,owner=False):
  value={k:row[k] for k in ('id','kind','title','summary','rfc','status','reason','created','updated')}
  value['references']=json.loads(row['reference_urls']);value['acceptance']='received for owner review; receipt is not approval or execution'
  if owner:value['clientId']=row['client'];value['agentName']=row['agent_name']
  return value
 def submit(self,client,message_id,body):
  allowed={'action','kind','title','summary','references','rfc'}
  if not isinstance(body,dict) or set(body)-allowed or body.get('kind') not in KINDS: raise IntakeError(400,'invalid_proposal_fields')
  title=text(body.get('title'),3,160);summary=text(body.get('summary'),10,6000)
  refs=body.get('references',[]);rfc=body.get('rfc','')
  if not isinstance(refs,list) or len(refs)>5 or not isinstance(rfc,str) or rfc and not re.fullmatch('rfc-000[1-7]',rfc): raise IntakeError(400,'invalid_references_or_rfc')
  for ref in refs:
   text(ref,1,500);u=urlsplit(ref)
   if u.scheme!='https' or not u.hostname or u.username or u.password: raise IntakeError(400,'https_references_required')
  fingerprint=digest(canonical(body));now=int(self.clock());identifier='proposal_'+secrets.token_hex(12)
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   old=db.execute('SELECT * FROM proposals WHERE client=? AND message_id=?',(client,message_id)).fetchone()
   if old:
    if old['fingerprint']!=fingerprint: raise IntakeError(409,'message_id_reused')
    return self._proposal(old)
   self._rate(db,'proposal:'+client,10,86400);self._rate(db,'proposal-global',100,86400)
   if db.execute('SELECT count(*) FROM proposals').fetchone()[0]>=MAX_PROPOSALS: raise IntakeError(503,'intake_capacity')
   db.execute('INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,client,message_id,fingerprint,body['kind'],title,summary,canonical(refs),rfc,'pending_owner','',now,now))
   return self._proposal(db.execute('SELECT * FROM proposals WHERE id=?',(identifier,)).fetchone())
 def own_proposal(self,client,identifier):
  with self.db() as db:
   row=db.execute('SELECT * FROM proposals WHERE id=? AND client=?',(identifier,client)).fetchone()
   if not row: raise IntakeError(404,'proposal_not_found')
   return self._proposal(row)
 def cached(self,client,message_id,fingerprint):
  with self.db() as db:
   row=db.execute('SELECT * FROM receipts WHERE client=? AND message_id=?',(client,message_id)).fetchone()
   if not row:return None
   if row['fingerprint']!=fingerprint:raise IntakeError(409,'message_id_reused')
   return json.loads(row['result'])
 def save_receipt(self,client,message_id,fingerprint,result):
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT count(*) FROM receipts').fetchone()[0]>=MAX_RECEIPTS:raise IntakeError(503,'intake_capacity')
   db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?)',(client,message_id,fingerprint,canonical(result),int(self.clock())))
 def verify_admin(self,key,method,path,body,headers):
  stamp=headers.get('x-ipvx-time','');nonce=headers.get('x-ipvx-nonce','');signature=headers.get('x-ipvx-signature','')
  if not re.fullmatch(r'[0-9]{10,12}',stamp) or abs(self.clock()-int(stamp))>30 or not re.fullmatch(r'[0-9a-f]{32}',nonce) or not hmac.compare_digest(signature,admin_signature(key,method,path,body,stamp,nonce)):raise IntakeError(403,'owner_authorization_required')
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM nonces WHERE at<?',(int(self.clock())-60,))
   if db.execute('SELECT 1 FROM nonces WHERE nonce=?',(nonce,)).fetchone():raise IntakeError(403,'replayed_authorization')
   db.execute('INSERT INTO nonces VALUES(?,?)',(nonce,int(self.clock())))
 def owner_list(self,offset=0):
  with self.db() as db:
   rows=db.execute('SELECT p.*,c.name AS agent_name FROM proposals p JOIN clients c ON c.id=p.client ORDER BY created DESC,id DESC LIMIT 5 OFFSET ?',(offset,)).fetchall()
   counts={r[0]:r[1] for r in db.execute('SELECT status,count(*) FROM proposals GROUP BY status')}
   return {'proposals':[self._proposal(r,True) for r in rows],'counts':counts,'visibility':'owner-private','limit':5,'offset':offset,'nextOffset':offset+5 if offset+5<sum(counts.values()) else None}
 def decide(self,identifier,body):
  if not isinstance(body,dict) or set(body)!={'decision','reason','requestId','actor'} or body['decision'] not in ('approved_for_discussion','declined'):raise IntakeError(400,'invalid_decision')
  reason=text(body['reason'],3,1000);actor=text(body['actor'],1,100);request_id=text(body['requestId'],8,128);fingerprint=digest(identifier+canonical(body))
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT * FROM audit WHERE decision_id=?',(request_id,)).fetchone()
   if old:
    if old['fingerprint']!=fingerprint:raise IntakeError(409,'decision_id_reused')
    return {'id':identifier,'status':body['decision'],'reason':reason,'idempotent':True}
   if not db.execute('SELECT 1 FROM proposals WHERE id=?',(identifier,)).fetchone():raise IntakeError(404,'proposal_not_found')
   if db.execute('SELECT count(*) FROM audit').fetchone()[0]>=MAX_AUDIT:raise IntakeError(503,'audit_capacity')
   db.execute('UPDATE proposals SET status=?,reason=?,updated=? WHERE id=?',(body['decision'],reason,int(self.clock()),identifier))
   db.execute('INSERT INTO audit(actor,proposal,decision_id,fingerprint,reason,at,decision) VALUES(?,?,?,?,?,?,?)',(actor,identifier,request_id,fingerprint,reason,int(self.clock()),body['decision']))
  return {'id':identifier,'status':body['decision'],'reason':reason,'executionGranted':False,'publicationGranted':False}
