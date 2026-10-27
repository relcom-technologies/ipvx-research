"""Fail closed if Kconfig changed any required no-IP property."""
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
required = ['64BIT', 'NET', 'PACKET', 'UNIX', 'BINFMT_ELF', 'BLK_DEV_INITRD',
            'PROC_FS', 'SYSFS', 'DEVTMPFS', 'VIRTIO_NET', 'VIRTIO_PCI',
            'SERIAL_8250_CONSOLE', 'HW_RANDOM_VIRTIO']
absent = ['INET', 'IPV6', 'MODULES']
for key in required:
    if f'CONFIG_{key}=y\n' not in text:
        raise SystemExit(f'Required CONFIG_{key}=y is missing')
for key in absent:
    if f'# CONFIG_{key} is not set\n' not in text:
        raise SystemExit(f'CONFIG_{key} was not removed')
print('PASS: required built-ins, CONFIG_INET=n, CONFIG_IPV6=n and CONFIG_MODULES=n')
