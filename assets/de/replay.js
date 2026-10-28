/* A read-only replay of verified, saved PCAP. No lab control or inferred latency. */
(() => {
  const byId = id => document.getElementById(id);
  const root = document.querySelector('.replay');
  if (!root) return;
  const scenarioInput = byId('replay-scenario'), position = byId('replay-position');
  const play = byId('replay-play'), back = byId('replay-back'), next = byId('replay-next');
  const status = byId('replay-status'), retry = byId('replay-retry'), list = byId('replay-events');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const roles = {1:'A', 2:'B', 3:'R', 0:"alle Nachbarn"};
  let dataset, scenario, index = 0, playing = false, timer, animation, buttons = [];

  function validate(data) {
    if (data?.schema_version !== 1 || data.status !== 'saved_measured_capture' ||
        !Array.isArray(data.scenarios) || data.scenarios.length !== 2) throw Error('schema');
    const hex = /^[a-f0-9]+$/;
    const kinds = new Set(['HELLO','TASK','RESULT']);
    for (const [i, s] of data.scenarios.entries()) {
      const id = ['baseline','relay-down'][i];
      if (s.id !== id || s.completed_tasks !== [16,0][i] || s.total_tasks !== 16 ||
          s.socket_rejections !== 12 || !Array.isArray(s.frames) || s.frames.length !== [90,10][i]) throw Error('scenario');
      const previous = {ar:-1, rb:-1};
      for (const [j, f] of s.frames.entries()) {
        const ends = f.link === 'ar' ? ['A','R'] : f.link === 'rb' ? ['R','B'] : [];
        if (f.index !== j || !Number.isFinite(f.link_at_ms) || f.link_at_ms < previous[f.link] ||
            !ends.includes(f.from_node) || !ends.includes(f.to_node) || f.from_node === f.to_node ||
            !kinds.has(f.kind) || !Number.isInteger(f.sequence) || f.sequence < 0 || f.sequence > 16 ||
            !Number.isInteger(f.frame_bytes) || f.frame_bytes < 14 || f.frame_bytes > 1600 ||
            !Number.isInteger(f.capture_frame) || f.capture_frame < 1 ||
            f.capture !== `${id}/${f.link}.pcap` || f.signature_verified !== true ||
            ![f.source_id, f.destination_id, f.frame_sha256].every(v => typeof v === 'string' && v.length === 64 && hex.test(v)) ||
            typeof f.frame_hex !== 'string' || f.frame_hex.length !== f.frame_bytes*2 || !hex.test(f.frame_hex) ||
            typeof f.payload_hex !== 'string' || f.payload_hex.length > 2600 || !hex.test(f.payload_hex) ||
            !(f.source_role in roles) || !(f.destination_role in roles)) throw Error('frame');
        previous[f.link] = f.link_at_ms;
      }
    }
    return data;
  }
  function node(tag, text, className) {
    const element = document.createElement(tag); element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function stop(message) {
    playing = false; clearTimeout(timer); animation?.cancel(); animation = null;
    byId('replay-packet').hidden = true;
    play.textContent = index === scenario?.frames.length-1 ? "Erneut versuchen" : "Reproduzieren";
    if (message) status.textContent = message;
  }
  function controls(enabled) {
    play.disabled = !enabled; scenarioInput.disabled = !enabled; position.disabled = !enabled;
    back.disabled = !enabled || index === 0;
    next.disabled = !enabled || index === scenario.frames.length-1;
  }
  function render() {
    const f = scenario.frames[index];
    byId('replay-position-label').textContent = `${index+1} von ${scenario.frames.length}`;
    position.value = index;
    position.setAttribute('aria-valuetext', `Frame ${index+1}: ${f.kind}, ${f.from_node} an ${f.to_node}`);
    byId('replay-frame-line').textContent = `${f.from_node} → ${f.to_node} · ${f.kind}${f.sequence ? ' №'+f.sequence : ''} · +${f.link_at_ms.toFixed(3)} ms ab Beginn dieses PCAP`;
    const fields = [
      ["Kanal", `${f.link === 'ar' ? 'A — R' : 'R — B'} · Frame ${f.capture_frame} im PCAP`],
      ["Ursprünglicher Sender", `${roles[f.source_role]} · ${f.source_id}`],
      ["Endgültiger Empfänger", f.destination_role ? `${roles[f.destination_role]} · ${f.destination_id}` : "HELLO: alle Nachbarn auf dem Kanal"],
      ["Zustellung", `EtherType 0x88B5 · Hop-Grenze ${f.hop_limit}`],
      ["Prüfung", "Ed25519, ID und CRC vom Exporter geprüft; keine Verschlüsselung"],
      ["Nutzlast", `${f.payload_hex.length/2} Bytes`]
    ];
    byId('replay-fields').replaceChildren(...fields.flatMap(([key, value]) => [node('dt',key),node('dd',value)]));
    byId('replay-byte-layout').replaceChildren(node('span',"Ethernet\n14 B"),node('span',"XNS1\n188 B"),node('span',`Daten
${f.payload_hex.length/2} B`));
    byId('replay-payload-note').textContent = f.kind === 'TASK' ? "Exakte 1 024 Aufgabenbytes als HEX. Deterministische Daten, keine LLM-Anfrage." :
      f.kind === 'RESULT' ? "64 ASCII-Zeichen von SHA-256, durch OS B berechnet. Daten offen übertragen." : "Signierte HELLO-Ankündigung: bestätigt Schlüsselkontrolle, keine Freigabe eines unabhängigen Betreibers.";
    byId('replay-payload').textContent = f.kind === 'TASK' ? f.payload_hex.match(/.{1,64}/g).join('\n') :
      Array.from(f.payload_hex.matchAll(/../g), ([v]) => String.fromCharCode(parseInt(v,16))).join('');
    byId('replay-frame-hash').textContent = f.frame_sha256;
    byId('replay-frame-hex').textContent = f.frame_hex.match(/.{1,64}/g).join('\n');
    byId('replay-pcap').href = `data/strict-native-2026-10-27/${f.capture}`;
    buttons.forEach((button,i) => button.setAttribute('aria-current', String(i === index)));
    root.querySelectorAll('[data-node]').forEach(n => n.dataset.selected = String(n.dataset.node === f.to_node));
    controls(true);
  }
  function select(value) {
    stop(); index = Math.max(0,Math.min(scenario.frames.length-1,value)); render();
    status.textContent = `Pause. Gewählter Frame ${index+1} von ${scenario.frames.length}.`;
  }
  function changeScenario() {
    stop(); scenario = dataset.scenarios.find(s => s.id === scenarioInput.value); index = 0;
    byId('replay-total').textContent = scenario.frames.length;
    byId('replay-completed').textContent = `${scenario.completed_tasks} / ${scenario.total_tasks}`;
    byId('replay-receipt').href = `data/strict-native-2026-10-27/${scenario.id}/receipt.json`;
    position.max = scenario.frames.length-1;
    buttons = scenario.frames.map((f,i) => {
      const button = node('button',''); button.type = 'button';
      button.append(node('strong',`${i+1}. ${f.from_node} → ${f.to_node} · ${f.kind}${f.sequence ? ' №'+f.sequence : ''}`),
                    node('small',`+${f.link_at_ms.toFixed(3)} ms · ${f.link}.pcap #${f.capture_frame}`),node('span',`${f.frame_bytes} B`));
      button.addEventListener('click',() => select(i));
      const li = node('li',''); li.append(button); return button;
    });
    list.replaceChildren(...buttons.map(button => button.parentElement)); list.scrollTop = 0; render();
    status.textContent = scenario.id === 'baseline' ? "Aufzeichnung bereit: alle 90 Frames, 16 von 16 Aufgaben." :
      "Negativer Lauf: alle 10 Frames, 0 von 16 Aufgaben. R-Stoppzeit in Frames nicht markiert.";
  }
  function cycle() {
    if (!playing) return;
    render();
    const f = scenario.frames[index], duration = Number(byId('replay-speed').value);
    const from = root.querySelector(`[data-node="${f.from_node}"]`).getBoundingClientRect();
    const to = root.querySelector(`[data-node="${f.to_node}"]`).getBoundingClientRect();
    const map = root.querySelector('.replay-map').getBoundingClientRect(), packet = byId('replay-packet');
    if (!motion.matches && typeof packet.animate === 'function') {
      packet.hidden = false;
      const point = rect => `translate(${rect.x+rect.width/2-map.x}px, ${rect.y+rect.height/2-map.y}px)`;
      animation = packet.animate([{transform:point(from)},{transform:point(to)}],{duration,easing:'linear',fill:'forwards'});
    }
    timer = setTimeout(() => {
      animation?.cancel(); animation = null; packet.hidden = true;
      if (index === scenario.frames.length-1) { stop("Ansicht abgeschlossen. Alle Frames gezeigt; Details über Protokollzeilen verfügbar."); return; }
      index++; cycle();
    },duration);
  }
  async function load() {
    stop(); controls(false); retry.hidden = true;
    status.textContent = "Verifizierter Mitschnitt wird geladen…";
    try {
      const response = await fetch('data/packet-replay.json',{credentials:'omit'});
      if (!response.ok) throw Error('HTTP');
      dataset = validate(await response.json()); changeScenario();
    } catch {
      status.textContent = "Aufzeichnung nicht geladen oder beschädigt. Original-PCAPs und Archive unten bleiben verfügbar.";
      controls(false); retry.hidden = false;
    }
  }
  play.addEventListener('click',() => {
    if (playing) {stop(`Pause. Frame ${index+1} von ${scenario.frames.length}.`);return;}
    if (index === scenario.frames.length-1) index = 0;
    playing = true; play.textContent = "Pause";
    status.textContent = "Gespeicherte Frames werden wiedergegeben. Tempo illustrativ; Originalzeit im Protokoll.";
    cycle();
  });
  back.addEventListener('click',() => select(index-1)); next.addEventListener('click',() => select(index+1));
  position.addEventListener('input',() => select(Number(position.value)));
  scenarioInput.addEventListener('change',changeScenario);
  byId('replay-speed').addEventListener('change',() => { if(playing) stop("Geschwindigkeit geändert. Zum Fortsetzen „Wiedergeben“ drücken."); });
  retry.addEventListener('click',load);
  document.addEventListener('visibilitychange',() => {if(document.hidden && playing)stop("Wiedergabe beim Verlassen der Seite pausiert.");});
  window.addEventListener('resize',() => {if(playing)stop("Pause nach Änderung der Fenstergröße.");});
  motion.addEventListener('change',() => {if(playing)stop("Pause nach Änderung der Bewegungseinstellung.");});
  load();
})();
