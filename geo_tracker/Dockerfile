FROM python:3.11-slim

# Refs #963 cache-bust 2026-05-17 04:55Z: force fresh build after killing
# zombie alembic / pid 679 (stale idle-in-tx llm_accounts holder) on the
# worker, plus pick up updated QG_PROXY_EXTRACT_URL secret (/get).

# 安装系统依赖（Playwright Chromium + Camoufox Firefox 共用）
# Refs #963: ``tzdata`` is required by Firefox / glibc to resolve named
# timezones like "Asia/Shanghai" — without it, JS
# ``Intl.DateTimeFormat().resolvedOptions().timeZone`` falls back to
# "UTC" regardless of any ``TZ`` env we pass to the Camoufox subprocess.
# Doubao's risk-control reads JS timezone and compares against the
# exit-IP geo; a Chinese qg residential IP paired with a UTC JS timezone
# is the canonical "you're using a proxy" signal, which gets us into
# the silent-rejection state where the page never leaves /home and we
# end up with ``doubao_homepage_content`` failures even though qg +
# block_webrtc are both in place.
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates tzdata \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    libgtk-3-0 libpango-1.0-0 libcairo2 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 设置 PYTHONPATH 让 Python 能找到 geo_tracker 模块
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器 & Camoufox
RUN playwright install chromium
RUN camoufox fetch

# 将当前目录内容复制到 /app/geo_tracker/ 下
# 这样 from geo_tracker.xxx import xxx 就能正常工作
COPY . ./geo_tracker/
