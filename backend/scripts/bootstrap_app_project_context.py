"""Dry-run-safe App project bootstrap helper for issue #492.

Default use is read-only:

    cd backend
    python scripts/bootstrap_app_project_context.py

Production writes are gated and require all of:

    --write --user-id <app-user-uuid> --approval-ref <github-approval-url-or-note>

The helper is intentionally narrow: it only creates/reuses the App project row
and idempotent project_competitors pins needed for a project-scoped App API
context. It does not repair analyzer facts, Backend API contracts, frontend
rendering, migrations, or CI/CD behavior.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402

DEFAULT_BRAND_ID = 12
DEFAULT_PROJECT_NAME = "Estee Lauder / 雅诗兰黛 App Analytics"
DEFAULT_PROJECT_SLUG = "estee-lauder-first-slice"
DEFAULT_COMPETITOR_BRAND_IDS = [2]
DEFAULT_COMPETITOR_POLICY = (
    "minimum evidence-based first slice: pin only brands with read-only diagnostics evidence "
    "for the Estee path; current production diagnostics point to source owner brand_id=2"
)
DEFAULT_ALIASES = ["雅诗兰黛", "Estee Lauder", "Estée Lauder"]


def stable_project_id(*, brand_id: int, project_slug: str) -> str:
    """Return a deterministic UUID-shaped target for repeatable dry-run/write handoff."""
    key = f"https://github.com/jotamotk/X/issues/492#brand={brand_id};project={project_slug}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def validate_write_gate(*, write: bool, user_id: str | None, approval_ref: str | None) -> None:
    if not write:
        return
    if not user_id:
        raise ValueError("--write requires --user-id; do not choose a production owner implicitly")
    if not approval_ref:
        raise ValueError("--write requires --approval-ref recorded on #492 or #481")


def validate_plan_can_write(plan: dict[str, Any]) -> None:
    if plan.get("write_requested") and plan.get("blockers"):
        raise ValueError(f"plan has blockers: {plan['blockers']}")


def _unique_ints(values: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _rollback_sql(
    *,
    project_id: str,
    primary_brand_id: int,
    competitor_brand_ids: Sequence[int],
    created_project: bool,
) -> str:
    lines: list[str] = []
    if competitor_brand_ids:
        brand_ids = ", ".join(str(v) for v in competitor_brand_ids)
        lines.append(
            "DELETE FROM project_competitors "
            f"WHERE project_id = '{project_id}' AND brand_id IN ({brand_ids});"
        )
    if created_project:
        lines.append(
            "DELETE FROM projects "
            f"WHERE id = '{project_id}' AND primary_brand_id = {primary_brand_id};"
        )
    if not lines:
        return "-- no rollback needed; dry-run found no pending project context changes"
    return "\n".join(lines)


def build_plan(
    *,
    brand_id: int,
    user_id: str | None,
    project_name: str,
    project_id: str,
    industry_id: int | None,
    competitor_brand_ids: Sequence[int],
    existing_project: dict[str, Any] | None,
    existing_competitor_brand_ids: set[int],
    write: bool,
    approval_ref: str | None,
) -> dict[str, Any]:
    validate_write_gate(write=write, user_id=user_id, approval_ref=approval_ref)

    competitor_ids = [v for v in _unique_ints(competitor_brand_ids) if v != brand_id]
    if existing_project:
        chosen_project_id = str(existing_project["id"])
        chosen_user_id = str(existing_project["user_id"])
        chosen_project_name = str(existing_project["name"])
        chosen_industry_id = existing_project.get("industry_id")
        created_project = False
    else:
        chosen_project_id = project_id
        chosen_user_id = user_id
        chosen_project_name = project_name
        chosen_industry_id = industry_id
        created_project = True

    missing_competitors = [
        brand_id for brand_id in competitor_ids if brand_id not in existing_competitor_brand_ids
    ]

    actions: list[dict[str, Any]] = []
    if created_project:
        actions.append(
            {
                "type": "create_project",
                "project_id": chosen_project_id,
                "primary_brand_id": brand_id,
                "user_id": chosen_user_id,
            }
        )
    for competitor_brand_id in missing_competitors:
        actions.append(
            {
                "type": "insert_project_competitor",
                "project_id": chosen_project_id,
                "brand_id": competitor_brand_id,
            }
        )

    blockers: list[str] = []
    if created_project and not chosen_user_id:
        blockers.append("creation requires an approved production App user_id owner")

    return {
        "dry_run": not write,
        "write_requested": write,
        "approval_ref": approval_ref,
        "project_id": chosen_project_id,
        "user_id": chosen_user_id,
        "project_name": chosen_project_name,
        "industry_id": chosen_industry_id,
        "primary_brand_id": brand_id,
        "competitor_brand_ids": competitor_ids,
        "competitor_policy": DEFAULT_COMPETITOR_POLICY,
        "existing_project_found": bool(existing_project),
        "actions": actions,
        "blockers": blockers,
        "rollback_sql": _rollback_sql(
            project_id=chosen_project_id,
            primary_brand_id=brand_id,
            competitor_brand_ids=missing_competitors,
            created_project=created_project,
        ),
    }


async def _fetch_mappings(
    session: AsyncSession, sql: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    result = await session.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


def _project_search_clause(aliases: Sequence[str]) -> tuple[str, dict[str, str]]:
    params: dict[str, str] = {}
    clauses = []
    for idx, alias in enumerate(aliases):
        key = f"alias_{idx}"
        params[key] = f"%{alias}%"
        clauses.append(f"LOWER(COALESCE(name, '')) LIKE LOWER(:{key})")
    if not clauses:
        return "FALSE", {}
    return " OR ".join(clauses), params


async def inspect_context(
    session: AsyncSession,
    *,
    brand_id: int,
    project_id: str,
    aliases: Sequence[str],
) -> dict[str, Any]:
    brand_rows = await _fetch_mappings(
        session,
        """
        SELECT id, name, name_zh, name_en
        FROM brands
        WHERE id = :brand_id
        """,
        {"brand_id": brand_id},
    )

    name_clause, alias_params = _project_search_clause(aliases)
    project_rows = await _fetch_mappings(
        session,
        f"""
        SELECT id, user_id, name, industry_id, primary_brand_id, is_active, deleted_at
        FROM projects
        WHERE id = :project_id
           OR primary_brand_id = :brand_id
           OR ({name_clause})
        ORDER BY deleted_at NULLS FIRST, primary_brand_id DESC NULLS LAST, name
        LIMIT 25
        """,
        {"brand_id": brand_id, "project_id": project_id, **alias_params},
    )

    target_as_competitor_rows = await _fetch_mappings(
        session,
        """
        SELECT pc.project_id, pc.brand_id, p.user_id, p.name, p.primary_brand_id
        FROM project_competitors pc
        JOIN projects p ON p.id = pc.project_id
        WHERE pc.brand_id = :brand_id
          AND p.deleted_at IS NULL
        ORDER BY p.name
        LIMIT 25
        """,
        {"brand_id": brand_id},
    )

    return {
        "brand_rows": brand_rows,
        "project_rows": project_rows,
        "target_as_competitor_rows": target_as_competitor_rows,
    }


def choose_existing_project(
    *, project_rows: Sequence[dict[str, Any]], brand_id: int, project_id: str
) -> dict[str, Any] | None:
    exact = [
        row
        for row in project_rows
        if row.get("id") == project_id and _is_intended_active_project(row, brand_id)
    ]
    if exact:
        return exact[0]
    primary = [
        row
        for row in project_rows
        if row.get("primary_brand_id") == brand_id and _is_intended_active_project(row, brand_id)
    ]
    if len(primary) == 1:
        return primary[0]
    return None


def _is_intended_active_project(row: dict[str, Any], brand_id: int) -> bool:
    return (
        row.get("primary_brand_id") == brand_id
        and row.get("deleted_at") is None
        and row.get("is_active") is not False
    )


def add_context_safety_notes(
    plan: dict[str, Any],
    *,
    context: dict[str, Any],
    existing_project: dict[str, Any] | None,
    brand_id: int,
) -> None:
    notes: list[str] = []
    blockers: list[str] = plan.setdefault("blockers", [])

    if not context["brand_rows"]:
        blockers.append(f"target brand_id={brand_id} was not found in brands")

    exact_project_rows = [
        row for row in context["project_rows"] if row.get("id") == plan["project_id"]
    ]
    unsafe_project_id_collisions = [
        row for row in exact_project_rows if not _is_intended_active_project(row, brand_id)
    ]
    if unsafe_project_id_collisions:
        blockers.append(
            f"project_id collision for {plan['project_id']} is not an active "
            f"primary_brand_id={brand_id} context"
        )

    active_projects = [row for row in context["project_rows"] if row.get("deleted_at") is None]
    primary_projects = [row for row in active_projects if row.get("primary_brand_id") == brand_id]
    if existing_project is None and len(primary_projects) > 1:
        blockers.append(
            f"multiple active projects already use primary_brand_id={brand_id}; "
            "choose one explicitly"
        )

    conflicting_name_projects = [
        row
        for row in active_projects
        if row.get("primary_brand_id") != brand_id and row.get("id") != plan["project_id"]
    ]
    if conflicting_name_projects:
        blockers.append(
            "project name/id search found active non-primary candidates; review before creating a "
            "new primary brand project"
        )

    if context["target_as_competitor_rows"]:
        notes.append(
            "target brand appears as a competitor in existing projects; those rows are not reused "
            "as the primary App project context"
        )

    plan["notes"] = notes


async def fetch_existing_competitors(session: AsyncSession, *, project_id: str) -> set[int]:
    rows = await _fetch_mappings(
        session,
        """
        SELECT brand_id
        FROM project_competitors
        WHERE project_id = :project_id
        """,
        {"project_id": project_id},
    )
    return {int(row["brand_id"]) for row in rows}


async def apply_plan(session: AsyncSession, plan: dict[str, Any]) -> None:
    if not plan["write_requested"]:
        return
    validate_plan_can_write(plan)
    for action in plan["actions"]:
        if action["type"] == "create_project":
            await session.execute(
                text(
                    """
                    INSERT INTO projects (
                        id, user_id, name, industry_id, primary_brand_id, is_active,
                        created_at, updated_at
                    )
                    VALUES (
                        :project_id, :user_id, :project_name, :industry_id, :brand_id,
                        TRUE, NOW(), NOW()
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "project_id": plan["project_id"],
                    "user_id": plan["user_id"],
                    "project_name": plan["project_name"],
                    "industry_id": plan["industry_id"],
                    "brand_id": plan["primary_brand_id"],
                },
            )
        elif action["type"] == "insert_project_competitor":
            await session.execute(
                text(
                    """
                    INSERT INTO project_competitors (project_id, brand_id, pinned_by, pinned_at)
                    VALUES (:project_id, :brand_id, :user_id, NOW())
                    ON CONFLICT (project_id, brand_id) DO NOTHING
                    """
                ),
                {
                    "project_id": action["project_id"],
                    "brand_id": action["brand_id"],
                    "user_id": plan["user_id"],
                },
            )
    await session.commit()


async def run(args: argparse.Namespace) -> dict[str, Any]:
    project_id = args.project_id or stable_project_id(
        brand_id=args.brand_id, project_slug=args.project_slug
    )
    validate_write_gate(write=args.write, user_id=args.user_id, approval_ref=args.approval_ref)

    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    brand_aliases = _unique_strings([args.project_name, *args.brand_alias])
    try:
        async with session_factory() as session:
            context = await inspect_context(
                session,
                brand_id=args.brand_id,
                project_id=project_id,
                aliases=brand_aliases,
            )
            existing_project = choose_existing_project(
                project_rows=context["project_rows"],
                brand_id=args.brand_id,
                project_id=project_id,
            )
            existing_competitors = (
                await fetch_existing_competitors(session, project_id=str(existing_project["id"]))
                if existing_project
                else set()
            )
            plan = build_plan(
                brand_id=args.brand_id,
                user_id=args.user_id,
                project_name=args.project_name,
                project_id=project_id,
                industry_id=args.industry_id,
                competitor_brand_ids=args.competitor_brand_id,
                existing_project=existing_project,
                existing_competitor_brand_ids=existing_competitors,
                write=args.write,
                approval_ref=args.approval_ref,
            )
            add_context_safety_notes(
                plan,
                context=context,
                existing_project=existing_project,
                brand_id=args.brand_id,
            )
            await apply_plan(session, plan)
            return {"diagnostics": context, "plan": plan}
    finally:
        await engine.dispose()


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = value.strip()
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        out.append(clean)
    return out


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brand-id", type=int, default=DEFAULT_BRAND_ID)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--project-slug", default=DEFAULT_PROJECT_SLUG)
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--industry-id", type=int, default=None)
    parser.add_argument("--user-id", default=None)
    parser.add_argument(
        "--competitor-brand-id",
        action="append",
        type=int,
        default=list(DEFAULT_COMPETITOR_BRAND_IDS),
        help="Competitor brand id to pin; repeatable. Default: 2",
    )
    parser.add_argument(
        "--brand-alias",
        action="append",
        default=None,
        help="Alias/name fragment used for read-only project lookup; repeatable.",
    )
    parser.add_argument("--approval-ref", default=None)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.brand_alias is None:
        args.brand_alias = list(DEFAULT_ALIASES) if args.brand_id == DEFAULT_BRAND_ID else []
    else:
        args.brand_alias = _unique_strings(args.brand_alias)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    try:
        output = asyncio.run(run(parse_args(argv)))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
