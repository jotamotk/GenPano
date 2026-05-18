#!/usr/bin/env python3
"""Bulk-retry N failed BestCoffer (or any filtered) queries through the VM CDP.

Invoked by `.github/workflows/vm-bulk-retry-via-vm.yml` inside the backend
container on ECS. Splits the N queries half/half between doubao-01 (CDP
9222) and doubao-02 (CDP 9223), calls `run_quick_retry` directly so the
HTTP-auth layer is bypassed (we're already inside the backend python
process with DB access).

Refs Epic #1110, Issue #1144.

Env vars:
  BULK_COUNT       integer count (default 20)
  BULK_FILTER      ILIKE pattern on queries.query_text (default %bestCoffer%)
  BULK_LLM         target LLM (default doubao)
  BULK_DRY_RUN     'true' to just list selected ids without running
  DATABASE_URL     SQLAlchemy URL (postgresql:// or postgresql+asyncpg://)

Exit codes:
  0   all selected retries succeeded
  2   DATABASE_URL not set
  3   no candidates matched the filter
  4   run_quick_retry cannot be imported (playwright missing on the host)
  5   one or more retries failed (count<total)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Paths added to sys.path so we can import both the backend's app.* and
# the repo-root geo_tracker.* packages when running inside the docker image.
sys.path.insert(0, "/app")
sys.path.insert(0, "/repo")


async def _main() -> int:
    count = int(os.environ.get("BULK_COUNT", "20"))
    filter_pat = os.environ.get("BULK_FILTER", "%bestCoffer%")
    target_llm = os.environ.get("BULK_LLM", "doubao")
    dry_run = os.environ.get("BULK_DRY_RUN", "false").lower() == "true"
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not db_url:
        print(json.dumps({"fatal": "DATABASE_URL not set in container"}))
        return 2
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    eng = create_async_engine(db_url, future=True)
    AsyncSessionLocal = sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                sa_text(
                    "SELECT id, query_text FROM queries "
                    "WHERE target_llm = :llm "
                    "  AND query_text ILIKE :pat "
                    "  AND status IN ('failed', 'expired', 'pending', 'no_response') "
                    "ORDER BY id DESC "
                    "LIMIT :n"
                ),
                {"llm": target_llm, "pat": filter_pat, "n": count},
            )
        ).fetchall()
    ids = [int(r[0]) for r in rows]
    print(json.dumps({"selected_count": len(ids), "ids": ids}))

    if dry_run:
        return 0

    if not ids:
        print(json.dumps({"fatal": "no matching queries found"}))
        return 3

    try:
        from geo_tracker.agent.vm_quick_retry import run_quick_retry
    except Exception as e:
        print(json.dumps({"fatal": f"cannot import run_quick_retry: {e!r}"}))
        return 4

    half = len(ids) // 2
    # The doubao-NN containers are attached to genpano_default network by
    # the workflow before this script runs, so we can reach them via
    # docker DNS using container name. Internal CDP port is 9222 inside
    # both containers (different external ports are docker-compose port
    # mapping artifacts, not the actual listening port). When we connect
    # via the docker network we bypass the port mapping entirely.
    plan = [(qid, "doubao-01", "http://doubao-01:9222") for qid in ids[:half]] + [
        (qid, "doubao-02", "http://doubao-02:9222") for qid in ids[half:]
    ]

    results: list[dict] = []
    for qid, vm_id, cdp in plan:
        async with AsyncSessionLocal() as session:
            try:
                row = (
                    await session.execute(
                        sa_text("SELECT query_text FROM queries WHERE id = :id"),
                        {"id": qid},
                    )
                ).first()
                if not row:
                    res = {
                        "id": qid,
                        "vm_id": vm_id,
                        "error": "missing_after_select",
                    }
                    results.append(res)
                    print(json.dumps(res))
                    continue
                r = await run_quick_retry(
                    query_id=qid,
                    query_text=row[0],
                    target_llm=target_llm,
                    session=session,
                    cdp_endpoint=cdp,
                    vm_id=vm_id,
                )
                res = {
                    "id": qid,
                    "vm_id": vm_id,
                    "rawText_chars": r.get("raw_text_chars"),
                    "attempt_n": r.get("attempt_n"),
                }
                results.append(res)
                print(json.dumps(res))
            except Exception as e:
                res = {"id": qid, "vm_id": vm_id, "error": repr(e)}
                results.append(res)
                print(json.dumps(res))

    total = len(results)
    success = sum(1 for r in results if not r.get("error"))
    print(json.dumps({"summary": {"total": total, "success": success}}))
    # Match exit code to bulk-mutation outcome (Codex P2 feedback on #1148):
    # the workflow result must reflect that at least one retry failed so
    # operators don't see a green build for a partial-failure run.
    if success < total:
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
