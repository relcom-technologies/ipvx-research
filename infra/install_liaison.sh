#!/usr/bin/env bash
set -euo pipefail
revision=${1:?exact source revision required}
[[ $revision =~ ^[0-9a-f]{40}$ && $(id -u) = 0 ]]
source_dir=$(cd "$(dirname "$0")/.." && pwd)
release=/srv/ipvx-liaison/releases/$revision
install -d -m 0755 "$release/scripts"
install -m 0644 "$source_dir"/services/liaison/{agent.py,worker.py,facts.json,config.example.json,requirements.lock} "$release/"
install -m 0644 "$source_dir/scripts/export_community.py" "$release/scripts/"
install -m 0644 "$source_dir/data/community-discussions.json" "$release/baseline-snapshot.json"
install -m 0700 "$source_dir/infra/configure_liaison.py" /usr/local/sbin/ipvx-liaison-configure
python3 -m venv "$release/venv"
"$release/venv/bin/python" -m pip install --only-binary=:all: --no-cache-dir -r "$release/requirements.lock"
install -d -m 0700 /etc/ipvx-liaison
install -d -m 0755 /var/lib/ipvx-liaison /var/lib/ipvx-liaison/public
install -d -m 0700 /var/lib/ipvx-liaison/state
if ! test -f /var/lib/ipvx-liaison/state/config.json; then
  python3 - "$release/config.example.json" <<'PY'
import json,os,sys
p='/var/lib/ipvx-liaison/state/config.json'
d=json.load(open(sys.argv[1]));assert d['daily_budget_usd']==3 and d['publication_mode']=='draft_only'
d['billing_authorized']=True
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as out:json.dump(d,out)
PY
fi
# A fixed unprivileged account owns only its state/public JSON, no portal roles.
id ipvx-liaison >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin ipvx-liaison
chown -R ipvx-liaison:ipvx-liaison /var/lib/ipvx-liaison
for mode in poll smoke; do
  extra=''; [[ $mode = smoke ]] && extra='--smoke'
  cat > "/etc/systemd/system/ipvx-liaison-$mode.service" <<EOF
[Unit]
Description=IPvX project liaison ($mode; private drafts, no automatic posts)
After=network-online.target
[Service]
Type=oneshot
User=ipvx-liaison
Group=ipvx-liaison
LoadCredential=ipvx-openai:/etc/ipvx-liaison/openai.key
LoadCredential=ipvx-anthropic:/etc/ipvx-liaison/anthropic.key
Environment=IPVX_LIAISON_REVISION=$revision
ExecStart=$release/venv/bin/python $release/worker.py --state-dir /var/lib/ipvx-liaison/state --public-dir /var/lib/ipvx-liaison/public $extra
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
ReadWritePaths=/var/lib/ipvx-liaison
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CPUQuota=25%
MemoryMax=256M
TasksMax=32
TimeoutStartSec=240
UMask=0077
EOF
done
cat > /etc/systemd/system/ipvx-liaison.timer <<'EOF'
[Unit]
Description=Read IPvX discussion and prepare one bounded draft every 15 minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Unit=ipvx-liaison-poll.service
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
# Credentials and one paid smoke check are separate workflow steps. Installing
# files alone neither starts the timer nor sends an API/social request.
echo 'IPvX liaison installed; timer not enabled by this installer'
