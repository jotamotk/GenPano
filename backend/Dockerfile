FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PORT=4000

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.4 --trusted-host mirrors.aliyun.com

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY static ./static
# genpano_models is the shared ORM package (ADR-004). It lives next to
# `app/` and is imported as `from genpano_models.x`. Without this COPY
# runtime alembic + uvicorn fail with ModuleNotFoundError on deploy.
COPY genpano_models ./genpano_models

EXPOSE 4000

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-4000}"]
