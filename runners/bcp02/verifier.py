"""Offline evidence reconciliation. Missing coverage is INCONCLUSIVE, never 0/0 PASS."""
from collections import defaultdict
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import stat

from bcp.core import verify
from bcp.wire import Reject, decode_ethernet, signing_inputs, digest, uint
from .common import CASES, NODES, Blocked, read_json, need, sha
from .fixture import FixtureChain
from .dataset import descriptor, fresh, lifetime
from .admission import verify_permit
from cryptography.exceptions import InvalidSignature
from .pcap import frames
from .scenarios import SCRIPTS, observed


def events(path):
    result=[]
    with open(path) as f:
        while True:
            line=f.readline(4097)
            if not line:break
            need(len(line)<=4096,'oversized event')
            result.append(json.loads(line))
    return result


def tables(path):
    with closing(sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro&immutable=1',uri=True)) as db:
        need(db.execute('PRAGMA integrity_check').fetchone()==('ok',),'journal integrity failure')
        return {name:db.execute('SELECT * FROM '+name).fetchall() for name in ('requests','deliveries','receipts','worker')}


def evaluate(directory):
    directory=Path(directory).resolve()
    result=dict(state_mode='fixture-state-ethernet',outcome='NOT_RUN',case_results={},
                real_chain_finality=False,independent_operators=False,physical_ethernet=False)
    try:
        manifest=read_json(directory/'run-manifest.json')
        if manifest['network_execution'] is not True:return result
        need(manifest['state_mode']=='fixture-state-ethernet','wrong state marker')
        total=0
        for p in directory.rglob('*'):
            meta=p.lstat()
            need(not p.is_symlink() and (stat.S_ISDIR(meta.st_mode) or stat.S_ISREG(meta.st_mode)),'unsafe evidence file type')
            if stat.S_ISREG(meta.st_mode):total+=meta.st_size
        need(total<=1024**3,'evidence exceeds artifact budget')
        for name in ('payload-manifest.json','worker-log.json','injection-manifest.json','fault-barriers.json',
                     'clock-health.json','process-policy.json','source-binary-dataset-hashes.json','state-bank.json'):
            read_json(directory/name)
        data=read_json(directory/'dataset/dataset.json');chain=FixtureChain(data)
        need(sha((directory/'dataset/dataset.json').read_bytes())==manifest['dataset_sha256'],'dataset mismatch')
        admission=read_json(directory/'dataset-admission.json')
        binding,bundle=descriptor((directory/'dataset/bundle.json').read_bytes())
        need(binding==admission['dataset'] and binding['run_id']==manifest['run_id']
             and binding['dataset_sha256']==manifest['dataset_sha256'], 'admission dataset mismatch')
        need(lifetime(data)==(binding['created_at'],binding['expires_at']), 'admission freshness metadata mismatch')
        permit=verify_permit(admission['envelope'],admission['owner_public_key'],
                             scope=manifest['scope_sha256'],now=admission['admitted_at'])
        need(permit['dataset']==binding and permit['run_id']==manifest['run_id']
             and permit['_document_sha256']==admission['permit_document_sha256'], 'permit receipt mismatch')
        for name,pin in bundle['files'].items():
            # Secret key contents are not needed by the offline verifier.
            if name.endswith('/key.json'):continue
            need(sha((directory/'dataset'/name).read_bytes())==pin, 'admission bundle member mismatch')
        for name in ('source-binary-dataset-hashes.json','state-bank.json'):
            index=read_json(directory/name)
            need(index['dataset_admission']==binding,'dataset index admission mismatch')
        captured=defaultdict(set);raw_by_hash={}

        for link in ('L1','L2'):
            folder=directory/'captures'/link
            count=0
            with open(folder/'capture.pcap','rb') as f:
                for timestamp,raw in frames(f):
                    count+=1
                    if raw[12:14]!=b'\x88\xb5':
                        result['outcome']='FAIL_ISOLATION';result['reason']='unexpected EtherType';return result
                    fresh(binding,timestamp)
                    need(permit['not_before']<=timestamp<permit['not_after'],'capture outside permit/dataset lifetime')
                    h=sha(raw);captured[h].add(link);raw_by_hash[h]=raw
            stats=read_json(folder/'capture-statistics.json')
            need(stats['filter'] is None and stats['snaplen']==65535 and stats['error'] is None
                 and stats['started_before_link_up'] is True and len(stats['statistics'])==1
                 and all(s['drops']==0 and s['unfiltered'] is True and s['packets']==count for s in stats['statistics']), 'capture coverage/drops')
        timeline=read_json(directory/'controller.json')
        need(set(timeline['capture_ready'])=={'L1','L2'} and max(timeline['capture_ready'].values())<timeline['link_up'],
             'capture setup window missing')
        need(timeline['resources_within_limits'] and timeline['clock_healthy'],'resource/clock evidence missing')
        need(timeline['process_isolation_verified'] is True,'process socket/capability audit missing')
        for inventory in (read_json(directory/'inventory-down.json'),read_json(directory/'inventory-up.json')):
            need(set(inventory)==set(NODES),'inventory missing')
            for name,node in inventory.items():
                need(not node['routes'] and not any(a.get('addr_info') for a in node['addresses']), 'IP inventory')
                need({p['ifname'].split('@')[0] for p in node['links']}=={'lo',*NODES[name][1]},'external interface')
        all_events=[];cases={};dbs={}
        for label in SCRIPTS:
            case=label.split('-')[0];variant=label.split('-',1)[1] if '-' in label else ''
            folder=directory/'cases'/label
            closed=read_json(folder/'closed.json')
            for file,pin in closed['files'].items():
                need(not Path(file).is_absolute() and '..' not in Path(file).parts,'unsafe closed evidence path')
                p=folder/file;need(p.resolve()==p and sha(p.read_bytes())==pin,'closed evidence mismatch')
            ev=[];db={}
            for node in NODES:
                ev+=events(folder/node/'events.jsonl');db[node]=tables(folder/node/'core.sqlite')
            for e in ev:
                fresh(binding,e['utc'])
                need(permit['not_before']<=e['utc']<permit['not_after'],'event outside permit/dataset lifetime')
            need(all(e['run_id']==manifest['run_id'] and e['case_id']==case for e in ev),'event scope mismatch')
            need(any(e['decision']=='READY' for e in ev),'missing process evidence')
            for e in ev:
                if e.get('frame_sha256'):
                    need(e['frame_sha256'] in captured,'event without raw capture')
                if e['decision']=='DELIVER' and e.get('disposition')=='NEW' or e['decision']=='COMPLETED':
                    h=e['immutable_sha256']
                    links=set()
                    for rh,raw in raw_by_hash.items():
                        try:frame=decode_ethernet(raw,chain.binding.profile)[2]
                        except Reject:continue
                        if 'immutable' in frame.fields and sha(frame.fields['immutable'])==h:links|=captured[rh]
                    need(links=={'L1','L2'},'delivery/receipt missing both-link correlation')
                if e['decision']=='FORWARD':need(e['node']=='R','wrong relay node')
            originals=len(db['A']['requests']);delivered=len(db['B']['deliveries']);workers=len(db['B']['worker'])
            requests={row[2]:row for row in db['A']['requests']}
            sql_ok=all(row[0]==uint(1,32) and row[1]==uint(2,32) and digest(row[4])==row[3] for row in requests.values())
            sql_ok &= all(row[0]==uint(1,32) and row[1] in requests and row[2]==requests[row[1]][3] for row in db['B']['deliveries'])
            sql_ok &= all(row[0]==uint(1,32) and row[1] in requests and (row[2]!=2 or row[3]==digest(digest(requests[row[1]][4]))) for row in db['A']['receipts'])
            sql_ok &= all(row[0]==uint(1,32) and row[1] in requests and row[2]==requests[row[1]][3]
                          and (row[3]!='DONE' or row[4]==digest(requests[row[1]][4])) for row in db['B']['worker'])
            new={e['message_id'] for e in ev if e['node']=='B' and e['decision']=='DELIVER' and e.get('disposition')=='NEW'}
            need(delivered==len(new),'delivery SQL/event mismatch')
            need(workers==len({e['message_id'] for e in ev if e['node']=='B' and e['decision']=='WORKER_DONE'}),'worker SQL/event mismatch')
            need(not db['R']['deliveries'] and not db['R']['worker'],'relay executed/decrypted application')
            expected=10 if case in ('P01','N02') else 0 if case in ('N01','N08') else 1
            ok=sql_ok and originals==expected and observed(ev,label)
            if case in ('P01','P02','N03','N04','N05','N09','N10'):
                ok &= delivered==workers==(10 if case=='P01' else 1)
                ok &= all(row[3]=='DONE' for row in db['B']['worker'])
                ok &= all(row[2]==2 for row in db['A']['receipts'])
            if case in ('N02','N06','N07','N08'):ok &= delivered==0 if variant!='reverse' else delivered==1
            if case=='P02':ok &= any(len(raw)==1514 and decode_ethernet(raw,chain.binding.profile)[2].kind==5 for raw in raw_by_hash.values())
            if case=='N11':ok &= workers==0 and delivered==1 and not db['A']['receipts']
            if case=='N02':
                barrier=closed['relay_stopped_monotonic']
                issued=[e for e in ev if e['node']=='A' and e['decision']=='ISSUED']
                unknown=[e for e in ev if e['node']=='A' and e['decision']=='UNKNOWN']
                ok &= len(issued)==len(unknown)==10 and all(e['monotonic']>barrier for e in issued)
                ok &= all(1<=e['attempts']<=3 for e in unknown)
                byid={e['message_id_override']:e for e in issued}
                ok &= all(0<=e['monotonic']-byid[e['message_id_override']]['monotonic']<=20 for e in unknown)
            result['case_results'][label]=dict(pass_criteria_met=bool(ok),originals=originals,deliveries=delivered,worker_rows=workers)
            all_events+=ev;cases[label]=ev;dbs[label]=db
        # Every captured signature is checked except the single explicit corrupt
        # hop injection, which must have its intact same-sequence twin captured.
        injected={e['frame_sha256'] for e in all_events if e.get('injection')=='hop-signature-final-byte'}
        need(all(e['node']=='A' and e['case_id']=='N03' for e in all_events if e.get('injection')=='hop-signature-final-byte'),'unexpected corruption declaration')
        data_attempts=[e for e in all_events if e['node']=='A' and e['decision']=='TX' and e['kind']==5]
        need(len(data_attempts)<=120 and sum(c['originals'] for c in result['case_results'].values())<=40,'run traffic bound')
        public={int(n):bytes.fromhex(k['signing']['public_key_hex']) for n,k in data['bank']['keys'].items()}
        for h,raw in raw_by_hash.items():
            try:
                frame=decode_ethernet(raw,chain.binding.profile)[2];f=frame.fields;s=signing_inputs(frame)
                if frame.kind==1:verify(public[f['node']],f['signature'],s['hello'])
                elif frame.kind in (2,3):
                    label='challenge' if frame.kind==2 else 'confirm';signer=f['responder' if frame.kind==2 else 'initiator']
                    verify(public[signer],f['signature'],s[label])
                elif frame.kind==4:
                    verify(public[f['path'][0]],f['signature'],s['route_link'])
                    for n,sig,part in zip(f['path'],f['node_signatures'],s['route_nodes']):verify(public[n],sig,part)
                else:
                    verify(public[f['sender']],f['signature'],s['hop']);verify(public[f['source']],f['source_signature'],s['source'])
                    need(sha(f['immutable'])==f['immutable_hash'].hex(),'immutable hash mismatch')
            except (Reject,KeyError):
                if h not in injected:
                    result['outcome']='FAIL_PROTOCOL';result['reason']='unexpected invalid signature/frame';return result
                twin=raw[:-1]+bytes([raw[-1]^1])
                need(sha(twin) in captured,'corrupt injection lacks intact twin')
        result['outcome']='PASS' if all(c['pass_criteria_met'] for c in result['case_results'].values()) else 'FAIL_PROTOCOL'
        result['interpretation']='Transport with synthetic fixture-state only; no chain finality, physical link or independent-operator conclusion.'
    except (Blocked,OSError,ValueError,KeyError,TypeError,InvalidSignature,sqlite3.Error) as e:
        result['outcome']='INCONCLUSIVE';result['reason']=str(e)
    return result
