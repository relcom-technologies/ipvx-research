(() => {
  const select = document.querySelector('#agent-message');
  if (!select) return;
  const $ = id => document.getElementById(id);
  const nodes = [...document.querySelectorAll('[data-agent]')];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let data, chosen, position = 0, playing = false, animation, timer, generation = 0;
  const labels = {echo: 'Эхо · проверка канала', review: 'A просит B проверить черновик', final: 'B возвращает рецензию для итога A'};
  const route = () => [...chosen.path, chosen.path[1], chosen.path[0]];
  function stop() {
    playing = false; generation++;
    animation?.cancel(); animation = null;
    clearTimeout(timer); $('agent-dot').hidden = true;
    $('agent-play').textContent = 'Показать путь';
  }
  function field(label, value) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = label; dd.textContent = value;
    $('agent-message-fields').append(dt, dd);
  }
  function paint() {
    const path = route();
    nodes.forEach(el => el.dataset.active = String(el.dataset.agent === path[position]));
    $('agent-hop').textContent = `${position} из 4 переходов`;
    $('agent-hop-text').textContent = position === 0 ? 'Отправитель подготовил зашифрованное задание.' :
      `${path[position - 1]} → ${path[position]} · ${position <= 2 ? 'подписанный конверт задания' : 'подписанная квитанция приёма'}`;
    if (position === 4) $('agent-hop-text').textContent += ' · Отправитель проверил квитанцию.';
  }
  function choose() {
    stop(); position = 0; chosen = data.deliveries[Number(select.value)];
    $('agent-message-purpose').textContent = `${labels[chosen.phase]}${chosen.case ? ' · ' + chosen.case : ''}`;
    $('agent-message-fields').replaceChildren();
    field('Сообщение', chosen.message_id); field('Данные задачи', `${chosen.bytes} байт до шифрования`);
    field('Проверенный путь', chosen.path.join(' → '));
    field('Приём и квитанция', `${chosen.elapsed_ms.toLocaleString('ru-RU')} мс на часах отправителя`);
    field('Попытки', String(chosen.attempts));
    paint();
  }
  function center(name) {
    const map = $('agent-map').getBoundingClientRect();
    const rect = nodes.find(n => n.dataset.agent === name).getBoundingClientRect();
    return {x: rect.left + rect.width / 2 - map.left, y: rect.top + rect.height / 2 - map.top};
  }
  async function advance(moving = false) {
    if (!chosen) return;
    if (position === 4) position = 0;
    const currentGeneration = generation, path = route();
    if (moving && !reduced.matches) {
      const a = center(path[position]), b = center(path[position + 1]);
      $('agent-dot').hidden = false;
      animation = $('agent-dot').animate([{transform: `translate(${a.x}px,${a.y}px)`}, {transform: `translate(${b.x}px,${b.y}px)`}], {duration: 650, easing: 'linear', fill: 'forwards'});
      try { await animation.finished; } catch { return; }
    }
    if (currentGeneration !== generation) return;
    $('agent-dot').hidden = true; position++; paint();
    if (playing && position < 4) timer = setTimeout(() => advance(true), 100);
    else stop();
  }
  select.addEventListener('change', choose);
  $('agent-play').addEventListener('click', () => {
    if (playing) { stop(); paint(); return; }
    playing = true; $('agent-play').textContent = 'Пауза'; advance(true);
  });
  $('agent-step').addEventListener('click', () => { stop(); advance(); });
  $('agent-reset').addEventListener('click', () => { stop(); position = 0; paint(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  addEventListener('resize', () => stop());
  reduced.addEventListener('change', () => stop());
  const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 8000);
  fetch('data/strict-agents-round.json', {signal: abort.signal, cache: 'no-cache'})
    .then(response => { if (!response.ok) throw Error('HTTP'); return response.json(); })
    .then(value => {
      if (value.schema_version !== 1 || !Array.isArray(value.deliveries) || !value.deliveries.length || value.deliveries.length > 1000) throw Error('record');
      for (const message of value.deliveries) {
        if (!Object.hasOwn(labels, message.phase) || !Array.isArray(message.path) || message.path.length !== 3 || message.path[1] !== 'R1' || !['A', 'B'].includes(message.path[0]) || !['A', 'B'].includes(message.path[2]) || message.path[0] === message.path[2]) throw Error('path');
        if (typeof message.message_id !== 'string' || !/^[0-9a-f]{32}$/.test(message.message_id) || !Number.isFinite(message.elapsed_ms) || message.elapsed_ms < 0 || !Number.isSafeInteger(message.bytes) || message.bytes < 0 || !Number.isSafeInteger(message.attempts) || message.attempts < 1) throw Error('message');
      }
      if (!value.nodes || Object.keys(value.nodes).sort().join(',') !== 'A,B,R1' || Object.values(value.nodes).some(n => typeof n.id !== 'string' || !/^ipvx:agent:[0-9a-f]{64}$/.test(n.id))) throw Error('identity');
      data = value; select.replaceChildren();
      data.deliveries.forEach((message, i) => {
        const option = document.createElement('option'); option.value = i;
        option.textContent = `${message.case || 'Эхо'} · ${labels[message.phase]} · ${i + 1}`; select.append(option);
      });
      select.value = String(data.deliveries.findIndex(m => m.phase === 'review'));
      const identities = $('agent-identities');
      for (const [name, record] of Object.entries(data.nodes)) {
        const p = document.createElement('p'), code = document.createElement('code');
        p.textContent = name + ' · '; code.textContent = record.id; p.append(code); identities.append(p);
      }
      select.disabled = false;
      for (const id of ['agent-play', 'agent-step', 'agent-reset']) $(id).disabled = false;
      choose();
    }).catch(() => { $('agent-message-purpose').textContent = 'Не удалось загрузить запись. Результаты и JSON доступны ниже; обновите страницу для повтора.'; })
    .finally(() => clearTimeout(timeout));
})();
