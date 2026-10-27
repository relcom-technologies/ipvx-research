"""Pin an already observed verified participant as bootstrap admin on this VM.

Run only through the scoped operator CI, as root. No raw provider subject, email,
token, first-login promotion or direct database modification is used.
"""
import json
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request


def configure(author):
    if os.geteuid() != 0 or not re.fullmatch(r'member_[a-f0-9]{24}', author):
        raise ValueError('Requires root and an observed project author ID')
    database = Path('/var/lib/ipvx-research-auth/community/community.sqlite3')
    if database.is_symlink() or not database.is_file():
        raise ValueError('The running community store must exist first')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute('SELECT 1 FROM users WHERE actor=?', (author,)).fetchone():
            raise ValueError('This author has not established a verified project session')
        old = db.execute("SELECT value FROM settings WHERE key='bootstrap_admin'").fetchone()
        if old and old[0] != author:
            raise ValueError('A different bootstrap administrator requires a reviewed migration')
    directory = Path('/etc/ipvx-research')
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != 0:
        raise ValueError('Operator configuration directory is not root-owned')
    directory.chmod(0o700)
    config = directory/'community.env'
    if config.exists() and (config.is_symlink() or config.stat().st_uid != 0
                            or not stat.S_ISREG(config.stat().st_mode)):
        raise ValueError('Operator configuration must be a root-owned regular file')
    def install(content):
        fd, name = tempfile.mkstemp(prefix='.community-', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, config)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    install(('IPVX_COMMUNITY_ADMIN_AUTHOR_ID=' + author + '\n').encode('ascii'))
    try:
        subprocess.run(['systemctl', 'restart', 'ipvx-research-auth.service'], check=True, timeout=45)
        # The identity listener remains bound to loopback; no authenticated
        # cookies or private response bodies are printed to CI.
        req = urllib.request.Request('http://127.0.0.1:8094/community/v1/session',
                                     headers={'Host': 'ipvx.org'})
        deadline = time.monotonic() + 12
        while True:
            try:
                with urllib.request.urlopen(req, timeout=2) as response:
                    value = json.loads(response.read(8192))
                    if value.get('authenticated') is not False or value.get('roles') != []:
                        raise ValueError('Anonymous boundary failed after restart')
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            pin = db.execute("SELECT value FROM settings WHERE key='bootstrap_admin'").fetchone()
            role = db.execute("SELECT 1 FROM roles WHERE actor=? AND role='admin'", (author,)).fetchone()
            if not pin or pin[0] != author or not role:
                raise ValueError('The identity service did not confirm the configured bootstrap role')
    except Exception:
        # Initialization may already have committed the audited bootstrap role.
        # Restoring only an environment file would falsely suggest rollback.
        # Retain the matching pin: retry this same confirmed author, or use an
        # explicit reviewed operator recovery; never silently change the owner.
        print('Bootstrap may already be applied. Configuration retained; health check failed. '
              'Retry the same confirmed author or perform reviewed recovery.', file=sys.stderr)
        raise
    print('Configured the confirmed existing project participant; anonymous access still has no roles.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Pass exactly one confirmed project author ID')
    configure(sys.argv[1])
