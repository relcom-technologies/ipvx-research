"""Owner-side tools, run on the owner's own computer: key generation and permit signing.

The private key never leaves that computer and is stored encrypted with a passphrase.
Nothing here opens a network connection or touches a stand. The stand prepares a permit
request (stand_launch.py prepare); the owner reads it, signs it here and hands back the
signed permit. Only the public key goes into launch-config.json.

    python3 -m runners.bcp02.owner keygen --key ~/.ipvx/bcp-owner.pem
    python3 -m runners.bcp02.owner sign --key ~/.ipvx/bcp-owner.pem --request request.json --out permit.json
"""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import sys
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .admission import PERMIT_DOMAIN
from .common import need, run_id, sha
from .dataset import parse

FIELDS = {'version', 'scope_sha256', 'run_id', 'host_image_sha256', 'not_before', 'not_after',
          'launch', 'transactions', 'production', 'dataset'}
DATASET = {'run_id', 'dataset_sha256', 'bundle_sha256', 'created_at', 'expires_at', 'max_state_age_seconds'}


def public_hex(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def keygen(path, passphrase):
    path = Path(path).expanduser()
    need(not path.exists(), 'refusing to overwrite an existing key file')
    need(len(passphrase) >= 12, 'passphrase must have at least 12 characters')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(passphrase.encode()))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(pem)
    return public_hex(key)


def load_key(path, passphrase):
    return serialization.load_pem_private_key(Path(path).expanduser().read_bytes(), passphrase.encode())


def check_request(payload, *, now=None):
    """The exact v2 payload admission.verify_permit accepts; refuse anything else before signing."""
    need(isinstance(payload, dict) and set(payload) == FIELDS, 'request must contain exactly the v2 permit fields')
    need(payload['version'] == 2 and payload['launch'] is True and payload['transactions'] == 0
         and payload['production'] is False, 'request must be a v2 launch with 0 transactions, not production')
    for name in ('scope_sha256', 'host_image_sha256'):
        value = payload[name]
        need(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), name + ' must be a SHA-256 hex digest')
    run_id(payload['run_id'])
    d = payload['dataset']
    need(isinstance(d, dict) and set(d) == DATASET and d['run_id'] == payload['run_id'], 'dataset descriptor mismatch')
    need(d['max_state_age_seconds'] == 1800, 'dataset freshness must be 1800 seconds')
    start, end = payload['not_before'], payload['not_after']
    need(all(type(v) is int for v in (start, end, d['created_at'], d['expires_at'])), 'times must be integers')
    need(d['created_at'] <= start < end <= d['expires_at'] and end - start <= 3600, 'window must lie inside the dataset lifetime')
    if now is not None:
        need(now < end, 'request window has already ended')
    return payload


def sign(key, payload):
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    need(parse(raw) == payload, 'payload does not round-trip')
    return dict(payload=base64.b64encode(raw).decode(), signature=base64.b64encode(key.sign(PERMIT_DOMAIN + raw)).decode())


def summary(payload, *, now):
    d = payload['dataset']
    left = payload['not_after'] - int(now)
    return '\n'.join([
        'Permit request for IPVX-BCP02-NET-001-F (isolated run, no transactions, not production)',
        '  run_id            ' + payload['run_id'],
        '  source scope      ' + payload['scope_sha256'],
        '  host image        ' + payload['host_image_sha256'],
        '  dataset           ' + d['dataset_sha256'],
        '  bundle            ' + d['bundle_sha256'],
        '  window (UTC)      ' + time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(payload['not_before']))
        + ' .. ' + time.strftime('%H:%M:%S', time.gmtime(payload['not_after'])),
        '  window ends in    %d min %d s' % (max(left, 0) // 60, max(left, 0) % 60),
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    k = sub.add_parser('keygen'); k.add_argument('--key', required=True)
    s = sub.add_parser('sign'); s.add_argument('--key', required=True); s.add_argument('--request', required=True)
    s.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    if args.command == 'keygen':
        first = getpass.getpass('New passphrase (12+ characters): ')
        need(first == getpass.getpass('Repeat passphrase: '), 'passphrases differ')
        print('owner_public_key ' + keygen(args.key, first))
        print('Keep the key file and passphrase private. Only the public key goes into launch-config.json.')
        return
    payload = check_request(parse(Path(args.request).read_bytes()), now=time.time())
    print(summary(payload, now=time.time()))
    need(input('Type the run_id to sign this permit: ').strip() == payload['run_id'], 'not confirmed; nothing signed')
    key = load_key(args.key, getpass.getpass('Key passphrase: '))
    doc = sign(key, payload)
    out = Path(args.out)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(json.dumps(doc) + '\n')
    print('signed by ' + public_hex(key))
    print('permit sha256 ' + sha(out.read_bytes()))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # a refused request must never print a traceback with key material nearby
        print('refused: ' + str(e), file=sys.stderr)
        raise SystemExit(2)
