FROM python:3.11-slim

# 安装系统依赖（Playwright Chromium + Camoufox Firefox 共用）
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
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
