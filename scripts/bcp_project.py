"""Editorial BCP status from pinned public facts; no service access or launch UI."""
import html
import json
from pathlib import Path

TEXT={
'ru':{
 'title':'BCP 0.2', 'lead':'Идентичность узла, разрешённый путь и пакет — из проверяемого состояния реестра.',
 'summary':'BCP 0.2 — пакетный слой и реестр IPvX. Контракты реестра проверены на живой цепочке Sepolia (REG-001); доставка пакетов по реестру (NET-001) ещё не запускалась.',
 'read':'Открыть BCP 0.2', 'source':'Код и спецификация', 'status':'Состояние разработки',
 'code':'Реализовано в коде', 'code_text':'Формат пакетов, NodeRegistry, TransitPolicy, ConnectionPolicy, EL/CL-адаптер и связь с ядром. Чтения контрактов привязаны к одному финализированному blockHash.',
 'checks':'Проверено офлайн', 'checks_text':'{runner} теста runner и {plan} проверок плана. Временные ключи, EVM в памяти, синтетические заголовки и memory ports; это не измерение сети или финальности цепочки.',
 'pending':'Следующий сетевой опыт', 'pending_text':'NET-001: протокол принят в двух вариантах — на тестовом и на живом состоянии реестра. Нужны ВМ стенда и собственный узел Sepolia; ни одна ещё не выделена. Допуск к запуску закрыт.',
 'idea':'Что меняет BCP', 'identity':'Идентичность', 'identity_text':'NodeRegistry связывает NFT-идентификатор узла с владельцем и ключами. Самостоятельно созданный ключ ещё не даёт права участвовать.',
 'route':'Разрешённый путь', 'route_text':'TransitPolicy и ConnectionPolicy задают допустимые переходы и соединения. Узел проверяет путь по закреплённому состоянию; блокчейн не заменяет канал передачи кадров.',
 'packet':'Формирование пакета', 'packet_text':'Идентификаторы, checkpoint, путь, подписи и зашифрованные данные получают точный двоичный формат. MAC указывает ближайшего соседа, идентификатор — конечный узел.',
 'admission':'Данные до допуска', 'admission_text':'Набор данных готовится отдельно. Подписанный допуск закрепляет его хеш, хеш всего пакета, run ID, время создания и срок свежести. Runner не создаёт новый набор после разрешения.',
 'expiry':'Свежесть — не более 30 минут; фактический срок ограничен самым ранним свежим checkpoint. Истёкший набор нельзя продлить копированием или повторным запуском.',
 'proof':'Проверить источники', 'format':'Формат допуска и ограничения', 'tests':'Отчёт офлайн-проверок', 'request':'Запрос ВМ',
 'boundary':'Границы доказательств', 'boundary_text':'Первый опыт планируется на одной Linux-ВМ: пространства имён A–R–B и два veth-канала. Живой блокчейн, открытое присоединение, физическая Ethernet-подложка и преимущество над IP этим не подтверждены.',
 'mesh':'Mesh — отдельный эксперимент', 'mesh_text':'Исторический стенд проверяет подписанную доставку и смену маршрута у заранее допущенных узлов. Это не реализация блокчейн-реестра BCP. Все его журналы, захваты и прежние выводы сохраняются.',
 'mesh_link':'Открыть Mesh и его доказательства', 'strict':'Записанный strict-LLM-опыт', 'date':'Снимок состояния', 'not_run':'Сетевой опыт не запускался',
},
'en':{
 'title':'BCP 0.2','lead':'Node identity, an authorized path and packet construction from verifiable registry state.',
 'summary':'BCP 0.2 is the IPvX packet layer and registry. The registry contracts were tested on the live Sepolia chain (REG-001); packet delivery driven by the registry (NET-001) has not run.',
 'read':'Explore BCP 0.2','source':'Code and specification','status':'Development status',
 'code':'Implemented in code','code_text':'Packet format, NodeRegistry, TransitPolicy, ConnectionPolicy, the EL/CL adapter and core integration. Contract reads are pinned to one finalized blockHash.',
 'checks':'Checked offline','checks_text':'{runner} runner tests and {plan} plan checks. Temporary keys, an in-memory EVM, synthetic headers and memory ports; no network or chain-finality measurement.',
 'pending':'Next network experiment','pending_text':'NET-001: the protocol is accepted in two variants, on test state and on live registry state. It needs the stand VM and an own Sepolia node; neither is allocated yet. Launch admission is closed.',
 'idea':'What BCP changes','identity':'Identity','identity_text':'NodeRegistry binds a node NFT identifier to its owner and keys. A self-generated key alone does not grant participation.',
 'route':'Authorized path','route_text':'TransitPolicy and ConnectionPolicy define allowed hops and connections. Nodes validate paths against pinned state; a blockchain does not replace the frame transport.',
 'packet':'Packet construction','packet_text':'Identifiers, checkpoint, path, signatures and encrypted data have an exact binary format. MAC identifies the next neighbor; the identifier names the final node.',
 'admission':'Data before admission','admission_text':'The dataset is prepared separately. A signed permit binds its hash, the entire bundle hash, run ID, creation and freshness deadline. The runner does not generate replacement input after authorization.',
 'expiry':'Freshness is at most 30 minutes, further limited by the oldest fresh checkpoint. Copying or restarting cannot extend an expired dataset.',
 'proof':'Inspect the sources','format':'Admission format and limits','tests':'Offline check receipt','request':'VM request',
 'boundary':'Evidence boundaries','boundary_text':'The first experiment is planned inside one Linux VM: A–R–B namespaces and two veth links. This does not establish live-chain operation, open admission, the physical Ethernet underlay or benefit over IP.',
 'mesh':'Mesh is a separate experiment','mesh_text':'The historical stand checks signed delivery and route changes among pre-admitted nodes. It does not implement the BCP blockchain registry. Its journals, captures and previous conclusions are preserved.',
 'mesh_link':'Open Mesh and its evidence','strict':'Recorded strict-LLM experiment','date':'Status snapshot','not_run':'Network experiment has not run',
},
'de':{
 'title':'BCP 0.2','lead':'Knotenidentität, erlaubter Pfad und Paketaufbau aus überprüfbarem Registerzustand.',
 'summary':'BCP 0.2 ist die Paketschicht und Registry von IPvX. Die Registry-Verträge wurden auf der lebenden Sepolia-Chain geprüft (REG-001); die von der Registry gesteuerte Paketzustellung (NET-001) ist noch nicht gelaufen.',
 'read':'BCP 0.2 erkunden','source':'Code und Spezifikation','status':'Entwicklungsstand',
 'code':'Im Code implementiert','code_text':'Paketformat, NodeRegistry, TransitPolicy, ConnectionPolicy, EL/CL-Adapter und Kernintegration. Vertragslesezugriffe sind an einen finalisierten blockHash gebunden.',
 'checks':'Offline geprüft','checks_text':'{runner} Runner-Tests und {plan} Planprüfungen. Temporäre Schlüssel, EVM im Speicher, synthetische Header und Memory-Ports; keine Messung von Netzwerk oder Chain-Finalität.',
 'pending':'Nächstes Netzwerkexperiment','pending_text':'NET-001: Das Protokoll ist in zwei Varianten angenommen, auf Testzustand und auf lebendem Registry-Zustand. Benötigt werden die Stand-VM und ein eigener Sepolia-Knoten; keine von beiden ist bisher zugeteilt. Startfreigabe ist gesperrt.',
 'idea':'Was BCP ändert','identity':'Identität','identity_text':'NodeRegistry bindet eine Knoten-NFT-Kennung an Eigentümer und Schlüssel. Ein selbst erzeugter Schlüssel allein berechtigt nicht zur Teilnahme.',
 'route':'Erlaubter Pfad','route_text':'TransitPolicy und ConnectionPolicy legen erlaubte Übergänge und Verbindungen fest. Knoten prüfen Pfade gegen fixierten Zustand; Blockchain ersetzt nicht den Frame-Transport.',
 'packet':'Paketaufbau','packet_text':'Kennungen, Checkpoint, Pfad, Signaturen und verschlüsselte Daten erhalten ein genaues Binärformat. MAC bezeichnet den nächsten Nachbarn, die Kennung den Zielknoten.',
 'admission':'Daten vor Freigabe','admission_text':'Der Datensatz wird separat vorbereitet. Der signierte Permit bindet Daten- und Paket-Hash, Run-ID, Erstellung und Aktualitätsfrist. Nach der Genehmigung erzeugt der Runner keinen Ersatzdatensatz.',
 'expiry':'Aktualität höchstens 30 Minuten, zusätzlich durch den ältesten frischen Checkpoint begrenzt. Kopieren oder Neustarten verlängert keinen abgelaufenen Datensatz.',
 'proof':'Quellen prüfen','format':'Freigabeformat und Grenzen','tests':'Offline-Prüfbericht','request':'VM-Antrag',
 'boundary':'Beleggrenzen','boundary_text':'Das erste Experiment ist in einer Linux-VM geplant: A–R–B-Namespaces und zwei veth-Verbindungen. Es belegt weder Live-Chain-Betrieb, offenen Zugang, physische Ethernet-Unterlage noch Vorteile gegenüber IP.',
 'mesh':'Mesh ist ein separates Experiment','mesh_text':'Der historische Stand prüft signierte Zustellung und Routenwechsel zwischen vorab zugelassenen Knoten. Er implementiert kein BCP-Blockchain-Register. Journale, Mitschnitte und frühere Schlussfolgerungen bleiben erhalten.',
 'mesh_link':'Mesh und Belege öffnen','strict':'Aufgezeichneter strict-LLM-Versuch','date':'Standaufnahme','not_run':'Netzwerkexperiment nicht gestartet',
},
'es':{
 'title':'BCP 0.2','lead':'Identidad del nodo, ruta autorizada y paquetes desde un estado de registro verificable.',
 'summary':'BCP 0.2 es la capa de paquetes y el registro de IPvX. Los contratos del registro se probaron en la cadena viva Sepolia (REG-001); la entrega de paquetes guiada por el registro (NET-001) aún no se ha ejecutado.',
 'read':'Explorar BCP 0.2','source':'Código y especificación','status':'Estado del desarrollo',
 'code':'Implementado en código','code_text':'Formato de paquetes, NodeRegistry, TransitPolicy, ConnectionPolicy, adaptador EL/CL e integración con el núcleo. Las lecturas de contratos se fijan a un blockHash finalizado.',
 'checks':'Comprobado offline','checks_text':'{runner} pruebas del runner y {plan} comprobaciones del plan. Claves temporales, EVM en memoria, cabeceras sintéticas y puertos en memoria; sin medición de red ni finalidad de cadena.',
 'pending':'Próximo experimento de red','pending_text':'NET-001: el protocolo está aceptado en dos variantes, sobre estado de prueba y sobre el estado vivo del registro. Necesita la VM del banco y un nodo Sepolia propio; ninguna está asignada aún. El permiso de inicio está cerrado.',
 'idea':'Qué cambia BCP','identity':'Identidad','identity_text':'NodeRegistry vincula el identificador NFT de un nodo con su propietario y claves. Una clave autogenerada no concede participación.',
 'route':'Ruta autorizada','route_text':'TransitPolicy y ConnectionPolicy definen saltos y conexiones permitidos. Los nodos verifican rutas contra un estado fijado; blockchain no sustituye el transporte de tramas.',
 'packet':'Formación del paquete','packet_text':'Identificadores, checkpoint, ruta, firmas y datos cifrados tienen un formato binario exacto. MAC indica el vecino siguiente; el identificador, el nodo final.',
 'admission':'Datos antes del permiso','admission_text':'El dataset se prepara por separado. El permiso firmado vincula su hash, el del paquete completo, run ID, creación y vencimiento. El runner no genera datos de sustitución tras la autorización.',
 'expiry':'Vigencia máxima de 30 minutos, limitada además por el checkpoint fresco más antiguo. Copiar o reiniciar no prolonga un dataset vencido.',
 'proof':'Revisar las fuentes','format':'Formato del permiso y límites','tests':'Informe de pruebas offline','request':'Solicitud de VM',
 'boundary':'Límites de las evidencias','boundary_text':'El primer experimento se prevé en una VM Linux: namespaces A–R–B y dos enlaces veth. No demuestra operación en cadena real, acceso abierto, sustrato Ethernet físico ni ventaja sobre IP.',
 'mesh':'Mesh es un experimento separado','mesh_text':'El banco histórico comprueba entrega firmada y cambios de ruta entre nodos previamente admitidos. No implementa el registro blockchain de BCP. Se conservan sus diarios, capturas y conclusiones previas.',
 'mesh_link':'Abrir Mesh y sus evidencias','strict':'Experimento strict-LLM registrado','date':'Instantánea de estado','not_run':'Experimento de red no ejecutado',
}}

def facts(root):
 d=json.loads((Path(root)/'data/bcp-status.json').read_text())
 assert d['network_experiment']=='NOT_RUN' and d['target_preflight']=='NOT_RUN' and d['ready_to_launch'] is False
 assert not any(d[k] for k in ['vm_allocated','open_admission_implemented','physical_underlay_verified','independent_operator_execution'])
 # REG-001 ran on Sepolia in read mode Q; that is registry evidence, not a network-experiment admission.
 assert d['registry_experiment']['status']=='completed' and d['registry_experiment']['read_mode']=='Q'
 checks=json.loads((Path(root)/'runners/bcp02/evidence/checks.json').read_text())
 assert checks['success'] and d['checks']['runner_tests']==checks['tests']
 assert d['admission']['max_state_age_seconds']==1800 and d['admission']['permit_version']==2
 return d


def render(root,language='ru',*,compact=False,lab=False):
 d=facts(root);t=TEXT[language];e=lambda x:html.escape(str(x),quote=True)
 page='https://ipvx.org/bcp.html' if lab else ('bcp.html' if language=='ru' else 'bcp.'+language+'.html')
 refs=d['references'];repo='https://github.com/relcom-technologies/ipvx-research'
 opening=f'<div class="bcp-intro"><h2>{e(t["title"] if compact else t["status"])}</h2><p class="lead">{e(t["summary"])}</p><p class="bcp-date">{e(t["date"])}: <time datetime="{e(d["as_of"])}">{e(d["as_of"])}</time></p></div>'
 rows=''.join(f'<div class="bcp-row"><h3>{e(t[k])}</h3><p>{e(t[k+"_text"].format(runner=d["checks"]["runner_tests"],plan=d["checks"]["plan_tests"]))}</p></div>' for k in ['code','checks','pending'])
 output=f'<section class="bcp-project section" data-bcp-mode="{('compact' if compact else 'full')}" data-i18n-fixed>{opening}<div class="bcp-status-list">{rows}</div>'
 if compact:return output+f'<p class="bcp-links"><a class="button" href="{page}">{e(t["read"])}</a><a href="{e(refs["runner"])}">{e(t["source"])}</a></p></section>'
 output+=f'<div class="bcp-explanation"><h2>{e(t["idea"])}</h2><ol class="bcp-lifecycle">'+''.join(f'<li><h3>{e(t[k])}</h3><p>{e(t[k+"_text"])}</p></li>' for k in ['identity','route','packet'])+'</ol></div>'
 output+=f'<div class="bcp-admission"><h2>{e(t["admission"])}</h2><p>{e(t["admission_text"])}</p><p>{e(t["expiry"])}</p><details><summary>{e(t["format"])}</summary><p><code>dataset_sha256 · bundle_sha256 · run_id · created_at · expires_at</code></p><p><a href="{repo}/blob/{d["references"]["dataset_admission_revision"]}/runners/bcp02/dataset-admission.md">{e(t["format"])}</a></p></details></div>'
 output+=f'<div class="bcp-boundary"><h2>{e(t["boundary"])}</h2><p>{e(t["boundary_text"])}</p></div><div class="bcp-history"><h2>{e(t["mesh"])}</h2><p>{e(t["mesh_text"])}</p><p><a href="{("#mesh" if lab else refs["lab_mesh"])}">{e(t["mesh_link"])}</a> · <a href="https://ipvx.org/architecture.html#research-network">{e(t["strict"])}</a></p></div>'
 output+=f'<div class="bcp-links"><h2>{e(t["proof"])}</h2><a href="{e(refs["specification"])}">{e(t["source"])}</a><a href="{repo}/blob/{refs["dataset_admission_revision"]}/runners/bcp02/evidence/checks.json">{e(t["tests"])}</a><a href="{e(refs["resource_request"])}">{e(t["request"])}</a></div></section>'
 return output


def header(language='ru'):
 t=TEXT[language]
 return '<div class="bcp-header" data-i18n-fixed><h1>BCP 0.2</h1><p class="lead">'+html.escape(t['lead'])+'</p></div>'
