"""Fail on missing translations, changed source spans or substituted evidence IDs."""
import hashlib
import json
import re
from i18n_sources import ROOT, key


def check():
    entries = json.loads((ROOT/'i18n/source.json').read_text())['entries']
    identities = {entry['id'] for entry in entries}
    assert len(identities) == len(entries)
    for language in ('en', 'de', 'es'):
        catalog = json.loads((ROOT/'i18n'/f'{language}.json').read_text())
        missing = identities - catalog.keys()
        assert not missing, f'{language}: {len(missing)} missing translations'
        for entry in entries:
            source, target = entry['source'], catalog[entry['id']]
            assert key(source) == entry['id']
            assert isinstance(target, str) and target.strip(), (language, entry['id'])
            # Scientific attribution and exact revisions must survive translation.
            for token in re.findall(r'(?<![a-zA-Z0-9])[0-9a-f]{40,64}(?![a-zA-Z0-9])|HX-\d{4}|RFC-\d{4}', source):
                assert token in target, (language, entry['id'], 'missing evidence identity', token)
            if source.startswith('{'):
                try:
                    json.loads(source)
                except ValueError:
                    pass
                else:
                    assert source == target, (language, entry['id'], 'raw JSON evidence translated')
    for span in json.loads((ROOT/'i18n/js-sources.json').read_text()):
        source = (ROOT/span['file']).read_bytes()
        assert hashlib.sha256(source).hexdigest() == span['sha256'], span['file']
    print(f'{len(entries)} editorial entries × 3 languages; coverage, revision IDs, raw JSON and JS source hashes checked')


if __name__ == '__main__':
    check()
