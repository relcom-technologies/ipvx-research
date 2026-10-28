"""Task-centred read-only view of the verified public projection."""
import hashlib
import html
import json
from pathlib import Path

TEXT = {
'ru': {
 'title':'Исследовать совместную задачу', 'lead':'Выберите задачу, затем откройте каждый этап и узел. Это запись завершённого опыта, не живой мониторинг.',
 'scope':'Три гостевые ОС на трёх физических хостах. Гостевые ядра без INET/IPv6; внешнее управление использует IP. Один оператор.',
 'association':'Этапы сопоставлены по case и phase. Отдельный сквозной causal ID в исходной публичной записи отсутствует.',
 'nodes':'Узлы и их процессы', 'node_hint':'Откройте узел: его роль, известные входы и выходы, а также отсутствующие измерения.',
 'A':'Отправитель и итог', 'B':'Рецензент', 'R1':'Маршрутизатор', 'identity':'Идентификатор и открытый ключ',
 'model':'Локальная модель и её SHA-256', 'neighbors':'Разрешённые соседи в этом опыте',
 'A_process':'Черновик → запрос B → приём рецензии → итог A.', 'B_process':'Приём запроса → квитанция → рецензия → отдельное сообщение A.',
 'R1_process':'Приём конверта → выбор следующего соседа → пересылка; R1 не запускает модель.',
 'missing':'Причина выбора конкретного маршрута, состояние очереди и время каждого перехода в публичной записи не сохранены.',
 'layer':'Гостевая ОС и IPvX поверх Ethernet. Физическая связность и протокольные соседства — разные уровни.',
 'tasks':'Четыре задачи', 'task_hint':'Откройте задачу, затем её этапы. Эхо-проверки вынесены в отдельный проигрыватель ниже.',
 'delivery':'384 задачи с документами', 'internet':'Готовность к глобальному Интернету', 'once':'Повторные выполнения', 'speed':'Сравнение скорости для ИИ',
 'claim':'Исходное утверждение и данные задачи', 'original':'Оригинал на английском', 'evidence_a':'Данные A', 'evidence_b':'Дополнительные данные B',
 'draft':'A: черновик модели', 'request':'A → R1 → B: запрос рецензии', 'review':'B: рецензия модели',
 'reply':'B → R1 → A: отдельная рецензия', 'final':'A: итог модели', 'outcome':'Проверка итогового решения',
 'inference':'Время вызова модели', 'tokens':'Токены входа / выхода', 'prompt_hash':'SHA-256 входного запроса',
 'output':'Исходный ответ модели', 'message':'ID сообщения', 'path':'Путь сообщения', 'receipt':'Доставка и квитанция на часах отправителя',
 'size':'Байт до шифрования', 'attempts':'Попытки', 'hop_unknown':'Время каждого перехода не записано в публичной проекции.',
 'receipt_limit':'Квитанция подтверждает приём, а не готовность или правильность ответа.', 'decision':'Решение / эталон',
 'yes':'совпало поле решения', 'no':'поле решения не совпало', 'quality':'Качество объяснения оценивается отдельно; исходный ответ сохранён.',
 'compare':'Сравнить режимы и попытки', 'same_run':'Один запуск: IPvX и IP через те же прикладные переходы A–R1–B.',
 'echo':'Эхо p50 / p95', 'task_time':'Полная задача p50 / p95', 'decisions':'Совпадение поля решения',
 'sample':'По 40 эхо и 4 задачи на режим. Выборка мала; сравнение не доказывает общего ускорения ИИ.',
 'previous':'Предыдущая попытка и завершённый опыт', 'previous_limit':'Ранее: 2 задачи, 20 эхо; IP-контроль остановился из-за рассогласования часов. Завершённый опыт: 4 задачи, 40 эхо на режим. Разные версии и объём выборки не позволяют приписать разницу одному изменению.',
 'manifest':'Манифест полноты и источники', 'recorded':'Зафиксировано', 'not_recorded':'Не записано публично',
 'native_count':'Нативных доставок / задач / измеренных вызовов моделей', 'warmups':'Прогревы моделей исключены из измерений',
 'frames':'Наблюдения кадров на обоих концах каналов', 'unknown':'Потери событий сборщика, время каждого перехода, ожидание очереди и причина выбора маршрута не установлены.',
 'clock':'Длительности измерены монотонными часами узла-отправителя. Общую временную шкалу между машинами нельзя считать точно установленной.',
 'privacy':'Оригинальные PCAP содержат адреса инфраструктуры и закрыты. Проверка лабораторией не равна независимой публичной перепроверке исходных байтов.',
 'evidence':'Публичные данные и методика', 'manifest_link':'Открыть манифест JSON', 'source_link':'Очищенная запись опыта', 'inputs_link':'Исходные условия задач', 'history':'История опыта',
 'comparison_note':'Для сравнения произвольных версий нужны повторные запуски с одинаковыми условиями; неизвестные показатели не заменяются нулями.',
 'nojs':'Все четыре задачи и исходные данные доступны без JavaScript.', 'expand':'Раскрыть этап', 'all_results':'Другие записи и покадровый проигрыватель ниже.'},
'en': {
 'title':'Inspect the collaborative task','lead':'Select a task, then open each stage and node. This is a recording of a completed experiment, not live monitoring.',
 'scope':'Three guest operating systems on three physical hosts. Guest kernels lack INET/IPv6; external management uses IP. One operator.',
 'association':'Stages are matched by case and phase. A separate end-to-end causal ID was not recorded in the public projection.',
 'nodes':'Nodes and their processes','node_hint':'Open a node for its role, known inputs and outputs, and missing measurements.','A':'Sender and final synthesis','B':'Reviewer','R1':'Router','identity':'Identity and public key','model':'Local model and its SHA-256','neighbors':'Admitted neighbors in this experiment',
 'A_process':'Draft → request to B → receive review → final synthesis.','B_process':'Receive request → receipt → review → separate message to A.','R1_process':'Receive envelope → choose next neighbor → forward; R1 does not run a model.','missing':'The reason for a particular route choice, queue state and per-hop times are not recorded in the public projection.','layer':'Guest OS and IPvX over Ethernet. Physical connectivity and protocol neighbors are different layers.',
 'tasks':'Four tasks','task_hint':'Open a task, then its stages. Echo checks remain in the separate replay below.','delivery':'384 document tasks','internet':'Readiness for the global Internet','once':'Duplicate executions','speed':'Speed comparison for AI','claim':'Original claim and task evidence','original':'Original English','evidence_a':'Evidence for A','evidence_b':'Additional evidence for B',
 'draft':'A: model draft','request':'A → R1 → B: review request','review':'B: model review','reply':'B → R1 → A: separate review','final':'A: final synthesis','outcome':'Check of the final decision','inference':'Model inference time','tokens':'Input / output tokens','prompt_hash':'Input prompt SHA-256','output':'Original model output','message':'Message ID','path':'Message path','receipt':'Delivery and receipt on sender clock','size':'Bytes before encryption','attempts':'Attempts','hop_unknown':'Per-hop times are not recorded in the public projection.','receipt_limit':'A receipt confirms admission, not the readiness or correctness of the answer.','decision':'Decision / reference','yes':'decision field matches','no':'decision field does not match','quality':'Explanation quality is assessed separately; the original output is retained.',
 'compare':'Compare modes and attempts','same_run':'One run: IPvX and IP through the same A–R1–B application hops.','echo':'Echo p50 / p95','task_time':'Complete task p50 / p95','decisions':'Decision-field match','sample':'40 echoes and 4 tasks per mode. The sample is small; it does not prove a general AI speedup.','previous':'Previous attempt and completed experiment','previous_limit':'Earlier: 2 tasks, 20 echoes; IP control stopped due to clock skew. Completed run: 4 tasks, 40 echoes per mode. Different revisions and sample sizes do not attribute the difference to one change.',
 'manifest':'Completeness manifest and sources','recorded':'Recorded','not_recorded':'Not publicly recorded','native_count':'Native deliveries / tasks / measured model calls','warmups':'Model warmups excluded from measurements','frames':'Frame observations at both ends of links','unknown':'Collector event loss, per-hop time, queue waiting time and route-selection rationale are not established.','clock':'Durations use the sending node’s monotonic clock. An exact shared clock across machines is not established.','privacy':'Original PCAPs contain infrastructure addresses and are private. Laboratory verification is not independent public verification of original bytes.','evidence':'Public data and method','manifest_link':'Open JSON manifest','source_link':'Sanitized experiment record','inputs_link':'Original task inputs','history':'Experiment history','comparison_note':'Comparing arbitrary versions requires repeated runs under matching conditions; unknown values are not replaced by zeros.','nojs':'All four tasks and original data are available without JavaScript.','expand':'Open stage','all_results':'Further records and the frame replay appear below.'},
'de': {
 'title':'Gemeinsame Aufgabe untersuchen','lead':'Wählen Sie eine Aufgabe und öffnen Sie jeden Schritt und Knoten. Dies ist die Aufzeichnung eines abgeschlossenen Versuchs, keine Live-Überwachung.',
 'scope':'Drei Gastbetriebssysteme auf drei physischen Hosts. Die Gastkernel enthalten kein INET/IPv6; die externe Verwaltung verwendet IP. Ein Betreiber.',
 'association':'Schritte werden anhand von case und phase zugeordnet. Eine separate durchgehende kausale ID wurde in der öffentlichen Projektion nicht aufgezeichnet.',
 'nodes':'Knoten und ihre Prozesse','node_hint':'Öffnen Sie einen Knoten für Rolle, bekannte Ein- und Ausgänge sowie fehlende Messungen.','A':'Absender und Endfassung','B':'Prüfender','R1':'Router','identity':'Identität und öffentlicher Schlüssel','model':'Lokales Modell und sein SHA-256','neighbors':'Zugelassene Nachbarn in diesem Versuch',
 'A_process':'Entwurf → Anfrage an B → Rezension empfangen → Endfassung.','B_process':'Anfrage empfangen → Quittung → Rezension → separate Nachricht an A.','R1_process':'Umschlag empfangen → nächsten Nachbarn wählen → weiterleiten; R1 führt kein Modell aus.','missing':'Der Grund der konkreten Routenwahl, der Warteschlangenzustand und Zeiten je Übergang sind öffentlich nicht aufgezeichnet.','layer':'Gastbetriebssystem und IPvX über Ethernet. Physische Verbindungen und Protokollnachbarn sind verschiedene Ebenen.',
 'tasks':'Vier Aufgaben','task_hint':'Öffnen Sie eine Aufgabe und ihre Schritte. Echo-Prüfungen stehen im separaten Player unten.','delivery':'384 Dokumentaufgaben','internet':'Bereitschaft für das globale Internet','once':'Doppelte Ausführungen','speed':'Geschwindigkeitsvergleich für KI','claim':'Ursprüngliche Aussage und Aufgabendaten','original':'Englisches Original','evidence_a':'Daten für A','evidence_b':'Zusätzliche Daten für B',
 'draft':'A: Modellentwurf','request':'A → R1 → B: Anfrage zur Prüfung','review':'B: Modellrezension','reply':'B → R1 → A: separate Rezension','final':'A: Endfassung','outcome':'Prüfung der endgültigen Entscheidung','inference':'Dauer des Modellaufrufs','tokens':'Eingabe- / Ausgabetoken','prompt_hash':'SHA-256 der Eingabe','output':'Ursprüngliche Modellausgabe','message':'Nachrichten-ID','path':'Nachrichtenweg','receipt':'Zustellung und Quittung auf der Uhr des Absenders','size':'Byte vor Verschlüsselung','attempts':'Versuche','hop_unknown':'Zeiten einzelner Übergänge sind öffentlich nicht aufgezeichnet.','receipt_limit':'Eine Quittung bestätigt die Annahme, nicht die Fertigstellung oder Richtigkeit der Antwort.','decision':'Entscheidung / Referenz','yes':'Entscheidungsfeld stimmt überein','no':'Entscheidungsfeld stimmt nicht überein','quality':'Die Qualität der Erklärung wird getrennt bewertet; die Originalausgabe bleibt erhalten.',
 'compare':'Modi und Versuche vergleichen','same_run':'Ein Lauf: IPvX und IP über dieselben Anwendungsschritte A–R1–B.','echo':'Echo p50 / p95','task_time':'Gesamtaufgabe p50 / p95','decisions':'Übereinstimmung des Entscheidungsfelds','sample':'40 Echos und 4 Aufgaben pro Modus. Die Stichprobe ist klein und belegt keine allgemeine KI-Beschleunigung.','previous':'Früherer Versuch und abgeschlossener Lauf','previous_limit':'Zuvor: 2 Aufgaben, 20 Echos; die IP-Kontrolle stoppte wegen abweichender Uhren. Abgeschlossen: 4 Aufgaben, 40 Echos je Modus. Unterschiedliche Revisionen und Stichprobengrößen erlauben keine Zuordnung zu einer einzelnen Änderung.',
 'manifest':'Vollständigkeitsmanifest und Quellen','recorded':'Aufgezeichnet','not_recorded':'Öffentlich nicht aufgezeichnet','native_count':'Native Zustellungen / Aufgaben / gemessene Modellaufrufe','warmups':'Aufwärmaufrufe aus Messungen ausgeschlossen','frames':'Frame-Beobachtungen an beiden Kanalenden','unknown':'Verlust von Collector-Ereignissen, Zeiten pro Übergang, Wartezeit in der Queue und Grund der Routenwahl sind nicht festgestellt.','clock':'Dauern verwenden die monotone Uhr des sendenden Knotens. Eine exakt gemeinsame Uhr über Maschinen hinweg ist nicht belegt.','privacy':'Original-PCAPs enthalten Infrastrukturadressen und sind privat. Eine Laborprüfung ist keine unabhängige öffentliche Prüfung der Originalbytes.','evidence':'Öffentliche Daten und Methode','manifest_link':'JSON-Manifest öffnen','source_link':'Bereinigte Versuchsaufzeichnung','inputs_link':'Ursprüngliche Aufgabendaten','history':'Versuchsgeschichte','comparison_note':'Beliebige Versionen erfordern wiederholte Läufe unter gleichen Bedingungen; unbekannte Werte werden nicht durch Nullen ersetzt.','nojs':'Alle vier Aufgaben und Originaldaten sind ohne JavaScript verfügbar.','expand':'Schritt öffnen','all_results':'Weitere Aufzeichnungen und der Frame-Player folgen unten.'},
'es': {
 'title':'Investigar la tarea colaborativa','lead':'Seleccione una tarea y abra cada etapa y nodo. Es un registro de un experimento terminado, no supervisión en directo.',
 'scope':'Tres sistemas invitados en tres equipos físicos. Los núcleos invitados no incluyen INET/IPv6; la administración externa usa IP. Un operador.',
 'association':'Las etapas se relacionan por case y phase. La proyección pública no registró un ID causal único de extremo a extremo.',
 'nodes':'Nodos y sus procesos','node_hint':'Abra un nodo para consultar su función, entradas y salidas conocidas y mediciones ausentes.','A':'Emisor y síntesis final','B':'Revisor','R1':'Enrutador','identity':'Identidad y clave pública','model':'Modelo local y su SHA-256','neighbors':'Vecinos admitidos en este experimento',
 'A_process':'Borrador → solicitud a B → recepción de revisión → síntesis final.','B_process':'Recibir solicitud → acuse → revisión → mensaje separado a A.','R1_process':'Recibir sobre → elegir siguiente vecino → reenviar; R1 no ejecuta un modelo.','missing':'La proyección pública no registra el motivo de la ruta concreta, el estado de la cola ni los tiempos por salto.','layer':'Sistema invitado e IPvX sobre Ethernet. La conectividad física y los vecinos del protocolo son capas distintas.',
 'tasks':'Cuatro tareas','task_hint':'Abra una tarea y después sus etapas. Las comprobaciones de eco permanecen en el reproductor inferior.','delivery':'384 tareas de documentos','internet':'Preparación para Internet global','once':'Ejecuciones duplicadas','speed':'Comparación de velocidad para IA','claim':'Afirmación original y datos de la tarea','original':'Original en inglés','evidence_a':'Datos para A','evidence_b':'Datos adicionales para B',
 'draft':'A: borrador del modelo','request':'A → R1 → B: solicitud de revisión','review':'B: revisión del modelo','reply':'B → R1 → A: revisión separada','final':'A: síntesis final','outcome':'Comprobación de la decisión final','inference':'Tiempo de inferencia','tokens':'Tokens de entrada / salida','prompt_hash':'SHA-256 de la entrada','output':'Salida original del modelo','message':'ID del mensaje','path':'Ruta del mensaje','receipt':'Entrega y acuse en el reloj del emisor','size':'Bytes antes del cifrado','attempts':'Intentos','hop_unknown':'Los tiempos por salto no están registrados en la proyección pública.','receipt_limit':'El acuse confirma la admisión, no que la respuesta esté lista o sea correcta.','decision':'Decisión / referencia','yes':'el campo de decisión coincide','no':'el campo de decisión no coincide','quality':'La calidad de la explicación se evalúa por separado; se conserva la salida original.',
 'compare':'Comparar modos e intentos','same_run':'Una ejecución: IPvX e IP por los mismos saltos de aplicación A–R1–B.','echo':'Eco p50 / p95','task_time':'Tarea completa p50 / p95','decisions':'Coincidencia del campo de decisión','sample':'40 ecos y 4 tareas por modo. La muestra es pequeña y no demuestra una aceleración general de la IA.','previous':'Intento anterior y experimento completado','previous_limit':'Antes: 2 tareas, 20 ecos; el control IP se detuvo por desfase de relojes. Ejecución completada: 4 tareas, 40 ecos por modo. Las versiones y muestras distintas no permiten atribuir la diferencia a un único cambio.',
 'manifest':'Manifiesto de integridad y fuentes','recorded':'Registrado','not_recorded':'No registrado públicamente','native_count':'Entregas nativas / tareas / llamadas de modelo medidas','warmups':'Calentamientos excluidos de las mediciones','frames':'Observaciones de tramas en ambos extremos','unknown':'No se han establecido pérdidas del colector, tiempos por salto, espera en cola ni motivo de selección de ruta.','clock':'Las duraciones usan el reloj monotónico del nodo emisor. No se ha establecido un reloj compartido exacto entre equipos.','privacy':'Los PCAP originales contienen direcciones de infraestructura y son privados. La verificación del laboratorio no equivale a una verificación pública independiente de los bytes originales.','evidence':'Datos públicos y método','manifest_link':'Abrir manifiesto JSON','source_link':'Registro depurado del experimento','inputs_link':'Datos originales de las tareas','history':'Historia del experimento','comparison_note':'Comparar versiones arbitrarias requiere ejecuciones repetidas en condiciones equivalentes; los valores desconocidos no se sustituyen por ceros.','nojs':'Las cuatro tareas y los datos originales están disponibles sin JavaScript.','expand':'Abrir etapa','all_results':'Más registros y el reproductor de tramas aparecen abajo.'}}


# The following are editorial translations of the exact project evidence inputs.
INPUT_TEXT = {
 'ru': {
  'delivery': ('Все 384 задания с документами в принятом нативном опыте вернули правильные результаты.', 'A1: Принятый нативный запуск выполнил 384 из 384 заданий правильно.', 'B1: Правильность проверяли по детерминированным эталонным ответам. Утверждение относится только к принятому запуску.'),
  'internet': ('Принятый опыт доказывает готовность IPvX к глобальному публичному Интернету.', 'A2: В реальном опыте использовали 16 процессов и выполнили все 384 задачи.', 'B2: Все 16 процессов работали на одной ВМ в изолированных пространствах имён. Состав был фиксирован. WAN, независимые операторы, враждебные узлы и большая таблица маршрутов не проверялись.'),
  'once': ('Повторная доставка вызвала дополнительные исполнения приложения в принятом запуске.', 'A3: В принятом запуске намеренно повторили 23 идентичных запроса и записали 80 повторных попыток.', 'B3: Проверки сохранённых квитанций насчитали ровно 384 уникальных исполнения для 384 исходных задач. Повторные запросы возвращали сохранённую квитанцию.'),
  'speed': ('Существующие измерения показывают, что нативный IPvX быстрее обычного IP для агентов с языковыми моделями.', 'A4: Задержка заданий с документами в принятом опыте: p50 — 459 мс, p95 — 1321 мс.', 'B4: В том опыте не было языковых моделей и обычной IP-базы для сравнения. Он не может установить относительное преимущество по скорости.')},
 'de': {
  'delivery': ('Alle 384 Dokumentaufgaben im akzeptierten nativen Versuch lieferten korrekte Ergebnisse.', 'A1: Der akzeptierte native Lauf schloss 384 von 384 Dokumentaufgaben korrekt ab.', 'B1: Die Korrektheit wurde anhand deterministischer Referenzantworten geprüft. Die Aussage betrifft nur den akzeptierten Lauf.'),
  'internet': ('Der akzeptierte Versuch beweist, dass IPvX für das globale öffentliche Internet bereit ist.', 'A2: Im echten Versuch wurden 16 Prozesse verwendet und alle 384 Aufgaben abgeschlossen.', 'B2: Alle 16 Prozesse liefen auf einer VM in isolierten Namensräumen. Die Zulassung war fest. WAN, unabhängige Betreiber, feindliche Teilnehmer und große Routingtabellen wurden nicht geprüft.'),
  'once': ('Doppelte Zustellung verursachte zusätzliche Anwendungsausführungen im akzeptierten Lauf.', 'A3: Im akzeptierten Lauf wurden 23 identische Anfragen absichtlich wiederholt und 80 Wiederholungsversuche protokolliert.', 'B3: Dauerhafte Quittungsprüfungen zählten genau 384 einzigartige Ausführungen für die 384 ursprünglichen Aufgaben. Wiederholte Anfragen erhielten die gespeicherte Quittung.'),
  'speed': ('Bestehende Messungen zeigen, dass natives IPvX für Sprachmodell-Agenten schneller als gewöhnliches IP ist.', 'A4: Die Dokumentaufgaben-Latenz des akzeptierten Versuchs betrug p50 459 ms und p95 1321 ms.', 'B4: Dieser Versuch enthielt weder Sprachmodelle noch eine gewöhnliche IP-Vergleichsbasis. Er kann keinen Geschwindigkeitsvergleich belegen.')},
 'es': {
  'delivery': ('Las 384 tareas de documentos del experimento nativo aceptado devolvieron resultados correctos.', 'A1: La ejecución nativa aceptada completó correctamente 384 de 384 tareas de documentos.', 'B1: La corrección se comprobó frente a respuestas esperadas deterministas. La afirmación se refiere únicamente a esa ejecución aceptada.'),
  'internet': ('El experimento aceptado demuestra que IPvX está listo para la Internet pública global.', 'A2: El experimento real utilizó 16 procesos y completó las 384 tareas.', 'B2: Los 16 procesos se ejecutaron en una sola máquina virtual con espacios de nombres aislados. La admisión era fija. No se probaron WAN, operadores independientes, pares hostiles ni tablas grandes de rutas.'),
  'once': ('La entrega duplicada causó ejecuciones adicionales de la aplicación en la ejecución aceptada.', 'A3: La ejecución aceptada repitió deliberadamente 23 solicitudes idénticas y registró 80 reintentos.', 'B3: Las comprobaciones de recibos persistentes contaron exactamente 384 ejecuciones únicas para las 384 tareas originales. Las solicitudes repetidas devolvieron el recibo guardado.'),
  'speed': ('Las mediciones existentes muestran que IPvX nativo es más rápido que IP ordinario para agentes con modelos de lenguaje.', 'A4: La latencia de las tareas de documentos en el experimento aceptado fue p50 459 ms y p95 1321 ms.', 'B4: Ese experimento no incluía modelos de lenguaje ni una base de comparación de IP ordinario. No puede establecer una ventaja comparativa de velocidad.')}
}


def make_manifest(root):
    raw = (root/'data/strict-agents-round.json').read_bytes(); d = json.loads(raw)
    i = json.loads((root/'data/strict-agent-inputs.json').read_text())
    assert d['status']=='measured' and len(d['tasks'])==4 and len(d['deliveries'])==48
    assert {x['case'] for x in i['cases']}=={x['case'] for x in d['tasks']}
    measured=[x for x in d['inferences'] if x['case']!='warmup']
    return {'schema_version':1,'status':'recorded_projection','source_revision':d['source_revision'],
      'source_run':d['workflow'],'public_record_sha256':hashlib.sha256(raw).hexdigest(),
      'public_inputs_sha256':hashlib.sha256((root/'data/strict-agent-inputs.json').read_bytes()).hexdigest(),
      'declared_scope':{'nodes':['A','R1','B'],'native_tasks':len(d['tasks']),'native_deliveries':len(d['deliveries']),
                        'native_echoes':sum(x['phase']=='echo' for x in d['deliveries']),
                        'native_measured_inferences':len(measured),'native_warmups':len(d['inferences'])-len(measured),
                        'native_frame_observations':d['frame_observations'],'frame_observations_count_both_ends':True},
      'coverage':{'task_records':'present','signed_receipts':'verified_in_private_lab','original_pcap':'private',
                  'public_reverification_of_original_pcap':'unavailable','causal_task_id':'not_recorded',
                  'per_hop_timing':'not_recorded_publicly','queue_waiting_time':'not_recorded_publicly',
                  'route_selection_reason':'not_recorded_publicly','event_collector_loss':'not_established',
                  'sampling_policy':'not_established','cross_host_clock_alignment':'uncertain'},
      'comparison':{'native':'recorded','ip':'recorded_same_application_hops','direct_ip':'not_part_of_this_run',
                    'arbitrary_versions':'not_established','native_tasks':4,'ip_tasks':4},
      'limitations':d['limits']}


def render(root, language='ru'):
    t=TEXT[language]; e=lambda x:html.escape(str(x),quote=True)
    back={'ru':'Вернуться к задачам','en':'Back to tasks','de':'Zurück zu den Aufgaben','es':'Volver a las tareas'}[language]
    private={'ru':'Журнал запуска доступен только лаборатории','en':'Run log available only to the lab','de':'Laufprotokoll nur im Labor zugänglich','es':'Registro de ejecución accesible solo al laboratorio'}[language]
    d=json.loads((root/'data/strict-agents-round.json').read_text())
    inputs={x['case']:x for x in json.loads((root/'data/strict-agent-inputs.json').read_text())['cases']}
    m=make_manifest(root); (root/'data/strict-agent-manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    def node(name):
        neighbors='R1' if name in ('A','B') else 'A, B'
        n=d['nodes'][name]
        model=f'<p><b>{e(t["model"])}:</b> {e(d["model"])} <code>{e(d["model_sha256"])}</code></p>' if name!='R1' else ''
        cases=' · '.join(f'<a href="#obs-case-{e(x["case"])}">{e(t[x["case"]])}</a>' for x in d['tasks'])
        return f'<details class="obs-node" id="obs-node-{name}"><summary><strong>{e(name)}</strong> · {e(t[name])}</summary><p>{e(t[name+"_process"])}</p><p><b>{e(t["identity"])}:</b> <code>{e(n["id"])}</code><br><code>{e(n["public_key"])}</code></p>{model}<p><b>{e(t["neighbors"])}:</b> {e(neighbors)}</p><p>{e(t["layer"])}</p><p class="obs-unknown">{e(t["missing"])}</p><p><b>{e(t["tasks"])}</b>: {cases}</p><p><a href="data/strict-agents-round.json">{e(t["source_link"])}</a> · <a href="#obs-tasks">{e(back)}</a></p></details>'
    def inference(case,phase,node_name):
        entries=[x for x in d['inferences'] if x['case']==case and x['phase']==phase and x['node']==node_name]
        assert len(entries)==1
        x=entries[0]; assert x['run']==inputs[case]['run']
        usage=x['usage'];output=e(json.dumps(x['parsed'],ensure_ascii=False,indent=2))
        return f'<p>{e(t["inference"])}: <b>{x["elapsed_ms"]:.3f} ms</b> · {e(t["tokens"])}: {usage["prompt_tokens"]} / {usage["completion_tokens"]}</p><p>{e(t["prompt_hash"])}: <code>{e(x["prompt_sha256"])}</code></p><details><summary>{e(t["output"])}</summary><pre lang="en">{output}</pre></details><p><a href="#obs-node-{node_name}">{e(t["nodes"])} · {e(node_name)}</a></p>'
    def message(case,phase):
        entries=[x for x in d['deliveries'] if x['case']==case and x['phase']==phase];assert len(entries)==1
        x=entries[0]; assert x['path']==(['A','R1','B'] if phase=='review' else ['B','R1','A'])
        return f'<p>{e(t["message"])}: <code>{e(x["message_id"])}</code></p><p>{e(t["path"])}: <b>{e(" → ".join(x["path"]))}</b></p><p>{e(t["receipt"])}: <b>{x["elapsed_ms"]:.3f} ms</b> · {e(t["size"])}: {x["bytes"]} · {e(t["attempts"])}: {x["attempts"]}</p><p class="obs-unknown">{e(t["hop_unknown"])} {e(t["receipt_limit"])}</p><p><a href="#obs-node-R1">{e(t["nodes"])} · R1</a></p>'
    def step(title,contents):
        return f'<li><details class="obs-step"><summary>{e(title)}</summary>{contents}</details></li>'
    tasks=[]
    for task in d['tasks']:
        case=task['case']; inp=inputs[case]
        examples=lambda items:''.join('<li lang="en">'+e(item)+'</li>' for item in items)
        original=f'<p lang="en">{e(inp["claim"])}</p><p>{e(t["evidence_a"])}:</p><ul>{examples(inp["evidence_a"])}</ul><p>{e(t["evidence_b"])}:</p><ul>{examples(inp["evidence_b"])}</ul>'
        if language == 'en':
            claim=original
        else:
            translated=INPUT_TEXT[language][case]
            claim=f'<p>{e(translated[0])}</p><p>{e(t["evidence_a"])}:</p><ul><li>{e(translated[1])}</li></ul><p>{e(t["evidence_b"])}:</p><ul><li>{e(translated[2])}</li></ul><details><summary>{e(t["original"])}</summary>{original}</details>'
        final=task['final'];outcome=f'<p>{e(t["decision"])}: <b>{e(final["decision"])} / {e(task["expected"])}</b> · {e(t["yes"] if task["decision_correct"] else t["no"])}</p><p>{e(t["quality"])}</p>'
        steps=(step(t['claim'],claim)+step(t['draft'],inference(case,'draft','A'))+
               step(t['request'],message(case,'review'))+step(t['review'],inference(case,'review','B'))+
               step(t['reply'],message(case,'final'))+step(t['final'],inference(case,'final','A'))+step(t['outcome'],outcome))
        tasks.append(f'<details class="obs-case" id="obs-case-{e(case)}"'+(' open' if case=='delivery' else '')+f'><summary>{e(t[case])} <small>· {task["elapsed_ms"]/1000:.2f} s · {e(t["yes"] if task["decision_correct"] else t["no"])}</small></summary><p class="obs-meta">{e(inp["run"])} · {e(t["association"])}</p><p class="obs-path" aria-label="{e(t["path"])}">A → R1 → B → R1 → A</p><ol class="obs-steps">{steps}</ol></details>')
    rows=''
    for mode,label in [('native','IPvX'),('ip','IP')]:
        v=d['modes'][mode];rows+=f'<tr><th scope="row">{label}</th><td>{v["echo"]["p50_ms"]:.3f} / {v["echo"]["p95_ms"]:.3f} ms</td><td>{v["task"]["p50_ms"]/1000:.3f} / {v["task"]["p95_ms"]/1000:.3f} s</td><td>{v["correct_decisions"]} / {v["tasks"]}</td></tr>'
    partial=json.loads((root/'data/strict-native-partial.json').read_text())
    history_page = 'history.html' if language == 'ru' else f'history.{language}.html'
    return f'''<section id="observatory" class="section observatory" data-i18n-fixed aria-labelledby="obs-title"><h2 id="obs-title">{e(t['title'])}</h2><p class="obs-lead">{e(t['lead'])}</p><p class="obs-scope">{e(t['scope'])}</p>
+<div class="obs-layout"><div class="obs-main"><h3 id="obs-tasks">{e(t['tasks'])}</h3><p>{e(t['task_hint'])}</p>{''.join(tasks)}<p class="small">{e(t['nojs'])} {e(t['all_results'])}</p></div><aside class="obs-aside"><h3>{e(t['nodes'])}</h3><p>{e(t['node_hint'])}</p>{''.join(node(n) for n in ['A','R1','B'])}</aside></div>
+<details class="obs-more"><summary>{e(t['compare'])}</summary><p>{e(t['same_run'])}</p><div class="obs-table" role="region" tabindex="0" aria-label="{e(t['compare'])}"><table><thead><tr><th scope="col">{e({'ru':'Режим','en':'Mode','de':'Modus','es':'Modo'}[language])}</th><th scope="col">{e(t['echo'])}</th><th scope="col">{e(t['task_time'])}</th><th scope="col">{e(t['decisions'])}</th></tr></thead><tbody>{rows}</tbody></table></div><p>{e(t['sample'])}</p><h3>{e(t['previous'])}</h3><p><a href="data/strict-native-partial.json">40557153199</a> · {e(partial['source_revision'][:7])} · p50 {partial['echo_p50_ms']:.4f} ms<br><a href="data/strict-agents-round.json">40563118803</a> · {e(d['source_revision'][:7])} · p50 {d['modes']['native']['echo']['p50_ms']:.3f} ms</p><p>{e(private)}.</p><p>{e(t['previous_limit'])}</p><p>{e(t['comparison_note'])}</p></details>
+<details class="obs-more"><summary>{e(t['manifest'])}</summary><h3>{e(t['recorded'])}</h3><p>{e(t['native_count'])}: 48 / 4 / 12. {e(t['warmups'])}: 4. {e(t['frames'])}: 13024.</p><h3>{e(t['not_recorded'])}</h3><p>{e(t['unknown'])}</p><p>{e(t['clock'])}</p><p>{e(t['privacy'])}</p><p><a href="data/strict-agent-manifest.json">{e(t['manifest_link'])}</a> · <a href="data/strict-agents-round.json">{e(t['source_link'])}</a> · <a href="data/strict-agent-inputs.json">{e(t['inputs_link'])}</a> · <a href="{e(history_page)}#HX-0085">{e(t['history'])}</a></p></details></section>'''.replace('\n+', '\n')
