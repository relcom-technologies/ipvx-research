"""Permit-free rehearsal of the stand's kernel contact. Synthetic frames, never BCP evidence.

Same namespaces, veth links, packet sockets, capture before link-up, privilege drop,
seccomp policy, /proc audit and cleanup as a run, because mocks cannot show them and a
real run spends its permit first. No permit, dataset, run key, Core, chain or measurement.
"""
import json
import os
from pathlib import Path
import platform
import selectors
import socket
import sqlite3
import subprocess
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from runners.bcp02.common import MACS, NEIGHBORS, control, need, private_json, read_json
from runners.bcp02.linux import isolate
from runners.bcp02.pcap import Writer, frames
from runners.bcp02.stand import NS, Stand, actor_parent, audit_process, execute, inode, reachable
from runners.bcp02.transport import PacketPort

MARK=b'IPVX-REHEARSAL-NOT-BCP'
SIZES=(60,1514)
UIDS={'A':60001,'R':60002,'B':60003}


def mac(port):
    return bytes.fromhex(MACS[port].replace(':',''))


def wrap(port,body):
    return mac(NEIGHBORS[port][1])+mac(port)+b'\x88\xb5'+body


def emit(**event):
    print(json.dumps(event),flush=True)


def denied():
    """The child's policy, exercised rather than only read back from /proc."""
    try:socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    except PermissionError:pass
    else:need(False,'socket creation was not denied')
    try:pid=os.fork()
    except PermissionError:return
    if pid==0:os._exit(1)
    need(False,'process creation was not denied')


def libraries():
    """What a node's journal and signatures need right after the drop, on throwaway keys."""
    key=Ed25519PrivateKey.generate();key.public_key().verify(key.sign(MARK),MARK)
    X25519PrivateKey.generate().exchange(X25519PrivateKey.generate().public_key())
    db=sqlite3.connect('rehearsal.sqlite');db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE t (v BLOB)');db.execute('INSERT INTO t VALUES (?)',(MARK,));db.commit()
    need(db.execute('PRAGMA integrity_check').fetchone()==('ok',),'journal integrity failure');db.close()


def child(role,uid,names):
    capture=role=='capture'
    ports={name:PacketPort(name,capture=capture) for name in names}
    policy=isolate(uid);denied()
    if not capture:libraries()
    file=writer=None;error=None
    if capture:
        file=open('capture.pcap','xb');os.chmod('capture.pcap',0o600);writer=Writer(file)
    selector=selectors.DefaultSelector();selector.register(sys.stdin,selectors.EVENT_READ,None)
    for name,port in ports.items():selector.register(port,selectors.EVENT_READ,name)
    ready=False;started=time.monotonic()
    try:
        while time.monotonic()-started<60:
            for selected,_ in selector.select(0.02):
                name=selected.data
                if name is None:
                    line=sys.stdin.readline()
                    if not line:raise EOFError('controller closed')
                    _,stage=control(line)
                    if stage=='STOP':
                        for port in ports.values() if capture else ():
                            while True:
                                try:writer.append(port.recv(),time.time())
                                except BlockingIOError:break
                        return
                    if stage=='PROBE':
                        for size in SIZES:
                            body=MARK+bytes(size-14-len(MARK));ports['a0'].send(wrap('a0',body))
                    continue
                try:raw=ports[name].recv()
                except BlockingIOError:continue
                if raw is None:continue
                if capture:
                    writer.append(raw,time.time())
                    if raw[12:14]!=b'\x88\xb5':
                        emit(decision='FAIL_ISOLATION',port=name);return
                    continue
                emit(decision='RX',port=name,bytes=len(raw),ifindex=ports[name].ifindex)
                if role=='R':
                    egress=next(p for p in ports if p!=name);ports[egress].send(wrap(egress,raw[14:]))
                elif role=='B':ports[name].send(wrap(name,raw[14:]))
            # After the first pass, so an error pending on a socket shows here.
            if not ready:
                ready=True;emit(decision='READY',policy=policy,interfaces={n:p.ifindex for n,p in ports.items()})
        emit(decision='ABORTED',reason='child runtime bound reached')
    except BaseException as e:
        error=type(e).__name__;emit(decision='CHILD_ERROR',error_type=error);raise
    finally:
        if file:
            file.flush();os.fsync(file.fileno());file.close()
            private_json('capture-statistics.json',dict(error=error,statistics=[p.statistics() for p in ports.values()]))
        for port in ports.values():port.close()
        selector.close()


def verify_capture(folder):
    """Both directions of both sizes, nothing else, no kernel drops."""
    with open(Path(folder)/'capture.pcap','rb') as f:seen=[raw for _,raw in frames(f)]
    stats=read_json(Path(folder)/'capture-statistics.json')
    need(stats['error'] is None and len(stats['statistics'])==1,'capture ended with an error')
    s=stats['statistics'][0]
    need(s['drops']==0 and s['unfiltered'] is True and s['packets']==len(seen),'capture coverage/drops')
    need(all(raw[12:14]==b'\x88\xb5' and raw[14:14+len(MARK)]==MARK for raw in seen),'foreign frame captured')
    need(sorted(len(raw) for raw in seen)==sorted(SIZES*2),'capture frame set mismatch')
    return dict(frames=len(seen),drops=s['drops'])


def rehearse(directory,*,run=execute,ino=inode,command=None):
    need(sys.platform=='linux' and os.geteuid()==0,'root on a Linux host required')
    directory=Path(directory).resolve();reachable(directory)
    actor_parent(directory);(directory/'captures').mkdir(mode=0o700)
    actors=actor_parent(actor_parent(directory/'cases')/'rehearsal')
    command=command or [sys.executable,'-I',str(Path(__file__).resolve())]
    stand=Stand(run,ino);children={};selector=selectors.DefaultSelector();received=[];processes=[]
    report=dict(schema_version=1,kind='kernel-rehearsal',outcome='REHEARSAL_FAIL',kernel=platform.release(),
        machine=platform.machine(),permit_used=False,dataset_used=False,bcp_frames=0,transactions=0,
        network_measurement=False,ready_to_launch=False,
        interpretation='Kernel plumbing with synthetic frames. Satisfies no launch gate and is no BCP evidence.')

    def spawn(key,node,role,ports):
        uid=UIDS[node];folder=(directory/'captures' if role=='capture' else actors)/key
        folder.mkdir(mode=0o700);os.chown(folder,uid,uid)
        stderr=open(directory/(key+'.stderr'),'xb');os.chmod(stderr.name,0o600)
        p=subprocess.Popen(['ip','netns','exec',NS[node],*command,role,str(uid),*ports],cwd=folder,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr,
            env={'PATH':os.environ['PATH'],'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'})
        stderr.close();os.set_blocking(p.stdout.fileno(),False)
        c=dict(process=p,key=key,node=node,role=role if role=='capture' else 'node',uid=uid,buffer=b'',ready=False)
        children[key]=c;selector.register(p.stdout,selectors.EVENT_READ,c)

    def poll():
        for selected,_ in selector.select(0.03):
            c=selected.data;data=os.read(selected.fileobj.fileno(),65536)
            if not data:
                selector.unregister(selected.fileobj);continue
            c['buffer']+=data
            while b'\n' in c['buffer']:
                line,c['buffer']=c['buffer'].split(b'\n',1);e=json.loads(line)
                need(e['decision'] in ('READY','RX'),c['key']+': '+e['decision']+' '+str(e.get('error_type') or e.get('reason') or ''))
                if e['decision']=='READY':
                    c['ready']=True;processes.append(audit_process(stand,c))
                else:received.append((c['key'],e['port'],e['bytes']))

    def wait(predicate,seconds=15):
        deadline=time.monotonic()+seconds
        while not predicate():
            need(time.monotonic()<deadline,'rehearsal deadline exceeded')
            for c in children.values():
                if c['process'].poll() is not None:
                    poll();need(False,c['key']+' exited unexpectedly: '+(directory/(c['key']+'.stderr')).read_text()[-300:])
            poll()

    def stop(key):
        c=children.pop(key);p=c['process']
        try:
            if p.poll() is None:
                p.stdin.write(b'P01:STOP\n');p.stdin.flush();p.wait(timeout=5)
            # Read what it wrote before exiting; EOF unregisters it.
            while p.stdout in selector.get_map():poll()
        finally:
            if p.poll() is None:p.kill();p.wait(timeout=5)
            if p.stdout in selector.get_map():selector.unregister(p.stdout)
            p.stdin.close();p.stdout.close()

    try:
        private_json(directory/'inventory-down.json',stand.create())
        spawn('capture-L1','A','capture',['a0']);spawn('capture-L2','B','capture',['b0'])
        wait(lambda:all(c['ready'] for c in children.values()))
        private_json(directory/'inventory-up.json',stand.up({'L1','L2'}))
        spawn('A','A','A',['a0']);spawn('R','R','R',['r0','r1']);spawn('B','B','B',['b0'])
        wait(lambda:all(c['ready'] for c in children.values()))
        children['A']['process'].stdin.write(b'P01:PROBE\n');children['A']['process'].stdin.flush()
        wait(lambda:sum(k=='A' for k,_,_ in received)==len(SIZES))
        for key in ('A','R','B','capture-L1','capture-L2'):stop(key)
        expected=[(k,p,s) for k,p in (('R','r0'),('B','b0'),('R','r1'),('A','a0')) for s in SIZES]
        need(sorted(received)==sorted(expected),'node frame set mismatch')
        report['links']={link:verify_capture(directory/'captures'/('capture-'+link)) for link in ('L1','L2')}
        report['processes']=processes;report['outcome']='REHEARSAL_PASS'
    except BaseException as e:
        report['reason']=type(e).__name__+': '+str(e)
    finally:
        for key in list(children):
            try:stop(key)
            except BaseException as e:report.setdefault('reason',type(e).__name__+': '+str(e))
        selector.close()
        try:
            stand.cleanup(archived=True)
            left=[n['name'] for n in json.loads(run(['ip','-j','netns','list']) or '[]') if n['name'] in NS.values()]
            need(not left,'namespaces left behind')
        except BaseException as e:
            report['outcome']='REHEARSAL_FAIL';report['objects_may_remain']=True
            report['cleanup_error']=type(e).__name__+': '+str(e)
        private_json(directory/'rehearsal.json',report)
    return report


if __name__=='__main__':child(sys.argv[1],int(sys.argv[2]),sys.argv[3:])
