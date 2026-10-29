"""Evaluate declared launch conditions. This does not authenticate participant claims."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

def scope_digest(plan):
 p=plan['partner'];w=plan['proposed_window']
 frozen={k:plan[k]for k in ['protocol_id','version','server_revision','source_sha256','control_environment','limits','retention','cases','protocol_document_sha256','harness_sha256']}
 frozen['partner']={k:p.get(k)for k in ['account','role','environment']}
 frozen['window']={k:w[k]for k in ['timezone','start','end','start_utc','end_utc','results_due']}
 # Acceptance bookkeeping is outside the immutable experimental conditions.
 frozen['retention']={k:v for k,v in frozen['retention'].items()if k!='agreed'}
 return hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def evaluate(plan,now=None):
 now=now or datetime.now(timezone.utc);p=plan['partner'];missing=[]
 if p.get('role')!='independent-client-runner':missing.append('external_client_runner_role_not_confirmed')
 env=p.get('environment')
 if not isinstance(env,dict)or not all(env.get(k)for k in ['language','runtime_version','os']):missing.append('partner_environment_missing')
 if not p.get('resource_authority_confirmed'):missing.append('partner_resource_authority_not_confirmed')
 if not p.get('agreement_comment_id'):missing.append('explicit_partner_agreement_evidence_missing')
 for field in ['scope_confirmed','retention_confirmed','window_confirmed']:
  if not p.get(field):missing.append(field)
 ack=plan.get('protocol_hash_acknowledged',{})
 digest=scope_digest(plan)
 if not all(isinstance(ack.get(role),dict)and ack[role].get('scope_sha256')==digest and ack[role].get('evidence')for role in ['owner','partner']):missing.append('frozen_protocol_hash_not_acknowledged_by_both')
 if not plan.get('local_preflight_passed'):missing.append('local_preflight_not_passed')
 window=plan['proposed_window']
 if not window.get('accepted'):missing.append('window_not_accepted')
 if datetime.fromisoformat(window['end'].replace('Z','+00:00'))<=now:missing.append('window_expired')
 return {'scope_sha256':digest,'ready_to_request_launch':not missing,'ready_to_launch':not missing and plan.get('owner_launch_decision')is True,'missing':missing+([]if plan.get('owner_launch_decision')is True else['owner_launch_decision_pending']),'interpretation':'Declared evidence gates only; no identity authentication, resources or execution are granted.'}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path);args=parser.parse_args();print(json.dumps(evaluate(json.loads(args.plan.read_text())),indent=2))
