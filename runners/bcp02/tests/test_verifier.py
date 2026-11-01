"""Fabricated unit evidence validates the verifier, never a recorded network run."""
import io
import json
from pathlib import Path
import shutil
import struct
import sqlite3
from contextlib import closing
import tempfile
import unittest

from runners.bcp02.common import NODES, private_json, sha
from runners.bcp02.fixture import export
from runners.bcp02.pcap import Writer
from runners.bcp02.scenarios import SCRIPTS
from runners.bcp02.verifier import evaluate
from runners.bcp02.tests.memory import Memory,T0


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)/'unit';cls.root.mkdir()
        export(cls.root/'dataset','offline-unit-tests',T0+100)
        data=json.loads((cls.root/'dataset/dataset.json').read_text());data['_directory']=str(cls.root/'dataset')
        private_json(cls.root/'run-manifest.json',dict(network_execution=True,state_mode='fixture-state-ethernet',
            run_id='offline-unit-tests',dataset_sha256=sha((cls.root/'dataset/dataset.json').read_bytes()),
            warning='FABRICATED UNIT EVIDENCE; NOT A NETWORK MEASUREMENT'))
        (cls.root/'cases').mkdir();(cls.root/'captures').mkdir();wire=[]
        for label,script in SCRIPTS.items():
            case=label.split('-')[0];variant=label.split('-',1)[1] if '-' in label else ''
            h=Memory(data,case,variant)
            try:
                for node in h.nodes.values():node.events.emit('READY',unit_test=True)
                h.start();h.script(script);wire+=h.wire
                for node in h.nodes.values():node.close()
                h.nodes={}
                folder=cls.root/'cases'/label;shutil.copytree(h.directory,folder)
                private_json(folder/'closed.json',dict(relay_stopped_monotonic=100.12 if case=='N02' else None,
                    files={str(p.relative_to(folder)):sha(p.read_bytes()) for p in folder.rglob('*') if p.is_file()}))
            finally:h.close()
        for link,ports in [('L1',{'a0','r0'}),('L2',{'r1','b0'})]:
            folder=cls.root/'captures'/link;folder.mkdir()
            with open(folder/'capture.pcap','wb') as f:
                w=Writer(f)
                for port,raw in wire:
                    if port in ports:w.append(raw,T0+100)
            private_json(folder/'capture-statistics.json',dict(filter=None,snaplen=65535,error=None,
                started_before_link_up=True,statistics=[dict(drops=0,unfiltered=True,packets=sum(port in ports for port,raw in wire))]))
        private_json(cls.root/'controller.json',dict(capture_ready={'L1':1,'L2':1.1},link_up=2,
            resources_within_limits=True,clock_healthy=True,process_isolation_verified=True))
        inventory={n:dict(routes=[],addresses=[],links=[{'ifname':p} for p in ('lo',*ports)]) for n,(_,ports) in NODES.items()}
        for name in ('inventory-down.json','inventory-up.json'):private_json(cls.root/name,inventory)
        for name in ('payload-manifest.json','worker-log.json','injection-manifest.json','fault-barriers.json',
                     'clock-health.json','process-policy.json','source-binary-dataset-hashes.json','state-bank.json'):
            private_json(cls.root/name,{'unit_test_fixture':True})

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def copy(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        folder=Path(temp.name)/'copy';shutil.copytree(self.root,folder);return folder

    def test_complete_synthetic_evidence_reconciles(self):
        result=evaluate(self.root)
        self.assertEqual(result['outcome'],'PASS',result)
        self.assertEqual(len(result['case_results']),14)
        self.assertFalse(result['real_chain_finality'])

    def test_capture_drop_is_inconclusive(self):
        folder=self.copy();p=folder/'captures/L1/capture-statistics.json'
        d=json.loads(p.read_text());d['statistics'][0]['drops']=1;p.write_text(json.dumps(d))
        self.assertEqual(evaluate(folder)['outcome'],'INCONCLUSIVE')

    def test_missing_capture_is_inconclusive(self):
        folder=self.copy();(folder/'captures/L2/capture.pcap').unlink()
        self.assertEqual(evaluate(folder)['outcome'],'INCONCLUSIVE')

    def test_truncated_capture_is_inconclusive(self):
        folder=self.copy();p=folder/'captures/L1/capture.pcap';p.write_bytes(p.read_bytes()[:-1])
        self.assertEqual(evaluate(folder)['outcome'],'INCONCLUSIVE')

    def test_unexpected_ethertype_fails_isolation(self):
        folder=self.copy();p=folder/'captures/L1/capture.pcap'
        raw=bytes(12)+b'\x08\x06'+bytes(30)
        with p.open('ab') as f:f.write(struct.pack('<IIII',T0,0,len(raw),len(raw))+raw)
        self.assertEqual(evaluate(folder)['outcome'],'FAIL_ISOLATION')

    def test_forged_worker_result_fails_despite_success_events(self):
        folder=self.copy();p=folder/'cases/N10/B/core.sqlite'
        with closing(sqlite3.connect(p)) as db:
            db.execute('UPDATE worker SET result=?',(bytes(32),));db.commit()
        closed=folder/'cases/N10/closed.json';d=json.loads(closed.read_text());d['files']['B/core.sqlite']=sha(p.read_bytes());closed.write_text(json.dumps(d))
        self.assertEqual(evaluate(folder)['outcome'],'FAIL_PROTOCOL')

    def test_unread_capture_packets_are_inconclusive(self):
        folder=self.copy();p=folder/'captures/L1/capture-statistics.json'
        d=json.loads(p.read_text());d['statistics'][0]['packets']+=1;p.write_text(json.dumps(d))
        self.assertEqual(evaluate(folder)['outcome'],'INCONCLUSIVE')


if __name__=='__main__':unittest.main()
