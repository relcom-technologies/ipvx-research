"""Verified full-capture records; no fabricated timing or additional experiment."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import heapq

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/strict-native-2026-10-27'
spec = importlib.util.spec_from_file_location('strict_verifier', ROOT / 'experiments/strict-native/scripts/verify.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

MACS = {'025800000001': 'A', '025800000011': 'R',
        '025800000012': 'R', '025800000002': 'B'}
KINDS = {1: 'TASK', 2: 'RESULT', 3: 'HELLO'}


def capture_records(path, keys):
    data = path.read_bytes()
    # The independently checked source capture is classic little-endian microsecond PCAP.
    if data[:4] != b'\xd4\xc3\xb2\xa1':
        raise ValueError('Unexpected timestamp encoding')
    frames = list(verifier.packets(path))
    offset = 24
    records = []
    origin = None
    for number, frame in enumerate(frames, 1):
        seconds, micros, size, original = struct.unpack('<IIII', data[offset:offset+16])
        offset += 16+size
        parsed = verifier.frame_record(frame, keys)
        body = frame[14:]
        source = MACS[frame[6:12].hex()]
        endpoints = ('A', 'R') if path.stem == 'ar' else ('R', 'B')
        if source not in endpoints:
            raise ValueError('Unexpected Ethernet source on fixed link')
        destination = next(x for x in endpoints if x != source)
        length = struct.unpack('!H', body[20:22])[0]
        timestamp = seconds*1_000_000+micros
        if origin is None:
            origin = timestamp
        records.append(dict(parsed, capture=f'{path.parent.name}/{path.name}', capture_frame=number,
                            timestamp_us=timestamp, link_at_ms=(timestamp-origin)/1000, link=path.stem,
                            from_node=source, to_node=destination, kind=KINDS[parsed['kind']],
                            frame_bytes=original, source_id=body[28:60].hex(), destination_id=body[60:92].hex(),
                            frame_sha256=hashlib.sha256(frame).hexdigest(), frame_hex=frame.hex(),
                            payload_hex=body[188:188+length].hex(), signature_verified=True))
    return records


def causal_order(frames):
    """Preserve each capture's order and match data packets across relay ports.

    QEMU dump timestamps use each process's virtual clock. Sorting both files by
    those timestamps can place a forwarded task before its sending frame. The
    output is a deterministic causal presentation, not a measured global clock.
    HELLO repeats have no unique sequence, so their inter-link order is unknown.
    """
    edges, degree = [set() for _ in frames], [0 for _ in frames]

    def before(a, b):
        if b not in edges[a]:
            edges[a].add(b); degree[b] += 1

    for link in ['ar', 'rb']:
        indexes = [i for i,f in enumerate(frames) if f['link'] == link]
        for a,b in zip(indexes,indexes[1:]):
            before(a,b)
    matches = 0
    for kind in ['TASK','RESULT']:
        source_link, target_link = ('ar','rb') if kind == 'TASK' else ('rb','ar')
        for sequence in range(1,17):
            source = [i for i,f in enumerate(frames) if f['kind'] == kind and f['sequence'] == sequence and f['link'] == source_link]
            target = [i for i,f in enumerate(frames) if f['kind'] == kind and f['sequence'] == sequence and f['link'] == target_link]
            if len(target) > len(source):
                raise ValueError('A forwarded data frame has no captured source')
            for a,b in zip(source,target):
                # Compare signed immutable content, excluding the relay-mutated TTL/CRC.
                ca, cb = bytearray.fromhex(frames[a]['frame_hex'][28:]), bytearray.fromhex(frames[b]['frame_hex'][28:])
                for content in [ca,cb]:
                    content[6]=0;content[24:28]=bytes(4)
                if ca != cb:
                    raise ValueError('The forwarded frame differs from its captured source')
                before(a,b); matches += 1
    available = [(frames[i]['link_at_ms'],frames[i]['link'],i) for i,n in enumerate(degree) if not n]
    heapq.heapify(available); ordered = []
    while available:
        _,_,i = heapq.heappop(available); ordered.append(frames[i])
        for j in edges[i]:
            degree[j] -= 1
            if not degree[j]:
                heapq.heappush(available,(frames[j]['link_at_ms'],frames[j]['link'],j))
    if len(ordered) != len(frames):
        raise ValueError('Captured frame order conflicts with verified forwarding')
    return ordered, matches


def build():
    summary = json.loads((FOLDER/'summary.json').read_text())
    scenarios = []
    for name in ['baseline', 'relay-down']:
        receipt = json.loads((FOLDER/name/'receipt.json').read_text())
        # Never rewrite measured receipts to make a generated view pass.
        for file in ['ar.pcap', 'rb.pcap', 'A.console.log', 'R.console.log', 'B.console.log']:
            if hashlib.sha256((FOLDER/name/file).read_bytes()).hexdigest() != receipt['hashes'][file]:
                raise ValueError('Measured evidence hash changed: '+file)
        frames = []
        for link in ['ar', 'rb']:
            frames += capture_records(FOLDER/name/f'{link}.pcap', {int(k): v for k,v in receipt['node_keys'].items()})
        frames, matches = causal_order(frames)
        for index, frame in enumerate(frames):
            frame['index'] = index
        if len(frames) != receipt['all_capture_frames_verified']:
            raise ValueError('Replay omits a captured frame')
        scenarios.append(dict(id=name, frames=frames, completed_tasks=receipt['completed_sha256_tasks'],
                              total_tasks=16, socket_rejections=receipt['kernel_socket_rejections'],
                              matched_data_forwards=matches,
                              receipt=f'data/strict-native-2026-10-27/{name}/receipt.json'))
    result = dict(schema_version=1, status='saved_measured_capture', source_revision=summary['source_revision'],
                  run_url=summary['run_url'], clock='Per-capture QEMU virtual clocks; no global cross-link latency or chronology established',
                  order='Per-link capture order plus matched immutable TASK/RESULT forwarding; other inter-link interleaving is illustrative',
                  scope='Three whole guests without INET/IPv6, deterministic SHA-256; one physical CI host; no LLM.',
                  scenarios=scenarios)
    (ROOT/'data/packet-replay.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',',':'))+'\n')
    print('Verified and exported all capture frames:', [len(s['frames']) for s in scenarios])


if __name__ == '__main__':
    build()
