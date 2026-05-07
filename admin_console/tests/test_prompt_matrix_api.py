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


def test_prompt_matrix_quality_blocked_run_fails_with_metrics(monkeypatch):
    class RunCursor:
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
            if "UPDATE prompt_generation_runs" in compact and "status = 'failed'" in compact:
                self.conn.run["status"] = "failed"
                self.conn.run["llm_error"] = next((value for value in params if value == "quality_gate_blocked"), None)
                self.conn.run["metrics_json"] = next((value for value in params if isinstance(value, str) and "quality_blocked" in value), None)

        def fetchone(self):
            return self.rows[0] if self.rows else None

    class RunConnection:
        def __init__(self):
            self.run = {"id": "run-1", "status": "running", "llm_error": None, "metrics_json": None}
            self.statements = []
            self.commits = 0

        def cursor(self, *args, **kwargs):
            return RunCursor(self)

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

        def close(self):
            pass

    class BadPromptClient:
        def generate_prompts(self, **kwargs):
            return (
                [
                    LLMPromptCandidate(
                        topic_id=1,
                        intent="informational",
                        language="zh-CN",
                        text="给我做一个NIKE私域会员运营策略分析",
                        template_strategy="latest",
                        template_version="v1",
                        confidence=0.8,
                        reason="keyword-stuffed",
                        tags={},
                    )
                ],
                {"model": "fake-prompt-llm", "usage": {}},
            )

    conn = RunConnection()
    monkeypatch.setattr(app_mod, "PromptMatrixClient", BadPromptClient)
    monkeypatch.setattr(app_mod, "_is_generation_run_cancelled", lambda *args, **kwargs: False)
    monkeypatch.setattr(app_mod, "_insert_admin_audit_log", lambda *args, **kwargs: None)

    result = app_mod._execute_prompt_matrix_generation(
        run_id="run-1",
        admin_id="admin-1",
        topics=[{"raw_id": 1, "title": "NIKE跑鞋尺码选择", "brand": "NIKE", "brand_id": 18, "dimension_key": "question"}],
        config={
            "template_strategy": "latest",
            "max_per_topic": 1,
            "max_prompts": 1,
            "intents": ["informational"],
            "languages": ["zh-CN"],
            "combinations": [],
        },
        known_brands=[{"id": 18, "name": "NIKE", "aliases": []}],
        existing_prompts=[],
        estimated=1,
        request_config={"max_prompts": 1},
        conn=conn,
    )

    assert result["quality_blocked"] is True
    assert conn.run["status"] == "failed"
    assert conn.run["llm_error"] == "quality_gate_blocked"
    assert '"quality_blocked": true' in conn.run["metrics_json"]
    assert '"prompt_not_natural": 1' in conn.run["metrics_json"]


