"""One bounded polling cycle, intended for a systemd timer on the IPvX machine."""
import argparse
import fcntl
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent import Ledger, BudgetError, draft, digest, job_key, validate_config, parse_reply
sys.path.insert(0,str(Path(__file__).resolve().parent))
import public_sources
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
    config=json.loads(Path(os.environ.get('IPVX_LIAISON_CONFIG_PATH',base/'config.json')).read_text())
    facts=json.loads((Path(__file__).parent/'facts.json').read_text())
    credentials=os.environ.get('CREDENTIALS_DIRECTORY')
    if credentials:
        for provider,environment in [('openai','IPVX_OPENAI_API_KEY'),('anthropic','IPVX_ANTHROPIC_API_KEY')]:
            os.environ[environment]=(Path(credentials)/('ipvx-'+provider)).read_text().strip()
    ledger=Ledger(base/'ledger.sqlite',config['daily_budget_usd'])
    now=datetime.now(timezone.utc).isoformat()
    generation=bool(config.get('generation_enabled'))
    retry_id=os.environ.get('IPVX_LIAISON_RETRY_ID') if smoke else None
    status=dict(schema_version=1,project_account='IPvXResearchLiaison',state='running_draft_service' if generation else 'reading_only',
        updated_at=now,code_revision=os.environ.get('IPVX_LIAISON_REVISION'),
        billing_authorized_usd_per_day=config['daily_budget_usd'],budget_timezone='Europe/Berlin',
        automatic_publication=False,generation_enabled=generation,operator_independent=False,local_inference_verified=False,
        models={role:dict(provider=config[role]['provider'],model=config[role]['model']) for role in ('writer','reviewer')},
        smoke_verified_current=False)
    try:
        source_coverage={}
        try:
            raw=read(BASE+'/comments?sort=new&limit=100');post=read(BASE)
            mirror=sanitize(raw,(post.get('post')or{}).get('comment_count'))
            atomic_json(public/'community-discussions.json',mirror,0o644)
            source_coverage['moltbook']=dict(checked=True,**mirror['coverage'])
        except Exception:
            mirror=dict(comments=[],coverage=dict(complete=False))
            source_coverage['moltbook']=dict(checked=False,complete=False,code='public_source_unavailable')
        extra=[]
        if config.get('extra_public_sources_enabled'):
            extra,coverage=public_sources.collect(config.get('github_project_account'));source_coverage.update(coverage)
        snapshot=dict(comments=sorted(mirror['comments']+extra,key=lambda x:(x.get('created_at') or '',x['id'])),coverage=source_coverage)
        atomic_json(base/'source-snapshot.json',snapshot)
        marker=base/('baseline-v2.json' if config.get('analysis_schema_version')==2 else 'baseline.json')
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
        elif smoke or generation:
            if not smoke:
                ready_path=base/'paired-readiness.json'
                ready=json.loads(ready_path.read_text()) if ready_path.exists() else {}
                if (ready.get('code_revision') != status['code_revision']
                        or ready.get('model_config_sha256') != model_config_hash(config)):
                    raise BudgetError('current_pair_verification_required')
                if (base/'provider-block.json').exists():
                    raise BudgetError('provider_prerequisite_requires_owner')
            validate_config(config)
            if undelivered_count(ledger)>=50:raise BudgetError('proposal_delivery_backpressure')
            rows=[row for row in snapshot['comments'] if not row['project_account']]
            if smoke:
                rows=[row for row in rows if row['id']=='651b962b-391d-4ba1-8dca-8f679cdfb91b']
                if not rows:raise ValueError('review_only_smoke_source_unavailable')
            for comment in rows[:1] if smoke else rows:
                identifier=job_key(comment,retry_id)
                with ledger.connect() as db:
                    if db.execute('SELECT 1 FROM jobs WHERE id=?',(identifier,)).fetchone():
                        if smoke:raise ValueError('smoke_attempt_already_recorded_use_explicit_new_retry')
                        continue
                if not ledger.pair_available(config):
                    status['budget_paused']=True
                    break
                result=draft(comment,snapshot,facts,config,ledger,operator_retry_id=retry_id)
                folder=base/'drafts';folder.mkdir(mode=0o700,exist_ok=True)
                atomic_json(folder/(digest(identifier)+'.json'),result)
                if smoke:
                    status['smoke_verified_current']=(result['status']=='draft_only' and result['published'] is False and
                        len(result['models'])==2 and all(trace['provider']==config[role]['provider'] and
                        trace['requested_model']==config[role]['model'] and trace['actual_model']==config[role]['model']
                        for role,trace in zip(('writer','reviewer'),result['models'],strict=True)))
                    status['smoke_attempt_sha256']=digest(retry_id)
                    if status['smoke_verified_current']:
                        atomic_json(base/'paired-readiness.json',dict(code_revision=status['code_revision'],
                            model_config_sha256=model_config_hash(config),recorded_at=now,
                            smoke_attempt_sha256=digest(retry_id),models=result['models']))
                        with ledger.connect() as db:
                            db.execute('INSERT OR IGNORE INTO jobs VALUES(?,?,?,?)',
                                (job_key(comment),digest(comment),'handled_by_operator_smoke',
                                    json.dumps({'operator_job':result['job_id']})))
                        blocked=base/'provider-block.json'
                        if blocked.exists():blocked.rename(base/('provider-block-archived-'+digest(retry_id)+'.json'))
                # One new technical response per cycle; no social publication.
                break
        with ledger.connect() as db:
            completed=db.execute("SELECT COUNT(*) FROM jobs WHERE state='draft'").fetchone()[0]
            failed=db.execute("SELECT COUNT(*) FROM jobs WHERE state='failed'").fetchone()[0]
            day=datetime.now(timezone.utc).astimezone(ledger.zone).date().isoformat()
            reserved=db.execute('SELECT COALESCE(SUM(amount),0) FROM reservations WHERE day=?',(day,)).fetchone()[0]
        status.update(paid_api_run_verified=completed>0,completed_drafts=completed,failed_jobs=failed,
            reserved_usd_today=reserved/1_000_000,source_coverage_complete=False,
            source_coverage=source_coverage,last_source_check=now,smoke=smoke)
    except Exception as error:
        # Exception messages/HTTP bodies may contain operator data. Public status
        # contains only a bounded category; no keys, prompts or private drafts.
        if getattr(error,'status_code',None) in (400,401,402,403,429):
            atomic_json(base/'provider-block.json',dict(recorded_at=now,
                error_category='provider_prerequisite',http_status=error.status_code))
        reason=str(error) if isinstance(error,BudgetError) else type(error).__name__
        status.update(state='attention_required',error_category=type(error).__name__,pause_reason=reason)
        export_notifications(base,ledger,status,facts,config)
        atomic_json(public/'liaison-status.json',status,0o644)
        print(json.dumps(dict(state=status['state'],error_category=status['error_category'])))
        raise SystemExit(1)
    export_notifications(base,ledger,status,facts,config)
    atomic_json(public/'liaison-status.json',status,0o644)
    print(json.dumps(status))


def model_config_hash(config):
    return digest({k:config[k] for k in ('writer','reviewer','max_output_tokens','daily_budget_usd','analysis_schema_version') if k in config})


def acknowledged():
    path=Path('/var/lib/ipvx-agent-mail-ack/ack.json')
    if not path.exists():return set()
    info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0
            or stat.S_IMODE(info.st_mode)!=0o640 or info.st_size>16*1024*1024):
        raise ValueError('mail_ack_permissions')
    value=json.loads(path.read_text())
    if value.get('schema_version')!=1 or not isinstance(value.get('accepted_ids'),list):raise ValueError('mail_ack_schema')
    return set(value['accepted_ids'])


def undelivered_count(ledger):
    accepted=acknowledged()
    with ledger.connect() as db:
        return sum(digest(row[0]) not in accepted for row in db.execute("SELECT id FROM jobs WHERE state='draft'"))


def export_notifications(base,ledger,status,facts,config):
    """Private validated drafts only; no raw prompts, keys or private A2A input."""
    ready=[];accepted=acknowledged()
    with ledger.connect() as db:
        rows=[]
        for row in db.execute("SELECT id,result FROM jobs WHERE state='draft' ORDER BY rowid"):
            if digest(row[0]) not in accepted:
                rows.append(row)
                if len(rows)>=50:break
    folder=base/'drafts';folder.mkdir(mode=0o700,exist_ok=True)
    for identifier,raw in reversed(rows):
        result=json.loads(raw)
        if result.get('status')!='draft_only' or result.get('published') is not False:continue
        try:parsed=parse_reply(json.dumps(result['draft']),facts,2)
        except (ValueError,KeyError,TypeError):continue
        if result['project_facts_sha256']!=digest(facts):continue
        # Recover a committed result after a crash before file materialization.
        output=folder/(digest(identifier)+'.json')
        if not output.exists():atomic_json(output,result)
        ready.append(dict(id=digest(identifier),source_url=result['source_url'],draft=parsed,
            models=[dict(provider=m['provider'],model=m['actual_model']) for m in result['models']]))
    atomic_json(base/'notification-feed.json',dict(schema_version=1,updated_at=status['updated_at'],
        state=status['state'],pause_reason=status.get('pause_reason'),
        budget_paused=status.get('budget_paused',False),ready=ready))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--public-dir',type=Path,required=True)
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args()
    args.state_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(args.state_dir/'worker.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cycle(args.state_dir,args.public_dir,args.smoke)
