"""Deterministic offline evidence; fixture expectations are never core inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from bcp import build
from bcp.wire import Reject, decode, ethernet
from fixtures import BY_ID, FIXTURE, PROFILE, VECTORS, ROOT, core_for, receive, signing, NOW, MONO


def report():
    cases=[]
    with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')), \
         patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')), \
         patch.object(socket,'getaddrinfo',side_effect=AssertionError('network forbidden')):
        for vector in VECTORS:
            core=core_for(vector)
            try:
                try:
                    decision=receive(core,vector);actual='ACCEPT';action=decision.action
                except Reject as error:
                    actual=error.code;action='LOCAL_REJECT_NO_APPLICATION_EXECUTION'
                expected='AUTH_FAILED' if vector['id']=='N29-REQUEST-HASH' else vector['expected']
                assert actual==expected,(vector['id'],actual,expected)
                cases.append({'id':vector['id'],'frozen_expected':vector['expected'],'actual':actual,
                              'action':action,'matches_frozen_expected':actual==vector['expected']})
            finally:core.journal.close()
        original=decode(bytes.fromhex(BY_ID['N29-REQUEST-HASH']['bcp_hex']),PROFILE)
        corrected=build.rewrap(original,bytes.fromhex(FIXTURE['sessions'][1]['session_id_hex']),1,1,signing(3))
        c=core_for(BY_ID['N29-REQUEST-HASH'])
        try:
            try:
                c.receive(ethernet(c.local_mac,bytes.fromhex('020000000003'),corrected.encode()),now=NOW,monotonic=MONO,clock_trusted=True)
                raise AssertionError('corrected negative vector accepted')
            except Reject as e:assert e.code=='INVALID_PAYLOAD'
        finally:c.journal.close()
    files=sorted([*ROOT.glob('bcp/*.py'),*ROOT.glob('tests/bcp/*.py'),ROOT/'bcp/requirements.lock'])
    return {
        'schema_version':1,'recorded_by':'codex-assistant','basis_revision':'51294fd987658236b42db6211645f0f707dbe243',
        'scope':'offline core against synthetic trusted-state inputs; no network experiment or independent implementation',
        'frozen_cases':50,'positive_accepted':14,'negative_rejected':36,'matches_frozen_expected':49,
        'fixture_errata':{'id':'N29-REQUEST-HASH','frozen_file_unchanged':True,
            'original_sha256':BY_ID['N29-REQUEST-HASH']['bcp_sha256'],
            'reason':'Hop sender 3 to receiver 2 is bound to session 1-3, not session 3-2. Authentication must fail before payload validation.',
            'corrected_actual':'INVALID_PAYLOAD','corrected_bcp_hex':corrected.encode().hex(),
            'corrected_sha256':hashlib.sha256(corrected.encode()).hexdigest(),'immutable_bytes_preserved':True},
        'cases':cases,
        'source_files':[{'path':str(f.relative_to(ROOT)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in files],
        'network_used':False,'chain_finality_verified':False,'independent_interoperability_established':False,
        'application_executed':False,'deployed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=report();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('50 frozen cases: 14 accept, 36 reject; 49 match original expectations; N29 documented early AUTH_FAILED; corrected N29 INVALID_PAYLOAD.')
