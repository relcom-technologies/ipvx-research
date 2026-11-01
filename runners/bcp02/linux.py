"""Privilege drop and seccomp for future disposable Linux stand processes only."""
import ctypes
import errno
import os
import platform
import resource
import sys
import time
from .common import need, sha

DENIED = ('socket', 'socketpair', 'setns', 'unshare', 'mount', 'umount2', 'pivot_root',
          'ptrace', 'bpf', 'execve', 'execveat', 'fork', 'vfork', 'clone', 'clone3',
          'io_uring_setup', 'io_uring_enter', 'io_uring_register')


def isolate(uid, *, library='/lib/x86_64-linux-gnu/libseccomp.so.2'):
    need(sys.platform=='linux' and platform.machine()=='x86_64' and os.geteuid()==0,
         'initial Linux x86_64 setup authority required')
    need(type(uid) is int and 60001<=uid<=60004, 'dedicated unused UID required')
    lib=ctypes.CDLL(library); libc=ctypes.CDLL(None,use_errno=True)
    lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
    ctx=lib.seccomp_init(0x7fff0000)
    need(bool(ctx), 'seccomp initialization failed')
    try:
        for name in DENIED:
            number=lib.seccomp_syscall_resolve_name(name.encode())
            need(number>=0, 'unsupported seccomp syscall '+name)
            need(lib.seccomp_rule_add(ctx,0x50000|errno.EPERM,number,0)==0,'seccomp rule failed')
        # No credential, capability or host networking authority survives startup.
        for cap in range(41):
            need(libc.prctl(24,cap,0,0,0)==0,'cannot drop capability bounding set')
        os.setgroups([]);os.setresgid(uid,uid,uid);os.setresuid(uid,uid,uid)
        need(libc.prctl(38,1,0,0,0)==0,'no_new_privs failed')
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(1200,1200))
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2))
        need(lib.seccomp_load(ctx)==0,'seccomp load failed')
    finally:lib.seccomp_release(ctx)
    with open('/proc/self/status') as f:
        status={line.split(':')[0]:line.split(':',1)[1].strip() for line in f if ':' in line}
    need(all(int(status[k],16)==0 for k in ('CapEff','CapPrm','CapBnd','CapAmb'))
         and status['NoNewPrivs']=='1' and status['Seccomp']=='2','process isolation not established')
    return {k:status[k] for k in ('CapEff','CapPrm','CapBnd','CapAmb','NoNewPrivs','Seccomp')}


class Clock:
    def __init__(self, wall, monotonic):
        self.wall,self.monotonic=wall,monotonic

    def read(self):
        now,mono=time.time(),time.monotonic()
        need(mono>=self.monotonic and abs((now-self.wall)-(mono-self.monotonic))<=5,'clock discontinuity')
        return dict(now=int(now),monotonic=mono,clock_trusted=True)
