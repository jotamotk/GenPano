"""GENPANO Session A1' Phase Gate Layer 2 — admin endpoints curl-style smoke.

Boots the FastAPI admin app inside a single Python process, wires it to an
in-memory aiosqlite engine that has the full Module A + Module C surface
seeded, and walks the 8-step Frank-style smoke sequence (login → users
list → freeze → soft-delete → kg alias list → resolve → submissions inbox
→ approve). Each step prints a `[Sx] PASS / FAIL` line so failures land
exactly where Frank can see them.

Why an in-process runner instead of curl + uvicorn:
  - Step 11 §5 row mandates Layer 2 reuse the per-test aiosqlite stack
    (decision #25 Rule 1 / #30 J5). Real curl needs a running uvicorn +
    SQLite file + admin-bootstrap dance Frank doesn't want to re-run by
    hand. ASGITransport(app=app) gives identical HTTP semantics to curl
    while staying single-process.
  - Decision #29.C horizontal: 'every Session ends with a click-through
    artefact'. This script IS that click-through for the API surface;
    Layer 3 SESSION_A1_PRIME_LAYER3_CHECKLIST.md is the browser slice.

Decision references:
- CLAUDE.md #30.H (alias_conflicts.candidate_ids N-候选 invariant)
- CLAUDE.md #30.J (Module C admin-side scope cut to alias / submissions)
- CLAUDE.md #24.E (admin runtime + JWT + cookies)
- ADMIN_PRD §4.1 / §4.3
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("ADMIN_JWT_SECRET", "x" * 64)
os.environ.setdefault("ADMIN_BOOTSTRAP_EMAIL", "smoke-admin-a1@example.com")
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "Smoke-A1prime-Strong-9!")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import Table  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.admin.auth.password import hash_password  # noqa: E402
from app.admin.auth.rate_limiter import reset_for_tests  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.admin import (  # noqa: E402
    AdminLoginAttempt,
    AdminPasswordReset,
    AdminSession,
    AdminUser,
    AdminUserModerationAction,
    AliasConflict,
    BrandSubmission,
    KgReviewQueue,
)
from app.models.user import User  # noqa: E402

_TABLES: list[Table] = [
    cast(Table, AdminUser.__table__),
    cast(Table, AdminSession.__table__),
    cast(Table, AdminPasswordReset.__table__),
    cast(Table, AdminLoginAttempt.__table__),
    cast(Table, User.__table__),
    cast(Table, AdminUserModerationAction.__table__),
    cast(Table, AliasConflict.__table__),
    cast(Table, BrandSubmission.__table__),
    cast(Table, KgReviewQueue.__table__),
]

ADMIN_EMAIL = "smoke-admin-a1@example.com"
ADMIN_PASSWORD = "Smoke-A1prime-Strong-9!"


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SmokeFailure(SystemExit):
    def __init__(self, step: str, detail: str) -> None:
        super().__init__(f"[FAIL] {step}: {detail}")


def _expect(step: str, condition: bool, detail: str) -> None:
    if not condition:
        raise SmokeFailure(step, detail)
    print(f"[{step}] PASS")


async def _seed(sessionmaker: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    """Seed: super_admin + 1 user + 1 pending alias_conflict + 1 pending submission.

    Returns the IDs needed by the smoke sequence so we don't round-trip
    them through HTTP only to assert their value back.
    """
    async with sessionmaker() as session:
        admin = AdminUser(
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            role="super_admin",
            status="active",
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

        user = User(
            email="smoke-user@example.com",
            name_zh="冒烟用户",
            name_en="Smoke User",
        )
        session.add(user)

        alias = AliasConflict(
            alias_value="LV",
            language="en",
            candidate_ids=["brand-louis-vuitton", "brand-las-vegas"],
        )
        session.add(alias)

        submission = BrandSubmission(
            brand_name_zh="花西子",
            brand_name_en="Florasis",
            aliases=["Hua Xi Zi"],
            status="pending",
            sla_started_at=_utc_naive_now() - timedelta(hours=2),
        )
        session.add(submission)

        await session.commit()
        await session.refresh(user)
        await session.refresh(alias)
        await session.refresh(submission)

        return {
            "admin_id": admin.id,
            "user_id": user.id,
            "alias_id": alias.id,
            "submission_id": submission.id,
            "alias_resolve_target": "brand-louis-vuitton",
        }


async def _run() -> None:
    reset_for_tests()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        for table in _TABLES:
            await conn.run_sync(table.create)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    try:
        seeds = await _seed(sessionmaker)
        print("==============================================")
        print("GENPANO Session A1' Layer 2 admin smoke")
        print("==============================================")
        print(f"  super_admin email = {ADMIN_EMAIL}")
        print(f"  user_id           = {seeds['user_id']}")
        print(f"  alias_id          = {seeds['alias_id']}")
        print(f"  submission_id     = {seeds['submission_id']}")
        print("")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # ----------------------------------------------------------
            # S1 POST /admin/api/v1/auth/login → 200 + access cookie
            # ----------------------------------------------------------
            res = await client.post(
                "/admin/api/v1/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            _expect("S1.login.status", res.status_code == 200, f"got {res.status_code}: {res.text}")
            _expect(
                "S1.login.cookie",
                "admin_access_token" in client.cookies,
                f"no admin_access_token cookie set; cookies={dict(client.cookies)}",
            )

            # ----------------------------------------------------------
            # S2 GET /admin/api/v1/users → 200 + items[0] is our seed
            # ----------------------------------------------------------
            res = await client.get("/admin/api/v1/users")
            _expect(
                "S2.users.list.status", res.status_code == 200, f"got {res.status_code}: {res.text}"
            )
            body = res.json()
            _expect(
                "S2.users.list.total",
                body["total"] >= 1,
                f"expected total>=1 got {body['total']}",
            )
            _expect(
                "S2.users.list.contains_seed",
                any(item["id"] == seeds["user_id"] for item in body["items"]),
                f"seed user_id {seeds['user_id']} not in items={body['items']}",
            )

            # ----------------------------------------------------------
            # S3 POST /admin/api/v1/users/{user_id}/freeze → 200
            # Decision #30.H Y3: writes user_moderation_actions, NOT users.status
            # ----------------------------------------------------------
            res = await client.post(
                f"/admin/api/v1/users/{seeds['user_id']}/freeze",
                json={"reason": "smoke abuse trigger", "expires_at": None},
            )
            _expect(
                "S3.freeze.status", res.status_code == 200, f"got {res.status_code}: {res.text}"
            )
            body = res.json()
            _expect(
                "S3.freeze.action",
                body.get("action") == "freeze",
                f"expected action=freeze got {body}",
            )

            # ----------------------------------------------------------
            # S4 GET /{user_id} → is_frozen now True (derived)
            # ----------------------------------------------------------
            res = await client.get(f"/admin/api/v1/users/{seeds['user_id']}")
            _expect(
                "S4.detail.status", res.status_code == 200, f"got {res.status_code}: {res.text}"
            )
            body = res.json()
            _expect(
                "S4.detail.is_frozen",
                body.get("is_frozen") is True,
                f"expected is_frozen=True after S3 got {body}",
            )

            # ----------------------------------------------------------
            # S5 DELETE /admin/api/v1/users/{user_id} → 200, soft-delete
            # Decision #30.H Y5: writes users.deletion_requested_at + moderation row
            # ----------------------------------------------------------
            res = await client.request(
                "DELETE",
                f"/admin/api/v1/users/{seeds['user_id']}",
                json={"reason": "smoke gdpr request"},
            )
            _expect(
                "S5.softdelete.status",
                res.status_code == 200,
                f"got {res.status_code}: {res.text}",
            )
            body = res.json()
            _expect(
                "S5.softdelete.action",
                body.get("action") == "soft_delete",
                f"expected action=soft_delete got {body}",
            )

            # ----------------------------------------------------------
            # S6 GET /admin/api/v1/kg/alias-conflicts → 200 + seed present
            # ----------------------------------------------------------
            res = await client.get("/admin/api/v1/kg/alias-conflicts")
            _expect(
                "S6.alias.list.status",
                res.status_code == 200,
                f"got {res.status_code}: {res.text}",
            )
            body = res.json()
            _expect(
                "S6.alias.list.contains_seed",
                any(item["id"] == seeds["alias_id"] for item in body["items"]),
                f"seed alias_id {seeds['alias_id']} not in items={body['items']}",
            )

            # ----------------------------------------------------------
            # S7 POST /alias-conflicts/{id}/resolve → 200, N-候选 invariant
            # Decision #30.H — resolved_to_id MUST be in candidate_ids
            # ----------------------------------------------------------
            res = await client.post(
                f"/admin/api/v1/kg/alias-conflicts/{seeds['alias_id']}/resolve",
                json={"resolved_to_id": seeds["alias_resolve_target"]},
            )
            _expect(
                "S7.alias.resolve.status",
                res.status_code == 200,
                f"got {res.status_code}: {res.text}",
            )
            body = res.json()
            _expect(
                "S7.alias.resolve.target",
                body.get("resolved_to_id") == seeds["alias_resolve_target"],
                f"expected resolved_to_id={seeds['alias_resolve_target']} got {body}",
            )

            # ----------------------------------------------------------
            # S7b N-候选 invariant negative: resolve to id NOT in candidates
            # MUST 422 (round 9 / #30.H — invariant guarded at endpoint layer)
            # ----------------------------------------------------------
            # (alias is already resolved, so verify a fresh one)
            async with sessionmaker() as session:
                fresh_alias = AliasConflict(
                    alias_value="DG",
                    language="en",
                    candidate_ids=["brand-dolce-gabbana", "brand-dragon-game"],
                )
                session.add(fresh_alias)
                await session.commit()
                await session.refresh(fresh_alias)
                fresh_id = fresh_alias.id

            res = await client.post(
                f"/admin/api/v1/kg/alias-conflicts/{fresh_id}/resolve",
                json={"resolved_to_id": "brand-not-a-candidate"},
            )
            _expect(
                "S7b.alias.resolve.invariant",
                res.status_code in {400, 422},
                f"expected 400/422 for non-candidate target, got {res.status_code}: {res.text}",
            )

            # ----------------------------------------------------------
            # S8 GET /admin/api/v1/kg/submissions → 200 + seed present
            # ----------------------------------------------------------
            res = await client.get("/admin/api/v1/kg/submissions")
            _expect(
                "S8.submissions.list.status",
                res.status_code == 200,
                f"got {res.status_code}: {res.text}",
            )
            body = res.json()
            _expect(
                "S8.submissions.list.contains_seed",
                any(item["id"] == seeds["submission_id"] for item in body["items"]),
                f"seed submission_id {seeds['submission_id']} not in items={body['items']}",
            )

            # ----------------------------------------------------------
            # S9 POST /submissions/{id}/approve → 200, status pending → approved
            # ----------------------------------------------------------
            res = await client.post(
                f"/admin/api/v1/kg/submissions/{seeds['submission_id']}/approve",
                json={"reason": "smoke approval"},
            )
            _expect(
                "S9.submission.approve.status",
                res.status_code == 200,
                f"got {res.status_code}: {res.text}",
            )
            body = res.json()
            _expect(
                "S9.submission.approve.action",
                body.get("action") == "approve",
                f"expected action=approve got {body}",
            )

        print("")
        print("==============================================")
        print("Layer 2 admin smoke: GREEN (9 / 9 step pass)")
        print("==============================================")

    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
        reset_for_tests()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
