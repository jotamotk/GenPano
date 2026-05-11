from __future__ import annotations

import pytest
from scripts.bootstrap_app_project_context import (
    DEFAULT_COMPETITOR_POLICY,
    build_plan,
    stable_project_id,
    validate_plan_can_write,
    validate_write_gate,
)


def test_stable_project_id_is_uuid_shaped_and_repeatable() -> None:
    first = stable_project_id(brand_id=12, project_slug="estee-lauder-first-slice")
    second = stable_project_id(brand_id=12, project_slug="estee-lauder-first-slice")

    assert first == second
    assert len(first) == 36
    assert first.count("-") == 4


def test_dry_run_plan_creates_minimum_estee_context() -> None:
    plan = build_plan(
        brand_id=12,
        user_id="user-1",
        project_name="Estee Lauder / 雅诗兰黛 App Analytics",
        project_id="11111111-1111-4111-8111-111111111111",
        industry_id=None,
        competitor_brand_ids=[2],
        existing_project=None,
        existing_competitor_brand_ids=set(),
        write=False,
        approval_ref=None,
    )

    assert plan["dry_run"] is True
    assert plan["project_id"] == "11111111-1111-4111-8111-111111111111"
    assert plan["primary_brand_id"] == 12
    assert plan["competitor_brand_ids"] == [2]
    assert plan["competitor_policy"] == DEFAULT_COMPETITOR_POLICY
    assert plan["actions"] == [
        {
            "type": "create_project",
            "project_id": "11111111-1111-4111-8111-111111111111",
            "primary_brand_id": 12,
            "user_id": "user-1",
        },
        {
            "type": "insert_project_competitor",
            "project_id": "11111111-1111-4111-8111-111111111111",
            "brand_id": 2,
        },
    ]
    assert "DELETE FROM project_competitors" in plan["rollback_sql"]
    assert "DELETE FROM projects" in plan["rollback_sql"]


def test_existing_project_reuse_only_adds_missing_competitors() -> None:
    plan = build_plan(
        brand_id=12,
        user_id="user-1",
        project_name="ignored when reusing",
        project_id="11111111-1111-4111-8111-111111111111",
        industry_id=7,
        competitor_brand_ids=[2, 24],
        existing_project={
            "id": "22222222-2222-4222-8222-222222222222",
            "user_id": "user-2",
            "name": "Existing Estee",
            "industry_id": 7,
            "primary_brand_id": 12,
        },
        existing_competitor_brand_ids={2},
        write=False,
        approval_ref=None,
    )

    assert plan["project_id"] == "22222222-2222-4222-8222-222222222222"
    assert plan["user_id"] == "user-2"
    assert plan["actions"] == [
        {
            "type": "insert_project_competitor",
            "project_id": "22222222-2222-4222-8222-222222222222",
            "brand_id": 24,
        }
    ]
    assert "DELETE FROM projects" not in plan["rollback_sql"]


def test_write_gate_requires_user_and_approval_ref() -> None:
    with pytest.raises(ValueError, match="--user-id"):
        validate_write_gate(write=True, user_id=None, approval_ref="approved on #492")

    with pytest.raises(ValueError, match="--approval-ref"):
        validate_write_gate(write=True, user_id="user-1", approval_ref=None)

    validate_write_gate(write=True, user_id="user-1", approval_ref="approved on #492")


def test_write_refuses_plan_with_blockers() -> None:
    plan = {
        "write_requested": True,
        "blockers": ["creation requires an approved production App user_id owner"],
    }

    with pytest.raises(ValueError, match="plan has blockers"):
        validate_plan_can_write(plan)
