"""Adversarial public registry integrity; no network or production fixtures."""
import copy
import json
from pathlib import Path
import unittest
from research_links import load, render, LANGS

ROOT=Path(__file__).resolve().parents[1]

class ResearchLinksTests(unittest.TestCase):
    def setUp(self): self.data=json.loads((ROOT/'data/research-links.json').read_text())
    def reject(self,edit):
        data=copy.deepcopy(self.data);edit(data)
        with self.assertRaises(ValueError):load(ROOT,data)
    def test_verified_public_chains(self):
        data=load(ROOT);self.assertEqual([c['stage'] for c in data['cases']],['local_preflight','measured'])
        self.assertIn('8.014',data['cases'][1]['result']['en'])
        self.assertIn('No final review',data['cases'][0]['limits']['en'])
    def test_access_labels_are_explicit_and_cannot_hide_a_private_ci_log(self):
        self.reject(lambda d:d['cases'][1]['run'].update(access='public'))
        self.reject(lambda d:d['cases'][0]['run'].update(access='private_repository'))
        self.reject(lambda d:d['cases'][1]['run'].pop('access'))
        for lang in LANGS:
            output=render(ROOT,lang)
            from research_links import COPY
            self.assertIn(COPY['private_run'][LANGS.index(lang)],output)
            self.assertIn(COPY['public_summary'][LANGS.index(lang)],output)
    def test_missing_or_duplicate_references(self):
        self.reject(lambda d:d['cases'].append(d['cases'][0]))
        self.reject(lambda d:d['cases'][0]['source']['comment_ids'].append('missing'))
        self.reject(lambda d:d['cases'][1]['source']['event_ids'].append('HX-9999'))
    def test_private_and_unpinned_sources_rejected(self):
        for url in ['javascript:alert(1)','https://ipvx.org/api/private','https://user:secret@github.com/x','http://127.0.0.1/']:
            self.reject(lambda d:d['cases'][0]['source'].update(url=url))
        self.reject(lambda d:d['cases'][0]['source'].update(kind='private_intake'))
        self.reject(lambda d:d['cases'][1]['source'].update(url='https://github.com/relcom-technologies/ipvx-research/blob/main/history/events.jsonl'))
    def test_evidence_hash_path_and_stage(self):
        self.reject(lambda d:d['cases'][0]['protocol']['artifact'].update(sha256='0'*64))
        self.reject(lambda d:d['cases'][0]['protocol']['artifact'].update(path='docs/../governance.json'))
        self.reject(lambda d:d['cases'][0]['protocol']['artifact'].update(revision='main'))
        self.reject(lambda d:d['cases'][0]['run'].update(classification='independent'))
        self.reject(lambda d:d['cases'][0].update(stage='launched'))
        self.reject(lambda d:d['cases'][1]['run'].update(url='https://example.org/runs/1'))
    def test_schema_and_localization(self):
        self.reject(lambda d:d.update(private_payload='forbidden'))
        self.reject(lambda d:d['cases'][0]['title'].pop('es'))
        self.reject(lambda d:d['cases'][0].update(rfcs=['rfc-9999']))
    def test_language_and_no_javascript_static_access(self):
        for lang in LANGS:
            output=render(ROOT,lang)
            self.assertIn('research-a2a-recovery',output)
            self.assertIn('<noscript>',output)
            self.assertIn('experiment.yml',output)
            self.assertNotIn('<form action=',output)
            compact=render(ROOT,lang,'compact');self.assertNotIn('id="research-draft-form"',compact)
            self.assertIn('matched-transport',render(ROOT,lang,'rfc','rfc-0004'))
            self.assertNotIn('research-index',render(ROOT,lang,'rfc','rfc-0001'))
    def test_hostile_text_is_escaped_in_html_and_payload(self):
        import unittest.mock as mock
        self.data['cases'][0]['title']['ru']='</script><img src=x onerror=alert(1)>'
        with mock.patch('research_links.load',return_value=self.data):output=render(ROOT)
        self.assertNotIn('</script><img',output)
        self.assertIn('&lt;/script&gt;',output)
        self.assertIn('\\u003c/script\\u003e',output)

if __name__=='__main__':unittest.main()
