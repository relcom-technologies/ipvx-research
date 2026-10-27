#!/usr/bin/env bash
# Called by the scoped relcom-infra workflow on the existing observer only.
set -euo pipefail
revision=${1:?exact source commit required}
[[ $revision =~ ^[0-9a-f]{40}$ ]]
[[ $(id -u) = 0 ]]
source_dir=$(cd "$(dirname "$0")/.." && pwd)
base=/srv/ipvx-research
release=$base/releases/$revision
install -d -m 0755 "$release/public"
python3 - "$source_dir" "$release" <<'PY'
import shutil,sys
from pathlib import Path
source,target=map(Path,sys.argv[1:])
files=[*source.glob('*.html'), source/'governance.json']
for directory in ('assets','data','rfc'):
    files.extend(p for p in (source/directory).rglob('*') if p.is_file())
for file in files:
    if file.is_symlink() or not file.resolve().is_relative_to(source.resolve()):
        raise SystemExit('Non-regular public source refused')
    destination=target/'public'/file.relative_to(source)
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(file,destination)
    destination.chmod(0o644)
shutil.copyfile(source/'infra/server.py',target/'server.py')
(target/'server.py').chmod(0o644)
PY
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
cat > /etc/systemd/system/ipvx-research.service <<EOF
[Unit]
Description=IPvX public research files (no lab API)
After=network-online.target
Wants=network-online.target
[Service]
DynamicUser=yes
ExecStart=/usr/bin/python3 $release/server.py --root $release/public --revision $revision
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictAddressFamilies=AF_INET AF_UNIX
IPAddressDeny=any
IPAddressAllow=10.10.50.0/24
CPUQuota=25%
MemoryMax=128M
TasksMax=32
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ipvx-research.service
systemctl restart ipvx-research.service
for attempt in {1..20}; do
  if curl --fail --silent http://10.10.50.131:8092/healthz | python3 -c 'import json,sys; assert json.load(sys.stdin)["revision"]==sys.argv[1]' "$revision"; then
    exit 0
  fi
  sleep 1
done
exit 1
