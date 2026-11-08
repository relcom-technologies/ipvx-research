"""Public facts must match offline evidence and never grant experiment access."""
import json
from pathlib import Path
import unittest
from bcp_project import facts, render, header, ru_count

ROOT=Path(__file__).resolve().parents[1]


class BcpPresentation(unittest.TestCase):
    def test_snapshot_agrees_with_actual_report_and_closed_config(self):
        d=facts(ROOT);c=json.loads((ROOT/'runners/bcp02/launch-config.json').read_text())
        self.assertEqual(d['checks']['runner_tests'],93)
        self.assertIsNone(c['owner_launch_decision']);self.assertIsNone(c['run_dataset'])
        self.assertEqual(d['network_experiment'],'NOT_RUN')

    def test_russian_counts_agree_with_their_number(self):
        forms=('тест','теста','тестов')
        for n,word in [(1,'тест'),(2,'теста'),(4,'теста'),(5,'тестов'),(11,'тестов'),(12,'тестов'),
                       (14,'тестов'),(21,'тест'),(22,'теста'),(63,'теста'),(77,'тестов'),(111,'тестов')]:
            self.assertEqual(ru_count(n,*forms),word,n)
        self.assertIn('93 теста runner и 14 проверок плана.',render(ROOT,'ru'))

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
            self.assertIn('relcom-infra/pull/865',render(ROOT,language))

    def test_status_states_light_client_read_and_open_conditions(self):
        d=facts(ROOT);self.assertFalse(d['state_source']['own_node_required']);self.assertFalse(d['state_source']['helios_running_on_stand'])
        self.assertNotIn('validator_request',d['references'])
        for language in ['ru','en','de','es']:
            with self.subTest(language=language):
                s=render(ROOT,language)
                for name in ['REG-001-LC','S1–S3','NET-001-L','Helios','2026-11-05','2026-11-06']:
                    self.assertIn(name,s)
                self.assertIn('bcp02-reg-001-lc',s)


if __name__=='__main__':unittest.main()
