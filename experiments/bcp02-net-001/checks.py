"""Static package checks only. Never builds/runs a node, EVM or network."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from readiness import evaluate
from preserve import check


def report():
    suite=unittest.defaultTestLoader.discover(str(HERE/'tests'))
    def names(group):
        for item in group:
            if isinstance(item,unittest.TestSuite):yield from names(item)
            else:yield item.id()
    ids=sorted(names(suite));result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    state=evaluate()
    if not state['plan_valid'] or state['ready_to_launch']:raise SystemExit('invalid planning package')
    return {'schema_version':1,'scope':'STATIC PREPARATION ONLY; no network experiment or stand provisioning',
        'tests_passed':result.testsRun,'test_ids':ids,'declared_cases':13,'preservation':check(),'readiness':state,
        'files':{str(p.relative_to(HERE)):sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.name not in ('static-checks.json','bundle-manifest.json')},
        'network_created':False,'runner_executed':False,'transactions':False,'deployment':False,'production_actions':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.write_text(json.dumps(report(),indent=2)+'\n')
