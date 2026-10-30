"""Evidence-bound, localized explanation of the measured strict-agent topology."""
import html
import json
import hashlib
from pathlib import Path

TEXT = {
'ru': {
 'title':'Как устроен проверенный стенд', 'intro':'Три гостевые ОС на разных физических машинах. У A и B работают локальные языковые модели; R1 пересылает сообщения между ними.',
 'scope':'Исследовательская визуализация записанного опыта. Это не прямой эфир; темп анимации условный.',
 'host':'Физическая машина', 'guest':'Гостевая ОС без INET и IPv6', 'model':'Локальная модель', 'router':'Служба маршрутизации', 'service':'IPvX-служба', 'socket':'Модель вызывается в процессе агента', 'id':'Собственный ключ и ID', 'ethernet':'Кадры Ethernet · EtherType 0x88B5',
 'management':'Внешнее управление, запуск виртуальных машин и этот сайт используют IP. Общая физическая сеть также переносит управляющий IP-трафик. Нативная доставка внутри гостевых ОС не использует IP или DNS.',
 'play':'Показать обмен', 'pause':'Остановить', 'step':'Этапы обмена', 'states':[
 ('A готовит задачу','Модель A готовит ответ. IPvX-служба адресует сообщение ID агента B, подписывает и шифрует его.'),
 ('Запрос проходит через R1','A отправляет кадр соседу R1; R1 выбирает следующий переход к B. Квитанция подтверждает приём, а не правильность результата.'),
 ('B проверяет и отвечает','Модель B получает задачу и формирует рецензию. Ответ отправляется отдельным сообщением через R1 обратно к A.'),
 ('A формирует итог','Модель A использует рецензию для итогового ответа. Оценка поля решения совпала с эталоном в двух из четырёх задач.')],
 'select':'Этап', 'facts':'Что подтверждено', 'facts_text':'{tasks} задачи и {deliveries} подтверждённых доставок в нативном режиме: {echo} эхо-проверок и {messages} сообщений по задачам. IP-контроль использовал те же прикладные переходы.',
 'missing':'Время на каждом переходе, ожидание в очереди и причина выбора маршрута в опубликованной записи отсутствуют. Показ пути не измеряет их.',
 'record':'Открыть запись задач и сообщений', 'manifest':'Что записано и чего не хватает', 'revision':'Версия кода опыта', 'future':'Внешние сети, открытый допуск, масштабная маршрутизация и физические серверы без IP на bare metal остаются отдельными непроверенными задачами.'},
'en': {
 'title':'Inside the tested setup','intro':'Three guest operating systems on separate physical machines. A and B run local language models; R1 forwards their messages.',
 'scope':'Research illustration of a recorded experiment. This is not a live feed; animation timing is illustrative.',
 'host':'Physical machine','guest':'Guest OS without INET or IPv6','model':'Local model','router':'Routing service','service':'IPvX service','socket':'Model called within agent process','id':'Own key and ID','ethernet':'Ethernet frames · EtherType 0x88B5',
 'management':'External management, virtual machine startup and this website use IP. The shared physical network also carries management IP traffic. Native delivery within the guest systems uses neither IP nor DNS.',
 'play':'Play exchange','pause':'Stop','step':'Exchange stages','states':[
 ('A prepares the task','Model A prepares a response. The IPvX service addresses the message to B’s ID, signs and encrypts it.'),
 ('Request travels through R1','A sends a frame to neighbor R1; R1 selects the next hop to B. A receipt confirms admission, not correctness.'),
 ('B reviews and replies','Model B receives the task and produces a review. The reply travels as a separate message through R1 back to A.'),
 ('A produces the final answer','Model A uses the review for its final answer. The decision field matched the reference in two of four tasks.')],
 'select':'Stage','facts':'What was verified','facts_text':'{tasks} tasks and {deliveries} signed deliveries in native mode: {echo} echo checks and {messages} task messages. The IP control used the same application hops.',
 'missing':'Per-hop timing, queue wait and the reason for route selection are absent from the public record. The animation does not measure them.',
 'record':'Inspect tasks and messages','manifest':'Recorded and missing evidence','revision':'Experiment code revision','future':'External networks, open admission, large-scale routing and bare-metal physical servers without IP remain separate untested goals.'},
'de': {
 'title':'Aufbau des geprüften Versuchs','intro':'Drei Gastbetriebssysteme auf getrennten physischen Maschinen. Auf A und B laufen lokale Sprachmodelle; R1 leitet ihre Nachrichten weiter.',
 'scope':'Forschungsdarstellung eines aufgezeichneten Versuchs. Kein Livebild; das Tempo der Animation ist illustrativ.',
 'host':'Physische Maschine','guest':'Gastbetriebssystem ohne INET und IPv6','model':'Lokales Modell','router':'Routingdienst','service':'IPvX-Dienst','socket':'Modellaufruf im Agentenprozess','id':'Eigener Schlüssel und eigene ID','ethernet':'Ethernet-Frames · EtherType 0x88B5',
 'management':'Externe Verwaltung, Start der virtuellen Maschinen und diese Website nutzen IP. Das gemeinsame physische Netz überträgt ebenfalls IP-Verwaltungsverkehr. Die native Zustellung innerhalb der Gastsysteme nutzt weder IP noch DNS.',
 'play':'Austausch zeigen','pause':'Anhalten','step':'Schritte des Austauschs','states':[
 ('A bereitet die Aufgabe vor','Modell A erstellt eine Antwort. Der IPvX-Dienst adressiert die Nachricht an die ID von B, signiert und verschlüsselt sie.'),
 ('Anfrage über R1','A sendet einen Frame an Nachbar R1; R1 wählt den nächsten Übergang zu B. Eine Quittung bestätigt die Annahme, nicht die Richtigkeit.'),
 ('B prüft und antwortet','Modell B erhält die Aufgabe und erstellt eine Rezension. Die Antwort reist als separate Nachricht über R1 zurück zu A.'),
 ('A erstellt das Ergebnis','Modell A nutzt die Rezension für seine Antwort. Das Entscheidungsfeld stimmte bei zwei von vier Aufgaben mit der Referenz überein.')],
 'select':'Schritt','facts':'Was überprüft wurde','facts_text':'{tasks} Aufgaben und {deliveries} bestätigte Zustellungen im nativen Modus: {echo} Echo-Prüfungen und {messages} Aufgabennachrichten. Die IP-Kontrolle nutzte dieselben Anwendungsschritte.',
 'missing':'Zeiten je Übergang, Wartezeit in der Queue und der Grund der Routenwahl fehlen in der öffentlichen Aufzeichnung. Die Animation misst sie nicht.',
 'record':'Aufgaben und Nachrichten untersuchen','manifest':'Vorhandene und fehlende Daten','revision':'Codeversion des Versuchs','future':'Externe Netze, offener Zugang, Routing in großem Maßstab und physische Bare-Metal-Server ohne IP bleiben separate ungeprüfte Ziele.'},
'es': {
 'title':'Cómo funciona el entorno probado','intro':'Tres sistemas invitados en máquinas físicas distintas. A y B ejecutan modelos de lenguaje locales; R1 reenvía sus mensajes.',
 'scope':'Representación de un experimento registrado. No es una transmisión en vivo; el ritmo de la animación es ilustrativo.',
 'host':'Máquina física','guest':'Sistema invitado sin INET ni IPv6','model':'Modelo local','router':'Servicio de encaminamiento','service':'Servicio IPvX','socket':'Modelo invocado en el proceso del agente','id':'Clave e ID propios','ethernet':'Tramas Ethernet · EtherType 0x88B5',
 'management':'La administración externa, el inicio de las máquinas virtuales y este sitio usan IP. La red física compartida también transporta tráfico IP de administración. La entrega nativa dentro de los invitados no usa IP ni DNS.',
 'play':'Mostrar intercambio','pause':'Detener','step':'Etapas del intercambio','states':[
 ('A prepara la tarea','El modelo A prepara una respuesta. El servicio IPvX dirige el mensaje al ID de B, lo firma y lo cifra.'),
 ('La petición pasa por R1','A envía una trama al vecino R1; R1 elige el siguiente salto a B. El recibo confirma la admisión, no la corrección.'),
 ('B revisa y responde','El modelo B recibe la tarea y produce una revisión. La respuesta viaja como mensaje separado por R1 de vuelta a A.'),
 ('A produce la respuesta final','El modelo A utiliza la revisión para su respuesta final. El campo de decisión coincidió con la referencia en dos de las cuatro tareas.')],
 'select':'Etapa','facts':'Qué se verificó','facts_text':'{tasks} tareas y {deliveries} entregas confirmadas en modo nativo: {echo} pruebas de eco y {messages} mensajes de tareas. El control IP utilizó los mismos saltos de aplicación.',
 'missing':'El registro público no incluye tiempos por salto, espera en cola ni motivo de elección de ruta. La animación no los mide.',
 'record':'Examinar tareas y mensajes','manifest':'Datos registrados y ausentes','revision':'Revisión del código del experimento','future':'Las redes externas, la admisión abierta, el encaminamiento a gran escala y los servidores físicos bare metal sin IP siguen siendo objetivos no probados.'}}

MODE_COPY={'ru': ('Режим: записанный strict-LLM-опыт · A–R1–B · 3 гостя / 3 физических хоста · 2 локальные модели.', 'Отдельно: живой mesh — 5 ВМ / 3 физических хоста, без LLM, с административным IP в ОС. У обоих нативные данные и маршруты идут в Ethernet 0x88B5; веб-панель и управление используют HTTPS/IP.', 'Открыть живой mesh и его версию'), 'en': ('Mode: recorded strict-LLM experiment · A–R1–B · 3 guests / 3 physical hosts · 2 local models.', 'Separate live mesh: 5 VMs / 3 physical hosts, without LLMs, with management IP in the OS. Both carry native data and routes over Ethernet 0x88B5; the web view and management use HTTPS/IP.', 'Open the live mesh and its revision'), 'de': ('Modus: aufgezeichneter strict-LLM-Versuch · A–R1–B · 3 Gäste / 3 physische Hosts · 2 lokale Modelle.', 'Separates Live-Mesh: 5 VMs / 3 physische Hosts, ohne LLMs, mit Verwaltungs-IP im Betriebssystem. Beide übertragen native Daten und Routen über Ethernet 0x88B5; Webansicht und Verwaltung nutzen HTTPS/IP.', 'Live-Mesh und dessen Version öffnen'), 'es': ('Modo: experimento strict-LLM registrado · A–R1–B · 3 invitados / 3 hosts físicos · 2 modelos locales.', 'Mesh en vivo separado: 5 VM / 3 hosts físicos, sin LLM y con IP de administración en el SO. Ambos llevan datos y rutas nativos por Ethernet 0x88B5; la vista web y la administración usan HTTPS/IP.', 'Abrir el mesh en vivo y su revisión')}

def check_evidence(root: Path):
 manifest=json.loads((root/'data/architecture-evidence.json').read_text())
 expected={'data/strict-agents-round.json','data/native-summary.json','data/scale-summary.json'}
 if set(manifest['records']) != expected:
  raise ValueError('Architecture evidence list needs review')
 for name,digest in manifest['records'].items():
  if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
   raise ValueError('Architecture needs review for changed evidence: '+name)

def render(root: Path, language='ru'):
 check_evidence(root)
 t=TEXT[language]; e=lambda s:html.escape(str(s),quote=True)
 d=json.loads((root/'data/strict-agents-round.json').read_text())
 assert d['status']=='measured' and set(d['nodes'])=={'A','R1','B'}
 assert len(d['tasks'])==d['modes']['native']['tasks'] and len(d['deliveries'])==d['modes']['native']['signed_deliveries']
 tasks=len(d['tasks']); deliveries=d['modes']['native']['signed_deliveries']; echo=sum(x['phase']=='echo' for x in d['deliveries']); messages=deliveries-echo
 def node(name):
  role=t['router'] if name=='R1' else t['model']
  inside=f'<p>{e(role)}</p>'+('' if name=='R1' else f'<p>{e(t["socket"])}</p>')+f'<p>{e(t["service"])} · {e(t["id"])}</p>'
  return f'<article class="net-machine" data-net-node="{name}"><span class="net-machine-label">{e(t["host"])} · {name}</span><div class="net-guest"><strong>{e(t["guest"])}</strong>{inside}</div></article>'
 links=''
 for idx,(title,description) in enumerate(t['states']):
  links+=f'<li class="net-stage" data-net-stage="{idx}"><h3>{e(title)}</h3><p>{e(description)}</p></li>'
 controls=''.join(f'<button type="button" data-net-select="{i}" aria-pressed="{str(i==0).lower()}">{e(t["select"])} {i+1}</button>' for i in range(len(t['states'])))
 replay='packet-replay.html' if language=='ru' else f'packet-replay.{language}.html'
 return f'''<section class="section research-network" id="research-network" data-i18n-fixed><h2>{e(t['title'])}</h2><p class="lead">{e(t['intro'])}</p><p class="net-qualification">{e(t['scope'])}</p><p>{e(MODE_COPY[language][0])}</p><p>{e(MODE_COPY[language][1])} <a href="https://lab.ipvx.org/#mesh">{e(MODE_COPY[language][2])}</a>.</p><div class="net-topology" data-net-topology><div class="net-grid">{node('A')}<div class="net-link" aria-hidden="true"><span></span></div>{node('R1')}<div class="net-link" aria-hidden="true"><span></span></div>{node('B')}</div><p class="net-transport">{e(t['ethernet'])}</p></div><p class="net-management">{e(t['management'])}</p><div class="net-controls" hidden><button type="button" class="button" data-net-play data-play-label="{e(t['play'])}" data-stop-label="{e(t['pause'])}">{e(t['play'])}</button><div role="group" aria-label="{e(t['step'])}">{controls}</div></div><ol class="net-stages">{links}</ol><div class="net-evidence"><h3>{e(t['facts'])}</h3><p>{e(t['facts_text'].format(tasks=tasks,deliveries=deliveries,echo=echo,messages=messages))}</p><p>{e(t['missing'])}</p><p>{e(t['future'])}</p><p>{e(t['revision'])}: <code>{e(d['source_revision'][:12])}</code></p><p><a href="{replay}#observatory">{e(t['record'])}</a> · <a href="data/strict-agent-manifest.json">{e(t['manifest'])}</a></p></div></section>'''
