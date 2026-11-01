"""Create only declared namespaces/veth; cleanup requires recorded ownership/inodes."""
import json
import os
from pathlib import Path
import subprocess
from .common import NODES, MACS, need

NS={n:'bcp02-net001-'+n.lower() for n in NODES}


class Stand:
    def __init__(self, execute, inode):
        self.execute,self.inode=execute,inode;self.created={};self.inventory=None

    def ip(self,*args):
        return self.execute(['ip',*args])

    def create(self):
        existing={n['name'] for n in json.loads(self.ip('-j','netns','list'))}
        need(not existing.intersection(NS.values()), 'namespace name collision; nothing deleted')
        for name in NS.values():
            self.ip('netns','add',name)
            self.created[name]=self.inode(name)
            for setting in ('net.ipv6.conf.all.disable_ipv6=1','net.ipv6.conf.default.disable_ipv6=1',
                            'net.ipv4.ip_forward=0','net.ipv6.conf.all.forwarding=0'):
                self.ip('netns','exec',name,'sysctl','-q','-w',setting)
        for a,pa,b,pb in (('A','a0','R','r0'),('R','r1','B','b0')):
            self.ip('link','add',pa,'netns',NS[a],'type','veth','peer','name',pb,'netns',NS[b])
        for node,(_,ports) in NODES.items():
            self.ip('-n',NS[node],'link','set','lo','down')
            self.ip('-n',NS[node],'addr','flush','dev','lo')
            for port in ports:
                self.ip('-n',NS[node],'link','set','dev',port,'address',MACS[port],'mtu','1500')
                self.ip('-n',NS[node],'addr','flush','dev',port)
        return self.audit(up=False)

    def audit(self, *, up):
        inventory={}
        for node,(_,ports) in NODES.items():
            name=NS[node]
            need(name in self.created and self.inode(name)==self.created[name], 'namespace ownership changed')
            links=json.loads(self.ip('-n',name,'-d','-j','link','show'))
            addresses=json.loads(self.ip('-n',name,'-j','addr','show'))
            routes=[]
            for version in ('-4','-6'):
                routes+=json.loads(self.ip('-n',name,version,'-j','route','show','table','all'))
            need({p['ifname'].split('@')[0] for p in links}=={'lo',*ports},'unexpected interface')
            need(not routes and not any(p.get('addr_info') for p in addresses),'IP address or route present')
            for p in links:
                port=p['ifname'].split('@')[0]
                need(('UP' in p['flags'])==(up and port!='lo'),'unexpected link state')
                if port=='lo':continue
                need(p['linkinfo']['info_kind']=='veth' and p['address']==MACS[port] and p['mtu']==1500
                     and 'master' not in p and p.get('link_index',0)>0,'unexpected Ethernet interface')
            inventory[node]=dict(namespace=name,inode=self.created[name],links=links,addresses=addresses,routes=routes)
        ports={p['ifname'].split('@')[0]:p for n in inventory.values() for p in n['links'] if p['ifname']!='lo'}
        for a,b in (('a0','r0'),('r1','b0')):
            need(ports[a]['link_index']==ports[b]['ifindex'] and ports[b]['link_index']==ports[a]['ifindex'], 'veth peer mismatch')
        self.inventory=inventory
        return inventory

    def up(self, capture_ready):
        need(capture_ready=={'L1','L2'},'full unfiltered captures must be ready before link-up')
        for node,(_,ports) in NODES.items():
            for port in ports:self.ip('-n',NS[node],'link','set','dev',port,'up')
        return self.audit(up=True)

    def cleanup(self, *, archived):
        need(archived,'evidence must be archived before deleting owned objects')
        # Audit all peers before deleting any namespace (deleting one endpoint
        # also removes its veth peer). Never delete an unexpected new interface.
        for name,saved_inode in self.created.items():
            need(self.inode(name)==saved_inode,'refuse cleanup after namespace replacement')
            current=json.loads(self.ip('-n',name,'-d','-j','link','show'))
            expected=next(n for n in NODES if NS[n]==name)
            need(all(p['ifname'].split('@')[0] in {'lo',*NODES[expected][1]} for p in current),'foreign interface in owned namespace')
            if self.inventory:
                pins={p['ifname'].split('@')[0]:p['ifindex'] for p in self.inventory[expected]['links']}
                need(all(pins.get(p['ifname'].split('@')[0])==p['ifindex'] for p in current),'interface identity changed')
        for name,inode in tuple(self.created.items()):
            need(self.inode(name)==inode,'refuse cleanup after namespace replacement')
            pids=self.ip('netns','pids',name).strip()
            need(not pids,'namespace processes still running')
            self.ip('netns','delete',name)
            del self.created[name]


def execute(command):
    return subprocess.check_output(command,text=True,timeout=10,stdin=subprocess.DEVNULL,stderr=subprocess.PIPE)


def inode(name):
    return Path('/run/netns',name).stat().st_ino
