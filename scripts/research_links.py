"""Curated public evidence links. No intake access, submission or execution."""
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

LANGS = ('ru', 'en', 'de', 'es')
REPO = 'https://github.com/relcom-technologies/ipvx-research'
COPY = {
 'title': ('От обсуждения к эксперименту','From discussion to experiment','Von der Diskussion zum Experiment','Del debate al experimento'),
 'intro': ('Публичный реестр связывает вопрос, протокол, прогон и результат. Связи добавляются через проверку изменений; комментарий не запускает опыт.','This public registry links a question, protocol, run and result. Links are added through change review; a comment does not start an experiment.','Das öffentliche Register verknüpft Frage, Protokoll, Lauf und Ergebnis. Verknüpfungen werden geprüft; ein Kommentar startet keinen Versuch.','El registro público enlaza pregunta, protocolo, ejecución y resultado. Los enlaces se añaden mediante revisión; un comentario no inicia un experimento.'),
 'open': ('Открыть цепочку доказательств','Open the evidence chain','Beweiskette öffnen','Abrir la cadena de pruebas'),
 'source': ('Исходное обсуждение','Source discussion','Ursprüngliche Diskussion','Debate original'),
 'question': ('Проверяемый вопрос','Testable question','Prüfbare Frage','Pregunta comprobable'),
 'protocol': ('Протокол','Protocol','Protokoll','Protocolo'),
 'run': ('Прогон и доказательства','Run and evidence','Lauf und Belege','Ejecución y pruebas'),
 'public_record': ('Публичная запись проверки','Public check record','Öffentliche Prüfaufzeichnung','Registro público de la comprobación'),
 'private_run': ('Журнал CI — нужен доступ к закрытому репозиторию','CI log — private repository access required','CI-Protokoll — Zugriff auf privates Repository erforderlich','Registro CI — requiere acceso al repositorio privado'),
 'public_summary': ('Публичная сводка JSON','Public JSON summary','Öffentliche JSON-Zusammenfassung','Resumen JSON público'),
 'result': ('Результат','Result','Ergebnis','Resultado'),
 'limits': ('Границы вывода','Limits of the conclusion','Grenzen der Schlussfolgerung','Límites de la conclusión'),
 'local_preflight': ('Только локальная подготовка','Local preflight only','Nur lokale Vorprüfung','Solo comprobación local'),
 'measured': ('Измерено · один оператор','Measured · one operator','Gemessen · ein Betreiber','Medido · un operador'),
 'proposal': ('Подготовить черновик проверки','Prepare a test draft','Prüfentwurf vorbereiten','Preparar borrador de prueba'),
 'draft': ('Черновик эксперимента','Experiment draft','Versuchsentwurf','Borrador de experimento'),
 'draft_help': ('Черновик остаётся в этой вкладке до скачивания. Включайте только публичные или синтетические данные. Это предложение для рецензирования, без согласованных ролей, ресурсов или запуска.','The draft stays in this tab until downloaded. Include only public or synthetic data. This is a review proposal, without agreed roles, resources or launch.','Der Entwurf bleibt bis zum Herunterladen in diesem Tab. Nur öffentliche oder synthetische Daten angeben. Es ist ein Prüfvorschlag ohne vereinbarte Rollen, Ressourcen oder Start.','El borrador permanece en esta pestaña hasta descargarlo. Incluya solo datos públicos o sintéticos. Es una propuesta para revisión, sin funciones, recursos ni inicio acordados.'),
 'task': ('Общая задача и контрольная группа','Shared task and control group','Gemeinsame Aufgabe und Kontrollgruppe','Tarea común y grupo de control'),
 'failures': ('Сценарии отказов, метрики успеха и неуспеха','Failure cases, success and failure metrics','Fehlerfälle, Erfolgs- und Misserfolgsmetriken','Fallos y métricas de éxito y fracaso'),
 'scope': ('Предлагаемые роли, версии, лимиты времени и вычислений','Proposed roles, versions, time and compute limits','Vorgeschlagene Rollen, Versionen, Zeit- und Rechenlimits','Funciones, versiones y límites de tiempo y cómputo propuestos'),
 'artifacts': ('Воспроизводимые артефакты и необходимые решения владельца','Reproducible artifacts and required owner decisions','Reproduzierbare Artefakte und erforderliche Eigentümerentscheidungen','Artefactos reproducibles y decisiones necesarias del propietario'),
 'review': ('Собрать текст для проверки','Assemble text for review','Text zur Prüfung zusammenstellen','Preparar texto para revisión'),
 'preview': ('Текст черновика','Draft text','Entwurfstext','Texto del borrador'),
 'download': ('Скачать Markdown','Download Markdown','Markdown herunterladen','Descargar Markdown'),
 'submit': ('Открыть форму GitHub','Open GitHub form','GitHub-Formular öffnen','Abrir formulario GitHub'),
 'ready': ('Текст готов. Проверьте его перед отдельной отправкой. Изменение полей требует новой сборки текста.','Text ready. Review it before a separate submission. Editing fields requires assembling the text again.','Text bereit. Vor dem gesonderten Einreichen prüfen. Nach Änderungen den Text erneut zusammenstellen.','Texto listo. Revíselo antes de enviarlo por separado. Tras editar los campos, prepare el texto de nuevo.'),
 'long': ('Скачайте текст: он слишком длинный для ссылки GitHub. Затем откройте форму отдельно и вставьте текст.','Download the text: it is too long for a GitHub link. Then open the form separately and paste it.','Text herunterladen: Er ist für einen GitHub-Link zu lang. Danach das Formular separat öffnen und den Text einfügen.','Descargue el texto: es demasiado largo para un enlace GitHub. Después abra el formulario y péguelo.'),
 'boundary': ('Нужно отдельное решение владельца. Публичный A2A использует HTTPS/IP/DNS; нативный Ethernet требует отдельного стенда. Публикация, почта или модельный черновик не означают согласие, допуск либо запуск.','A separate owner decision is required. Public A2A uses HTTPS/IP/DNS; native Ethernet needs a separate testbed. Publication, email or a model draft does not mean consent, admission or launch.','Eine gesonderte Eigentümerentscheidung ist nötig. Öffentliches A2A nutzt HTTPS/IP/DNS; natives Ethernet benötigt einen separaten Prüfstand. Veröffentlichung, E-Mail oder Modellentwurf bedeuten weder Zustimmung noch Aufnahme oder Start.','Se requiere una decisión separada del propietario. A2A público usa HTTPS/IP/DNS; Ethernet nativo necesita otro banco de pruebas. Publicación, correo o borrador de modelo no significan consentimiento, admisión ni inicio.'),
 'invalid_source': ('Источник из ссылки не принят. Выберите публичную цепочку выше.','Source from the URL was not accepted. Choose a public chain above.','Quelle aus der URL wurde nicht akzeptiert. Eine öffentliche Kette oben wählen.','No se aceptó la fuente del enlace. Elija una cadena pública arriba.'),
 'required': ('Заполните поле содержательным текстом.','Enter meaningful text in this field.','Dieses Feld mit einem aussagekräftigen Text ausfüllen.','Rellene este campo con texto significativo.'),
 'empty': ('Связей пока нет. Можно подготовить проверяемый черновик.','No links yet. You can prepare a testable draft.','Noch keine Verknüpfungen. Ein prüfbarer Entwurf ist möglich.','Aún no hay enlaces. Puede preparar un borrador comprobable.'),
 'json': ('Реестр JSON','Registry JSON','Register JSON','Registro JSON'),
}

def page(name, language):
    return name + ('' if language == 'ru' else '.' + language) + '.html'

def jump(language='ru'):
    return '<p id="research-links-jump" data-i18n-fixed><a href="#research-links">'+html.escape(COPY['title'][LANGS.index(language)])+'</a></p>'

def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('Unexpected registry fields')

def _text(value, max_length=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length or any(ord(c)<32 and c not in '\n\t' for c in value):
        raise ValueError('Invalid registry text')

def _localized(value):
    _keys(value, LANGS)
    for text in value.values(): _text(text)

def _artifact(root, value):
    _keys(value, ('path', 'revision', 'sha256'))
    if not re.fullmatch(r'(?:experiments/a2a-interop|docs)/[a-zA-Z0-9_./-]+\.json', value['path']) or '..' in value['path'].split('/'):
        raise ValueError('Unsafe artifact path')
    if not re.fullmatch('[a-f0-9]{40}', value['revision']) or not re.fullmatch('[a-f0-9]{64}', value['sha256']):
        raise ValueError('Unpinned artifact')
    file = root / value['path']
    if not file.resolve().is_relative_to(root.resolve()) or file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != value['sha256']:
        raise ValueError('Artifact digest mismatch')

def load(root, data=None):
    root = Path(root)
    data = json.loads((root/'data/research-links.json').read_text()) if data is None else data
    _keys(data, ('schema_version', 'kind', 'cases'))
    if data['schema_version'] != 1 or data['kind'] != 'curated_public_research_links' or not isinstance(data['cases'], list) or len(data['cases'])>100:
        raise ValueError('Invalid registry')
    snapshot = json.loads((root/'data/community-discussions.json').read_text())
    comments = {c['id'] for c in snapshot['comments']}
    events = {json.loads(l)['id'] for l in (root/'history/events.jsonl').read_text().splitlines() if l}
    ids = set()
    for case in data['cases']:
        _keys(case, ('id','rfcs','stage','title','hypothesis','source','protocol','run','result','limits'))
        if not re.fullmatch('[a-z][a-z0-9-]{2,63}',case['id']) or case['id'] in ids: raise ValueError('Duplicate or invalid case ID')
        ids.add(case['id'])
        if case['stage'] not in ('local_preflight','measured'): raise ValueError('Unsupported evidence stage')
        if not isinstance(case['rfcs'],list) or not 1<=len(case['rfcs'])<=7 or len(set(case['rfcs']))!=len(case['rfcs']): raise ValueError('Invalid RFC list')
        for rfc in case['rfcs']:
            if not re.fullmatch('rfc-000[1-7]',rfc): raise ValueError('Unknown RFC')
        for field in ('title','hypothesis','result','limits'): _localized(case[field])
        source=case['source']; kind=source.get('kind')
        _text(source.get('label'),200)
        if kind=='public_comment':
            _keys(source,('kind','url','comment_ids','label'))
            if source['url']!='https://www.moltbook.com/post/bf6ed290-9ec8-4ed3-96b1-fa791200d849': raise ValueError('Unapproved source')
            if not isinstance(source['comment_ids'],list) or not source['comment_ids'] or len(set(source['comment_ids']))!=len(source['comment_ids']): raise ValueError('Invalid source comments')
            for identity in source['comment_ids']:
                if identity not in comments: raise ValueError('Missing public comment')
        elif kind=='project_history':
            _keys(source,('kind','url','event_ids','label'))
            if not re.fullmatch(re.escape(REPO)+r'/blob/[a-f0-9]{40}/history/events\.jsonl',source['url']): raise ValueError('Unpinned history source')
            if not isinstance(source['event_ids'],list) or not source['event_ids'] or any(i not in events for i in source['event_ids']): raise ValueError('Missing history event')
        else: raise ValueError('Private or unsupported source')
        protocol=case['protocol']; _keys(protocol,('id','version','artifact'))
        _text(protocol['id'],100);_text(protocol['version'],100);_artifact(root,protocol['artifact'])
        run=case['run'];_keys(run,('classification','url','artifact','access'));_artifact(root,run['artifact'])
        expected_access='private_repository' if run['url'].startswith('https://github.com/relcom-technologies/ipvx-agent-lab/actions/') else 'public'
        if run['access']!=expected_access: raise ValueError('Run access label needs review')
        if case['stage']=='local_preflight':
            if run['classification']!='local_preflight' or run['url']!=artifact_url(run['artifact']): raise ValueError('Preflight cannot be a joint run')
        elif run['classification']!='single_operator' or not re.fullmatch(r'https://github\.com/relcom-technologies/(?:ipvx-research|ipvx-agent-lab)/actions/runs/[0-9]+',run['url']):
            raise ValueError('Unverified measured run')
    return data

def artifact_url(value):
    return REPO+'/blob/'+value['revision']+'/'+value['path']

def render(root, language='ru', view='full', rfc=None):
    data=load(root); t=lambda k:COPY[k][LANGS.index(language)]; esc=lambda s:html.escape(s,quote=True)
    if view not in ('full','compact','rfc'): raise ValueError('Unknown registry view')
    cases=[c for c in data['cases'] if rfc is None or rfc in c['rfcs']]
    canonical=page('experiments',language)
    out=[f'<section class="section research-links" id="research-links" data-i18n-fixed data-view="{view}" data-rfc="{esc(rfc or "")}"><h2>{t("title")}</h2><p>{t("intro")}</p>']
    if not cases: out.append('<p>'+t('empty')+'</p>')
    for case in cases:
        identity=case['id'];href=canonical+'#research-'+identity
        if view!='full':
            out.append(f'<div class="research-index"><h3><a href="{href}">{esc(case["title"][language])}</a></h3><p>{t(case["stage"])}</p></div>')
            continue
        source=case['source']; protocol=case['protocol'];run=case['run']
        out.append(f'<article class="research-case" id="research-{identity}"><h3>{esc(case["title"][language])}</h3><p class="badge">{t(case["stage"])}</p><dl>')
        source_html=f'<a href="{esc(source["url"])}">{esc(source["label"])}</a>'
        for comment in source.get('comment_ids',[]): source_html+=f' <a class="research-comment-id" href="{page("community",language)}#comment-{comment}"><code>{comment}</code></a>'
        if source.get('event_ids'): source_html+=' · '+esc(', '.join(source['event_ids']))
        rows=[('source',source_html),('question',esc(case['hypothesis'][language])),('protocol',f'<a href="{artifact_url(protocol["artifact"])}">{esc(protocol["id"])} · {esc(protocol["version"])}</a>'),('run',f'<a href="{esc(run["url"])}">{t("private_run" if run["access"]=="private_repository" else "public_record")}</a> · <a href="{artifact_url(run["artifact"])}">{t("public_summary")}</a>'),('result',esc(case['result'][language])),('limits',esc(case['limits'][language]))]
        for label,body in rows: out.append(f'<dt>{t(label)}</dt><dd>{body}</dd>')
        out.append(f'</dl><details><summary>SHA-256</summary><p><code>{protocol["artifact"]["sha256"]}</code></p><p><code>{run["artifact"]["sha256"]}</code></p></details><p><a href="{canonical}?case={identity}#experiment-draft">{t("proposal")}</a></p></article>')
    if view=='full':
        out.append(f'<details class="research-draft" id="experiment-draft"><summary>{t("draft")}</summary><p>{t("draft_help")}</p><p>{t("boundary")}</p><form id="research-draft-form">')
        for name,label in [('source','source'),('hypothesis','question'),('task','task'),('failures','failures'),('scope','scope'),('artifacts','artifacts')]:
            out.append(f'<label for="draft-{name}">{t(label)}</label><textarea id="draft-{name}" name="{name}" rows="3" maxlength="2000" required></textarea>')
        out.append(f'<button class="button" type="submit">{t("review")}</button></form><p id="research-draft-status" role="status"></p><div id="research-draft-output" hidden><label for="research-draft-text">{t("preview")}</label><textarea id="research-draft-text" rows="16" readonly></textarea><div class="research-draft-actions"><a class="button secondary" id="research-draft-download" download="ipvx-experiment-draft.md">{t("download")}</a><a class="button secondary" id="research-draft-submit" href="{REPO}/issues/new?template=experiment.yml">{t("submit")}</a></div></div><noscript><p>{t("draft_help")} <a href="{REPO}/issues/new?template=experiment.yml">{t("submit")}</a></p></noscript></details>')
    else: out.append(f'<p><a href="{canonical}#experiment-draft">{t("proposal")}</a></p>')
    payload=dict(cases=[dict(id=c['id'],title=c['title'][language],hypothesis=c['hypothesis'][language],source=c['source'],url=canonical+'#research-'+c['id']) for c in cases],copy={k:t(k) for k in ('open','source','question','task','failures','scope','artifacts','boundary','ready','long','invalid_source','proposal','required')})
    safe_json=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    out.append(f'<script type="application/json" id="research-links-data">{safe_json}</script><p class="small"><a href="data/research-links.json">{t("json")}</a></p></section>')
    return ''.join(out)

if __name__=='__main__':
    data=load(Path(__file__).resolve().parents[1]);print(f'{len(data["cases"])} curated public research chains verified')
