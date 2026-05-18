# VM-per-account Doubao Chrome container.
#
# One container = one isolated Chrome with persistent profile.
# Designed for running multiple instances on a single Linux host
# (each instance maps to a different host port; profile lives on
# host-mounted volume so login state survives container restart).
#
# Build:   docker compose build
# Run:     docker compose up -d
# See:     experiments/vm_per_account/docker/docker-compose.yml
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:zh \
    LC_ALL=zh_CN.UTF-8

# Single RUN to minimise layers
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg apt-transport-https \
      locales tini iproute2 socat \
      xfce4-session xfce4-panel xfwm4 xfce4-terminal \
      x11vnc novnc websockify \
      xvfb xdotool dbus-x11 x11-utils \
      fonts-wqy-microhei fonts-noto-cjk \
    && locale-gen zh_CN.UTF-8 \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
       | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Persistent Chrome profile mount point
VOLUME ["/profile"]

# Entry script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Defaults — override via docker-compose env
ENV VNC_PASSWORD=changeme \
    CDP_PORT=9222 \
    NOVNC_PORT=6080 \
    CHROME_TARGET_URL=https://www.doubao.com/chat \
    DISPLAY=:0

# Documented ports (actual binding done by docker-compose)
EXPOSE 6080 9222

# tini handles signal forwarding so docker stop is clean
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
