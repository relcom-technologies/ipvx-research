"""Read-only preservation of accepted sources/history and this reviewed package."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runners.bcp02.common import read_json,sha,need


def check():
    saved=read_json(Path(__file__).with_name('evidence')/'preservation.json')
    for name,pin in saved['files'].items():
        p=ROOT/name;need(p.resolve()==p and sha(p.read_bytes())==pin,'previous source changed: '+name)
    prefix=b''.join((ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)[:saved['history_events']])
    need(sha(prefix)==saved['history_prefix_sha256'],'accepted history prefix changed')
    from runners.bcp02.admission import source_hash
    digest=source_hash()
    return dict(previous_files=len(saved['files']),previous_events=saved['history_events'],
                source_scope_sha256=digest,network_execution=False,old_evidence_reissued=False)


if __name__=='__main__':print(json.dumps(check(),indent=2))
