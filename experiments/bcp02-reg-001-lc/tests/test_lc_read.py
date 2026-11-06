from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))

import derive_expected
import lc_read
from adapters.bcp02.codec import CHAIN_ID,calldata,hx,keccak256
from adapters.bcp02.tests.fixtures import Chain,h
from lightclient.bcp02.light import HELIOS_VERSION,LoopbackHTTP

PROTOCOL=json.loads((HERE/'protocol.json').read_text())
EXPECTED=json.loads((HERE/'expected.json').read_text())
CODE=b'\x00'


def word(value):
    return value if isinstance(value,bytes) else int(value,0).to_bytes(32,'big')


def encoded(row):
    return hx(b''.join(word(v) for v in row))


class FakeHelios(Chain):
    """Helios answering on loopback with the given registry state; real addresses and rules."""
    def __init__(self, protocol, state):
        super().__init__()
        self.version=HELIOS_VERSION;self.syncing=False;self.oldest=None
        registry,transit,connection=protocol['contracts']['addresses']
        s=protocol['selection'];self.answers={}
        def at(address,name,*args):return address.lower()+':'+calldata(name,*args)
        self.answers[at(transit,'registry')]=encoded([registry])
        self.answers[at(connection,'registry')]=encoded([registry])
        self.answers[at(connection,'transit')]=encoded([transit])
        for nft,row in state['nodes'].items():
            self.answers[at(registry,'node',int(nft))]=encoded(row)
            self.answers[at(registry,'ownerOf',int(nft))]=encoded(row[:1])
        rule=lambda v:bytes.fromhex(v[2:])
        for name,row in state['edges'].items():self.answers[at(transit,'edge',rule(s['edges'][name]))]=encoded(row)
        for name,row in state['connections'].items():
            c=rule(s['connections'][name]);self.answers[at(connection,'connection',c)]=encoded(row)
            for edge,value in s['edges'].items():
                self.answers[at(connection,'allowsEdge',c,rule(value))]=encoded(['0x1' if edge in state['allowed_edges'][name] else '0x0'])

    def light_exchange(self, transport, method, path, body, timeout):
        assert method=='POST' and path=='/' and timeout>0
        result=[]
        for request in json.loads(body):
            name,params=request['method'],request['params'];self.log.append((name,deepcopy(params)))
            error=None;value=None
            if name=='eth_chainId':value=hex(CHAIN_ID)
            elif name=='web3_clientVersion':value=self.version
            elif name=='eth_syncing':value=self.syncing
            elif name=='eth_getBlockByNumber' and params[0]=='finalized':value=self.el[hx(self.points[self.head].block_hash)]
            elif name=='eth_getBlockByNumber':
                number=int(params[0],16)
                if self.oldest is not None and number<self.oldest:error={'code':-32000,'message':'outside EIP-2935 ring buffer range'}
                else:value=next(self.el[hx(p.block_hash)] for p in self.points if p.number==number)
            elif name=='eth_getBlockByHash':value=self.el.get(params[0])
            elif name=='eth_getCode':value=hx(CODE)
            elif name=='eth_call':value=self.answers[params[0]['to'].lower()+':'+params[0]['data']]
            else:raise AssertionError(name)
            reply={'jsonrpc':'2.0','id':request['id']}
            if error:reply['error']=error
            else:reply['result']=deepcopy(value)
            result.append(reply)
        return result


class DerivationTests(unittest.TestCase):
    def test_expected_file_is_the_derivation(self):
        self.assertEqual(derive_expected.derive(),EXPECTED)

    def test_only_node_a_and_its_edge_differ_from_s4(self):
        s4=next(json.loads(l) for l in (derive_expected.RUN/'run-6.jsonl').read_text().splitlines() if '"snapshot-s4"' in l)['snapshot']
        self.assertEqual(EXPECTED['nodes']['1'][1:4],['21',derive_expected.key(1038),derive_expected.key(1039)])
        self.assertEqual(EXPECTED['nodes']['1'][4:],s4['nfts'][0][4:])
        for index,nft in enumerate(('1','2','3','99')):
            self.assertEqual(EXPECTED['nodes'][nft][0],s4['nfts'][index][0].lower())
        self.assertEqual(EXPECTED['nodes']['2'][1:],s4['nfts'][1][1:]);self.assertEqual(EXPECTED['nodes']['3'][1:],s4['nfts'][2][1:])
        self.assertEqual(EXPECTED['edges']['A->R'][:-1],s4['edges'][0][:-1]);self.assertEqual(EXPECTED['edges']['A->R'][-1],'2')
        self.assertEqual(EXPECTED['edges']['R->B'],s4['edges'][1]);self.assertEqual(EXPECTED['connections']['A->B'],s4['connections'][0])

    def test_protocol_pins_are_the_run_6_contracts_and_rules(self):
        results=json.loads((derive_expected.ROOT/'experiments/bcp02-reg-001/results.json').read_text())['complete_run']['contracts']
        self.assertEqual(PROTOCOL['contracts']['addresses'],[results[n] for n in PROTOCOL['contracts']['names']])
        journal=(derive_expected.RUN/'run-6.jsonl').read_text()
        s=PROTOCOL['selection']
        for rule in (*s['edges'].values(),*s['connections'].values()):
            self.assertRegex(journal,'rule '+re.escape(rule[:10]))
        self.assertFalse(PROTOCOL['transactions_performed'])

    def test_published_result_is_the_pinned_pass(self):
        raw=(HERE/'result.json').read_bytes();result=json.loads(raw);pinned=PROTOCOL['results']
        self.assertEqual(sha256(raw).hexdigest(),pinned['sha256'])
        self.assertEqual((result['outcome'],result['differences'],result['transactions_sent']),('PASS',[],0))
        self.assertEqual(lc_read.compare(EXPECTED,result['observed']),[])
        self.assertEqual((result['block']['number'],result['checkpoint']),(pinned['block'],pinned['checkpoint']['root']))


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patch.stopall)
        patch.object(socket,'create_connection',side_effect=AssertionError('live network forbidden')).start()
        patch.object(socket.socket,'connect',side_effect=AssertionError('live network forbidden')).start()
        self.protocol=deepcopy(PROTOCOL)
        self.protocol['contracts']['runtime_keccak256']=[hx(keccak256(CODE))]*3
        self.protocol['helios']['bootstrap_blocks_behind_head']=1
        self.state=deepcopy(EXPECTED)

    def read(self):
        self.chain=chain=getattr(self,'chain',None) or FakeHelios(self.protocol,self.state)
        patch.object(LoopbackHTTP,'_exchange',lambda transport,*args:chain.light_exchange(transport,*args)).start()
        now=lambda:chain.points[chain.head].timestamp+60
        return lc_read.read(self.protocol,EXPECTED,h('checkpoint'),h('binary'),Path(self.tmp.name)/'light.sqlite',now=now)

    def test_expected_state_passes_with_a_verified_ancestry_lookup(self):
        result=self.read()
        self.assertEqual((result['outcome'],result['differences']),('PASS',[]))
        self.assertEqual(result['transactions_sent'],0)
        self.assertEqual(result['bootstrap_block'],self.chain.points[0].number)
        self.assertEqual(result['block']['number'],self.chain.points[1].number)
        names={name for name,_ in self.chain.log}
        self.assertLessEqual(names,{'eth_chainId','web3_clientVersion','eth_syncing','eth_getBlockByNumber',
                                    'eth_getBlockByHash','eth_getCode','eth_call'})
        lookups=[p[0] for name,p in self.chain.log if name=='eth_getBlockByNumber']
        self.assertGreaterEqual(lookups.count(hex(self.chain.points[0].number)),2)
        json.dumps(result)

    def test_plain_s4_is_not_a_pass(self):
        self.state['nodes']['1'][1:4]=['1',derive_expected.key(10),derive_expected.key(11)]
        self.state['edges']['A->R'][-1]='1'
        result=self.read()
        self.assertEqual(result['outcome'],'FAIL_STATE')
        self.assertEqual([d['path'] for d in result['differences']],['nodes.1','edges.A->R'])

    def test_any_single_value_difference_fails(self):
        self.state['nodes']['2'][2]=derive_expected.key(77)
        result=self.read()
        self.assertEqual(result['outcome'],'FAIL_STATE')
        self.assertEqual(result['differences'][0]['path'],'nodes.2')
        self.assertEqual(result['differences'][0]['observed'][2],derive_expected.key(77))

    def test_compare_reports_missing_and_extra(self):
        seen=deepcopy(EXPECTED);del seen['nodes']['99'];seen['edges']['extra']=['1']
        self.assertEqual([d['path'] for d in lc_read.compare(EXPECTED,seen)],['nodes.99','edges.extra'])

    def test_syncing_helios_blocks_without_a_verdict(self):
        self.chain=FakeHelios(self.protocol,self.state);self.chain.syncing={'currentBlock':'0x1'}
        result=self.read()
        self.assertEqual((result['outcome'],result['reject']),('BLOCKED','STATE_UNAVAILABLE'))
        self.assertNotIn('observed',result)

    def test_wrong_client_blocks(self):
        self.chain=FakeHelios(self.protocol,self.state);self.chain.version='helios-0.11.0'
        self.assertEqual(self.read()['outcome'],'BLOCKED')

    def test_bootstrap_outside_history_window_blocks(self):
        self.chain=FakeHelios(self.protocol,self.state);self.chain.oldest=self.chain.points[1].number
        self.assertEqual(self.read()['outcome'],'BLOCKED')


if __name__=='__main__':
    unittest.main()
