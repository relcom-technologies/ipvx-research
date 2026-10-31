"""Synthetic state adapter ONLY for offline tests. Never imported by bcp."""
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from bcp.core import Core, Session
from bcp.journal import Journal
from bcp.state import Node, Edge, Connection, Snapshot, StateView, Attestation
from bcp.wire import Checkpoint, decode

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT/'docs/proposals/bcp-0.2'
FIXTURE = json.loads((SPEC/'fixture-context.json').read_text())
VECTORS = json.loads((SPEC/'vectors.json').read_text())['vectors']
BY_ID = {v['id']:v for v in VECTORS}
PROFILE = bytes.fromhex(FIXTURE['profile_id_hex'])
NOW = FIXTURE['now']
MONO = 100.0


def checkpoint(x):
    return Checkpoint(x['number'],bytes.fromhex(x['block_hash_hex']),bytes.fromhex(x['state_root_hex']),x['timestamp'])


def signing(nft):
    n = next(n for n in FIXTURE['nodes'] if int(n['nft_hex'],16) == nft)
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(n['public_test_signing_seed_hex']))


def encryption(nft):
    n = next(n for n in FIXTURE['nodes'] if int(n['nft_hex'],16) == nft)
    return X25519PrivateKey.from_private_bytes(bytes.fromhex(n['public_test_encryption_key_hex']))


def snapshot(c, node_overrides=None, edge_overrides=None, connection_overrides=None):
    nodes,edges,connections = {},{},{}
    for original in FIXTURE['nodes']:
        n = dict(original); nft = int(n['nft_hex'],16); n.update((node_overrides or {}).get(str(nft),{}))
        nodes[nft] = Node(nft,bytes.fromhex(n['owner_hex']),n['key_epoch'],bytes.fromhex(n['signing_public_key_hex']),
                          bytes.fromhex(n['encryption_public_key_hex']),n['status'],n['roles'])
    for original in FIXTURE['edges']:
        n = dict(original);n.update((edge_overrides or {}).get(n['rule_id_hex'],{}));rule=bytes.fromhex(n['rule_id_hex'])
        edges[rule] = Edge(rule,n['from_nft'],n['to_nft'],n['version'],n['from_epoch'],n['to_epoch'],n['cost'],
                           n['max_ciphertext'],n['traffic_mask'],n['status'])
    for original in FIXTURE['connections']:
        n = dict(original);n.update((connection_overrides or {}).get(n['rule_id_hex'],{}));rule=bytes.fromhex(n['rule_id_hex'])
        connections[rule] = Connection(rule,n['source_nft'],n['destination_nft'],n['version'],n['source_epoch'],n['destination_epoch'],
                                       n['traffic_mask'],n['max_hops'],n['max_ciphertext'],n['status'],
                                       frozenset(bytes.fromhex(e) for e in n['allowed_edges_hex']))
    return Snapshot(PROFILE,checkpoint(c),nodes,edges,connections)


def state(assumptions=None):
    a = assumptions or {}
    c = a.get('checkpoint_override',FIXTURE['checkpoint'])
    l = a.get('latest_checkpoint',c)
    flags = dict(FIXTURE['finality_assumptions']); flags.update(a)
    att = Attestation(authenticated=flags['authenticated_state_channel'],chain_identity_matches=flags['chain_identity_matches'],
                      el_synced=flags['el_synced'],cl_synced=flags['cl_synced'],execution_hash_matches=flags['el_cl_execution_hash_match'],
                      finality_tag=flags['finality_tag'],optimistic=flags['execution_optimistic'],finalized_conflict=flags['finalized_conflict'],
                      checkpoint_available=a.get('checkpoint_available',True),latest_extends_packet=True,latest_extends_saved=True)
    return StateView(snapshot(c),snapshot(l,a.get('node_overrides'),a.get('edge_overrides'),a.get('connection_overrides')),att)


def core_for(vector, journal=None):
    a = vector['assumptions'];receiver = vector['receiver_nft'] or 3
    view = state(a)
    mac = bytes.fromhex(next(n['mac_hex'] for n in FIXTURE['nodes'] if int(n['nft_hex'],16) == receiver))
    core = Core(PROFILE,receiver,mac,view,journal or Journal(),decryption_key=encryption(receiver))
    # Each vector is independent and assumes pre-existing sessions/pending nonces.
    # Bypass ONLY the offline test setup; the core has no JSON fixture loader.
    for s in FIXTURE['sessions']:
        t = bytes.fromhex(s['transcript_hex'])
        sid = bytes.fromhex(s['session_id_hex'])
        core._sessions[sid] = Session(sid,s['initiator_nft'],s['responder_nft'],t[144:150],t[150:156],
                                      int.from_bytes(t[64:72],'big'),int.from_bytes(t[72:80],'big'),s['expires_at'],MONO+300)
        for sender in (s['initiator_nft'],s['responder_nft']):
            core._floors[sid,sender] = a.get('last_link_sequence',0)
    hello = decode(bytes.fromhex(BY_ID['V01-HELLO']['bcp_hex']),PROFILE)
    core._remember_hello(hello,MONO)
    challenge = decode(bytes.fromhex(BY_ID['V02-CHALLENGE']['bcp_hex']),PROFILE)
    if receiver == 3:
        core.sent_challenge(challenge,MONO)
    for original in FIXTURE['initial_requester_outbox']:
        core.journal.remember_request(original['requester_nft'],original['responder_nft'],bytes.fromhex(original['message_id_hex']),
                                     bytes.fromhex(original['request_hash_hex']),bytes.fromhex(original['plaintext_hex']))
        if a.get('previous_receipt_phase'):
            core.journal.receipt(original['requester_nft'],original['responder_nft'],bytes.fromhex(original['message_id_hex']),
                                 bytes.fromhex(original['request_hash_hex']),1,b'')
    if a.get('stored_request_hash_hex'):
        req = FIXTURE['initial_requester_outbox'][0]
        core.journal.deliver(req['requester_nft'],bytes.fromhex(req['message_id_hex']),bytes.fromhex(a['stored_request_hash_hex']))
    return core


def receive(core, vector, **overrides):
    a = vector['assumptions']
    options = dict(now=a.get('now',NOW),monotonic=MONO,clock_trusted=a.get('clock_trusted',True));options.update(overrides)
    return core.receive(bytes.fromhex(vector['ethernet_hex']),**options)
