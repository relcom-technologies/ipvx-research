"""Independently inspect full-link pcap, signed frames and guest console receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HEADER = 188
CASES = 16


def events(path):
    return [json.loads(line[10:]) for line in path.read_text(errors='replace').splitlines()
            if line.startswith('XNS_EVENT ')]


def packets(path):
    data = path.read_bytes()
    if len(data) < 24:
        raise ValueError('Missing full pcap global header')
    endian = {b'\xd4\xc3\xb2\xa1': '<', b'\xa1\xb2\xc3\xd4': '>',
              b'\x4d\x3c\xb2\xa1': '<', b'\xa1\xb2\x3c\x4d': '>'}.get(data[:4])
    if endian is None or struct.unpack(endian+'I', data[20:24])[0] != 1:
        raise ValueError('Expected classic Ethernet pcap')
    offset = 24
    while offset < len(data):
        if offset + 16 > len(data):
            raise ValueError('Truncated pcap record header')
        _, _, captured, original = struct.unpack(endian+'IIII', data[offset:offset+16])
        offset += 16
        if captured != original or offset + captured > len(data):
            raise ValueError('Truncated Ethernet capture')
        yield data[offset:offset+captured]
        offset += captured


def expected(sequence):
    return hashlib.sha256(bytes((sequence*31+i*17) & 255 for i in range(1024))).hexdigest()


def frame_record(frame, keys):
    if len(frame) < 14:
        raise ValueError('Short Ethernet frame')
    ether_type, offset = struct.unpack('!H', frame[12:14])[0], 14
    while ether_type in (0x8100, 0x88a8, 0x9100):
        if len(frame) < offset+4:
            raise ValueError('Short VLAN frame')
        ether_type = struct.unpack('!H', frame[offset+2:offset+4])[0]
        offset += 4
    if ether_type != 0x88b5:
        raise ValueError(f'Unexpected whole-link EtherType: {ether_type:#06x}')
    body = frame[offset:]
    if len(body) < HEADER or body[:4] != b'XNS1' or body[4] != 1 or body[5] not in (1, 2, 3):
        raise ValueError('Unknown protocol/version')
    size = struct.unpack('!H', body[20:22])[0]
    if size > 1300 or len(body) < HEADER+size or not 1 <= body[6] <= 8 or body[7] or body[22:24] != b'\0\0':
        raise ValueError('Invalid frame bounds')
    body = body[:HEADER+size]
    crc = bytearray(body);crc[24:28] = bytes(4)
    if zlib.crc32(crc) != struct.unpack('!I', body[24:28])[0]:
        raise ValueError('CRC mismatch')
    sequence, source, destination = struct.unpack('!III', body[8:20])
    public = body[92:124]
    if hashlib.sha256(public).digest() != body[28:60]:
        raise ValueError('Node ID is not SHA256(public key)')
    if source not in keys or keys[source]['public_key'] != public.hex():
        raise ValueError('Frame key differs from actual guest-generated key')
    signed = bytearray(body);signed[6]=0;signed[24:28]=bytes(4);signed[124:188]=bytes(64)
    Ed25519PublicKey.from_public_bytes(public).verify(body[124:188], bytes(signed))
    if body[5] == 3 and (destination != 0 or sequence != 0 or body[60:92] != bytes(32) or body[HEADER:] != b'HELLO'):
        raise ValueError('Invalid signed HELLO fixture')
    if body[5] in (1, 2):
        if destination not in keys or body[60:92].hex() != keys[destination]['node_id']:
            raise ValueError('Task/result destination ID mismatch')
        if not 1 <= sequence <= CASES:
            raise ValueError('Unknown task sequence')
        payload = body[HEADER:]
        if body[5] == 1:
            if source != 1 or destination != 2 or payload != bytes((sequence*31+i*17) & 255 for i in range(1024)):
                raise ValueError('Task bytes differ from the actual fixture')
        elif source != 2 or destination != 1 or payload.decode('ascii') != expected(sequence):
            raise ValueError('Result differs from independently calculated SHA256')
    return {'kind': body[5], 'sequence': sequence, 'source_role': source,
            'destination_role': destination, 'hop_limit': body[6], 'bytes': len(body)}


def verify(directory, mode):
    logs = {node: events(directory/f'{node}.console.log') for node in 'ARB'}
    keys = {}
    for node, role in [('A', 1), ('B', 2), ('R', 3)]:
        rows = logs[node]
        boot = [row for row in rows if row.get('event') == 'boot']
        if len(boot) != 1:
            raise ValueError('One actual boot and generated key per guest is required')
        keys[role] = {'public_key': boot[0]['public_key'], 'node_id': boot[0]['node_id']}
        if hashlib.sha256(bytes.fromhex(boot[0]['public_key'])).hexdigest() != boot[0]['node_id']:
            raise ValueError('Boot public key and ID mismatch')
        probes = [row for row in rows if row.get('event') == 'socket_probe']
        expected_probes = {(family, kind) for family in ['AF_INET', 'AF_INET6'] for kind in ['stream', 'datagram']}
        if {(row['family'], row['kind']) for row in probes} != expected_probes:
            raise ValueError('Missing negative kernel socket probe')
        if any(not row['rejected'] or row['errno'] != 97 for row in probes):
            raise ValueError('IP-family socket was not rejected with EAFNOSUPPORT on x86_64 Linux')
        if not any(row.get('event') == 'unix_probe' and row['available'] for row in rows):
            raise ValueError('AF_UNIX unavailable')
        if sum(row.get('event') == 'packet_probe' and row['available'] for row in rows) != (2 if node == 'R' else 1):
            raise ValueError('Missing actual AF_PACKET interface probe')
    captured = {name: [frame_record(frame, keys) for frame in packets(directory/f'{name}.pcap')]
                for name in ['ar', 'rb']}
    results = [row for row in logs['A'] if row.get('event') == 'task_result']
    for row in results:
        if row['sha256'] != expected(row['sequence']):
            raise ValueError('Console task result is wrong')
    if mode == 'baseline':
        if len(results) != CASES or {row['sequence'] for row in results} != set(range(1, CASES+1)):
            raise ValueError('Not all sixteen actual tasks completed')
        if not any(row.get('event') == 'summary' and row['ok'] and row['completed'] == CASES for row in logs['A']):
            raise ValueError('Missing successful guest summary')
        if any(row.get('event') == 'failure' for rows in logs.values() for row in rows):
            raise ValueError('A guest reported failure')
        if not any(row.get('event') == 'duplicate' for row in logs['B']):
            raise ValueError('Duplicate delivery did not exercise receiver deduplication')
        for name, frames in captured.items():
            for sequence in range(1, CASES+1):
                for kind in (1, 2):
                    if not any(row['sequence'] == sequence and row['kind'] == kind for row in frames):
                        raise ValueError(f'{name}: missing task/result frame for {sequence}')
    else:
        if len(results) >= CASES or any(row.get('event') == 'summary' for row in logs['A']):
            raise ValueError('Relay removal did not prevent completion')
        if not any(row.get('event') == 'failure' and row['step'] in ('hello_timeout', 'task_timeout') for row in logs['A']):
            raise ValueError('Expected actual connectivity timeout was not observed')
    receipt = {'schema_version': 1, 'mode': mode, 'passed': True, 'actual_guests': 3,
               'topology': 'A--R--B; no direct A/B link', 'guest_ip_stack': 'compiled_out_and_probed',
               'kernel_socket_rejections': 12, 'all_capture_frames_verified': sum(map(len, captured.values())),
               'ether_types': ['0x88b5'], 'node_keys': keys, 'completed_sha256_tasks': len(results),
               'llm': False, 'confidentiality': False, 'identity': 'guest-generated Ed25519; SHA256(public key); RAM only',
               'admission': 'TOFU role binding on fixed private links; not external operator admission',
               'routing': 'fixed forwarding table; no dynamic discovery of paths or failover',
               'hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in directory.iterdir() if path.is_file() and path.name != 'receipt.json'}}
    (directory/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({'mode': mode, 'passed': True, 'tasks': len(results),
                      'all_frames_verified': receipt['all_capture_frames_verified']}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path)
    parser.add_argument('--mode',choices=['baseline','relay-down'],required=True)
    args=parser.parse_args();verify(args.directory,args.mode)
