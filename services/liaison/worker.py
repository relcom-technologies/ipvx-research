"""One bounded polling cycle, intended for a systemd timer on the IPvX machine."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent import Ledger, draft, digest
sys.path.insert(0, str(Path(__file__).resolve().parent/'scripts'))
from export_community import sanitize, read, BASE


def atomic_json(path, data, mode=0o600):
    temporary=path.with_suffix('.next')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,mode)
    with os.fdopen(fd,'w') as handle:
        json.dump(data,handle,ensure_ascii=False,indent=2)
        handle.flush();os.fsync(handle.fileno())
    os.chmod(temporary,mode);os.replace(temporary,path)


def cycle(base, public, smoke=False):
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    public.mkdir(parents=True,exist_ok=True,mode=0o755)
    os.chmod(public,0o755)
    config=json.loads((base/'config.json').read_text())
    facts=json.loads((Path(__file__).parent/'facts.json').read_text())
    credentials=os.environ.get('CREDENTIALS_DIRECTORY')
    if credentials:
        for provider,environment in [('openai','IPVX_OPENAI_API_KEY'),('anthropic','IPVX_ANTHROPIC_API_KEY')]:
            os.environ[environment]=(Path(credentials)/('ipvx-'+provider)).read_text().strip()
    ledger=Ledger(base/'ledger.sqlite',config['daily_budget_usd'])
    now=datetime.now(timezone.utc).isoformat()
    status=dict(schema_version=1,project_account='IPvXResearchLiaison',state='running_draft_service',
        updated_at=now,code_revision=os.environ.get('IPVX_LIAISON_REVISION'),
        billing_authorized_usd_per_day=config['daily_budget_usd'],budget_timezone='Europe/Berlin',
        automatic_publication=False,operator_independent=False,local_inference_verified=False,
        models={role:dict(provider=config[role]['provider'],model=config[role]['model']) for role in ('writer','reviewer')})
    try:
        raw=read(BASE+'/comments?sort=new&limit=100');post=read(BASE)
        snapshot=sanitize(raw,(post.get('post')or{}).get('comment_count'))
        atomic_json(public/'community-discussions.json',snapshot,0o644)
        marker=base/'baseline.json'
        if not marker.exists() and not smoke:
            # Never answer the whole historical thread on first deployment.
            # Only the reviewed release snapshot is historical. New comments
            # arriving during deployment remain unseen jobs for the next cycle.
            reviewed=json.loads((Path(__file__).parent/'baseline-snapshot.json').read_text())
            with ledger.connect() as db:
                for comment in reviewed['comments']:
                    identifier=comment['id']+':'+digest(comment['text'])
                    db.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?)',(identifier,digest(comment),'historical',None))
            atomic_json(marker,dict(recorded_at=now,classification='historical_baseline_no_replies'))
        else:
            rows=[row for row in snapshot['comments'] if not row['project_account']]
            if smoke:
                rows=[row for row in rows if row['id']=='45be4b90-6314-4959-87e6-db87c3eb43e8']
            for comment in rows[:1] if smoke else rows:
                identifier=comment['id']+':'+digest(comment['text'])
                with ledger.connect() as db:
                    if db.execute('SELECT 1 FROM jobs WHERE id=?',(identifier,)).fetchone():continue
                result=draft(comment,snapshot,facts,config,ledger)
                folder=base/'drafts';folder.mkdir(mode=0o700,exist_ok=True)
                atomic_json(folder/(digest(identifier)+'.json'),result)
                # One new technical response per cycle; no social publication.
                break
        with ledger.connect() as db:
            completed=db.execute("SELECT COUNT(*) FROM jobs WHERE state='draft'").fetchone()[0]
            failed=db.execute("SELECT COUNT(*) FROM jobs WHERE state='failed'").fetchone()[0]
            day=datetime.now(timezone.utc).astimezone(ledger.zone).date().isoformat()
            reserved=db.execute('SELECT COALESCE(SUM(amount),0) FROM reservations WHERE day=?',(day,)).fetchone()[0]
        status.update(paid_api_run_verified=completed>0,completed_drafts=completed,failed_jobs=failed,
            reserved_usd_today=reserved/1_000_000,source_coverage_complete=False,
            last_source_check=now,smoke=smoke)
    except Exception as error:
        # Exception messages/HTTP bodies may contain operator data. Public status
        # contains only a bounded category; no keys, prompts or private drafts.
        status.update(state='attention_required',error_category=type(error).__name__)
        atomic_json(public/'liaison-status.json',status,0o644)
        print(json.dumps(dict(state=status['state'],error_category=status['error_category'])))
        raise SystemExit(1)
    atomic_json(public/'liaison-status.json',status,0o644)
    print(json.dumps(status))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--public-dir',type=Path,required=True)
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args();cycle(args.state_dir,args.public_dir,args.smoke)
