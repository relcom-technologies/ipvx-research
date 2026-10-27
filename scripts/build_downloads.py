"""Rebuild two deterministic, public-only research bundles from explicit inputs."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/downloads'


def pack(name, entries, label, scope):
    DEST.mkdir(exist_ok=True)
    path = DEST / name
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in sorted(entries.items()):
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return dict(name=name, label=label, scope=scope, bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), files=len(entries))


def regular_tree(folder, prefix):
    entries = {}
    for path in sorted((ROOT / folder).rglob('*')):
        if not path.is_file():
            continue
        if path.is_symlink() or '__pycache__' in path.parts or path.suffix == '.pyc':
            if path.is_symlink():
                raise ValueError('A download input must not be a symlink')
            continue
        # Build outputs, downloaded packages and model weights are never public inputs.
        if any(part in ('build', '.venv', 'node_modules', '.git') for part in path.relative_to(ROOT / folder).parts):
            continue
        entries[str(Path(prefix) / path.relative_to(ROOT / folder))] = path.read_bytes()
    return entries


def build():
    prototype = regular_tree('experiments/strict-native', 'source')
    prototype.update(regular_tree('data/strict-native-2026-10-27', 'evidence'))
    readiness = ROOT / 'data/strict-readiness-2026-10-27.json'
    if readiness.exists():
        prototype['readiness/summary.json'] = readiness.read_bytes()
    for name in ['rfc/0006-native-devices-and-bootstrap.md', 'rfc/0007-collaborative-rfc-review.md',
                 'docs/native-device-prototype.md']:
        prototype[name] = (ROOT / name).read_bytes()
    prototype['README-RU.txt'] = '''IPvX: проверенный прототип ОС без TCP/IP

Исходный код, инструкции, полный захват двух виртуальных Ethernet-каналов,
консольные журналы и квитанции. Настоящий запуск:
https://github.com/relcom-technologies/ipvx-research/actions/runs/40500966557
Точная проверенная ревизия: 90adf2c66cef042d0a663d0e34c097963f6b775d.

Начните с source/README.md. В нём сохранён первоначальный план до запуска;
датированное измеренное состояние — в evidence/summary.json и приложении RFC-0006.
Установите зависимости сборки из README, выполните bash scripts/build.sh
и python3 scripts/run.py из папки source/.
Повторный анализ: python3 scripts/verify.py ../evidence/baseline --mode baseline
и python3 scripts/verify.py ../evidence/relay-down --mode relay-down (из source/).
Проверяющему нужен cryptography==50.0.2; путь к evidence задайте относительно архива.

Результат: три целых гостя Linux без INET/IPv6, 16/16 задач SHA-256; 90 кадров.
Без посредника: 0/16; 10 кадров. Ключи Ed25519 в памяти, TOFU, без шифрования.
Один CI-хост, заранее заданные переходы. Это не физическая сеть разных машин,
не работа языковой модели и не измерение выигрыша относительно IP.
Сборочный хост и сайт используют обычный Интернет. Ядро, бинарники и веса модели
в этот небольшой архив не включены. Захваты относятся только к данному опыту.
readiness/summary.json — более поздняя проверка готовности существующих машин,
без загрузки строгой ОС, запуска моделей или изменения сети.
'''.encode()

    history = regular_tree('history', 'history')
    events = [json.loads(line) for line in (ROOT / 'history/events.jsonl').read_text().splitlines() if line.strip()]
    people = json.loads((ROOT / 'history/participants.json').read_text())
    history['history.json'] = (json.dumps(dict(schema_version=1, events=events, participants=people,
                                               snapshot_through=events[-1]['id']), ensure_ascii=False, indent=2)+'\n').encode()
    paragraphs = ['IPvX — атрибутированная история',
                  'Это сводка доступных свидетельств, а не полный стенографический протокол.\n']
    for event in events:
        paragraphs += [f"{event['id']} · {event['title']} [{event['status']}]",
                       f"Автор: {event['attributed_to']}; записал: {event['recorded_by']}; событие: {event['occurred_at'] or 'точная дата неизвестна'}",
                       event['summary'], 'Основание: '+event['decision_rationale'],
                       'Источники: '+'; '.join(event['evidence']),
                       'Ограничения: '+'; '.join(event['limitations']), '']
    history['history-ru.txt'] = '\n'.join(paragraphs).encode()
    history['README.txt'] = (f'''Полная доступная выгрузка журнала IPvX через {events[-1]['id']}.
{len(events)} событий. Начните с history-ru.txt или history.json.
Канонические исходники: history/events.jsonl, participants.json и README.md.
Ретроспективы, неизвестные даты и исходные ошибочные позиции сохранены.
Манифесты Git отражают подписанные в них исторические снимки, а не текущий HEAD.
Запись в истории не означает принятия RFC, независимого аудита или публикации кода.
Это не выгрузка приватной переписки, секретов и всей недоступной старой истории.
''').encode()
    bundles = [pack('ipvx-native-device-prototype.zip', prototype, 'Код, инструкции и захваты трафика',
                    'Проверенный строгий прототип: три гостя на одном CI-хосте, задачи SHA-256, без LLM.'),
               pack('ipvx-research-history.zip', history, 'Полная доступная выгрузка истории',
                    f"{len(events)} событий по {events[-1]['id']}; авторы, основания, проверки и ограничения.")]
    manifest = dict(schema_version=1, snapshot_through=events[-1]['id'], bundles=bundles)
    (DEST / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    (DEST / 'SHA256SUMS.txt').write_text(''.join(f"{b['sha256']}  {b['name']}\n" for b in bundles))
    print(f"Built {len(bundles)} deterministic public bundles through {events[-1]['id']}")


if __name__ == '__main__':
    build()
