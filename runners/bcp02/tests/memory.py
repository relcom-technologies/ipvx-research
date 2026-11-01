"""Unit-test doubles only. No namespace, packet socket, child node or real clock."""
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from runners.bcp02.common import NODES, NEIGHBORS, Events
from runners.bcp02.node import Node
from runners.bcp02.scenarios import observed

T0=1800000000


class Memory:
    def __init__(self,dataset,case,variant=''):
        self.temp=TemporaryDirectory();self.directory=Path(self.temp.name)
        self.dataset=dataset;self.case=case;self.variant=variant;self.now=100.0
        self.nodes={};self.events=[];self.queue=deque();self.wire=[]
        self.patches=[patch('time.monotonic',lambda:self.now),patch('time.time',lambda:T0+self.now)]
        for p in self.patches:p.start()
        for name in NODES:self.open(name)

    def clock(self):return dict(now=int(T0+self.now),monotonic=self.now,clock_trusted=True)

    def open(self,name,*,defer=False):
        folder=self.directory/name;folder.mkdir(exist_ok=True)
        parent=self
        class Port:
            def __init__(self,name):self.name=name;self.ifindex={'a0':1,'r0':2,'r1':3,'b0':4}[name]
            def send(self,raw):
                parent.wire.append((self.name,raw))
                other=NEIGHBORS[self.name][1]
                node=next(n for n,(_,ports) in NODES.items() if other in ports)
                parent.queue.append((node,other,raw))
        import json
        key=json.loads((Path(self.dataset['_directory'])/name/'key.json').read_text())
        self.nodes[name]=Node(name,'offline-unit-tests',self.case,self.dataset,key,
            {p:Port(p) for p in NODES[name][1]},Events(folder/'events.jsonl','offline-unit-tests',name,self.events.append),
            self.clock,directory=folder,variant=self.variant,defer_handshake=defer)

    def command(self,name,stage):self.nodes[name].command(self.case+':'+stage)

    def tick(self):
        self.now+=0.05
        for n in list(self.nodes.values()):n.tick()
        for _ in range(500):
            if not self.queue:return
            name,port,raw=self.queue.popleft()
            if name in self.nodes:self.nodes[name].handle(port,raw)
        raise AssertionError('unbounded memory transport loop')

    def wait(self,condition,*,cursor=0):
        for _ in range(1900):
            if observed(self.events[cursor:],condition):return
            self.tick()
        raise AssertionError('unit condition missing: '+condition+'; tail='+str(self.events[-6:]))

    def start(self):
        for n in self.nodes:self.command(n,'START')
        self.wait('ROUTES')

    def stop(self,name):self.nodes.pop(name).close()

    def script(self,steps):
        cursor=0
        for target,stage in steps:
            if target=='WAIT':self.wait(stage,cursor=cursor if stage=='N09-route' else 0)
            elif target=='STOP':self.stop(stage)
            elif target=='RESTART':self.open(stage,defer=True);self.command(stage,'START')
            elif target=='BARRIER':assert stage=='R_STOPPED' and 'R' not in self.nodes
            else:
                if stage=='HANDSHAKE':cursor=len(self.events)
                for n in list(self.nodes) if target=='ALL' else [target]:self.command(n,stage)
            self.tick()

    def close(self):
        for n in self.nodes.values():n.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
