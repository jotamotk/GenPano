"""Durable analyzer task handoff helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import AnalysisStatus, AnalyzerRun, LLMResponse


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def mark_analyzer_run_handoff_failed(
    session: AsyncSession,
    *,
    analyzer_run_id: int,
    response_id: int | None,
    failure_code: str,
    failure_message: str,
    previous_analysis_status: str | None = None,
) -> dict[str, Any]:
    run = await session.get(AnalyzerRun, int(analyzer_run_id))
    if run is None:
        return {
            "response_id": response_id,
            "status": "failed",
            "error": "analyzer_run_not_found",
            "analyzer_run_id": analyzer_run_id,
        }

    run.status = "failed"
    run.completed_at = _utcnow_naive()
    run.failure_code = failure_code
    run.failure_message = failure_message

    if response_id is not None:
        response = await session.get(LLMResponse, int(response_id))
        if response is not None:
            preserve_status = previous_analysis_status or response.analysis_status
            if str(preserve_status or "").lower() == AnalysisStatus.DONE.value:
                response.analysis_status = AnalysisStatus.DONE.value
            else:
                response.analysis_status = AnalysisStatus.FAILED.value

    await session.commit()
    return {
        "response_id": response_id,
        "status": "failed",
        "error": failure_code,
        "analyzer_run_id": int(analyzer_run_id),
    }
