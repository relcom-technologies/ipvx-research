"""Editorial BCP status from pinned public facts; no service access or launch UI."""
import html
import hashlib
import json
from pathlib import Path

TEXT={
'ru':{
 'title':'BCP 0.2', 'lead':'Идентичность узла, разрешённый путь и пакет — из проверяемого состояния реестра.',
 'summary':'BCP 0.2 — пакетный слой и реестр IPvX. Контракты реестра проверены на живой цепочке Sepolia: REG-001 шёл в режиме чтения Q, а R1 закрыт 2026-11-06 чтением REG-001-LC через лёгкий клиент — по заменённому критерию, текущему состоянию; значения S1–S3 остаются наблюдениями режима Q. Доставка пакетов по реестру прошла на тестовом состоянии реестра (NET-001-F, PASS 2026-11-08); на живом состоянии (NET-001-L) она ещё не запускалась.',
 'read':'Открыть BCP 0.2', 'source':'Код и спецификация', 'status':'Состояние разработки',
 'code':'Реализовано в коде', 'code_text':'Формат пакетов, NodeRegistry, TransitPolicy, ConnectionPolicy, EL/CL-адаптер и связь с ядром. Чтения контрактов привязаны к одному финализированному blockHash.',
 'checks':'Проверено офлайн', 'checks_text':'{runner} {runner_ru} runner и {plan} {plan_ru} плана. Временные ключи, EVM в памяти, синтетические заголовки и memory ports; это не измерение сети или финальности цепочки.',
 'pending':'Следующий сетевой опыт', 'pending_text':'NET-001-F прошёл 2026-11-08 на отдельной ВМ стенда: прогон bcp-net001-run-0003 по подписанному владельцем разрешению дал PASS во всех 14 вариантах проверок, независимый верификатор подтвердил итог. Это доставка кадров Ethernet между тремя узлами на настоящем ядре Linux при синтетическом состоянии реестра: финальность цепочки, физическая линия и независимые операторы этим не проверены. Следующий опыт — NET-001-L на живом состоянии реестра. Он читает реестр через лёгкий клиент Helios: режим LC заменил режим V 2026-11-05, собственный узел Sepolia не нужен. Helios на стенде пока не работает, а правило обновления снимка в NET-001-L остаётся открытым условием. Допуск к новому запуску закрыт: каждый прогон требует отдельного подписанного разрешения владельца.',
 'idea':'Что меняет BCP', 'identity':'Идентичность', 'identity_text':'NodeRegistry связывает NFT-идентификатор узла с владельцем и ключами. Самостоятельно созданный ключ ещё не даёт права участвовать.',
 'route':'Разрешённый путь', 'route_text':'TransitPolicy и ConnectionPolicy задают допустимые переходы и соединения. Узел проверяет путь по закреплённому состоянию; блокчейн не заменяет канал передачи кадров.',
 'packet':'Формирование пакета', 'packet_text':'Идентификаторы, checkpoint, путь, подписи и зашифрованные данные получают точный двоичный формат. MAC указывает ближайшего соседа, идентификатор — конечный узел.',
 'admission':'Данные до допуска', 'admission_text':'Набор данных готовится отдельно. Подписанный допуск закрепляет его хеш, хеш всего пакета, run ID, время создания и срок свежести. Runner не создаёт новый набор после разрешения.',
 'expiry':'Свежесть — не более 30 минут; фактический срок ограничен самым ранним свежим checkpoint. Истёкший набор нельзя продлить копированием или повторным запуском.',
 'proof':'Проверить источники', 'format':'Формат допуска и ограничения', 'tests':'Отчёт офлайн-проверок', 'request':'Запрос ВМ','lc_read':'Чтение REG-001-LC',
 'boundary':'Границы доказательств', 'boundary_text':'Первый опыт, NET-001-F, прошёл на одной Linux-ВМ: пространства имён A–R–B и два veth-канала. Живой блокчейн, открытое присоединение, физическая Ethernet-подложка и преимущество над IP этим не подтверждены.',
 'mesh':'Mesh — отдельный эксперимент', 'mesh_text':'Исторический стенд проверяет подписанную доставку и смену маршрута у заранее допущенных узлов. Это не реализация блокчейн-реестра BCP. Все его журналы, захваты и прежние выводы сохраняются.',
 'mesh_link':'Открыть Mesh и его доказательства', 'strict':'Записанный strict-LLM-опыт', 'date':'Снимок состояния', 'not_run':'Сетевой опыт не запускался',
},
'en':{
 'title':'BCP 0.2','lead':'Node identity, an authorized path and packet construction from verifiable registry state.',
 'summary':'BCP 0.2 is the IPvX packet layer and registry. The registry contracts were tested on the live Sepolia chain: REG-001 ran in read mode Q, and R1 was closed on 2026-11-06 by the REG-001-LC light-client read on its replacement criterion, the current state; the S1–S3 values remain mode Q observations. Packet delivery driven by the registry passed on test registry state (NET-001-F, PASS on 2026-11-08); on live state (NET-001-L) it has not run.',
 'read':'Explore BCP 0.2','source':'Code and specification','status':'Development status',
 'code':'Implemented in code','code_text':'Packet format, NodeRegistry, TransitPolicy, ConnectionPolicy, the EL/CL adapter and core integration. Contract reads are pinned to one finalized blockHash.',
 'checks':'Checked offline','checks_text':'{runner} runner tests and {plan} plan checks. Temporary keys, an in-memory EVM, synthetic headers and memory ports; no network or chain-finality measurement.',
 'pending':'Next network experiment','pending_text':'NET-001-F passed on 2026-11-08 on the separate stand VM: run bcp-net001-run-0003, under a permit signed by the owner, gave PASS in all 14 check variants, and the independent verifier confirmed the result. This is Ethernet frame delivery between three nodes on a real Linux kernel with synthetic registry state: it does not test chain finality, a physical link or independent operators. The next experiment is NET-001-L on live registry state. It reads the registry through the Helios light client: mode LC replaced mode V on 2026-11-05, so no own Sepolia node is needed. Helios is not running on the stand yet, and the snapshot refresh rule in NET-001-L remains an open condition. Admission to a new launch is closed: every run needs its own permit signed by the owner.',
 'idea':'What BCP changes','identity':'Identity','identity_text':'NodeRegistry binds a node NFT identifier to its owner and keys. A self-generated key alone does not grant participation.',
 'route':'Authorized path','route_text':'TransitPolicy and ConnectionPolicy define allowed hops and connections. Nodes validate paths against pinned state; a blockchain does not replace the frame transport.',
 'packet':'Packet construction','packet_text':'Identifiers, checkpoint, path, signatures and encrypted data have an exact binary format. MAC identifies the next neighbor; the identifier names the final node.',
 'admission':'Data before admission','admission_text':'The dataset is prepared separately. A signed permit binds its hash, the entire bundle hash, run ID, creation and freshness deadline. The runner does not generate replacement input after authorization.',
 'expiry':'Freshness is at most 30 minutes, further limited by the oldest fresh checkpoint. Copying or restarting cannot extend an expired dataset.',
 'proof':'Inspect the sources','format':'Admission format and limits','tests':'Offline check receipt','request':'VM request','lc_read':'REG-001-LC read',
 'boundary':'Evidence boundaries','boundary_text':'The first experiment, NET-001-F, passed inside one Linux VM: A–R–B namespaces and two veth links. This does not establish live-chain operation, open admission, the physical Ethernet underlay or benefit over IP.',
 'mesh':'Mesh is a separate experiment','mesh_text':'The historical stand checks signed delivery and route changes among pre-admitted nodes. It does not implement the BCP blockchain registry. Its journals, captures and previous conclusions are preserved.',
 'mesh_link':'Open Mesh and its evidence','strict':'Recorded strict-LLM experiment','date':'Status snapshot','not_run':'Network experiment has not run',
},
'de':{
 'title':'BCP 0.2','lead':'Knotenidentität, erlaubter Pfad und Paketaufbau aus überprüfbarem Registerzustand.',
 'summary':'BCP 0.2 ist die Paketschicht und Registry von IPvX. Die Registry-Verträge wurden auf der lebenden Sepolia-Chain geprüft: REG-001 lief im Lesemodus Q, und R1 wurde am 2026-11-06 durch die Light-Client-Lesung REG-001-LC nach dem Ersatzkriterium, dem aktuellen Zustand, geschlossen; die Werte S1–S3 bleiben Beobachtungen im Modus Q. Die von der Registry gesteuerte Paketzustellung hat auf Test-Registry-Zustand bestanden (NET-001-F, PASS am 2026-11-08); auf lebendem Zustand (NET-001-L) ist sie noch nicht gelaufen.',
 'read':'BCP 0.2 erkunden','source':'Code und Spezifikation','status':'Entwicklungsstand',
 'code':'Im Code implementiert','code_text':'Paketformat, NodeRegistry, TransitPolicy, ConnectionPolicy, EL/CL-Adapter und Kernintegration. Vertragslesezugriffe sind an einen finalisierten blockHash gebunden.',
 'checks':'Offline geprüft','checks_text':'{runner} Runner-Tests und {plan} Planprüfungen. Temporäre Schlüssel, EVM im Speicher, synthetische Header und Memory-Ports; keine Messung von Netzwerk oder Chain-Finalität.',
 'pending':'Nächstes Netzwerkexperiment','pending_text':'NET-001-F hat am 2026-11-08 auf der separaten Stand-VM bestanden: Der Lauf bcp-net001-run-0003 mit einer vom Eigentümer signierten Genehmigung ergab PASS in allen 14 Prüfvarianten, und der unabhängige Verifier hat das Ergebnis bestätigt. Das ist die Zustellung von Ethernet-Frames zwischen drei Knoten auf einem echten Linux-Kernel mit synthetischem Registry-Zustand: Chain-Finalität, eine physische Leitung und unabhängige Betreiber werden damit nicht geprüft. Das nächste Experiment ist NET-001-L auf lebendem Registry-Zustand. Es liest die Registry über den Helios-Light-Client: Modus LC hat Modus V am 2026-11-05 ersetzt, ein eigener Sepolia-Knoten ist nicht nötig. Helios läuft auf dem Stand noch nicht, und die Aktualisierungsregel für Snapshots in NET-001-L bleibt eine offene Bedingung. Die Freigabe für einen neuen Start ist gesperrt: Jeder Lauf braucht eine eigene vom Eigentümer signierte Genehmigung.',
 'idea':'Was BCP ändert','identity':'Identität','identity_text':'NodeRegistry bindet eine Knoten-NFT-Kennung an Eigentümer und Schlüssel. Ein selbst erzeugter Schlüssel allein berechtigt nicht zur Teilnahme.',
 'route':'Erlaubter Pfad','route_text':'TransitPolicy und ConnectionPolicy legen erlaubte Übergänge und Verbindungen fest. Knoten prüfen Pfade gegen fixierten Zustand; Blockchain ersetzt nicht den Frame-Transport.',
 'packet':'Paketaufbau','packet_text':'Kennungen, Checkpoint, Pfad, Signaturen und verschlüsselte Daten erhalten ein genaues Binärformat. MAC bezeichnet den nächsten Nachbarn, die Kennung den Zielknoten.',
 'admission':'Daten vor Freigabe','admission_text':'Der Datensatz wird separat vorbereitet. Der signierte Permit bindet Daten- und Paket-Hash, Run-ID, Erstellung und Aktualitätsfrist. Nach der Genehmigung erzeugt der Runner keinen Ersatzdatensatz.',
 'expiry':'Aktualität höchstens 30 Minuten, zusätzlich durch den ältesten frischen Checkpoint begrenzt. Kopieren oder Neustarten verlängert keinen abgelaufenen Datensatz.',
 'proof':'Quellen prüfen','format':'Freigabeformat und Grenzen','tests':'Offline-Prüfbericht','request':'VM-Antrag','lc_read':'Lesung REG-001-LC',
 'boundary':'Beleggrenzen','boundary_text':'Das erste Experiment, NET-001-F, hat in einer Linux-VM bestanden: A–R–B-Namespaces und zwei veth-Verbindungen. Es belegt weder Live-Chain-Betrieb, offenen Zugang, physische Ethernet-Unterlage noch Vorteile gegenüber IP.',
 'mesh':'Mesh ist ein separates Experiment','mesh_text':'Der historische Stand prüft signierte Zustellung und Routenwechsel zwischen vorab zugelassenen Knoten. Er implementiert kein BCP-Blockchain-Register. Journale, Mitschnitte und frühere Schlussfolgerungen bleiben erhalten.',
 'mesh_link':'Mesh und Belege öffnen','strict':'Aufgezeichneter strict-LLM-Versuch','date':'Standaufnahme','not_run':'Netzwerkexperiment nicht gestartet',
},
'es':{
 'title':'BCP 0.2','lead':'Identidad del nodo, ruta autorizada y paquetes desde un estado de registro verificable.',
 'summary':'BCP 0.2 es la capa de paquetes y el registro de IPvX. Los contratos del registro se probaron en la cadena viva Sepolia: REG-001 se ejecutó en modo de lectura Q, y R1 se cerró el 2026-11-06 con la lectura REG-001-LC mediante cliente ligero, según su criterio sustitutivo, el estado actual; los valores S1–S3 siguen siendo observaciones del modo Q. La entrega de paquetes guiada por el registro pasó sobre estado de prueba del registro (NET-001-F, PASS el 2026-11-08); sobre estado vivo (NET-001-L) aún no se ha ejecutado.',
 'read':'Explorar BCP 0.2','source':'Código y especificación','status':'Estado del desarrollo',
 'code':'Implementado en código','code_text':'Formato de paquetes, NodeRegistry, TransitPolicy, ConnectionPolicy, adaptador EL/CL e integración con el núcleo. Las lecturas de contratos se fijan a un blockHash finalizado.',
 'checks':'Comprobado offline','checks_text':'{runner} pruebas del runner y {plan} comprobaciones del plan. Claves temporales, EVM en memoria, cabeceras sintéticas y puertos en memoria; sin medición de red ni finalidad de cadena.',
 'pending':'Próximo experimento de red','pending_text':'NET-001-F pasó el 2026-11-08 en la VM separada del banco: la ejecución bcp-net001-run-0003, con un permiso firmado por el propietario, dio PASS en las 14 variantes de comprobación, y el verificador independiente confirmó el resultado. Es la entrega de tramas Ethernet entre tres nodos sobre un kernel Linux real con estado sintético del registro: no prueba la finalidad de la cadena, un enlace físico ni operadores independientes. El siguiente experimento es NET-001-L sobre el estado vivo del registro. Lee el registro con el cliente ligero Helios: el modo LC sustituyó al modo V el 2026-11-05, así que no hace falta un nodo Sepolia propio. Helios aún no se ejecuta en el banco, y la regla de actualización de la instantánea en NET-001-L sigue siendo una condición abierta. El acceso a un nuevo inicio está cerrado: cada ejecución necesita su propio permiso firmado por el propietario.',
 'idea':'Qué cambia BCP','identity':'Identidad','identity_text':'NodeRegistry vincula el identificador NFT de un nodo con su propietario y claves. Una clave autogenerada no concede participación.',
 'route':'Ruta autorizada','route_text':'TransitPolicy y ConnectionPolicy definen saltos y conexiones permitidos. Los nodos verifican rutas contra un estado fijado; blockchain no sustituye el transporte de tramas.',
 'packet':'Formación del paquete','packet_text':'Identificadores, checkpoint, ruta, firmas y datos cifrados tienen un formato binario exacto. MAC indica el vecino siguiente; el identificador, el nodo final.',
 'admission':'Datos antes del permiso','admission_text':'El dataset se prepara por separado. El permiso firmado vincula su hash, el del paquete completo, run ID, creación y vencimiento. El runner no genera datos de sustitución tras la autorización.',
 'expiry':'Vigencia máxima de 30 minutos, limitada además por el checkpoint fresco más antiguo. Copiar o reiniciar no prolonga un dataset vencido.',
 'proof':'Revisar las fuentes','format':'Formato del permiso y límites','tests':'Informe de pruebas offline','request':'Solicitud de VM','lc_read':'Lectura REG-001-LC',
 'boundary':'Límites de las evidencias','boundary_text':'El primer experimento, NET-001-F, pasó en una VM Linux: namespaces A–R–B y dos enlaces veth. No demuestra operación en cadena real, acceso abierto, sustrato Ethernet físico ni ventaja sobre IP.',
 'mesh':'Mesh es un experimento separado','mesh_text':'El banco histórico comprueba entrega firmada y cambios de ruta entre nodos previamente admitidos. No implementa el registro blockchain de BCP. Se conservan sus diarios, capturas y conclusiones previas.',
 'mesh_link':'Abrir Mesh y sus evidencias','strict':'Experimento strict-LLM registrado','date':'Instantánea de estado','not_run':'Experimento de red no ejecutado',
}}

def facts(root):
 d=json.loads((Path(root)/'data/bcp-status.json').read_text())
 assert d['ready_to_launch'] is False
 # NET-001-F ran once under an owner-signed permit; the record keeps its limits. NET-001-L has not run.
 f=d['net001_f'];record=json.loads((Path(root)/f['record']).read_text())
 assert d['network_experiment']=='NET-001-F_PASS' and f['outcome']==record['outcome']=='PASS' and f['run_id']==record['run_id']
 assert record['verifier_outcome']=='PASS' and record['permit_used'] is True and record['transactions']==0
 assert not any(record[k] for k in ('real_chain_finality','physical_ethernet','independent_operators'))
 assert f['cases']==len(record['case_results'])==14 and all(c['pass_criteria_met'] for c in record['case_results'].values())
 assert d['net001_l']=='NOT_RUN'
 assert not any(d[k] for k in ['open_admission_implemented','physical_underlay_verified','independent_operator_execution'])
 # The stand VM exists; what ran on it is the permit-free kernel rehearsal, never a network measurement.
 stand=d['stand'];record=json.loads((Path(root)/stand['record']).read_text())
 assert d['vm_allocated'] is True and stand['rehearsal']==record['outcome']=='REHEARSAL_PASS' and stand['rehearsal_runs']==len(record['runs'])
 assert record['network_measurement'] is False and record['permit_used'] is False and record['transactions']==0 and stand['network_measurement'] is False
 scope=d['source_scope'];manifest=json.loads((Path(root)/'runners/bcp02/manifest.json').read_text())
 assert scope['pinned_files']==len(manifest['files'])
 # The owner confirmed the runner pins; the ack covers every pin except launch-config.json, which carries it.
 config=json.loads((Path(root)/'runners/bcp02/launch-config.json').read_text())
 canonical=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
 assert scope['runner_scope_sha256']==hashlib.sha256(b'IPVX-BCP02-NET-001-F/runner3\0'+canonical).hexdigest()
 assert scope['owner_confirmed'] is True and config['owner_public_key'] and config['owner_scope_ack']['owner_statement']
 assert scope['reviewed_pins_sha256']==config['owner_scope_ack']['reviewed_pins_sha256']
 assert config['run_dataset'] is None and config['accepted_window'] is None and config['owner_launch_decision'] is None
 # REG-001 ran on Sepolia in read mode Q; that is registry evidence, not a network-experiment admission.
 assert d['registry_experiment']['status']=='completed' and d['registry_experiment']['read_mode']=='Q'
 # R1 was closed by the REG-001-LC read on the replacement criterion; S1-S3 remain mode Q observations.
 lc=d['registry_lc_read'];result=json.loads((Path(root)/lc['result']).read_text())
 assert lc['status']=='completed' and lc['closes']=='R1' and lc['read_mode']==result['read_mode']=='LC' and lc['outcome']==result['outcome']=='PASS'
 assert lc['read_on']==result['started_at'][:10] and lc['criterion']=='current_state' and lc['s1_s3_read_mode']=='Q'
 src=d['state_source']
 assert src['read_mode']=='LC' and src['replaces']=='V' and src['own_node_required'] is False
 assert src['helios_running_on_stand'] is False and src['snapshot_refresh_rule']=='open'
 checks=json.loads((Path(root)/'runners/bcp02/evidence/checks.json').read_text())
 assert checks['success'] and d['checks']['runner_tests']==checks['tests']
 assert d['admission']['max_state_age_seconds']==1800 and d['admission']['permit_version']==2
 return d


def ru_count(n,one,few,many):
 """Russian noun form after the number n: 1 тест, 2 теста, 5 тестов, 11 тестов, 21 тест."""
 return one if n%10==1 and n%100!=11 else few if 2<=n%10<=4 and not 12<=n%100<=14 else many


def render(root,language='ru',*,compact=False,lab=False):
 d=facts(root);t=TEXT[language];e=lambda x:html.escape(str(x),quote=True)
 page='https://ipvx.org/bcp.html' if lab else ('bcp.html' if language=='ru' else 'bcp.'+language+'.html')
 refs=d['references'];repo='https://github.com/relcom-technologies/ipvx-research'
 opening=f'<div class="bcp-intro"><h2>{e(t["title"] if compact else t["status"])}</h2><p class="lead">{e(t["summary"])}</p><p class="bcp-date">{e(t["date"])}: <time datetime="{e(d["as_of"])}">{e(d["as_of"])}</time></p></div>'
 r,p=d['checks']['runner_tests'],d['checks']['plan_tests']
 counts=dict(runner=r,plan=p,runner_ru=ru_count(r,'тест','теста','тестов'),plan_ru=ru_count(p,'проверка','проверки','проверок'))
 rows=''.join(f'<div class="bcp-row"><h3>{e(t[k])}</h3><p>{e(t[k+"_text"].format(**counts))}</p></div>' for k in ['code','checks','pending'])
 output=f'<section class="bcp-project section" data-bcp-mode="{('compact' if compact else 'full')}" data-i18n-fixed>{opening}<div class="bcp-status-list">{rows}</div>'
 if compact:return output+f'<p class="bcp-links"><a class="button" href="{page}">{e(t["read"])}</a><a href="{e(refs["runner"])}">{e(t["source"])}</a></p></section>'
 output+=f'<div class="bcp-explanation"><h2>{e(t["idea"])}</h2><ol class="bcp-lifecycle">'+''.join(f'<li><h3>{e(t[k])}</h3><p>{e(t[k+"_text"])}</p></li>' for k in ['identity','route','packet'])+'</ol></div>'
 output+=f'<div class="bcp-admission"><h2>{e(t["admission"])}</h2><p>{e(t["admission_text"])}</p><p>{e(t["expiry"])}</p><details><summary>{e(t["format"])}</summary><p><code>dataset_sha256 · bundle_sha256 · run_id · created_at · expires_at</code></p><p><a href="{repo}/blob/{d["references"]["dataset_admission_revision"]}/runners/bcp02/dataset-admission.md">{e(t["format"])}</a></p></details></div>'
 output+=f'<div class="bcp-boundary"><h2>{e(t["boundary"])}</h2><p>{e(t["boundary_text"])}</p></div><div class="bcp-history"><h2>{e(t["mesh"])}</h2><p>{e(t["mesh_text"])}</p><p><a href="{("#mesh" if lab else refs["lab_mesh"])}">{e(t["mesh_link"])}</a> · <a href="https://ipvx.org/architecture.html#research-network">{e(t["strict"])}</a></p></div>'
 output+=f'<div class="bcp-links"><h2>{e(t["proof"])}</h2><a href="{e(refs["specification"])}">{e(t["source"])}</a><a href="{repo}/blob/{refs["dataset_admission_revision"]}/runners/bcp02/evidence/checks.json">{e(t["tests"])}</a><a href="{e(refs["registry_lc_read"])}">{e(t["lc_read"])}</a><a href="{e(refs["resource_request"])}">{e(t["request"])}</a></div></section>'
 return output


def header(language='ru'):
 t=TEXT[language]
 return '<div class="bcp-header" data-i18n-fixed><h1>BCP 0.2</h1><p class="lead">'+html.escape(t['lead'])+'</p></div>'
