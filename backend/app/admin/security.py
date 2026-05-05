"""Admin auth dependency.

Phase R.4 stub: returns the current operator if their `User.role == 'paid'`
(treated as admin during migration). Phase 2 will add a real `is_operator`
flag + role-based scope check.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from genpano_models import User

from app.core.errors import forbidden
from app.core.security import current_user


async def current_admin_operator(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> User:
    """Verify caller is an admin operator. 403 otherwise."""
    if user.role != "paid":
        # Phase R.4 stub — treat 'paid' as admin until real role table lands
        raise forbidden("admin only")
    # Stash on request.state for audit decorator
    request.state.user = user
    return user
