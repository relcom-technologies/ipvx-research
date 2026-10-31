"""Pure packet construction; returns bytes, never sends or admits anything.

Callers must authorize the chosen registry/policy inputs separately. Signing a
packet is not proof that its path or state is authorized.
"""
from .core import HPKE
from .wire import (decode, digest, domain, fixed, header, hpke_info,
                   route_node_input, uint, require)


def hello(profile, node, epoch, nonce, checkpoint, roles, mac, key):
    body = (uint(node,32)+uint(epoch,8)+fixed(nonce,32)+checkpoint.encode()
            +uint(roles,1)+b'\0'+fixed(mac,6))
    h = header(1,268,profile)
    return decode(h+body+key.sign(domain('hello')+h+body),profile)


def handshake(profile, kind, transcript, key):
    require(kind in (2,3), 'UNSUPPORTED_VERSION')
    transcript = fixed(transcript,248)
    body = transcript+digest(domain('session')+profile+transcript)
    h = header(kind,388,profile)
    return decode(h+body+key.sign(domain('challenge' if kind == 2 else 'confirm')+h+body),profile)


def route(profile, session, sequence, checkpoint, nonce, issued, expires, nodes, edges, node_keys, link_key):
    """Offline fixture convenience: each suffix still needs its own real signature.

    This constructor is not a distributed route-discovery implementation. A live
    router must obtain peer-signed suffixes without holding their private keys.
    """
    require(1 <= len(nodes) <= 8 and len(edges) == len(nodes)-1 and len(node_keys) == len(nodes), 'ROUTE_INVALID')
    prefix = (fixed(session,32)+uint(sequence,8)+checkpoint.encode()+fixed(nonce,32)+uint(issued,8)+uint(expires,8)
              +uint(len(nodes),1)+b'\0'*3+b''.join(uint(n,32)+uint(e,8) for n,e in nodes)
              +b''.join(fixed(rule,32)+uint(v,8) for rule,v in edges))
    h = header(4,240+144*len(nodes),profile)
    placeholder = decode(h+prefix+b'\0'*(64*len(nodes)+64),profile)
    body = prefix+b''.join(key.sign(route_node_input(placeholder,i)) for i,key in enumerate(node_keys))
    return decode(h+body+link_key.sign(domain('route-link')+h+body),profile)


def wrap(kind, profile, immutable, path, session, sequence, hop_index, key):
    require(0 <= hop_index < len(path)-1, 'ROUTE_INVALID')
    h = header(kind,44+len(immutable)+208,profile)
    hop = (fixed(session,32)+uint(sequence,8)+uint(hop_index,1)+b'\0'*7+digest(immutable)
           +uint(path[hop_index],32)+uint(path[hop_index+1],32))
    return decode(h+immutable+hop+key.sign(domain('hop')+h+hop),profile)


def rewrap(frame, session, sequence, hop_index, key):
    """Preserves source signature and every immutable byte; no send or IP fallback."""
    require(frame.kind in (5,6,7), 'UNSUPPORTED_VERSION')
    return wrap(frame.kind,frame.profile,frame.fields['immutable'],frame.fields['path'],session,sequence,hop_index,key)


def packet(profile, kind, checkpoint, source, destination, policy, message, packet_id,
           plaintext, path, edges, session, sequence, hop_index, source_key, hop_key,
           destination_key, *, issued, expires, request_hash=None, max_hops=None):
    require(kind in (5,6,7), 'UNSUPPORTED_VERSION')
    require(2 <= len(path) <= 8 and len(edges) == len(path)-1, 'ROUTE_INVALID')
    require(source.nft == path[0] and destination.nft == path[-1], 'ROUTE_INVALID')
    if kind == 5:
        require(request_hash is None or request_hash == digest(plaintext), 'INVALID_PAYLOAD')
        request_hash = digest(plaintext)
    else:
        request_hash = fixed(request_hash,32)
    core = (checkpoint.encode()+fixed(source.owner,20)+uint(source.nft,32)+fixed(destination.owner,20)
            +uint(destination.nft,32)+fixed(policy.rule,32)+uint(policy.version,8)+uint(source.epoch,8)
            +uint(destination.epoch,8)+fixed(message,32)+fixed(packet_id,32)+request_hash+uint(issued,8)+uint(expires,8)
            +uint(len(path)-1 if max_hops is None else max_hops,1)+uint(kind-5,1)+uint(len(path),1)
            +b'\0'+uint(len(plaintext)+16,2)+b'\0'*2)
    prefix = core+b''.join(uint(n,32) for n in path)+b''.join(fixed(rule,32)+uint(v,8) for rule,v in edges)
    h = header(kind,716+72*len(path)+len(plaintext),profile)
    encrypted = HPKE.encrypt(plaintext,destination_key,info=domain('hpke-info')+h+prefix)
    enc, ct = encrypted[:32],encrypted[32:]
    body = prefix+enc+digest(ct)+ct
    immutable = body+source_key.sign(domain('packet')+h+body)
    return wrap(kind,profile,immutable,path,session,sequence,hop_index,hop_key)


def receipt_plaintext(source, message, request_hash, phase, result=b''):
    require(phase in (1,2) and (phase != 1 or result == b''), 'INVALID_PAYLOAD')
    return uint(source,32)+fixed(message,32)+fixed(request_hash,32)+uint(phase,1)+b'\0'*7+uint(len(result),2)+digest(result)+result


def error_plaintext(source, message, request_hash, code):
    require(1 <= code <= 20, 'INVALID_PAYLOAD')
    return uint(source,32)+fixed(message,32)+fixed(request_hash,32)+uint(code,2)+b'\0'*2
