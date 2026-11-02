"""Sealed per-run fixture input. No permit, namespace, socket or live RPC here."""
import json
import os
from pathlib import Path
import stat

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from bcp.wire import Checkpoint, Reader
from .common import need, sha, run_id, NODES, private_json

MAX_AGE = 1800
FILES = {'dataset.json', 'bank.json', 'public-keys.json', *(n+'/key.json' for n in NODES)}
FIELDS = {'run_id', 'dataset_sha256', 'bundle_sha256', 'created_at', 'expires_at', 'max_state_age_seconds'}


def parse(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, 'duplicate dataset JSON key')
            result[k] = v
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def read_private(path):
    """Hash/use the same bounded bytes; no symlink, hardlink or special input."""
    p = Path(path)
    need(p.absolute() == p.resolve(), 'dataset path contains a symlink')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.geteuid()
             and stat.S_IMODE(s.st_mode) == 0o600 and s.st_size <= 16*1024*1024, 'unsafe private dataset file')
        with os.fdopen(fd, 'rb', closefd=False) as f: raw = f.read(16*1024*1024+1)
        need(len(raw) <= 16*1024*1024, 'dataset file grew beyond bound')
        return raw
    finally: os.close(fd)


def directory(path):
    p = Path(path).absolute()
    need(p == p.resolve(), 'dataset directory contains a symlink')
    s = p.lstat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid()
         and stat.S_IMODE(s.st_mode) == 0o700, 'unsafe private dataset directory')
    return p


def lifetime(data):
    created = data['created_at']
    need(type(created) is int and created > 0, 'dataset creation time must be an integer')
    points = []
    for env in [data['fresh'], *data['branches'].values()]:
        for encoded in env['points']:
            r = Reader(bytes.fromhex(encoded)); point = Checkpoint.read(r); r.done()
            need(created-60 <= point.timestamp <= created, 'invalid fresh checkpoint time')
            points.append(point.timestamp)
    need(points, 'missing fresh checkpoints')
    # Intentional stale N08 fixture is excluded. Bound all ordinary/fault fresh
    # checkpoints, including the oldest trusted checkpoint, without time relabeling.
    return created, min(created+MAX_AGE, min(points)+MAX_AGE)


def fresh(binding, now):
    need(type(binding) is dict and set(binding) == FIELDS, 'dataset admission fields missing/unknown')
    run_id(binding['run_id'])
    for name in ('dataset_sha256', 'bundle_sha256'):
        value = binding[name]
        need(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'invalid dataset hash')
    start, end = binding['created_at'], binding['expires_at']
    need(type(start) is int and type(end) is int and 0 < start < end <= start+MAX_AGE
         and type(binding['max_state_age_seconds']) is int and binding['max_state_age_seconds'] == MAX_AGE,
         'dataset freshness exceeds protocol bound')
    need(start <= now < end, 'dataset not yet valid or expired')


def descriptor(raw):
    manifest = parse(raw)
    need(type(manifest['schema_version']) is int and manifest['schema_version'] == 1 and set(manifest['files']) == FILES, 'invalid sealed file set')
    result = {k:manifest[k] for k in FIELDS-{'bundle_sha256'}}
    need(manifest['files']['dataset.json'] == result['dataset_sha256'], 'dataset manifest mismatch')
    return dict(result, bundle_sha256=sha(raw)), manifest


def inspect_public(root, expected, now):
    """Children read only public state/manifest; never another actor's key."""
    root = directory(root)
    raw = read_private(root/'bundle.json'); binding, manifest = descriptor(raw)
    need(binding == expected, 'signed dataset binding mismatch')
    fresh(binding, now)
    data_raw = read_private(root/'dataset.json')
    need(sha(data_raw) == binding['dataset_sha256'], 'dataset bytes changed')
    data = parse(data_raw)
    need(data['state_mode'] == 'fixture-state-ethernet' and data['run_id'] == binding['run_id'], 'dataset run/mode mismatch')
    need(lifetime(data) == (binding['created_at'], binding['expires_at']), 'dataset freshness metadata mismatch')
    return data, manifest


def validate_key(raw, node, data):
    key = parse(raw); nft = NODES[node][0]
    need(type(key['nft']) is int and key['nft'] == nft, 'actor key identity mismatch')
    signing = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key['signing']))
    encryption = X25519PrivateKey.from_private_bytes(bytes.fromhex(key['encryption']))
    public = data['bank']['keys'][str(nft)]
    need(signing.public_key().public_bytes_raw().hex() == public['signing']['public_key_hex']
         and encryption.public_key().public_bytes_raw().hex() == public['encryption']['public_key_hex'], 'actor key/public state mismatch')
    return key


def actor_key(path, node, data, manifest):
    raw = read_private(path)
    need(sha(raw) == manifest['files'][node+'/key.json'], 'actor key bytes changed')
    return validate_key(raw, node, data)


def load(root, expected, now):
    root = directory(root); data, manifest = inspect_public(root, expected, now)
    actual = set()
    for p in root.rglob('*'):
        if p.is_dir():
            need(str(p.relative_to(root)) in NODES, 'unexpected dataset directory'); directory(p)
        else: actual.add(str(p.relative_to(root)))
    need(actual == FILES | {'bundle.json'}, 'unexpected/missing dataset files')
    contents = {}
    for name, pin in manifest['files'].items():
        raw = read_private(root/name); need(sha(raw) == pin, 'sealed dataset member changed: '+name)
        contents[name] = raw
    need(sha(contents['dataset.json']) == expected['dataset_sha256'], 'dataset changed during load')
    need(parse(contents['bank.json']) == data['bank'] and parse(contents['public-keys.json']) == data['bank']['keys'], 'public EVM bank mismatch')
    for node in NODES: validate_key(contents[node+'/key.json'], node, data)
    contents['bundle.json'] = read_private(root/'bundle.json')
    need(sha(contents['bundle.json']) == expected['bundle_sha256'], 'bundle changed during load')
    return contents


def seal(root, now):
    root = directory(root)
    data = parse(read_private(root/'dataset.json')); start, end = lifetime(data)
    need(data['state_mode'] == 'fixture-state-ethernet', 'fixture marker required')
    pins = {n:sha(read_private(root/n)) for n in sorted(FILES)}
    private_json(root/'bundle.json', dict(schema_version=1,run_id=run_id(data['run_id']),
        created_at=start,expires_at=end,max_state_age_seconds=MAX_AGE,dataset_sha256=pins['dataset.json'],files=pins))
    binding, _ = descriptor(read_private(root/'bundle.json'))
    load(root, binding, now)
    return binding


def snapshot(contents, destination):
    """Copy verified in-memory bytes, not a second read of mutable input paths."""
    root = Path(destination); root.mkdir(mode=0o700, exist_ok=False)
    for n in NODES: (root/n).mkdir(mode=0o700)
    need(set(contents) == FILES | {'bundle.json'}, 'snapshot file set mismatch')
    for name, raw in contents.items():
        fd = os.open(root/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
