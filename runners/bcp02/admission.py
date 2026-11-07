"""Source binding and separate signed owner permit. JSON is not owner authority."""
import base64
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .common import ROOT, PLAN, read_json, sha, need

HERE=Path(__file__).resolve().parent


def source_hash():
    manifest=read_json(HERE/'manifest.json')
    for name,expected in manifest['files'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,'unsafe source path')
        p=ROOT/name
        need(p.resolve()==p and sha(p.read_bytes())==expected,'source pin mismatch: '+name)
    import json
    return sha(b'IPVX-BCP02-NET-001-F/runner3\0'+json.dumps(manifest,sort_keys=True,separators=(',',':')).encode())


PERMIT_DOMAIN = b'IPVX BCP02 isolated run permit v2\0'


def verify_permit(doc, public_key, *, scope, now):
    """Signature/integrity check; caller supplies the reviewed trusted owner key."""
    from .dataset import parse, fresh
    raw=base64.b64decode(doc['payload'],validate=True)
    need(len(raw)<=8192,'permit too large')
    signature=base64.b64decode(doc['signature'],validate=True)
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(signature,PERMIT_DOMAIN+raw)
    permit=parse(raw)
    need(set(permit)=={'version','scope_sha256','run_id','host_image_sha256','not_before','not_after',
                       'launch','transactions','production','dataset'} and type(permit['version']) is int
         and permit['version']==2, 'dataset-bound v2 permit required')
    need(permit['scope_sha256']==scope, 'permit source/scope mismatch')
    start,end=permit['not_before'],permit['not_after']
    need(type(start) is int and type(end) is int and start<=now<end and 0<end-start<=3600,
         'permit window not accepted/current')
    fresh(permit['dataset'],now)
    need(permit['dataset']['run_id']==permit['run_id'] and start>=permit['dataset']['created_at']
         and end<=permit['dataset']['expires_at'], 'permit exceeds signed dataset lifetime/run')
    need(permit['launch'] is True and type(permit['transactions']) is int and permit['transactions']==0
         and permit['production'] is False, 'permit operation mismatch')
    permit['_document_sha256']=sha(raw+signature)
    return permit


def authorize(path, *, config=None, now=None):
    c=read_json(HERE/'launch-config.json') if config is None else config
    need(c['state_mode']=='fixture-state-ethernet' and c['owner_public_key'] and c['review_evidence']
         and c['host_image_sha256'] and c['kernel_config_sha256'] and all(c['binary_sha256'].values())
         and c['allocated_host'] and c['accepted_window'] and c['owner_scope_ack']
         and c['owner_launch_decision'] and c['resources_allocated'] is True and c.get('run_dataset'),
         'BLOCKED: implementation review, host/dataset pins and separate owner launch decision are missing')
    p=Path(path);s=p.lstat()
    need(stat.S_ISREG(s.st_mode) and not p.is_symlink() and s.st_uid==0
         and stat.S_IMODE(s.st_mode)==0o600,'owner permit must be a root-owned regular 0600 file')
    parent=p.resolve().parent;ps=parent.stat()
    need(ps.st_uid==0 and not stat.S_IMODE(ps.st_mode)&0o022,'permit parent must not be writable by other users')
    permit=verify_permit(read_json(p),c['owner_public_key'],scope=source_hash(),
                         now=time.time() if now is None else now)
    need(c['accepted_window']==[permit['not_before'],permit['not_after']], 'permit window not accepted/current')
    need(permit['host_image_sha256']==c['host_image_sha256'] and permit['dataset']==c['run_dataset'],
         'permit host/dataset differs from reviewed configuration')
    return permit,c


def claim_once(permit, *, ledger=Path('/var/lib/ipvx-bcp02-used-permits')):
    """Consumed even on a failed run; copying/renaming a permit cannot reuse it."""
    from .common import private_json,run_id
    ledger=Path(ledger);ledger.mkdir(mode=0o700,exist_ok=True)
    s=ledger.lstat()
    need(stat.S_ISDIR(s.st_mode) and not ledger.is_symlink() and s.st_uid==os.geteuid()
         and stat.S_IMODE(s.st_mode)==0o700,'unsafe permit ledger')
    identifier=run_id(permit['run_id'])
    private_json(ledger/('permit-'+permit['_document_sha256']+'.json'),dict(run_id=identifier,consumed_at=time.time()))
    private_json(ledger/('run-'+identifier+'.json'),dict(permit_sha256=permit['_document_sha256']))
    fd=os.open(ledger,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def preflight(config):
    need(sys.platform=='linux' and platform.machine()=='x86_64' and os.geteuid()==0,
         'disposable Linux x86_64 setup authority required')
    need(sha(Path('/etc/machine-id').read_bytes())==config['allocated_host']['machine_id_sha256'], 'allocated host identity mismatch')
    need(len(os.sched_getaffinity(0))<=2,'host exceeds accepted vCPU bound')
    mem=next(int(s.split()[1]) for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemTotal:'))
    need(mem<=4096*1024,'host exceeds accepted RAM bound')
    need(subprocess.check_output(['timedatectl','show','-p','NTPSynchronized','--value'],text=True,timeout=5).strip()=='yes',
         'trusted synchronized wall clock required')
    for name in ('python','ip','node','libseccomp'):
        path=(sys.executable if name=='python' else '/lib/x86_64-linux-gnu/libseccomp.so.2' if name=='libseccomp' else shutil.which(name))
        need(path is not None and sha(Path(path).read_bytes())==config['binary_sha256'][name], 'binary pin mismatch: '+name)
    kernel=Path('/boot/config-'+platform.release())
    need(kernel.is_file() and sha(kernel.read_bytes())==config['kernel_config_sha256'],'kernel config pin required')
    need('CONFIG_NET_NS=y' in kernel.read_text() and 'CONFIG_SECCOMP_FILTER=y' in kernel.read_text(),'kernel facilities missing')
    # Provision dependencies before disconnecting this disposable host. No data
    # namespace can be linked to host networking; host egress must already be down.
    links=read_command(['ip','-d','-j','link','show'])
    need(all(p['ifname']=='lo' or 'UP' not in p['flags'] for p in links),'host egress not closed')
    need(not read_command(['ip','-j','route','show','default'])
         and not read_command(['ip','-6','-j','route','show','default']), 'host default route remains')
    import pwd
    for uid in range(60001,60005):
        try:pwd.getpwuid(uid)
        except KeyError:pass
        else:need(False,'dedicated UID collision')
    for p in Path('/proc').glob('[0-9]*/status'):
        try:
            lines=p.read_text().splitlines()
        except (PermissionError,FileNotFoundError,ProcessLookupError):continue
        for line in lines:
            if line.startswith('Uid:'):need(not any(60001<=int(n)<=60004 for n in line.split()[1:]),'dedicated UID is already running')
    for name,version in [('cryptography','50.0.2'),('pycryptodome','4.2.0')]:
        need(importlib.metadata.version(name)==version,'Python dependency pin mismatch')
    return dict(state_mode='fixture-state-ethernet',kernel=platform.release(),host_egress_closed=True,
                ntp_synchronized=True,wall=time.time(),monotonic=time.monotonic(),binary_pins=config['binary_sha256'])


def read_command(argv):
    import json
    return json.loads(subprocess.check_output(argv,text=True,timeout=5))
