"""Diagnostic — verify admin user exists and bcrypt hash matches."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import bcrypt  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.admin import AdminUser  # noqa: E402


async def _verify() -> int:
    test_password = "Layer3-bootstrap-2026"
    test_email = "frank@genpano.com"

    async with AsyncSessionLocal() as session:
        r = await session.execute(select(AdminUser).where(AdminUser.email == test_email))
        user = r.scalar_one_or_none()
        if user is None:
            print("NO USER FOUND")
            return 1

        print(f"email={user.email}")
        print(f"role={user.role}")
        print(f"status={user.status}")
        print(f"force_password_change_at={user.force_password_change_at}")
        print(f"password_hash[0:20]={user.password_hash[:20]}")
        print(f"password_hash_full_length={len(user.password_hash)}")

        ok = bcrypt.checkpw(
            test_password.encode("utf-8"),
            user.password_hash.encode("utf-8"),
        )
        print(f"bcrypt verify '{test_password}' = {ok}")

    return 0


def main() -> int:
    return asyncio.run(_verify())


if __name__ == "__main__":
    sys.exit(main())
