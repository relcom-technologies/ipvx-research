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
python3 "$source_dir/infra/export.py" "$source_dir" "$release/public"
install -m 0644 "$source_dir/infra/server.py" "$release/server.py"
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
