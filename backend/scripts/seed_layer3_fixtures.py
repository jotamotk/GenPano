"""Layer 3 walkthrough fixtures — Session A1' Phase Gate Layer 3.

Idempotent seeds for Frank's browser walkthrough:
- 1 user (smoke-user@example.com) — Module A users list/detail
- 1 alias_conflicts (alias_value='苹果', 2 candidate UUIDs) — Module C KG aliases
- 1 brand_submission (brand_name_zh='花西子', sla_started_at = NOW - 2h, pending) — Module C KG submissions

Re-run is safe (lookup-by-natural-key + skip-if-exists pattern).

Usage (inside docker container):
    uv run python scripts/seed_layer3_fixtures.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.admin import AliasConflict, BrandSubmission  # noqa: E402
from app.models.user import User  # noqa: E402


SEED_USER_EMAIL = "smoke-user@example.com"
SEED_ALIAS_VALUE = "苹果"
SEED_BRAND_NAME_ZH = "花西子"


async def _seed_async() -> int:
    async with AsyncSessionLocal() as session:
        # 1 · user
        existing_user = (
            await session.execute(select(User).where(User.email == SEED_USER_EMAIL))
        ).scalar_one_or_none()
        if existing_user is None:
            user = User(
                email=SEED_USER_EMAIL,
                name_zh="冒烟测试用户",
                name_en="Smoke Test User",
                preferences={},
            )
            session.add(user)
            await session.flush()
            user_id = user.id
            print(f"OK: user seeded id={user_id} email={SEED_USER_EMAIL}")
        else:
            user_id = existing_user.id
            print(f"OK: user already present id={user_id} email={SEED_USER_EMAIL} (no-op)")

        # 2 · alias_conflict (alias_value='苹果' + zh, 2 candidate UUIDs)
        existing_alias = (
            await session.execute(
                select(AliasConflict).where(
                    AliasConflict.alias_value == SEED_ALIAS_VALUE,
                    AliasConflict.language == "zh",
                )
            )
        ).scalar_one_or_none()
        if existing_alias is None:
            candidate_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
            alias = AliasConflict(
                alias_value=SEED_ALIAS_VALUE,
                language="zh",
                candidate_ids=candidate_ids,
            )
            session.add(alias)
            await session.flush()
            alias_id = alias.id
            print(
                f"OK: alias_conflict seeded id={alias_id} alias_value={SEED_ALIAS_VALUE!r} "
                f"candidates={candidate_ids}"
            )
        else:
            alias_id = existing_alias.id
            print(
                f"OK: alias_conflict already present id={alias_id} "
                f"alias_value={SEED_ALIAS_VALUE!r} (no-op)"
            )

        # 3 · brand_submission (brand_name_zh='花西子', sla_started_at = NOW - 2h, pending)
        existing_sub = (
            await session.execute(
                select(BrandSubmission).where(BrandSubmission.brand_name_zh == SEED_BRAND_NAME_ZH)
            )
        ).scalar_one_or_none()
        if existing_sub is None:
            sla_started = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
            sub = BrandSubmission(
                brand_name_zh=SEED_BRAND_NAME_ZH,
                brand_name_en="Florasis",
                aliases=["Florasis", "花西子"],
                status="pending",
                sla_started_at=sla_started,
            )
            session.add(sub)
            await session.flush()
            sub_id = sub.id
            print(
                f"OK: brand_submission seeded id={sub_id} brand_name_zh={SEED_BRAND_NAME_ZH!r} "
                f"sla_started_at={sla_started.isoformat()} status=pending"
            )
        else:
            sub_id = existing_sub.id
            print(
                f"OK: brand_submission already present id={sub_id} "
                f"brand_name_zh={SEED_BRAND_NAME_ZH!r} (no-op)"
            )

        await session.commit()

        print()
        print("=== Layer 3 Fixture IDs ===")
        print(f"user_id           = {user_id}")
        print(f"alias_conflict_id = {alias_id}")
        print(f"brand_submission_id = {sub_id}")

    return 0


def main() -> int:
    return asyncio.run(_seed_async())


if __name__ == "__main__":
    sys.exit(main())
