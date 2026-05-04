"""Backward-compat shim — see `genpano_models.user` (ADR-004)."""

from genpano_models.user import User, UserAuthToken

__all__ = ["User", "UserAuthToken"]
