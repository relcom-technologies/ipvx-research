"""Authenticated validated-node reads, pinned by execution hash. No live CLI.

EL/CL consensus validation is performed by the operator's trusted full clients.
This adapter verifies API identity, finalized agreement, ancestry, code and ABI;
it does not verify BLS consensus, full beacon-body SSZ, or storage proofs.
"""
from dataclasses import dataclass
from math import isfinite
import sqlite3
import time

from bcp.state import Node, Edge, Connection, Snapshot, StateView, Attestation
from bcp.wire import Checkpoint, Reject, require
from .binding import Limits, Selection
from .codec import (CHAIN_ID,GENESIS,hx,hexdata,quantity,decimal,execution_header,beacon_header,
                    calldata,abi_words,keccak256,no_proxy_opcodes)
from .rpc import PinnedHTTPS
from .store import SavedPoint

SUPPORTED_FORKS=frozenset(('deneb','electra','fulu'))


class _HeadMismatch(Exception):
    pass


@dataclass(frozen=True)
class Bundle:
    view: StateView
    cl_root: bytes
    cl_slot: int
    request_count: int
    selection: Selection


class Adapter:
    def __init__(self, binding, store, *, limits=Limits(), ssl_context=None):
        require(store.fingerprint==binding.fingerprint,'STATE_UNAVAILABLE')
        self.binding,self.store,self.limits=binding,store,limits
        self.el=PinnedHTTPS(binding.el,ssl_context=ssl_context)
        self.cl=PinnedHTTPS(binding.cl,ssl_context=ssl_context)
        # Instances are single-reader; store publication additionally uses CAS.
        self._busy=False

    def _budget(self, count=1):
        elapsed=time.monotonic()-self._started
        require(isfinite(elapsed) and 0<=elapsed<=self.limits.deadline_seconds,'STATE_UNAVAILABLE')
        self._requests+=count
        require(self._requests<=self.limits.requests,'STATE_UNAVAILABLE')
        return min(3.0,max(0.001,self.limits.deadline_seconds-elapsed))

    def _rpc(self, method, params):
        return self.el.batch([(method,params)],self._budget())[0]

    def _batch(self, calls):
        result=[]
        for start in range(0,len(calls),self.limits.batch_size):
            part=calls[start:start+self.limits.batch_size]
            result.extend(self.el.batch(part,self._budget(len(part))))
        return result

    def _beacon(self, path):
        return self.cl.beacon(path,self._budget())

    def _header(self, root):
        if root not in self._cl_headers:
            value=beacon_header(self._beacon('/eth/v1/beacon/headers/'+hx(root)))
            require(value[0]==root,'STATE_UNAVAILABLE')
            self._cl_headers[root]=value
        return self._cl_headers[root]

    def _el_header(self, block_hash):
        if block_hash not in self._el_headers:
            value=execution_header(self._rpc('eth_getBlockByHash',[hx(block_hash),False]))
            require(value[0].block_hash==block_hash,'STATE_UNAVAILABLE')
            self._el_headers[block_hash]=value
        return self._el_headers[block_hash]

    def _identity(self):
        b=self.binding
        require(quantity(self._rpc('eth_chainId',[]))==CHAIN_ID,'STATE_UNAVAILABLE')
        genesis=self._rpc('eth_getBlockByNumber',['0x0',False])
        require(type(genesis) is dict and hexdata(genesis['hash'],32)==GENESIS
                and quantity(genesis['number'])==0,'STATE_UNAVAILABLE')
        g=self._beacon('/eth/v1/beacon/genesis')['data']
        require(decimal(g['genesis_time'])==b.cl_genesis_time
                and hexdata(g['genesis_validators_root'],32)==b.cl_genesis_validators_root
                and hexdata(g['genesis_fork_version'],4)==b.cl_genesis_fork_version,'STATE_UNAVAILABLE')
        ev=self._rpc('web3_clientVersion',[]);cv=self._beacon('/eth/v1/node/version')['data']['version']
        require(type(ev) is str and ev.startswith(b.el_version_prefix)
                and type(cv) is str and cv.startswith(b.cl_version_prefix),'STATE_UNAVAILABLE')

    def _head(self):
        require(self._rpc('eth_syncing',[]) is False,'STATE_UNAVAILABLE')
        s=self._beacon('/eth/v1/node/syncing')['data']
        require(s['is_syncing'] is False and decimal(s['sync_distance'])==0 and s['el_offline'] is False,'STATE_UNAVAILABLE')
        require(s['is_optimistic'] is False,'FINALITY_REQUIRED')
        root,slot,parent,message,signature=beacon_header(self._beacon('/eth/v1/beacon/headers/finalized'))
        self._cl_headers[root]=(root,slot,parent,message,signature)
        block=self._beacon('/eth/v2/beacon/blocks/'+hx(root))
        require(block['execution_optimistic'] is False and block['finalized'] is True,'FINALITY_REQUIRED')
        require(block['version'] in SUPPORTED_FORKS,'STATE_UNAVAILABLE')
        m=block['data']['message'];payload=m['body']['execution_payload']
        for key in ('slot','proposer_index','parent_root','state_root'):require(m[key]==message[key],'STATE_UNAVAILABLE')
        require(block['data']['signature']==signature,'STATE_UNAVAILABLE')
        cp,el_parent=execution_header(self._rpc('eth_getBlockByNumber',['finalized',False]))
        payload_cp=Checkpoint(decimal(payload['block_number']),hexdata(payload['block_hash'],32),
                              hexdata(payload['state_root'],32),decimal(payload['timestamp']))
        if cp!=payload_cp:raise _HeadMismatch()
        require(hexdata(payload['parent_hash'],32)==el_parent
                and cp.timestamp==self.binding.cl_genesis_time+12*slot,'STATE_UNAVAILABLE')
        pinned=self._el_header(cp.block_hash)
        require(pinned==(cp,el_parent),'STATE_UNAVAILABLE')
        return SavedPoint(cp,root,slot)

    def _conflict(self, trusted):
        if trusted:self.store.latch()
        raise Reject('STATE_CONFLICT' if trusted else 'FINALITY_REQUIRED')

    def _el_ancestor(self, head, target, trusted):
        current=head
        for _ in range(self.limits.ancestry_headers+1):
            if current.number==target.number:
                if current!=target:self._conflict(trusted)
                return
            if current.number<target.number:self._conflict(trusted)
            cp,parent=self._el_header(current.block_hash)
            require(cp==current,'STATE_UNAVAILABLE')
            earlier,_=self._el_header(parent)
            require(earlier.number+1==current.number and earlier.timestamp<current.timestamp,'STATE_UNAVAILABLE')
            current=earlier
        raise Reject('STATE_UNAVAILABLE')

    def _cl_ancestor(self, head, target):
        current=head
        for _ in range(self.limits.ancestry_headers+1):
            if current[1]<=target.cl_slot:
                if (current[0],current[1])!=(target.cl_root,target.cl_slot):self._conflict(True)
                return
            parent=self._header(current[2])
            require(parent[1]<current[1],'STATE_UNAVAILABLE')
            current=parent
        raise Reject('STATE_UNAVAILABLE')

    def _fresh(self, cp, now):
        require(cp.timestamp<=now+5,'TIME_UNTRUSTED')
        require(now-cp.timestamp<=1800,'STATE_STALE')

    def _snapshot(self, cp, selection):
        b=self.binding;selector={'blockHash':hx(cp.block_hash),'requireCanonical':True}
        codes=self._batch([('eth_getCode',[hx(a),selector]) for a in b.addresses])
        for value,pin in zip(codes,b.runtime_hashes):
            code=hexdata(value);require(keccak256(code)==pin,'STATE_UNAVAILABLE');no_proxy_opcodes(code)
        def calls(items):
            return self._batch([('eth_call',[{'to':hx(address),'data':data},selector]) for address,data in items])
        registry,transit,connection=b.addresses
        bindings=calls([(transit,calldata('registry')),(connection,calldata('registry')),(connection,calldata('transit'))])
        require([abi_words(v,[160])[0] for v in bindings]==[registry,registry,transit],'STATE_UNAVAILABLE')
        edges={};connections={};nfts=set(selection.nfts)
        rows=calls([(transit,calldata('edge',rule)) for rule in selection.edges])
        for rule,row in zip(selection.edges,rows):
            values=abi_words(row,[256,256,64,64,64,32,16,32,8]);status=values[-1]
            require(status in (0,1,2),'STATE_UNAVAILABLE')
            require(status!=0 or not any(values),'STATE_UNAVAILABLE')
            edges[rule]=Edge(rule,*values)
            if status:
                require(values[0]!=values[1] and all(v>0 for v in values[2:5])
                        and 16<=values[6]<=1500 and 1<=values[7]<=7,'STATE_UNAVAILABLE')
                nfts.update(values[:2])
        rows=calls([(connection,calldata('connection',rule)) for rule in selection.connections])
        for rule,row in zip(selection.connections,rows):
            values=abi_words(row,[256,256,64,64,64,32,8,16,8]);status=values[-1]
            require(status in (0,1,2) and (status!=0 or not any(values)),'STATE_UNAVAILABLE')
            connections[rule]=Connection(rule,*values,frozenset())
            if status:
                require(values[0]!=values[1] and all(v>0 for v in values[2:5]) and 1<=values[5]<=7
                        and 1<=values[6]<=7 and 16<=values[7]<=1500,'STATE_UNAVAILABLE')
                nfts.update(values[:2])
        require(len(nfts)<=128,'STATE_UNAVAILABLE')
        nfts=sorted(nfts);nodes={}
        for nft,row in zip(nfts,calls([(registry,calldata('node',nft)) for nft in nfts])):
            owner,epoch,signing,encryption,status,roles=abi_words(row,[160,64,'bytes32','bytes32',8,8])
            require(status in (0,1,2),'STATE_UNAVAILABLE')
            require(status!=0 or not (any(owner) or epoch or any(signing) or any(encryption) or roles),'STATE_UNAVAILABLE')
            if status:require(any(owner) and epoch>0,'STATE_UNAVAILABLE')
            if status==1:require(any(signing) and any(encryption) and roles in (1,2,3),'STATE_UNAVAILABLE')
            nodes[nft]=Node(nft,owner,epoch,signing,encryption,status,roles)
        owned=[n for n in nodes.values() if n.status]
        for node,row in zip(owned,calls([(registry,calldata('ownerOf',n.nft)) for n in owned])):
            require(abi_words(row,[160])[0]==node.owner,'STATE_UNAVAILABLE')
        pairs=[(c,e) for c in selection.connections for e in selection.edges]
        allowed={c:set() for c in selection.connections}
        for (c,e),row in zip(pairs,calls([(connection,calldata('allowsEdge',c,e)) for c,e in pairs])):
            value=abi_words(row,[1])[0]
            if value:
                require(connections[c].status==edges[e].status==1,'STATE_UNAVAILABLE');allowed[c].add(e)
        for rule,c in tuple(connections.items()):
            connections[rule]=Connection(c.rule,c.source,c.destination,c.version,c.source_epoch,c.destination_epoch,
                                          c.traffic_mask,c.max_hops,c.max_ciphertext,c.status,frozenset(allowed[rule]))
        for item in (*edges.values(),*connections.values()):
            if item.status==1:
                source,dest=nodes[item.source],nodes[item.destination]
                require(source.status==dest.status==1 and (source.epoch,dest.epoch)==(item.source_epoch,item.destination_epoch),
                        'STATE_UNAVAILABLE')
                if isinstance(item,Connection):require(source.roles&1 and dest.roles&1,'STATE_UNAVAILABLE')
        return Snapshot(b.profile,cp,nodes,edges,connections)

    def read(self, selection, *, now, clock_trusted, packet_checkpoint=None, confirmed_core_checkpoint=None):
        """Return C/L for an explicit bounded catalog. Never infer an empty ledger.

        confirmed_core_checkpoint must come from the embedding core's durable
        journal, NOT from a packet. Without it latest_extends_saved stays None.
        """
        require(not self._busy,'STATE_UNAVAILABLE')
        require(type(selection) is Selection,'STATE_UNAVAILABLE')
        require(clock_trusted is True and type(now) is int and now>=0,'TIME_UNTRUSTED')
        self._busy=True;self._started=time.monotonic();self._requests=0;self._el_headers={};self._cl_headers={}
        try:
            saved=self.store.get();self._identity()
            for attempt in range(3):
                try:head=self._head();break
                except _HeadMismatch:
                    if attempt==2:raise Reject('STATE_UNAVAILABLE') from None
            self._fresh(head.execution,now)
            anchor=saved or SavedPoint(self.binding.bootstrap_execution,self.binding.bootstrap_cl_root,self.binding.bootstrap_cl_slot)
            require(head.execution.number>=anchor.execution.number and head.cl_slot>=anchor.cl_slot,'STATE_CONFLICT')
            self._el_ancestor(head.execution,anchor.execution,True)
            self._cl_ancestor(self._header(head.cl_root),anchor)
            # On first use bind the CL bootstrap root to the exact execution
            # checkpoint as well; an execution ancestor alone cannot bind CL.
            if saved is None:
                h=self._header(anchor.cl_root)
                block=self._beacon('/eth/v2/beacon/blocks/'+hx(anchor.cl_root))
                require(block['execution_optimistic'] is False and block['finalized'] is True
                        and block['version'] in SUPPORTED_FORKS,'FINALITY_REQUIRED')
                m=block['data']['message'];p=m['body']['execution_payload']
                for key in ('slot','proposer_index','parent_root','state_root'):require(m[key]==h[3][key],'STATE_UNAVAILABLE')
                require(block['data']['signature']==h[4],'STATE_UNAVAILABLE')
                require(Checkpoint(decimal(p['block_number']),hexdata(p['block_hash'],32),hexdata(p['state_root'],32),decimal(p['timestamp']))
                        ==anchor.execution,'STATE_UNAVAILABLE')
            cp=packet_checkpoint or head.execution
            require(type(cp) is Checkpoint,'STATE_UNAVAILABLE');cp.encode();self._fresh(cp,now)
            self._el_ancestor(head.execution,cp,False)
            if confirmed_core_checkpoint is not None:
                require(type(confirmed_core_checkpoint) is Checkpoint,'STATE_UNAVAILABLE')
                confirmed_core_checkpoint.encode();self._el_ancestor(head.execution,confirmed_core_checkpoint,True)
            latest=self._snapshot(head.execution,selection)
            packet=latest if cp==head.execution else self._snapshot(cp,selection)
            self._budget(0);ended=now+int(time.monotonic()-self._started)
            att=Attestation(True,True,True,True,True,'finalized',False,False,True,True,
                            True if confirmed_core_checkpoint is not None else None)
            view=StateView(packet,latest,att);view.check(self.binding.profile,cp,ended)
            self.store.save(saved,head)  # only a complete validated bundle advances state
            return Bundle(view,head.cl_root,head.cl_slot,self._requests,selection)
        except Reject:raise
        except (KeyError,TypeError,ValueError,OverflowError,RecursionError,sqlite3.Error):raise Reject('STATE_UNAVAILABLE') from None
        finally:self._busy=False
