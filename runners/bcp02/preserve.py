"""Read-only preservation of accepted sources/history and this reviewed package."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runners.bcp02.common import read_json,sha,need,in_scope


# Accepted sources revised later by non-BCP pull requests. Their original bytes
# are verified in an explicit immutable archive; every other accepted source
# still has to match in place. Current bytes remain pinned independently by
# source_hash() below.
ARCHIVED={
    # Presentation builders, revised in the website PR.
    'scripts/build_portal.py':'dataset-v2','scripts/build_languages.py':'dataset-v2',
    # Liaison service, revised in PR53 (Sonnet 5.5 writer, 1 USD/day limit).
    'infra/install_liaison.sh':'liaison-pr53','scripts/test_liaison.py':'liaison-pr53',
    'services/liaison/README.md':'liaison-pr53','services/liaison/agent.py':'liaison-pr53',
    'services/liaison/config.example.json':'liaison-pr53',
    # Portal assets and browser check, revised in PR65 (IPvX as a replacement for IP and DNS).
    'assets/portal.js':'portal-pr65','assets/portal.css':'portal-pr65','assets/en/portal.js':'portal-pr65',
    'assets/de/portal.js':'portal-pr65','assets/es/portal.js':'portal-pr65','scripts/browser_check.mjs':'portal-pr65',
    # Kernel contact fixed in runner revision 3, after the first rehearsal on a real kernel.
    'runners/bcp02/stand.py':'runner-v2','runners/bcp02/transport.py':'runner-v2','runners/bcp02/tests/test_runner.py':'runner-v2',
    # Source scope narrowed on 2026-11-08: scope predicate, plan checks limited to the scope,
    # regenerated plan report and bundle, workflow triggers equal to the scope.
    'runners/bcp02/common.py':'scope-2026-11-08','.github/workflows/bcp-runner.yml':'scope-2026-11-08',
    'experiments/bcp02-net-001/preserve.py':'scope-2026-11-08','experiments/bcp02-net-001/readiness.py':'scope-2026-11-08',
    'experiments/bcp02-net-001/static-checks.json':'scope-2026-11-08','experiments/bcp02-net-001/bundle-manifest.json':'scope-2026-11-08',
    'experiments/bcp02-net-001/tests/test_plan.py':'scope-2026-11-08',
}


def _accepted(name):
    return ROOT/'runners/bcp02/evidence/archive'/ARCHIVED[name]/name if name in ARCHIVED else ROOT/name


def check():
    # Since 2026-11-08 only sources inside the runner's scope are preserved here; website,
    # forum and documentation files outside it may change without touching the runner.
    scope=read_json(Path(__file__).with_name('manifest.json'))['scope']
    saved=read_json(Path(__file__).with_name('evidence')/'preservation.json')
    for name,pin in saved['files'].items():
        if not in_scope(name,scope):continue
        p=_accepted(name)
        need(p.resolve()==p and sha(p.read_bytes())==pin,'previous source changed: '+name)
    prefix=b''.join((ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)[:saved['history_events']])
    need(sha(prefix)==saved['history_prefix_sha256'],'accepted history prefix changed')
    revision=read_json(Path(__file__).with_name('evidence')/'dataset-preservation.json')
    for name,pin in revision['unchanged_files'].items():
        if not in_scope(name,scope):continue
        need(sha(_accepted(name).read_bytes())==pin,'dataset revision preservation mismatch: '+name)
    for name,pin in revision['archived_evidence'].items():
        need(sha((ROOT/name).read_bytes())==pin,'dataset revision preservation mismatch: '+name)
    prefix=b''.join((ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)[:revision['history_events']])
    need(sha(prefix)==revision['history_prefix_sha256'],'dataset revision history prefix changed')
    from runners.bcp02.admission import source_hash
    digest=source_hash()
    inside=lambda names:sum(1 for n in names if in_scope(n,scope))
    return dict(previous_files=len(saved['files']),previous_files_checked=inside(saved['files']),previous_events=saved['history_events'],
                previous_presentation_sources_archived=2,previous_liaison_sources_archived=5,previous_portal_sources_archived=6,
                previous_runner_sources_archived=3,previous_scope_sources_archived=7,
                dataset_revision_previous_events=revision['history_events'],
                dataset_revision_unchanged_files=len(revision['unchanged_files']),
                dataset_revision_unchanged_files_checked=inside(revision['unchanged_files']),archived_reports=len(revision['archived_evidence']),
                source_scope_sha256=digest,network_execution=False,old_evidence_reissued=False)


if __name__=='__main__':print(json.dumps(check(),indent=2))
