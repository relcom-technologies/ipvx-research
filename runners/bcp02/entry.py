"""Private child entry point. Rechecks admission before opening any packet socket."""
import os
from pathlib import Path
import selectors
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from runners.bcp02.admission import authorize
from runners.bcp02.common import Events, need, read_json, private_json, sha, control
from runners.bcp02.linux import isolate, Clock
from runners.bcp02.transport import PacketPort
from runners.bcp02.node import Node
from runners.bcp02.pcap import Writer


def main():
    need(len(sys.argv)==3,'entry requires private config and permit paths')
    authorize(sys.argv[2])
    c=read_json(sys.argv[1]);need(os.stat('/proc/self/ns/net').st_ino==c['namespace_inode'],'child in wrong namespace')
    os.umask(0o077)
    need(sha(Path(c['dataset']).read_bytes())==c['dataset_sha256'],'dataset changed')
    dataset=read_json(c['dataset']);key=None
    if c['role']=='node':key=read_json('key.json')
    ports={name:PacketPort(name,capture=c['role']=='capture') for name in c['ports']}
    # All sockets/secret material opened before dropping every capability. The
    # process then cannot create any new socket, switch namespaces or exec.
    policy=isolate(c['uid'])
    events=Events('events.jsonl',c['run_id'],c['node'],lambda e:print(__import__('json').dumps(e),flush=True))
    events.case=c.get('case','P01')
    events.emit('READY',policy=policy,namespace_inode=c['namespace_inode'],
                interfaces={p:v.ifindex for p,v in ports.items()},role=c['role'])
    clock=Clock(c['wall'],c['monotonic']);selector=selectors.DefaultSelector()
    selector.register(sys.stdin,selectors.EVENT_READ,None)
    for name,p in ports.items():selector.register(p,selectors.EVENT_READ,name)
    node=None;file=None;writer=None;started=time.monotonic();capture_error=None
    if c['role']=='node':
        node=Node(c['node'],c['run_id'],c['case'],dataset,key,ports,events,clock.read,
                  variant=c.get('variant',''),defer_handshake=c.get('defer_handshake',False))
    else:
        file=open('capture.pcap','xb');os.chmod('capture.pcap',0o600);writer=Writer(file)
    try:
        while time.monotonic()-started<(90 if node else 1200):
            for selected,_ in selector.select(0.02):
                port=selected.data
                if port is None:
                    line=sys.stdin.readline()
                    if not line:raise EOFError('controller closed')
                    case,stage=control(line)
                    if node:node.command(line)
                    elif stage=='STOP':
                        # Nodes are stopped first. Drain the capture socket to
                        # EAGAIN so unread queued frames cannot disappear at exit.
                        for capture in ports.values():
                            while True:
                                try:raw=capture.recv()
                                except BlockingIOError:break
                                writer.append(raw,time.time())
                                if raw[12:14]!=b'\x88\xb5':events.emit('FAIL_ISOLATION',frame_sha256=sha(raw))
                        return
                    else:need(False,'capture accepts only STOP control')
                else:
                    try:raw=ports[port].recv()
                    except BlockingIOError:continue
                    if raw is None:continue
                    if node:node.handle(port,raw)
                    else:
                        writer.append(raw,time.time())
                        if raw[12:14]!=b'\x88\xb5':
                            events.emit('FAIL_ISOLATION',frame_sha256=sha(raw));return
                if node and node.stopped:return
            if node:node.tick()
        events.emit('ABORTED',reason='child runtime bound reached')
    except BaseException as e:
        capture_error=type(e).__name__;events.emit('CHILD_ERROR',error_type=capture_error);raise
    finally:
        if file:
            file.flush();os.fsync(file.fileno());file.close()
            private_json('capture-statistics.json',dict(role='capture',link=c['link'],
                started_before_link_up=True,filter=None,snaplen=65535,error=capture_error,
                statistics=[p.statistics() for p in ports.values()]))
        if node:node.close()
        else:events.close()
        for p in ports.values():p.close()
        selector.close()


if __name__=='__main__':main()
