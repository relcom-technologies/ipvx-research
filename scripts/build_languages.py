"""Static, reviewable language editions with adjacent immutable originals.

No visitor text, signed envelopes, model output JSON or protocol bytes are sent
to a translation service. Missing editorial translations stop the build.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from i18n_sources import ROOT, SKIP, ATTRS, VOID, key, editorial
from observatory import render as render_observatory
from research_architecture import render as render_research_architecture
from research_contributions import render as render_research_contributions
from agent_directory import render as render_agent_directory
from agent_intake_ui import owner as render_agent_owner
from collaboration import render as render_collaboration, entry_link as render_collaboration_link

LANGUAGES = {'ru': 'Русский', 'en': 'English', 'de': 'Deutsch', 'es': 'Español'}
NOTICES = {
    'en': ('Editorial translation. Original RFCs and attributed records are available alongside the translation; evidence files stay unchanged.', 'Original page', 'Original document', 'Original record', 'Language'),
    'de': ('Redaktionelle Übersetzung. Original-RFCs und zugeordnete Aufzeichnungen stehen neben der Übersetzung; Belegdateien bleiben unverändert.', 'Originalseite', 'Originaldokument', 'Originaleintrag', 'Sprache'),
    'es': ('Traducción editorial. Los RFC y los registros atribuidos originales están disponibles junto a la traducción; los archivos de evidencia no se modifican.', 'Página original', 'Documento original', 'Registro original', 'Idioma'),
}


@dataclass
class Element:
    tag: str
    attrs: list = field(default_factory=list)
    children: list = field(default_factory=list)

    def attr(self, name):
        return next((v for k, v in self.attrs if k.lower() == name), None)

    def set(self, name, value):
        self.attrs = [(k, v) for k, v in self.attrs if k.lower() != name]
        self.attrs.append((name, value))


class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Element('root')
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        spellings = {m.group(1).lower(): m.group(1) for m in re.finditer(r'([^\s=<>/]+)\s*=', raw)}
        original_tag = re.match(r'<([^\s/>]+)', raw)[1]
        node = Element(original_tag, [(spellings.get(k, k), v) for k, v in attrs])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag.lower() == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)

    def handle_decl(self, value):
        self.stack[-1].children.append(Element('raw', children=['<!'+value+'>']))

    def handle_comment(self, value):
        self.stack[-1].children.append(Element('raw', children=['<!--'+value+'-->']))


def render(node, raw=False):
    if isinstance(node, str):
        return node if raw else html.escape(node, quote=False)
    if node.tag in ('root', 'raw'):
        return ''.join(render(c, node.tag == 'raw') for c in node.children)
    attrs = ''.join(' '+name+('="'+html.escape(value, quote=True)+'"' if value is not None else '') for name, value in node.attrs)
    opening = '<'+node.tag+attrs+'>'
    if node.tag.lower() in VOID:
        return opening
    return opening+''.join(render(c, node.tag.lower() in ('script', 'style')) for c in node.children)+'</'+node.tag+'>'


def page_name(name, language):
    return name if language == 'ru' else name.removesuffix('.html')+'.'+language+'.html'


def translator(catalog):
    def translate(value):
        stripped = value.strip()
        if not editorial(value):
            return value
        if key(value) not in catalog:
            raise ValueError('Missing translation: '+stripped[:120])
        target = catalog[key(value)]
        if not isinstance(target, str) or not target.strip():
            raise ValueError('Empty translation: '+stripped[:120])
        return value[:len(value)-len(value.lstrip())]+target+value[len(value.rstrip()):]
    return translate


def language_nav(name, language):
    label = 'Язык' if language == 'ru' else NOTICES[language][4]
    links = []
    for code, native in LANGUAGES.items():
        link = Element('a', [('href', page_name(name, code)), ('lang', code), ('hreflang', code)], [native])
        if code == language:
            link.set('aria-current', 'page')
        links.append(link)
    return Element('nav', [('class', 'language-switch'), ('aria-label', label)], links)


def strip_ids(node):
    if isinstance(node, Element):
        node.attrs = [(k, v) for k, v in node.attrs if k not in ('id', 'aria-labelledby', 'aria-describedby')]
        for child in node.children:
            strip_ids(child)


def localized(tree, name, language, catalog, pages):
    translate = translator(catalog) if language != 'ru' else lambda v: v
    original_nodes = {}
    original_languages = {}
    history_path = ROOT/'history/events.jsonl'
    if history_path.exists():
        for line in history_path.read_text().splitlines():
            event = json.loads(line)
            original_languages[event['id']] = ('ru' if re.search('[А-Яа-яЁё]', event['summary']) else
                'de' if event['attributed_to'] == 'codex-translator-de' else 'en')
    def remember(node):
        if isinstance(node, Element):
            classes = (node.attr('class') or '').split()
            if 'history-entry' in classes or 'rfc-prose' in classes:
                original_nodes[id(node)] = deepcopy(node)
            for child in node.children:
                remember(child)
    remember(tree)
    def walk(node, skipped=False):
        if isinstance(node, str):
            return node if skipped else translate(node)
        if language != 'ru' and node.attr('id') == 'collaboration-hub':
            return next(child for child in Tree(render_collaboration(ROOT, language)).root.children if isinstance(child, Element))
        if language != 'ru' and node.attr('id') == 'collaboration-link':
            return next(child for child in Tree(render_collaboration_link(language)).root.children if isinstance(child, Element))
        if language != 'ru' and node.attr('id') == 'agent-intake-owner':
            return next(child for child in Tree(render_agent_owner(language)).root.children if isinstance(child, Element))
        if language != 'ru' and node.attr('id') == 'agent-invitation':
            return next(child for child in Tree(render_agent_directory(language)).root.children if isinstance(child, Element))
        if language != 'ru' and node.attr('id') == 'compute-contributions':
            return next(child for child in Tree(render_research_contributions(language)).root.children if isinstance(child, Element))
        if language != 'ru' and node.attr('id') == 'research-network':
            return next(child for child in Tree(render_research_architecture(ROOT, language)).root.children if isinstance(child, Element))
        if language != 'ru' and node.attr('id') == 'observatory':
            return next(child for child in Tree(render_observatory(ROOT, language)).root.children if isinstance(child, Element))
        skip = skipped or node.tag.lower() in SKIP or node.tag == 'raw'
        for attr, value in list(node.attrs):
            lower = attr.lower()
            if lower in ('href', 'src') and value and value.startswith(('assets/', 'data/downloads/')):
                value = re.sub(r'\?v=[a-f0-9]{16}$', '', value)
                node.set(lower, value)
            if lower in ATTRS and value and (lower != 'content' or node.attr('name') == 'description'):
                node.set(lower, translate(value))
            if language != 'ru' and lower in ('href', 'src', 'action') and value:
                if value in ('assets/llm-comparison.svg', 'assets/llm-comparison-mobile.svg'):
                    node.set(lower, value.replace('assets/', 'assets/'+language+'/'))
                elif re.fullmatch(r'assets/(?:portal|relcom|community|admin|replay|agent-replay)\.js', value):
                    node.set(lower, value.replace('assets/', 'assets/'+language+'/'))
                else:
                    canonical = value.removeprefix('https://ipvx.org/')
                    path = canonical.split('?', 1)[0].split('#', 1)[0]
                    if path in pages:
                        node.set(lower, value.replace(path, page_name(path, language), 1))
                    elif value.startswith('https://ipvx.org/auth/login?returnTo='):
                        node.set(lower, re.sub(r'returnTo=/(account|admin)\.html', r'returnTo=/\1.'+language+'.html', value))
        original = original_nodes.get(id(node))
        node.children = [walk(child, skip) for child in node.children]
        if node.tag == 'html':
            node.set('lang', language)
        if node.tag == 'head':
            for code in LANGUAGES:
                node.children.append(Element('link', [('rel', 'alternate'), ('hreflang', code), ('href', 'https://ipvx.org/'+page_name(name, code))]))
            node.children.extend([
                Element('link', [('rel', 'canonical'), ('href', 'https://ipvx.org/'+page_name(name, language))]),
                Element('link', [('rel', 'stylesheet'), ('href', 'assets/languages.css')]),
                Element('script', [('src', 'assets/languages.js'), ('defer', None)]),
            ])
        if node.tag == 'body':
            for i, child in enumerate(node.children):
                if isinstance(child, Element) and child.tag == 'header':
                    node.children.insert(i+1, language_nav(name, language))
                    break
        if language != 'ru' and node.tag == 'main':
            notice = Element('aside', [('class', 'translation-note')], [
                NOTICES[language][0]+' ', Element('a', [('href', name), ('hreflang', 'ru')], [NOTICES[language][1]])])
            node.children.insert(0, notice)
        if language != 'ru' and original:
            original_language = original_languages.get(node.attr('id'), 'ru')
            strip_ids(original)
            history = 'history-entry' in (node.attr('class') or '').split()
            original.set('lang', original_language if history else 'en')
            if history:
                original.tag = 'div'
                original.set('class', 'original-record')
                if original.children and isinstance(original.children[0], Element) and original.children[0].tag == 'summary':
                    original.children[0].tag = 'h3'
                node.children.append(Element('details', [('class', 'translation-original')], [Element('summary', children=[NOTICES[language][3]]), original]))
            else:
                node.children.append(Element('details', [('class', 'translation-original')], [Element('summary', children=[NOTICES[language][2]]), original]))
        return node
    return walk(tree)


def fingerprint_assets(root):
    """Change cached resource URLs only when their actual bytes change."""
    pattern = re.compile(r'(?P<prefix>\b(?:src|href)=")(?P<path>(?:assets/[^"?#]+|data/downloads/[^"?#]+\.zip))(?:\?v=[a-f0-9]{16})?(?P<end>")')
    for page in root.glob('*.html'):
        def replace(match):
            path = root/match['path']
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Invalid fingerprint input: '+match['path'])
            version = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            return match['prefix']+match['path']+'?v='+version+match['end']
        page.write_text(pattern.sub(replace, page.read_text()))


def build(languages=LANGUAGES):
    sources = {p.name: p.read_text() for p in ROOT.glob('*.html') if not re.search(r'\.(en|de|es)\.html$', p.name)}
    spans = json.loads((ROOT/'i18n/js-sources.json').read_text())
    for language in languages:
        catalog = {} if language == 'ru' else json.loads((ROOT/'i18n'/f'{language}.json').read_text())
        translate = translator(catalog) if catalog else lambda v: v
        for name, source in sources.items():
            tree = localized(Tree(source).root, name, language, catalog, sources)
            (ROOT/page_name(name, language)).write_text(render(tree)+'\n')
        if language == 'ru':
            continue
        folder = ROOT/'assets'/language
        folder.mkdir(exist_ok=True)
        for file in ['portal', 'relcom', 'community', 'admin', 'replay', 'agent-replay']:
            source = (ROOT/'assets'/f'{file}.js').read_text()
            own_spans = [span for span in spans if span['file'] == f'assets/{file}.js']
            digest = hashlib.sha256(source.encode()).hexdigest()
            for span in sorted(own_spans, key=lambda s: s['start'], reverse=True):
                assert span['sha256'] == digest, 'Re-extract changed JavaScript source'
                target = translate(span['source'])
                if span['kind'] == 'literal':
                    target = json.dumps(target, ensure_ascii=False)
                else:
                    target = target.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
                source = source[:span['start']]+target+source[span['end']:]
            source = source.replace("'ru-RU'", repr({'en': 'en-GB', 'de': 'de-DE', 'es': 'es-ES'}[language]))
            if file == 'portal':
                source = source.replace("fetch('data/llm-summary.json')", "fetch('data/llm-summary."+language+".json')")
            if file == 'community':
                source = source.replace("entry.rfc+'.html#discussion'", "entry.rfc+'."+language+".html#discussion'")
            (folder/f'{file}.js').write_text(source)
        for file in ('llm-comparison.svg', 'llm-comparison-mobile.svg'):
            root = ET.fromstring((ROOT/'assets'/file).read_text())
            for el in root.iter():
                if el.tag.rsplit('}', 1)[-1] in ('text', 'tspan', 'title', 'desc') and el.text and editorial(el.text):
                    el.text = translate(el.text)
            ET.register_namespace('', 'http://www.w3.org/2000/svg')
            (folder/file).write_text(ET.tostring(root, encoding='unicode'))
        def data_translate(value):
            if isinstance(value, dict):
                return {k: data_translate(v) for k, v in value.items()}
            if isinstance(value, list):
                return [data_translate(v) for v in value]
            return translate(value) if isinstance(value, str) and re.search('[А-Яа-яЁё]', value) else value
        summary = data_translate(json.loads((ROOT/'data/llm-summary.json').read_text()))
        (ROOT/'data'/f'llm-summary.{language}.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    fingerprint_assets(ROOT)
    print(len(sources)*len(languages), 'static language pages; originals and evidence preserved')


if __name__ == '__main__':
    build()
