"""Admin API routes (Phase R.4 — migration target from admin_console Flask).

13 sub-routers per ADR-001:
  session, brands, topic_plan, prompt_matrix, query_pool, scheduler,
  segments, profiles, accounts, users, analyzer, artifacts, stats

Each sub-router is a stub initially; subsequent PRs migrate routes from
`admin_console/app.py` (15391 LOC Flask) to FastAPI.
"""

from app.api.admin.router import router

__all__ = ["router"]
