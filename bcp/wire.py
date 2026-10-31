"""Bounded binary codec for BCP-MIN-001 0.2 (not the historical mesh codec)."""
from dataclasses import dataclass
from hashlib import sha256
from struct import pack, unpack
from types import MappingProxyType


ERRORS = ('MALFORMED_HEADER UNSUPPORTED_VERSION PROFILE_MISMATCH NONCANONICAL '
          'PACKET_TOO_LARGE AUTH_FAILED SESSION_REPLAY EXPIRED STATE_UNAVAILABLE '
          'STATE_STALE STATE_CONFLICT TIME_UNTRUSTED KEY_REVOKED POLICY_DENIED '
          'ROUTE_INVALID NO_AUTHORIZED_ROUTE MESSAGE_CONFLICT UNKNOWN '
          'INVALID_PAYLOAD FINALITY_REQUIRED').split()


class Reject(ValueError):
    """A local rejection, never an instruction to emit an ERROR packet."""
    def __init__(self, code):
        self.code = code
        self.number = ERRORS.index(code) + 1
        super().__init__(code)


def require(ok, code):
    if not ok:
        raise Reject(code)


def digest(value):
    return sha256(value).digest()


def domain(label):
    return b'IPvX-BCP/0.2/' + label.encode('ascii') + b'\0'


def uint(value, size):
    if type(value) is not int or not 0 <= value < 1 << (size * 8):
        raise ValueError('unsigned integer out of range')
    return value.to_bytes(size, 'big')


def fixed(value, size):
    if not isinstance(value, bytes) or len(value) != size:
        raise ValueError('incorrect byte field length')
    return value


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, size):
        require(self.offset + size <= len(self.data), 'MALFORMED_HEADER')
        value = self.data[self.offset:self.offset + size]
        self.offset += size
        return value

    def number(self, size):
        return int.from_bytes(self.take(size), 'big')

    def zero(self, size):
        require(not any(self.take(size)), 'NONCANONICAL')

    def done(self):
        require(self.offset == len(self.data), 'MALFORMED_HEADER')


@dataclass(frozen=True)
class Checkpoint:
    number: int
    block_hash: bytes
    state_root: bytes
    timestamp: int

    def encode(self):
        return (uint(self.number, 8) + fixed(self.block_hash, 32)
                + fixed(self.state_root, 32) + uint(self.timestamp, 8))

    @classmethod
    def read(cls, reader):
        return cls(reader.number(8), reader.take(32), reader.take(32), reader.number(8))


def header(kind, length, profile):
    require(1 <= kind <= 7, 'UNSUPPORTED_VERSION')
    require(44 <= length <= 1500, 'PACKET_TOO_LARGE')
    return pack('!4sBBBBHH32s', b'BCP0', 0, 2, kind, 0, length, 0, fixed(profile, 32))


def context_id(chain_id, genesis, addresses, code_hashes):
    """Deployment binding only. This hash does not authenticate chain state."""
    if len(addresses) != 3 or len(code_hashes) != 3:
        raise ValueError('exactly three contracts required')
    context = (domain('context') + uint(chain_id, 32) + fixed(genesis, 32)
               + b''.join(fixed(a, 20) for a in addresses)
               + b''.join(fixed(h, 32) for h in code_hashes)
               + pack('!HHIHHBBIHB', 1, 1500, 1800, 5, 60, 8, 4, 604800, 1, 1))
    return digest(context)


@dataclass(frozen=True)
class Frame:
    kind: int
    profile: bytes
    body: bytes
    fields: dict

    def __post_init__(self):
        object.__setattr__(self, 'fields', MappingProxyType(dict(self.fields)))

    @property
    def header(self):
        return header(self.kind, 44 + len(self.body), self.profile)

    def encode(self):
        return self.header + self.body


def decode(raw, profile):
    require(isinstance(raw, bytes) and len(raw) >= 44 and raw[:4] == b'BCP0', 'MALFORMED_HEADER')
    _, major, minor, kind, flags, size, reserved, found = unpack('!4sBBBBHH32s', raw[:44])
    require((major, minor) == (0, 2) and 1 <= kind <= 7, 'UNSUPPORTED_VERSION')
    require(max(len(raw), size) <= 1500, 'PACKET_TOO_LARGE')
    require(size == len(raw), 'MALFORMED_HEADER')
    require(flags == reserved == 0, 'NONCANONICAL')
    require(found == profile, 'PROFILE_MISMATCH')
    r = Reader(raw[44:]); f = {}
    if kind == 1:
        require(size == 268, 'MALFORMED_HEADER')
        f.update(node=r.number(32), epoch=r.number(8), nonce=r.take(32), checkpoint=Checkpoint.read(r), roles=r.number(1))
        r.zero(1); f.update(mac=r.take(6), signature=r.take(64))
    elif kind in (2, 3):
        require(size == 388, 'MALFORMED_HEADER')
        f.update(initiator=r.number(32), responder=r.number(32), initiator_epoch=r.number(8), responder_epoch=r.number(8),
                 initiator_nonce=r.take(32), responder_nonce=r.take(32), initiator_mac=r.take(6), responder_mac=r.take(6),
                 checkpoint=Checkpoint.read(r), initiator_roles=r.number(1), responder_roles=r.number(1))
        r.zero(2); f.update(expires=r.number(8), session=r.take(32), signature=r.take(64))
    elif kind == 4:
        f.update(session=r.take(32), sequence=r.number(8), checkpoint=Checkpoint.read(r), nonce=r.take(32),
                 issued=r.number(8), expires=r.number(8))
        p = r.number(1); r.zero(3)
        require(1 <= p <= 8, 'ROUTE_INVALID')
        require(size == 240 + 144*p, 'MALFORMED_HEADER')
        f['nodes'] = tuple((r.number(32), r.number(8)) for _ in range(p))
        f['path'] = tuple(n for n, _ in f['nodes'])
        f['edges'] = tuple((r.take(32), r.number(8)) for _ in range(p-1))
        f['node_signatures'] = tuple(r.take(64) for _ in range(p))
        f['signature'] = r.take(64)
        require(len(set(f['path'])) == p, 'ROUTE_INVALID')
    else:
        f.update(checkpoint=Checkpoint.read(r), source_owner=r.take(20), source=r.number(32),
                 destination_owner=r.take(20), destination=r.number(32), rule=r.take(32), version=r.number(8),
                 source_epoch=r.number(8), destination_epoch=r.number(8), message=r.take(32), packet=r.take(32),
                 request_hash=r.take(32), issued=r.number(8), expires=r.number(8), max_hops=r.number(1), traffic=r.number(1))
        p = r.number(1); r.zero(1); ct_size = r.number(2); r.zero(2)
        require(2 <= p <= 8, 'ROUTE_INVALID')
        require(size == 700 + 72*p + ct_size and ct_size >= 16, 'MALFORMED_HEADER')
        f['path'] = tuple(r.number(32) for _ in range(p))
        f['edges'] = tuple((r.take(32), r.number(8)) for _ in range(p-1))
        f['info_prefix'] = raw[44:44+r.offset]
        f.update(enc=r.take(32), payload_hash=r.take(32), ciphertext=r.take(ct_size), source_signature=r.take(64))
        f['immutable'] = raw[44:44+r.offset]
        f.update(session=r.take(32), sequence=r.number(8), hop_index=r.number(1))
        r.zero(7); f.update(immutable_hash=r.take(32), sender=r.number(32), next=r.number(32), signature=r.take(64))
        path = f['path']; i = f['hop_index']
        require(len(set(path)) == p and path[0] == f['source'] and path[-1] == f['destination']
                and 0 <= i < p-1 and path[i:i+2] == (f['sender'], f['next'])
                and p-1 <= f['max_hops'] <= 7, 'ROUTE_INVALID')
        require(f['traffic'] == kind-5, 'NONCANONICAL')
    r.done()
    return Frame(kind, found, raw[44:], f)


def decode_ethernet(raw, profile):
    require(isinstance(raw, bytes) and len(raw) >= 14 and raw[12:14] == b'\x88\xb5', 'MALFORMED_HEADER')
    return raw[:6], raw[6:12], decode(raw[14:], profile)


def ethernet(destination, source, payload):
    return fixed(destination, 6) + fixed(source, 6) + b'\x88\xb5' + payload


def route_node_input(frame, index):
    f = frame.fields
    return (domain('route-node') + frame.profile + f['checkpoint'].encode() + f['nonce']
            + uint(f['issued'], 8) + uint(f['expires'], 8) + uint(len(f['path'])-index, 1)
            + b''.join(uint(n, 32)+uint(e, 8) for n,e in f['nodes'][index:])
            + b''.join(rule+uint(v, 8) for rule,v in f['edges'][index:]))


def signing_inputs(frame):
    if frame.kind == 1:
        return {'hello': domain('hello') + frame.header + frame.body[:-64]}
    if frame.kind in (2, 3):
        label = 'challenge' if frame.kind == 2 else 'confirm'
        return {label: domain(label) + frame.header + frame.body[:-64]}
    if frame.kind == 4:
        return {'route_nodes': [route_node_input(frame, i) for i in range(len(frame.fields['path']))],
                'route_link': domain('route-link') + frame.header + frame.body[:-64]}
    return {'source': domain('packet') + frame.header + frame.fields['immutable'][:-64],
            'hop': domain('hop') + frame.header + frame.body[-208:-64]}


def hpke_info(frame):
    return domain('hpke-info') + frame.header + frame.fields['info_prefix']
