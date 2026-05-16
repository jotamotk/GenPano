"""Phase N triggers — auto-create alerts from upstream events.

Plan §D8 (Alert linkage): a diagnostic at severity P0/P1 should
automatically write an `alerts` row so the FE bell badge surfaces it.
This module owns the diagnostic→alert side. Other triggers
(monitoring_outage / citation_mismatch / competitor_overtake) ride on
top of the same diagnostic→alert path because each is implemented as a
diagnostic rule (Phase D rules: MonitoringOutageRule,
CitationVolumeDropRule, CompetitorOvertakeRule).

The trigger is best-effort: failing to create an alert MUST NOT prevent
the diagnostic from being persisted. Callers wrap in try/except.
"""

from __future__ import annotations

import logging
import uuid

from genpano_models import Alert, Diagnostic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


SEVERITY_ALERT_THRESHOLD = {"P0", "P1"}


def _new_id() -> str:
    return str(uuid.uuid4())


async def create_alert_from_diagnostic(
    session: AsyncSession,
    diagnostic: Diagnostic,
    *,
    autocommit: bool = True,
) -> Alert | None:
    """Create one `alerts` row when diagnostic severity is P0 or P1.

    Returns the created Alert or None when the diagnostic doesn't
    qualify or when an alert already exists for this diagnostic.

    The created alert carries:
        source = 'diagnostic'
        source_ref_id = diagnostic.id
        scope = 'user' (FE bell — admin operator scope is a separate path)
        title = diagnostic.title
        body = diagnostic.description
    """
    if diagnostic.severity not in SEVERITY_ALERT_THRESHOLD:
        return None

    # Dedup: at most one alert per (source, source_ref_id). Without this
    # guard, every evaluator retry (manual refresh, periodic re-eval)
    # inserts a duplicate bell-badge entry. There's no UniqueConstraint
    # on alerts(source, source_ref_id) yet, so we enforce in code.
    existing_stmt = select(Alert).where(
        Alert.source == "diagnostic",
        Alert.source_ref_id == diagnostic.id,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        return None

    alert = Alert(
        id=_new_id(),
        project_id=diagnostic.project_id,
        brand_id=diagnostic.brand_id,
        source="diagnostic",
        source_ref_id=diagnostic.id,
        severity=diagnostic.severity,
        scope="user",
        title=diagnostic.title,
        body=diagnostic.description,
        status="unread",
    )
    try:
        session.add(alert)
        if autocommit:
            await session.commit()
            await session.refresh(alert)
        return alert
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("create_alert_from_diagnostic failed: %s", exc)
        try:
            await session.rollback()
        except Exception:
            pass
        return None


async def resolve_alert_for_diagnostic(
    session: AsyncSession,
    diagnostic: Diagnostic,
) -> int:
    """Mark linked alerts as resolved when diagnostic transitions to resolved.

    Returns the number of alerts updated. Idempotent.
    """
    if diagnostic.status != "resolved":
        return 0
    from datetime import UTC, datetime

    from sqlalchemy import update

    now = datetime.now(UTC).replace(tzinfo=None)
    stmt = (
        update(Alert)
        .where(
            Alert.source == "diagnostic",
            Alert.source_ref_id == diagnostic.id,
            Alert.status != "resolved",
        )
        .values(status="resolved", resolved_at=now)
    )
    res = await session.execute(stmt)
    await session.commit()
    return int(getattr(res, "rowcount", 0) or 0)
