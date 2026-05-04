"""Phase R.3 / ADR-004 — verify backward-compat shim works after move to
`genpano_models`. New code should import from `genpano_models`, but legacy
imports via `app.models.*` and `app.db.base` must continue to resolve to the
same class objects (no double-defined SQLAlchemy mappers, no metadata drift).
"""

from genpano_models import Base, BrandMention, User
from genpano_models.base import Base as genpano_base

from app.db import base as legacy_base_module
from app.models import (
    Base as legacy_base,
)
from app.models import (
    BrandMention as legacy_brand_mention,
)
from app.models import (
    User as legacy_user,
)


def test_base_is_single_class() -> None:
    """Base must be the SAME class object across all import paths.

    If we accidentally re-defined DeclarativeBase in two places, SQLAlchemy
    would complain about double-mapped tables OR alembic would emit
    drop+recreate ops on every autogenerate run.
    """
    assert legacy_base is Base
    assert genpano_base is Base
    assert legacy_base_module.Base is Base


def test_user_orm_is_single_class() -> None:
    assert legacy_user is User
    assert User.__tablename__ == "users"


def test_brand_mention_orm_is_single_class() -> None:
    assert legacy_brand_mention is BrandMention
    assert BrandMention.__tablename__ == "brand_mentions"


def test_metadata_naming_convention_intact() -> None:
    """The naming convention is critical for stable alembic constraint names.
    If this test fails, every PR with schema changes will produce churn."""
    nc = Base.metadata.naming_convention
    assert nc["pk"] == "pk_%(table_name)s"
    assert nc["fk"] == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    assert nc["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert nc["ck"] == "ck_%(table_name)s_%(constraint_name)s"
    assert nc["ix"] == "ix_%(column_0_label)s"
