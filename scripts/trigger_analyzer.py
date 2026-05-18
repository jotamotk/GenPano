#!/usr/bin/env python3
"""Enqueue analyze_response celery task for every llm_responses row that
matches a SQL filter (e.g. 'recently-updated bestCoffer-prompt queries').

Runs inside the worker container — has geo_tracker on sys.path.

Env:
  QUERY_FILTER  SQL ILIKE pattern on queries.query_text (default %bestCoffer%)
  COUNT         max number of recent responses to enqueue (default 50)
  TARGET_LLM    queries.target_llm (default doubao)
  DATABASE_URL  set by env_file

Exit code: 0 on success, non-zero on fatal.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "/app")
sys.path.insert(0, "/repo")


async def _main() -> int:
    filter_pat = os.environ.get("QUERY_FILTER", "%bestCoffer%")
    count = int(os.environ.get("COUNT", "50"))
    target_llm = os.environ.get("TARGET_LLM", "doubao")

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not db_url:
        print(json.dumps({"fatal": "no DATABASE_URL"}))
        return 2
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    eng = create_async_engine(db_url, future=True)
    AsyncSessionLocal = sessionmaker(
        bind=eng, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                sa_text(
                    "SELECT r.id, r.query_id, length(r.raw_text) AS chars "
                    "FROM llm_responses r "
                    "JOIN queries q ON q.id = r.query_id "
                    "WHERE q.target_llm = :llm "
                    "  AND q.query_text ILIKE :pat "
                    "ORDER BY r.collected_at DESC NULLS LAST, r.id DESC "
                    "LIMIT :n"
                ),
                {"llm": target_llm, "pat": filter_pat, "n": count},
            )
        ).fetchall()
    if not rows:
        print(json.dumps({"fatal": "no rows in llm_responses for filter"}))
        return 3

    print(json.dumps({"selected": [{"resp_id": int(r[0]), "q_id": int(r[1]), "chars": int(r[2] or 0)} for r in rows]}))

    # Import the celery task and enqueue.
    try:
        from geo_tracker.tasks.celery_tasks import analyze_response
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"fatal": f"cannot import analyze_response: {exc!r}"}))
        return 4

    enqueued = 0
    for r in rows:
        rid = int(r[0])
        try:
            analyze_response.apply_async(args=[rid], queue="analysis")
            enqueued += 1
            print(json.dumps({"enqueued": rid}))
        except Exception as exc:
            print(json.dumps({"id": rid, "error": repr(exc)}))
    print(json.dumps({"summary": {"total": len(rows), "enqueued": enqueued}}))
    return 0 if enqueued == len(rows) else 5


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
