"""Boot actual no-IP Linux guests on Unix-only virtual Ethernet links.

Host downloads, CI orchestration and console collection use normal host facilities.
No NIC, namespace, TAP, DNS or firewall on the host is configured by this runner.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def events(path):
    result = []
    if path.exists():
        for line in path.read_text(errors='replace').splitlines():
            if line.startswith('XNS_EVENT '):
                result.append(json.loads(line[10:]))
    return result


def wait_file(path, process, timeout=10):
    until = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None or time.monotonic() > until:
            raise RuntimeError('QEMU Unix network listener did not become ready')
        time.sleep(.05)


def scenario(artifacts, output, relay_down):
    output.mkdir(parents=True, exist_ok=True)
    processes, handles, commands = {}, [], {}
    with tempfile.TemporaryDirectory(prefix='xns-') as sockets:
        ar, rb = Path(sockets)/'ar.sock', Path(sockets)/'rb.sock'
        base = ['qemu-system-x86_64', '-machine', 'q35,accel=tcg', '-cpu', 'max',
                '-smp', '1', '-m', '192M', '-nodefaults', '-display', 'none', '-monitor', 'none',
                '-no-reboot', '-nic', 'none', '-kernel', str(artifacts/'bzImage'),
                '-initrd', str(artifacts/'initramfs.cpio.gz'),
                '-object', 'rng-random,id=entropy,filename=/dev/urandom',
                '-device', 'virtio-rng-pci,rng=entropy']
        def start(node, links):
            command = base + ['-append', f'console=ttyS0 panic=-1 reboot=t xns.role={node}',
                              '-serial', f'file:{output/node}.console.log']
            for name, socket, server, mac, capture in links:
                command += ['-netdev', f'stream,id={name},server={"on" if server else "off"},addr.type=unix,addr.path={socket}',
                            '-device', f'virtio-net-pci,netdev={name},mac={mac}']
                if capture:
                    command += ['-object', f'filter-dump,id=cap{name},netdev={name},file={output/capture},maxlen=65535']
            commands[node] = command
            stderr = (output/f'{node}.qemu.log').open('wb');handles.append(stderr)
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr)
            processes[node] = process
            return process
        try:
            a = start('A', [('ar', ar, True, '02:58:00:00:00:01', 'ar.pcap')]);wait_file(ar,a)
            r = start('R', [('ar', ar, False, '02:58:00:00:00:11', None),
                            ('rb', rb, True, '02:58:00:00:00:12', 'rb.pcap')]);wait_file(rb,r)
            start('B', [('rb', rb, False, '02:58:00:00:00:02', None)])
            if relay_down:
                until = time.monotonic() + 90
                while True:
                    logs = {node: events(output/f'{node}.console.log') for node in processes}
                    if all(sum(x.get('event') == 'packet_probe' for x in logs[node]) >= (2 if node == 'R' else 1)
                           for node in processes):
                        if any(x.get('event') == 'summary' for x in logs['A']):
                            raise RuntimeError('Relay failure was injected too late')
                        r.terminate();r.wait(timeout=10)
                        break
                    if time.monotonic() > until:
                        raise RuntimeError('All guests did not reach native socket readiness')
                    time.sleep(.05)
            a.wait(timeout=180)
        finally:
            for process in processes.values():
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.kill();process.wait()
            for handle in handles: handle.close()
            (output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
    subprocess.run([sys.executable, str(ROOT/'scripts/verify.py'), str(output),
                    '--mode', 'relay-down' if relay_down else 'baseline'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, default=ROOT/'build/artifacts')
    parser.add_argument('--output', type=Path, default=ROOT/'build/results')
    args = parser.parse_args()
    if not shutil.which('qemu-system-x86_64'):
        raise SystemExit('QEMU is required; no guest-run result can be inferred without it')
    subprocess.run(['qemu-system-x86_64', '--version'], check=True)
    for name, down in [('baseline', False), ('relay-down', True)]:
        scenario(args.artifacts.resolve(), (args.output/name).resolve(), down)
