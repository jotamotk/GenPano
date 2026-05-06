import pytest

import admin_console.app as app_mod
from admin_console.prompt_matrix import LLMPromptCandidate, PromptMatrixError


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(str(sql).split())
        self.conn.statements.append((compact, params))
        params = params or []
        if "SELECT * FROM prompt_candidates WHERE id = %s FOR UPDATE" in compact:
            candidate = self.conn.candidates.get(params[0])
            self.rows = [dict(candidate)] if candidate else []
        elif "INSERT INTO prompts" in compact and "RETURNING id" in compact:
            self.rows = [{"id": self.conn.next_prompt_id}]
        elif "UPDATE prompt_candidates" in compact and "RETURNING *" in compact:
            candidate_id = params[-1]
            candidate = dict(self.conn.candidates[candidate_id])
            candidate.update(
                {
                    "status": params[0],
                    "reviewed_by": params[1],
                    "review_reason": params[2],
                    "approved_prompt_id": params[3],
                }
            )
            self.conn.candidates[candidate_id] = candidate
            self.rows = [candidate]
        elif "INSERT INTO prompt_candidates" in compact and "RETURNING *" in compact:
            row = {
                "id": params[0],
                "run_id": params[1],
                "topic_id": params[2],
                "topic_text": params[3],
                "brand_id": params[4],
                "brand_name": params[5],
                "dimension": params[6],
                "intent": params[7],
                "language": params[8],
                "template_strategy": params[9],
                "template_version": params[10],
                "text": params[11],
                "status": "pending",
                "confidence": params[12],
                "reason": params[13],
                "duplicate_of": params[14],
                "tags": params[15],
                "approved_prompt_id": None,
            }
            self.rows = [row]
            self.conn.inserted_candidates.append(row)
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, candidates=None):
        self.statements = []
        self.inserted_candidates = []
        self.candidates = candidates or {}
        self.next_prompt_id = 777
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

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


def test_prompt_matrix_requires_admin(client):
    response = client.get("/api/admin/prompt-matrix/config")
    assert response.status_code == 401
    assert response.get_json()["error"] == "admin_session_required"


def test_topics_pagination_and_filters(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)

    def fake_fetch(cur, filters=None, page=1, per_page=20, topic_ids=None):
        assert filters["q"] == "skin"
        assert filters["brand_id"] == 2
        assert filters["coverage"] == "gap"
        assert page == 2
        assert per_page == 1
        return ([{"id": "T-9", "raw_id": 9, "title": "skin barrier", "coverage": "gap"}], 3, {"matchingTopics": 3})

    monkeypatch.setattr(app_mod, "_fetch_prompt_matrix_topics", fake_fetch)
    response = client.get("/api/admin/prompt-matrix/topics?q=skin&brand_id=2&coverage=gap&page=2&per_page=1")
    body = response.get_json()
    assert response.status_code == 200
    assert body["rows"][0]["raw_id"] == 9
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["total_pages"] == 3


def test_gaps_summary(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())
    monkeypatch.setattr(
        app_mod,
        "_prompt_matrix_gaps_for_topics",
        lambda cur, topic_ids=None, filters=None, config=None, limit=200: [
            {"id": "PG-1", "topic": "A", "gap": "No Prompt", "priority": "P1", "estimate": 4},
            {"id": "PG-2", "topic": "B", "gap": "Missing intent", "priority": "P2", "estimate": 2},
        ],
    )
    response = client.get("/api/admin/prompt-matrix/gaps?topic_ids=1,2")
    body = response.get_json()
    assert response.status_code == 200
    assert body["summary"]["gap_count"] == 2
    assert body["summary"]["estimated_prompts"] == 6


def test_candidates_are_paginated_and_status_filtered(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())

    def fake_fetch(cur, status="pending", query=None, limit=100, offset=0, include_total=False):
        assert status == "approved"
        assert query == "skin"
        assert limit == 10
        assert offset == 20
        rows = [{"id": "c3", "status": "approved", "text": "Which moisturizer is better for sensitive skin?"}]
        return (rows, 31) if include_total else rows

    monkeypatch.setattr(app_mod, "_fetch_prompt_matrix_candidates", fake_fetch)
    monkeypatch.setattr(
        app_mod,
        "_prompt_matrix_candidate_status_counts",
        lambda cur, query=None: {"pending": 8, "approved": 31, "rejected": 2, "all": 41},
    )
    response = client.get("/api/admin/prompt-matrix/candidates?status=approved&q=skin&page=3&per_page=10")
    body = response.get_json()
    assert response.status_code == 200
    assert body["rows"][0]["id"] == "c3"
    assert body["pagination"] == {"page": 3, "per_page": 10, "total": 31, "total_pages": 4}
    assert body["summary"]["status_counts"]["approved"] == 31


def test_candidates_db_error_returns_controlled_json(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: (_ for _ in ()).throw(RuntimeError("db unavailable")))

    response = client.get("/api/admin/prompt-matrix/candidates?status=approved")
    body = response.get_json()

    assert response.status_code == 503
    assert body["success"] is False
    assert body["error"] == "candidate_load_failed"


def test_prompts_support_server_side_query_for_query_pool(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())

    def fake_fetch(cur, intent=None, language=None, query=None, page=1, per_page=50, topic_ids=None):
        assert intent == "commercial"
        assert language == "zh-CN"
        assert query == "barrier"
        assert page == 4
        assert per_page == 25
        assert topic_ids is None
        return ([{"id": "p-1", "templateText": "How to repair skin barrier?", "intent": "commercial"}], 126)

    monkeypatch.setattr(app_mod, "_fetch_prompt_matrix_prompts", fake_fetch)
    monkeypatch.setattr(app_mod, "_prompt_matrix_stats", lambda cur: {"totalPrompts": 126})
    response = client.get(
        "/api/admin/prompt-matrix/prompts?intent=commercial&language=zh-CN&q=barrier&page=4&per_page=25"
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["rows"][0]["id"] == "p-1"
    assert body["pagination"] == {"page": 4, "per_page": 25, "total": 126, "total_pages": 6}


def test_prompts_support_topic_filter_for_query_pool(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())

    def fake_fetch(cur, intent=None, language=None, query=None, page=1, per_page=50, topic_ids=None):
        assert topic_ids == [101, 202]
        return ([{"id": "p-2", "topic_id": 101, "templateText": "Prompt for topic 101"}], 1)

    monkeypatch.setattr(app_mod, "_fetch_prompt_matrix_prompts", fake_fetch)
    monkeypatch.setattr(app_mod, "_prompt_matrix_stats", lambda cur: {"totalPrompts": 1})

    response = client.get("/api/admin/prompt-matrix/prompts?topic_ids=101,202&page=1&per_page=25")
    body = response.get_json()

    assert response.status_code == 200
    assert body["rows"][0]["topic_id"] == 101
    assert body["pagination"]["total"] == 1


def test_prompt_candidate_migration_backfills_updated_at(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, table: False)

    app_mod._ensure_prompt_matrix_tables()

    statements = "\n".join(sql for sql, _params in conn.statements)
    assert "ALTER TABLE prompt_candidates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP" in statements


def test_query_pool_candidates_use_cursor_api_contract(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())

    def fake_fetch(
        cur,
        run_id=None,
        status=None,
        segment_id=None,
        profile_id=None,
        query=None,
        limit=100,
        cursor=None,
        direction="next",
    ):
        assert run_id == "run-1"
        assert status == "ready"
        assert segment_id == "seg-1"
        assert profile_id == "profile-1"
        assert query == "barrier"
        assert limit == 50
        assert cursor == "opaque-cursor"
        assert direction == "prev"
        return (
            [
                {
                    "id": "qc-1",
                    "run_id": "run-1",
                    "candidate_seq": 98,
                    "prompt_id": "prompt-1",
                    "segment_id": "seg-1",
                    "profile_id": "profile-1",
                    "rendered_query": "敏感肌如何修复屏障？",
                    "candidate_status": "ready",
                }
            ],
            "next-cursor",
            "prev-cursor",
            100_000_000,
        )

    monkeypatch.setattr(app_mod, "_fetch_query_pool_candidates", fake_fetch)

    response = client.get(
        "/api/admin/query-pool/candidates"
        "?run_id=run-1&status=ready&segment_id=seg-1&profile_id=profile-1"
        "&q=barrier&limit=50&cursor=opaque-cursor&direction=prev"
    )
    body = response.get_json()

    assert response.status_code == 200
    assert body["rows"][0]["rendered_query"] == "敏感肌如何修复屏障？"
    assert body["next_cursor"] == "next-cursor"
    assert body["prev_cursor"] == "prev-cursor"
    assert body["approx_total"] == 100_000_000


def test_query_pool_candidates_validate_status(client, monkeypatch):
    login(monkeypatch)

    response = client.get("/api/admin/query-pool/candidates?status=running")
    body = response.get_json()

    assert response.status_code == 400
    assert body["error"] == "invalid_status"


def test_generate_requires_topic_selection(client, monkeypatch):
    login(monkeypatch)
    monkeypatch.setattr(app_mod, "get_db", lambda: FakeConnection())
    monkeypatch.setattr(app_mod, "_prompt_matrix_selection_from_payload", lambda cur, payload: ([], {"mode": "explicit"}))
    response = client.post("/api/admin/prompt-matrix/generate", json={"topic_ids": []})
    assert response.status_code == 400
    assert response.get_json()["error"] == "topic_ids_required"


def test_generate_writes_run_and_candidates(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_prompt_matrix_selection_from_payload", lambda cur, payload: ([1], {"mode": "explicit", "topic_ids": [1]}))
    monkeypatch.setattr(
        app_mod,
        "_fetch_prompt_matrix_topics_by_ids",
        lambda cur, topic_ids, config=None: [
            {"raw_id": 1, "title": "Sensitive skin moisturizer", "brand_id": 2, "brand": "Winona", "dimension_key": "scenario"}
        ],
    )
    monkeypatch.setattr(app_mod, "_prompt_matrix_brand_rows", lambda cur: [{"id": 2, "name": "Winona", "aliases": []}])
    monkeypatch.setattr(app_mod, "_fetch_prompt_matrix_prompt_texts", lambda cur, topic_ids=None: [])
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, table: False)

    class FakeClient:
        def generate_prompts(self, **kwargs):
            return (
                [
                    LLMPromptCandidate(
                        topic_id=1,
                        intent="informational",
                        language="en-US",
                        text="Which moisturizer is better for sensitive skin during seasonal changes?",
                        template_strategy="latest",
                        template_version="v1",
                        confidence=0.91,
                        reason="covers gap",
                        tags={"routing": "deferred_to_query_pool"},
                    )
                ],
                {"model": "mock", "usage": {"total_tokens": 12}},
            )

    monkeypatch.setattr(app_mod, "PromptMatrixClient", FakeClient)
    response = client.post("/api/admin/prompt-matrix/generate", json={"topic_ids": [1], "max_prompts": 10})
    body = response.get_json()
    assert response.status_code == 200
    assert body["summary"]["generated"] == 1
    assert any("INSERT INTO prompt_generation_runs" in sql for sql, _ in conn.statements)
    assert any("INSERT INTO prompt_candidates" in sql for sql, _ in conn.statements)
    assert any("INSERT INTO admin_audit_log" in sql for sql, _ in conn.statements)


def test_generate_llm_config_missing_is_controlled(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_prompt_matrix_selection_from_payload", lambda cur, payload: ([1], {"mode": "explicit", "topic_ids": [1]}))
    monkeypatch.setattr(
        app_mod,
        "_fetch_prompt_matrix_topics_by_ids",
        lambda cur, topic_ids, config=None: [
            {"raw_id": 1, "title": "Sensitive skin moisturizer", "brand_id": 2, "brand": "Winona", "dimension_key": "scenario"}
        ],
    )
    monkeypatch.setattr(app_mod, "_prompt_matrix_brand_rows", lambda cur: [])
    monkeypatch.setattr(app_mod, "_fetch_prompt_matrix_prompt_texts", lambda cur, topic_ids=None: [])
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, table: False)

    class MissingClient:
        def __init__(self):
            raise PromptMatrixError("llm_config_missing", "missing config")

    monkeypatch.setattr(app_mod, "PromptMatrixClient", MissingClient)
    response = client.post("/api/admin/prompt-matrix/generate", json={"topic_ids": [1]})
    body = response.get_json()
    assert response.status_code == 503
    assert body["error"] == "llm_config_missing"
    assert any("UPDATE prompt_generation_runs" in sql for sql, _ in conn.statements)


def test_generate_does_not_use_local_generation_when_llm_quality_gate_fails(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection()
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_prompt_matrix_selection_from_payload", lambda cur, payload: ([1], {"mode": "explicit", "topic_ids": [1]}))
    monkeypatch.setattr(
        app_mod,
        "_fetch_prompt_matrix_topics_by_ids",
        lambda cur, topic_ids, config=None: [
            {"raw_id": 1, "title": "Winona repair cream category", "brand_id": None, "brand": None, "dimension_key": "category"}
        ],
    )
    monkeypatch.setattr(app_mod, "_prompt_matrix_brand_rows", lambda cur: [{"id": 2, "name": "Winona", "aliases": []}])
    monkeypatch.setattr(app_mod, "_fetch_prompt_matrix_prompt_texts", lambda cur, topic_ids=None: [])
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, table: False)

    class LeakyClient:
        def generate_prompts(self, **kwargs):
            raise PromptMatrixError("category_brand_leak", "leaky output")

    monkeypatch.setattr(app_mod, "PromptMatrixClient", LeakyClient)
    response = client.post("/api/admin/prompt-matrix/generate", json={"topic_ids": [1], "max_prompts": 4})
    body = response.get_json()
    assert response.status_code == 502
    assert body["success"] is False
    assert body["error"] == "category_brand_leak"
    assert conn.inserted_candidates == []
    assert any("UPDATE prompt_generation_runs" in sql for sql, _ in conn.statements)
    assert any("INSERT INTO admin_audit_log" in sql for sql, _ in conn.statements)


def test_approve_candidate_writes_prompt(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(
        {
            "c1": {
                "id": "c1",
                "run_id": "r1",
                "topic_id": 1,
                "topic_text": "Sensitive skin moisturizer",
                "brand_id": 2,
                "brand_name": "Winona",
                "dimension": "scenario",
                "intent": "commercial",
                "language": "zh-CN",
                "template_strategy": "latest",
                "template_version": "v1",
                "text": "敏感肌换季时应该怎么挑选温和保湿面霜？",
                "status": "pending",
                "confidence": 0.9,
                "reason": "covers gap",
                "duplicate_of": None,
                "tags": {},
                "approved_prompt_id": None,
            }
        }
    )
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, table: True)
    monkeypatch.setattr(
        app_mod,
        "_table_columns",
        lambda cur, table: {
            "id",
            "topic_id",
            "text",
            "intent",
            "language",
            "template_strategy",
            "template_version",
            "status",
            "tags",
            "generated_by",
            "created_at",
            "updated_at",
        },
    )
    response = client.post("/api/admin/prompt-matrix/candidates/c1/review", json={"status": "approved"})
    body = response.get_json()
    assert response.status_code == 200
    assert body["candidate"]["approved_prompt_id"] == 777
    assert any("INSERT INTO prompts" in sql for sql, _ in conn.statements)


def test_approve_candidate_rejects_language_mismatch(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(
        {
            "c1": {
                "id": "c1",
                "run_id": "r1",
                "topic_id": 1,
                "intent": "informational",
                "language": "en-US",
                "template_strategy": "latest",
                "template_version": "v1",
                "text": "How should I choose Nike的徒步鞋？",
                "status": "pending",
                "confidence": 0.9,
                "reason": "mixed language",
                "duplicate_of": None,
                "tags": {},
                "approved_prompt_id": None,
            }
        }
    )
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    monkeypatch.setattr(app_mod, "_table_exists", lambda cur, table: table == "prompts")
    monkeypatch.setattr(app_mod, "_table_columns", lambda cur, table: {"id", "topic_id", "text", "language"})
    response = client.post("/api/admin/prompt-matrix/candidates/c1/review", json={"status": "approved"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "prompt_language_mismatch"
    assert not any("INSERT INTO prompts" in sql for sql, _ in conn.statements)


def test_reviewed_candidate_cannot_be_reviewed_twice(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection({"c1": {"id": "c1", "status": "approved", "approved_prompt_id": 10}})
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    response = client.post("/api/admin/prompt-matrix/candidates/c1/review", json={"status": "rejected"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "candidate_already_reviewed"


def test_bulk_review_partial_failure_returns_409(client, monkeypatch):
    login(monkeypatch)
    conn = FakeConnection(
        {
            "ok": {
                "id": "ok",
                "run_id": "r1",
                "topic_id": 1,
                "topic_text": "Topic",
                "intent": "informational",
                "language": "zh-CN",
                "text": "敏感肌应该怎么挑选保湿面霜？",
                "status": "pending",
                "confidence": 0.8,
                "tags": {},
            },
            "bad": {"id": "bad", "status": "approved", "approved_prompt_id": 3},
        }
    )
    monkeypatch.setattr(app_mod, "get_db", lambda: conn)
    response = client.post(
        "/api/admin/prompt-matrix/candidates/bulk-review",
        json={"candidate_ids": ["ok", "bad"], "status": "rejected"},
    )
    body = response.get_json()
    assert response.status_code == 409
    assert body["summary"]["updated_count"] == 1
    assert body["failed"][0]["id"] == "bad"
