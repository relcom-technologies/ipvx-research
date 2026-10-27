"""Validate append-only attribution structure and public journal boundaries."""
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
rows=[json.loads(line) for line in (ROOT/'history/events.jsonl').read_text().splitlines() if line.strip()]
actors={p['id'] for p in json.loads((ROOT/'history/participants.json').read_text())['participants']}
ids={row['id'] for row in rows}
assert len(ids)==len(rows),'Repeated history ID'
for sequence,row in enumerate(rows,1):
    assert row['sequence']==sequence and row['id']==f'HX-{sequence:04}',f'History sequence {sequence}'
    assert row['attributed_to'] in actors and row['recorded_by'] in actors,row['id']
    assert row['origin'] in ('contemporaneous_author_record','retrospective_reconstruction'),row['id']
    assert row['time_precision'] in ('unknown','day','instant'),row['id']
    assert row['occurred_at'] is not None or row['time_precision']=='unknown',row['id']
    assert set(row['related_to'])<=ids and row['id'] not in row['related_to'],row['id']
    assert row['title'] and row['summary'] and row['decision_rationale'] and row['evidence'],row['id']
    assert isinstance(row['limitations'],list),row['id']
    if row['origin']=='contemporaneous_author_record':assert row['limitations'],row['id']
    text=json.dumps(row,ensure_ascii=False)
    private=r'10\.10\.50\.|192\.168\.\d+\.\d+|BEGIN (?:OPENSSH|RSA|EC) PRIVATE KEY|ghp_[A-Za-z0-9]{20}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
    assert not re.search(private,text),f'Public boundary violation in {row["id"]}'
print(f'{len(rows)} attributed history events; sequence, actors, links and public boundaries valid')
