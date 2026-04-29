"""Clear Layer 3 fixtures (idempotent) — for migration roundtrip testing."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402


async def _clear() -> int:
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM brand_submissions"))
        await session.execute(text("DELETE FROM alias_conflicts"))
        await session.execute(text("DELETE FROM users"))
        await session.commit()
        print("OK: cleared brand_submissions / alias_conflicts / users")
    return 0


def main() -> int:
    return asyncio.run(_clear())


if __name__ == "__main__":
    sys.exit(main())
