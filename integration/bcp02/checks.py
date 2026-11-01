"""Deterministic logical outcomes; HPKE ciphertext randomness is not frozen."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from integration.bcp02.offline_cycle import scenario


def report():
    suite=unittest.defaultTestLoader.discover(str(ROOT/'integration/bcp02/tests'))
    def names(group):
        for item in group:
            if isinstance(item,unittest.TestSuite):yield from names(item)
            else:yield item.id()
    ids=sorted(names(suite));result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    files=sorted(p for p in (ROOT/'integration').rglob('*') if p.is_file() and p.suffix in ('.py','.mjs','.md')
                 and '__pycache__' not in p.parts)
    files.append(ROOT/'integration/bcp02/tests/contract-reads.json')
    return {'schema_version':1,'base':'8fb04e89dfbbe7a1b6f05f1fdb465bf4193c1179','tests_passed':result.testsRun,
        'test_ids':ids,'cycle':scenario(),
        'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha256(p.read_bytes()).hexdigest()} for p in files],
        'ciphertext_bytes':'Fresh HPKE randomness; logical outcomes and within-run immutable equality reproduced',
        'live_chain':False,'transactions':False,'network_experiments':False,'deployment':False,'production_actions':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();args.output.write_text(json.dumps(report(),indent=2)+'\n')
