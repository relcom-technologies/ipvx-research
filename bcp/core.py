"""Offline receive/authorization state machine. All effects are local data.

FORWARD and DELIVER are decisions, not socket writes or application execution.
Do not attach this core to a live interface before the omitted runtime gates
(authenticated chain adapter, resource limits and lifecycle) are implemented.
"""
from dataclasses import dataclass
from math import isfinite

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.hpke import Suite, KEM, KDF, AEAD

from .wire import (Reject, Reader, decode_ethernet, digest, domain, hpke_info,
                   signing_inputs, require, uint, ERRORS)

HPKE = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.CHACHA20_POLY1305)


def verify(key, signature, data):
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(signature, data)
    except (InvalidSignature, ValueError):
        raise Reject('AUTH_FAILED') from None


@dataclass(frozen=True)
class Session:
    identity: bytes
    initiator: int
    responder: int
    initiator_mac: bytes
    responder_mac: bytes
    initiator_epoch: int
    responder_epoch: int
    expires: int
    monotonic_deadline: float

    def mac(self, nft):
        require(nft in (self.initiator, self.responder), 'AUTH_FAILED')
        return self.initiator_mac if nft == self.initiator else self.responder_mac

    def epoch(self, nft):
        require(nft in (self.initiator, self.responder), 'AUTH_FAILED')
        return self.initiator_epoch if nft == self.initiator else self.responder_epoch


@dataclass(frozen=True)
class Decision:
    action: str
    frame: object
    plaintext: bytes | None = None
    disposition: str | None = None


class Core:
    def __init__(self, profile, local_nft, local_mac, state, journal, *, decryption_key=None):
        self.profile, self.local_nft, self.local_mac = profile, local_nft, local_mac
        self.state, self.journal, self.decryption_key = state, journal, decryption_key
        self._sessions = {}
        self._floors = {}
        self._hellos = {}
        self._confirms = {}
        self._challenges = {}
        self._routes = {}
        self._control_tokens, self._control_at, self._hello_at = 32.0, None, None
        self._last_monotonic = None

    def sent_hello(self, frame, monotonic):
        require(frame.kind == 1 and frame.fields['node'] == self.local_nft
                and frame.profile == self.profile and frame.fields['mac'] == self.local_mac, 'AUTH_FAILED')
        self._remember_hello(frame, monotonic)

    def _remember_hello(self, frame, monotonic):
        f = frame.fields
        self._hellos = {k:v for k,v in self._hellos.items() if v[1] >= monotonic}
        require(len(self._hellos) < 8 or (f['node'], f['nonce']) in self._hellos, 'POLICY_DENIED')
        self._hellos[(f['node'], f['nonce'])] = (f, monotonic+5)

    def sent_challenge(self, frame, monotonic):
        require(frame.kind == 2 and frame.profile == self.profile and frame.fields['responder'] == self.local_nft,
                'AUTH_FAILED')
        self._match_hello(frame.fields, monotonic)
        self._confirms = {k:v for k,v in self._confirms.items() if v[1] >= monotonic}
        require(len(self._confirms) < 8 or frame.fields['session'] in self._confirms, 'POLICY_DENIED')
        self._confirms[frame.fields['session']] = (frame.body[:248], monotonic+5)

    def sent_confirm(self, frame, monotonic, now):
        require(frame.kind == 3 and frame.profile == self.profile and frame.fields['initiator'] == self.local_nft,
                'AUTH_FAILED')
        old = self._challenges.pop(frame.fields['session'], None)
        require(old is not None and old[0] == frame.body[:248] and monotonic <= old[1], 'AUTH_FAILED')
        require(now <= frame.fields['expires'], 'EXPIRED')
        self._admit(frame.fields, monotonic, now)

    def _match_hello(self, f, monotonic):
        old = self._hellos.get((f['initiator'], f['initiator_nonce']))
        require(old is not None and monotonic <= old[1], 'AUTH_FAILED')
        h = old[0]
        require((h['epoch'], h['roles'], h['mac'], h['checkpoint']) ==
                (f['initiator_epoch'], f['initiator_roles'], f['initiator_mac'], f['checkpoint']), 'AUTH_FAILED')

    def _admit(self, f, monotonic, now):
        self._sessions = {k:s for k,s in self._sessions.items() if s.monotonic_deadline >= monotonic and s.expires >= now}
        peers = {s.initiator if s.responder == self.local_nft else s.responder for s in self._sessions.values()
                 if s.monotonic_deadline > monotonic}
        peer = f['responder'] if self.local_nft == f['initiator'] else f['initiator']
        require(peer in peers or len(peers) < 4, 'POLICY_DENIED')
        # One current session per peer; replacement cannot accumulate old floors.
        self._sessions = {k:s for k,s in self._sessions.items() if peer not in (s.initiator,s.responder)}
        self._sessions[f['session']] = Session(f['session'], f['initiator'], f['responder'], f['initiator_mac'],
                                              f['responder_mac'], f['initiator_epoch'], f['responder_epoch'],
                                              f['expires'], monotonic+min(300, f['expires']-now))
        self._floors = {k:v for k,v in self._floors.items() if k[0] in self._sessions}
        self._hellos.pop((f['initiator'], f['initiator_nonce']), None)

    def _session(self, f, sender, destination_mac, source_mac, monotonic):
        s = self._sessions.get(f['session'])
        require(s is not None and {s.initiator, s.responder} == {sender,self.local_nft}, 'AUTH_FAILED')
        require(source_mac == s.mac(sender) and destination_mac == s.mac(self.local_nft) == self.local_mac, 'AUTH_FAILED')
        require(f['sequence'] > self._floors.get((s.identity,sender), 0), 'SESSION_REPLAY')
        return s

    def _clock(self, now, trusted, issued=None, expires=None, lifetime=60):
        require(trusted is True and type(now) is int and now >= 0, 'TIME_UNTRUSTED')
        if issued is not None:
            require(0 < expires-issued <= lifetime and issued <= now+5 and now <= expires, 'EXPIRED')

    def receive(self, ethernet_bytes, *, now, monotonic, clock_trusted):
        destination_mac, source_mac, frame = decode_ethernet(ethernet_bytes, self.profile)
        f = frame.fields; k = frame.kind; inputs = signing_inputs(frame)
        require(type(monotonic) in (float,int) and isfinite(monotonic) and monotonic >= 0, 'TIME_UNTRUSTED')
        require(self._last_monotonic is None or monotonic >= self._last_monotonic, 'TIME_UNTRUSTED')
        self._last_monotonic = monotonic
        if k <= 4:
            if self._control_at is not None:
                require(monotonic >= self._control_at, 'TIME_UNTRUSTED')
                self._control_tokens = min(32.0,self._control_tokens+16*(monotonic-self._control_at))
            self._control_at = monotonic
            require(self._control_tokens >= 1, 'POLICY_DENIED')
            self._control_tokens -= 1
            if k == 1:
                require(self._hello_at is None or monotonic-self._hello_at >= 1, 'POLICY_DENIED')
                self._hello_at = monotonic
        if k == 1:
            require(destination_mac == b'\xff'*6 and f['mac'] == source_mac, 'AUTH_FAILED')
            verify(self.state.key(f['node']), f['signature'], inputs['hello'])
        elif k in (2,3):
            signer = f['responder'] if k == 2 else f['initiator']
            receiver = f['initiator'] if k == 2 else f['responder']
            require(receiver == self.local_nft and f['initiator'] != f['responder']
                    and f['initiator_mac'] != f['responder_mac'], 'AUTH_FAILED')
            require(destination_mac == self.local_mac == f['initiator_mac' if k == 2 else 'responder_mac']
                    and source_mac == f['responder_mac' if k == 2 else 'initiator_mac'], 'AUTH_FAILED')
            require(f['session'] == digest(domain('session') + self.profile + frame.body[:248]), 'AUTH_FAILED')
            verify(self.state.key(signer), f['signature'], inputs['challenge' if k == 2 else 'confirm'])
            self._match_hello(f, monotonic)
            if k == 3:
                pending = self._confirms.get(f['session'])
                require(pending is not None and pending[0] == frame.body[:248] and monotonic <= pending[1], 'AUTH_FAILED')
        else:
            sender = f['path'][0] if k == 4 else f['sender']
            if k == 4:
                require(self.local_nft not in f['path'], 'ROUTE_INVALID')
            else:
                require(f['next'] == self.local_nft, 'ROUTE_INVALID')
            session = self._session(f, sender, destination_mac, source_mac, monotonic)
            verify(self.state.key(sender), f['signature'], inputs['route_link' if k == 4 else 'hop'])
            if k >= 5:
                require(f['immutable_hash'] == digest(f['immutable']), 'AUTH_FAILED')
            # Authentication and immutable binding precede the anti-replay commit.
            self._floors[(session.identity,sender)] = f['sequence']
            if k == 4:
                for nft, signature, data in zip(f['path'], f['node_signatures'], inputs['route_nodes']):
                    verify(self.state.key(nft), signature, data)
            else:
                verify(self.state.key(f['source']), f['source_signature'], inputs['source'])
                require(digest(f['ciphertext']) == f['payload_hash'], 'INVALID_PAYLOAD')
        self._clock(now, clock_trusted, f.get('issued'), f.get('expires'), 30 if k == 4 else 60)
        if k in (2,3):
            require(0 < f['expires']-now <= 300, 'EXPIRED')
        if k >= 4:
            require(now <= session.expires and monotonic <= session.monotonic_deadline, 'EXPIRED')
        self.state.check(self.profile, f['checkpoint'], now)
        self.journal.checkpoint(self.state.latest.checkpoint, self.state.attestation.latest_extends_saved)
        if k == 1:
            n = self.state.node(f['node'], f['epoch'])
            require(f['roles'] == n.roles, 'POLICY_DENIED')
            self._remember_hello(frame, monotonic)
            return Decision('PENDING_CHALLENGE', frame)
        if k in (2,3):
            for label in ('initiator','responder'):
                n = self.state.node(f[label], f[label+'_epoch'])
                require(f[label+'_roles'] == n.roles, 'POLICY_DENIED')
            self.state.neighbors(f['initiator'],f['responder'])
            if k == 2:
                self._challenges = {k:v for k,v in self._challenges.items() if v[1] >= monotonic}
                require(len(self._challenges) < 8 or f['session'] in self._challenges, 'POLICY_DENIED')
                self._challenges[f['session']] = (frame.body[:248],monotonic+5)
                return Decision('CONFIRM_SESSION', frame)
            self._confirms.pop(f['session'])
            self._admit(f,monotonic,now)
            return Decision('ADMIT_SESSION', frame)
        self.state.node(sender,session.epoch(sender)); self.state.node(self.local_nft,session.epoch(self.local_nft))
        self.state.neighbors(sender,self.local_nft)
        if k == 4:
            cost = self.state.authorize_path(f['path'],f['edges'],epochs=tuple(e for _,e in f['nodes']))
            if len(f['path']) > 1:
                self.state.node(sender,role=2)
            self._routes = {k:v for k,v in self._routes.items() if v[1] >= monotonic}
            require(len(self._routes) < 64 or frame.encode() in self._routes, 'POLICY_DENIED')
            self._routes[frame.encode()] = (frame,monotonic+5,cost)
            return Decision('CACHE_ROUTE', frame)
        self.state.node(f['source'], f['source_epoch'], f['source_owner'], role=1)
        self.state.node(f['destination'], f['destination_epoch'], f['destination_owner'], role=1)
        self.state.authorize_path(f['path'], f['edges'], connection=(f['rule'], f['version']),
                                  traffic=f['traffic'], size=len(f['ciphertext']), max_hops=f['max_hops'])
        if self.local_nft != f['destination']:
            return Decision('FORWARD', frame)
        require(self.decryption_key is not None, 'STATE_UNAVAILABLE')
        require(self.decryption_key.public_key().public_bytes_raw() == self.state.node(self.local_nft).encryption_key,
                'KEY_REVOKED')
        try:
            plaintext = HPKE.decrypt(f['enc']+f['ciphertext'], self.decryption_key, info=hpke_info(frame))
        except (InvalidTag, ValueError):
            raise Reject('INVALID_PAYLOAD') from None
        if k == 5:
            require(digest(plaintext) == f['request_hash'], 'INVALID_PAYLOAD')
            disposition = self.journal.deliver(f['source'], f['message'], f['request_hash'])
        else:
            disposition = self._response(f, plaintext, k)
        return Decision('DELIVER', frame, plaintext, disposition)

    def _response(self, f, plaintext, kind):
        r = Reader(plaintext)
        try:
            original_source, message, request_hash = r.number(32), r.take(32), r.take(32)
            require((original_source,message,request_hash) == (self.local_nft,f['message'],f['request_hash']), 'INVALID_PAYLOAD')
            if kind == 6:
                phase = r.number(1); r.zero(7); size = r.number(2); result_hash = r.take(32); result = r.take(size)
                require(phase in (1,2) and result_hash == digest(result)
                        and (phase != 1 or size == 0), 'INVALID_PAYLOAD')
                error = None
            else:
                phase, result = 0, b''
                error = r.number(2); r.zero(2)
                require(1 <= error <= len(ERRORS), 'INVALID_PAYLOAD')
            r.done()
        except Reject:
            raise Reject('INVALID_PAYLOAD') from None
        self.journal.receipt(original_source,f['source'],message,request_hash,phase,result,error)
        return 'RECEIPT' if kind == 6 else 'ERROR_RECORDED'

    def routes(self, *, now, monotonic, clock_trusted):
        """Recheck revocations and local liveness before returning candidates."""
        self._clock(now,clock_trusted)
        require(type(monotonic) in (float,int) and isfinite(monotonic)
                and (self._last_monotonic is None or monotonic >= self._last_monotonic), 'TIME_UNTRUSTED')
        candidates = []
        for frame, deadline, _ in self._routes.values():
            if monotonic > deadline or now > frame.fields['expires']:
                continue
            f = frame.fields
            try:
                session = self._sessions.get(f['session'])
                require(session is not None and now <= session.expires and monotonic <= session.monotonic_deadline, 'EXPIRED')
                self.state.check(self.profile,f['checkpoint'],now)
                self.journal.checkpoint(self.state.latest.checkpoint,self.state.attestation.latest_extends_saved)
                cost = self.state.authorize_path(f['path'],f['edges'],epochs=tuple(e for _,e in f['nodes']))
                self.state.node(self.local_nft,session.epoch(self.local_nft))
                self.state.node(f['path'][0],session.epoch(f['path'][0]))
                self.state.neighbors(self.local_nft,f['path'][0])
                local_costs = []
                for e in self.state.packet.edges.values():
                    if (e.source,e.destination) != (self.local_nft,f['path'][0]):
                        continue
                    try:
                        local_costs.append(self.state.edge(e.rule,e.version,e.source,e.destination).cost)
                    except Reject:
                        pass
                require(bool(local_costs), 'POLICY_DENIED')
                cost += min(local_costs)
                candidates.append((cost,len(f['edges'])+1,uint(self.local_nft,32)+b''.join(uint(n,32) for n in f['path']),frame))
            except Reject:
                continue
        return [c[-1] for c in sorted(candidates,key=lambda c:c[:3])]
