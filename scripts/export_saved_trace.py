"""Explicit public allow-list; never exports contact roster or management endpoints."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
j=json.loads((root/'../ipvx-agent-lab/reports/llm/round1-native.json').read_text())
d=next(x for x in j['nodes']['A']['deliveries.jsonl'] if x['phase']=='review' and x['case']=='delivery')
a=next(x for x in j['nodes']['A']['inferences.jsonl'] if x['phase']=='draft' and x['case']=='delivery')
b=next(x for x in j['nodes']['B']['inferences.jsonl'] if x['phase']=='review' and x['case']=='delivery')
pins={name:{'id':record['payload']['id'],'public_key':record['payload']['public_key']} for name,record in j['roster'].items()}
trace={'kind':'saved-native-llm-delivery','run':j['run'],'revision':j['revision'],'message_id':d['message_id'],'case':d['case'],'path':d['path'],'elapsed_ms':d['elapsed_ms'],'saved_plaintext_task':{'action':'collaborate','phase':'review','case':'delivery','draft':a['parsed']},'receiver_model_output':b['parsed'],'public_verification_keys':pins,'signed_delivery_proof':d['proof'],'binding_limit':'Signatures authenticate the hop chain and ciphertext receipt. Plaintext model/task text is associated by the saved worker journal; no public proof of ciphertext decryption is supplied. This is operator-collected evidence, not independent attestation.'}
s=json.dumps(trace,ensure_ascii=False,indent=2)
assert not re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',s)
keys=set()
def walk(x):
 if isinstance(x,dict):
  keys.update(x)
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(trace)
assert not keys & {'private_key','management_ip','admin_token','host','hostname','endpoint','encryption_key','public_contacts','roster'}
(root/'data/native-llm-trace.json').write_text(s+'\n')
print('Sanitized trace exported: public verification keys only, no contact roster/IP/management metadata.')
