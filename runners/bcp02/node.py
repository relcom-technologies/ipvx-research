"""One sequential actor per node, receiving payloads only through Ethernet ports."""
import os
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from adapters.bcp02.store import Store
from bcp import build
from bcp.wire import Reject, decode_ethernet, digest, ethernet, uint, require
from integration.bcp02.journal import BoundJournal
from .common import NODES, MACS, NEIGHBORS, control, need, sha
from .fixture import FixtureChain
from .routes import advertise
from .runtime import Runtime
from .worker import Worker, Scheduler


def payload(run,case,index,size):
    seed=digest(f'{run}/{case}/{index}/synthetic-request'.encode())
    return (seed*((size+31)//32))[:size]


class Node:
    def __init__(self,name,run,case,dataset,key,ports,events,clock,*,directory='.',variant='',defer_handshake=False):
        self.name,self.run,self.case,self.variant=name,run,case,variant
        self.nft=NODES[name][0];self.ports=ports;self.events=events;events.case=case;self.clock=clock
        need(key['nft']==self.nft and set(ports)==set(NODES[name][1]),'node key/port binding mismatch')
        self.key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key['signing']))
        self.decrypt=X25519PrivateKey.from_private_bytes(bytes.fromhex(key['encryption']))
        self.chain=FixtureChain(dataset)
        self.journal=BoundJournal(str(directory)+'/core.sqlite',self.chain.binding.profile,self.nft)
        self.store=Store(str(directory)+'/adapter.sqlite',self.chain.binding.fingerprint)
        adapter=self.chain.adapter(self.store)
        self.cores={port:Runtime(adapter,self.journal,self.chain.selection,self.nft,bytes.fromhex(MACS[port].replace(':','')),
                               decryption_key=None if name=='R' else self.decrypt) for port in ports}
        self.worker=Worker(self.journal.db)
        self.scheduler=Scheduler(clock=lambda:self.clock()['monotonic'],attempts=1 if case=='N02' else 3)
        self.sequence={};self.session_ports={};self.started=False;self.stopped=False;self.defer=defer_handshake
        self.last_control=-10;self.suffixes={};self.queue=[];self.last_data=None;self.saved=None
        self.issued=0;self.finished=0;self.duplicates_sent=False;self.worker_paused=False

    def seq(self,session):
        self.sequence[session]=self.sequence.get(session,0)+1
        return self.sequence[session]

    def state(self,port):
        return self.cores[port].state(**self.clock()).view

    def session(self,port):
        now=self.clock();peer=NEIGHBORS[port][0]
        live=[s for s in self.cores[port]._core._sessions.values() if peer in (s.initiator,s.responder)
              and s.expires>=now['now'] and s.monotonic_deadline>=now['monotonic']]
        require(len(live)==1,'AUTH_FAILED')
        s=live[0];self.session_ports[s.identity]=self.ports[port].ifindex
        return s.identity

    def tx(self,port,frame,*,raw=None,injection=None):
        target=b'\xff'*6 if frame.kind==1 else bytes.fromhex(MACS[NEIGHBORS[port][1]].replace(':',''))
        raw=ethernet(target,bytes.fromhex(MACS[port].replace(':','')),frame.encode()) if raw is None else raw
        self.ports[port].send(raw)
        self.events.emit('TX',frame,tx=self.ports[port].ifindex,frame_sha256=sha(raw),
                         ethernet_bytes=len(raw),injection=injection,variant=self.variant)

    def hello(self,port):
        view=self.state(port);me=view.node(self.nft);now=self.clock()
        frame=build.hello(self.chain.binding.profile,self.nft,me.epoch,os.urandom(32),view.packet.checkpoint,
                          me.roles,bytes.fromhex(MACS[port].replace(':','')),self.key)
        self.cores[port].sent_hello(frame,**now);self.tx(port,frame)

    def origin(self,port):
        view=self.state(port);now=self.clock();sid=self.session(port)
        frame=advertise(self.chain.binding.profile,view.packet.checkpoint,view.node(self.nft),self.key,sid,
                        self.seq(sid),os.urandom(32),now['now'],now['now']+30)
        self.tx(port,frame)

    def relay_suffix(self,ingress,frame):
        egress=next(p for p in self.ports if p!=ingress)
        self.suffixes[ingress]=frame
        sid=self.session(egress);view=self.state(egress);f=frame.fields
        edges=[e for e in view.packet.edges.values() if (e.source,e.destination)==(self.nft,f['path'][0]) and e.status==1]
        require(len(edges)==1,'POLICY_DENIED');edge=edges[0]
        self.tx(egress,advertise(self.chain.binding.profile,f['checkpoint'],view.node(self.nft),self.key,sid,
            self.seq(sid),f['nonce'],f['issued'],f['expires'],suffix=frame,edge=(edge.rule,edge.version),view=view))

    def route(self,port,destination):
        view=self.state(port)
        routes=self.cores[port].routes(view.packet.checkpoint,**self.clock())
        routes=[r for r in routes if r.fields['path'][-1]==destination]
        require(bool(routes),'NO_AUTHORIZED_ROUTE')
        f=routes[0].fields;peer=f['path'][0]
        edges=[e for e in view.packet.edges.values() if (e.source,e.destination)==(self.nft,peer) and e.status==1]
        require(len(edges)==1,'POLICY_DENIED')
        return (self.nft,)+f['path'],((edges[0].rule,edges[0].version),)+f['edges']

    def prepare(self,index=0):
        port='a0';size=568 if self.case=='P02' else 569 if self.case=='N01' else 128
        plain=payload(self.run,self.case,index,size);message=digest(f'{self.run}/{self.case}/{self.variant}/{index}'.encode())
        # Oversize must not create an outbox row. Other requests are staged even
        # when a stopped relay makes a current route unavailable.
        if self.case!='N01':self.cores[port].stage(message,plain,2,**self.clock())
        self.events.emit('ISSUED',message_id_override=message.hex(),payload_sha256=sha(plain),ordinal=index,
                         payload_bytes=len(plain),variant=self.variant)
        path,edges=self.route(port,2);sid=self.session(port)
        frame=self.cores[port].prepare_data(plaintext=plain,path=path,edges=edges,connection=self.chain.connections['ab'],
            session=sid,sequence=self.seq(sid),message=message,packet_id=digest(message+b'data'),key=self.key,
            expires=self.clock()['now']+60,**self.clock())
        self.last_data=frame
        return frame,plain

    def response(self,data,kind=6,phase=2,result=b'',message=None):
        f=data.fields;port='b0';path,edges=self.route(port,1);sid=self.session(port)
        msg=f['message'] if message is None else message
        plain=(build.receipt_plaintext(1,msg,f['request_hash'],phase,result) if kind==6
               else build.error_plaintext(1,msg,f['request_hash'],18))
        return self.cores[port].send_packet(kind,plain,msg,os.urandom(32),f['request_hash'],path,edges,
            self.chain.connections['ba'],sid,self.seq(sid),self.key,**self.clock())

    def handle(self,port,raw):
        frame=None
        try:
            _,_,frame=decode_ethernet(raw,self.chain.binding.profile)
            if frame.kind>=4:
                known=self.session_ports.get(frame.fields['session'])
                require(known is None or known==self.ports[port].ifindex,'AUTH_FAILED')
            decision=self.cores[port].receive(raw,**self.clock());f=frame.fields
            self.events.emit(decision.action,frame,rx=self.ports[port].ifindex,frame_sha256=sha(raw),
                disposition=decision.disposition,latest=self.journal.saved_checkpoint(),variant=self.variant)
            if decision.action=='PENDING_CHALLENGE':
                view=self.state(port);me=view.node(self.nft);now=self.clock()
                transcript=(uint(f['node'],32)+uint(self.nft,32)+uint(f['epoch'],8)+uint(me.epoch,8)
                    +f['nonce']+os.urandom(32)+f['mac']+bytes.fromhex(MACS[port].replace(':',''))+f['checkpoint'].encode()
                    +uint(f['roles'],1)+uint(me.roles,1)+bytes(2)+uint(now['now']+200,8))
                reply=build.handshake(self.chain.binding.profile,2,transcript,self.key)
                self.cores[port].sent_challenge(reply,**self.clock());self.tx(port,reply)
            elif decision.action=='CONFIRM_SESSION':
                reply=build.handshake(self.chain.binding.profile,3,frame.body[:248],self.key)
                self.cores[port].sent_confirm(reply,**self.clock());self.tx(port,reply)
                self.session(port);self.origin(port)
            elif decision.action=='ADMIT_SESSION':
                self.session(port)
                if self.name=='R':
                    for ingress,suffix in list(self.suffixes.items()):
                        if ingress!=port:self.relay_suffix(ingress,suffix)
            elif decision.action=='CACHE_ROUTE' and self.name=='R':self.relay_suffix(port,frame)
            elif decision.action=='FORWARD':
                require(decision.plaintext is None,'INVALID_PAYLOAD')
                peer=f['path'][f['hop_index']+2]
                egress=next(p for p in self.ports if NEIGHBORS[p][0]==peer)
                sid=self.session(egress)
                self.tx(egress,self.cores[egress].forward(frame,sid,self.seq(sid),self.key,**self.clock()))
            elif decision.action=='DELIVER' and frame.kind==5:
                self.delivered(frame,decision.plaintext,decision.disposition)
            elif decision.action=='DELIVER' and self.name=='A':self.received_receipt(frame,decision.plaintext)
        except Reject as e:
            self.events.emit('REJECT',frame,rx=self.ports[port].ifindex,reject=e.code,frame_sha256=sha(raw),
                             latest=self.journal.saved_checkpoint(),variant=self.variant)

    def delivered(self,frame,plaintext,disposition):
        require(self.name=='B','POLICY_DENIED')
        if self.case=='N11':
            self.worker_paused=True
            self.events.emit('WORKER_GAP_UNKNOWN',frame,variant=self.variant)
            return
        if self.case=='N07' and self.variant=='reverse':
            self.saved=self.response(frame,phase=1)
            self.events.emit('REVERSE_PREPARED',frame,variant=self.variant)
            return
        result=self.worker.accept(frame,plaintext,disposition)
        if result is None:
            self.events.emit('WORKER_UNKNOWN',frame);return
        self.events.emit('WORKER_DONE' if disposition=='NEW' else 'WORKER_CACHED',frame,
                         result_sha256=sha(result),variant=self.variant)
        self.tx('b0',self.response(frame,phase=1))
        self.tx('b0',self.response(frame,phase=2,result=result))
        if self.case in ('P01','N10'):
            self.tx('b0',self.response(frame,phase=1))
            self.tx('b0',self.response(frame,kind=7))
        if self.case=='N10':
            self.tx('b0',self.response(frame,phase=2,result=result,message=digest(frame.fields['message']+b'unknown')))
            self.tx('b0',self.response(frame,phase=2,result=b'explicit conflicting result'))

    def received_receipt(self,frame,plaintext):
        f=frame.fields
        row=self.journal.db.execute('SELECT phase,result FROM receipts WHERE source=? AND message=?',(uint(1,32),f['message'])).fetchone()
        if not row or row[0]!=2:return
        plain=self.journal.db.execute('SELECT plaintext FROM requests WHERE source=? AND message=?',(uint(1,32),f['message'])).fetchone()[0]
        require(row[1]==digest(digest(plain)),'INVALID_PAYLOAD')
        if frame.kind==7 or plaintext[96]!=2:
            self.events.emit('RECEIPT_RETAINED',frame,result_matches=True,variant=self.variant);return
        self.events.emit('COMPLETED',frame,result_matches=True,variant=self.variant)
        if self.scheduler.pending and self.scheduler.pending['message']==f['message']:
            self.scheduler.finish(f['message']);self.finished+=1
        if self.case=='N05' and not self.duplicates_sent:
            self.duplicates_sent=True;self.retry_last()
        if self.case=='N10':
            try:self.cores['a0'].stage(f['message'],plain+b'conflict',2,**self.clock())
            except Reject as e:self.events.emit('REJECT',frame,reject=e.code,variant=self.variant)

    def retry_last(self):
        require(self.last_data is not None,'UNKNOWN')
        sid=self.session('a0')
        self.tx('a0',self.cores['a0'].retry(self.last_data,sid,self.seq(sid),self.key,**self.clock()))

    def command(self,line):
        case,stage=control(line);need(case==self.case,'wrong case control')
        if stage=='START':self.started=True
        elif stage=='STOP':self.stopped=True
        elif stage=='HANDSHAKE':self.defer=False;self.hello('b0' if self.name=='B' else 'a0') if self.name!='R' else None
        elif stage=='PREPARE' and self.name=='A':self.saved,self.saved_plain=self.prepare()
        elif stage in ('ROTATE','DENY_FORWARD','DENY_REVERSE','UNAVAILABLE','STALE'):
            self.chain.mode={'ROTATE':'rotated','DENY_FORWARD':'edge_denied','DENY_REVERSE':'reverse_denied',
                             'UNAVAILABLE':'unavailable','STALE':'stale'}[stage]
            try:
                view=self.state(next(iter(self.ports)))
                self.events.emit('STATE_OBSERVED',latest=view.latest.checkpoint,variant=self.variant)
            except Reject as e:self.events.emit('REJECT',reject=e.code,variant=self.variant)
        elif stage=='RETRY' and self.name=='A':self.retry_last()
        elif stage=='PROBE':
            if self.name=='A':
                if self.case in ('N06','N07') and self.saved is not None and self.variant!='reverse':
                    self.tx('a0',self.saved,injection='older-C-after-L')
                elif self.case not in ('N08',) and not self.queue and self.issued==0:
                    self.queue=list(range(10 if self.case in ('P01','N02') else 1))
            elif self.name=='B' and self.case=='N07' and self.variant=='reverse' and self.chain.mode=='reverse_denied':
                need(self.saved is not None,'reverse response missing');self.tx('b0',self.saved,injection='older-C-reverse')
        self.events.emit('BARRIER_ACK',stage=stage,variant=self.variant)

    def tick(self):
        if not self.started:return
        now=self.clock()['monotonic']
        if now-self.last_control>=2 and self.chain.mode=='active':
            self.last_control=now
            if self.name!='R' and not self.defer:
                port=next(iter(self.ports))
                try:self.session(port);self.origin(port)
                except Reject:self.hello(port)
        if self.name!='A':return
        if self.queue and self.scheduler.pending is None:
            index=self.queue.pop(0);self.issued+=1
            try:
                frame,plain=self.prepare(index)
                self.scheduler.begin(frame.fields['message'],frame,plain)
            except Reject as e:
                self.events.emit('REJECT',reject=e.code,variant=self.variant)
                if self.case=='N02' and e.code=='NO_AUTHORIZED_ROUTE':
                    plain=payload(self.run,self.case,index,128)
                    message=digest(f'{self.run}/{self.case}/{self.variant}/{index}'.encode())
                    self.scheduler.begin(message,None,plain)
        pending=self.scheduler.pending
        if pending:
            action=self.scheduler.due()
            if action=='UNKNOWN':
                self.events.emit('UNKNOWN',pending['frame'],message_id_override=pending['message'].hex(),
                                 attempts=pending['count'],variant=self.variant)
                self.scheduler.finish(pending['message'])
            elif action=='SEND' and pending['frame'] is not None:
                frame=pending['frame']
                try:
                    if pending['count']>1:
                        sid=self.session('a0');frame=self.cores['a0'].retry(frame,sid,self.seq(sid),self.key,**self.clock())
                    if self.case=='N03' and pending['count']==1:
                        target=bytes.fromhex(MACS['r0'].replace(':',''));raw=ethernet(target,bytes.fromhex(MACS['a0'].replace(':','')),frame.encode())
                        bad=raw[:-1]+bytes([raw[-1]^1]);self.tx('a0',frame,raw=bad,injection='hop-signature-final-byte')
                    self.tx('a0',frame)
                    if self.case=='N04' and pending['count']==1:self.tx('a0',frame,injection='identical-replay')
                except Reject as e:self.events.emit('REJECT',frame,reject=e.code,variant=self.variant)

    def close(self):
        self.journal.close();self.store.close();self.events.close()
