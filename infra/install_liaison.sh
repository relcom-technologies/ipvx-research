#!/usr/bin/env bash
set -euo pipefail
revision=${1:?exact source revision required}
[[ $revision =~ ^[0-9a-f]{40}$ && $(id -u) = 0 ]]
source_dir=$(cd "$(dirname "$0")/.." && pwd)
release=/srv/ipvx-liaison/releases/$revision
install -d -m 0755 "$release/scripts"
install -m 0644 "$source_dir"/services/liaison/{agent.py,worker.py,public_sources.py,facts.json,config.example.json,requirements.lock} "$release/"
install -m 0644 "$source_dir/scripts/export_community.py" "$release/scripts/"
install -m 0644 "$source_dir/data/community-discussions.json" "$release/baseline-snapshot.json"
install -m 0700 "$source_dir/infra/configure_liaison.py" /usr/local/sbin/ipvx-liaison-configure
if [[ -n ${IPVX_LIAISON_RUNTIME:-} ]]; then
  test -x "$IPVX_LIAISON_RUNTIME/bin/python"
  cmp "$release/requirements.lock" "$(dirname "$IPVX_LIAISON_RUNTIME")/requirements.lock"
  if [[ -e $release/venv ]]; then
    test -L "$release/venv" && test "$(readlink "$release/venv")" = "$IPVX_LIAISON_RUNTIME"
  else
    ln -s "$IPVX_LIAISON_RUNTIME" "$release/venv"
  fi
else
  python3 -m venv "$release/venv"
  "$release/venv/bin/python" -m pip install --only-binary=:all: --no-cache-dir -r "$release/requirements.lock"
fi
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
# Preserve every ledger/job and key; migrate only the reviewed configuration.
python3 - "$release/config.example.json" <<'PY'
import json,os
import sys,shutil
p='/var/lib/ipvx-liaison/state/config.json'
d=json.load(open(p))
assert d['daily_budget_usd']==3 and d['publication_mode']=='draft_only'
target='/etc/ipvx-liaison/config.json'
if not os.path.exists(target):shutil.copyfile(p,'/etc/ipvx-liaison/config.before-autonomous.json')
current=json.load(open(sys.argv[1]));current['billing_authorized']=True
current['generation_enabled']=False
current['github_project_account']=json.load(open('/etc/ipvx-notifier/notification.json'))['github_owner']
fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as out:json.dump(current,out)
os.chmod(target,0o600)
os.chmod('/etc/ipvx-liaison/config.before-autonomous.json',0o600)
PY
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
LoadCredential=ipvx-config:/etc/ipvx-liaison/config.json
Environment=IPVX_LIAISON_REVISION=$revision
Environment=IPVX_LIAISON_CONFIG_PATH=%d/ipvx-config
EnvironmentFile=-/run/ipvx-liaison-smoke.env
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
CapabilityBoundingSet=
InaccessiblePaths=-/var/lib/private -/var/lib/ipvx-participation-watch -/etc/ipvx-research
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
Description=Read IPvX public replies and prepare one bounded private proposal every five minutes
[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
Unit=ipvx-liaison-poll.service
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
# Credentials and one paid smoke check are separate owner operations. Installing
# files alone neither starts the timer nor sends an API/social request.
echo 'IPvX liaison installed; timer not enabled by this installer'
