"""Verify the exact public JSON projection without claiming to verify an absent pcap."""
import copy,hashlib,json,unittest
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
ROOT=Path(__file__).resolve().parents[1]


def verify(envelope,key,purpose):
    if set(envelope)!={'wire','purpose','payload','signature'} or envelope['wire']!='ipvx-agent-lab/1' or envelope['purpose']!=purpose:raise ValueError('Wrong evidence domain')
    body={k:envelope[k] for k in ('wire','purpose','payload')}
    wire=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(bytes.fromhex(envelope['signature']),wire)
    return envelope['payload']


class ReproductionRecord(unittest.TestCase):
    def setUp(self):
        self.record=json.loads((ROOT/'docs/reproduction-kit-2026-10-30.json').read_text())
        self.folder=ROOT/self.record['artifacts']['public_projection']
        self.key=self.record['CI_operator']['public_key']

    def test_public_projection_preserves_signatures_and_exact_artifact_bindings(self):
        expected={'session.json','result.json','report.json','observations.json','comparison.json'}
        self.assertEqual({p.name for p in self.folder.iterdir()},expected)
        for entry in self.record['artifacts']['JSON_files']:
            self.assertEqual(hashlib.sha256((self.folder/entry['name']).read_bytes()).hexdigest(),entry['sha256'])
        session=verify(json.loads((self.folder/'session.json').read_text()),self.key,'reproduction-session/1')
        result=verify(json.loads((self.folder/'result.json').read_text()),self.key,'reproduction-result/1')
        self.assertEqual(result['session_sha256'],hashlib.sha256((self.folder/'session.json').read_bytes()).hexdigest())
        self.assertEqual(result['kit_sha256'],self.record['kit_sha256'])
        self.assertEqual(session['kit_sha256'],result['kit_sha256'])
        self.assertEqual(set(result['files']),{'report.json','observations.json','frames.pcap'})
        for name in ('report.json','observations.json'):
            self.assertEqual(result['files'][name],hashlib.sha256((self.folder/name).read_bytes()).hexdigest())
        report=json.loads((self.folder/'report.json').read_text())
        self.assertEqual(result['files']['frames.pcap'],report['capture_sha256'])
        self.assertEqual(report['spec_sha256'],self.record['original_spec_sha256'])
        self.assertFalse((self.folder/'frames.pcap').exists())
        compared=json.loads((self.folder/'comparison.json').read_text())
        self.assertEqual(compared['independent_operator'],'not_established')
        self.assertTrue(compared['requires_owner_review'])
        self.assertEqual(compared['repeated_metrics'],report['metrics'])

    def test_modified_signature_or_another_test_key_is_not_accepted(self):
        signed=json.loads((self.folder/'result.json').read_text());changed=copy.deepcopy(signed)
        changed['payload']['kit_sha256']='0'*64
        with self.assertRaises(InvalidSignature):verify(changed,self.key,'reproduction-result/1')
        with self.assertRaises(InvalidSignature):verify(signed,'0'*64,'reproduction-result/1')
        with self.assertRaises(ValueError):verify(signed,self.key,'participant-execution')


if __name__=='__main__':unittest.main()
