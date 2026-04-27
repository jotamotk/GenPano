"""Alembic migration environment.

The application uses async SQLAlchemy URLs (asyncpg / aiosqlite), but Alembic
runs migrations through a sync engine. _sync_url() rewrites the driver portion
so the same DATABASE_URL configured for the FastAPI app can drive migrations.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db._upstream_stubs import UPSTREAM_STUB_NAMES
from app.db.base import Base
from app.models import *  # noqa: F401,F403

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


def include_object(object, name, type_, reflected, compare_to):
    """Filter upstream stub tables out of autogenerate output.

    Stubs are in Base.metadata so SQLAlchemy can resolve ForeignKey
    strings at sort_tables_and_constraints time. But they have no
    real DB representation -- autogenerate's metadata-to-DB diff would
    mark them as 'added table' and write op.create_table for each.

    `include_name` does NOT cover this path (it only fires for
    reflected-but-not-in-metadata names). `include_object` fires on
    BOTH directions and exposes `reflected: bool` to disambiguate:
    - reflected=True: object came from DB inspection
    - reflected=False: object came from target_metadata (our case)

    For our 4 stub tables, we want them excluded regardless of
    direction, so we don't even check `reflected` -- name match alone.
    """
    if type_ == "table" and name in UPSTREAM_STUB_NAMES:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
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
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
