"""Derive the expected registry state from the published REG-001 run 6 records.

Expected = snapshot S4 + the 20 setKeys writes of the R4 latency series, which ran
after S4 (contracts/bcp02/reg001/runner.mjs). Nothing here reads a chain; run it from
anywhere and redirect the output to expected.json.
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'experiments/bcp02-reg-001/runs'
WRITES=20
SERIES_KEY_BASE=1000      # runner.mjs: setKeys(A, key(1000+2i), key(1001+2i), endpoint)
EFFECTIVE,UNUSABLE='1','2'


def key(n):
    return '0x'+format(n,'064x')


def derive():
    steps={}
    for line in (RUN/'run-6.jsonl').read_text().splitlines():
        row=json.loads(line);steps[row['step']]=row
    s4=steps['snapshot-s4']['snapshot']
    series=steps['latency-series']['records']
    if len(series)!=WRITES or not all(r['included'] for r in series):raise ValueError('unexpected R4 series')
    if min(r['block'] for r in series)<=s4['block']['number']:raise ValueError('the series must follow S4')
    sent={t['tx']:t for t in json.loads((RUN/'run-6-transactions.json').read_text())['transactions']}
    for record in series:
        t=sent[record['tx']]
        if (t['contract'],t['fn'],t['status'])!=('NodeRegistry','setKeys',1):raise ValueError('unexpected R4 write')
    nodes=dict(zip(('1','2','3','99'),([row[0].lower(),*row[1:]] for row in s4['nfts'])))
    edges=dict(zip(('A->R','R->B'),(list(row) for row in s4['edges'])))
    connections={'A->B':list(s4['connections'][0])}
    # Every write raises A's epoch, so the A->R agreement no longer matches it
    # (BilateralPolicy._effective), exactly as R's rotation did in S2.
    a=nodes['1'];last=SERIES_KEY_BASE+2*(WRITES-1)
    a[1:4]=[str(int(a[1])+WRITES),key(last),key(last+1)]
    if edges['A->R'][-1]!=EFFECTIVE:raise ValueError('S4 changed')
    edges['A->R'][-1]=UNUSABLE
    if edges['R->B'][-1]!=UNUSABLE or connections['A->B'][-1]!=UNUSABLE:raise ValueError('S4 changed')
    return {'schema_version':1,'protocol_id':'IPVX-BCP02-REG-001-LC',
            'derived_from':{'snapshot':'S4','s4_block':s4['block']['number'],'s4_block_hash':s4['block']['hash'],
                            'later_writes':WRITES,'last_write_block':max(r['block'] for r in series)},
            'changed_from_s4':['nodes.1','edges.A->R'],
            'nodes':nodes,'edges':edges,'connections':connections,'allowed_edges':{'A->B':[]}}


if __name__=='__main__':
    print(json.dumps(derive(),indent=2))
