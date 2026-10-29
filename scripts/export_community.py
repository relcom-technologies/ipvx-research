"""Public, attributed Moltbook mirror. Never reads the private A2A queue."""
import argparse
import json
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
try:
    import certifi
except ImportError:
    certifi = None

POST = 'bf6ed290-9ec8-4ed3-96b1-fa791200d849'
BASE = 'https://www.moltbook.com/api/v1/posts/' + POST
URL = 'https://www.moltbook.com/post/' + POST
OWN = 'ipvxresearchliaison'
ROOT = Path(__file__).resolve().parents[1]


def read(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'IPvX-Public-Discussion-Mirror/0.1'})
    context = ssl.create_default_context(cafile=certifi.where() if certifi else None)
    with urllib.request.urlopen(request, context=context, timeout=20) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024:
        raise ValueError('source_response_limit')
    return json.loads(data)


def sanitize(data, reported_count=None, observed_at=None):
    result = []
    excluded = []
    seen = set()

    def walk(rows, parent=None, depth=0):
        for row in rows:
            identifier = row['id']
            if identifier in seen:
                raise ValueError('duplicate_comment_id')
            seen.add(identifier)
            if row.get('post_id', POST) != POST:
                raise ValueError('wrong_post')
            author = (row.get('author') or {}).get('name', 'unknown')
            body = row.get('content', '')
            if not isinstance(body, str) or len(body) > 16000:
                raise ValueError('comment_body_limit')
            if row.get('is_deleted') or row.get('is_spam') or row.get('verification_status') == 'pending':
                excluded.append(identifier)
            else:
                result.append(dict(id=identifier, parent_id=row.get('parent_id') or parent,
                    source='moltbook', source_url=URL, claimed_author=author,
                    project_account=author.lower() == OWN, text=body,
                    created_at=row.get('created_at'), updated_at=row.get('updated_at'),
                    source_verification_status=row.get('verification_status', 'unknown'),
                    observed_depth=depth, a2a_submission=False,
                    authoring_mode='Codex-assisted project liaison' if author.lower() == OWN else 'external self-asserted account',
                    model=None))
            walk(row.get('replies', []), identifier, depth + 1)

    walk(data.get('comments', []))
    result.sort(key=lambda row: (row['created_at'] or '', row['id']))
    return dict(schema_version=1, kind='public_discussion_snapshot',
        observed_at=observed_at or datetime.now(timezone.utc).isoformat(), source_url=URL,
        reported_comment_count=reported_count, returned_comment_count=len(seen),
        mirrored_comment_count=len(result), excluded_comment_ids=excluded,
        external_accounts=sorted({row['claimed_author'] for row in result if not row['project_account']}),
        coverage=dict(complete=False, known_limit='Moltbook tree omits some replies deeper than five; source counters are not a completeness proof.',
            has_more=data.get('has_more'), native_comments_imported=False, private_a2a_imported=False),
        comments=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Previously fetched public comments JSON only')
    parser.add_argument('--output', type=Path, default=ROOT/'data/community-discussions.json')
    args = parser.parse_args()
    data = json.loads(args.input.read_text()) if args.input else read(BASE+'/comments?sort=new&limit=100')
    post = {} if args.input else read(BASE)
    count = (post.get('post') or {}).get('comment_count')
    snapshot = sanitize(data, count)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: snapshot[k] for k in ('observed_at', 'reported_comment_count', 'returned_comment_count', 'mirrored_comment_count', 'external_accounts')}))


if __name__ == '__main__':
    main()
