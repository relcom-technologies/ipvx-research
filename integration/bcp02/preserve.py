"""Offline verification of previous sources/evidence and append-only history."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


if __name__=='__main__':
    record=json.loads((ROOT/'integration/bcp02/evidence/preservation.json').read_text())
    for entry in record['unchanged_files']:
        assert sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256'],entry['path']
    prefix=b''.join((ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)[:record['prior_history_events']])
    assert sha256(prefix).hexdigest()==record['prior_history_sha256'],'previous history changed'
    print(len(record['unchanged_files']),'previous source/evidence files and',record['prior_history_events'],'events preserved')
