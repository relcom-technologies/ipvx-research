"""Refresh adapter state for every core operation; return local decisions only.

No state/attestation input, network interface, transaction, automatic response,
message-ID allocation, application execution or fallback cache is exposed.
"""
from math import ceil,isfinite
import sqlite3
import time

from adapters.bcp02.binding import Selection
from bcp import build
from bcp.core import Core,verify
from bcp.wire import Frame,Reject,decode,decode_ethernet,digest,require,signing_inputs
from .journal import BoundJournal


class AdapterCore:
    def __init__(self,adapter,journal,selection,local_nft,local_mac,*,decryption_key=None):
        require(type(selection) is Selection and isinstance(journal,BoundJournal),'STATE_UNAVAILABLE')
        require(journal.profile==adapter.binding.profile and journal.local_nft==local_nft,'STATE_CONFLICT')
        require(local_nft in selection.nfts and type(local_mac) is bytes and len(local_mac)==6,'POLICY_DENIED')
        self.adapter,self.journal,self.selection=adapter,journal,selection
        self.profile=adapter.binding.profile
        self._core=Core(self.profile,local_nft,local_mac,None,journal,decryption_key=decryption_key)

    def _scope(self,frame):
        f=frame.fields
        nfts=(f['node'],) if frame.kind==1 else ((f['initiator'],f['responder']) if frame.kind in (2,3) else f['path'])
        require(all(n in self.selection.nfts for n in nfts),'POLICY_DENIED')
        require(all(e in self.selection.edges for e,_ in f.get('edges',())),'POLICY_DENIED')
        if frame.kind>=5:require(f['rule'] in self.selection.connections,'POLICY_DENIED')

    def _canonical(self,frame):
        require(type(frame) is Frame,'MALFORMED_HEADER')
        frame=decode(frame.encode(),self.profile);self._scope(frame)
        return frame

    def _invoke(self,checkpoint,callback,*,now,monotonic,clock_trusted):
        self._core._clock(now,clock_trusted)
        require(type(monotonic) in (int,float) and isfinite(monotonic) and monotonic>=0,'TIME_UNTRUSTED')
        require(self._core._last_monotonic is None or monotonic>=self._core._last_monotonic,'TIME_UNTRUSTED')
        started=time.monotonic()
        try:
            with self.journal.guard() as saved:
                try:
                    self._core.state=None
                    bundle=self.adapter.read(self.selection,now=now,clock_trusted=clock_trusted,
                        packet_checkpoint=checkpoint,confirmed_core_checkpoint=saved)
                    elapsed=time.monotonic()-started
                    require(isfinite(elapsed) and 0<=elapsed<=self.adapter.limits.deadline_seconds,'STATE_UNAVAILABLE')
                    ended_now,ended_mono=now+ceil(elapsed),monotonic+elapsed
                    view=bundle.view;view.check(self.profile,view.packet.checkpoint,ended_now)
                    self._core.state=view
                    self._core._last_monotonic=ended_mono
                    return callback(bundle,ended_now,ended_mono)
                finally:self._core.state=None  # no fallback; only the lock owner clears state
        except sqlite3.Error:raise Reject('STATE_UNAVAILABLE') from None

    def state(self,*,now,monotonic,clock_trusted,checkpoint=None):
        """Read/commit a complete bundle for pure host-side packet construction."""
        def publish(bundle,n,m):
            self.journal.checkpoint(bundle.view.latest.checkpoint,bundle.view.attestation.latest_extends_saved)
            return bundle
        return self._invoke(checkpoint,publish,now=now,monotonic=monotonic,clock_trusted=clock_trusted)

    def receive(self,raw,*,now,monotonic,clock_trusted):
        _,_,frame=decode_ethernet(raw,self.profile);self._scope(frame)
        return self._invoke(frame.fields['checkpoint'],lambda b,n,m:self._core.receive(raw,now=n,monotonic=m,clock_trusted=True),
                            now=now,monotonic=monotonic,clock_trusted=clock_trusted)

    def _sent(self,frame,kind,*,now,monotonic,clock_trusted):
        frame=self._canonical(frame);require(frame.kind==kind,'UNSUPPORTED_VERSION')
        def commit(bundle,n,m):
            f=frame.fields;view=bundle.view
            signer=f['node'] if kind==1 else f['responder'] if kind==2 else f['initiator']
            require(signer==self._core.local_nft,'AUTH_FAILED')
            if kind==1:
                node=view.node(signer,f['epoch']);require(node.roles==f['roles'],'POLICY_DENIED')
            else:
                require(0<f['expires']-n<=300,'EXPIRED')
                for label in ('initiator','responder'):
                    node=view.node(f[label],f[label+'_epoch']);require(node.roles==f[label+'_roles'],'POLICY_DENIED')
                view.neighbors(f['initiator'],f['responder'])
            label={1:'hello',2:'challenge',3:'confirm'}[kind]
            verify(view.key(signer),f['signature'],signing_inputs(frame)[label])
            if kind==3:self._core.sent_confirm(frame,m,n,clock_trusted=True)
            else:
                self.journal.checkpoint(view.latest.checkpoint,view.attestation.latest_extends_saved)
                (self._core.sent_hello if kind==1 else self._core.sent_challenge)(frame,m)
        return self._invoke(frame.fields['checkpoint'],commit,now=now,monotonic=monotonic,clock_trusted=clock_trusted)

    def sent_hello(self,frame,**clock):return self._sent(frame,1,**clock)
    def sent_challenge(self,frame,**clock):return self._sent(frame,2,**clock)
    def sent_confirm(self,frame,**clock):return self._sent(frame,3,**clock)

    def routes(self,checkpoint,*,now,monotonic,clock_trusted):
        """Only cached routes for this explicit C; recheck L before returning."""
        return self._invoke(checkpoint,lambda b,n,m:self._core.routes(now=n,monotonic=m,clock_trusted=True),
                            now=now,monotonic=monotonic,clock_trusted=clock_trusted)

    def prepare_data(self,*,plaintext,path,edges,connection,session,sequence,message,packet_id,key,expires,
                     now,monotonic,clock_trusted):
        """Authorize and remember the original before returning locally built DATA.

        This does not send, retry, choose a new ID, or execute the payload.
        Sequence numbers and IDs are explicitly supplied by the host.
        """
        path,edges=tuple(path),tuple(edges)
        require(type(plaintext) is bytes and 2<=len(path)<=8 and len(edges)==len(path)-1,'ROUTE_INVALID')
        require(path[0]==self._core.local_nft and all(n in self.selection.nfts for n in path),'POLICY_DENIED')
        require(all(e in self.selection.edges for e,_ in edges) and connection in self.selection.connections,'POLICY_DENIED')
        def make(bundle,n,m):
            view=bundle.view
            self._core._clock(n,True,n,expires)
            source=view.node(path[0],role=1);destination=view.node(path[-1],role=1)
            require(key.public_key().public_bytes_raw()==source.signing_key,'AUTH_FAILED')
            policy=view.packet.connections[connection]
            view.authorize_path(path,edges,connection=(connection,policy.version),traffic=0,size=len(plaintext)+16,max_hops=len(path)-1)
            active=self._core._sessions.get(session)
            require(active is not None and {active.initiator,active.responder}=={path[0],path[1]}
                    and m<=active.monotonic_deadline and n<=active.expires,'AUTH_FAILED')
            for nft in (path[0],path[1]):view.node(nft,active.epoch(nft))
            view.neighbors(path[0],path[1])
            from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
            frame=build.packet(self.profile,5,view.packet.checkpoint,source,destination,policy,message,packet_id,plaintext,
                path,edges,session,sequence,0,key,key,X25519PublicKey.from_public_bytes(destination.encryption_key),
                issued=n,expires=expires)
            self.journal.checkpoint(view.latest.checkpoint,view.attestation.latest_extends_saved)
            self.journal.remember_request(path[0],path[-1],message,digest(plaintext),plaintext)
            return frame
        return self._invoke(None,make,now=now,monotonic=monotonic,clock_trusted=clock_trusted)
