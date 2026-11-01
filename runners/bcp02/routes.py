"""Construct ROUTE by retaining verified peer suffix signatures, signing only self."""
from bcp.core import verify
from bcp.wire import decode, domain, fixed, header, route_node_input, signing_inputs, uint, require


def advertise(profile, checkpoint, node, key, session, sequence, nonce, issued, expires,
              *, suffix=None, edge=None, view=None):
    require(key.public_key().public_bytes_raw() == node.signing_key, 'AUTH_FAILED')
    nodes, edges, signatures = ((node.nft, node.epoch),), (), ()
    if suffix is not None:
        f = suffix.fields
        require(suffix.kind == 4 and suffix.profile == profile and f['checkpoint'] == checkpoint
                and node.nft not in f['path'] and len(f['path']) < 8 and view is not None, 'ROUTE_INVALID')
        require((nonce, issued, expires) == (f['nonce'], f['issued'], f['expires']), 'ROUTE_INVALID')
        view.check(profile, checkpoint, issued)
        view.authorize_path(f['path'], f['edges'], epochs=tuple(e for _, e in f['nodes']))
        for (nft, epoch), signature, data in zip(f['nodes'], f['node_signatures'], signing_inputs(suffix)['route_nodes']):
            verify(view.node(nft, epoch).signing_key, signature, data)
        require(node.roles & 2 and edge is not None, 'POLICY_DENIED')
        view.edge(*edge, node.nft, f['path'][0])
        nodes += f['nodes']; edges = (edge,) + f['edges']; signatures = f['node_signatures']
    prefix = (fixed(session, 32) + uint(sequence, 8) + checkpoint.encode() + fixed(nonce, 32)
              + uint(issued, 8) + uint(expires, 8) + uint(len(nodes), 1) + b'\0'*3
              + b''.join(uint(n, 32)+uint(e, 8) for n, e in nodes)
              + b''.join(fixed(rule, 32)+uint(v, 8) for rule, v in edges))
    h = header(4, 240+144*len(nodes), profile)
    unsigned = decode(h+prefix+b'\0'*64+ b''.join(signatures)+b'\0'*64, profile)
    body = prefix + key.sign(route_node_input(unsigned, 0)) + b''.join(signatures)
    return decode(h+body+key.sign(domain('route-link')+h+body), profile)
