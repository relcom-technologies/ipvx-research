"""Owned editorial strings; evidence bytes, code and source records are immutable."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'script', 'style', 'pre', 'code'}
ATTRS = {'title', 'alt', 'aria-label', 'placeholder', 'content'}
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


def key(text):
    return hashlib.sha256(text.strip().encode()).hexdigest()[:16]


def editorial(text):
    s = text.strip()
    return bool(re.search(r'[A-Za-zА-Яа-яЁё]', s)) and not (
        re.fullmatch(r'[a-f0-9]{16,}', s) or s.startswith(('https://', 'http://', 'ipvx:agent:')))


class Sources(HTMLParser):
    def __init__(self, add):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.ignored = 0
        self.add = add

    def handle_starttag(self, tag, attrs):
        if self.ignored:
            if tag not in VOID: self.ignored += 1
            return
        if 'data-i18n-fixed' in dict(attrs):
            self.ignored = 1
            return
        for name, value in attrs:
            if name in ATTRS and value and (name != 'content' or dict(attrs).get('name') == 'description'):
                self.add(value, 'attribute:' + name)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.ignored:
            self.ignored -= 1
            return
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]

    def handle_data(self, value):
        if not self.ignored and not set(self.stack) & SKIP:
            self.add(value, 'text:' + '/'.join(self.stack[-3:]))


def collect():
    entries = {}
    def add(value, context):
        if not editorial(value):
            return
        identity = key(value)
        if identity in entries:
            assert entries[identity]['source'] == value.strip(), 'Hash collision'
            return
        entries[identity] = dict(id=identity, source=value.strip(), context=context)
    # Order short public pages first; the long attributed history follows.
    pages = sorted(p for p in ROOT.glob('*.html') if not re.search(r'\.(?:en|de|es)\.html$', p.name))
    for page in sorted(pages, key=lambda p: (p.name == 'history.html', p.name)):
        parser = Sources(lambda value, context: add(value, page.name + ':' + context))
        parser.feed(page.read_text())
    for file in sorted((ROOT/'assets').glob('*.svg')):
        parser = Sources(lambda value, context: add(value, file.name + ':' + context))
        parser.feed(file.read_text())
    js = ROOT/'i18n/js-sources.json'
    if js.exists():
        for entry in json.loads(js.read_text()):
            add(entry['source'], entry['context'])
    def data_strings(value, context):
        if isinstance(value, dict):
            for name, child in value.items():
                data_strings(child, context + '.' + name)
        elif isinstance(value, list):
            for child in value:
                data_strings(child, context + '[]')
        elif isinstance(value, str) and re.search('[А-Яа-яЁё]', value):
            add(value, context)
    data_strings(json.loads((ROOT/'data/llm-summary.json').read_text()), 'data/llm-summary.json')
    return list(entries.values())


if __name__ == '__main__':
    entries = collect()
    (ROOT/'i18n/source.json').write_text(json.dumps(dict(schema_version=1, entries=entries), ensure_ascii=False, indent=2)+'\n')
    print(len(entries), 'source strings;', sum(len(x['source']) for x in entries), 'characters')
