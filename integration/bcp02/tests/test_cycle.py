from dataclasses import replace
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from adapters.bcp02.codec import hx
from adapters.bcp02.rpc import PinnedHTTPS
from bcp import build
from bcp.journal import Journal
from bcp.wire import Reject,digest,ethernet,uint
from integration.bcp02.journal import BoundJournal
from integration.bcp02.runtime import AdapterCore
from cycle_fixture import DATA,Harness,h,mac,signing,encryption


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        patch('time.monotonic',return_value=1000.0).start()  # logical time, not a latency benchmark
        deny=AssertionError('Live network forbidden in offline BCP integration')
        patch.object(socket,'create_connection',side_effect=deny).start()
        patch.object(socket,'getaddrinfo',side_effect=deny).start()
        patch.object(socket.socket,'connect',side_effect=deny).start()
        self.h=Harness(self.tmp.name);self.addCleanup(self.h.close)
        harness=self.h
        patch.object(PinnedHTTPS,'_exchange',lambda transport,*args:harness.chain.exchange(transport,*args)).start()

    def reject(self,code,fn,*args,**kwargs):
        with self.assertRaises(Reject) as caught:fn(*args,**kwargs)
        self.assertEqual(caught.exception.code,code)

    def rows(self,n,table):return self.h.journals[n].db.execute('SELECT * FROM '+table).fetchall()

    def test_complete_cycle_real_contract_keys_and_durable_receipts(self):
        x=self.h;x.connect();route=x.advertise();data=x.data()
        # Original plaintext/account/message/hash already durable before any hop.
        original=self.rows(1,'requests')[0]
        self.assertEqual(original,(uint(1,32),uint(2,32),h('message'),digest(b'offline request'),b'offline request'))
        self.assertEqual(route.fields['path'],(3,2))
        delivered=x.deliver(data);self.assertEqual((delivered.action,delivered.disposition,delivered.plaintext),('DELIVER','NEW',b'offline request'))
        self.assertEqual(x.return_response(x.response(data,6),'ACCEPTED').disposition,'RECEIPT')
        self.assertEqual(x.return_response(x.response(data,6,phase=2,result=b'offline result'),'COMPLETED').disposition,'RECEIPT')
        self.assertEqual(x.return_response(x.response(data,7),'ERROR').disposition,'ERROR_RECORDED')
        self.assertEqual(self.rows(1,'receipts')[0][2:],(2,digest(b'offline result'),18))
        self.assertEqual(len(x.trace),16)
        self.assertEqual({row['kind'] for row in x.trace},set(range(1,8)))
        self.assertTrue(all(n._core.state is None for n in x.nodes.values()))
        for n in (1,2,3):
            view=x.state(n)
            self.assertEqual(view.packet.nodes[n].signing_key,signing(n).public_key().public_bytes_raw())
            self.assertEqual(view.packet.nodes[n].encryption_key,encryption(n).public_key().public_bytes_raw())
        tags=[p[-1] for name,p in x.chain.log if name in ('eth_call','eth_getCode')]
        self.assertTrue(tags and all(t=={'blockHash':hx(x.chain.points[1].block_hash),'requireCanonical':True} for t in tags))

    def test_c_and_l_advance_uses_actual_core_journal_not_packet_assertion(self):
        x=self.h;x.connect();data=x.data();x.chain.head=2;x.chain.later_state='active'
        adapter=x.nodes[3].adapter;saved=x.journals[3].saved_checkpoint()
        with patch.object(adapter,'read',wraps=adapter.read) as reader:
            self.assertEqual(x.receive(3,1,data,'old-C-new-L').action,'FORWARD')
        self.assertEqual(reader.call_args.kwargs['confirmed_core_checkpoint'],saved)
        self.assertEqual(reader.call_args.kwargs['packet_checkpoint'],data.fields['checkpoint'])
        self.assertEqual(x.journals[3].saved_checkpoint(),x.chain.points[2])
        tags={p[-1]['blockHash'] for name,p in x.chain.log if name in ('eth_call','eth_getCode')}
        self.assertEqual(tags,{hx(x.chain.points[1].block_hash),hx(x.chain.points[2].block_hash)})

    def test_key_rotation_in_new_l_blocks_old_authenticated_data(self):
        x=self.h;x.connect();data=x.data();x.chain.head=2
        self.reject('KEY_REVOKED',x.receive,3,1,data,'revoked')
        self.assertEqual(self.rows(2,'deliveries'),[])
        self.assertIsNone(x.nodes[3]._core.state)

    def test_withdrawn_transit_blocks_forward_without_delivering(self):
        x=self.h;x.connect();data=x.data();x.chain.later_state='edge_denied';x.chain.head=2
        self.reject('POLICY_DENIED',x.receive,3,1,data,'edge-withdrawn')
        self.assertEqual(self.rows(2,'deliveries'),[])

    def test_reverse_connection_is_independently_required(self):
        x=self.h;x.connect();data=x.data();x.deliver(data);response=x.response(data,6)
        x.chain.later_state='reverse_denied';x.chain.head=2
        self.reject('POLICY_DENIED',x.receive,3,2,response,'reverse-denied')
        self.assertEqual(self.rows(1,'receipts'),[])

    def test_retransmission_deduplicates_but_session_replay_is_rejected(self):
        x=self.h;x.connect();data=x.data();x.deliver(data)
        self.reject('SESSION_REPLAY',x.receive,3,1,data,'replayed-hop')
        session=x.session(1,3);again=build.rewrap(data,session,x.sequence(session,1),0,signing(1))
        self.assertEqual(x.deliver(again,'RETRY').disposition,'DUPLICATE')
        self.assertEqual(len(self.rows(2,'deliveries')),1)
        self.assertEqual(len(self.rows(1,'requests')),1)

    def test_original_outbox_conflict_never_returns_replacement_packet(self):
        x=self.h;x.connect();x.data();old=self.rows(1,'requests')
        self.reject('MESSAGE_CONFLICT',x.data,plaintext=b'changed')
        self.assertEqual(self.rows(1,'requests'),old)
        self.assertEqual(self.rows(2,'deliveries'),[])

    def test_pending_limit_preserves_completed_originals_and_never_reallocates_ids(self):
        x=self.h;x.connect();first=x.data()
        for i in range(63):x.data(message=h('pending-'+str(i)))
        self.assertEqual(len(self.rows(1,'requests')),64)
        self.reject('POLICY_DENIED',x.data,message=h('over-limit'))
        self.assertEqual(len(self.rows(1,'requests')),64)
        x.deliver(first);x.return_response(x.response(first,6,phase=2,result=b'done'),'COMPLETED')
        x.data(message=h('after-completion'))
        self.assertEqual(len(self.rows(1,'requests')),65)  # original retained, no purge
        self.assertEqual(self.rows(1,'receipts')[0][2],2)

    def test_restart_keeps_dedup_but_requires_real_handshake_again(self):
        x=self.h;x.connect();data=x.data();x.deliver(data);old=self.rows(2,'deliveries')
        x.restart(2);self.assertEqual(x.nodes[2]._core._sessions,{})
        session=x.session(3,2);last=build.rewrap(data,session,x.sequence(session,3),1,signing(3))
        self.reject('AUTH_FAILED',x.receive,2,3,last,'after-restart-without-handshake')
        self.assertEqual(self.rows(2,'deliveries'),old)
        x.handshake(3,2)
        first=build.rewrap(data,x.session(1,3),x.sequence(x.session(1,3),1),0,signing(1))
        self.assertEqual(x.deliver(first,'AFTER-RESTART').disposition,'DUPLICATE')
        self.assertEqual(self.rows(2,'deliveries'),old)

    def test_completed_receipt_and_original_survive_requester_restart(self):
        x=self.h;x.connect();data=x.data();x.deliver(data)
        x.return_response(x.response(data,6,phase=2,result=b'result'),'COMPLETED')
        before=(self.rows(1,'requests'),self.rows(1,'receipts'));x.restart(1)
        self.assertEqual((self.rows(1,'requests'),self.rows(1,'receipts')),before)
        self.assertEqual(x.nodes[1]._core._sessions,{})

    def test_unknown_receipt_does_not_create_original_or_erase_completed(self):
        x=self.h;x.connect();data=x.data();x.deliver(data)
        x.return_response(x.response(data,6,phase=2,result=b'result'),'COMPLETED')
        old=(self.rows(1,'requests'),self.rows(1,'receipts'))
        response=x.response(data,6,message=h('unknown'))
        self.reject('UNKNOWN',x.return_response,response,'UNSOLICITED')
        self.assertEqual((self.rows(1,'requests'),self.rows(1,'receipts')),old)

    def test_late_accepted_and_error_do_not_downgrade_completed(self):
        x=self.h;x.connect();data=x.data();x.deliver(data)
        x.return_response(x.response(data,6,phase=2,result=b'result'),'COMPLETED')
        x.return_response(x.response(data,6),'LATE-ACCEPTED')
        x.return_response(x.response(data,7),'LATE-ERROR')
        self.assertEqual(self.rows(1,'receipts')[0][2:],(2,digest(b'result'),18))
        self.reject('MESSAGE_CONFLICT',x.return_response,x.response(data,6,phase=2,result=b'changed'),'CHANGED-RESULT')
        self.assertEqual(self.rows(1,'receipts')[0][2:],(2,digest(b'result'),18))

    def test_rpc_failure_never_reuses_previous_state_or_creates_outbox(self):
        x=self.h;x.connect();x.data();old=self.rows(1,'requests')
        def fail(name,p,value):
            if name=='eth_call':raise Reject('STATE_UNAVAILABLE')
            return value
        x.chain.hook=fail
        self.reject('STATE_UNAVAILABLE',x.data,message=h('not-stored'))
        self.assertEqual(self.rows(1,'requests'),old)
        self.assertIsNone(x.nodes[1]._core.state)
        self.assertEqual(self.rows(2,'deliveries'),[])

    def test_outbox_storage_failure_returns_no_frame(self):
        x=self.h;x.connect()
        with patch.object(x.journals[1],'remember_request',side_effect=sqlite3.OperationalError('disk failure')):
            self.reject('STATE_UNAVAILABLE',x.data)
        self.assertEqual(self.rows(1,'requests'),[])

    def test_stale_clock_and_malformed_or_unknown_scope_stop_before_core(self):
        x=self.h;before=len(x.chain.log)
        self.reject('MALFORMED_HEADER',x.nodes[1].receive,b'not a frame',**x.clock())
        unknown=build.hello(x.chain.binding.profile,9,1,h('n'),x.chain.points[1],1,mac(9),signing(1))
        self.reject('POLICY_DENIED',x.nodes[1].receive,ethernet(bytes([255])*6,mac(9),unknown.encode()),**x.clock())
        self.assertEqual(len(x.chain.log),before)
        self.reject('TIME_UNTRUSTED',x.nodes[1].state,now=x.now,monotonic=x.mono,clock_trusted=False)
        self.reject('STATE_STALE',x.nodes[1].state,now=x.now+2000,monotonic=x.mono,clock_trusted=True)
        self.assertIsNone(x.journals[1].saved_checkpoint())

    def test_packet_expiry_is_checked_after_adapter_read_delay(self):
        x=self.h;x.connect();data=x.data(expires=x.now+2);adapter=x.nodes[3].adapter;original=adapter.read;clock=[1000.0]
        def delayed(*a,**kw):
            result=original(*a,**kw);clock[0]+=3;return result
        with patch('time.monotonic',side_effect=lambda:clock[0]),patch.object(adapter,'read',side_effect=delayed):
            self.reject('EXPIRED',x.receive,3,1,data,'expired-during-read')
        self.assertEqual(self.rows(2,'deliveries'),[])

    def test_sender_control_signature_must_match_contract_key(self):
        x=self.h
        hello=build.hello(x.chain.binding.profile,1,1,h('nonce'),x.chain.points[1],1,mac(1),signing(2))
        self.reject('AUTH_FAILED',x.nodes[1].sent_hello,hello,**x.clock())
        self.assertEqual(x.nodes[1]._core._hellos,{})
        self.assertIsNone(x.journals[1].saved_checkpoint())

    def test_forged_packet_checkpoint_cannot_poison_saved_conflict(self):
        x=self.h;cp=replace(x.chain.points[1],state_root=h('forged'))
        hello=build.hello(x.chain.binding.profile,1,1,h('nonce'),cp,1,mac(1),signing(1))
        self.reject('FINALITY_REQUIRED',x.nodes[3].receive,ethernet(bytes([255])*6,mac(1),hello.encode()),**x.clock())
        self.assertIsNone(x.journals[3].saved_checkpoint());self.assertIsNone(x.stores[3].get())
        x.handshake(1,3)

    def test_core_conflict_survives_restart_and_stops_before_adapter_io(self):
        x=self.h;x.state(1);j=x.journals[1]
        with j.guard():self.reject('STATE_CONFLICT',j.checkpoint,replace(j.saved_checkpoint(),state_root=h('conflict')))
        x.restart(1);before=len(x.chain.log)
        self.reject('STATE_CONFLICT',x.state,1);self.assertEqual(len(x.chain.log),before)

    def test_adapter_conflict_survives_restart_without_core_admission(self):
        x=self.h;x.state(1);store=x.stores[1];saved=store.get()
        store.save(saved,replace(saved,execution=replace(saved.execution,state_root=h('conflict'))))
        self.reject('STATE_CONFLICT',x.state,1);x.restart(1);before=len(x.chain.log)
        self.reject('STATE_CONFLICT',x.state,1);self.assertEqual(len(x.chain.log),before)

    def test_journal_scope_and_legacy_import_are_not_guessed(self):
        x=self.h
        self.reject('STATE_CONFLICT',BoundJournal,x.directory/'core-1.sqlite',x.chain.binding.profile,2)
        self.reject('STATE_CONFLICT',BoundJournal,x.directory/'core-1.sqlite',h('other-profile'),1)
        legacy=x.directory/'legacy.sqlite';j=Journal(legacy);j.remember_request(1,2,h('msg'),digest(b'original'),b'original');j.close()
        self.reject('STATE_CONFLICT',BoundJournal,legacy,x.chain.binding.profile,1)
        self.assertIsNone(x.journals[1].saved_checkpoint())

    def test_journal_cas_rejects_an_unproved_concurrent_advance(self):
        x=self.h;x.state(1);other=BoundJournal(x.directory/'core-1.sqlite',x.chain.binding.profile,1);done=[False]
        self.addCleanup(other.close)
        def hook(name,p,value):
            if name=='eth_getCode' and not done[0]:
                done[0]=True
                with other.guard():other.checkpoint(x.chain.points[2],True)
            return value
        x.chain.hook=hook
        self.reject('STATE_UNAVAILABLE',x.state,1)
        self.assertEqual(x.journals[1].saved_checkpoint(),x.chain.points[2])

    def test_integration_does_not_accept_caller_attestation_or_saved_anchor(self):
        x=self.h
        with self.assertRaises(TypeError):x.nodes[1].state(**x.clock(),confirmed_core_checkpoint=x.chain.points[0])
        with self.assertRaises(TypeError):AdapterCore(x.nodes[1].adapter,x.journals[1],x.chain.selection,1,mac(1),state='trusted')
        with x.journals[1].guard():self.reject('STATE_UNAVAILABLE',x.nodes[1].state,**x.clock())

if __name__=='__main__':unittest.main()
