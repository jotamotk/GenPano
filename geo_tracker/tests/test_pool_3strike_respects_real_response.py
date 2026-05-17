"""Refs #963 verify-readonly comment 4469641196 (2026-05-17T06:47:58Z) +
PR ``[#963] 3-strike ban: skip strike when query has real captured response``.

Background — the failure chain that motivated this fix:
  1. ``response_validation.doubao_persistence_auth_reason`` (Mode C class
     of false-positives) sometimes flags a real Doubao answer page as
     ``doubao_homepage_content`` / ``doubao_not_logged_in`` despite the
     scraper having persisted a 1000+ char real answer into the
     ``llm_responses`` table (e.g. Q-184971 raw_text=1255 starting with
     "是的，bestCoffer 企业级 AI 数据脱敏工具非常适合金融行业的多业务场景使
     用…", Q-184988 raw_text=1191 with the bestCoffer accuracy answer).
  2. ``execute_query`` calls ``settle_failure`` with that reason, which
     reaches ``AccountPool.report_failure`` since the reason is NOT in
     ``INFRASTRUCTURE_FAILURE_REASONS``.
  3. ``report_failure`` sees the reason in :data:`EXPIRED_ACCOUNT_REASONS`
     and increments ``expired_transition_count``; after 3 strikes the
     account is permanently banned (``account_no_active``).
  4. With Doubao's active pool already at ~3 accounts (per verify-readonly
     comment 4469641196: "5 of 7 recent failed Doubao queries are
     other:* — i.e. the dominant failure mode is account exhaustion"),
     the false-positive strike compounds the exhaustion and tightens the
     loop.

The fix passes ``query_id`` through ``settle_failure`` into
``report_failure``; when a real captured response (raw_text >=
:data:`STRIKE_SKIP_MIN_RAW_TEXT_CHARS` = 100) exists for the query, the
strike is SKIPPED. Status still transitions to ``expired`` (cookies may
genuinely need refresh), but the strike counter does not climb, so a
re-login can still recover the account before the 3rd false-positive
permanently bans it.

This is defense-in-depth: the orthogonal validator fix on
``claude/issue-963-validator-false-positive`` addresses the root cause
(stop generating false-positives in the first place). If a future
regression slips through that gate, this strike-layer guard still
prevents account exhaustion when there is hard evidence of capture
success (a long ``llm_responses.raw_text`` row).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AccountStatus,
    Base,
    LLMAccount,
    LLMResponse,
    Query,
)
from geo_tracker.pool.account_pool import (
    STRIKE_SKIP_MIN_RAW_TEXT_CHARS,
    AccountPool,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as db:
        yield db
    await engine.dispose()


# Q-184971 verify-readonly evidence (issue #963 comment 4469641196):
# the persisted llm_responses.raw_text was a 1255-char real Doubao answer
# starting with the substring below. Reproduce the exact length in tests
# so the threshold check is anchored to production data, not a synthetic
# string short enough to look like login chrome.
Q184971_RAW_TEXT_SAMPLE_PREFIX = (
    "是的，bestCoffer 企业级 AI 数据脱敏工具非常适合金融行业的多业务"
    "场景使用。"
)
Q184971_RAW_TEXT_LEN = 1255


def _doubao_account(account_id: int = 47, **overrides) -> LLMAccount:
    """Build a Doubao LLMAccount with sensible defaults.

    Default ``account_id=47`` matches the Q-184971 / account-47 evidence in
    issue #963 comment 4469641196 so the failure case in the regression
    tests mirrors a real production row identifier.
    """
    fields = {
        "id": account_id,
        "llm_name": "doubao",
        "email": f"acc{account_id}@local",
        "phone_number": f"100000{account_id:04d}",
        "cookies_json": '[{"name": "a", "value": "b"}]',
        "daily_limit": 20,
        "query_count_today": 0,
        "consecutive_fails": 0,
        "expired_transition_count": 0,
        "status": AccountStatus.ACTIVE.value,
    }
    fields.update(overrides)
    return LLMAccount(**fields)


def _query(query_id: int, account_id: int, retry_reason: str | None = None) -> Query:
    return Query(
        id=query_id,
        query_text="bestCoffer 企业级 AI 数据脱敏工具适合金融行业吗",
        target_llm="doubao",
        status="failed",
        retry_reason=retry_reason,
        account_id=account_id,
        retry_count=0,
    )


def _response(query_id: int, raw_text: str) -> LLMResponse:
    return LLMResponse(query_id=query_id, raw_text=raw_text)


# ─── Test 1 — Q-184971 anchor: real captured response must NOT strike ────────


@pytest.mark.asyncio
async def test_q184971_anchor_real_captured_response_skips_strike(
    session: AsyncSession,
) -> None:
    """Q-184971 reproduction (issue #963 comment 4469641196): account 47 had a
    query whose ``llm_responses.raw_text`` was 1255 chars of real Doubao
    answer ("是的，bestCoffer 企业级 AI 数据脱敏工具非常适合金融行业的多业务
    场景使用…"), yet a Mode-C validator false-positive caused the failure
    to be reported with a reason in EXPIRED_ACCOUNT_REASONS. The strike
    layer must NOT increment ``expired_transition_count`` for this case —
    the captured response is hard evidence the account served a real
    answer, so a strike toward the 3-strike permanent ban is a false
    punishment.
    """
    session.add(_doubao_account(account_id=47))
    await session.commit()

    # Seed a query + a real 1255-char response, matching Q-184971's row.
    # raw_text is built up by repeating the captured prefix so the
    # persisted length matches production (1255 chars exactly).
    repeat_count = (Q184971_RAW_TEXT_LEN // len(Q184971_RAW_TEXT_SAMPLE_PREFIX)) + 1
    raw_text = (Q184971_RAW_TEXT_SAMPLE_PREFIX * repeat_count)[:Q184971_RAW_TEXT_LEN]
    assert len(raw_text) == Q184971_RAW_TEXT_LEN, (
        "Q-184971 fixture must reproduce the 1255-char raw_text seen in "
        "production (issue #963 comment 4469641196)"
    )
    session.add(_query(184971, account_id=47, retry_reason="no_response"))
    session.add(_response(184971, raw_text))
    await session.commit()

    pool = AccountPool(session)

    # Mode-C false-positive: validator reports a reason in
    # EXPIRED_ACCOUNT_REASONS even though the response was captured.
    # ``doubao_homepage_content`` is the exact reason that production
    # produces for this class of false-positive (see EXPIRED_ACCOUNT_REASONS
    # comment in pool/account_pool.py).
    await pool.report_failure(
        47,
        reason="doubao_homepage_content",
        query_id=184971,
    )

    acc = await session.get(LLMAccount, 47)
    assert acc.expired_transition_count == 0, (
        "Account 47 had a 1255-char real captured response for Q-184971; "
        "the 3-strike layer must not punish it toward account_no_active. "
        "If this assertion regresses, a Mode-C-style validator "
        "false-positive can again drain Doubao accounts."
    )
    # Status still flips to expired — cookies may genuinely need refresh,
    # and that path is unaffected by this fix. This is the additive
    # contract: skip the strike only; do not touch the expired transition.
    assert acc.status == AccountStatus.EXPIRED.value


# ─── Test 2 — no response row: real failure must STILL strike ────────────────


@pytest.mark.asyncio
async def test_real_failure_with_no_response_row_still_strikes(
    session: AsyncSession,
) -> None:
    """Negative control: when ``no_response`` reaches ``report_failure`` for a
    query that has NO ``llm_responses`` row at all, the strike MUST still
    fire. The fix is narrow — defense against captured-real-answer
    false-positives only — and must NOT regress the legitimate
    cookies-actually-expired path that the 3-strike layer was built for.
    """
    session.add(_doubao_account(account_id=48))
    # Query exists but no llm_responses row — i.e. real "we never got an
    # answer" failure, not a validator false-positive.
    session.add(_query(184990, account_id=48, retry_reason="no_response"))
    await session.commit()

    pool = AccountPool(session)

    # ``doubao_not_logged_in`` is the canonical real-auth-failure reason and
    # sits in EXPIRED_ACCOUNT_REASONS. The strike must fire.
    await pool.report_failure(
        48,
        reason="doubao_not_logged_in",
        query_id=184990,
    )
    acc = await session.get(LLMAccount, 48)
    assert acc.expired_transition_count == 1, (
        "Query with no captured response is a real failure; strike must "
        "still fire so the 3-strike permanent ban kicks in after 3 such "
        "failures. Removing this would re-introduce the expired-ricochet "
        "bug that PR #1102 originally fixed."
    )
    assert acc.status == AccountStatus.EXPIRED.value


# ─── Boundary tests: threshold semantics + missing-query-id fallback ─────────


@pytest.mark.asyncio
async def test_short_response_below_threshold_still_strikes(
    session: AsyncSession,
) -> None:
    """Boundary: a captured response shorter than
    :data:`STRIKE_SKIP_MIN_RAW_TEXT_CHARS` (e.g. 50 chars — typical login-page
    chrome length) must NOT bypass the strike. Login-page text fits below
    the threshold; only a real answer reliably crosses it.
    """
    session.add(_doubao_account(account_id=49))
    session.add(_query(184991, account_id=49))
    # 50 chars — looks like UI chrome, not a real answer.
    session.add(_response(184991, "请登录后继续使用 / Please log in to continue."[:50]))
    await session.commit()

    pool = AccountPool(session)
    await pool.report_failure(
        49,
        reason="doubao_not_logged_in",
        query_id=184991,
    )
    acc = await session.get(LLMAccount, 49)
    assert acc.expired_transition_count == 1, (
        "Short captured text (login chrome) does not constitute real "
        "answer evidence; strike must still fire."
    )


@pytest.mark.asyncio
async def test_missing_query_id_keeps_legacy_strike_behavior(
    session: AsyncSession,
) -> None:
    """When ``query_id`` is None (cookie keep-alive probe, manual cooldown
    writes), the strike behavior is unchanged from PR #1102. This keeps
    the fix narrow and ensures non-query call sites are not silently
    weakened.
    """
    session.add(_doubao_account(account_id=50))
    await session.commit()
    pool = AccountPool(session)

    await pool.report_failure(50, reason="doubao_not_logged_in")
    acc = await session.get(LLMAccount, 50)
    assert acc.expired_transition_count == 1


@pytest.mark.asyncio
async def test_non_expired_reason_unaffected_by_response_check(
    session: AsyncSession,
) -> None:
    """``rate_limit`` is NOT in EXPIRED_ACCOUNT_REASONS, so the
    captured-response check must never run for it. This guards against
    accidentally widening the gate beyond the targeted false-positive
    class.
    """
    session.add(_doubao_account(account_id=51))
    session.add(_query(184992, account_id=51))
    session.add(_response(184992, "x" * (STRIKE_SKIP_MIN_RAW_TEXT_CHARS + 50)))
    await session.commit()

    pool = AccountPool(session)
    await pool.report_failure(
        51,
        reason="rate_limit",
        query_id=184992,
    )
    acc = await session.get(LLMAccount, 51)
    # rate_limit goes to COOLDOWN per existing semantics and never touches
    # the expired counter — the captured-response branch must be inert.
    assert acc.expired_transition_count == 0
    assert acc.status == AccountStatus.COOLDOWN.value


@pytest.mark.asyncio
async def test_threshold_constant_matches_validator_whitelist(
    session: AsyncSession,
) -> None:
    """The strike-skip threshold must match the
    ``.flow-markdown-body >= 100`` answer-whitelist gate in
    ``response_validation.doubao_persistence_auth_reason``. If a future
    edit desynchronizes the two layers (one accepts at 100 chars, the
    other at 200), Mode-C protection could be silently weakened.
    Asserting the literal value here forces a deliberate cross-file
    review on any change.
    """
    assert STRIKE_SKIP_MIN_RAW_TEXT_CHARS == 100, (
        "STRIKE_SKIP_MIN_RAW_TEXT_CHARS must stay aligned with the "
        "100-char answer whitelist in response_validation. Update both "
        "or neither."
    )


@pytest.mark.asyncio
async def test_first_time_false_positive_in_memory_response_skips_strike(
    session: AsyncSession,
) -> None:
    """Refs #963 Codex P1 on PR #1109: at the post-extract Doubao failure
    branches in ``celery_tasks.execute_query`` (lines 1136 and 1176), the
    ``LLMResponse`` row has NOT yet been inserted into ``llm_responses``
    — the DB insert is on the success path (``db.add(response)`` at line
    1223). For a FIRST-TIME Mode-C false-positive there is therefore no
    orphan row to find via the DB lookup, and without an in-memory
    response thread the strike fires anyway, defeating the defense.

    This regression test asserts that passing the in-memory
    ``response_text`` (the captured ``response.raw_text`` from the
    just-finished browser run) is sufficient to skip the strike — the
    DB query is not consulted. This mirrors the production live-path
    where ``response_validation.doubao_persistence_auth_reason``
    misclassifies a fresh real answer.
    """
    session.add(_doubao_account(account_id=70))
    # Query exists but NO llm_responses row yet — first-time failure
    # before db.add(response) runs.
    session.add(_query(190001, account_id=70, retry_reason="doubao_homepage_content"))
    await session.commit()

    pool = AccountPool(session)

    # In-memory captured response — 1255 chars matches Q-184971's
    # raw_text length anchored to verify-readonly evidence.
    real_answer_in_memory = (
        "是的，bestCoffer 企业级 AI 数据脱敏工具非常适合金融行业的多业务"
        "场景使用。 其从功能设计、合规适配到实际案例，均深度贴合金融行业"
        "的高敏感、强监管、多场景需求。 一、核心金融场景全覆盖 监管报送"
        "与合规审计 痛点：需向央行、金监总局报送 KYC 记录、反洗钱报告等"
    )
    assert len(real_answer_in_memory) >= 100, (
        "Test fixture must exceed STRIKE_SKIP_MIN_RAW_TEXT_CHARS to "
        "exercise the bypass path."
    )

    await pool.report_failure(
        70,
        reason="doubao_homepage_content",
        query_id=190001,
        response_text=real_answer_in_memory,
    )

    acc = await session.get(LLMAccount, 70)
    assert acc.expired_transition_count == 0, (
        "First-time Mode-C false-positive (response captured in-memory "
        "but llm_responses row not yet persisted) MUST skip the strike. "
        "The in-memory response_text was passed explicitly; the DB "
        "lookup would have returned no row at this point. Without this "
        "guard, the validator false-positive class would still burn "
        f"accounts on the first occurrence — current count: {acc.expired_transition_count}."
    )
    # Status still flips to EXPIRED so the re-login cycle can still run.
    assert acc.status == AccountStatus.EXPIRED.value


@pytest.mark.asyncio
async def test_short_in_memory_response_still_strikes(
    session: AsyncSession,
) -> None:
    """Boundary control for the new ``response_text`` parameter: a SHORT
    in-memory response (below the 100-char threshold, e.g. 50 chars of
    login-page chrome that survived a partial scrape) must NOT bypass
    the strike. The threshold guards against treating UI chrome as a
    real answer.
    """
    session.add(_doubao_account(account_id=71))
    session.add(_query(190002, account_id=71, retry_reason="doubao_not_logged_in"))
    await session.commit()

    pool = AccountPool(session)
    # 50 chars — fits typical login chrome lengths, below the 100-char
    # answer-whitelist threshold.
    short_chrome_text = "请登录后继续使用 / Please log in to continue using"
    assert len(short_chrome_text) < 100

    await pool.report_failure(
        71,
        reason="doubao_not_logged_in",
        query_id=190002,
        response_text=short_chrome_text,
    )

    acc = await session.get(LLMAccount, 71)
    assert acc.expired_transition_count == 1, (
        "Short in-memory text (likely login chrome) must NOT bypass the "
        "strike — only text >= STRIKE_SKIP_MIN_RAW_TEXT_CHARS qualifies "
        "as evidence of a real captured answer."
    )
