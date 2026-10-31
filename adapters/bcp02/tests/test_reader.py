from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from bcp.wire import Reject,Checkpoint
from bcp.journal import Journal
from adapters.bcp02.binding import Endpoint,Limits,Selection
from adapters.bcp02.codec import abi_words,beacon_header,calldata,hexdata,hx,keccak256,no_proxy_opcodes
from adapters.bcp02.reader import Adapter
from adapters.bcp02.rpc import PinnedHTTPS
from adapters.bcp02.store import Store,SavedPoint
from fixtures import Chain,DATA,h


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.chain=Chain();self.binding=self.chain.binding
        self.path=Path(self.tmp.name)/'adapter.sqlite'
        self.store=Store(self.path,self.binding.fingerprint);self.addCleanup(self.store.close)
        self.addCleanup(patch.stopall)
        patch.object(socket,'create_connection',side_effect=AssertionError('live network forbidden')).start()
        patch.object(socket.socket,'connect',side_effect=AssertionError('live network forbidden')).start()
        chain=self.chain
        patch.object(PinnedHTTPS,'_exchange',lambda transport,*args:chain.exchange(transport,*args)).start()
        self.adapter=Adapter(self.binding,self.store)

    def read(self,**kwargs):
        return self.adapter.read(self.chain.selection,now=self.chain.points[self.chain.head].timestamp+60,clock_trusted=True,**kwargs)

    def reject(self,code='STATE_UNAVAILABLE',**kwargs):
        with self.assertRaises(Reject) as caught:self.read(**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_real_contract_views_one_hash_and_core_authorization(self):
        result=self.read();v=result.view
        self.assertEqual(v.latest.nodes[1].epoch,1)
        self.assertEqual(v.latest.nodes[9].status,0)
        rules=self.chain.selection.edges;c=self.chain.selection.connections[0]
        self.assertEqual(v.authorize_path([1,3,2],[(e,1) for e in rules],connection=(c,1),traffic=0,size=20,max_hops=1),2)
        tags=[p[-1] for name,p in self.chain.log if name in ('eth_call','eth_getCode')]
        self.assertGreater(len(tags),10)
        self.assertTrue(all(t=={'blockHash':hx(self.chain.points[1].block_hash),'requireCanonical':True} for t in tags))
        self.assertIsNone(v.attestation.latest_extends_saved)
        self.assertEqual(self.store.get().execution,self.chain.points[1])

    def test_head_movement_during_calls_does_not_mix_snapshots(self):
        def hook(name,p,value):
            if name=='eth_getCode':self.chain.head=2
            return value
        self.chain.hook=hook
        v=self.read().view
        self.assertEqual(v.latest.checkpoint,self.chain.points[1]);self.assertEqual(v.latest.nodes[1].epoch,1)

    def test_old_packet_new_state_revokes_and_proves_saved_ancestry(self):
        self.read();self.chain.head=2
        v=self.read(packet_checkpoint=self.chain.points[1],confirmed_core_checkpoint=self.chain.points[1]).view
        self.assertTrue(v.attestation.latest_extends_saved)
        self.assertEqual((v.packet.nodes[1].epoch,v.latest.nodes[1].epoch),(1,2))
        with self.assertRaises(Reject) as e:v.node(1)
        self.assertEqual(e.exception.code,'KEY_REVOKED')
        tags={p[-1]['blockHash'] for name,p in self.chain.log if name in ('eth_call','eth_getCode')}
        self.assertEqual(tags,{hx(self.chain.points[1].block_hash),hx(self.chain.points[2].block_hash)})

    def test_core_journal_advances_only_with_proof_to_its_own_saved_checkpoint(self):
        journal=Journal(Path(self.tmp.name)/'core.sqlite')
        try:
            first=self.read().view;journal.checkpoint(first.latest.checkpoint,first.attestation.latest_extends_saved)
            self.chain.head=2;unbound=self.read().view
            with self.assertRaises(Reject) as e:journal.checkpoint(unbound.latest.checkpoint,unbound.attestation.latest_extends_saved)
            self.assertEqual(e.exception.code,'STATE_UNAVAILABLE')
            proven=self.read(confirmed_core_checkpoint=first.latest.checkpoint).view
            journal.checkpoint(proven.latest.checkpoint,proven.attestation.latest_extends_saved)
        finally:journal.close()

    def test_confirmed_journal_conflict_stops_adapter(self):
        self.reject('STATE_CONFLICT',confirmed_core_checkpoint=replace(self.chain.points[1],block_hash=h('trusted-conflict')))
        with self.assertRaises(Reject):self.store.get()

    def test_success_reopens_with_saved_anchor_and_reduced_reads(self):
        first=self.read();before=len(self.chain.log)
        second=Store(self.path,self.binding.fingerprint)
        try:
            self.adapter=Adapter(self.binding,second);other=self.read()
            self.assertEqual(first.view.latest,other.view.latest)
            self.assertLess(other.request_count,first.request_count)
        finally:second.close()

    def test_initial_cl_bootstrap_must_bind_exact_execution_state(self):
        def hook(n,p,v):
            if n=='/eth/v2/beacon/blocks/'+self.chain.roots[0]:
                v['data']['message']['body']['execution_payload']['state_root']=hx(h('wrong-bootstrap-binding'))
            return v
        self.chain.hook=hook;self.reject();self.assertIsNone(self.store.get())

    def test_future_clock_and_bad_ancestry_do_not_publish(self):
        with self.assertRaises(Reject) as e:
            self.adapter.read(self.chain.selection,now=self.chain.points[1].timestamp-6,clock_trusted=True)
        self.assertEqual(e.exception.code,'TIME_UNTRUSTED')
        self.chain.el[hx(self.chain.points[0].block_hash)]['number']='0x1'
        self.reject();self.assertIsNone(self.store.get())

    def test_multiple_batches_keep_same_hash(self):
        self.adapter=Adapter(self.binding,self.store,limits=Limits(batch_size=1))
        self.read()
        tags=[p[-1] for n,p in self.chain.log if n in ('eth_call','eth_getCode')]
        self.assertTrue(all(t['blockHash']==hx(self.chain.points[1].block_hash) for t in tags))

    def test_forged_packet_does_not_poison_durable_conflict(self):
        forged=replace(self.chain.points[1],state_root=h('forged'))
        self.reject('FINALITY_REQUIRED',packet_checkpoint=forged)
        self.assertIsNone(self.store.get());self.read()

    def test_unknown_packet_is_unavailable_not_an_empty_snapshot(self):
        cp=replace(self.chain.points[0],number=99,block_hash=h('unavailable'))
        self.reject(packet_checkpoint=cp);self.assertIsNone(self.store.get())

    def test_saved_execution_conflict_latches_across_restart_before_rpc(self):
        self.read()
        cp=self.chain.points[1];self.chain.points[1]=replace(cp,state_root=h('fork'))
        self.chain.el[hx(cp.block_hash)]['stateRoot']=hx(h('fork'))
        self.chain.blocks[self.chain.roots[1]]['data']['message']['body']['execution_payload']['state_root']=hx(h('fork'))
        self.reject('STATE_CONFLICT')
        second=Store(self.path,self.binding.fingerprint)
        try:
            self.adapter=Adapter(self.binding,second);before=len(self.chain.log)
            self.reject('STATE_CONFLICT');self.assertEqual(len(self.chain.log),before)
        finally:second.close()

    def test_saved_cl_conflict_latches(self):
        self.read();saved=self.store.get()
        self.store.save(saved,replace(saved,cl_root=h('other-finalized-root')))
        self.reject('STATE_CONFLICT')
        with self.assertRaises(Reject):self.store.get()

    def test_lagged_provider_does_not_rollback_saved_head(self):
        self.chain.head=2;self.read();self.chain.head=1;self.reject('STATE_CONFLICT')
        self.assertEqual(self.store.get().execution,self.chain.points[2])

    def test_binding_change_refused_and_no_reset(self):
        with self.assertRaises(ValueError):Store(self.path,h('different-binding'))
        with self.assertRaises(Reject):Adapter(replace(self.binding,el=Endpoint('https://other.invalid',h('pin'))),self.store)
        self.assertIsNone(self.store.get())

    def test_store_compare_and_swap_preserves_other_reader(self):
        saved=SavedPoint(self.chain.points[0],bytes.fromhex(self.chain.roots[0][2:]),self.chain.slot)
        self.store.save(None,saved)
        with self.assertRaises(Reject):self.store.save(None,replace(saved,execution=self.chain.points[1]))
        self.assertEqual(self.store.get(),saved)

    def test_identity_and_sync_failures(self):
        cases=[('eth_chainId',lambda v:'0x1'),('web3_clientVersion',lambda v:'unapproved'),
          ('eth_getBlockByNumber',lambda v:{**v,'hash':hx(h('other-genesis'))} if v.get('number')=='0x0' else v),
          ('/eth/v1/beacon/genesis',lambda v:{'data':{**v['data'],'genesis_time':'1'}}),
          ('/eth/v1/node/version',lambda v:{'data':{'version':'other'}}),
          ('eth_syncing',lambda v:{'startingBlock':'0x1'}),
          ('/eth/v1/node/syncing',lambda v:{'data':{**v['data'],'sync_distance':'1'}}),
          ('/eth/v1/node/syncing',lambda v:{'data':{**v['data'],'el_offline':True}})]
        for target,mutate in cases:
            with self.subTest(target=target):
                self.chain.hook=lambda n,p,v:mutate(v) if n==target else v
                self.reject();self.assertIsNone(self.store.get())

    def test_optimistic_or_unfinalized_or_noncanonical_rejected(self):
        for field in ('execution_optimistic','finalized','canonical'):
            with self.subTest(field=field):
                def hook(n,p,v):
                    if n.endswith('/headers/finalized'):
                        if field=='canonical':v['data'][field]=False
                        else:v[field]=field=='execution_optimistic'
                    return v
                self.chain.hook=hook;self.reject('FINALITY_REQUIRED')

    def test_el_cl_transitional_disagreement_is_bounded(self):
        self.chain.mismatches=3;self.reject();self.assertIsNone(self.store.get())
        self.chain.mismatches=1;self.read()

    def test_beacon_header_body_or_execution_mismatch(self):
        for kind in ('root','body','signature','parent','timestamp','fork'):
            with self.subTest(kind=kind):
                def hook(n,p,v):
                    if kind=='root' and n.endswith('/headers/finalized'):v['data']['root']=hx(h('bad-root'))
                    if '/eth/v2/beacon/blocks/' in n:
                        m=v['data']['message'];payload=m['body']['execution_payload']
                        if kind=='body':m['state_root']=hx(h('bad-state'))
                        if kind=='signature':v['data']['signature']=hx(bytes(96))
                        if kind=='parent':payload['parent_hash']=hx(h('bad-parent'))
                        if kind=='timestamp':payload['timestamp']='1'
                        if kind=='fork':v['version']='gloas'
                    return v
                self.chain.hook=hook;self.reject();self.assertIsNone(self.store.get())

    def test_code_immutable_getters_and_abi_fail_closed(self):
        for kind in ('code','getter','padding','enum','owner','empty'):
            with self.subTest(kind=kind):
                def hook(n,p,v):
                    if n=='eth_getCode' and kind=='code':return '0x6000'
                    if n=='eth_call':
                        data=p[0]['data']
                        if kind=='getter' and data==calldata('registry'):return hx(bytes(32))
                        if kind in ('padding','enum','empty') and data==calldata('node',1):
                            raw=bytearray.fromhex(v[2:])
                            if kind=='padding':raw[0]=1
                            elif kind=='enum':raw[159]=3
                            else:raw[159]=0
                            return hx(raw)
                        if kind=='owner' and data==calldata('ownerOf',1):return hx(bytes(32))
                    return v
                self.chain.hook=hook;self.reject();self.assertIsNone(self.store.get())

    def test_missing_record_is_zero_and_allows_edge_is_strict_bool(self):
        for target in ('node','allowsEdge'):
            with self.subTest(target=target):
                def hook(n,p,v):
                    if n=='eth_call' and p[0]['data'].startswith(calldata(target)[:10]):
                        raw=bytearray.fromhex(v[2:]);raw[31]=2
                        if target=='node':raw[159]=0
                        return hx(raw)
                    return v
                self.chain.hook=hook;self.reject()

    def test_partial_read_failure_never_advances_store(self):
        def hook(n,p,v):
            if n=='eth_call' and p[0]['data'].startswith(calldata('allowsEdge')[:10]):raise Reject('STATE_UNAVAILABLE')
            return v
        self.chain.hook=hook;self.reject();self.assertIsNone(self.store.get())
        self.chain.hook=None
        with patch.object(self.store,'save',side_effect=sqlite3.OperationalError('disk unavailable')):
            self.reject();self.assertIsNone(self.store.get())

    def test_clock_freshness_request_ancestry_and_deadline_bounds(self):
        with self.assertRaises(Reject):self.adapter.read(self.chain.selection,now=1,clock_trusted=False)
        with self.assertRaises(Reject) as e:self.adapter.read(self.chain.selection,now=self.chain.points[1].timestamp+1801,clock_trusted=True)
        self.assertEqual(e.exception.code,'STATE_STALE')
        for limits in (Limits(requests=1),Limits(ancestry_headers=1)):
            self.chain.head=2;self.adapter=Adapter(self.binding,self.store,limits=limits)
            self.reject();self.assertIsNone(self.store.get())
        self.chain=Chain();self.adapter=Adapter(self.binding,self.store)
        with patch('adapters.bcp02.reader.time.monotonic',side_effect=[0,31]):self.reject()

    def test_selections_endpoints_and_limits_are_bounded(self):
        for fn in (lambda:Selection(nfts=(1,1)),lambda:Selection(edges=(b'x',)),lambda:Limits(requests=0),
                   lambda:Endpoint('http://el.invalid',h('pin')),lambda:Endpoint('https://u:p@el.invalid',h('pin')),
                   lambda:Endpoint('https://el.invalid/?x=y',h('pin')),lambda:replace(self.binding,runtime_hashes=(bytes(32),)*3),
                   lambda:replace(self.binding,el_version_prefix='Geth/v1.17.100/')):
            with self.subTest(fn=fn),self.assertRaises((ValueError,Reject)):fn()

    def test_codec_canonical_words_keccak_and_opcode_guard(self):
        self.assertEqual(keccak256(b'').hex(),'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        no_proxy_opcodes(bytes.fromhex('60f400'))  # PUSH data is not an opcode.
        for value,widths in (('0x01',[8]),(hx((256).to_bytes(32,'big')),[8]),(hx((2).to_bytes(32,'big')),[1])):
            with self.assertRaises(Reject):abi_words(value,widths)
        with self.assertRaises(Reject):no_proxy_opcodes(bytes.fromhex('f4'))

if __name__=='__main__':unittest.main()
