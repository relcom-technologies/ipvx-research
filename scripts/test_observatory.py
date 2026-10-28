"""Evidence linkage, disclosure completeness and language parity."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from observatory import TEXT, make_manifest, render
from export_observatory_inputs import export

ROOT=Path(__file__).resolve().parents[1]


class Observatory(unittest.TestCase):
    def test_manifest_counts_and_unknowns(self):
        data=make_manifest(ROOT)
        self.assertEqual(data['declared_scope']['native_deliveries'],48)
        self.assertEqual(data['declared_scope']['native_echoes'],40)
        self.assertEqual(data['declared_scope']['native_tasks'],4)
        self.assertEqual(data['declared_scope']['native_measured_inferences'],12)
        self.assertEqual(data['coverage']['causal_task_id'],'not_recorded')
        self.assertEqual(data['coverage']['per_hop_timing'],'not_recorded_publicly')
        self.assertEqual(data['coverage']['event_collector_loss'],'not_established')

    def test_each_task_has_real_three_inferences_two_distinct_messages(self):
        source=json.loads((ROOT/'data/strict-agents-round.json').read_text())
        for task in source['tasks']:
            case=task['case']
            inferences=[x for x in source['inferences'] if x['case']==case]
            self.assertEqual({(x['node'],x['phase']) for x in inferences},{('A','draft'),('B','review'),('A','final')})
            messages=[x for x in source['deliveries'] if x['case']==case]
            self.assertEqual({x['phase'] for x in messages},{'review','final'})
            self.assertEqual(len({x['message_id'] for x in messages}),2)
            self.assertEqual(len({x['run'] for x in inferences}),1)

    def test_all_four_languages_render_four_tasks_and_node_disclosures(self):
        for language in TEXT:
            self.assertEqual(set(TEXT[language]),set(TEXT['ru']))
            html=render(ROOT,language)
            self.assertEqual(html.count('class="obs-case"'),4)
            self.assertEqual(html.count('class="obs-node"'),3)
            self.assertEqual(html.count('class="obs-step"'),28)
            self.assertIn('d5cb8cd8c779483197db58de1f848aba',html)
            self.assertIn('9c769a29e5e142e190e04cb1a326027e',html)
            self.assertNotIn('10.10.50.',html)

    def test_case_source_mismatch_refused(self):
        public=json.loads((ROOT/'data/strict-agents-round.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bad=copy.deepcopy(public)
            bad['tasks'][0]['claim']='Altered claim'
            (root/'public.json').write_text(json.dumps(bad))
            for run in ('round1-native','round2-native'):
                (root/(run+'.json')).write_text(json.dumps(dict(revision=bad['source_revision'],mode='native',cases=[dict(id='delivery',claim='Original claim',expected='yes',a=['A1'],b=['B1'])])))
            with self.assertRaises(AssertionError):export(root,root/'public.json')


if __name__=='__main__':unittest.main()
