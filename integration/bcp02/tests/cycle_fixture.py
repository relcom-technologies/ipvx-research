"""Public-key EVM fixture + synthetic authenticated EL/CL envelopes, no sockets."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from adapters.bcp02.tests.fixtures import Chain as BaseChain
from adapters.bcp02.binding import Selection
from adapters.bcp02.codec import hx
from adapters.bcp02.reader import Adapter
from adapters.bcp02.store import Store
from bcp import build
from bcp.wire import ethernet,uint
from integration.bcp02.journal import BoundJournal
from integration.bcp02.runtime import AdapterCore

DATA=json.loads(Path(__file__).with_name('contract-reads.json').read_text())
def h(text):return sha256(text.encode()).digest()
def signing(n):return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(DATA['keys'][str(n)]['signing']['public_test_seed_hex']))
def encryption(n):return X25519PrivateKey.from_private_bytes(bytes.fromhex(DATA['keys'][str(n)]['encryption']['public_test_seed_hex']))
def mac(n):return bytes.fromhex('0200000000')+bytes([n])


class Chain(BaseChain):
    def __init__(self):
        super().__init__();self.later_state='rotated'
        self.binding=replace(self.binding,addresses=tuple(bytes.fromhex(a[2:]) for a in DATA['addresses']),
                             runtime_hashes=tuple(bytes.fromhex(a[2:]) for a in DATA['runtime_hashes']))
        self.edges={k:bytes.fromhex(v[2:]) for k,v in DATA['edges'].items()}
        self.connections={k:bytes.fromhex(v[2:]) for k,v in DATA['connections'].items()}
        self.selection=Selection((1,2,3),tuple(self.edges.values()),tuple(self.connections.values()))

    def exchange(self,transport,method,path,body,timeout):
        if method!='POST':return super().exchange(transport,method,path,body,timeout)
        requests=json.loads(body)
        if not all(r['method'] in ('eth_call','eth_getCode') for r in requests):
            return super().exchange(transport,method,path,body,timeout)
        result=[]
        for request in requests:
            name,p=request['method'],request['params'];self.log.append((name,deepcopy(p)))
            selector=p[-1]
            assert set(selector)=={'blockHash','requireCanonical'} and selector['requireCanonical'] is True
            index=[hx(c.block_hash) for c in self.points].index(selector['blockHash'])
            if name=='eth_getCode':value=DATA['codes'][p[0]]
            else:value=DATA['states'][self.later_state if index==2 else 'active'][p[0]['to']+':'+p[0]['data']]
            if self.hook:value=self.hook(name,p,value)
            result.append({'jsonrpc':'2.0','id':request['id'],'result':value})
        return list(reversed(result))


class Harness:
    def __init__(self,directory):
        self.directory=Path(directory);self.chain=Chain();self.now=self.chain.points[2].timestamp+100
        self.mono=100.0;self.handshakes=0;self.sessions={};self.sequences={};self.nodes={};self.journals={};self.stores={};self.trace=[]
        for n in (1,2,3):self.open_node(n)

    def open_node(self,n):
        journal=BoundJournal(self.directory/f'core-{n}.sqlite',self.chain.binding.profile,n)
        store=Store(self.directory/f'adapter-{n}.sqlite',self.chain.binding.fingerprint)
        self.journals[n],self.stores[n]=journal,store
        self.nodes[n]=AdapterCore(Adapter(self.chain.binding,store),journal,self.chain.selection,n,mac(n),decryption_key=encryption(n))

    def restart(self,n):
        self.journals[n].close();self.stores[n].close();self.open_node(n)

    def close(self):
        for obj in (*self.journals.values(),*self.stores.values()):obj.close()

    def clock(self):
        self.mono+=0.1
        return dict(now=self.now,monotonic=self.mono,clock_trusted=True)

    def state(self,n,**kwargs):return self.nodes[n].state(**self.clock(),**kwargs).view

    def sequence(self,session,sender):
        key=(session,sender);self.sequences[key]=self.sequences.get(key,0)+1
        return self.sequences[key]

    def receive(self,n,sender,frame,stage):
        decision=self.nodes[n].receive(ethernet(mac(n),mac(sender),frame.encode()),**self.clock())
        self.trace.append({'stage':stage,'kind':frame.kind,'receiver':n,'action':decision.action,
                           'disposition':decision.disposition,'bcp_bytes':len(frame.encode())})
        return decision

    def handshake(self,a,b):
        view=self.state(a);cp=view.packet.checkpoint;nodes=view.packet.nodes;self.handshakes+=1
        prefix=f'handshake-{a}-{b}-{self.handshakes}'
        hello=build.hello(self.chain.binding.profile,a,nodes[a].epoch,h(prefix+'a'),cp,nodes[a].roles,mac(a),signing(a))
        self.nodes[a].sent_hello(hello,**self.clock())
        decision=self.nodes[b].receive(ethernet(bytes([255])*6,mac(a),hello.encode()),**self.clock())
        self.trace.append({'stage':'HELLO','kind':1,'receiver':b,'action':decision.action,'disposition':None,'bcp_bytes':len(hello.encode())})
        transcript=(uint(a,32)+uint(b,32)+uint(nodes[a].epoch,8)+uint(nodes[b].epoch,8)+h(prefix+'a')+h(prefix+'b')
                    +mac(a)+mac(b)+cp.encode()+uint(nodes[a].roles,1)+uint(nodes[b].roles,1)+bytes(2)+uint(self.now+200,8))
        challenge=build.handshake(self.chain.binding.profile,2,transcript,signing(b))
        self.nodes[b].sent_challenge(challenge,**self.clock());self.receive(a,b,challenge,'CHALLENGE')
        confirm=build.handshake(self.chain.binding.profile,3,transcript,signing(a))
        self.nodes[a].sent_confirm(confirm,**self.clock());self.receive(b,a,confirm,'CONFIRM')
        self.sessions[frozenset((a,b))]=confirm.fields['session']
        return confirm.fields['session']

    def session(self,a,b):return self.sessions[frozenset((a,b))]

    def connect(self):
        self.handshake(1,3);self.handshake(3,2)

    def advertise(self):
        view=self.state(2);cp=view.packet.checkpoint;profile=self.chain.binding.profile
        origin=build.route(profile,self.session(2,3),self.sequence(self.session(2,3),2),cp,h('route'),self.now,self.now+30,
                           ((2,1),),(),[signing(2)],signing(2))
        self.receive(3,2,origin,'ROUTE-ORIGIN')
        suffix=build.route(profile,self.session(1,3),self.sequence(self.session(1,3),3),cp,h('route'),self.now,self.now+30,
                           ((3,1),(2,1)),((self.chain.edges['rb'],1),),[signing(3),signing(2)],signing(3))
        self.receive(1,3,suffix,'ROUTE-SUFFIX')
        routes=self.nodes[1].routes(cp,**self.clock())
        assert len(routes)==1 and routes[0].fields['path']==(3,2)
        return routes[0]

    def data(self,*,plaintext=b'offline request',message=None,expires=None):
        session=self.session(1,3)
        return self.nodes[1].prepare_data(plaintext=plaintext,path=(1,3,2),edges=tuple((self.chain.edges[k],1) for k in ('ar','rb')),
            connection=self.chain.connections['ab'],session=session,sequence=self.sequence(session,1),message=message or h('message'),
            packet_id=h('data'),key=signing(1),expires=self.now+60 if expires is None else expires,**self.clock())

    def deliver(self,frame,stage='DATA'):
        decision=self.receive(3,1,frame,stage+'-relay');assert decision.action=='FORWARD' and decision.plaintext is None
        session=self.session(3,2)
        second=build.rewrap(decision.frame,session,self.sequence(session,3),1,signing(3))
        assert frame.fields['immutable']==second.fields['immutable'] and frame.fields['source_signature']==second.fields['source_signature']
        return self.receive(2,3,second,stage+'-destination')

    def response(self,data,kind,*,phase=1,result=b'',code=18,message=None):
        view=self.state(2);f=data.fields;msg=message or f['message']
        plain=(build.receipt_plaintext(1,msg,f['request_hash'],phase,result) if kind==6
               else build.error_plaintext(1,msg,f['request_hash'],code))
        session=self.session(2,3)
        return build.packet(self.chain.binding.profile,kind,view.packet.checkpoint,view.packet.nodes[2],view.packet.nodes[1],
            view.packet.connections[self.chain.connections['ba']],msg,h(f'response-{phase}-{kind}'),plain,(2,3,1),
            tuple((self.chain.edges[k],1) for k in ('br','ra')),session,self.sequence(session,2),0,signing(2),signing(2),
            encryption(1).public_key(),issued=self.now,expires=self.now+60,request_hash=f['request_hash'])

    def return_response(self,frame,stage):
        first=self.receive(3,2,frame,stage+'-relay');assert first.action=='FORWARD' and first.plaintext is None
        session=self.session(3,1);second=build.rewrap(frame,session,self.sequence(session,3),1,signing(3))
        assert second.fields['immutable']==frame.fields['immutable']
        return self.receive(1,3,second,stage+'-destination')
