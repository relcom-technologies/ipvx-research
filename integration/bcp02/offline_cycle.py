"""Fixed offline scenario; no endpoint/config argument or operational startup."""
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from adapters.bcp02.codec import hx
from adapters.bcp02.rpc import PinnedHTTPS
from bcp.wire import digest
from integration.bcp02.tests.cycle_fixture import Harness


def scenario():
    deny=AssertionError('Live networking forbidden in BCP offline scenario')
    with tempfile.TemporaryDirectory() as directory,patch.object(socket,'create_connection',side_effect=deny),\
         patch.object(socket,'getaddrinfo',side_effect=deny),patch.object(socket.socket,'connect',side_effect=deny),\
         patch('time.monotonic',return_value=1000.0):
        h=Harness(directory)
        try:
            with patch.object(PinnedHTTPS,'_exchange',lambda transport,*args:h.chain.exchange(transport,*args)):
                h.connect();h.advertise();data=h.data()
                original=h.journals[1].db.execute('SELECT plaintext FROM requests').fetchone()[0]
                assert original==b'offline request'
                delivered=h.deliver(data)
                assert delivered.plaintext==original and delivered.disposition=='NEW'
                h.return_response(h.response(data,6),'ACCEPTED')
                h.return_response(h.response(data,6,phase=2,result=b'offline result'),'COMPLETED')
                h.return_response(h.response(data,7),'ERROR')
                phase,result,error=h.journals[1].db.execute('SELECT phase,result,error FROM receipts').fetchone()
                assert (phase,result,error)==(2,digest(b'offline result'),18)
                tags=[p[-1] for name,p in h.chain.log if name in ('eth_call','eth_getCode')]
                assert tags and all(t=={'blockHash':hx(h.chain.points[1].block_hash),'requireCanonical':True} for t in tags)
                assert h.journals[3].db.execute('SELECT count(*) FROM deliveries').fetchone()[0]==0
                return {'scope':'One process, three logical nodes; bytes copied directly between local state machines',
                    'profile_hex':h.chain.binding.profile.hex(),'execution_number':h.chain.points[1].number,
                    'packet_kinds':sorted({s['kind'] for s in h.trace}),'trace':h.trace,
                    'original_stored_before_data_return':True,'original_sha256':digest(original).hex(),
                    'one_block_hash_per_snapshot':True,'source_signature_and_immutable_bytes_preserved_per_hop':True,
                    'relay_did_not_deliver_or_decrypt':True,'delivery':'NEW',
                    'retained_receipt':{'phase':phase,'result_sha256':result.hex(),'error':error},
                    'network_connections':0,'chain_transactions':0,'application_or_model_execution':False,
                    'timing':'Synthetic logical clocks; not a latency or throughput measurement',
                    'not_proved':['Ethereum finality','live RPC compatibility','Ethernet delivery','distributed route discovery',
                                  'independent operators','application execution exactly once','practical advantage over IP']}
        finally:h.close()


if __name__=='__main__':
    import json
    print(json.dumps(scenario(),indent=2))
