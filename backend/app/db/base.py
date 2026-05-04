"""Backward-compat shim — Base now lives in `genpano_models.base` (ADR-004).

Existing `from app.db.base import Base` imports continue to work via this
re-export. New code should import directly from `genpano_models`.
"""

from genpano_models.base import NAMING_CONVENTION, Base

__all__ = ["NAMING_CONVENTION", "Base"]
