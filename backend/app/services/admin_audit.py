"""Admin audit logging — stub interface for Step 3.

The real persistence layer (writing rows into `admin_audit_log` per
ADMIN_PRD §5.2) is delivered in Session 3'. Step 3 calls record_audit()
at every privileged write so the call sites are correct from day one;
the body is currently a structlog INFO record carrying the same fields
that will eventually become the row schema.

Audit field list (ADMIN_PRD §5.2):
  operator_id, action, target_type, target_id, diff_json, reason,
  ip, ua, created_at
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def record_audit(
    *,
    operator_id: str,
    action: str,
    target_type: str,
    target_id: str | None = None,
    diff: dict[str, Any] | None = None,
    reason: str | None = None,
    ip: str | None = None,
    ua: str | None = None,
) -> None:
    """Record an admin moderation / privileged action.

    Stub: emits a structured INFO log; real DB INSERT into
    `admin_audit_log` arrives in Session 3'. The signature here MUST
    stay stable so call sites do not need to change later.
    """
    logger.info(
        "admin_audit.stub",
        extra={
            "audit": {
                "operator_id": operator_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "diff": diff,
                "reason": reason,
                "ip": ip,
                "ua": ua,
            }
        },
    )
