"""Fail closed if Kconfig changed any required no-IP property."""
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
required = ['64BIT', 'NET', 'PACKET', 'UNIX', 'BINFMT_ELF', 'BLK_DEV_INITRD',
            'PROC_FS', 'SYSFS', 'DEVTMPFS', 'VIRTIO_NET', 'VIRTIO_PCI',
            'SERIAL_8250_CONSOLE', 'HW_RANDOM_VIRTIO']
absent = ['INET', 'MODULES']
for key in required:
    if f'CONFIG_{key}=y\n' not in text:
        raise SystemExit(f'Required CONFIG_{key}=y is missing')
for key in absent:
    if f'# CONFIG_{key} is not set\n' not in text:
        raise SystemExit(f'CONFIG_{key} was not removed')
# IPv6 Kconfig is inside `if INET` in this pinned kernel, so its disabled
# symbol may be completely absent when INET=n. Neither y nor m is permitted.
if any(f'CONFIG_IPV6={value}\n' in text for value in ('y', 'm')):
    raise SystemExit('CONFIG_IPV6 was enabled')
if len(sys.argv) > 2:
    generated = Path(sys.argv[2]).read_text()
    if any(f'#define CONFIG_{key} ' in generated for key in ('INET', 'IPV6', 'MODULES')):
        raise SystemExit('Forbidden network/module definition in generated kernel configuration')
print('PASS: required built-ins, CONFIG_INET=n, CONFIG_IPV6=n and CONFIG_MODULES=n')
