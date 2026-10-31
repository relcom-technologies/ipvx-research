"""Synthetic EL/CL envelopes around actual offline EVM view results.

Header hashes/state roots are synthetic, not Ethereum consensus/storage proofs.
No socket is opened. Tests patch the authenticated transport at its I/O boundary.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from bcp.wire import Checkpoint
from adapters.bcp02.binding import Binding,Endpoint,Selection
from adapters.bcp02.codec import CHAIN_ID,GENESIS,hx

DATA=json.loads(Path(__file__).with_name('contract-reads.json').read_text())
def h(text):return sha256(text.encode()).digest()


class Chain:
    def __init__(self):
        self.genesis_time=1655733600;self.slot=1000000
        self.points=[];self.headers={};self.blocks={};self.el={};parent=b'\0'*32
        for i in range(3):
            slot=self.slot+i;timestamp=self.genesis_time+12*slot
            cp=Checkpoint(100+i,h('execution'+str(i)),h('execution-state'+str(i)),timestamp)
            message={'slot':str(slot),'proposer_index':'3','parent_root':hx(parent),
                     'state_root':hx(h('beacon-state'+str(i))),'body_root':hx(h('body'+str(i)))}
            # Independent SSZ tree implementation (five fields padded to 8 leaves).
            leaves=[slot.to_bytes(32,'little'),(3).to_bytes(32,'little'),parent,
                    h('beacon-state'+str(i)),h('body'+str(i)),bytes(32),bytes(32),bytes(32)]
            root=sha256(sha256(sha256(leaves[0]+leaves[1]).digest()+sha256(leaves[2]+leaves[3]).digest()).digest()
                        +sha256(sha256(leaves[4]+leaves[5]).digest()+sha256(leaves[6]+leaves[7]).digest()).digest()).digest()
            signature=hx(bytes([i+1])*96)
            self.headers[hx(root)]={'execution_optimistic':False,'finalized':True,'data':{
                'root':hx(root),'canonical':True,'header':{'message':message,'signature':signature}}}
            payload={'block_number':str(cp.number),'block_hash':hx(cp.block_hash),'state_root':hx(cp.state_root),
                     'timestamp':str(timestamp),'parent_hash':hx(self.points[-1].block_hash if i else h('pre-bootstrap'))}
            body={k:v for k,v in message.items() if k!='body_root'};body['body']={'execution_payload':payload}
            self.blocks[hx(root)]={'version':'fulu','execution_optimistic':False,'finalized':True,
                                  'data':{'message':body,'signature':signature}}
            self.el[hx(cp.block_hash)]={'number':hex(cp.number),'hash':hx(cp.block_hash),'stateRoot':hx(cp.state_root),
                                      'timestamp':hex(timestamp),'parentHash':payload['parent_hash']}
            self.points.append(cp);parent=root
        self.roots=list(self.headers);self.head=1;self.log=[];self.hook=None;self.mismatches=0
        self.binding=Binding(Endpoint('https://el.invalid',h('el-cert')),Endpoint('https://cl.invalid',h('cl-cert')),
            tuple(bytes.fromhex(a[2:]) for a in DATA['addresses']),tuple(bytes.fromhex(a[2:]) for a in DATA['runtime_hashes']),
            self.genesis_time,h('genesis-validators'),bytes.fromhex('90000069'),self.points[0],
            bytes.fromhex(self.roots[0][2:]),self.slot,h('el-binary'),h('cl-binary'),'Geth/v1.17.10/','Lighthouse/v8.3.2-')
        self.selection=Selection((1,2,3,9),tuple(bytes.fromhex(DATA['rules'][k][2:]) for k in ('ar','rb')),
                                 (bytes.fromhex(DATA['rules']['connection'][2:]),))

    def exchange(self, transport, method, path, body, timeout):
        assert timeout>0
        if method=='GET':
            if path.endswith('/genesis'):result={'data':{'genesis_time':str(self.genesis_time),
                'genesis_validators_root':hx(self.binding.cl_genesis_validators_root),
                'genesis_fork_version':hx(self.binding.cl_genesis_fork_version)}}
            elif path.endswith('/version'):result={'data':{'version':'Lighthouse/v8.3.2-fixture'}}
            elif path.endswith('/syncing'):result={'data':{'head_slot':str(self.slot+self.head),'sync_distance':'0',
                'is_syncing':False,'is_optimistic':False,'el_offline':False}}
            elif '/headers/' in path:result=self.headers[self.roots[self.head] if path.endswith('/finalized') else path.rsplit('/',1)[1]]
            else:result=self.blocks[path.rsplit('/',1)[1]]
            result=deepcopy(result);self.log.append((path,None))
            return self.hook(path,None,result) if self.hook else result
        requests=json.loads(body);result=[]
        for request in requests:
            name,params=request['method'],request['params'];self.log.append((name,deepcopy(params)))
            if name=='eth_chainId':value=hex(CHAIN_ID)
            elif name=='web3_clientVersion':value='Geth/v1.17.10/fixture'
            elif name=='eth_syncing':value=False
            elif name=='eth_getBlockByNumber':
                if params[0]=='0x0':value={'number':'0x0','hash':hx(GENESIS)}
                else:
                    value=deepcopy(self.el[hx(self.points[self.head].block_hash)])
                    if self.mismatches:self.mismatches-=1;value['hash']=hx(h('mismatch'))
            elif name=='eth_getBlockByHash':value=deepcopy(self.el.get(params[0]))
            else:
                selector=params[-1]
                assert set(selector)=={'blockHash','requireCanonical'} and selector['requireCanonical'] is True
                index=[hx(p.block_hash) for p in self.points].index(selector['blockHash'])
                if name=='eth_getCode':value=DATA['codes'][params[0]]
                else:
                    key=params[0]['to']+':'+params[0]['data']
                    value=DATA['states']['rotated' if index==2 else 'active'][key]
            value=deepcopy(value)
            if self.hook:value=self.hook(name,params,value)
            result.append({'jsonrpc':'2.0','id':request['id'],'result':value})
        return list(reversed(result))  # RPC batch responses need not retain order.
