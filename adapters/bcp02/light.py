"""BCP 0.2-LC verified-light-client reads through a local Helios. No live CLI.

Helios verifies Ethereum consensus from a pinned weak-subjectivity checkpoint
(sync-committee BLS signatures) and checks every account, storage and code value
it serves against the verified state root with Merkle proofs. It answers on this
host's loopback interface only. The adapter checks its identity and finality,
canonical ancestry through Helios's EIP-2935 lookups, code hashes and ABI, and
reuses the validated-node snapshot reader unchanged.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from struct import pack
from urllib.parse import urlsplit

from bcp.wire import Checkpoint, digest, domain, fixed, require, uint
from .binding import Limits
from .codec import CHAIN_ID, GENESIS, execution_header, quantity
from .reader import Adapter
from .rpc import LoopbackHTTP
from .store import SavedPoint

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

    # The shared reader's anchor fields; the beacon side is Helios's, not tracked here.
    bootstrap_cl_root=NO_CL_ROOT
    bootstrap_cl_slot=0

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

    def _bind_anchor(self, saved, head, anchor):
        self._el_ancestor(head.execution,anchor.execution,True)
