from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "backend" / "scripts" / "app_analytics_readonly_evidence.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "app-analytics-readonly-evidence.yml"


def load_script():
    spec = importlib.util.spec_from_file_location(
        "app_analytics_readonly_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_db_sql_is_read_only_and_covers_required_evidence() -> None:
    mod = load_script()

    cfg = mod.EvidenceConfig(
        project_id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
        brand_id=12,
        competitor_brand_ids=(2,),
        date_from="2026-04-24",
        date_to="2026-05-11",
    )
    sql = mod.build_db_sql(cfg)

    mod.assert_read_only_sql(sql)
    lowered = sql.lower()
    assert "begin transaction read only" in lowered
    assert "response counts by engine/date" in lowered
    assert "analyzer run/failure counts" in lowered
    assert "brand_mentions coverage" in lowered
    assert "citation_sources and official domains" in lowered
    assert "sentiment_drivers" in lowered
    assert "topic -> prompt -> query -> response linkage" in lowered
    assert "daily score/component aggregate counts" in lowered
    assert "analysis_status = 'done'" in lowered
    assert "'completed'" not in lowered
    assert "coalesce(avg(" not in lowered
    assert "mention_rate_non_null_count" in lowered
    assert "mention_rate_null_count" in lowered
    assert "visibility_non_null_count" in lowered
    assert "visibility_null_count" in lowered
    assert "sentiment_non_null_count" in lowered
    assert "sentiment_null_count" in lowered
    assert "sov_non_null_count" in lowered
    assert "sov_null_count" in lowered
    assert "citation_non_null_count" in lowered
    assert "citation_null_count" in lowered
    assert "geo_score_non_null_count" in lowered
    assert "geo_score_null_count" in lowered
    assert "insert" not in lowered
    assert "update" not in lowered
    assert "delete" not in lowered


def test_project_context_does_not_compare_project_id_to_uuid_literal() -> None:
    mod = load_script()

    project_id = "95d43022-a5c8-5944-b6d6-34b29faa18b5"
    cfg = mod.EvidenceConfig(
        project_id=project_id,
        brand_id=12,
        competitor_brand_ids=(2,),
        date_from="2026-04-24",
        date_to="2026-05-11",
    )
    sql = mod.build_db_sql(cfg)

    assert f"WHERE p.id = '{project_id}'::uuid" not in sql
    assert f"ORDER BY (p.id = '{project_id}'::uuid)" not in sql
    assert f"WHERE p.id::text = '{project_id}'" in sql
    assert f"ORDER BY (p.id::text = '{project_id}')" in sql


def test_project_id_input_remains_uuid_shape_validated() -> None:
    mod = load_script()

    cfg = mod.EvidenceConfig(
        project_id="not-a-uuid",
        brand_id=12,
        competitor_brand_ids=(2,),
        date_from="2026-04-24",
        date_to="2026-05-11",
    )

    with pytest.raises(ValueError, match="project_id must be UUID-shaped"):
        mod.build_db_sql(cfg)


def test_read_only_sql_guard_rejects_write_keywords() -> None:
    mod = load_script()

    with pytest.raises(ValueError, match="write-capable SQL"):
        mod.assert_read_only_sql("SELECT 1; UPDATE projects SET name = 'x';")


def test_api_probe_plan_uses_get_only_and_masks_token() -> None:
    mod = load_script()

    cfg = mod.EvidenceConfig(
        project_id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
        brand_id=12,
        competitor_brand_ids=(2,),
        date_from="2026-04-24",
        date_to="2026-05-11",
        base_url="http://116.62.36.173/",
    )
    probes = mod.build_api_probe_plan(cfg)

    assert probes
    assert {probe.method for probe in probes} == {"GET"}
    assert any("/overview" in probe.path for probe in probes)
    assert any("/metrics" in probe.path for probe in probes)
    assert any("/competitors/metrics" in probe.path for probe in probes)
    assert any("/topics/monitoring" in probe.path for probe in probes)
    assert any("/sentiment" in probe.path for probe in probes)
    assert any("/citations/authority-trend" in probe.path for probe in probes)
    assert any("/competitors/trends" in probe.path for probe in probes)

    token = "header.payload.signature"
    rendered = mod.mask_secret(token, visible=4)
    assert token not in rendered
    assert rendered.startswith("head")
    assert rendered.endswith("ture")


def test_missing_secret_report_names_exact_secret() -> None:
    mod = load_script()

    report = mod.missing_secret_report(
        {
            "SERVER_HOST": "",
            "SERVER_USER": "deploy",
            "SERVER_SSH_KEY": "",
            "APP_ANALYTICS_BEARER_TOKEN": "",
        }
    )

    assert "SERVER_HOST" in report
    assert "SERVER_SSH_KEY" in report
    assert "APP_ANALYTICS_BEARER_TOKEN" in report
    assert "SERVER_USER" not in report


def test_workflow_is_manual_read_only_and_has_no_write_mode() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "workflow_dispatch" in text
    assert "write" not in lowered
    assert "dry_run" not in lowered
    assert "app_analytics_readonly_evidence.py" in text
    assert "APP_ANALYTICS_BEARER_TOKEN" in text
    assert "SERVER_HOST" in text
    assert "docker compose exec -T postgres psql" in text
    assert "python backend/scripts/app_analytics_readonly_evidence.py db-sql" in text
