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
install -m 0644 "$source_dir/infra/auth.py" "$release/auth.py"
install -m 0644 "$source_dir/infra/community.py" "$release/community.py"
install -m 0644 "$source_dir/infra/configure_community.py" "$release/configure_community.py"
install -m 0644 "$source_dir/infra/auth-requirements.lock" "$release/auth-requirements.lock"
python3 -m venv "$release/auth-venv"
"$release/auth-venv/bin/python" -m pip install --only-binary=:all: --no-cache-dir -r "$release/auth-requirements.lock"
for module in a2a_service a2a_store a2a_admin; do
  install -m 0644 "$source_dir/infra/$module.py" "$release/$module.py"
done
install -m 0644 "$source_dir/infra/a2a-requirements.lock" "$release/a2a-requirements.lock"
python3 -m venv "$release/a2a-venv"
"$release/a2a-venv/bin/python" -m pip install --only-binary=:all: --no-cache-dir -r "$release/a2a-requirements.lock"
install -d -m 0700 /etc/ipvx-research
python3 - <<'KEY'
import os,secrets,stat
from pathlib import Path
path=Path('/etc/ipvx-research/a2a-admin.key')
if not path.exists():
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as out: out.write(secrets.token_bytes(32))
assert not path.is_symlink() and stat.S_ISREG(path.stat().st_mode)
assert stat.S_IMODE(path.stat().st_mode)==0o600 and len(path.read_bytes())==32
KEY
cat > /etc/systemd/system/ipvx-research-a2a.service <<EOF
[Unit]
Description=IPvX A2A proposal intake (loopback only, no execution)
After=network-online.target
[Service]
DynamicUser=yes
StateDirectory=ipvx-research-a2a
StateDirectoryMode=0700
LoadCredential=ipvx-a2a-admin:/etc/ipvx-research/a2a-admin.key
Environment=IPVX_A2A_STATE_DIR=/var/lib/ipvx-research-a2a/state
Environment=IPVX_PUBLIC_DIR=$release/public
Environment=IPVX_RELEASE_REVISION=$revision
ExecStart=$release/a2a-venv/bin/python $release/a2a_service.py
Restart=always
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
IPAddressAllow=127.0.0.1/32
CPUQuota=25%
MemoryMax=256M
TasksMax=64
LimitFSIZE=64M
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
ln -sfn "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
cat > /etc/systemd/system/ipvx-research-auth.service <<EOF
[Unit]
Description=IPvX Relcom ID sign-in (loopback only, no laboratory access)
After=network-online.target
Wants=network-online.target
[Service]
DynamicUser=yes
StateDirectory=ipvx-research-auth
LoadCredential=ipvx-a2a-admin:/etc/ipvx-research/a2a-admin.key
StateDirectoryMode=0700
EnvironmentFile=-/etc/ipvx-research/community.env
Environment=IPVX_AUTH_STATE_DIR=/var/lib/ipvx-research-auth/state
Environment=IPVX_COMMUNITY_STATE_DIR=/var/lib/ipvx-research-auth/community
Environment=RELCOM_ID_CLIENT_ID=396952476441378818
Environment=RELCOM_ID_ORG_ID=396952378110115842
ExecStart=$release/auth-venv/bin/python $release/auth.py
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
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CPUQuota=25%
MemoryMax=192M
TasksMax=32
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/ipvx-research.service <<EOF
[Unit]
Description=IPvX public research files (no lab API)
After=network-online.target
Wants=network-online.target
[Service]
DynamicUser=yes
ExecStart=/usr/bin/python3 $release/server.py --root $release/public --revision $revision --auth-port 8094 --a2a-port 8095
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
IPAddressAllow=127.0.0.1/32
CPUQuota=25%
MemoryMax=128M
TasksMax=32
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ipvx-research-a2a.service
systemctl restart ipvx-research-a2a.service
systemctl enable --now ipvx-research-auth.service
systemctl restart ipvx-research-auth.service
systemctl enable --now ipvx-research.service
systemctl restart ipvx-research.service
for attempt in {1..20}; do
  if curl --fail --silent http://10.10.50.131:8092/healthz | python3 -c 'import json,sys; assert json.load(sys.stdin)["revision"]==sys.argv[1]' "$revision"; then
    if curl --fail --silent -H 'Host: ipvx.org' http://10.10.50.131:8092/auth/session | python3 -c 'import json,sys; j=json.load(sys.stdin); assert j["authenticated"] is False and j["user"] is None'; then
      if curl --fail --silent http://127.0.0.1:8095/healthz | python3 -c 'import json,sys; assert json.load(sys.stdin)["revision"]==sys.argv[1]' "$revision"; then
        exit 0
      fi
    fi
  fi
  sleep 1
done
exit 1
