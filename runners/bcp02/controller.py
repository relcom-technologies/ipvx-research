"""Future root setup/controller on the separately admitted disposable host only."""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time

from .admission import preflight, source_hash, claim_once
from .common import NODES, need, private_json, sha, control, run_id, ROOT
from .fixture import export
from .scenarios import SCRIPTS, observed
from .stand import Stand, NS, execute, inode
from .verifier import evaluate


class Controller:
    def __init__(self,directory,permit,config,permit_path):
        self.directory=Path(directory);self.permit=permit;self.config=config;self.permit_path=str(Path(permit_path).resolve())
        self.run=run_id(permit['run_id']);self.children={};self.selector=selectors.DefaultSelector();self.events=[]
        self.start=time.monotonic();self.acked=set();self.serial=0;self.current='P01';self.label='P01'
        self.timeline=dict(capture_ready={},link_up=None,resources_within_limits=True,clock_healthy=True,
                           process_isolation_verified=False,controls=[],processes=[])
        self.stand=Stand(execute,inode)

    def bounds(self):
        need(time.monotonic()-self.start<1200 and time.time()<self.permit['not_after'],'run time/window bound')
        size=0
        for p in self.directory.rglob('*'):
            need(not p.is_symlink(),'artifact symlink')
            if p.is_file():size+=p.stat().st_size
        need(size<=1024**3,'artifact storage bound')
        need(abs((time.time()-self.health['wall'])-(time.monotonic()-self.health['monotonic']))<=5,'clock jump')

    def spawn(self,key,node,directory,*,role='node',link=None,port=None,defer=False):
        directory=Path(directory)
        uid={'A':60001,'R':60002,'B':60003}.get(node,60004)
        if not directory.exists():directory.mkdir(mode=0o700);os.chown(directory,uid,uid)
        if role=='node' and not (directory/'key.json').exists():
            shutil.copyfile(self.directory/'dataset'/node/'key.json',directory/'key.json');(directory/'key.json').chmod(0o600)
        config=dict(role=role,uid=uid,node=node if role=='node' else key,case=self.current,run_id=self.run,
            variant=self.label.split('-',1)[1] if '-' in self.label else '',defer_handshake=defer,
            ports=list(NODES[node][1]) if role=='node' else [port],link=link,
            namespace_inode=self.stand.created[NS[node]],dataset=str(self.directory/'dataset/dataset.json'),
            dataset_sha256=self.dataset_hash,wall=self.health['wall'],monotonic=self.health['monotonic'])
        self.serial+=1;path=self.directory/'configs'/f'{self.serial}.json';private_json(path,config)
        stderr=open(directory/f'stderr-{self.serial}.log','xb');os.chmod(stderr.name,0o600)
        p=subprocess.Popen(['ip','netns','exec',NS[node],sys.executable,'-I',str(Path(__file__).with_name('entry.py')),
            str(path),self.permit_path],cwd=directory,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,
            env={'PATH':os.environ['PATH'],'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
        stderr.close();os.set_blocking(p.stdout.fileno(),False)
        child=dict(process=p,key=key,node=node,role=role,link=link,directory=directory,buffer=b'',ready=False,uid=uid)
        self.children[key]=child;self.selector.register(p.stdout,selectors.EVENT_READ,child)
        return child

    def audit_process(self,child):
        pid=child['process'].pid
        status={s.split(':',1)[0]:s.split(':',1)[1].strip() for s in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in s}
        need(all(int(status[k],16)==0 for k in ('CapEff','CapPrm','CapBnd','CapAmb'))
             and status['NoNewPrivs']=='1' and status['Seccomp']=='2'
             and set(map(int,status['Uid'].split()))=={child['uid']},'root process-policy audit failed')
        need(Path(f'/proc/{pid}/ns/net').stat().st_ino==self.stand.created[NS[child['node']]],'process namespace mismatch')
        for name in ('tcp','tcp6','udp','udp6','raw','raw6'):
            p=Path(f'/proc/{pid}/net/{name}')
            need(not p.exists() or len(p.read_text().splitlines())<=1,'INET socket present')
        packets=Path(f'/proc/{pid}/net/packet').read_text().splitlines()[1:]
        allowed={str(p['ifindex']) for p in self.stand.inventory[child['node']]['links'] if p['ifname']!='lo'}
        entries={line.split()[-1]:line.split() for line in packets}
        sockets=[]
        for fd in Path(f'/proc/{pid}/fd').iterdir():
            try:target=os.readlink(fd)
            except FileNotFoundError:continue
            if target.startswith('socket:['):
                sock=target[8:-1];need(sock in entries,'non-packet socket fd')
                fields=entries[sock];need(fields[2]=='3' and fields[4] in allowed,'unbound/wrong packet socket')
                need(fields[3] in ('88b5','0003'),'unexpected packet protocol');sockets.append(sock)
        expected=len(NODES[child['node']][1]) if child['role']=='node' else 1
        need(len(sockets)==expected,'packet socket count mismatch')
        return dict(pid=pid,node=child['key'],uid=child['uid'],namespace_inode=self.stand.created[NS[child['node']]],
                    status={k:status[k] for k in ('CapEff','CapPrm','CapBnd','CapAmb','NoNewPrivs','Seccomp')},packet_sockets=sockets)

    def poll(self,timeout=0.03):
        self.bounds()
        for selected,_ in self.selector.select(timeout):
            c=selected.data
            data=os.read(selected.fileobj.fileno(),65536)
            if not data:
                self.selector.unregister(selected.fileobj);continue
            c['buffer']+=data;need(len(c['buffer'])<1024**2,'child output overflow')
            while b'\n' in c['buffer']:
                line,c['buffer']=c['buffer'].split(b'\n',1);need(len(line)<4096,'oversized child event')
                e=json.loads(line);need(e['node']==c['key'] and e['run_id']==self.run,'child event identity mismatch')
                if e['decision'] in ('FAIL_ISOLATION','CHILD_ERROR','ABORTED'):need(False,e['decision'])
                if e['decision']=='READY':
                    c['ready']=True;self.timeline['processes'].append(self.audit_process(c))
                    if c['role']=='capture':self.timeline['capture_ready'][c['link']]=time.monotonic()
                if e['decision']=='BARRIER_ACK':self.acked.add((c['key'],e['stage']))
                if c['role']=='node':self.events.append(e)
        need(len(self.events)<100000,'event budget exceeded')

    def wait(self,predicate,seconds=10):
        deadline=time.monotonic()+seconds
        while not predicate():
            need(time.monotonic()<deadline,'case/barrier deadline exceeded')
            for c in self.children.values():
                if c['process'].poll() is not None and not c.get('stopping'):need(False,'child exited unexpectedly')
            self.poll()

    def send(self,node,stage):
        c=self.children[node];line=self.current+':'+stage;control(line)
        self.acked.discard((node,stage));c['process'].stdin.write((line+'\n').encode());c['process'].stdin.flush()
        self.timeline['controls'].append(dict(case_id=self.current,node=node,stage=stage,monotonic=time.monotonic()))
        self.wait(lambda:(node,stage) in self.acked)

    def stop(self,key):
        c=self.children[key];c['stopping']=True
        p=c['process']
        if p.poll() is None:
            p.stdin.write((self.current+':STOP\n').encode());p.stdin.flush()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5);need(False,'child required forced stop')
        for _ in range(3):self.poll(0)
        p.stdin.close();p.stdout.close()
        del self.children[key]

    def case(self,label,script):
        self.current=label.split('-')[0];self.label=label;self.events=[]
        folder=self.directory/'cases'/label;folder.mkdir(mode=0o700)
        for node in NODES:self.spawn(node,node,folder/node)
        self.wait(lambda:all(self.children[n]['ready'] for n in NODES))
        for node in NODES:self.send(node,'START')
        self.wait(lambda:observed(self.events,'ROUTES'),15)
        stopped_at=None;route_cursor=0;case_start=time.monotonic()
        try:
            for target,stage in script:
                need(time.monotonic()-case_start<90,'case bound')
                if target=='WAIT':
                    cursor=route_cursor if stage=='N09-route' else 0
                    self.wait(lambda:observed(self.events[cursor:],stage),max(1,90-(time.monotonic()-case_start)))
                elif target=='STOP':
                    self.stop(stage)
                    if stage=='R':stopped_at=time.monotonic()
                elif target=='RESTART':
                    self.spawn(stage,stage,folder/stage,defer=True)
                    self.wait(lambda:self.children[stage]['ready']);self.send(stage,'START')
                elif target=='BARRIER':
                    need(stage=='R_STOPPED' and 'R' not in self.children,'relay stop barrier missing')
                else:
                    if stage=='HANDSHAKE':route_cursor=len(self.events)
                    for node in NODES if target=='ALL' else [target]:self.send(node,stage)
            # Drain late ACCEPTED/ERROR without sleeping through the controller.
            end=time.monotonic()+0.3
            while time.monotonic()<end:self.poll()
        finally:
            for node in list(NODES):
                if node in self.children:self.stop(node)
            pins={str(p.relative_to(folder)):sha(p.read_bytes()) for p in folder.rglob('*')
                  if p.is_file() and p.name not in ('key.json','closed.json')}
            private_json(folder/'closed.json',dict(files=pins,relay_stopped_monotonic=stopped_at))

    def run_all(self):
        # Nothing below is called by tests or PR CI. Admission is checked by CLI.
        self.health=preflight(self.config)
        need(time.time()<self.permit['not_after'],'permit expired during preflight')
        claim_once(self.permit)
        self.directory.mkdir(mode=0o700,exist_ok=False)
        for name in ('configs','captures','cases'):(self.directory/name).mkdir(mode=0o700)
        result=None;error=None
        try:
            self.dataset_hash=export(self.directory/'dataset',self.run,int(time.time()))
            private_json(self.directory/'run-manifest.json',dict(run_id=self.run,state_mode='fixture-state-ethernet',
                network_execution=True,scope_sha256=source_hash(),dataset_sha256=self.dataset_hash,
                source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                host_preflight=self.health,transactions=0,models=0,paid_calls=0))
            private_json(self.directory/'inventory-down.json',self.stand.create())
            for link,node,port in [('L1','A','a0'),('L2','B','b0')]:
                self.spawn('capture-'+link,node,self.directory/'captures'/link,role='capture',link=link,port=port)
            self.wait(lambda:set(self.timeline['capture_ready'])=={'L1','L2'})
            self.timeline['link_up']=time.monotonic()
            private_json(self.directory/'inventory-up.json',self.stand.up(set(self.timeline['capture_ready'])))
            for label,script in SCRIPTS.items():self.case(label,script)
            self.timeline['process_isolation_verified']=True
        except BaseException as e:error=type(e).__name__+': '+str(e)
        finally:
            for key in list(self.children):
                try:self.stop(key)
                except BaseException as e:error=error or type(e).__name__+': '+str(e)
            private_json(self.directory/'controller.json',self.timeline)
            self.export_indexes()
            result=evaluate(self.directory)
            if error and result['outcome']!='FAIL_ISOLATION':result['outcome']='ABORTED';result['controller_error']=error
            private_json(self.directory/'transport-result.json',result)
            # Keep all private evidence for >=7 days. Teardown deletes only
            # owned namespace objects, never artifacts, fixtures or old trials.
            sums=''.join(sha(p.read_bytes())+'  '+str(p.relative_to(self.directory))+'\n'
                         for p in sorted(self.directory.rglob('*')) if p.is_file() and p.name!='key.json')
            fd=os.open(self.directory/'SHA256SUMS',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:f.write(sums);f.flush();os.fsync(f.fileno())
            try:self.stand.cleanup(archived=True)
            except BaseException as e:
                private_json(self.directory/'cleanup-error.json',dict(outcome='ABORTED',reason=str(e),objects_may_remain=True))
                result['outcome']='ABORTED';result['cleanup_error']=True
            private_json(self.directory/'result.json',result)
            final=''.join(sha(p.read_bytes())+'  '+str(p.relative_to(self.directory))+'\n'
                          for p in sorted(self.directory.rglob('*')) if p.is_file() and p.name!='key.json')
            fd=os.open(self.directory/'FINAL-SHA256SUMS',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:f.write(final);f.flush();os.fsync(f.fileno())
            self.selector.close()
        return result

    def export_indexes(self):
        """After stopping children: derive indexes, never read/relay live outboxes."""
        ev=[]
        for p in (self.directory/'cases').glob('*/*/events.jsonl'):
            for line in p.read_text().splitlines():ev.append(json.loads(line))
        private_json(self.directory/'payload-manifest.json',[e for e in ev if e['decision']=='ISSUED'])
        private_json(self.directory/'worker-log.json',[e for e in ev if e['decision'].startswith('WORKER_')])
        private_json(self.directory/'injection-manifest.json',[e for e in ev if e.get('injection')])
        private_json(self.directory/'fault-barriers.json',self.timeline['controls'])
        private_json(self.directory/'clock-health.json',self.health)
        private_json(self.directory/'process-policy.json',self.timeline['processes'])
        private_json(self.directory/'source-binary-dataset-hashes.json',dict(scope_sha256=source_hash(),
            binaries=self.config['binary_sha256'],dataset_sha256=getattr(self,'dataset_hash',None)))
        private_json(self.directory/'state-bank.json',dict(mode='fixture-state-ethernet',dataset='dataset/dataset.json',
            sha256=getattr(self,'dataset_hash',None),live_rpc=False,transactions=0))
