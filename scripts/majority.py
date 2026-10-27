"""GitHub-authenticated comments; latest vote per eligible member, no model votes."""
import datetime,json,re

def tally(roster,comments,opened_at,now):
    eligible=set(roster['eligible']);votes={}
    if not eligible:raise ValueError('Empty roster')
    opened=datetime.datetime.fromisoformat(opened_at.replace('Z','+00:00'))
    if opened.tzinfo is None or now.tzinfo is None:raise ValueError('Timezone required')
    close=opened+datetime.timedelta(hours=roster['window_hours'])
    for c in sorted(comments,key=lambda x:(x['created_at'],x['id'])):
        who=c['user']['login'];body=c['body'].strip()
        created=datetime.datetime.fromisoformat(c['created_at'].replace('Z','+00:00'))
        updated=datetime.datetime.fromisoformat(c.get('updated_at',c['created_at']).replace('Z','+00:00'))
        if who in eligible and c['user'].get('type')=='User' and opened<=created<=close and updated<=close:
            m=re.fullmatch(r'/vote\s+(yes|no|abstain)',body)
            if m:votes[who]=m[1]
    required=len(eligible)//2+1;yes=sum(v=='yes' for v in votes.values())
    return {'eligible':len(eligible),'required':required,'yes':yes,'no':sum(v=='no' for v in votes.values()),'votes':votes,'closed':now>=close,'approved':now>=close and yes>=required,'deadline':close.isoformat()}

if __name__=='__main__':
 import sys
 roster=json.load(open(sys.argv[1]));issue=json.load(open(sys.argv[2]));comments=json.load(open(sys.argv[3]));print(json.dumps(tally(roster,comments,issue['created_at'],datetime.datetime.now(datetime.timezone.utc)),ensure_ascii=False))
