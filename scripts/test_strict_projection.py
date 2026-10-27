"""Public export must never copy private hop proofs or unknown metadata."""
import json
from pathlib import Path
import tempfile
import unittest
from export_strict_comparison import project


class PublicProjection(unittest.TestCase):
    def test_private_extensions_and_signed_network_metadata_stay_private(self):
        sentinel = 'PRIVATE-METADATA-MUST-NOT-LEAVE'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = dict(frames=1, ethertypes={'88b5': 1}, verified_link_envelopes=1,
                           incomplete_rpc_assemblies=0, pcap_sha256='a'*64, private=sentinel)
            mode = dict(echo={}, task={}, inference={}, correct_decisions=1, tasks=4,
                        signed_deliveries=48, capture_frames=2, verified_link_envelopes=2,
                        captures=[capture], private=sentinel)
            summary = dict(schema_version=1, status='measured', source_revision='b'*40,
                           model_sha256='c'*64, answer_comparison=[], limits=[],
                           modes=dict(native=mode, ip=mode), private=sentinel)
            (root/'verified-summary.json').write_text(json.dumps(summary))
            for run in ('round1-native','round2-native'):
                nodes={}; roster={}
                for name in ('A','B','R1'):
                    files={'environment.json':sentinel}
                    if name=='A':
                        delivery=dict(message_id='d'*32,case=None,phase='echo',bytes=10,
                                      elapsed_ms=1,attempts=1,path=['A','R1','B'],
                                      proof={'signed_network':sentinel}, private=sentinel)
                        task=dict(case='delivery',claim='Fixed public case',expected='yes',
                                  final={'decision':'yes'},decision_correct=True,elapsed_ms=2,private=sentinel)
                        files.update({'deliveries.jsonl':'\n'.join([json.dumps(delivery)]*24),
                                      'results.jsonl':'\n'.join([json.dumps(task)]*2)})
                    nodes[name]={'files':files}
                    roster[name]={'payload':dict(id='agent-public-id',public_key='e'*64,endpoint=sentinel)}
                    folder=root/run/name;folder.mkdir(parents=True)
                    (folder/'adapter-summary.json').write_text(json.dumps(dict(out=1, private=sentinel)))
                (root/(run+'.json')).write_text(json.dumps(dict(nodes=nodes,roster=roster,private=sentinel)))
            exported=project(root)
            self.assertNotIn(sentinel,json.dumps(exported))
            self.assertEqual(len(exported['deliveries']),48)
            self.assertEqual(exported['adapter_transmissions'],6)


if __name__=='__main__':unittest.main()
