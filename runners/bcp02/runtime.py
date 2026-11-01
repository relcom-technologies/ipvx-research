"""Additive send-side binding; frozen core/adapter sources remain unchanged."""
from bcp import build
from bcp.wire import digest, require
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
from integration.bcp02.runtime import AdapterCore


class Runtime(AdapterCore):
    def stage(self, message, plaintext, destination, **clock):
        def save(bundle, n, m):
            self.journal.checkpoint(bundle.view.latest.checkpoint, bundle.view.attestation.latest_extends_saved)
            self.journal.remember_request(self._core.local_nft, destination, message, digest(plaintext), plaintext)
        return self._invoke(None, save, **clock)

    def send_packet(self, kind, plaintext, message, packet, request_hash, path, edges, connection,
                    session, sequence, key, *, now, monotonic, clock_trusted):
        def make(bundle, n, m):
            view = bundle.view
            view.authorize_path(path, edges, connection=(connection, view.packet.connections[connection].version),
                                traffic=kind-5, size=len(plaintext)+16, max_hops=len(path)-1)
            self.active(session, path[1], n, m, view)
            source = view.node(path[0], role=1); destination = view.node(path[-1], role=1)
            require(source.nft == self._core.local_nft and key.public_key().public_bytes_raw() == source.signing_key, 'AUTH_FAILED')
            self.journal.checkpoint(view.latest.checkpoint, view.attestation.latest_extends_saved)
            return build.packet(self.profile, kind, view.packet.checkpoint, source, destination,
                view.packet.connections[connection], message, packet, plaintext, path, edges, session, sequence, 0,
                key, key, X25519PublicKey.from_public_bytes(destination.encryption_key),
                issued=n, expires=n+60, request_hash=request_hash)
        return self._invoke(None, make, now=now, monotonic=monotonic, clock_trusted=clock_trusted)

    def active(self, session, peer, now, monotonic, view):
        s = self._core._sessions.get(session)
        require(s is not None and {s.initiator, s.responder} == {self._core.local_nft, peer}
                and now <= s.expires and monotonic <= s.monotonic_deadline, 'AUTH_FAILED')
        for nft in (peer, self._core.local_nft):
            view.node(nft, s.epoch(nft))
        view.neighbors(peer, self._core.local_nft)
        return s

    def forward(self, frame, session, sequence, key, **clock):
        f = frame.fields; index = f['hop_index']+1
        require(f['path'][index] == self._core.local_nft and index < len(f['path'])-1, 'ROUTE_INVALID')
        def make(bundle, n, m):
            view = bundle.view
            view.authorize_path(f['path'], f['edges'], connection=(f['rule'], f['version']),
                                traffic=f['traffic'], size=len(f['ciphertext']), max_hops=f['max_hops'])
            self.active(session, f['path'][index+1], n, m, view)
            require(key.public_key().public_bytes_raw() == view.node(self._core.local_nft).signing_key, 'AUTH_FAILED')
            self.journal.checkpoint(view.latest.checkpoint, view.attestation.latest_extends_saved)
            return build.rewrap(frame, session, sequence, index, key)
        return self._invoke(f['checkpoint'], make, **clock)

    def retry(self, frame, session, sequence, key, **clock):
        f=frame.fields
        require(f['source']==self._core.local_nft, 'AUTH_FAILED')
        def make(bundle,n,m):
            view=bundle.view
            self._core._clock(n,True,f['issued'],f['expires'])
            view.authorize_path(f['path'],f['edges'],connection=(f['rule'],f['version']),
                                traffic=f['traffic'],size=len(f['ciphertext']),max_hops=f['max_hops'])
            self.active(session,f['path'][1],n,m,view)
            require(view.node(f['source']).signing_key==key.public_key().public_bytes_raw(),'AUTH_FAILED')
            self.journal.checkpoint(view.latest.checkpoint,view.attestation.latest_extends_saved)
            return build.rewrap(frame,session,sequence,0,key)
        return self._invoke(f['checkpoint'],make,**clock)
