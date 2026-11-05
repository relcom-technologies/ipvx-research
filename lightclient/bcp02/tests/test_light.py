from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import MagicMock,patch

from bcp.wire import Reject,context_id
from adapters.bcp02.codec import CHAIN_ID,GENESIS,hx
from adapters.bcp02.store import Store
from adapters.bcp02.tests.fixtures import Chain,DATA,h
from lightclient.bcp02.light import (HELIOS_VERSION,LightAdapter,LightBinding,LoopbackEndpoint,
                                     LoopbackHTTP,VALIDATED_NODE,profile_context)


class LightChain(Chain):
    """Helios on loopback: EL JSON-RPC only, blocks by number inside its history window."""
    def __init__(self):
        super().__init__()
        self.version=HELIOS_VERSION;self.syncing=False;self.oldest=None;self.forks={}
        self.light=LightBinding(LoopbackEndpoint('http://127.0.0.1:8545'),self.binding.addresses,
            self.binding.runtime_hashes,h('ws-checkpoint'),self.points[0],h('helios-binary'),HELIOS_VERSION,
            'https://execution.invalid','https://consensus.invalid')

    def light_exchange(self, transport, method, path, body, timeout):
        assert method=='POST' and path=='/' and timeout>0
        result=[]
        for request in json.loads(body):
            name,params=request['method'],request['params'];self.log.append((name,deepcopy(params)))
            value=None;error=None
            if name=='eth_chainId':value=hex(CHAIN_ID)
            elif name=='web3_clientVersion':value=self.version
            elif name=='eth_syncing':value=self.syncing
            elif name=='eth_getBlockByNumber' and params[0]=='finalized':value=self.el[hx(self.points[self.head].block_hash)]
            elif name=='eth_getBlockByNumber':
                number=int(params[0],16)
                if self.oldest is not None and number<self.oldest:error={'code':-32000,'message':'outside EIP-2935 ring buffer range'}
                elif number in self.forks:value=self.forks[number]
                else:value=next((self.el[hx(p.block_hash)] for p in self.points if p.number==number),None)
            elif name=='eth_getBlockByHash':value=self.el.get(params[0])
            else:
                selector=params[-1]
                assert set(selector)=={'blockHash','requireCanonical'} and selector['requireCanonical'] is True
                index=[hx(p.block_hash) for p in self.points].index(selector['blockHash'])
                if name=='eth_getCode':value=DATA['codes'][params[0]]
                else:value=DATA['states']['rotated' if index==2 else 'active'][params[0]['to']+':'+params[0]['data']]
            reply={'jsonrpc':'2.0','id':request['id']}
            if error:reply['error']=error
            else:reply['result']=deepcopy(value)
            result.append(reply)
        return result


class LightReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.chain=LightChain();self.binding=self.chain.light
        self.store=Store(Path(self.tmp.name)/'light.sqlite',self.binding.fingerprint);self.addCleanup(self.store.close)
        self.addCleanup(patch.stopall)
        patch.object(socket,'create_connection',side_effect=AssertionError('live network forbidden')).start()
        patch.object(socket.socket,'connect',side_effect=AssertionError('live network forbidden')).start()
        chain=self.chain
        patch.object(LoopbackHTTP,'_exchange',lambda transport,*args:chain.light_exchange(transport,*args)).start()
        self.adapter=LightAdapter(self.binding,self.store)

    def read(self,**kwargs):
        return self.adapter.read(self.chain.selection,now=self.chain.points[self.chain.head].timestamp+60,clock_trusted=True,**kwargs)

    def reject(self,code='STATE_UNAVAILABLE',**kwargs):
        with self.assertRaises(Reject) as caught:self.read(**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_reads_one_hash_without_beacon_and_under_its_own_profile(self):
        v=self.read().view
        self.assertEqual(v.latest.checkpoint,self.chain.points[1]);self.assertEqual(v.latest.nodes[1].epoch,1)
        tags=[p[-1] for name,p in self.chain.log if name in ('eth_call','eth_getCode')]
        self.assertGreater(len(tags),10)
        self.assertTrue(all(t=={'blockHash':hx(self.chain.points[1].block_hash),'requireCanonical':True} for t in tags))
        self.assertTrue(all(name.startswith(('eth_','web3_')) for name,_ in self.chain.log))
        self.assertEqual(v.latest.profile,self.binding.profile)
        self.assertNotEqual(self.binding.profile,self.chain.binding.profile)
        self.assertEqual(self.store.get().execution,self.chain.points[1])

    def test_profile_differs_from_validated_node_only_in_trust_mode(self):
        b=self.binding
        self.assertEqual(profile_context(b.addresses,b.runtime_hashes,VALIDATED_NODE),
                         context_id(CHAIN_ID,GENESIS,b.addresses,b.runtime_hashes))
        with self.assertRaises(Reject):profile_context(b.addresses,b.runtime_hashes,3)

    def test_saved_ancestry_is_one_verified_lookup(self):
        self.read();self.chain.head=2;self.chain.log.clear()
        v=self.read(confirmed_core_checkpoint=self.chain.points[1]).view
        self.assertTrue(v.attestation.latest_extends_saved)
        self.assertIn(('eth_getBlockByNumber',[hex(self.chain.points[1].number),False]),self.chain.log)
        self.assertEqual(self.store.get().execution,self.chain.points[2])

    def test_bootstrap_off_chain_latches_conflict(self):
        self.chain.forks[self.chain.points[0].number]=dict(self.chain.el[hx(self.chain.points[0].block_hash)],hash=hx(h('other')))
        self.reject('STATE_CONFLICT')
        self.chain.forks.clear();self.reject('STATE_CONFLICT')  # durable latch, no reset

    def test_saved_point_outside_history_window_is_unavailable_not_conflict(self):
        self.read();self.chain.head=2;self.chain.oldest=self.chain.points[2].number
        self.reject()
        self.assertEqual(self.store.get().execution,self.chain.points[1])
        self.chain.oldest=None;self.read()

    def test_packet_off_chain_is_not_durable(self):
        self.read();self.chain.head=2
        self.reject('FINALITY_REQUIRED',packet_checkpoint=replace(self.chain.points[1],state_root=h('forged')))
        self.read()

    def test_identity_and_sync_failures(self):
        for change in (lambda c:setattr(c,'version','helios-0.11.1'),lambda c:setattr(c,'syncing',{'currentBlock':'0x1'})):
            chain=self.chain;change(chain)
            self.reject();chain.version=HELIOS_VERSION;chain.syncing=False
        self.assertIsNone(self.store.get())

    def test_binding_and_transport_bounds(self):
        b=self.binding
        for bad in (lambda:LoopbackEndpoint('http://192.0.2.1:8545'),lambda:LoopbackEndpoint('https://127.0.0.1:8545'),
                    lambda:LoopbackEndpoint('http://127.0.0.1'),lambda:LoopbackEndpoint('http://127.0.0.1:8545/rpc'),
                    lambda:replace(b,client_version='helios-0.11.1'),lambda:replace(b,checkpoint_cl_root=bytes(32)),
                    lambda:replace(b,execution_rpc='http://execution.invalid'),
                    lambda:replace(b,consensus_rpc='https://user:key@consensus.invalid')):
            with self.assertRaises(ValueError):bad()
        with self.assertRaises(Reject):LightAdapter(self.chain.binding,self.store)
        with self.assertRaises(Reject):LightAdapter(replace(b,execution_rpc='https://other.invalid'),self.store)
        transport=LoopbackHTTP(b.endpoint);connection=MagicMock()
        connection.sock.getpeername.return_value=('192.0.2.1',8545)
        with self.assertRaises(Reject):transport._authenticate(connection)
        connection.sock.getpeername.return_value=('127.0.0.1',8545);transport._authenticate(connection)
        with self.assertRaises(Reject):transport.beacon('/eth/v1/beacon/genesis',1)


class LoopbackTransportTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(socket.socket,'connect',side_effect=AssertionError('live network forbidden')).start()
        self.transport=LoopbackHTTP(LoopbackEndpoint('http://127.0.0.1:8545'))

    def exchange(self,raw=b'[]',*,status=200,headers=None,peer='127.0.0.1'):
        self.connection=MagicMock();self.connection.sock.getpeername.return_value=(peer,8545)
        response=self.connection.getresponse.return_value;response.status=status;response.isclosed.return_value=False
        values={'Content-Type':'application/json',**(headers or {})}
        response.getheader.side_effect=lambda name,default=None:values.get(name,default)
        response.read1.side_effect=[raw,b'']
        patch('lightclient.bcp02.light.http.client.HTTPConnection',return_value=self.connection).start()
        return self.transport._exchange('POST','/',b'[]',1)

    def test_loopback_peer_checked_before_request_and_bounds_kept(self):
        self.assertEqual(self.exchange(),[]);self.connection.close.assert_called_once()
        with self.assertRaises(Reject):self.exchange(peer='192.0.2.1')
        self.connection.request.assert_not_called()
        for kwargs in ({'status':302},{'headers':{'Content-Type':'text/html'}},{'headers':{'Content-Encoding':'gzip'}},
                       {'headers':{'Content-Length':str(9*1024*1024)}},{'raw':b'{"a":1,"a":2}'}):
            with self.subTest(**kwargs),self.assertRaises(Reject):self.exchange(**kwargs)


if __name__=='__main__':
    unittest.main()
