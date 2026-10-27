"""Offline signature verification. Requires PyNaCl; no network or private keys."""
import hashlib,json,sys
from pathlib import Path
from nacl.signing import VerifyKey

def canonical(value):
 def check(v):
  if v is None or type(v) in (str,int,bool):return
  if isinstance(v,list):
   for x in v:check(x)
   return
  if isinstance(v,dict) and all(isinstance(k,str) for k in v):
   for x in v.values():check(x)
   return
  raise ValueError('Unsupported canonical type')
 check(value)
 return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def verify(e,key,purpose):
 if set(e)!={'wire','purpose','payload','signature'} or e['wire']!='ipvx-agent-lab/1' or e['purpose']!=purpose:raise ValueError('Domain mismatch')
 body={k:e[k] for k in ('wire','purpose','payload')};VerifyKey(bytes.fromhex(key)).verify(canonical(body),bytes.fromhex(e['signature']));return e['payload']
def main(path):
 j=json.loads(Path(path).read_text());pins=j['public_verification_keys'];ids={p['id']:p['public_key'] for p in pins.values()}
 for p in pins.values():
  if p['id']!='ipvx:agent:'+hashlib.sha256(bytes.fromhex(p['public_key'])).hexdigest():raise ValueError('Identity/key mismatch')
 reply=j['signed_delivery_proof'];receipt=reply['receipt'];r=verify(receipt,ids[receipt['payload']['sender']],'direct-receipt');path=j['path']
 assert r['sender']==pins[path[-1]]['id'] and r['recipient']==pins[path[0]]['id'] and r['message_id']==j['message_id']
 assert len(reply['hops'])==len(path)-1
 traces=set()
 for i,envelope in enumerate(reply['hops']):
  node=pins[path[i]]['id'];h=verify(envelope,ids[node],'mesh-hop');traces.add(h['trace_id'])
  assert h['node']==node and h['next']==pins[path[i+1]]['id'] and h['message_id']==r['message_id']
  assert h['receipt_hash']==digest(receipt) and h['message_hash']==r['request_hash'] and h['ciphertext_sha256']==r['ciphertext_sha256']
  assert h['network']['transport']=='ethernet' and h['network']['ethertype']=='0x88b5'
 assert len(traces)==1
 print('PASS: identity keys, recipient receipt and',len(reply['hops']),'linked native hops. Historical signatures verified; no current reachability, operator independence or public plaintext-decryption proof asserted.')
if __name__=='__main__':main(sys.argv[1])
