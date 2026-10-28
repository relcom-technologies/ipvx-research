"""Export only the four reviewed project claims and their supplied evidence."""
import argparse
import json
from pathlib import Path


def export(private, public):
    public_data = json.loads(public.read_text())
    expected = {x['case']: x for x in public_data['tasks']}
    output = []
    for run in ('round1-native', 'round2-native'):
        source = json.loads((private / (run+'.json')).read_text())
        assert source['revision'] == public_data['source_revision'] and source['mode'] == 'native'
        for item in source['cases']:
            assert item['id'] in expected and item['claim'] == expected[item['id']]['claim']
            assert item['expected'] == expected[item['id']]['expected']
            assert all(isinstance(s, str) and len(s) <= 1000 for s in item['a'] + item['b'])
            output.append({'case': item['id'], 'claim': item['claim'], 'expected': item['expected'],
                           'evidence_a': item['a'], 'evidence_b': item['b'], 'run': run})
    assert len(output) == 4 and {x['case'] for x in output} == set(expected)
    return {'schema_version': 1, 'source_revision': public_data['source_revision'],
            'source_run': public_data['workflow'], 'cases': output,
            'scope': 'Only task claims and supplied evidence; private logs and network identifiers excluded.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('private', type=Path)
    p.add_argument('public', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    args.output.write_text(json.dumps(export(args.private, args.public), ensure_ascii=False, indent=2)+'\n')
