import pytest

import admin_console.app as app_mod


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, *args, **kwargs):
        return FakeCursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture
def client():
    app_mod.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return app_mod.app.test_client()


def login(monkeypatch):
    monkeypatch.setattr(
        app_mod,
        "_current_admin",
        lambda: {"id": "admin-1", "email": "admin@example.com", "role": "admin", "status": "active"},
    )


def test_query_pool_assemble_creates_run_and_candidates(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fake_assemble(cur, admin_id, payload, dry_run=False):
        assert admin_id == "admin-1"
        assert dry_run is False
        assert payload["selection"]["mode"] == "explicit"
        assert payload["selection"]["prompt_ids"] == ["101", "102"]
        assert payload["config"]["profiles_per_prompt"] == 2
        return {
            "id": "run-1",
            "status": "completed",
            "candidates_estimated": 4,
            "candidates_assembled": 4,
            "preflight_summary": {"scheduler_intake": "ready", "duplicate_review": 0},
        }

    monkeypatch.setattr(app_mod, "_assemble_query_pool_run", fake_assemble)

    response = client.post(
        "/api/admin/query-pool/assemble",
        json={
            "selection": {"mode": "explicit", "prompt_ids": ["101", "102"]},
            "config": {"profiles_per_prompt": 2, "desired_engine_policy": "inherit", "max_candidates": 100},
        },
    )
    body = response.get_json()

    assert response.status_code == 201
    assert body["success"] is True
    assert body["run"]["id"] == "run-1"
    assert body["run"]["candidates_assembled"] == 4
    assert conn.commits == 1
    assert conn.closed is True


def test_query_pool_preflight_is_dry_run(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fake_assemble(cur, admin_id, payload, dry_run=False):
        assert dry_run is True
        return {
            "id": None,
            "status": "preview",
            "candidates_estimated": 6,
            "candidates_assembled": 0,
            "preflight_summary": {"candidate_ready": 6, "scheduler_intake": "ready"},
        }

    monkeypatch.setattr(app_mod, "_assemble_query_pool_run", fake_assemble)

    response = client.post(
        "/api/admin/query-pool/preflight",
        json={
            "selection": {"mode": "explicit", "prompt_ids": ["101", "102"]},
            "config": {"profiles_per_prompt": 3, "desired_engine_policy": "balanced", "max_candidates": 100},
        },
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["run"]["status"] == "preview"
    assert conn.commits == 0
    assert conn.closed is True


def test_query_pool_assemble_helper_builds_candidates_without_engine_fanout(monkeypatch):
    monkeypatch.setattr(app_mod, "_query_pool_prompt_ids_from_selection", lambda cur, selection, max_prompts: ["101"])
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_prompt_rows",
        lambda cur, prompt_ids: [{"id": "101", "text": "请以 {profile_name} 视角回答：{profile_need}"}],
    )
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_profile_pool",
        lambda cur, segment_ids=None: [
            {
                "segment_id": "SEG-1",
                "segment_name": "敏感肌人群",
                "segment_weight": 10,
                "profile_id": "P-1",
                "profile_name": "一线年轻女性",
                "profile_demographic": "25 岁，上海",
                "profile_need": "修复屏障",
                "profile_weight": 2,
            },
            {
                "segment_id": "SEG-2",
                "segment_name": "价格敏感人群",
                "segment_weight": 4,
                "profile_id": "P-2",
                "profile_name": "学生党",
                "profile_demographic": "22 岁，武汉",
                "profile_need": "控制预算",
                "profile_weight": 1,
            },
        ],
    )
    inserted = {}

    def fake_insert(cur, **kwargs):
        inserted["kwargs"] = kwargs
        return "run-1"

    monkeypatch.setattr(app_mod, "_insert_query_pool_run", fake_insert)
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *args, **kwargs: None)

    run = app_mod._assemble_query_pool_run(
        FakeCursor(),
        "admin-1",
        {
            "selection": {"mode": "explicit", "prompt_ids": ["101"]},
            "config": {
                "profiles_per_prompt": 2,
                "desired_engine_policy": "benchmark_panel",
                "max_candidates": 10,
            },
        },
    )

    assert run["id"] == "run-1"
    assert run["candidates_estimated"] == 2
    assert run["candidates_assembled"] == 2
    assert len(inserted["kwargs"]["candidates"]) == 2
    assert "engine" not in inserted["kwargs"]["candidates"][0]
    assert "修复屏障" in inserted["kwargs"]["candidates"][0]["rendered_query"]


def test_query_pool_candidate_cap_hold_blocks_run(monkeypatch):
    monkeypatch.setattr(app_mod, "_query_pool_prompt_ids_from_selection", lambda cur, selection, max_prompts: ["101"])
    monkeypatch.setattr(app_mod, "_fetch_query_pool_prompt_rows", lambda cur, prompt_ids: [{"id": "101", "text": "Q"}])
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_profile_pool",
        lambda cur, segment_ids=None: [
            {"segment_id": "SEG-1", "segment_weight": 1, "profile_id": "P-1", "profile_weight": 1},
            {"segment_id": "SEG-2", "segment_weight": 1, "profile_id": "P-2", "profile_weight": 1},
        ],
    )

    with pytest.raises(ValueError, match="query_pool_candidate_cap_exceeded"):
        app_mod._assemble_query_pool_run(
            FakeCursor(),
            "admin-1",
            {
                "selection": {"mode": "explicit", "prompt_ids": ["101"]},
                "config": {
                    "profiles_per_prompt": 2,
                    "desired_engine_policy": "inherit",
                    "max_candidates": 1,
                    "overflow_policy": "hold",
                },
            },
        )


def test_query_pool_candidate_status_update_validates_status(client, monkeypatch):
    login(monkeypatch)

    response = client.post("/api/admin/query-pool/candidates/qc-1/review", json={"status": "running"})
    body = response.get_json()

    assert response.status_code == 400
    assert body["error"] == "invalid_status"


def test_query_pool_candidate_status_update(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fake_update(cur, candidate_id, status, admin_id, reason=None):
        assert candidate_id == "qc-1"
        assert status == "ready"
        assert admin_id == "admin-1"
        assert reason == "duplicate reviewed"
        return {
            "id": "qc-1",
            "candidate_status": "ready",
            "rendered_query": "敏感肌如何修复屏障？",
        }

    monkeypatch.setattr(app_mod, "_update_query_pool_candidate_status", fake_update)

    response = client.post(
        "/api/admin/query-pool/candidates/qc-1/review",
        json={"status": "ready", "reason": "duplicate reviewed"},
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["candidate"]["candidate_status"] == "ready"
    assert conn.commits == 1


def test_query_pool_render_replaces_profile_variables():
    rendered = app_mod._render_query_pool_candidate(
        {"id": "101", "templateText": "请以 {profile_name} 视角回答：{profile_need}"},
        {"segment_id": "SEG-1", "segment_name": "敏感肌人群"},
        {
            "profile_id": "P-1",
            "profile_name": "一线年轻女性",
            "profile_demographic": "25 岁，上海",
            "profile_need": "修复屏障",
        },
    )

    assert rendered == "请以 一线年轻女性 视角回答：修复屏障"


def test_query_pool_sampling_is_weighted_and_deterministic():
    pool = [
        {"profile_id": "P-low", "segment_id": "SEG-low", "segment_weight": 1, "profile_weight": 1},
        {"profile_id": "P-high", "segment_id": "SEG-high", "segment_weight": 9, "profile_weight": 1},
        {"profile_id": "P-zero", "segment_id": "SEG-zero", "segment_weight": 0, "profile_weight": 10},
    ]

    first = app_mod._sample_query_pool_profiles(pool, 1, strategy="balanced", seed="prompt-1")
    second = app_mod._sample_query_pool_profiles(pool, 1, strategy="balanced", seed="prompt-1")

    assert first == second
    assert first[0]["profile_id"] == "P-high"


def test_query_pool_core_strategy_uses_only_highest_weight_segments():
    pool = [
        {"profile_id": "P-core", "segment_id": "SEG-core", "segment_weight": 10, "profile_weight": 1},
        {"profile_id": "P-supplement", "segment_id": "SEG-supplement", "segment_weight": 9, "profile_weight": 100},
        {"profile_id": "P-core-2", "segment_id": "SEG-core", "segment_weight": 10, "profile_weight": 0.5},
    ]

    sampled = app_mod._sample_query_pool_profiles(pool, 2, strategy="core", seed="prompt-1")

    assert {item["segment_id"] for item in sampled} == {"SEG-core"}
    assert [item["profile_id"] for item in sampled] == ["P-core", "P-core-2"]


def test_query_pool_full_strategy_prefers_segment_coverage():
    pool = [
        {"profile_id": "P-a1", "segment_id": "SEG-a", "segment_weight": 10, "profile_weight": 10},
        {"profile_id": "P-a2", "segment_id": "SEG-a", "segment_weight": 10, "profile_weight": 9},
        {"profile_id": "P-b1", "segment_id": "SEG-b", "segment_weight": 2, "profile_weight": 3},
    ]

    sampled = app_mod._sample_query_pool_profiles(pool, 2, strategy="full", seed="prompt-1")

    assert {item["segment_id"] for item in sampled} == {"SEG-a", "SEG-b"}


def test_query_pool_split_policy_caps_candidates_and_reports_cap():
    prompt_rows = [
        {"id": "101", "text": "Q1 {profile_id}"},
        {"id": "102", "text": "Q2 {profile_id}"},
    ]
    profile_pool = [
        {"profile_id": "P-a", "segment_id": "SEG-a", "segment_weight": 10, "profile_weight": 1},
        {"profile_id": "P-b", "segment_id": "SEG-b", "segment_weight": 9, "profile_weight": 1},
    ]

    candidates, summary = app_mod._build_query_pool_candidates(
        prompt_rows,
        profile_pool,
        {
            "profiles_per_prompt": 2,
            "profile_strategy": "balanced",
            "max_candidates": 3,
            "overflow_policy": "split",
        },
    )

    assert len(candidates) == 3
    assert summary["candidate_ready"] == 3
    assert summary["raw_candidates_estimated"] == 4
    assert summary["candidate_cap_reached"] is True
