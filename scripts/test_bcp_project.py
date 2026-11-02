"""Public facts must match offline evidence and never grant experiment access."""
import json
from pathlib import Path
import unittest
from bcp_project import facts, render, header

ROOT=Path(__file__).resolve().parents[1]


class BcpPresentation(unittest.TestCase):
    def test_snapshot_agrees_with_actual_report_and_closed_config(self):
        d=facts(ROOT);c=json.loads((ROOT/'runners/bcp02/launch-config.json').read_text())
        self.assertEqual(d['checks']['runner_tests'],63)
        self.assertIsNone(c['owner_launch_decision']);self.assertIsNone(c['run_dataset'])
        self.assertEqual(d['network_experiment'],'NOT_RUN')

    def test_all_languages_distinguish_three_evidence_states(self):
        for language in ['ru','en','de','es']:
            with self.subTest(language=language):
                s=header(language)+render(ROOT,language)
                self.assertEqual(s.count('class="bcp-row"'),3)
                for name in ['NodeRegistry','TransitPolicy','ConnectionPolicy','dataset_sha256','expires_at','veth']:
                    self.assertIn(name,s)
                self.assertIn('https://lab.ipvx.org/#mesh',s)
                self.assertNotIn('<form',s);self.assertNotIn('<button',s)
                if language!='ru':self.assertNotRegex(s,'[А-Яа-яЁё]')

    def test_compact_view_links_to_full_document_and_keeps_pending_state(self):
        for language in ['ru','en','de','es']:
            s=render(ROOT,language,compact=True)
            self.assertIn('bcp'+('' if language=='ru' else '.'+language)+'.html',s)
            self.assertEqual(s.count('class="bcp-row"'),3)
            self.assertIn('pull/845',render(ROOT,language))


if __name__=='__main__':unittest.main()
