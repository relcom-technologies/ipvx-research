"""Deterministic offline unit-check receipt, explicitly not network evidence."""
import argparse
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import socket
import subprocess

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def check():
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).with_name('tests')))
    def ids(suite):
        for item in suite:
            if isinstance(item,unittest.TestSuite):yield from ids(item)
            else:yield item.id()
    names=sorted(ids(suite));log=io.StringIO()
    original_popen=subprocess.Popen
    def evm_only(argv,*args,**kwargs):
        if not (isinstance(argv,list) and len(argv)==6 and argv[1]=='--import'
                and Path(argv[2])==ROOT/'contracts/bcp02/test/offline.mjs'
                and Path(argv[3])==ROOT/'runners/bcp02/generate_bank.mjs'):
            raise AssertionError('Only the offline EVM helper may run as a test subprocess')
        return original_popen(argv,*args,**kwargs)
    deny=AssertionError('Actual sockets/DNS are forbidden in runner offline checks')
    with patch.object(socket,'socket',side_effect=deny),patch.object(socket,'create_connection',side_effect=deny),\
         patch.object(socket,'getaddrinfo',side_effect=deny),patch.object(subprocess,'Popen',side_effect=evm_only):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    report=dict(schema_version=1,scope='Offline unit tests with memory ports, synthetic clocks and fabricated PCAP/SQL evidence',
        tests=result.testsRun,success=result.wasSuccessful(),test_names=names,
        failures=len(result.failures),errors=len(result.errors),protocol_cases=13,case_variants=14,
        network_execution=False,namespace_creation=False,packet_sockets_opened=0,chain_transactions=0,
        deployed=False,production_actions=False,ready_to_launch=False,
        interpretation='Passing tests validate code paths and verifier decisions; they do not establish Linux isolation or Ethernet delivery.')
    if not result.wasSuccessful():sys.stderr.write(log.getvalue())
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    report=check();encoded=json.dumps(report,indent=2)+'\n'
    if args.output:args.output.write_text(encoded)
    else:print(encoded,end='')
    raise SystemExit(0 if report['success'] else 1)
