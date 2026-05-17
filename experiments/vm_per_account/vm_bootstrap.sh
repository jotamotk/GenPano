#!/usr/bin/env bash
# vm_bootstrap.sh — provision a fresh Aliyun ECS Ubuntu 22.04 host into a
# VM-resident persistent-Chrome runner for the M1 PoC described in
# experiments/vm_per_account/README.md.
#
# Run as root (or via sudo) on a freshly-provisioned Ubuntu 22.04 host:
#
#     sudo bash vm_bootstrap.sh
#
# Idempotent: safe to re-run. Will not re-create the ops user, will not
# regenerate the VNC password if one already exists, will not start the two
# Chrome services automatically (operator does that after first manual login).
set -euo pipefail

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
OPS_USER="ops"
OPS_HOME="/home/${OPS_USER}"
VNC_PASSWORD_FILE="${OPS_HOME}/.vncpasswd"
VNC_DISPLAY=":0"
DOUBAO_PROFILE_DIR="${OPS_HOME}/profile-doubao"
DEEPSEEK_PROFILE_DIR="${OPS_HOME}/profile-deepseek"
DOUBAO_DEBUG_PORT="9222"
DEEPSEEK_DEBUG_PORT="9223"

log() { printf '[vm_bootstrap] %s\n' "$*"; }

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: must run as root (use sudo)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# -----------------------------------------------------------------------------
# 1. Base apt setup + desktop + VNC + tools
# -----------------------------------------------------------------------------
log "apt update"
apt-get update -y

log "install xfce4 minimal, x11vnc, novnc, websockify, xdotool, xvfb, dbus-x11, curl, ca-certificates, gnupg"
apt-get install -y --no-install-recommends \
  xfce4-session xfce4-panel xfwm4 xfce4-terminal \
  x11vnc novnc websockify \
  xvfb xdotool dbus-x11 \
  curl ca-certificates gnupg apt-transport-https ufw sudo \
  fonts-wqy-microhei fonts-noto-cjk

# -----------------------------------------------------------------------------
# 2. Google Chrome from Google's apt repo
# -----------------------------------------------------------------------------
if [[ ! -f /etc/apt/sources.list.d/google-chrome.list ]]; then
  log "add Google Chrome apt key and repo"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg
  chmod 0644 /etc/apt/keyrings/google-chrome.gpg
  cat >/etc/apt/sources.list.d/google-chrome.list <<'EOF'
deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main
EOF
  apt-get update -y
fi

if ! command -v google-chrome >/dev/null 2>&1; then
  log "install google-chrome-stable"
  apt-get install -y google-chrome-stable
else
  log "google-chrome already installed: $(google-chrome --version)"
fi

# -----------------------------------------------------------------------------
# 3. Tailscale (official installer)
# -----------------------------------------------------------------------------
if ! command -v tailscale >/dev/null 2>&1; then
  log "install tailscale via official one-liner"
  curl -fsSL https://tailscale.com/install.sh | sh
else
  log "tailscale already installed: $(tailscale version | head -n1)"
fi

# -----------------------------------------------------------------------------
# 4. ops user with passwordless sudo
# -----------------------------------------------------------------------------
if ! id "${OPS_USER}" >/dev/null 2>&1; then
  log "create user ${OPS_USER}"
  useradd -m -s /bin/bash "${OPS_USER}"
fi

# passwordless sudo for ops
SUDOERS_FILE="/etc/sudoers.d/${OPS_USER}-nopass"
if [[ ! -f "${SUDOERS_FILE}" ]]; then
  log "grant passwordless sudo to ${OPS_USER}"
  echo "${OPS_USER} ALL=(ALL) NOPASSWD:ALL" > "${SUDOERS_FILE}"
  chmod 0440 "${SUDOERS_FILE}"
fi

install -d -o "${OPS_USER}" -g "${OPS_USER}" -m 0755 "${DOUBAO_PROFILE_DIR}"
install -d -o "${OPS_USER}" -g "${OPS_USER}" -m 0755 "${DEEPSEEK_PROFILE_DIR}"

# -----------------------------------------------------------------------------
# 5. VNC password (generate once, keep across re-runs)
# -----------------------------------------------------------------------------
# spec: "generates random 8-char VNC password if /home/ops/.vncpasswd doesn't
# exist, stores via `x11vnc -storepasswd <pwd> /home/ops/.vncpasswd`"
if [[ ! -s "${VNC_PASSWORD_FILE}" ]]; then
  log "generate VNC password and store via x11vnc -storepasswd at ${VNC_PASSWORD_FILE}"
  VNC_PW="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 8)"
  # Cache the plaintext to display in the banner before storepasswd binary-encodes.
  printf '%s' "${VNC_PW}" > "${OPS_HOME}/.vncpasswd.plain"
  chown "${OPS_USER}:${OPS_USER}" "${OPS_HOME}/.vncpasswd.plain"
  chmod 0600 "${OPS_HOME}/.vncpasswd.plain"
  # Write the x11vnc-format password file (binary blob) at the spec path.
  sudo -u "${OPS_USER}" x11vnc -storepasswd "${VNC_PW}" "${VNC_PASSWORD_FILE}"
  chmod 0600 "${VNC_PASSWORD_FILE}"
  chown "${OPS_USER}:${OPS_USER}" "${VNC_PASSWORD_FILE}"
fi
# Banner needs the plaintext; read from sidecar if present, else mark unknown.
if [[ -s "${OPS_HOME}/.vncpasswd.plain" ]]; then
  VNC_PW_DISPLAY="$(cat "${OPS_HOME}/.vncpasswd.plain")"
else
  VNC_PW_DISPLAY="(already set on a prior run; reset by deleting ${VNC_PASSWORD_FILE} and re-running)"
fi

# -----------------------------------------------------------------------------
# 6. systemd units
# -----------------------------------------------------------------------------
log "write systemd units"

# Xvfb on display :0 — spec uses Xvfb@0.service template-style name and the
# exact ExecStart from the plan.
cat >/etc/systemd/system/Xvfb@0.service <<EOF
[Unit]
Description=Xvfb virtual framebuffer on display :%i
After=network.target
Before=xfce.service x11vnc.service

[Service]
Type=simple
User=${OPS_USER}
ExecStart=/usr/bin/Xvfb :%i -screen 0 1920x1080x24 -nolisten tcp
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/xfce.service <<EOF
[Unit]
Description=Xfce4 session on ${VNC_DISPLAY}
After=Xvfb@0.service
Requires=Xvfb@0.service

[Service]
Type=simple
User=${OPS_USER}
Environment=DISPLAY=${VNC_DISPLAY}
Environment=HOME=${OPS_HOME}
WorkingDirectory=${OPS_HOME}
ExecStart=/usr/bin/dbus-launch --exit-with-session /usr/bin/startxfce4
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/x11vnc.service <<EOF
[Unit]
Description=x11vnc bound to localhost:5900 with rfbauth
After=xfce.service
Requires=Xvfb@0.service

[Service]
Type=simple
User=${OPS_USER}
Environment=DISPLAY=${VNC_DISPLAY}
ExecStart=/usr/bin/x11vnc -display ${VNC_DISPLAY} -localhost -forever -shared -rfbauth ${VNC_PASSWORD_FILE}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/websockify.service <<EOF
[Unit]
Description=websockify wrapping x11vnc on port 6080 (noVNC web client)
After=x11vnc.service
Requires=x11vnc.service

[Service]
Type=simple
User=${OPS_USER}
ExecStart=/usr/bin/websockify --web /usr/share/novnc 6080 localhost:5900
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Chrome units. Spec: WantedBy=default.target, NOT auto-enabled; ExecStart
# uses --user-data-dir, --remote-debugging-port, --remote-debugging-address,
# --no-sandbox, --no-first-run.
cat >/etc/systemd/system/chrome-doubao.service <<EOF
[Unit]
Description=Google Chrome (persistent profile) for Doubao with CDP on ${DOUBAO_DEBUG_PORT}
After=xfce.service
Requires=Xvfb@0.service

[Service]
Type=simple
User=${OPS_USER}
Environment=DISPLAY=${VNC_DISPLAY}
Environment=HOME=${OPS_HOME}
WorkingDirectory=${OPS_HOME}
ExecStart=/usr/bin/google-chrome --user-data-dir=${DOUBAO_PROFILE_DIR} --remote-debugging-port=${DOUBAO_DEBUG_PORT} --remote-debugging-address=127.0.0.1 --no-sandbox --no-first-run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

cat >/etc/systemd/system/chrome-deepseek.service <<EOF
[Unit]
Description=Google Chrome (persistent profile) for DeepSeek with CDP on ${DEEPSEEK_DEBUG_PORT}
After=xfce.service
Requires=Xvfb@0.service

[Service]
Type=simple
User=${OPS_USER}
Environment=DISPLAY=${VNC_DISPLAY}
Environment=HOME=${OPS_HOME}
WorkingDirectory=${OPS_HOME}
ExecStart=/usr/bin/google-chrome --user-data-dir=${DEEPSEEK_PROFILE_DIR} --remote-debugging-port=${DEEPSEEK_DEBUG_PORT} --remote-debugging-address=127.0.0.1 --no-sandbox --no-first-run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

log "systemctl daemon-reload"
systemctl daemon-reload

log "enable+start Xvfb@0, xfce, x11vnc, websockify (display stack)"
systemctl enable --now Xvfb@0.service
systemctl enable --now xfce.service
systemctl enable --now x11vnc.service
systemctl enable --now websockify.service

# Chrome services: enabled (so they survive reboot once the operator wants
# them) but intentionally NOT started here. Operator starts them after the
# first VNC login so the first launch is observable.
log "enable (but do NOT start) chrome-doubao + chrome-deepseek (operator starts them after first VNC login)"
systemctl enable chrome-doubao.service
systemctl enable chrome-deepseek.service

# -----------------------------------------------------------------------------
# 7. Firewall: allow Tailscale; deny public 9222/9223/5900/6080
# -----------------------------------------------------------------------------
if ! ufw status | grep -q "Status: active"; then
  log "configure ufw: allow ssh + tailscale0; block public 5900/6080/9222/9223"
  ufw --force reset >/dev/null 2>&1 || true
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow OpenSSH || ufw allow 22/tcp
  ufw allow in on tailscale0
  # Belt-and-suspenders explicit denials for the operator-facing ports on
  # public interfaces. Tailscale interface allow above wins for tailnet peers.
  ufw deny 5900/tcp || true
  ufw deny 6080/tcp || true
  ufw deny 9222/tcp || true
  ufw deny 9223/tcp || true
  ufw --force enable
else
  log "ufw already active; leaving rules in place"
fi

# -----------------------------------------------------------------------------
# 8. Final banner
# -----------------------------------------------------------------------------
TS_HOSTNAME="$(hostname)"

cat <<BANNER

==== TAILSCALE ====
$(tailscale status 2>/dev/null || echo "Run: sudo tailscale up")

==== VNC PASSWORD ====
${VNC_PW_DISPLAY}
(stored as x11vnc rfbauth blob at ${VNC_PASSWORD_FILE})

==== NEXT STEPS ====
1. sudo tailscale up
   (open the printed URL, authenticate)
2. tailscale ip --4    # note the 100.x.x.x address
   hostname            # note the machine name (e.g. ${TS_HOSTNAME})
3. On your laptop: install Tailscale (https://tailscale.com/download), log
   into the same account, then open in browser:
      http://<tailscale-hostname-or-ip>:6080/vnc.html
   Connect with the VNC password above.
4. ON THE VM (SSH or VNC terminal): start the two Chrome services:
      sudo systemctl start chrome-doubao chrome-deepseek
5. VNC in. In the Doubao Chrome window log into doubao.com (扫码 / SMS).
   In the DeepSeek Chrome window log into chat.deepseek.com. Close any
   onboarding popups so both engines land on the chat page.
6. ON THE VM, verify CDP:
      curl http://127.0.0.1:9222/json/version
      curl http://127.0.0.1:9223/json/version
   Both should return Chrome version JSON.

BANNER

# =============================================================================
# 9. vm_side runtime (Issue #1115) — FastAPI runner + login_watchdog
# =============================================================================
# Appended (do not replace step 8) by Phase 2 work. Provisions a venv for the
# ``vm_side/`` package, installs requirements + playwright chromium, and
# registers two systemd units that start automatically once vm_side/ is
# present at /home/ops/vm_side/.
#
# IDEMPOTENT: a marker file under VM_SIDE_VENV records the mtime of
# requirements.txt that was last installed. If the file's mtime has not
# advanced, pip install is skipped.

VM_SIDE_DIR="${OPS_HOME}/vm_side"
VM_SIDE_VENV="${OPS_HOME}/.venv-vm-side"
VM_SIDE_MARKER="${VM_SIDE_VENV}/.requirements_mtime"
VM_SIDE_PY="${VM_SIDE_VENV}/bin/python"
VM_SIDE_PIP="${VM_SIDE_VENV}/bin/pip"
VM_SIDE_PLAYWRIGHT="${VM_SIDE_VENV}/bin/playwright"

log "ensure python3 + python3-venv for vm_side"
apt-get install -y --no-install-recommends python3 python3-venv python3-pip

if [[ ! -x "${VM_SIDE_PY}" ]]; then
  log "create vm_side venv at ${VM_SIDE_VENV}"
  sudo -u "${OPS_USER}" python3 -m venv "${VM_SIDE_VENV}"
else
  log "vm_side venv already exists at ${VM_SIDE_VENV}"
fi

if [[ -f "${VM_SIDE_DIR}/requirements.txt" ]]; then
  REQ_MTIME="$(stat -c '%Y' "${VM_SIDE_DIR}/requirements.txt" 2>/dev/null || echo 0)"
  LAST_MTIME="$(cat "${VM_SIDE_MARKER}" 2>/dev/null || echo 0)"
  if [[ "${REQ_MTIME}" != "${LAST_MTIME}" ]]; then
    log "install vm_side requirements.txt (mtime ${REQ_MTIME} != marker ${LAST_MTIME})"
    sudo -u "${OPS_USER}" "${VM_SIDE_PIP}" install --upgrade pip
    sudo -u "${OPS_USER}" "${VM_SIDE_PIP}" install -r "${VM_SIDE_DIR}/requirements.txt"
    sudo -u "${OPS_USER}" "${VM_SIDE_PLAYWRIGHT}" install chromium
    echo "${REQ_MTIME}" | sudo -u "${OPS_USER}" tee "${VM_SIDE_MARKER}" >/dev/null
  else
    log "vm_side requirements.txt unchanged since last install — skipping pip"
  fi
else
  log "WARNING: ${VM_SIDE_DIR}/requirements.txt not found — skipping vm_side venv install"
  log "         operator must rsync vm_side/ to ${VM_SIDE_DIR} then re-run this script"
fi

log "write systemd unit: vm-side-runner.service"
cat >/etc/systemd/system/vm-side-runner.service <<EOF
[Unit]
Description=vm_side FastAPI runner (Issue #1115)
After=chrome-doubao.service chrome-deepseek.service network-online.target
Wants=chrome-doubao.service chrome-deepseek.service

[Service]
Type=simple
User=${OPS_USER}
WorkingDirectory=${VM_SIDE_DIR}
Environment=PYTHONPATH=${OPS_HOME}
Environment=VM_SIDE_HOST=127.0.0.1
Environment=VM_SIDE_PORT=7000
ExecStart=${VM_SIDE_PY} -m vm_side runner
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

log "write systemd unit: vm-side-watchdog.service"
cat >/etc/systemd/system/vm-side-watchdog.service <<EOF
[Unit]
Description=vm_side login watchdog + Prometheus gauges (Issue #1115)
After=chrome-doubao.service chrome-deepseek.service network-online.target
Wants=chrome-doubao.service chrome-deepseek.service

[Service]
Type=simple
User=${OPS_USER}
WorkingDirectory=${VM_SIDE_DIR}
Environment=PYTHONPATH=${OPS_HOME}
Environment=VM_SIDE_PROM_PORT=8000
Environment=VM_ID=%H
ExecStart=${VM_SIDE_PY} -m vm_side watchdog
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

if [[ -d "${VM_SIDE_DIR}" && -x "${VM_SIDE_PY}" ]]; then
  log "enable+start vm-side-runner + vm-side-watchdog"
  systemctl enable --now vm-side-runner.service || true
  systemctl enable --now vm-side-watchdog.service || true
else
  log "vm_side/ or venv not ready; enabling units but not starting"
  systemctl enable vm-side-runner.service || true
  systemctl enable vm-side-watchdog.service || true
fi

cat <<BANNER2

==== VM_SIDE RUNTIME (Issue #1115) ====
runner   : ${VM_SIDE_PY} -m vm_side runner   -> 127.0.0.1:7000
watchdog : ${VM_SIDE_PY} -m vm_side watchdog -> Prometheus :8000
Verify   : curl http://127.0.0.1:7000/healthz
Logs     : journalctl -u vm-side-runner -f
           journalctl -u vm-side-watchdog -f

BANNER2

