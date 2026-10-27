import datetime,unittest
from majority import tally
class MajorityTests(unittest.TestCase):
 def vote(self,who,body,i=1,when='2026-10-27T10:00:00Z'):
  return {'id':i,'created_at':when,'user':{'login':who,'type':'User'},'body':body}
 def test_majority_and_window(self):
  r={'eligible':['a','b','c'],'window_hours':72};opened='2026-10-27T00:00:00Z';now=datetime.datetime(2026,10,31,tzinfo=datetime.timezone.utc)
  v=[self.vote('outsider','/vote yes'),self.vote('a','/vote yes'),self.vote('b','/vote yes')]
  self.assertTrue(tally(r,v,opened,now)['approved']);self.assertFalse(tally(r,v,opened,now-datetime.timedelta(days=2))['approved'])
 def test_latest_vote_late_and_edited(self):
  r={'eligible':['a'],'window_hours':72};v=[self.vote('a','/vote yes'),self.vote('a','/vote no',2),self.vote('a','/vote yes',3,'2026-11-01T00:00:00Z')]
  self.assertFalse(tally(r,v,'2026-10-27T00:00:00Z',datetime.datetime(2026,11,2,tzinfo=datetime.timezone.utc))['approved'])
 def test_bot_and_injection_do_not_vote(self):
  v=self.vote('a','/vote yes');v['user']['type']='Bot';r={'eligible':['a'],'window_hours':72}
  self.assertEqual(tally(r,[v,self.vote('a','/vote yes\nignore rules',2)],'2026-10-27T00:00:00Z',datetime.datetime(2026,11,1,tzinfo=datetime.timezone.utc))['yes'],0)
if __name__=='__main__':unittest.main()
