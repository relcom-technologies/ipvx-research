"""Checks over explicit trusted state inputs; not an Ethereum finality verifier.

No RPC/JSON loader is provided. A future authenticated EL+CL adapter must establish
the attestations below. Tests supply synthetic attestations through test helpers.
"""
from dataclasses import dataclass
from types import MappingProxyType

from .wire import Checkpoint, require


@dataclass(frozen=True)
class Node:
    nft: int
    owner: bytes
    epoch: int
    signing_key: bytes
    encryption_key: bytes
    status: int
    roles: int


@dataclass(frozen=True)
class Edge:
    rule: bytes
    source: int
    destination: int
    version: int
    source_epoch: int
    destination_epoch: int
    cost: int
    max_ciphertext: int
    traffic_mask: int
    status: int


@dataclass(frozen=True)
class Connection:
    rule: bytes
    source: int
    destination: int
    version: int
    source_epoch: int
    destination_epoch: int
    traffic_mask: int
    max_hops: int
    max_ciphertext: int
    status: int
    allowed_edges: frozenset

    def __post_init__(self):
        object.__setattr__(self, 'allowed_edges', frozenset(self.allowed_edges))


@dataclass(frozen=True)
class Snapshot:
    profile: bytes
    checkpoint: Checkpoint
    nodes: dict
    edges: dict
    connections: dict

    def __post_init__(self):
        for key in ('nodes', 'edges', 'connections'):
            object.__setattr__(self, key, MappingProxyType(dict(getattr(self, key))))


@dataclass(frozen=True)
class Attestation:
    authenticated: bool = False
    chain_identity_matches: bool = False
    el_synced: bool = False
    cl_synced: bool = False
    execution_hash_matches: bool = False
    finality_tag: str = ''
    optimistic: bool = True
    finalized_conflict: bool = False
    checkpoint_available: bool = False
    # A future trusted adapter supplies ancestry, not an untrusted packet.
    latest_extends_packet: bool = False
    latest_extends_saved: bool | None = None


@dataclass(frozen=True)
class StateView:
    packet: Snapshot
    latest: Snapshot
    attestation: Attestation

    def check(self, profile, checkpoint, now):
        a = self.attestation
        require(all(flag is True for flag in (a.authenticated,a.chain_identity_matches,a.el_synced,a.cl_synced,
                                             a.execution_hash_matches,a.checkpoint_available)), 'STATE_UNAVAILABLE')
        require(a.finality_tag == 'finalized' and a.optimistic is False, 'FINALITY_REQUIRED')
        require(a.finalized_conflict is False, 'STATE_CONFLICT')
        require(self.packet.profile == self.latest.profile == profile
                and self.packet.checkpoint == checkpoint, 'STATE_UNAVAILABLE')
        c, l = checkpoint, self.latest.checkpoint
        require(l.number >= c.number, 'STATE_CONFLICT')
        if l.number == c.number:
            require(l == c, 'STATE_CONFLICT')
        else:
            require(a.latest_extends_packet is True, 'STATE_CONFLICT')
        for s in (self.packet, self.latest):
            require(now - s.checkpoint.timestamp <= 1800, 'STATE_STALE')
            require(s.checkpoint.timestamp <= now+5, 'TIME_UNTRUSTED')
            for n in s.nodes.values():
                require(n.status in (0, 1, 2), 'STATE_UNAVAILABLE')
                if n.status == 1:
                    require(n.roles in (1, 2, 3) and len(n.owner) == 20 and any(n.owner)
                            and len(n.signing_key) == len(n.encryption_key) == 32
                            and any(n.signing_key) and any(n.encryption_key) and n.epoch > 0, 'STATE_UNAVAILABLE')
            for e in (*s.edges.values(), *s.connections.values()):
                require(e.status in (0, 1, 2), 'STATE_UNAVAILABLE')

    def key(self, nft):
        n = self.packet.nodes.get(nft)
        require(n is not None, 'STATE_UNAVAILABLE')
        return n.signing_key

    def node(self, nft, epoch=None, owner=None, role=None):
        c = self.packet.nodes.get(nft); l = self.latest.nodes.get(nft)
        require(c is not None and l is not None and c.status == l.status == 1, 'KEY_REVOKED')
        require((c.owner, c.epoch, c.signing_key, c.encryption_key, c.roles)
                == (l.owner, l.epoch, l.signing_key, l.encryption_key, l.roles), 'KEY_REVOKED')
        require((epoch is None or epoch == c.epoch) and (owner is None or owner == c.owner), 'KEY_REVOKED')
        require(role is None or c.roles & role, 'POLICY_DENIED')
        return c

    def edge(self, rule, version, source, destination, traffic=None, size=0):
        c = self.packet.edges.get(rule); l = self.latest.edges.get(rule)
        require(c is not None and l is not None and c == l and c.status == 1, 'POLICY_DENIED')
        a, b = self.node(source), self.node(destination)
        require((c.source, c.destination, c.version, c.source_epoch, c.destination_epoch)
                == (source, destination, version, a.epoch, b.epoch), 'POLICY_DENIED')
        require(0 <= c.cost < 2**32 and size <= c.max_ciphertext, 'POLICY_DENIED')
        require(traffic is None or c.traffic_mask & (1 << traffic), 'POLICY_DENIED')
        return c

    def neighbors(self, a, b):
        """Both directed consents are required before a session is admitted."""
        for source, destination in ((a, b), (b, a)):
            candidates = [e for e in self.packet.edges.values() if (e.source, e.destination) == (source, destination)]
            valid = False
            from .wire import Reject
            for e in candidates:
                try:
                    self.edge(e.rule, e.version, source, destination)
                    valid = True
                    break
                except Reject:
                    pass
            require(valid, 'POLICY_DENIED')

    def authorize_path(self, path, edges, *, epochs=None, connection=None, traffic=None, size=0, max_hops=None):
        require(1 <= len(path) <= 8 and len(set(path)) == len(path) and len(edges) == len(path)-1, 'ROUTE_INVALID')
        for i,nft in enumerate(path):
            self.node(nft, epoch=epochs[i] if epochs else None,
                      role=2 if 0 < i < len(path)-1 else None)
        policy = None
        if connection is not None:
            rule, version = connection
            policy = self.packet.connections.get(rule); latest = self.latest.connections.get(rule)
            require(policy is not None and latest is not None and policy == latest and policy.status == 1, 'POLICY_DENIED')
            a, b = self.node(path[0]), self.node(path[-1])
            require((policy.source, policy.destination, policy.version, policy.source_epoch, policy.destination_epoch)
                    == (path[0], path[-1], version, a.epoch, b.epoch), 'POLICY_DENIED')
            require(policy.traffic_mask & (1 << traffic) and size <= policy.max_ciphertext
                    and max_hops <= policy.max_hops, 'POLICY_DENIED')
        cost = 0
        for i,(rule,version) in enumerate(edges):
            e = self.edge(rule, version, path[i], path[i+1], traffic, size)
            require(policy is None or rule in policy.allowed_edges, 'POLICY_DENIED')
            cost += e.cost
        return cost
