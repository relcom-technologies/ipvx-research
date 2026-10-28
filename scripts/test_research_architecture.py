"""The diagram must track evidence and remain inspectable in every edition."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from research_architecture import TEXT,check_evidence,render
from research_contributions import TEXT as CONTRIBUTIONS,render as render_contribution

ROOT=Path(__file__).resolve().parents[1]
class ArchitectureTests(unittest.TestCase):
 def test_current_diagram_tracks_record_and_languages(self):
  d=json.loads((ROOT/'data/strict-agents-round.json').read_text())
  check_evidence(ROOT)
  for language in ('ru','en','de','es'):
   page=render(ROOT,language)
   self.assertIn(d['source_revision'][:12],page)
   self.assertEqual(page.count('class="net-machine"'),3)
   self.assertEqual(page.count('class="net-stage"'),4)
   self.assertIn(str(d['modes']['native']['signed_deliveries']),page)
   self.assertIn('data-net-play',page)
   self.assertIn('#join-form',render_contribution(language))
   self.assertEqual(set(TEXT[language]),set(TEXT['ru']))
   self.assertEqual(len(CONTRIBUTIONS[language]),len(CONTRIBUTIONS['ru']))
 def test_changed_evidence_blocks_stale_diagram(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);shutil.copytree(ROOT/'data',root/'data')
   (root/'data/scale-summary.json').write_text('{}')
   with self.assertRaisesRegex(ValueError,'Architecture needs review'):
    check_evidence(root)
if __name__=='__main__':unittest.main()
