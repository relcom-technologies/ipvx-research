"""Check historical source hashes and the append-only journal prefix offline."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def check():
    receipt=json.loads((ROOT/'adapters/bcp02/evidence/preservation.json').read_text())
    for entry in receipt['unchanged_files']:
        assert sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256'],entry['path']
    lines=(ROOT/'history/events.jsonl').read_bytes().splitlines(keepends=True)
    prefix=b''.join(lines[:receipt['prior_history_events']])
    assert sha256(prefix).hexdigest()==receipt['prior_history_sha256'],'history prefix changed'
    print(f"Preserved {len(receipt['unchanged_files'])} source/evidence files and {receipt['prior_history_events']} prior events")


if __name__=='__main__':check()
