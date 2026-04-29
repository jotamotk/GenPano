"""A1' Step 8 · Group J Harness rule unit tests.

Pattern mirrors the in-tree fixture-driven contract used by the rest of
Group F / D8-D10: each rule gets a positive case (canonical violation)
and a negative case (compliant code). The positive case mirrors what the
self-seeded `__ci_fixtures__/J*_*.cifixture.py` already encodes; the
negative case is hand-written here so we never accidentally accept the
fixture's own pattern as "OK".

Decision references:
- CLAUDE.md #30.I (Step 8 closing loop / .mjs sweep + Group J landing)
- CLAUDE.md #30.H (Path B Variant 2 — round 9 J5 white-list)
- CLAUDE.md #28.A (Platform Layer boundary — J2)
- CLAUDE.md #24 (admin auth + RBAC scaffold — J3)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# `scripts/` is not a package (no __init__.py); add it to sys.path so the
# rule classes import like the selftest does. Cheaper than packaging.
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from ci_check import (  # type: ignore[import-not-found]  # noqa: E402
    J1AdminWriteMustRecordAudit,
    J2AccountPoolRewriteForbidden,
    J3RbacSuperAdminOnly,
    J4CookieMaskInResponse,
    J5UserDataWriteOnlyDeletionRequestedAt,
)


def _write(tmp: Path, rel: str, body: str) -> Path:
    target = tmp / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    # sanity: every fixture body must be syntactically valid Python
    ast.parse(body)
    return target


# ---------------------------------------------------------------------------
# J1 — admin write handler must call record_audit
# ---------------------------------------------------------------------------


def test_j1_positive_handler_without_audit(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/users.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/freeze')\n"
        "async def freeze(user_id: str) -> dict:\n"
        "    return {'user_id': user_id}\n",
    )
    violations = J1AdminWriteMustRecordAudit().scan([src])
    assert len(violations) == 1
    assert violations[0].rule_id == "J1"
    assert "freeze" in violations[0].message


def test_j1_negative_handler_with_audit(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/users.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "\n"
        "async def record_audit(**kw): ...\n"
        "\n"
        "@router.post('/freeze')\n"
        "async def freeze(user_id: str) -> dict:\n"
        "    await record_audit(action='freeze', target_id=user_id)\n"
        "    return {'user_id': user_id}\n",
    )
    assert J1AdminWriteMustRecordAudit().scan([src]) == []


def test_j1_negative_auth_endpoints_whitelisted(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/auth/login.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/login')\n"
        "async def login() -> dict:\n"
        "    return {'ok': True}\n",
    )
    assert J1AdminWriteMustRecordAudit().scan([src]) == []


# ---------------------------------------------------------------------------
# J2 — account pool / luban / cookie-crypto names live only in app/accounts/
# ---------------------------------------------------------------------------


def test_j2_positive_auto_register_outside_accounts(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/services/registration.py",
        "def auto_register(phone: str) -> dict:\n"
        "    return {'status': 'registered'}\n"
        "\n"
        "class CookieEncoder:\n"
        "    def encrypt(self, v: str) -> bytes:\n"
        "        return b''\n",
    )
    violations = J2AccountPoolRewriteForbidden().scan([src])
    assert len(violations) == 2
    rule_ids = {v.rule_id for v in violations}
    assert rule_ids == {"J2"}


def test_j2_negative_inside_accounts_dir(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/accounts/auto_register.py",
        "def auto_register(phone: str) -> dict:\n"
        "    return {}\n"
        "\n"
        "class CookieEncoder:\n"
        "    pass\n",
    )
    assert J2AccountPoolRewriteForbidden().scan([src]) == []


# ---------------------------------------------------------------------------
# J3 — require_role(...) callsite must be the literal 'super_admin'
# ---------------------------------------------------------------------------


def test_j3_positive_non_super_admin_literal(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/staff.py",
        "from fastapi import Depends\n"
        "def require_role(*a): ...\n"
        "_dep = require_role('ops_admin')\n",
    )
    violations = J3RbacSuperAdminOnly().scan([src])
    assert len(violations) == 1
    assert violations[0].rule_id == "J3"


def test_j3_positive_variable_arg(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/staff.py",
        "ROLE = 'super_admin'\n"
        "def require_role(*a): ...\n"
        "_dep = require_role(ROLE)\n",  # not a Constant 'super_admin'
    )
    violations = J3RbacSuperAdminOnly().scan([src])
    assert len(violations) == 1


def test_j3_negative_super_admin_literal(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/users.py",
        "def require_role(*a): ...\n"
        "_dep = require_role('super_admin')\n",
    )
    assert J3RbacSuperAdminOnly().scan([src]) == []


# ---------------------------------------------------------------------------
# J4 — cookies in response must route through mask_secret(...)
# ---------------------------------------------------------------------------


def test_j4_positive_unmasked_cookies_in_dict(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/accounts.py",
        "class _A:\n"
        "    cookies = ''\n"
        "\n"
        "def get_account(a: _A) -> dict:\n"
        "    return {'id': 'x', 'cookies': a.cookies}\n",
    )
    violations = J4CookieMaskInResponse().scan([src])
    assert len(violations) == 1
    assert violations[0].rule_id == "J4"


def test_j4_negative_mask_secret_wrap(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/accounts.py",
        "def mask_secret(v): return '***'\n"
        "class _A:\n"
        "    cookies = ''\n"
        "\n"
        "def get_account(a: _A) -> dict:\n"
        "    return {'id': 'x', 'cookies': mask_secret(a.cookies)}\n",
    )
    assert J4CookieMaskInResponse().scan([src]) == []


# ---------------------------------------------------------------------------
# J5 — admin code may only write users.deletion_requested_at
# ---------------------------------------------------------------------------


def test_j5_positive_password_hash_write(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/users.py",
        "class _U:\n"
        "    password_hash: str = ''\n"
        "\n"
        "def force_rewrite(u: _U) -> None:\n"
        "    u.password_hash = '$2a$12$evil'\n",
    )
    violations = J5UserDataWriteOnlyDeletionRequestedAt().scan([src])
    assert len(violations) == 1
    assert violations[0].rule_id == "J5"
    assert "password_hash" in violations[0].message


def test_j5_negative_deletion_requested_at_only(tmp_path: Path) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/users.py",
        "from datetime import datetime, UTC\n"
        "class _U:\n"
        "    deletion_requested_at = None\n"
        "\n"
        "def soft_delete(u: _U) -> None:\n"
        "    u.deletion_requested_at = datetime.now(UTC)\n",
    )
    assert J5UserDataWriteOnlyDeletionRequestedAt().scan([src]) == []


def test_j5_negative_admin_auth_path_whitelisted(tmp_path: Path) -> None:
    """`app/admin/auth/password.py` writes admin_user.password_hash —
    legitimate (admin self-service password change against AdminUser, not
    User). The whitelist on path keeps the rule from misfiring."""
    src = _write(
        tmp_path,
        "app/admin/auth/password_change.py",
        "class _AdminUser:\n"
        "    password_hash: str = ''\n"
        "\n"
        "def change(admin: _AdminUser, new_hash: str) -> None:\n"
        "    admin.password_hash = new_hash\n",
    )
    assert J5UserDataWriteOnlyDeletionRequestedAt().scan([src]) == []


# ---------------------------------------------------------------------------
# Cross-rule sanity — passing the same compliant file through every J rule
# must produce zero violations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule_cls",
    [
        J1AdminWriteMustRecordAudit,
        J2AccountPoolRewriteForbidden,
        J3RbacSuperAdminOnly,
        J4CookieMaskInResponse,
        J5UserDataWriteOnlyDeletionRequestedAt,
    ],
)
def test_all_j_rules_clean_baseline(tmp_path: Path, rule_cls: type) -> None:
    src = _write(
        tmp_path,
        "app/admin/api/v1/clean.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "async def record_audit(**kw): ...\n"
        "def require_role(role: str): ...\n"
        "def mask_secret(v): return '***'\n"
        "\n"
        "@router.post('/x')\n"
        "async def handler() -> dict:\n"
        "    await record_audit(action='x')\n"
        "    return {}\n",
    )
    rule = rule_cls()
    assert rule.scan([src]) == []
