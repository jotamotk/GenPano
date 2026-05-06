import json

import pytest

import admin_console.app as app_mod


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class RecordingCursor(FakeCursor):
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


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


class StreamingCursor(FakeCursor):
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        compact = " ".join(str(sql).split())
        self.conn.statements.append((compact, params))
        if "INSERT INTO query_generation_candidates" in compact:
            self.conn.inserted_candidates.append(params)
        if "UPDATE query_generation_runs" in compact:
            self.conn.run_updates.append((compact, params))


class StreamingConnection(FakeConnection):
    def __init__(self):
        super().__init__()
        self.statements = []
        self.inserted_candidates = []
        self.run_updates = []

    def cursor(self, *args, **kwargs):
        return StreamingCursor(self)




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


def test_query_pool_assemble_starts_async_run_without_inline_llm(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fail_inline_assemble(*args, **kwargs):
        pytest.fail("assemble API must not call the LLM generation path inline")

    def fake_start(cur, admin_id, payload):
        assert admin_id == "admin-1"
        assert payload["selection"]["mode"] == "explicit"
        assert payload["selection"]["prompt_ids"] == ["101", "102"]
        assert payload["config"]["profiles_per_prompt"] == 2
        return {
            "id": "run-1",
            "status": "running",
            "candidates_estimated": 4,
            "candidates_assembled": 0,
            "preflight_summary": {"scheduler_intake": "running", "candidate_ready": 0},
        }

    spawned = []
    monkeypatch.setattr(app_mod, "_assemble_query_pool_run", fail_inline_assemble)
    monkeypatch.setattr(app_mod, "_start_query_pool_assembly_run", fake_start, raising=False)
    monkeypatch.setattr(
        app_mod,
        "_spawn_query_pool_assembly_worker",
        lambda run_id, admin_id, payload: spawned.append((run_id, admin_id, payload)),
        raising=False,
    )

    response = client.post(
        "/api/admin/query-pool/assemble",
        json={
            "selection": {"mode": "explicit", "prompt_ids": ["101", "102"]},
            "config": {"profiles_per_prompt": 2, "desired_engine_policy": "inherit", "max_candidates": 100},
        },
    )
    body = response.get_json()

    assert response.status_code == 202
    assert body["success"] is True
    assert body["run"]["id"] == "run-1"
    assert body["run"]["status"] == "running"
    assert body["run"]["candidates_assembled"] == 0
    assert conn.commits == 1
    assert conn.closed is True
    assert spawned == [
        (
            "run-1",
            "admin-1",
            {
                "selection": {"mode": "explicit", "prompt_ids": ["101", "102"]},
                "config": {"profiles_per_prompt": 2, "desired_engine_policy": "inherit", "max_candidates": 100},
            },
        )
    ]


def test_query_pool_run_detail_api_returns_json_on_load_failure(client, monkeypatch):
    login(monkeypatch)

    def fail_get_db():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(app_mod, "get_db", fail_get_db)

    response = client.get("/api/admin/query-pool/runs/run-1")
    body = response.get_json()

    assert response.status_code == 503
    assert body["success"] is False
    assert body["error"] == "query_pool_run_load_failed"


def test_query_pool_running_run_reports_estimated_count_without_ready_candidates(monkeypatch):
    monkeypatch.setattr(app_mod, "_query_pool_prompt_ids_from_selection", lambda cur, selection, max_prompts: ["74"])
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_prompt_rows",
        lambda cur, prompt_ids: [{"id": "74", "text": "夏天通勤防晒怎么选？", "topic_text": "夏天通勤防晒"}],
    )
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_profile_pool",
        lambda cur, segment_ids=None: [
            {
                "segment_id": "SEG-HXZ-001",
                "segment_name": "混油夏妆人群",
                "segment_weight": 10,
                "profile_id": "P-HXZ-002",
                "profile_name": "通勤白领",
                "profile_demographic": "28 岁，杭州，夏天每天通勤",
                "profile_need": "怕油腻又不想太贵",
                "profile_weight": 1,
            }
        ],
    )
    cur = RecordingCursor()

    run = app_mod._start_query_pool_assembly_run(
        cur,
        "admin-1",
        {
            "selection": {"mode": "explicit", "prompt_ids": ["74"]},
            "config": {"profiles_per_prompt": 1, "max_candidates": 10},
        },
    )

    assert run["status"] == "running"
    assert run["candidates_estimated"] == 1
    assert run["candidates_assembled"] == 0
    assert run["preflight_summary"]["raw_candidates_estimated"] == 1
    assert run["preflight_summary"]["candidate_ready"] == 0
    assert run["preflight_summary"]["scheduler_intake"] == "running"


def test_query_pool_async_run_streams_candidates_batch_by_batch(monkeypatch):
    monkeypatch.setenv("QUERY_POOL_LLM_BATCH_SIZE", "1")
    monkeypatch.setattr(app_mod, "_query_pool_prompt_ids_from_selection", lambda cur, selection, max_prompts: ["101", "102", "103"])
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_prompt_rows",
        lambda cur, prompt_ids: [
            {"id": "101", "text": "How should I choose sunscreen?", "topic_text": "oily commute sunscreen"},
            {"id": "102", "text": "How should I choose cleanser?", "topic_text": "gentle daily cleanser"},
            {"id": "103", "text": "How should I choose moisturizer?", "topic_text": "light moisturizer"},
        ],
    )
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_profile_pool",
        lambda cur, segment_ids=None: [
            {
                "segment_id": "SEG-1",
                "segment_weight": 1,
                "profile_id": "P-1",
                "profile_weight": 1,
                "profile_need": "daily use without overspending",
            }
        ],
    )
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *args, **kwargs: None)
    conn = StreamingConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    batch_sizes = []

    def fake_query_generator(contexts):
        batch_sizes.append(len(contexts))
        return (
            {
                context["candidate_key"]: f"Which {context['topic_text']} is worth buying for everyday use?"
                for context in contexts
            },
            {"model": "fake-query-llm", "usage": {"total_tokens": len(contexts)}},
        )

    monkeypatch.setattr(app_mod, "_generate_query_pool_llm_queries", fake_query_generator)

    app_mod._execute_query_pool_assembly_run(
        "run-stream",
        "admin-1",
        {
            "selection": {"mode": "explicit", "prompt_ids": ["101", "102", "103"]},
            "config": {"profiles_per_prompt": 1, "max_candidates": 10},
        },
    )

    assert batch_sizes == [1, 1, 1]
    assert len(conn.inserted_candidates) == 3
    assert conn.commits >= 4
    assert any("status = 'completed'" in sql for sql, _params in conn.run_updates)


def test_query_pool_async_run_marks_quality_blocked_with_summary(monkeypatch):
    monkeypatch.setenv("QUERY_POOL_LLM_BATCH_SIZE", "1")
    monkeypatch.setattr(app_mod, "_query_pool_prompt_ids_from_selection", lambda cur, selection, max_prompts: ["101"])
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_prompt_rows",
        lambda cur, prompt_ids: [{"id": "101", "text": "预算内怎么选大牌香水？", "topic_text": "大牌香水送礼"}],
    )
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_profile_pool",
        lambda cur, segment_ids=None: [
            {
                "segment_id": "SEG-1",
                "segment_weight": 1,
                "profile_id": "P-1",
                "profile_weight": 1,
                "profile_need": "送礼不踩雷，价格别太夸张",
            }
        ],
    )
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app_mod,
        "_generate_query_pool_llm_queries",
        lambda contexts: (
            {contexts[0]["candidate_key"]: "CRM私域会员运营策略分析"},
            {"model": "fake-query-llm", "usage": {"total_tokens": 8}},
        ),
    )

    def fail_repair(value, context, candidate_key):
        raise app_mod.TopicPlanLLMError(
            "query_not_natural",
            f"LLM query for {candidate_key} must sound like a real consumer question",
        )

    monkeypatch.setattr(app_mod, "_query_pool_repair_query_text", fail_repair)
    conn = StreamingConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    app_mod._execute_query_pool_assembly_run(
        "run-quality",
        "admin-1",
        {
            "selection": {"mode": "explicit", "prompt_ids": ["101"]},
            "config": {"profiles_per_prompt": 1, "max_candidates": 10},
        },
    )

    failed_updates = [(sql, params) for sql, params in conn.run_updates if "status = 'failed'" in sql]
    assert failed_updates
    params = failed_updates[-1][1]
    summary = json.loads(params[2])
    assert params[5] == "quality_gate_blocked: quality_gate_blocked"
    assert summary["quality_blocked"] is True
    assert summary["by_reason"]["query_not_natural"] == 1
    assert summary["rejected_sample"][0]["reason"] == "query_not_natural"
    assert conn.inserted_candidates == []


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

    def fake_llm_generate(contexts):
        assert [item["profile_need"] for item in contexts] == ["修复屏障", "控制预算"]
        assert contexts[0]["segment_name"] == "敏感肌人群"
        assert contexts[0]["prompt_text"] == "请以 {profile_name} 视角回答：{profile_need}"
        return (
            {
                contexts[0]["candidate_key"]: "敏感肌最近屏障不稳，修复类面霜怎么选？",
                contexts[1]["candidate_key"]: "学生党预算有限，修复屏障买哪种更划算？",
            },
            {"model": "fake-query-llm", "usage": {"total_tokens": 42}},
        )

    monkeypatch.setattr(app_mod, "_insert_query_pool_run", fake_insert)
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_mod, "_generate_query_pool_llm_queries", fake_llm_generate)

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
    assert inserted["kwargs"]["candidates"][0]["rendered_query"] == "敏感肌最近屏障不稳，修复类面霜怎么选？"
    assert inserted["kwargs"]["candidates"][0]["generation_method"] == "llm"
    assert inserted["kwargs"]["candidates"][0]["llm_model"] == "fake-query-llm"
    assert inserted["kwargs"]["preflight_summary"]["generation_method"] == "llm"


def test_query_pool_preflight_estimates_without_calling_llm(monkeypatch):
    monkeypatch.setattr(app_mod, "_query_pool_prompt_ids_from_selection", lambda cur, selection, max_prompts: ["101"])
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_prompt_rows",
        lambda cur, prompt_ids: [{"id": "101", "text": "敏感肌面霜怎么选？"}],
    )
    monkeypatch.setattr(
        app_mod,
        "_fetch_query_pool_profile_pool",
        lambda cur, segment_ids=None: [
            {"segment_id": "SEG-1", "segment_weight": 1, "profile_id": "P-1", "profile_weight": 1},
            {"segment_id": "SEG-2", "segment_weight": 1, "profile_id": "P-2", "profile_weight": 1},
        ],
    )
    monkeypatch.setattr(
        app_mod,
        "_generate_query_pool_llm_queries",
        lambda contexts: pytest.fail("dry-run preflight should not call LLM"),
    )

    run = app_mod._assemble_query_pool_run(
        FakeCursor(),
        "admin-1",
        {
            "selection": {"mode": "explicit", "prompt_ids": ["101"]},
            "config": {"profiles_per_prompt": 2, "max_candidates": 10},
        },
        dry_run=True,
    )

    assert run["status"] == "preview"
    assert run["candidates_estimated"] == 2
    assert run["candidates_assembled"] == 0
    assert run["preflight_summary"]["candidate_ready"] == 2
    assert run["preflight_summary"]["generation_method"] == "llm_estimate"


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


def test_query_pool_candidate_row_exposes_prompt_context():
    row = app_mod._query_pool_candidate_row(
        {
            "id": "qc-1",
            "run_id": "run-1",
            "candidate_seq": 1,
            "prompt_id": "72",
            "prompt_text": "敏感肌能用雅诗兰黛粉底吗？",
            "topic_id": 8,
            "topic_text": "粉底选购",
            "segment_id": "SEG-HXZ-001",
            "profile_id": "P-HXZ-001",
            "rendered_query": "敏感肌用这款粉底会不会闷痘？",
        }
    )

    assert row["prompt_id"] == "72"
    assert row["prompt_text"] == "敏感肌能用雅诗兰黛粉底吗？"
    assert row["topic_id"] == "8"
    assert row["topic_text"] == "粉底选购"


def test_query_pool_candidate_delete_api(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fake_delete(cur, candidate_ids, admin_id, reason=None):
        assert candidate_ids == ["qc-1"]
        assert admin_id == "admin-1"
        assert reason == "bad query"
        return {"deleted": ["qc-1"], "missing": []}

    monkeypatch.setattr(app_mod, "_delete_query_pool_candidates", fake_delete, raising=False)

    response = client.delete("/api/admin/query-pool/candidates/qc-1", json={"reason": "bad query"})
    body = response.get_json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["deleted"] == ["qc-1"]
    assert conn.commits == 1


def test_query_pool_candidate_bulk_delete_api_requires_ids(client, monkeypatch):
    login(monkeypatch)

    response = client.post("/api/admin/query-pool/candidates/bulk-delete", json={"candidate_ids": []})
    body = response.get_json()

    assert response.status_code == 400
    assert body["error"] == "candidate_ids_required"


def test_query_pool_candidate_bulk_delete_api(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fake_delete(cur, candidate_ids, admin_id, reason=None):
        assert candidate_ids == ["qc-1", "qc-2"]
        assert admin_id == "admin-1"
        assert reason == "cleanup"
        return {"deleted": ["qc-1", "qc-2"], "missing": []}

    monkeypatch.setattr(app_mod, "_delete_query_pool_candidates", fake_delete, raising=False)

    response = client.post(
        "/api/admin/query-pool/candidates/bulk-delete",
        json={"candidate_ids": ["qc-1", "qc-2"], "reason": "cleanup"},
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["deleted"] == ["qc-1", "qc-2"]
    assert conn.commits == 1


def test_query_pool_llm_prompt_uses_profile_context_without_internal_terms():
    messages = app_mod._build_query_pool_llm_messages(
        [
            {
                "candidate_key": "c-1",
                "prompt_id": "101",
                "prompt_text": "预算内怎么选大牌香水？",
                "topic_id": "T-1",
                "topic_text": "大牌香水送礼怎么选",
                "segment_id": "SEG-1",
                "segment_name": "价格敏感型",
                "profile_id": "P-1",
                "profile_name": "刚入职白领",
                "profile_demographic": "25 岁，上海，预算有限",
                "profile_need": "送礼不踩雷，价格别太夸张",
            }
        ]
    )
    joined = "\n".join(message["content"] for message in messages)

    assert "真实消费者" in joined
    assert "送礼不踩雷" in joined
    assert "价格别太夸张" in joined
    assert "不要出现 Segment/Profile/用户画像" in joined
    assert "质检会修复或拒绝" in joined
    assert "query_not_natural" in joined
    assert "query_repaired" in joined
    assert '"candidate_key": "c-1"' in joined


def test_query_pool_unrepairable_query_rejections_are_summarized(monkeypatch):
    contexts = [
        {
            "candidate_key": "c-1",
            "prompt_id": "101",
            "prompt_text": "预算内怎么选大牌香水？",
            "topic_id": "T-1",
            "topic_text": "大牌香水送礼怎么选",
            "segment_id": "SEG-1",
            "segment_name": "价格敏感型",
            "profile_id": "P-1",
            "profile_name": "刚入职白领",
            "profile_demographic": "25 岁，上海，预算有限",
            "profile_need": "送礼不踩雷，价格别太夸张",
        }
    ]

    def fail_repair(value, context, candidate_key):
        raise app_mod.TopicPlanLLMError(
            "query_not_natural",
            f"LLM query for {candidate_key} must sound like a real consumer question",
        )

    monkeypatch.setattr(app_mod, "_query_pool_repair_query_text", fail_repair)

    candidates, stats = app_mod._query_pool_candidates_from_llm_queries(
        contexts,
        {"c-1": "CRM私域会员运营策略分析"},
        {"model": "fake-query-llm", "usage": {}},
    )
    summary = app_mod._query_pool_summary(
        contexts=contexts,
        profile_pool=[
            {
                "segment_id": "SEG-1",
                "segment_weight": 1,
                "profile_id": "P-1",
                "profile_weight": 1,
            }
        ],
        config={"profiles_per_prompt": 1, "max_candidates": 10},
        raw_estimated=1,
        candidates=candidates,
        rejected_by_reason=stats["by_reason"],
        rejected_sample=stats["rejected_sample"],
        generation_method="llm",
    )

    assert candidates == []
    assert stats["rejected_total"] == 1
    assert stats["by_reason"]["query_not_natural"] == 1
    assert stats["rejected_sample"][0]["reason"] == "query_not_natural"
    assert summary["quality_blocked"] is True
    assert summary["rejected_total"] == 1
    assert summary["by_reason"]["query_not_natural"] == 1


def test_query_pool_llm_parser_requires_all_candidate_keys():
    parsed = app_mod._parse_query_pool_llm_queries(
        '{"queries":[{"candidate_key":"c-1","query":"刚入职送人大牌香水怎么选才不踩雷？"}]}',
        {"c-1"},
    )

    assert parsed == {"c-1": "刚入职送人大牌香水怎么选才不踩雷？"}
    with pytest.raises(app_mod.TopicPlanLLMError, match="missing query"):
        app_mod._parse_query_pool_llm_queries('{"queries":[]}', {"c-1"})
    with pytest.raises(app_mod.TopicPlanLLMError, match="real consumer question"):
        app_mod._parse_query_pool_llm_queries(
            '{"queries":[{"candidate_key":"c-1","query":"夏天通勤防晒轻薄不油"}]}',
            {"c-1"},
        )
    parsed_without_validation = app_mod._parse_query_pool_llm_queries(
        '{"queries":[{"candidate_key":"c-1","query":"夏天通勤防晒轻薄不油"}]}',
        {"c-1"},
        validate_queries=False,
    )
    assert parsed_without_validation == {"c-1": "夏天通勤防晒轻薄不油"}


def test_query_pool_repairs_single_unnatural_llm_query_instead_of_failing():
    prompt_rows = [{"id": "74", "text": "夏天通勤防晒怎么选？", "topic_text": "夏天通勤防晒"}]
    profile_pool = [
        {
            "segment_id": "SEG-HXZ-001",
            "segment_name": "混油夏妆人群",
            "segment_weight": 10,
            "profile_id": "P-HXZ-002",
            "profile_name": "通勤白领",
            "profile_demographic": "28 岁，杭州，夏天每天通勤",
            "profile_need": "怕油腻又不想太贵",
            "profile_weight": 1,
        }
    ]

    candidates, summary = app_mod._build_query_pool_candidates(
        prompt_rows,
        profile_pool,
        {
            "profiles_per_prompt": 1,
            "profile_strategy": "balanced",
            "max_candidates": 10,
            "overflow_policy": "split",
        },
        query_generator=lambda contexts: (
            {contexts[0]["candidate_key"]: "夏天通勤防晒轻薄不油"},
            {"model": "fake-query-llm", "usage": {}},
        ),
    )

    assert len(candidates) == 1
    assert candidates[0]["prompt_id"] == "74"
    assert candidates[0]["segment_id"] == "SEG-HXZ-001"
    assert candidates[0]["profile_id"] == "P-HXZ-002"
    assert candidates[0]["rendered_query"] != "夏天通勤防晒轻薄不油"
    assert app_mod.is_natural_user_prompt(candidates[0]["rendered_query"])
    assert summary["candidate_ready"] == 1
    assert summary["query_repaired"] == 1
    assert summary["requested"] == 1
    assert summary["accepted"] == 1
    assert summary["rejected_total"] == 0
    assert summary["quality_blocked"] is False
    assert summary["by_reason"]["query_repaired"] == 1


def test_query_pool_repairs_when_llm_and_context_are_stilted():
    prompt_rows = [
        {
            "id": "82",
            "text": "高端奢侈品集团旗下产品线有哪些？",
            "topic_text": "高端奢侈品集团旗下产品线",
        }
    ]
    profile_pool = [
        {
            "segment_id": "SEG-HXZ-001",
            "segment_name": "后台用户画像",
            "segment_weight": 10,
            "profile_id": "P-HXZ-001",
            "profile_name": "运营触达人群",
            "profile_demographic": "后台分层",
            "profile_need": "用户画像触达和转化路径",
            "profile_weight": 1,
        }
    ]

    candidates, summary = app_mod._build_query_pool_candidates(
        prompt_rows,
        profile_pool,
        {
            "profiles_per_prompt": 1,
            "profile_strategy": "balanced",
            "max_candidates": 10,
            "overflow_policy": "split",
        },
        query_generator=lambda contexts: (
            {contexts[0]["candidate_key"]: "高端奢侈品集团旗下产品线市场表现"},
            {"model": "fake-query-llm", "usage": {}},
        ),
    )

    rendered_query = candidates[0]["rendered_query"]
    assert len(candidates) == 1
    assert app_mod.is_natural_user_prompt(rendered_query)
    assert "集团旗下" not in rendered_query
    assert "产品线" not in rendered_query
    assert "用户画像" not in rendered_query
    assert summary["candidate_ready"] == 1
    assert summary["query_repaired"] == 1


def test_insert_query_pool_run_persists_llm_generation_metadata():
    cur = RecordingCursor()

    app_mod._insert_query_pool_run(
        cur,
        admin_id="admin-1",
        selection={"mode": "explicit", "prompt_ids": ["101"]},
        config={
            "profiles_per_prompt": 1,
            "desired_engine_policy": "inherit",
            "engine_panel_id": None,
            "max_candidates": 10,
            "overflow_policy": "split",
        },
        candidates=[
            {
                "id": "candidate-1",
                "candidate_seq": 1,
                "prompt_id": "101",
                "segment_id": "SEG-1",
                "profile_id": "P-1",
                "rendered_query": "刚入职送人大牌香水怎么选才不踩雷？",
                "render_hash": "hash-1",
                "candidate_status": "candidate",
                "generation_method": "llm",
                "llm_model": "fake-query-llm",
                "llm_usage": {"total_tokens": 42},
            }
        ],
        preflight_summary={"raw_candidates_estimated": 1},
    )

    candidate_insert = next(sql for sql, _params in cur.calls if "INSERT INTO query_generation_candidates" in sql)
    candidate_params = next(params for sql, params in cur.calls if "INSERT INTO query_generation_candidates" in sql)
    assert "generation_method" in candidate_insert
    assert "llm_model" in candidate_insert
    assert "llm_usage_json" in candidate_insert
    assert "llm" in candidate_params
    assert "fake-query-llm" in candidate_params


def test_query_pool_run_failed_persists_llm_error():
    cur = RecordingCursor()

    app_mod._mark_query_pool_run_failed(
        cur,
        run_id="run-1",
        error_code="llm_call_failed",
        error_message="upstream timeout",
    )

    sql, params = cur.calls[0]
    assert "UPDATE query_generation_runs" in sql
    assert "status = 'failed'" in sql
    assert "llm_error" in sql
    assert params == ("llm_call_failed: upstream timeout", "run-1")


def test_query_pool_cleanup_deletes_non_llm_candidates_and_orphan_runs():
    cur = RecordingCursor()

    app_mod._delete_non_llm_query_pool_candidates(cur)
    sql = "\n".join(call[0] for call in cur.calls)

    assert "DELETE FROM query_generation_candidates" in sql
    assert "COALESCE(generation_method, 'template') <> 'llm'" in sql
    assert "DELETE FROM query_generation_runs" in sql


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
        query_generator=lambda contexts: (
            {context["candidate_key"]: f"自然问题 {index} 怎么选？" for index, context in enumerate(contexts)},
            {"model": "fake-query-llm", "usage": {}},
        ),
    )

    assert len(candidates) == 3
    assert summary["candidate_ready"] == 3
    assert summary["raw_candidates_estimated"] == 4
    assert summary["candidate_cap_reached"] is True
