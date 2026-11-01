"""Bounded private artifacts and controls. No command carries application data."""
import hashlib
import json
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'experiments/bcp02-net-001'
CASES = ('P01', 'P02', *(f'N{i:02}' for i in range(1, 12)))
NODES = {'A': (1, ('a0',)), 'R': (3, ('r0', 'r1')), 'B': (2, ('b0',))}
MACS = {'a0': '02:bc:02:00:01:01', 'r0': '02:bc:02:00:03:01',
        'r1': '02:bc:02:00:03:02', 'b0': '02:bc:02:00:02:01'}
NEIGHBORS = {'a0': (3, 'r0'), 'r0': (1, 'a0'), 'r1': (2, 'b0'), 'b0': (3, 'r1')}
STAGES = ('START', 'PREPARE', 'PROBE', 'RETRY', 'HANDSHAKE', 'ROTATE', 'DENY_FORWARD',
          'DENY_REVERSE', 'UNAVAILABLE', 'STALE', 'STOP', 'BARRIER')


class Blocked(RuntimeError):
    pass


def need(ok, reason):
    if not ok:
        raise Blocked(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    def pairs(items):
        d = {}
        for k, v in items:
            need(k not in d, 'duplicate JSON key')
            d[k] = v
        return d
    p = Path(path)
    need(not p.is_symlink() and p.stat().st_size <= 16 * 1024 * 1024, 'unsafe JSON input')
    return json.loads(p.read_text(), object_pairs_hook=pairs)


def private_json(path, value):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, sort_keys=True, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())


def control(line):
    need(type(line) is str and len(line) <= 64, 'invalid control length')
    fields = line.strip().split(':')
    need(len(fields) == 2 and fields[0] in CASES and fields[1] in STAGES,
         'control must contain only declared case and barrier name')
    return tuple(fields)


def run_id(value):
    need(type(value) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{7,39}', value), 'invalid run id')
    return value


class Events:
    def __init__(self, path, run, node, notify=lambda e: None):
        self.run, self.node, self.case, self.notify = run_id(run), node, 'P01', notify
        self.file = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600), 'a')

    def emit(self, decision, frame=None, *, rx=None, tx=None, reject=None, latest=None, **extra):
        f = frame.fields if frame else {}
        e = dict(run_id=self.run, case_id=self.case, node=self.node,
                 utc=time.time(), monotonic=time.monotonic(), rx_ifindex=rx, tx_ifindex=tx,
                 kind=frame.kind if frame else None, message_id=f.get('message', b'').hex(),
                 packet_id=f.get('packet', b'').hex(), session_id=f.get('session', b'').hex(),
                 sequence=f.get('sequence'), checkpoint_C=f['checkpoint'].encode().hex() if frame else None,
                 latest_L=latest.encode().hex() if latest else None,
                 immutable_sha256=sha(f['immutable']) if 'immutable' in f else None,
                 source_signature_sha256=sha(f['source_signature']) if 'source_signature' in f else None,
                 decision=decision, reject_code=reject, **extra)
        encoded = json.dumps(e, sort_keys=True)
        need(len(encoded) < 4096, 'event too large')
        self.file.write(encoded + '\n'); self.file.flush(); os.fsync(self.file.fileno())
        self.notify(e)
        return e

    def close(self):
        self.file.close()
