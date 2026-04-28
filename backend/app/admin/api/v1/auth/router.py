"""Aggregate APIRouter for the 6 admin-auth endpoints.

`app/main.py` mounts this once under `/admin/api/v1/auth`. Splitting one
router per endpoint file keeps each handler readable while still giving
us a single mount point.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.admin.api.v1.auth.change_password import router as change_password_router
from app.admin.api.v1.auth.forgot_password import router as forgot_password_router
from app.admin.api.v1.auth.login import router as login_router
from app.admin.api.v1.auth.logout import router as logout_router
from app.admin.api.v1.auth.refresh import router as refresh_router
from app.admin.api.v1.auth.reset_password import router as reset_password_router

router = APIRouter(prefix="/admin/api/v1/auth", tags=["admin-auth"])
router.include_router(login_router)
router.include_router(refresh_router)
router.include_router(logout_router)
router.include_router(forgot_password_router)
router.include_router(reset_password_router)
router.include_router(change_password_router)
