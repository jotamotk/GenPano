from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import (
    AnalysisStatus,
    AnalyzerQualityFlag,
    AnalyzerRun,
    LLMResponse,
    ResponseAnalysis,
)

ACTIVE_ANALYZER_RUN_STATUSES = {"queued", "running"}
DEFAULT_STALE_ACTIVE_ANALYZER_RUN_SECONDS = 30 * 60
STALE_ACTIVE_ANALYZER_RUN_CODE = "stale_active_analyzer_run_recovered"


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class AnalyzerRunRecoveryResult:
    response_id: int
    active_run_id: int | None = None
    active_run_status: str | None = None
    active_run_started_at: str | None = None
    recovered: bool = False
    blocked: bool = False
    reason: str | None = None
    age_seconds: float | None = None
    has_analysis: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "active_run_id": self.active_run_id,
            "active_run_status": self.active_run_status,
            "active_run_started_at": self.active_run_started_at,
            "recovered": self.recovered,
            "blocked": self.blocked,
            "reason": self.reason,
            "age_seconds": self.age_seconds,
            "has_analysis": self.has_analysis,
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _run_age_seconds(run: AnalyzerRun, now: datetime) -> float | None:
    if run.started_at is None:
        return None
    return max((now - run.started_at).total_seconds(), 0.0)


async def find_active_analyzer_run(
    session: AsyncSession,
    response_id: int,
) -> AnalyzerRun | None:
    return await session.scalar(
        select(AnalyzerRun)
        .where(
            AnalyzerRun.response_id == int(response_id),
            AnalyzerRun.status.in_(sorted(ACTIVE_ANALYZER_RUN_STATUSES)),
        )
        .order_by(AnalyzerRun.started_at.desc(), AnalyzerRun.id.desc())
        .limit(1)
    )


async def summarize_active_analyzer_run(
    session: AsyncSession,
    *,
    response_id: int,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_STALE_ACTIVE_ANALYZER_RUN_SECONDS,
) -> AnalyzerRunRecoveryResult:
    now = now or _utcnow_naive()
    run = await find_active_analyzer_run(session, response_id)
    has_analysis = await _has_response_analysis(session, response_id)
    if run is None:
        return AnalyzerRunRecoveryResult(
            response_id=int(response_id),
            has_analysis=has_analysis,
            reason="no_active_analyzer_run",
        )

    age_seconds = _run_age_seconds(run, now)
    blocked_reason = _active_run_block_reason(
        run,
        age_seconds=age_seconds,
        stale_after_seconds=stale_after_seconds,
        has_analysis=has_analysis,
    )
    return AnalyzerRunRecoveryResult(
        response_id=int(response_id),
        active_run_id=int(run.id),
        active_run_status=str(run.status),
        active_run_started_at=_iso(run.started_at),
        blocked=blocked_reason is not None,
        reason=blocked_reason or "stale_active_analyzer_run_recoverable",
        age_seconds=age_seconds,
        has_analysis=has_analysis,
    )


async def recover_stale_active_analyzer_run(
    session: AsyncSession,
    *,
    response_id: int,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_STALE_ACTIVE_ANALYZER_RUN_SECONDS,
) -> AnalyzerRunRecoveryResult:
    now = now or _utcnow_naive()
    run = await find_active_analyzer_run(session, response_id)
    has_analysis = await _has_response_analysis(session, response_id)
    if run is None:
        return AnalyzerRunRecoveryResult(
            response_id=int(response_id),
            has_analysis=has_analysis,
            reason="no_active_analyzer_run",
        )

    age_seconds = _run_age_seconds(run, now)
    blocked_reason = _active_run_block_reason(
        run,
        age_seconds=age_seconds,
        stale_after_seconds=stale_after_seconds,
        has_analysis=has_analysis,
    )
    if blocked_reason is not None:
        return AnalyzerRunRecoveryResult(
            response_id=int(response_id),
            active_run_id=int(run.id),
            active_run_status=str(run.status),
            active_run_started_at=_iso(run.started_at),
            blocked=True,
            reason=blocked_reason,
            age_seconds=age_seconds,
            has_analysis=has_analysis,
        )

    run.status = "failed"
    run.completed_at = now
    run.failure_code = STALE_ACTIVE_ANALYZER_RUN_CODE
    run.failure_message = (
        "Recovered stale active analyzer run before retrying the same response. "
        f"started_at={_iso(run.started_at)} age_seconds={age_seconds:.0f}"
    )
    response = await session.get(LLMResponse, int(response_id))
    if response is not None and response.analysis_status == AnalysisStatus.RUNNING.value:
        response.analysis_status = AnalysisStatus.PENDING.value
    session.add(
        AnalyzerQualityFlag(
            run_id=int(run.id),
            response_id=int(response_id),
            flag_key="flag_stale_active_analyzer_run_recovered_analysis",
            severity="error",
            code=STALE_ACTIVE_ANALYZER_RUN_CODE,
            message=run.failure_message,
            target_type="analysis",
            target_key=None,
            blocks_metric_readiness=True,
            evidence_json={
                "active_run_id": int(run.id),
                "active_run_started_at": _iso(run.started_at),
                "age_seconds": age_seconds,
                "stale_after_seconds": stale_after_seconds,
            },
        )
    )
    await session.flush()
    return AnalyzerRunRecoveryResult(
        response_id=int(response_id),
        active_run_id=int(run.id),
        active_run_status="failed",
        active_run_started_at=_iso(run.started_at),
        recovered=True,
        reason=STALE_ACTIVE_ANALYZER_RUN_CODE,
        age_seconds=age_seconds,
        has_analysis=has_analysis,
    )


async def _has_response_analysis(session: AsyncSession, response_id: int) -> bool:
    return (
        await session.scalar(
            select(ResponseAnalysis.id)
            .where(ResponseAnalysis.response_id == int(response_id))
            .limit(1)
        )
    ) is not None


def _active_run_block_reason(
    run: AnalyzerRun,
    *,
    age_seconds: float | None,
    stale_after_seconds: int,
    has_analysis: bool,
) -> str | None:
    if str(run.status or "").lower() not in ACTIVE_ANALYZER_RUN_STATUSES:
        return "active_run_status_not_active"
    if has_analysis:
        return "active_run_has_existing_analysis"
    if age_seconds is None:
        return "active_run_started_at_missing"
    if age_seconds < stale_after_seconds:
        return "active_analyzer_run_in_progress"
    return None
