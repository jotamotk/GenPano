from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from geo_tracker.db.models import (
    AccountStatus,
    Base,
    LLMAccount,
    LLMResponse,
    QuotaCounterRepair,
    Query,
    QueryStatus,
)
from geo_tracker.tasks import quota_counter_repair
from geo_tracker.tasks.quota_counter_repair import (
    RepairBlocked,
    apply_quota_repair_plan,
    build_quota_repair_report,
    build_quota_repair_payload,
    validate_deployed_code_sha,
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


async def _account(
    session: AsyncSession,
    *,
    account_id: int,
    llm_name: str,
    query_count_today: int,
    daily_limit: int = 20,
) -> LLMAccount:
    account = LLMAccount(
        id=account_id,
        llm_name=llm_name,
        status=AccountStatus.ACTIVE.value,
        cookies_json='[{"name":"session","value":"ok"}]',
        query_count_today=query_count_today,
        daily_limit=daily_limit,
    )
    session.add(account)
    await session.commit()
    return account


def _query(
    query_id: int,
    *,
    account_id: int | None,
    target_llm: str,
    reason: str | None,
    event_at: datetime,
    status: str = QueryStatus.FAILED.value,
) -> Query:
    return Query(
        id=query_id,
        account_id=account_id,
        target_llm=target_llm,
        query_text=f"query {query_id}",
        status=status,
        retry_reason=reason,
        started_at=event_at,
        finished_at=event_at,
        created_at=event_at,
    )


@pytest.mark.asyncio
async def test_report_selects_only_current_day_non_consuming_unresponded_account_attempts(
    session: AsyncSession,
):
    day_start = datetime(2026, 5, 11)
    await _account(
        session,
        account_id=10,
        llm_name="chatgpt",
        query_count_today=5,
    )
    await _account(
        session,
        account_id=11,
        llm_name="deepseek",
        query_count_today=3,
    )

    included_1 = _query(
        101,
        account_id=10,
        target_llm="chatgpt",
        reason="no_response",
        event_at=day_start + timedelta(hours=1),
    )
    included_2 = _query(
        102,
        account_id=10,
        target_llm="chatgpt",
        reason="browser_timeout",
        event_at=day_start + timedelta(hours=2),
    )
    included_3 = _query(
        103,
        account_id=11,
        target_llm="deepseek",
        reason="soft_time_limit",
        event_at=day_start + timedelta(hours=3),
    )
    consuming_failure = _query(
        104,
        account_id=10,
        target_llm="chatgpt",
        reason="cookies_expired",
        event_at=day_start + timedelta(hours=4),
    )
    successful = _query(
        105,
        account_id=10,
        target_llm="chatgpt",
        reason=None,
        event_at=day_start + timedelta(hours=5),
        status=QueryStatus.DONE.value,
    )
    previous_day = _query(
        106,
        account_id=10,
        target_llm="chatgpt",
        reason="no_input",
        event_at=day_start - timedelta(minutes=1),
    )
    no_account = _query(
        107,
        account_id=None,
        target_llm="chatgpt",
        reason="page_load_failed",
        event_at=day_start + timedelta(hours=6),
    )
    ambiguous_exception = _query(
        108,
        account_id=11,
        target_llm="deepseek",
        reason="exception",
        event_at=day_start + timedelta(hours=7),
    )
    has_response = _query(
        109,
        account_id=11,
        target_llm="deepseek",
        reason="browser_timeout",
        event_at=day_start + timedelta(hours=8),
    )
    session.add_all(
        [
            included_1,
            included_2,
            included_3,
            consuming_failure,
            successful,
            previous_day,
            no_account,
            ambiguous_exception,
            has_response,
        ]
    )
    session.add(
        LLMResponse(
            query_id=109,
            raw_text="platform returned text before persistence failed",
            response_time_ms=1000,
        )
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )

    assert report.candidate_query_ids == [101, 102, 103]
    assert report.manual_review_query_ids == [108]
    assert report.total_refundable_attempts == 3
    assert [
        (item.engine, item.account_id, item.reason, item.refundable_attempts)
        for item in report.groups
    ] == [
        ("chatgpt", 10, "browser_timeout", 1),
        ("chatgpt", 10, "no_response", 1),
        ("deepseek", 11, "soft_time_limit", 1),
    ]
    assert [
        (
            item.engine,
            item.account_id,
            item.current_query_count_today,
            item.proposed_delta,
            item.after_query_count_today,
            item.safe_to_apply,
        )
        for item in report.account_plans
    ] == [
        ("chatgpt", 10, 5, 2, 3, True),
        ("deepseek", 11, 3, 1, 2, True),
    ]
    assert json.loads(json.dumps(report.to_dict()))["total_refundable_attempts"] == 3


@pytest.mark.asyncio
async def test_underflow_dry_run_blocks_without_negative_after_counter(
    session: AsyncSession,
):
    day_start = datetime(2026, 5, 11)
    await _account(
        session,
        account_id=19,
        llm_name="chatgpt",
        query_count_today=1,
    )
    session.add_all(
        [
            _query(
                191,
                account_id=19,
                target_llm="chatgpt",
                reason="no_response",
                event_at=day_start + timedelta(hours=1),
            ),
            _query(
                192,
                account_id=19,
                target_llm="chatgpt",
                reason="page_load_failed",
                event_at=day_start + timedelta(hours=2),
            ),
        ]
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )
    payload = build_quota_repair_payload(report, mode="dry_run")

    assert report.total_refundable_attempts == 2
    assert report.account_plans[0].safe_to_apply is False
    assert report.account_plans[0].proposed_delta == 0
    assert report.account_plans[0].unapplied_delta == 2
    assert report.account_plans[0].after_query_count_today == 1
    assert report.account_plans[0].after_query_count_today >= 0
    assert "counter_underflow" in report.account_plans[0].unsafe_reasons
    assert payload["ok"] is False
    assert payload["blocked"] is True
    assert "counter_underflow" in payload["error"]
    assert (
        payload["report"]["account_plans"][0]["after_query_count_today"] >= 0
    )


@pytest.mark.asyncio
async def test_apply_guard_blocks_counter_underflow_and_exact_total_mismatch(
    session: AsyncSession,
):
    day_start = datetime(2026, 5, 11)
    account = await _account(
        session,
        account_id=20,
        llm_name="chatgpt",
        query_count_today=1,
    )
    session.add_all(
        [
            _query(
                201,
                account_id=20,
                target_llm="chatgpt",
                reason="no_response",
                event_at=day_start + timedelta(hours=1),
            ),
            _query(
                202,
                account_id=20,
                target_llm="chatgpt",
                reason="page_load_failed",
                event_at=day_start + timedelta(hours=2),
            ),
        ]
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )

    assert report.account_plans[0].proposed_delta == 0
    assert report.account_plans[0].unapplied_delta == 2
    assert report.account_plans[0].after_query_count_today == 1
    assert report.account_plans[0].safe_to_apply is False

    with pytest.raises(RepairBlocked, match="would drop below zero"):
        await apply_quota_repair_plan(
            session,
            report,
            expected_total_delta=2,
            current_service_day_start=day_start,
        )
    await session.refresh(account)
    assert account.query_count_today == 1

    account.query_count_today = 3
    await session.commit()
    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )

    with pytest.raises(RepairBlocked, match="expected_total_delta"):
        await apply_quota_repair_plan(
            session,
            report,
            expected_total_delta=1,
            current_service_day_start=day_start,
        )
    await session.refresh(account)
    assert account.query_count_today == 3

    applied = await apply_quota_repair_plan(
        session,
        report,
        expected_total_delta=2,
        current_service_day_start=day_start,
        approval_ref="https://github.com/jotamotk/X/issues/519#issuecomment-1",
    )
    await session.refresh(account)

    assert applied.total_delta == 2
    assert account.query_count_today == 1


@pytest.mark.asyncio
async def test_repeated_apply_cannot_double_refund_same_query_ids(session: AsyncSession):
    day_start = datetime(2026, 5, 11)
    account = await _account(
        session,
        account_id=30,
        llm_name="chatgpt",
        query_count_today=3,
    )
    session.add_all(
        [
            _query(
                301,
                account_id=30,
                target_llm="chatgpt",
                reason="no_response",
                event_at=day_start + timedelta(hours=1),
            ),
            _query(
                302,
                account_id=30,
                target_llm="chatgpt",
                reason="no_input",
                event_at=day_start + timedelta(hours=2),
            ),
        ]
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )
    applied = await apply_quota_repair_plan(
        session,
        report,
        expected_total_delta=2,
        current_service_day_start=day_start,
        approval_ref="https://github.com/jotamotk/X/issues/519#issuecomment-2",
    )
    await session.refresh(account)
    assert applied.total_delta == 2
    assert account.query_count_today == 1

    repairs = (
        await session.execute(
            select(QuotaCounterRepair.query_id).order_by(QuotaCounterRepair.query_id)
        )
    ).scalars().all()
    assert repairs == [301, 302]

    with pytest.raises(RepairBlocked, match="already repaired"):
        await apply_quota_repair_plan(
            session,
            report,
            expected_total_delta=2,
            current_service_day_start=day_start,
            approval_ref="https://github.com/jotamotk/X/issues/519#issuecomment-2",
        )
    await session.refresh(account)
    assert account.query_count_today == 1

    next_report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )
    assert next_report.candidate_query_ids == []
    assert next_report.repaired_query_ids == [301, 302]


@pytest.mark.asyncio
async def test_old_window_apply_is_blocked_after_service_day_reset(session: AsyncSession):
    old_day_start = datetime(2026, 5, 10)
    current_day_start = old_day_start + timedelta(days=1)
    account = await _account(
        session,
        account_id=40,
        llm_name="deepseek",
        query_count_today=5,
    )
    session.add(
        _query(
            401,
            account_id=40,
            target_llm="deepseek",
            reason="page_load_failed",
            event_at=old_day_start + timedelta(hours=23),
        )
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=old_day_start,
        service_day_end=current_day_start,
    )

    with pytest.raises(RepairBlocked, match="current service day"):
        await apply_quota_repair_plan(
            session,
            report,
            expected_total_delta=1,
            current_service_day_start=current_day_start,
            approval_ref="https://github.com/jotamotk/X/issues/519#issuecomment-3",
        )
    await session.refresh(account)
    assert account.query_count_today == 5


@pytest.mark.asyncio
async def test_cross_midnight_attempt_uses_start_day_not_finished_day(
    session: AsyncSession,
):
    day_start = datetime(2026, 5, 11)
    previous_day_start = day_start - timedelta(days=1)
    await _account(
        session,
        account_id=50,
        llm_name="chatgpt",
        query_count_today=2,
    )
    query = _query(
        501,
        account_id=50,
        target_llm="chatgpt",
        reason="browser_timeout",
        event_at=day_start + timedelta(minutes=1),
    )
    query.started_at = day_start - timedelta(minutes=1)
    query.executed_at = day_start - timedelta(minutes=1)
    session.add(query)
    await session.commit()

    current_day_report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )
    previous_day_report = await build_quota_repair_report(
        session,
        service_day_start=previous_day_start,
        service_day_end=day_start,
    )

    assert current_day_report.candidate_query_ids == []
    assert previous_day_report.candidate_query_ids == [501]


@pytest.mark.asyncio
async def test_query_account_engine_mismatch_is_unsafe_and_not_applied(
    session: AsyncSession,
):
    day_start = datetime(2026, 5, 11)
    account = await _account(
        session,
        account_id=60,
        llm_name="chatgpt",
        query_count_today=2,
    )
    session.add(
        _query(
            601,
            account_id=60,
            target_llm="deepseek",
            reason="no_response",
            event_at=day_start + timedelta(hours=1),
        )
    )
    await session.commit()

    report = await build_quota_repair_report(
        session,
        service_day_start=day_start,
        service_day_end=day_start + timedelta(days=1),
    )

    assert report.account_plans[0].safe_to_apply is False
    assert "engine_mismatch" in report.account_plans[0].unsafe_reasons
    with pytest.raises(RepairBlocked, match="engine_mismatch"):
        await apply_quota_repair_plan(
            session,
            report,
            expected_total_delta=1,
            current_service_day_start=day_start,
            approval_ref="https://github.com/jotamotk/X/issues/519#issuecomment-4",
        )
    await session.refresh(account)
    assert account.query_count_today == 2


def test_deployed_code_sha_guard_rejects_mismatch_and_invalid_values():
    reviewed = "a" * 40

    assert validate_deployed_code_sha(reviewed, reviewed) == reviewed
    with pytest.raises(RepairBlocked, match="deployed code SHA mismatch"):
        validate_deployed_code_sha(reviewed, "b" * 40)
    with pytest.raises(RepairBlocked, match="40-character git SHA"):
        validate_deployed_code_sha("not-a-sha", reviewed)


def test_main_returns_nonzero_for_blocked_dry_run_payload(monkeypatch, capsys):
    async def fake_run_cli(args):
        return {
            "ok": False,
            "mode": "dry_run",
            "blocked": True,
            "blocking_reasons": ["counter_underflow"],
            "error": "repair would drop below zero; unsafe reasons=counter_underflow",
            "report": {"account_plans": []},
        }

    monkeypatch.setattr(quota_counter_repair, "_run_cli", fake_run_cli)

    assert quota_counter_repair.main(["--dry-run"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is False
    assert output["blocked"] is True
