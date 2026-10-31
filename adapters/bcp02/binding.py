"""Explicit operator trust/deployment binding. No operational defaults or loader."""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from bcp.wire import Checkpoint, context_id, fixed
from .codec import CHAIN_ID, GENESIS


@dataclass(frozen=True)
class Endpoint:
    url: str
    certificate_sha256: bytes

    def __post_init__(self):
        p=urlsplit(self.url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError('an explicit HTTPS endpoint without credentials/query is required')
        if not p.hostname.isascii() or '%' in self.url or '\\' in self.url or any(ord(c)<33 for c in self.url):
            raise ValueError('noncanonical endpoint')
        if p.port is not None and not 1<=p.port<=65535:raise ValueError('invalid port')
        fixed(self.certificate_sha256,32)
        if not any(self.certificate_sha256):raise ValueError('certificate pin required')


@dataclass(frozen=True)
class Binding:
    el: Endpoint
    cl: Endpoint
    addresses: tuple
    runtime_hashes: tuple
    cl_genesis_time: int
    cl_genesis_validators_root: bytes
    cl_genesis_fork_version: bytes
    bootstrap_execution: Checkpoint
    bootstrap_cl_root: bytes
    bootstrap_cl_slot: int
    el_binary_sha256: bytes
    cl_binary_sha256: bytes
    el_version_prefix: str
    cl_version_prefix: str

    def __post_init__(self):
        object.__setattr__(self,'addresses',tuple(self.addresses))
        object.__setattr__(self,'runtime_hashes',tuple(self.runtime_hashes))
        if len(self.addresses)!=3 or len(set(self.addresses))!=3 or len(self.runtime_hashes)!=3:
            raise ValueError('three distinct contracts and three approved actual runtime hashes required')
        for value in self.addresses:
            fixed(value,20)
            if not any(value):raise ValueError('contract address required')
        for value in (*self.runtime_hashes,self.cl_genesis_validators_root,self.bootstrap_cl_root,
                      self.el_binary_sha256,self.cl_binary_sha256):
            fixed(value,32)
            if not any(value):raise ValueError('explicit nonzero trust pin required')
        fixed(self.cl_genesis_fork_version,4)
        self.bootstrap_execution.encode()
        for value in (self.cl_genesis_time,self.bootstrap_cl_slot):
            if type(value) is not int or not 0<=value<2**64:raise ValueError('invalid CL binding')
        if self.bootstrap_execution.timestamp!=self.cl_genesis_time+12*self.bootstrap_cl_slot:
            raise ValueError('bootstrap execution timestamp/CL slot mismatch')
        for value in (self.el_version_prefix,self.cl_version_prefix):
            if type(value) is not str or not value or len(value)>128:raise ValueError('pinned client version prefix required')
        if not re.match(r'^Geth/v1\.17\.10[-/]',self.el_version_prefix) or not re.match(r'^Lighthouse/v8\.3\.2[-/]',self.cl_version_prefix):
            raise ValueError('client prefixes must retain the accepted reference versions')

    @property
    def profile(self):
        return context_id(CHAIN_ID,GENESIS,self.addresses,self.runtime_hashes)

    @property
    def fingerprint(self):
        value={'profile':self.profile.hex(),'endpoints':[(e.url,e.certificate_sha256.hex()) for e in (self.el,self.cl)],
               'cl_genesis':[self.cl_genesis_time,self.cl_genesis_validators_root.hex(),self.cl_genesis_fork_version.hex()],
               'bootstrap':[self.bootstrap_execution.encode().hex(),self.bootstrap_cl_root.hex(),self.bootstrap_cl_slot],
               'binaries':[self.el_binary_sha256.hex(),self.cl_binary_sha256.hex()],
               'versions':[self.el_version_prefix,self.cl_version_prefix]}
        return sha256(b'IPvX BCP adapter binding\0'+json.dumps(value,sort_keys=True,separators=(',',':')).encode()).digest()


@dataclass(frozen=True)
class Limits:
    ancestry_headers: int = 512
    requests: int = 4096
    batch_size: int = 128
    deadline_seconds: int = 30

    def __post_init__(self):
        for value,maximum in ((self.ancestry_headers,4096),(self.requests,16384),(self.batch_size,256),(self.deadline_seconds,60)):
            if type(value) is not int or not 1<=value<=maximum:raise ValueError('invalid resource bound')


@dataclass(frozen=True)
class Selection:
    nfts: tuple = ()
    edges: tuple = ()
    connections: tuple = ()

    def __post_init__(self):
        for field in ('nfts','edges','connections'):
            value=tuple(getattr(self,field));object.__setattr__(self,field,value)
            if len(set(value))!=len(value):raise ValueError('duplicate selection')
        if len(self.nfts)>128 or len(self.edges)>64 or len(self.connections)>16:raise ValueError('selection exceeds bound')
        for nft in self.nfts:
            if type(nft) is not int or not 0<=nft<2**256:raise ValueError('invalid NFT')
        for rule in (*self.edges,*self.connections):fixed(rule,32)
