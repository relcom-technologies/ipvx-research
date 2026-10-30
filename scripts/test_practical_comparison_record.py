"""Public signature/paired-summary projection; absent raw pcaps are not reverified."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from cryptography.exceptions import InvalidSignature
from test_reproduction_record import verify

ROOT=Path(__file__).resolve().parents[1]


def hashed(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


class PracticalComparisonRecord(unittest.TestCase):
    def setUp(self):
        self.record=json.loads((ROOT/'docs/practical-comparison-2026-10-30.json').read_text())
        self.folder=ROOT/self.record['artifacts']['public_projection']
        self.key=self.record['CI_operator']['public_key']

    def test_signed_scope_source_and_exact_projection(self):
        r=self.record
        self.assertEqual({p.name for p in self.folder.iterdir()},{'session.json','report.json','protocol.json'})
        for entry in r['artifacts']['JSON_files']:
            self.assertEqual(hashlib.sha256((self.folder/entry['name']).read_bytes()).hexdigest(),entry['sha256'])
        signed_session=json.loads((self.folder/'session.json').read_text())
        session=verify(signed_session,self.key,'practical-session/1')
        report=verify(json.loads((self.folder/'report.json').read_text()),self.key,'practical-result/1')
        protocol=json.loads((self.folder/'protocol.json').read_text())
        self.assertEqual(session['source']['files']['experiments/practical-benefit/protocol.json'],
                         hashlib.sha256((self.folder/'protocol.json').read_bytes()).hexdigest())
        self.assertEqual(session['protocol'],protocol)
        self.assertEqual(session['protocol_sha256'],hashed(protocol))
        self.assertEqual(report['protocol_sha256'],session['protocol_sha256'])
        self.assertEqual(report['session_sha256'],hashed(signed_session))
        self.assertEqual(session['source']['revision'],r['measured_revision'])
        self.assertEqual(report['source_sha256'],hashed(session['source']['files']))
        self.assertEqual(report['status'],'measured');self.assertIsNone(report['failure'])
        self.assertFalse(report['production']);self.assertEqual(report['independent_operator'],'not_established')
        expected=[(scenario,pair,arm) for scenario in protocol['scenarios'] for pair in range(5)
                  for arm in (protocol['arms'] if pair%2==0 else list(reversed(protocol['arms'])))]
        self.assertEqual(session['order'],[list(x) for x in expected])
        self.assertEqual([(r['scenario'],r['pair'],r['arm']) for r in report['runs']],expected)
        self.assertEqual(len(report['files']),40)
        self.assertFalse(any(self.folder.glob('*.pcap')))
        self.assertEqual(report['comparison'],r['comparison'])

    def test_screening_threshold_and_ratios_recompute_without_claiming_superiority(self):
        report=verify(json.loads((self.folder/'report.json').read_text()),self.key,'practical-result/1')
        for group in report['comparison']:
            eligible=True;pairs=[]
            for pair in range(5):
                arms={x['arm']:x['metrics'] for x in report['runs'] if x['scenario']==group['scenario'] and x['pair']==pair}
                eligible=eligible and all(m['correct']==40 and m['duplicate_executions']==0 and m['duplicate_replays_equal'] for m in arms.values())
                ratios={k:None if arms['native'][k] is None or not arms['tcp-http'][k] else arms['native'][k]*1000000//arms['tcp-http'][k]
                        for k in ('p95_us','work_wire_bytes','cpu_us','sum_peak_rss_kib','work_us','recovery_us')}
                pairs.append(ratios)
            for k,value in group['median_ratios_ppm'].items():
                self.assertEqual(value,sorted(x[k] for x in pairs)[2] if all(x[k] is not None for x in pairs) else None)
            med=group['median_ratios_ppm']
            signal=eligible and any(med[k] is not None and med[k]<=800000 for k in ('p95_us','work_wire_bytes'))
            self.assertEqual(group['screening_signal'],signal)
            self.assertEqual(group['all_pairs_eligible'],eligible)
            self.assertEqual(group['practical_superiority'],'not_established')

    def test_wrong_key_tamper_and_domain_do_not_authenticate(self):
        signed=json.loads((self.folder/'report.json').read_text());changed=copy.deepcopy(signed)
        changed['payload']['production']=True
        with self.assertRaises(InvalidSignature): verify(changed,self.key,'practical-result/1')
        with self.assertRaises(InvalidSignature): verify(signed,'0'*64,'practical-result/1')
        with self.assertRaises(ValueError): verify(signed,self.key,'reproduction-result/1')


if __name__=='__main__': unittest.main()
