"""Alembic migration environment.

The application uses async SQLAlchemy URLs (asyncpg / aiosqlite), but Alembic
runs migrations through a sync engine. _sync_url() rewrites the driver portion
so the same DATABASE_URL configured for the FastAPI app can drive migrations.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url(async_url: str) -> str:
    """Convert an async SQLAlchemy URL to its sync equivalent for Alembic.

    Mapping:
      postgresql+asyncpg://...  ->  postgresql+psycopg://...   (psycopg 3)
      sqlite+aiosqlite://...    ->  sqlite://...               (stdlib)

    Any other URL is returned unchanged so users wiring up a sync URL directly
    (e.g. for ad-hoc migrations) are not penalized.
    """
    if async_url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + async_url[len("postgresql+asyncpg://") :]
    if async_url.startswith("sqlite+aiosqlite://"):
        return "sqlite://" + async_url[len("sqlite+aiosqlite://") :]
    return async_url


sync_url = _sync_url(get_settings().database_url)
config.set_main_option("sqlalchemy.url", sync_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to DB and run)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
