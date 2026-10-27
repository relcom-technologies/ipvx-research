"""Labels communicate a research vote, never grant permissions or deploy code."""
import datetime,json,os,subprocess
from majority import tally
repo=os.environ['REPO']
def gh(*args):return subprocess.check_output(['gh',*args],text=True)
def api(path):return json.loads(gh('api',path))
# Complete pagination, rather than allowing a truncated electorate/late vote.
def pages(path):
 result=[]
 for page in range(1,101):
  chunk=api(path+('&' if '?' in path else '?')+f'per_page=100&page={page}');result.extend(chunk)
  if len(chunk)<100:return result
 raise RuntimeError('Pagination exceeds bound; fail closed')
import base64,urllib.parse
for issue in pages(f'repos/{repo}/issues?state=open&labels=proposal'):
 if 'pull_request' in issue:continue
 commits=api(f'repos/{repo}/commits?path=governance.json&until='+urllib.parse.quote(issue['created_at'])+'&per_page=1')
 if not commits:raise RuntimeError('No electorate at proposal opening; fail closed')
 frozen=api(f'repos/{repo}/contents/governance.json?ref='+commits[0]['sha'])
 roster=json.loads(base64.b64decode(frozen['content']))
 result=tally(roster,pages(f'repos/{repo}/issues/{issue["number"]}/comments'),issue['created_at'],datetime.datetime.now(datetime.timezone.utc))
 label='majority-approved' if result['approved'] else 'majority-not-approved' if result['closed'] else 'vote-open'
 existing={x['name'] for x in issue['labels']}
 for stale in existing & {'majority-approved','majority-not-approved','vote-open'}-{label}:
  gh('api','--method','DELETE',f'repos/{repo}/issues/{issue["number"]}/labels/{stale}')
 gh('api','--method','POST',f'repos/{repo}/issues/{issue["number"]}/labels','-f',f'labels[]={label}')
 print(json.dumps({'issue':issue['number'],**result}))
