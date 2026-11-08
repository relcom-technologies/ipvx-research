"""Operator steps on the disposable stand around one authorized run. Root only.

prepare  Export a fresh dataset, record its descriptor, the launch window and this run's
         decision slot in launch-config.json, re-pin that file in manifest.json and write
         the exact v2 permit request for the owner to sign on their own computer.
start    Check the signed permit first, then take the host off the network, run once and
         bring the network back. A separate systemd timer restores the network even if this
         process dies, because the project has no console on the stand.
restore  Bring the saved links up and restart systemd-networkd; safe to repeat.
reviewed-pins  Print the digest of all runner pins except launch-config.json, which the
         owner acknowledges in owner_scope_ack. Read-only; runs anywhere.

The permit, not this file, is the authority: `start` refuses before touching the network
unless admission.authorize accepts the permit against the configured owner key.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .common import ROOT, need, read_json, run_id, sha

HERE = Path(__file__).resolve().parent
STATE = Path('/var/lib/ipvx-bcp/network-state.json')
LEAD_SECONDS = 60
STATIC = ('owner_public_key', 'review_evidence', 'host_image_sha256', 'kernel_config_sha256',
          'allocated_host', 'owner_scope_ack')


NODE = 'v24.22.2 official linux-x64 tarball, SHASUMS256 verified'


def host_inventory(run=None):
    """Recompute the operator-attested host image digest recorded as host_image_sha256."""
    import platform
    run = run or (lambda args: subprocess.check_output(args, text=True, timeout=60))
    packages = run(['dpkg-query', '-W', '-f', '${Package}=${Version}\\n']).splitlines()
    inventory = {'os_release': Path('/etc/os-release').read_text(), 'kernel_release': platform.release(),
                 'machine': platform.machine(), 'packages': sorted(packages), 'node': NODE}
    return sha(json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode())


def command(args, *, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True, timeout=120)


def window(descriptor, now):
    """Earliest start a minute after preparation, latest end at the dataset's own deadline."""
    start = max(int(now), descriptor['created_at']) + LEAD_SECONDS
    end = descriptor['expires_at']
    need(start < end and end - start <= 3600, 'no usable launch window inside the dataset lifetime')
    return [start, end]


CONFIG_NAME = 'runners/bcp02/launch-config.json'


def reviewed_pins(manifest=None, name=CONFIG_NAME):
    """Digest of every runner pin except launch-config.json, the file that carries the owner's ack.

    The full scope hash cannot be acknowledged inside launch-config.json, because writing the
    ack, and later the run slots, changes that file. This digest covers everything else, so any
    change to runner code, tests or plan after the owner's ack makes prepare refuse.
    """
    manifest = dict(read_json(HERE/'manifest.json') if manifest is None else manifest)
    files = dict(manifest['files'])
    need(name in files, 'launch-config.json must be pinned')
    del files[name]
    manifest['files'] = files
    return sha(b'IPVX-BCP02-NET-001-F/reviewed-pins\0' + json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())


def ready(config, manifest=None, name=CONFIG_NAME):
    need(all(config[k] for k in STATIC) and all(config['binary_sha256'].values()) and config['resources_allocated'] is True,
         'static owner and host pins must be reviewed and merged before preparing a run')
    key = config['owner_public_key']
    need(isinstance(key, str) and len(key) == 64 and all(c in '0123456789abcdef' for c in key), 'owner_public_key must be a raw Ed25519 key in hex')
    ack = config['owner_scope_ack']
    need(isinstance(ack, dict) and ack.get('owner_statement') and ack.get('reviewed_pins_sha256') == reviewed_pins(manifest, name),
         'runner pins changed since the owner acknowledged them')
    need(config['run_dataset'] is None and config['accepted_window'] is None and config['owner_launch_decision'] is None,
         'launch-config already names a run; start from a fresh tree')
    return config


def record(config_path, manifest_path, descriptor, accepted):
    """Write this run's dataset, window and decision slot, then re-pin the config file."""
    manifest = read_json(manifest_path)
    name = str(Path(config_path).resolve().relative_to(ROOT))
    config = ready(read_json(config_path), manifest, name)
    config['run_dataset'] = descriptor
    config['accepted_window'] = accepted
    config['owner_launch_decision'] = {'run_id': descriptor['run_id'], 'form': 'owner-signed v2 permit for this run only'}
    raw = (json.dumps(config, indent=2) + '\n').encode()
    Path(config_path).write_bytes(raw)
    manifest['files'][name] = sha(raw)
    Path(manifest_path).write_text(json.dumps(manifest, indent=2) + '\n')
    return config


def request(config, scope):
    d = config['run_dataset']
    return dict(version=2, scope_sha256=scope, run_id=d['run_id'], host_image_sha256=config['host_image_sha256'],
                not_before=config['accepted_window'][0], not_after=config['accepted_window'][1],
                launch=True, transactions=0, production=False, dataset=d)


def prepare(run, dataset_dir, request_path):
    from .admission import source_hash
    from .dataset import seal
    from .fixture import export
    need(os.geteuid() == 0, 'root required')
    run_id(run)
    source_hash()  # the tree must match its pins before anything is written
    config = ready(read_json(HERE/'launch-config.json'))
    need(host_inventory() == config['host_image_sha256'], 'host changed since its image digest was recorded')
    now = int(time.time())
    export(dataset_dir, run, now)
    descriptor = seal(dataset_dir, time.time())
    config = record(HERE/'launch-config.json', HERE/'manifest.json', descriptor, window(descriptor, time.time()))
    scope = source_hash()
    payload = request(config, scope)
    fd = os.open(request_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, 'w') as f:
        f.write(json.dumps(payload, sort_keys=True, indent=2) + '\n')
    return payload


def links(run=command):
    """Non-loopback links that are up, and the devices of default routes."""
    up = [l['ifname'] for l in json.loads(run(['ip', '-j', 'link', 'show']).stdout)
          if l['ifname'] != 'lo' and 'UP' in l.get('flags', [])]
    routes = json.loads(run(['ip', '-j', 'route', 'show', 'default']).stdout)
    return dict(links=up, default_devices=sorted({r['dev'] for r in routes}))


def take_down(state, run=command):
    run(['systemctl', 'stop', 'systemd-networkd.socket', 'systemd-networkd'])
    for name in state['links']:
        run(['ip', 'link', 'set', 'dev', name, 'down'])
    after = links(run)
    need(not after['links'] and not after['default_devices'], 'host network still up')


def restore(state=None, run=command, wait=60):
    state = state or read_json(STATE)
    for name in state['links']:
        run(['ip', 'link', 'set', 'dev', name, 'up'], check=False)
    run(['systemctl', 'start', 'systemd-networkd.socket', 'systemd-networkd'], check=False)
    for name in state['links']:
        run(['networkctl', 'reconfigure', name], check=False)
    deadline = time.monotonic() + wait
    while True:
        now = links(run)
        if set(state['default_devices']) <= set(now['default_devices']):
            return now
        need(time.monotonic() < deadline, 'default route did not come back')
        time.sleep(1)


def start(permit, dataset_dir, output, run=command):
    from .admission import authorize
    need(os.geteuid() == 0, 'root required')
    signed, config = authorize(permit)  # refuse before any network change
    state = links(run)
    need(state['links'] and state['default_devices'], 'expected an online host before the run')
    STATE.parent.mkdir(mode=0o711, exist_ok=True)
    STATE.write_text(json.dumps(state) + '\n')
    # Independent safety net: restore the network after the window even if this process dies.
    delay = max(60, signed['not_after'] - int(time.time()) + 300)
    unit = 'ipvx-bcp-restore-' + signed['run_id']
    run(['systemd-run', '--unit', unit, '--on-active', '%ds' % delay, '--working-directory', str(ROOT),
         sys.executable, '-B', '-m', 'runners.bcp02.stand_launch', 'restore'])
    status = dict(run_id=signed['run_id'], started_at=time.time(), network_state=state, safety_timer=unit)
    log = Path(output).parent/(signed['run_id'] + '-cli.json')
    try:
        take_down(state, run)
        status['network_down_at'] = time.time()
        with open(log, 'x') as f:
            finished = subprocess.run([sys.executable, '-B', '-m', 'runners.bcp02.cli', 'run', '--permit', str(permit),
                                       '--dataset', str(dataset_dir), '--output', str(output)],
                                      cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                                      timeout=max(60, signed['not_after'] - int(time.time()) + 120))
        status['cli_exit'] = finished.returncode
    except BaseException as e:
        status['error'] = type(e).__name__ + ': ' + str(e)
    finally:
        try:
            status['network_after'] = restore(state, run)
            run(['systemctl', 'stop', unit + '.timer'], check=False)
        except BaseException as e:
            status['restore_error'] = type(e).__name__ + ': ' + str(e)
        status['finished_at'] = time.time()
        Path(output).parent.joinpath(signed['run_id'] + '-launch.json').write_text(json.dumps(status, indent=2) + '\n')
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--run-id', required=True)
    p.add_argument('--dataset', required=True, type=Path); p.add_argument('--request', required=True, type=Path)
    s = sub.add_parser('start'); s.add_argument('--permit', required=True, type=Path)
    s.add_argument('--dataset', required=True, type=Path); s.add_argument('--output', required=True, type=Path)
    sub.add_parser('restore')
    sub.add_parser('inventory')
    sub.add_parser('reviewed-pins', help='digest the owner acknowledges; needs no root')
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        print(json.dumps(prepare(args.run_id, args.dataset, args.request), indent=2))
    elif args.command == 'start':
        print(json.dumps(start(args.permit, args.dataset, args.output), indent=2))
    elif args.command == 'inventory':
        print(host_inventory())
    elif args.command == 'reviewed-pins':
        print(reviewed_pins())
    else:
        print(json.dumps(restore(), indent=2))


if __name__ == '__main__':
    main()
