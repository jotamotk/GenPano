#!/usr/bin/env bash
# Entrypoint for VM-per-account Doubao Chrome container.
#
# Each container is one isolated Chrome browser + Xvfb display + x11vnc + noVNC.
# The container does not run any business code — it's purely a remote browser
# that the Celery worker on the host (or any Tailscale peer) drives over CDP.
#
# Persistent state (cookies / login session / localStorage) lives in /profile
# which is mounted as a docker volume — survives container restart.
set -euo pipefail

: "${VNC_PASSWORD:?must set VNC_PASSWORD env}"
: "${CDP_PORT:=9222}"
: "${NOVNC_PORT:=6080}"
: "${CHROME_TARGET_URL:=https://www.doubao.com/chat}"
: "${DISPLAY:=:0}"
export DISPLAY
# Chrome 116+ silently ignores --remote-debugging-address=0.0.0.0 and only
# binds CDP to 127.0.0.1 inside this container. We expose CDP externally by
# running socat as a sidecar: Chrome listens on this internal loopback port,
# socat listens on the container's external CDP_PORT and forwards. The
# extra hop means Chrome sees 127.0.0.1 as the source IP and accepts the
# request instead of TCP-resetting it as a DNS-rebinding attempt.
: "${CDP_INTERNAL_PORT:=9322}"

# Clean up stale X server lock + socket. Without this, Xvfb refuses to
# start with "Server is already active for display 0" — these files can
# be baked into the image by package post-install hooks (xfce4-session /
# mesa) running a transient X server during apt-get, or be left over if
# a previous container instance died mid-startup.
rm -f /tmp/.X0-lock /tmp/.X11-unix/X0 2>/dev/null || true

# Workaround: docker mounted /profile may be owned by root; chrome needs rw
mkdir -p /profile
chmod 0700 /profile

# ---- 1. VNC password storage ----
mkdir -p /root/.vnc
x11vnc -storepasswd "$VNC_PASSWORD" /root/.vnc/passwd
chmod 0600 /root/.vnc/passwd

# ---- 2. Xvfb on :0 ----
echo "[entrypoint] starting Xvfb on $DISPLAY ..."
Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp \
  > /var/log/xvfb.log 2>&1 &

# Wait for display socket
for i in $(seq 1 20); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
# Do NOT pipe xdpyinfo into `head` — `head` closes the pipe after a few
# lines and the SIGPIPE return code propagates under `set -o pipefail`,
# making this look like an Xvfb failure when it actually succeeded.
if ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
  echo "[entrypoint] FATAL: Xvfb never came up; xvfb.log:"
  cat /var/log/xvfb.log
  exit 1
fi
echo "[entrypoint] Xvfb is up on $DISPLAY"

# ---- 3. Xfce desktop ----
echo "[entrypoint] starting Xfce ..."
dbus-launch --exit-with-session startxfce4 \
  > /var/log/xfce.log 2>&1 &
sleep 5

# ---- 4. Chrome (persistent /profile, CDP on internal loopback port) ----
echo "[entrypoint] starting Chrome (CDP internal=$CDP_INTERNAL_PORT, external via socat=$CDP_PORT, profile=/profile)..."
# Chrome 116+ refuses to listen on non-loopback for CDP. Bind to localhost
# only; socat below exposes it on $CDP_PORT.
google-chrome \
  --user-data-dir=/profile \
  --remote-debugging-port="$CDP_INTERNAL_PORT" \
  --remote-allow-origins=* \
  --no-sandbox --no-first-run --no-default-browser-check \
  --disable-blink-features=AutomationControlled \
  --disable-dev-shm-usage \
  --window-size=1920,1080 \
  "$CHROME_TARGET_URL" \
  > /var/log/chrome.log 2>&1 &

# Wait for Chrome's internal CDP to come up
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$CDP_INTERNAL_PORT/json/version" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -sf "http://127.0.0.1:$CDP_INTERNAL_PORT/json/version" >/dev/null || {
  echo "[entrypoint] WARN: Chrome CDP not yet reachable on internal port $CDP_INTERNAL_PORT; chrome.log:"
  tail -20 /var/log/chrome.log
}
echo "[entrypoint] Chrome CDP up on internal 127.0.0.1:$CDP_INTERNAL_PORT"

# ---- 4b. socat bridge: external $CDP_PORT (0.0.0.0) -> Chrome 127.0.0.1:$CDP_INTERNAL_PORT ----
echo "[entrypoint] starting socat CDP bridge: 0.0.0.0:$CDP_PORT -> 127.0.0.1:$CDP_INTERNAL_PORT"
socat TCP-LISTEN:"$CDP_PORT",reuseaddr,fork TCP:127.0.0.1:"$CDP_INTERNAL_PORT" \
  > /var/log/socat-cdp.log 2>&1 &
for i in $(seq 1 10); do
  if ss -tln 2>/dev/null | grep -q ":$CDP_PORT "; then break; fi
  sleep 0.5
done

# ---- 5. x11vnc binds to Xvfb display ----
echo "[entrypoint] starting x11vnc ..."
x11vnc -display "$DISPLAY" -forever -shared \
  -rfbauth /root/.vnc/passwd \
  > /var/log/x11vnc.log 2>&1 &

# Wait for VNC socket 5900
for i in $(seq 1 20); do
  if ss -tln | grep -q ':5900 '; then break; fi
  sleep 0.5
done

# ---- 6. websockify (noVNC) — foreground, keeps container alive ----
echo "[entrypoint] starting websockify on $NOVNC_PORT (Connect via noVNC)..."
exec websockify --web /usr/share/novnc "0.0.0.0:$NOVNC_PORT" "localhost:5900"
