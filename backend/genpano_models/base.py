"""Shared SQLAlchemy DeclarativeBase for the entire GenPano stack.

ADR-004: this is the single source of truth for the ORM `Base` class. backend,
geo_tracker (Phase R.4 follow-up), and admin (after merging into backend) all
import `Base` from here.

The naming convention is critical: it ensures alembic-generated constraint
names are stable across environments.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
