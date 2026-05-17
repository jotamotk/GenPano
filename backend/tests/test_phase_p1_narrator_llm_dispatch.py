"""[#1044 P1] B2-4 completion — narrator._call_llm wires real Doubao /
DeepSeek / OpenAI chat-completions dispatch.

Pre-fix the `_call_llm` hook was a stub that always returned None, so
report sections silently ran the deterministic fallback even when an
operator had provisioned an LLM endpoint. This module verifies the
new dispatch:

  - With `LLM_NARRATIVE_PROVIDER=doubao` + ARK_* env set, an HTTP POST
    is made to `{base_url}/chat/completions` carrying the section
    metrics; the response `choices[0].message.content` becomes the
    narrative.
  - With missing credentials, dispatch returns None (graceful) and
    the deterministic fallback runs.
  - Network errors / HTTP non-200 / empty completions all fall back.
  - Section metrics and tables are trimmed before being shipped to
    the model so the prompt stays small.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.reports.narrator import (
    _build_messages,
    _normalize_completion,
    _resolve_llm_endpoint,
    _trim_metrics,
    _trim_tables,
    narrate,
)
from app.reports.sections.base import ReportContext, SectionData


def _section(**kwargs) -> SectionData:
    return SectionData(
        section_type=kwargs.get("section_type", "executive_summary"),
        title=kwargs.get("title", "Executive Summary"),
        summary=kwargs.get("summary", "GEO score 72 over 30 samples."),
        metrics=kwargs.get("metrics", {"geo_score": 72, "samples": 30}),
        tables=kwargs.get("tables", []),
        chosen_variant=kwargs.get("chosen_variant", "full"),
        narrative=kwargs.get("narrative", None),
    )


def _ctx(locale: str = "zh-CN") -> ReportContext:
    # ReportContext is created downstream by the builder; for narrator
    # tests we just need a stub carrying `locale`.
    class _Stub:
        def __init__(self, loc):
            self.locale = loc

    return _Stub(locale)  # type: ignore[return-value]


# ── happy path: Doubao dispatch ─────────────────────────────


@pytest.mark.asyncio
async def test_b2_4_doubao_dispatch_returns_llm_text(monkeypatch):
    """LLM_NARRATIVE_PROVIDER=doubao + creds → POST to /chat/completions,
    response content becomes the narrative."""
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "doubao")
    monkeypatch.setenv("DOUBAO_API_KEY", "test-key")
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://api.example.invalid/v3")
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-2")

    posted: list[dict] = []

    async def fake_post(self, url, json=None, headers=None, **_kwargs):
        posted.append({"url": url, "headers": headers, "body": json})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "本期 GEO 总分 72,基于 30 个采样,整体处于行业中段。"
                                "建议关注 V/S 维度的环比拆分。"
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    out = await narrate(_section(), _ctx())

    assert out is not None
    assert "GEO 总分 72" in out
    assert len(posted) == 1
    assert posted[0]["url"] == "https://api.example.invalid/v3/chat/completions"
    assert posted[0]["headers"]["Authorization"] == "Bearer test-key"
    assert posted[0]["body"]["model"] == "doubao-2"
    assert posted[0]["body"]["messages"][0]["role"] == "system"
    assert posted[0]["body"]["messages"][1]["role"] == "user"
    # User message carries the section payload as JSON
    user_content = posted[0]["body"]["messages"][1]["content"]
    assert "executive_summary" in user_content


@pytest.mark.asyncio
async def test_b2_4_no_credentials_falls_through_to_deterministic(monkeypatch):
    """Provider set but no API key → return None from LLM path, runs
    deterministic fallback. The fallback ALWAYS produces something."""
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "doubao")
    monkeypatch.delenv("DOUBAO_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_ARK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    out = await narrate(_section(), _ctx())
    # Deterministic fallback executes — non-empty narrative.
    assert out is not None
    assert "GEO" in out  # exec summary fallback always references geo_score


@pytest.mark.asyncio
async def test_b2_4_network_error_falls_through(monkeypatch):
    """RequestError from httpx → log + fallback. No exception escapes."""
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "doubao")
    monkeypatch.setenv("DOUBAO_API_KEY", "x")
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://api.example.invalid/v3")
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-2")

    async def boom(self, url, json=None, headers=None, **_kwargs):
        raise httpx.RequestError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)

    out = await narrate(_section(), _ctx())
    assert out is not None  # deterministic fallback


@pytest.mark.asyncio
async def test_b2_4_http_500_falls_through(monkeypatch):
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "doubao")
    monkeypatch.setenv("DOUBAO_API_KEY", "x")
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://api.example.invalid/v3")
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-2")

    async def fail(self, url, json=None, headers=None, **_kwargs):
        return httpx.Response(500, json={"error": "server down"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fail)

    out = await narrate(_section(), _ctx())
    assert out is not None


@pytest.mark.asyncio
async def test_b2_4_empty_completion_falls_through(monkeypatch):
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "doubao")
    monkeypatch.setenv("DOUBAO_API_KEY", "x")
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://api.example.invalid/v3")
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-2")

    async def empty(self, url, json=None, headers=None, **_kwargs):
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", empty)

    out = await narrate(_section(), _ctx())
    assert out is not None  # fallback ran


# ── env / provider resolution ───────────────────────────────


def test_b2_4_endpoint_resolution_doubao(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", "k")
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://example.invalid/v3")
    monkeypatch.setenv("DOUBAO_MODEL", "doubao-2")
    assert _resolve_llm_endpoint("doubao") == (
        "k",
        "https://example.invalid/v3",
        "doubao-2",
    )


def test_b2_4_endpoint_resolution_deepseek_uses_default_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    # No base url / model → defaults
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_NARRATIVE_MODEL", raising=False)
    api, base, model = _resolve_llm_endpoint("deepseek")
    assert api == "k"
    assert base == "https://api.deepseek.com/v1"
    assert model == "deepseek-chat"


def test_b2_4_endpoint_resolution_unknown_provider(monkeypatch):
    monkeypatch.setenv("FOO_API_KEY", "k")
    assert _resolve_llm_endpoint("foo") is None


def test_b2_4_endpoint_resolution_missing_key_returns_none(monkeypatch):
    monkeypatch.delenv("DOUBAO_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_ARK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://x.invalid")
    monkeypatch.setenv("DOUBAO_MODEL", "m")
    assert _resolve_llm_endpoint("doubao") is None


# ── prompt construction ─────────────────────────────────────


def test_b2_4_prompt_carries_section_payload_as_json():
    section = _section(
        section_type="competitor_comparison",
        summary="primary brand #2 in competitor set",
        metrics={"primary_id": 42, "competitor_count": 5},
        tables=[{"name": "competitors", "rows": [{"brand_id": 1, "geo_score": 80}]}],
    )
    messages = _build_messages(section, _ctx("zh-CN"))
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Simplified Chinese" in messages[0]["content"]
    user = messages[1]["content"]
    # User content has JSON payload
    json_part = user.partition("\n\n")[2]
    parsed = json.loads(json_part)
    assert parsed["section_type"] == "competitor_comparison"
    assert parsed["metrics"]["primary_id"] == 42
    assert parsed["tables"][0]["name"] == "competitors"


def test_b2_4_prompt_en_locale_uses_english_locale_hint():
    section = _section()
    messages = _build_messages(section, _ctx("en-US"))
    assert "English" in messages[0]["content"]
    assert "80-120 words" in messages[0]["content"]


def test_b2_4_trim_metrics_drops_none_and_caps_at_ten():
    raw = {f"k{i}": i for i in range(20)}
    raw["should_drop"] = None
    out = _trim_metrics(raw)
    assert "should_drop" not in out
    assert len(out) == 10


def test_b2_4_trim_metrics_stringifies_nested():
    out = _trim_metrics({"nested": {"a": 1, "b": [2, 3]}})
    assert isinstance(out["nested"], str)
    assert '"a"' in out["nested"]


def test_b2_4_trim_tables_keeps_first_3_rows_first_2_tables():
    tables = [
        {"name": "t1", "rows": [{"i": i} for i in range(10)]},
        {"name": "t2", "rows": [{"i": i} for i in range(10)]},
        {"name": "t3", "rows": [{"i": 0}]},
    ]
    out = _trim_tables(tables)
    assert len(out) == 2
    assert out[0]["name"] == "t1"
    assert len(out[0]["rows"]) == 3
    assert out[0]["row_count"] == 10  # full count preserved as metadata


# ── completion normalization ────────────────────────────────


def test_b2_4_normalize_strips_markdown_fence():
    txt = "```\nGEO score 72.\n```"
    assert _normalize_completion(txt) == "GEO score 72."


def test_b2_4_normalize_strips_leading_bullet():
    assert _normalize_completion("- Hello world.") == "Hello world."
    assert _normalize_completion('"quoted"') == 'quoted"'


def test_b2_4_normalize_collapses_whitespace():
    assert _normalize_completion("Hello   world\n\nfoo") == "Hello world foo"


def test_b2_4_normalize_returns_empty_for_empty_input():
    assert _normalize_completion("") == ""
    assert _normalize_completion("   \n   ") == ""


# ── idempotence ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_b2_4_existing_narrative_is_passthrough(monkeypatch):
    """Pre-set narrative is never overwritten — caller wins."""
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "doubao")
    monkeypatch.setenv("DOUBAO_API_KEY", "k")
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://x.invalid")
    monkeypatch.setenv("DOUBAO_MODEL", "m")

    posted: list = []

    async def trap(self, url, json=None, headers=None, **_kwargs):
        posted.append(url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "X"}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", trap)

    s = _section(narrative="pre-existing prose")
    out = await narrate(s, _ctx())
    assert out == "pre-existing prose"
    assert posted == []  # no HTTP call


@pytest.mark.asyncio
async def test_b2_4_provider_off_skips_llm_path(monkeypatch):
    """`LLM_NARRATIVE_PROVIDER=off` short-circuits to fallback, no HTTP."""
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "off")

    posted: list = []

    async def trap(self, url, json=None, headers=None, **_kwargs):
        posted.append(url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "X"}}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", trap)

    out = await narrate(_section(), _ctx())
    assert out is not None  # fallback ran
    assert posted == []  # no HTTP call
