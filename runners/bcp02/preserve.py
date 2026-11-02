"""Read-only preservation of accepted sources/history and this reviewed package."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runners.bcp02.common import read_json,sha,need


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
}


def _accepted(name):
    return ROOT/'runners/bcp02/evidence/archive'/ARCHIVED[name]/name if name in ARCHIVED else ROOT/name


def check():
    saved=read_json(Path(__file__).with_name('evidence')/'preservation.json')
    for name,pin in saved['files'].items():
        p=_accepted(name)
        need(p.resolve()==p and sha(p.read_bytes())==pin,'previous source changed: '+name)
    prefix=b''.join((ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)[:saved['history_events']])
    need(sha(prefix)==saved['history_prefix_sha256'],'accepted history prefix changed')
    revision=read_json(Path(__file__).with_name('evidence')/'dataset-preservation.json')
    for name,pin in revision['unchanged_files'].items():
        need(sha(_accepted(name).read_bytes())==pin,'dataset revision preservation mismatch: '+name)
    for name,pin in revision['archived_evidence'].items():
        need(sha((ROOT/name).read_bytes())==pin,'dataset revision preservation mismatch: '+name)
    prefix=b''.join((ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)[:revision['history_events']])
    need(sha(prefix)==revision['history_prefix_sha256'],'dataset revision history prefix changed')
    from runners.bcp02.admission import source_hash
    digest=source_hash()
    return dict(previous_files=len(saved['files']),previous_events=saved['history_events'],
                previous_presentation_sources_archived=2,previous_liaison_sources_archived=5,
                dataset_revision_previous_events=revision['history_events'],
                dataset_revision_unchanged_files=len(revision['unchanged_files']),archived_reports=len(revision['archived_evidence']),
                source_scope_sha256=digest,network_execution=False,old_evidence_reissued=False)


if __name__=='__main__':print(json.dumps(check(),indent=2))
