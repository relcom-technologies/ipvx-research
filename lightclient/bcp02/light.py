"""BCP 0.2-LC verified-light-client reads through a local Helios. No live CLI.

Helios verifies Ethereum consensus from a pinned weak-subjectivity checkpoint
(sync-committee BLS signatures) and checks every account, storage and code value
it serves against the verified state root with Merkle proofs. It answers on this
host's loopback interface only. The adapter checks its identity and finality,
canonical ancestry through Helios's EIP-2935 lookups, code hashes and ABI, and
reuses the validated-node snapshot reader. The accepted adapters/bcp02 files are
imported, never modified: their hashes are pinned by later work.
"""
from dataclasses import dataclass
from hashlib import sha256
import http.client
import json
import sqlite3
from struct import pack
import time
from urllib.parse import urlsplit

from bcp.state import StateView, Attestation
from bcp.wire import Checkpoint, Reject, digest, domain, fixed, require, uint
from adapters.bcp02.binding import Limits, Selection
from adapters.bcp02.codec import CHAIN_ID, GENESIS, execution_header, quantity
from adapters.bcp02.reader import Adapter, Bundle
from adapters.bcp02.rpc import MAX_BODY, PinnedHTTPS, strict_json
from adapters.bcp02.store import SavedPoint

HELIOS_VERSION='helios-0.12.0'
VALIDATED_NODE,VERIFIED_LIGHT_CLIENT=1,2
NO_CL_ROOT=bytes(32)  # this mode does not track a beacon root; Helios holds it


def profile_context(addresses, code_hashes, trust_mode):
    """bcp.wire.context_id with the trust-mode byte as a parameter."""
    require(trust_mode in (VALIDATED_NODE,VERIFIED_LIGHT_CLIENT),'STATE_UNAVAILABLE')
    context=(domain('context')+uint(CHAIN_ID,32)+fixed(GENESIS,32)
             +b''.join(fixed(a,20) for a in addresses)+b''.join(fixed(h,32) for h in code_hashes)
             +pack('!HHIHHBBIHB',1,1500,1800,5,60,8,4,604800,1,trust_mode))
    return digest(context)


def _plain(url):
    p=urlsplit(url)
    if p.username or p.password or p.query or p.fragment or not p.hostname:raise ValueError('URL without credentials/query is required')
    if not url.isascii() or '%' in url or '\\' in url or any(ord(c)<33 for c in url):raise ValueError('noncanonical URL')
    return p


class LoopbackHTTP(PinnedHTTPS):
    """Plain HTTP to the light client on this host's loopback interface only.

    The channel is local, so there is no certificate to pin; Helios, not this
    transport, verifies consensus and state. Beacon paths are not served. The
    exchange keeps PinnedHTTPS's bounds: status 200, identity encoding, JSON,
    8 MiB body and a monotonic deadline.
    """
    def __init__(self, endpoint):
        self.endpoint=endpoint;self._id=0

    def _authenticate(self, connection):
        require(connection.sock.getpeername()[0] in ('127.0.0.1','::1'),'STATE_UNAVAILABLE')

    def _exchange(self, method, path, body, timeout):
        deadline=time.monotonic()+timeout
        endpoint=urlsplit(self.endpoint.url)
        connection=http.client.HTTPConnection(endpoint.hostname,endpoint.port,timeout=timeout)
        try:
            connection.connect()
            self._authenticate(connection)
            connection.request(method,path,body=body,headers={'Accept':'application/json','Content-Type':'application/json'})
            response=connection.getresponse()
            require(response.status==200,'STATE_UNAVAILABLE')
            require(response.getheader('Content-Encoding','identity').lower()=='identity','STATE_UNAVAILABLE')
            require(response.getheader('Content-Type','').split(';',1)[0].lower()=='application/json','STATE_UNAVAILABLE')
            length=response.getheader('Content-Length')
            require(length is None or (length.isdecimal() and int(length)<=MAX_BODY),'STATE_UNAVAILABLE')
            chunks=[];size=0
            while True:
                remaining=deadline-time.monotonic()
                require(remaining>0,'STATE_UNAVAILABLE')
                sock=connection.sock or response.fp.raw._sock
                sock.settimeout(remaining)
                chunk=response.read1(min(65536,MAX_BODY+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
                require(size<=MAX_BODY,'STATE_UNAVAILABLE')
                if response.isclosed():break
            return strict_json(b''.join(chunks))
        except (OSError,http.client.HTTPException,ValueError,RecursionError,AttributeError):
            raise Reject('STATE_UNAVAILABLE') from None
        finally:connection.close()

    def beacon(self, path, timeout):
        raise Reject('STATE_UNAVAILABLE')


@dataclass(frozen=True)
class LoopbackEndpoint:
    url: str

    def __post_init__(self):
        p=_plain(self.url)
        if p.scheme!='http' or p.hostname not in ('127.0.0.1','::1') or p.path not in ('','/'):
            raise ValueError('the light client is reached over loopback HTTP only')
        if p.port is None or not 1<=p.port<=65535:raise ValueError('explicit port required')


@dataclass(frozen=True)
class LightBinding:
    endpoint: LoopbackEndpoint
    addresses: tuple
    runtime_hashes: tuple
    checkpoint_cl_root: bytes       # Helios weak-subjectivity checkpoint (beacon block root)
    bootstrap_execution: Checkpoint
    client_binary_sha256: bytes
    client_version: str
    execution_rpc: str              # declared Helios upstreams; this adapter never contacts them
    consensus_rpc: str

    def __post_init__(self):
        object.__setattr__(self,'addresses',tuple(self.addresses))
        object.__setattr__(self,'runtime_hashes',tuple(self.runtime_hashes))
        if len(self.addresses)!=3 or len(set(self.addresses))!=3 or len(self.runtime_hashes)!=3:
            raise ValueError('three distinct contracts and three approved actual runtime hashes required')
        for value in self.addresses:
            fixed(value,20)
            if not any(value):raise ValueError('contract address required')
        for value in (*self.runtime_hashes,self.checkpoint_cl_root,self.client_binary_sha256):
            fixed(value,32)
            if not any(value):raise ValueError('explicit nonzero trust pin required')
        self.bootstrap_execution.encode()
        if self.client_version!=HELIOS_VERSION:raise ValueError('client must be the pinned Helios release')
        for url in (self.execution_rpc,self.consensus_rpc):
            if _plain(url).scheme!='https':raise ValueError('Helios upstreams must be HTTPS')

    @property
    def profile(self):
        return profile_context(self.addresses,self.runtime_hashes,VERIFIED_LIGHT_CLIENT)

    @property
    def fingerprint(self):
        value={'mode':'verified-light-client','profile':self.profile.hex(),'endpoint':self.endpoint.url,
               'checkpoint':self.checkpoint_cl_root.hex(),'bootstrap':self.bootstrap_execution.encode().hex(),
               'binary':self.client_binary_sha256.hex(),'version':self.client_version,
               'upstreams':[self.execution_rpc,self.consensus_rpc]}
        return sha256(b'IPvX BCP light adapter binding\0'+json.dumps(value,sort_keys=True,separators=(',',':')).encode()).digest()


class LightAdapter(Adapter):
    def __init__(self, binding, store, *, limits=Limits()):
        require(type(binding) is LightBinding and store.fingerprint==binding.fingerprint,'STATE_UNAVAILABLE')
        self.binding,self.store,self.limits=binding,store,limits
        self.el=LoopbackHTTP(binding.endpoint);self.cl=None
        self._busy=False

    def _identity(self):
        # Helios cannot serve block 0 (outside its verified history); the chain is
        # bound by chain ID here and by the pinned checkpoint inside Helios.
        require(quantity(self._rpc('eth_chainId',[]))==CHAIN_ID,'STATE_UNAVAILABLE')
        require(self._rpc('web3_clientVersion',[])==self.binding.client_version,'STATE_UNAVAILABLE')

    def _head(self):
        # Helios answers false only while its verified head is at most 60 s old.
        require(self._rpc('eth_syncing',[]) is False,'STATE_UNAVAILABLE')
        cp,parent=execution_header(self._rpc('eth_getBlockByNumber',['finalized',False]))
        require(self._el_header(cp.block_hash)==(cp,parent),'STATE_UNAVAILABLE')
        return SavedPoint(cp,NO_CL_ROOT,0)

    def _el_ancestor(self, head, target, trusted):
        # One verified lookup replaces the parent walk: Helios returns a block by
        # number only when its hash matches the EIP-2935 history of its verified
        # head (8191 blocks, about 27 hours). An older target is unavailable,
        # never a conflict.
        if target.number>head.number:self._conflict(trusted)
        if target.number==head.number:
            if target!=head:self._conflict(trusted)
            return
        cp,_=execution_header(self._rpc('eth_getBlockByNumber',[hex(target.number),False]))
        require(cp.number==target.number,'STATE_UNAVAILABLE')
        if cp!=target:self._conflict(trusted)

    def read(self, selection, *, now, clock_trusted, packet_checkpoint=None, confirmed_core_checkpoint=None):
        """Adapter.read without the beacon walk and bootstrap binding, which Helios owns."""
        require(not self._busy,'STATE_UNAVAILABLE')
        require(type(selection) is Selection,'STATE_UNAVAILABLE')
        require(clock_trusted is True and type(now) is int and now>=0,'TIME_UNTRUSTED')
        self._busy=True;self._started=time.monotonic();self._requests=0;self._el_headers={};self._cl_headers={}
        try:
            saved=self.store.get();self._identity();head=self._head()
            self._fresh(head.execution,now)
            anchor=saved or SavedPoint(self.binding.bootstrap_execution,NO_CL_ROOT,0)
            require(head.execution.number>=anchor.execution.number,'STATE_CONFLICT')
            self._el_ancestor(head.execution,anchor.execution,True)
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
