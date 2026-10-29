"""Root-only stdin credential installation; never writes values to stdout."""
import json
import os
from pathlib import Path

def configure(directory, raw):
    if set(raw) != {'openai','anthropic'}:raise ValueError('credential_names')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    for name,value in raw.items():
        if not isinstance(value,str) or not 20<=len(value)<=1000 or any(c.isspace() for c in value):raise ValueError('credential_format')
        path=directory/(name+'.key')
        if path.is_symlink():raise ValueError('credential_symlink')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(value)
        os.chmod(path,0o600)

if __name__=='__main__':
    import sys
    if os.geteuid()!=0:raise SystemExit('root_required')
    payload=sys.stdin.buffer.read(4097)
    if len(payload)>4096:raise SystemExit('credential_payload_limit')
    configure(Path('/etc/ipvx-liaison'),json.loads(payload))
    print('IPvX liaison credentials installed privately')
