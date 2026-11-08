"""Read-only preservation check; no imports of experimental/runtime modules."""
from hashlib import sha256
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def check():
    # Since 2026-11-08 only files inside the runner's source scope are preserved here.
    from fnmatch import fnmatchcase
    scope=json.loads((ROOT/'runners/bcp02/manifest.json').read_text())['scope']
    record=json.loads((HERE/'preservation.json').read_text())
    checked=[e for e in record['unchanged_files'] if any(fnmatchcase(e['path'],g) for g in scope)]
    for entry in checked:
        path=ROOT/entry['path']
        if Path(entry['path']).is_absolute() or '..' in Path(entry['path']).parts or path.resolve()!=path:raise ValueError('unsafe preservation path')
        assert sha256(path.read_bytes()).hexdigest()==entry['sha256'],entry['path']
    prefix=b''.join((ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)[:record['prior_history_events']])
    assert sha256(prefix).hexdigest()==record['prior_history_sha256'],'history prefix changed'
    return {'previous_files':len(record['unchanged_files']),'previous_files_checked':len(checked),'previous_events':record['prior_history_events']}


def check_bundle():
    manifest=json.loads((HERE/'bundle-manifest.json').read_text())
    report=json.loads((HERE/'static-checks.json').read_text())
    assert manifest['scope_sha256']==report['readiness']['scope_sha256'],'bundle scope mismatch'
    assert (manifest['protocol_id'],manifest['version'],manifest['status'],manifest['execution_performed'])==('IPVX-BCP02-NET-001-F','0.1','proposed_not_run',False)
    expected={str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='bundle-manifest.json'}
    assert set(manifest['files'])==expected,'bundle inventory mismatch'
    for name,digest in manifest['files'].items():
        relative=Path(name);path=HERE/relative
        if relative.is_absolute() or '..' in relative.parts or path.resolve()!=path:raise ValueError('unsafe bundle path')
        assert sha256(path.read_bytes()).hexdigest()==digest,name
    assert sha256((ROOT/'.github/workflows/bcp-net-plan.yml').read_bytes()).hexdigest()==manifest['workflow_sha256']
    return {'bundle_files':len(expected),'run_performed':False}


if __name__=='__main__':print(json.dumps({**check(),**check_bundle()},indent=2))
