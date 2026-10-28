"""Project discovery is reachable and never claims nonexistent agent services."""
import json
from pathlib import Path
from urllib.parse import urlsplit
import unittest
from agent_directory import TEXT,render
ROOT=Path(__file__).resolve().parents[1]
class AgentDirectoryTests(unittest.TestCase):
 def test_read_only_descriptor_and_destinations(self):
  d=json.loads((ROOT/'data/agent-discovery.json').read_text())
  schema=json.loads((ROOT/'data/agent-discovery.schema.json').read_text())
  self.assertEqual(d['kind'],'research_project_directory')
  self.assertTrue(set(schema['required'])<=set(d))
  self.assertEqual(set(d['languages']),{'ru','en','de','es'})
  self.assertTrue(d['protocols']['a2a_server_available'])
  self.assertEqual(d['participation']['automated_submission_endpoint'],'https://ipvx.org/a2a')
  self.assertFalse(d['protocols']['mcp_server_available'])
  self.assertFalse(d['protocols']['this_directory_is_an_a2a_agent_card'])
  for capability in ('automated_membership_or_voting','automatic_resource_access'):
   self.assertFalse(d['participation'][capability])
  for resource in d['read_only_resources']:
   u=urlsplit(resource['url']); self.assertEqual((u.scheme,u.netloc),('https','ipvx.org'))
   self.assertTrue((ROOT/u.path.lstrip('/')).is_file(),u.path)
 def test_agent_page_in_four_languages(self):
  for language in ('ru','en','de','es'):
   html=render(language)
   self.assertIn('data/agent-discovery.json',html)
   self.assertIn('participate',html)
   self.assertEqual(len(TEXT[language]),len(TEXT['ru']))
if __name__=='__main__':unittest.main()
