"""Fresh, explicit synthetic EL/CL envelopes around real local EVM view outputs.

Only this marked fixture provider replaces transport; the accepted Adapter still
checks identity, ancestry, code hashes and EIP-1898 contract reads. No live RPC.
"""
from copy import deepcopy
import os
from pathlib import Path
import subprocess

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from adapters.bcp02.binding import Binding, Endpoint, Selection
from adapters.bcp02.codec import CHAIN_ID, GENESIS, hx
from adapters.bcp02.reader import Adapter
from bcp.wire import Checkpoint, Reject, digest, require
from .common import ROOT, private_json, read_json, need, sha


def envelopes(run, timestamp, *, branch='active'):
    """Timestamp is fixed once, never refreshed when reading this dataset."""
    genesis = 1655733600; slot = (timestamp-genesis)//12
    need(slot > 1000, 'invalid fixture epoch')
    points, headers, blocks, el = [], {}, {}, {}
    parent = bytes(32)
    for i in range(3):
        s = slot+i; t = genesis+12*s
        h = lambda label: digest(f'{run}/{slot}/{i}/{branch if i==2 else "common"}/{label}'.encode())
        cp = Checkpoint(100+i, h('execution'), h('execution-state'), t)
        message = dict(slot=str(s), proposer_index='3', parent_root=hx(parent),
                       state_root=hx(h('beacon-state')), body_root=hx(h('body')))
        leaves = [s.to_bytes(32,'little'), (3).to_bytes(32,'little'), parent,
                  h('beacon-state'), h('body'), bytes(32), bytes(32), bytes(32)]
        while len(leaves)>1:
            leaves=[digest(leaves[j]+leaves[j+1]) for j in range(0,len(leaves),2)]
        root = leaves[0]; signature=hx(bytes([i+1])*96)
        headers[hx(root)] = dict(execution_optimistic=False, finalized=True,
            data=dict(root=hx(root), canonical=True, header=dict(message=message, signature=signature)))
        payload=dict(block_number=str(cp.number), block_hash=hx(cp.block_hash), state_root=hx(cp.state_root),
                     timestamp=str(t), parent_hash=hx(points[-1].block_hash if points else h('parent')))
        body={k:v for k,v in message.items() if k!='body_root'}; body['body']={'execution_payload':payload}
        blocks[hx(root)]=dict(version='fulu', execution_optimistic=False, finalized=True,
                             data=dict(message=body,signature=signature))
        el[hx(cp.block_hash)] = dict(number=hex(cp.number), hash=hx(cp.block_hash), stateRoot=hx(cp.state_root),
                                   timestamp=hex(t), parentHash=payload['parent_hash'])
        points.append(cp); parent=root
    return dict(genesis_time=genesis, slot=slot, points=[p.encode().hex() for p in points],
                headers=headers, blocks=blocks, el=el, roots=list(headers))


def export(directory, run, now, *, node_binary='node'):
    """Future preparation only; CLI admission precedes calls. Tests use temp dirs."""
    directory=Path(directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    public={}
    for nft,name in ((1,'A'),(2,'B'),(3,'R'),(101,'rotated')):
        signing=Ed25519PrivateKey.generate(); encryption=X25519PrivateKey.generate()
        public[str(nft)]={'signing':{'public_key_hex':signing.public_key().public_bytes_raw().hex()},
                          'encryption':{'public_key_hex':encryption.public_key().public_bytes_raw().hex()}}
        if nft != 101:
            folder=directory/name; folder.mkdir(mode=0o700)
            private_json(folder/'key.json',dict(nft=nft,signing=signing.private_bytes_raw().hex(),
                                                encryption=encryption.private_bytes_raw().hex()))
    private_json(directory/'public-keys.json',public)
    generated=directory/'bank.json'
    cmd=[node_binary,'--import',str(ROOT/'contracts/bcp02/test/offline.mjs'),
         str(Path(__file__).with_name('generate_bank.mjs')),str(directory/'public-keys.json'),str(generated)]
    subprocess.run(cmd,check=True,timeout=90,stdin=subprocess.DEVNULL,capture_output=True)
    generated.chmod(0o600)
    bank=read_json(generated)
    need(bank['keys']==public and set(bank['states'])=={'active','rotated','reverse_denied','edge_denied'},'unexpected EVM bank')
    private_json(directory/'dataset.json',dict(schema=1,state_mode='fixture-state-ethernet',run_id=run,
        warning='Synthetic headers/state roots; no Ethereum finality or deployed contracts.',
        bank=bank, fresh=envelopes(run,now-24), stale=envelopes(run+'-stale',now-1920),
        branches={mode:envelopes(run,now-24,branch=mode) for mode in ('rotated','edge_denied','reverse_denied')},
        evm_generator_sha256=sha(Path(__file__).with_name('generate_bank.mjs').read_bytes())))
    return sha((directory/'dataset.json').read_bytes())


class FixtureChain:
    def __init__(self, dataset):
        need(dataset['state_mode']=='fixture-state-ethernet', 'fixture marker required')
        self.data=dataset; self.bank=dataset['bank']; self.mode='active'; self.log=[]
        self.fresh=dataset['fresh']; self.head=1
        from bcp.wire import Reader
        self.points=[Checkpoint.read(Reader(bytes.fromhex(p))) for p in self.fresh['points']]
        h=lambda label:digest((dataset['run_id']+'/'+label).encode())
        self.binding=Binding(Endpoint('https://el.invalid',h('fixture-el-cert')),
            Endpoint('https://cl.invalid',h('fixture-cl-cert')),
            tuple(bytes.fromhex(a[2:]) for a in self.bank['addresses']),
            tuple(bytes.fromhex(a[2:]) for a in self.bank['runtime_hashes']),
            self.fresh['genesis_time'],h('fixture-genesis-validators'),bytes.fromhex('90000069'),
            self.points[0],bytes.fromhex(self.fresh['roots'][0][2:]),self.fresh['slot'],
            h('synthetic-el-not-installed'),h('synthetic-cl-not-installed'),
            'Geth/v1.17.10/','Lighthouse/v8.3.2-')
        self.edges={k:bytes.fromhex(v[2:]) for k,v in self.bank['edges'].items()}
        self.connections={k:bytes.fromhex(v[2:]) for k,v in self.bank['connections'].items()}
        self.selection=Selection((1,2,3),tuple(self.edges.values()),tuple(self.connections.values()))

    def _current(self):
        if self.mode=='unavailable':raise Reject('STATE_UNAVAILABLE')
        if self.mode=='stale':return self.data['stale']
        return self.fresh if self.mode=='active' else self.data['branches'][self.mode]

    def batch(self, calls, timeout):
        require(timeout>0,'STATE_UNAVAILABLE');env=self._current();result=[]
        index=1 if self.mode in ('active','stale') else 2
        for name,p in calls:
            self.log.append((name,deepcopy(p)))
            if name=='eth_chainId':v=hex(CHAIN_ID)
            elif name=='web3_clientVersion':v='Geth/v1.17.10/fixture'
            elif name=='eth_syncing':v=False
            elif name=='eth_getBlockByNumber':v={'number':'0x0','hash':hx(GENESIS)} if p[0]=='0x0' else env['el']['0x'+env['points'][index][16:80]]
            elif name=='eth_getBlockByHash':v=env['el'].get(p[0])
            elif name in ('eth_call','eth_getCode'):
                selector=p[-1]
                require(selector.keys()=={'blockHash','requireCanonical'} and selector['requireCanonical'] is True,'STATE_UNAVAILABLE')
                hashes=['0x'+point[16:80] for point in env['points']];where=hashes.index(selector['blockHash'])
                if name=='eth_getCode':v=self.bank['codes'][p[0]]
                else:
                    state=self.mode if where==2 else 'active'
                    v=self.bank['states'][state][p[0]['to']+':'+p[0]['data']]
            else:raise Reject('STATE_UNAVAILABLE')
            result.append(deepcopy(v))
        return result

    def beacon(self, path, timeout):
        require(timeout>0,'STATE_UNAVAILABLE');env=self._current()
        self.log.append((path,None));index=1 if self.mode in ('active','stale') else 2
        if path.endswith('/genesis'):v={'data':dict(genesis_time=str(env['genesis_time']),
            genesis_validators_root=hx(self.binding.cl_genesis_validators_root),
            genesis_fork_version=hx(self.binding.cl_genesis_fork_version))}
        elif path.endswith('/version'):v={'data':{'version':'Lighthouse/v8.3.2-fixture'}}
        elif path.endswith('/syncing'):v={'data':dict(is_syncing=False,sync_distance='0',is_optimistic=False,el_offline=False)}
        elif '/headers/' in path:v=env['headers'][env['roots'][index] if path.endswith('/finalized') else path.rsplit('/',1)[1]]
        elif '/blocks/' in path:v=env['blocks'][path.rsplit('/',1)[1]]
        else:raise Reject('STATE_UNAVAILABLE')
        return deepcopy(v)

    def adapter(self, store):
        adapter=Adapter(self.binding,store)
        adapter.el=adapter.cl=self
        return adapter
