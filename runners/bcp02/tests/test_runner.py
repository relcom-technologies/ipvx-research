import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch, Mock

from bcp.wire import Reject, decode_ethernet, digest
from runners.bcp02.common import Blocked, control, NODES, read_json
from runners.bcp02.admission import authorize, claim_once
from runners.bcp02.fixture import export, FixtureChain
from runners.bcp02.scenarios import SCRIPTS, observed
from runners.bcp02.transport import PacketPort
from runners.bcp02.pcap import Writer, frames
from runners.bcp02.worker import Scheduler
from runners.bcp02.verifier import evaluate
from runners.bcp02.tests.memory import Memory, T0


class RunnerCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        dest=Path(cls.folder.name)/'data'
        export(dest,'offline-unit-tests',T0+100)
        cls.dataset=read_json(dest/'dataset.json');cls.dataset['_directory']=str(dest)

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def scenario(self,label):
        case=label.split('-')[0];variant=label.split('-',1)[1] if '-' in label else ''
        h=Memory(self.dataset,case,variant)
        try:
            with patch.object(socket,'socket',side_effect=AssertionError('network forbidden in unit tests')),\
                 patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')),\
                 patch.object(socket,'getaddrinfo',side_effect=AssertionError('DNS forbidden')):
                h.start();h.script(SCRIPTS[label]);self.assertTrue(observed(h.events,label))
                if case in ('P01','P02','N03','N04','N05','N09','N10'):
                    expected=10 if case=='P01' else 1
                    b=h.nodes['B'].journal.db
                    self.assertEqual(b.execute('SELECT count(*) FROM deliveries').fetchone()[0],expected)
                    self.assertEqual(b.execute('SELECT count(*) FROM worker').fetchone()[0],expected)
                if case=='N01':
                    self.assertEqual(h.nodes['A'].journal.db.execute('SELECT count(*) FROM requests').fetchone()[0],0)
                if case=='N02':
                    self.assertEqual(h.nodes['A'].journal.db.execute('SELECT count(*) FROM requests').fetchone()[0],10)
                    self.assertFalse(any(e['node']=='B' and e.get('disposition')=='NEW' for e in h.events))
                if case=='P02':self.assertTrue(any(len(raw)==1514 for _,raw in h.wire))
                if case=='N11':self.assertEqual(h.nodes['B'].journal.db.execute('SELECT count(*) FROM worker').fetchone()[0],0)
                if case=='N10':
                    rows=h.nodes['A'].journal.db.execute('SELECT phase,result FROM receipts').fetchall()
                    self.assertEqual(rows[0][0],2)
                if 'R' in h.nodes:self.assertEqual(h.nodes['R'].journal.db.execute('SELECT count(*) FROM worker').fetchone()[0],0)
        finally:h.close()

    def test_fault_banks_have_distinct_execution_and_cl_hashes(self):
        d=self.dataset;branches=list(d['branches'].values())
        self.assertEqual(len({b['points'][2] for b in branches}),3)
        self.assertEqual(len({b['roots'][2] for b in branches}),3)
        self.assertTrue(all(b['points'][:2]==d['fresh']['points'][:2] for b in branches))
        self.assertTrue(all(b['roots'][:2]==d['fresh']['roots'][:2] for b in branches))

    def test_relay_rejects_other_port_session(self):
        h=Memory(self.dataset,'P02')
        try:
            h.start();frame,plain=h.nodes['A'].prepare()
            from bcp.wire import ethernet
            from runners.bcp02.common import MACS
            raw=ethernet(bytes.fromhex(MACS['r0'].replace(':','')),bytes.fromhex(MACS['a0'].replace(':','')),frame.encode())
            h.nodes['R'].handle('r1',raw)
            self.assertEqual(h.events[-1]['reject_code'],'AUTH_FAILED')
            self.assertFalse(any(e['decision']=='FORWARD' for e in h.events))
        finally:h.close()


for label in SCRIPTS:
    def test(self,label=label):self.scenario(label)
    setattr(RunnerCases,'test_case_'+label.replace('-','_'),test)


class GuardTests(unittest.TestCase):
    def test_permit_cannot_be_reused_or_copied(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=Path(d)/'ledger';permit={'run_id':'offline-permit-test','_document_sha256':'a'*64}
            claim_once(permit,ledger=ledger)
            with self.assertRaises(FileExistsError):claim_once(dict(permit),ledger=ledger)

    def test_new_signature_cannot_reuse_same_run_id(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=Path(d)/'ledger';permit={'run_id':'offline-permit-test','_document_sha256':'a'*64}
            claim_once(permit,ledger=ledger)
            with self.assertRaises(FileExistsError):claim_once({**permit,'_document_sha256':'b'*64},ledger=ledger)

    def test_closed_admission_before_any_operations(self):
        with patch('runners.bcp02.admission.source_hash',side_effect=AssertionError('must not get this far')):
            with self.assertRaisesRegex(Blocked,'launch decision'):authorize('/does/not/exist')

    def test_controls_cannot_carry_frames_or_payload(self):
        self.assertEqual(control('P01:START'),('P01','START'))
        for value in ('P01:START:payload','P01:TX','P01:START\nN02:STOP','x'*100,'N99:START'):
            with self.assertRaises(Blocked):control(value)

    def test_pcap_roundtrip_and_truncation(self):
        f=io.BytesIO();w=Writer(f);w.append(bytes(12)+b'\x88\xb5'+b'1234',123.25)
        raw=f.getvalue();self.assertEqual(list(frames(io.BytesIO(raw)))[0][0],123.25)
        for short in (raw[:5],raw[:-1]):
            with self.assertRaises(Blocked):list(frames(io.BytesIO(short)))

    def test_capture_budget(self):
        w=Writer(io.BytesIO(),budget=30)
        with self.assertRaises(Blocked):w.append(b'0'*14,1)

    def test_empty_evidence_never_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(evaluate(d)['outcome'],'INCONCLUSIVE')
            Path(d,'run-manifest.json').write_text('{"network_execution":false}')
            self.assertEqual(evaluate(d)['outcome'],'NOT_RUN')
            import os
            fifo=Path(d)/'untrusted.json';os.mkfifo(fifo)
            with self.assertRaises(Blocked):read_json(fifo)

    def test_scheduler_original_survives_unknown_and_caps_retries(self):
        clock=[0.0];s=Scheduler(clock=lambda:clock[0]);s.begin(b'id',None,b'plain')
        self.assertEqual(s.due(),'SEND')
        for t in (5,10):clock[0]=t;self.assertEqual(s.due(),'SEND')
        clock[0]=15;self.assertEqual(s.due(),'UNKNOWN')
        self.assertEqual(s.pending['message'],b'id');self.assertEqual(s.total,3)
        with self.assertRaises(Reject):s.begin(b'new',None,b'plain')

    def test_packet_port_binding_outgoing_and_truncation(self):
        api=Mock(AF_PACKET=17,SOCK_RAW=3,SOL_SOCKET=1,SO_RCVBUF=8,MSG_TRUNC=32)
        api.htons.side_effect=lambda n:n;api.if_nametoindex.return_value=7
        api.socket.return_value.getsockopt.return_value=0
        ioctl=lambda fd,request,buffer:buffer[:16]+(7).to_bytes(4,'little')+buffer[20:]
        raw=bytes(12)+b'\x88\xb5'+bytes(44)
        def receive(buffers,*args):buffers[0][:len(raw)]=raw;return len(raw),[],0,('a0',0,4,0,b'')
        api.socket.return_value.recvmsg_into.side_effect=receive
        port=PacketPort('a0',api=api,ioctl=ioctl);self.assertIsNone(port.recv())
        api.socket.return_value.recvmsg_into.side_effect=None
        api.socket.return_value.recvmsg_into.return_value=(1515,[],32,('a0',0,0,0,b''))
        with self.assertRaisesRegex(Blocked,'truncated'):port.recv()
        api.socket.return_value.recvmsg_into.return_value=(100,[],0,('r0',0,0,0,b''))
        with self.assertRaisesRegex(Blocked,'interface'):port.recv()
        with self.assertRaises(Blocked):port.send(bytes(1515))


if __name__=='__main__':unittest.main()
