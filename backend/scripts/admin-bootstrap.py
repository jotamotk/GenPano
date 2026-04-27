"""Idempotent super_admin seed — Session A0' Step 6.

Creates the first super_admin row from `ADMIN_BOOTSTRAP_EMAIL` +
`ADMIN_BOOTSTRAP_PASSWORD` env. Re-running on a populated DB is a no-op;
detection is by `role='super_admin' AND email=<bootstrap email>`.

Per master decision #24.G: a freshly-seeded super_admin is created with
`force_password_change_at=NOW()`, so the first login funnels through
`/admin/change-password` regardless of whether the bootstrap password was
strong on its own. The Frank-mandated MVP-friendly seed mechanism.

Usage:
    ADMIN_BOOTSTRAP_EMAIL=frank@genpano.com \\
    ADMIN_BOOTSTRAP_PASSWORD='<strong>' \\
    python scripts/admin-bootstrap.py

Exits 0 on success or no-op; non-zero on missing env / DB errors. Re-run is
safe: row count is invariant across calls.

The hyphenated filename matches the spec-aligned invocation surface used by
`verify-session-a0prime.sh`. Direct script invocation (`python scripts/...`)
does not require an importable module name, so the hyphen is fine.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Allow `python scripts/admin-bootstrap.py` from anywhere by ensuring the
# backend root (parent of `scripts/`) is on sys.path before app imports.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.admin.auth.password import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.admin import AdminUser  # noqa: E402


async def _bootstrap_async() -> int:
    email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL")
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    if not email or not password:
        print(
            "ERR: ADMIN_BOOTSTRAP_EMAIL + ADMIN_BOOTSTRAP_PASSWORD must be set",
            file=sys.stderr,
        )
        return 2

    email_normalised = email.strip().lower()

    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(
                select(AdminUser).where(AdminUser.email == email_normalised)
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.role != "super_admin":
                print(
                    f"ERR: row {email_normalised!r} exists but role={existing.role!r}; "
                    "refusing to overwrite",
                    file=sys.stderr,
                )
                return 3
            print(
                f"OK: super_admin {email_normalised!r} already present (no-op)"
            )
            return 0

        now = datetime.now(UTC).replace(tzinfo=None)
        user = AdminUser(
            email=email_normalised,
            password_hash=hash_password(password),
            role="super_admin",
            status="active",
            force_password_change_at=now,
            last_password_at=now,
        )
        session.add(user)
        await session.commit()
        print(
            f"OK: super_admin {email_normalised!r} seeded "
            "(force_password_change_at set; first login must rotate)"
        )
        return 0


def main() -> int:
    return asyncio.run(_bootstrap_async())


if __name__ == "__main__":
    sys.exit(main())
