"""One zero-transaction read of REG-001 run 6 through a local Helios (mode LC).

Compares the verified finalized state with expected.json and writes one result file.
There is no retry and no signing path: this script holds no keys and sends no
transactions. It assumes Helios is already running as the README says.
"""
from argparse import ArgumentParser
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]))

from bcp.wire import Reject
from adapters.bcp02.binding import Selection
from adapters.bcp02.codec import execution_header,hexdata,hx
from adapters.bcp02.store import Store
from lightclient.bcp02.light import HELIOS_VERSION,LightAdapter,LightBinding,LoopbackEndpoint,LoopbackHTTP

PASS,FAIL_STATE,BLOCKED='PASS','FAIL_STATE','BLOCKED'
TIMEOUT=30


def selection_of(protocol):
    s=protocol['selection']
    return Selection(tuple(s['nfts']),tuple(hexdata(s['edges'][n]) for n in s['edges']),
                     tuple(hexdata(s['connections'][n]) for n in s['connections']))


def binding_of(protocol, bootstrap, checkpoint, binary_sha256):
    c=protocol['contracts'];h=protocol['helios']
    return LightBinding(LoopbackEndpoint(h['endpoint']),tuple(hexdata(a) for a in c['addresses']),
                        tuple(hexdata(x) for x in c['runtime_keccak256']),checkpoint,bootstrap,binary_sha256,
                        HELIOS_VERSION,h['execution_rpc'],h['consensus_rpc'])


def bootstrap_point(protocol):
    """A point behind the verified head, so the read exercises the EIP-2935 ancestry lookup."""
    transport=LoopbackHTTP(LoopbackEndpoint(protocol['helios']['endpoint']))
    try:
        head,_=execution_header(transport.batch([('eth_getBlockByNumber',['finalized',False])],TIMEOUT)[0])
        number=head.number-protocol['helios']['bootstrap_blocks_behind_head']
        return execution_header(transport.batch([('eth_getBlockByNumber',[hex(number),False])],TIMEOUT)[0])[0]
    except (KeyError,TypeError,ValueError):raise Reject('STATE_UNAVAILABLE') from None


def observed(snapshot, protocol):
    s=protocol['selection'];edges={hexdata(v):k for k,v in s['edges'].items()}
    connections={hexdata(v):k for k,v in s['connections'].items()}
    return {'nodes':{str(n.nft):[hx(n.owner),str(n.epoch),hx(n.signing_key),hx(n.encryption_key),str(n.status),str(n.roles)]
                     for n in snapshot.nodes.values()},
            'edges':{edges[e.rule]:[str(v) for v in (e.source,e.destination,e.version,e.source_epoch,e.destination_epoch,
                                                     e.cost,e.max_ciphertext,e.traffic_mask,e.status)]
                     for e in snapshot.edges.values()},
            'connections':{connections[c.rule]:[str(v) for v in (c.source,c.destination,c.version,c.source_epoch,
                                                                 c.destination_epoch,c.traffic_mask,c.max_hops,
                                                                 c.max_ciphertext,c.status)]
                           for c in snapshot.connections.values()},
            'allowed_edges':{connections[c.rule]:sorted(edges[e] for e in c.allowed_edges)
                             for c in snapshot.connections.values()}}


def compare(expected, seen):
    """Every differing, missing or extra value; an empty list is the only match."""
    differences=[]
    for section in ('nodes','edges','connections','allowed_edges'):
        want,got=expected[section],seen[section]
        for name in sorted(set(want)|set(got)):
            if want.get(name)!=got.get(name):
                differences.append({'path':section+'.'+name,'expected':want.get(name),'observed':got.get(name)})
    return differences


def read(protocol, expected, checkpoint, binary_sha256, store_path, *, now=time.time):
    """Return a result dict. A Reject is a blocked read, never a state verdict."""
    result={'protocol_id':protocol['protocol_id'],'read_mode':'LC','transactions_sent':0,'outcome':BLOCKED,
            'checkpoint':hx(checkpoint),'helios_binary_sha256':binary_sha256.hex(),'client_version':HELIOS_VERSION,
            'execution_rpc':protocol['helios']['execution_rpc'],'consensus_rpc':protocol['helios']['consensus_rpc']}
    try:
        bootstrap=bootstrap_point(protocol)
        binding=binding_of(protocol,bootstrap,checkpoint,binary_sha256)
        store=Store(store_path,binding.fingerprint)
        try:
            bundle=LightAdapter(binding,store).read(selection_of(protocol),now=int(now()),clock_trusted=True)
        finally:store.close()
    except Reject as reject:
        result['reject']=reject.code
        return result
    latest=bundle.view.latest;seen=observed(latest,protocol);differences=compare(expected,seen)
    result.update(outcome=FAIL_STATE if differences else PASS,differences=differences,observed=seen,
                  block={'number':latest.checkpoint.number,'hash':hx(latest.checkpoint.block_hash),
                         'state_root':hx(latest.checkpoint.state_root),'timestamp':latest.checkpoint.timestamp},
                  bootstrap_block=bootstrap.number,profile=hx(binding.profile),binding_fingerprint=hx(binding.fingerprint),
                  request_count=bundle.request_count)
    return result


def file_sha256(path):
    return sha256(Path(path).read_bytes()).digest()


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',required=True,help='beacon root that two operators confirmed, the one given to Helios')
    parser.add_argument('--helios-tarball',required=True)
    parser.add_argument('--helios-binary',required=True)
    parser.add_argument('--clock-synchronized',action='store_true',required=True,help='the operator checked NTP on this host')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    protocol=json.loads((HERE/'protocol.json').read_text());expected=json.loads((HERE/'expected.json').read_text())
    output=Path(args.output)
    if output.exists():parser.error('one read, one result: the output file already exists')
    if file_sha256(args.helios_tarball).hex()!=protocol['helios']['release_tarball_sha256']:parser.error('release tarball hash differs')
    started=datetime.now(timezone.utc).isoformat(timespec='seconds')
    with tempfile.TemporaryDirectory() as directory:
        result=read(protocol,expected,hexdata(args.checkpoint),file_sha256(args.helios_binary),Path(directory)/'light.sqlite')
    result.update(started_at=started,ended_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(result['outcome'],result.get('reject',''),len(result.get('differences',[])))
    return {PASS:0,FAIL_STATE:1,BLOCKED:2}[result['outcome']]


if __name__=='__main__':
    sys.exit(main())
