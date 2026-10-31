"""Deterministic test/source receipt. No live chain or networking capability."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def report():
    suite=unittest.defaultTestLoader.discover(str(ROOT/'adapters/bcp02/tests'))
    def names(group):
        for item in group:
            if isinstance(item,unittest.TestSuite):yield from names(item)
            else:yield item.id()
    tests=sorted(names(suite))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
    paths=sorted(p for p in (ROOT/'adapters').rglob('*') if p.is_file()
                 and p.suffix in ('.py','.mjs','.lock') and '__pycache__' not in p.parts)
    paths.append(ROOT/'adapters/bcp02/tests/contract-reads.json')
    return {'schema_version':1,'base':'9ac92e80152e588abcee6b97b18796d038cd0154',
      'scope':'Offline authenticated-transport fixtures; actual in-memory EVM contract read words; synthetic EL/CL headers',
      'tests_passed':result.testsRun,'test_ids':tests,
      'files':[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
      'live_chain':False,'transactions':False,'network_experiments':False,'deployment':False,'production_actions':False,
      'not_proved':['Ethereum consensus/finality','BLS or full beacon-body SSZ or storage proofs',
                    'live client interoperability','operator or endpoint ownership','independent audit','packet delivery']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.write_text(json.dumps(report(),indent=2)+'\n')
