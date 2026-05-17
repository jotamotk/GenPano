"""Slack webhook fan-out for ``needs_relogin`` alerts (Issue #1116).

Reads ``SLACK_WEBHOOK_URL`` lazily on each call so tests can monkeypatch
``os.environ`` between cases. No-op when the env var is unset — keeps
production safe by default and lets dev/staging skip the call without
extra plumbing.

Posts are fire-and-forget: the caller wraps ``notify_relogin_needed``
in ``asyncio.create_task`` so the inbound webhook from the VM-side
watchdog can return 200 immediately, even when Slack is slow / down.
A failure is logged at WARNING but never bubbles to the operator.
"""

from __future__ import annotations

import logging
import os
from typing import Final

import httpx

logger = logging.getLogger(__name__)


_SLACK_TIMEOUT_SECONDS: Final[float] = 5.0


def _webhook_url() -> str:
    """Return the configured Slack webhook URL, or ``""`` when unset.

    Reading via env getter on every call (instead of caching) keeps the
    helper test-friendly: ``monkeypatch.setenv`` / ``delenv`` toggles
    behavior without restarting the FastAPI app.
    """
    return os.getenv("SLACK_WEBHOOK_URL", "").strip()


def _format_text(*, vm_id: str, engine: str, novnc_url: str | None) -> str:
    """Build the message body. Kept in one place so tests can assert
    on a stable shape without hard-coding the channel-side template."""
    text = f":warning: VM {vm_id} ({engine}) needs CAPTCHA / re-login"
    if novnc_url:
        text += f"\n{novnc_url}"
    return text


async def notify_relogin_needed(
    *,
    vm_id: str,
    engine: str,
    novnc_url: str | None = None,
    reason: str | None = None,
) -> bool:
    """Post a ``needs_relogin`` alert to Slack. Returns ``True`` on
    success (or when the webhook is intentionally unset), ``False``
    when the HTTP call failed.

    Never raises: failures are caught + logged so the
    ``asyncio.create_task`` wrapper can swallow the result without
    a top-level UnhandledTaskException.
    """
    url = _webhook_url()
    if not url:
        # No-op: production behaviour when SLACK_WEBHOOK_URL is unset.
        # Logged at debug so we don't spam the operator console.
        logger.debug(
            "slack webhook not configured; skipping notify_relogin_needed for vm_id=%s engine=%s",
            vm_id,
            engine,
        )
        return True

    text = _format_text(vm_id=vm_id, engine=engine, novnc_url=novnc_url)
    payload: dict[str, str] = {"text": text}
    if reason:
        # Slack ignores unknown keys; including reason aids debugging
        # via webhook proxy logs without changing the user-visible text.
        payload["genpano_reason"] = reason

    try:
        async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
        if response.status_code >= 400:
            logger.warning(
                "slack webhook returned %s for vm_id=%s engine=%s",
                response.status_code,
                vm_id,
                engine,
            )
            return False
        return True
    except Exception as exc:  # fan-out helper must never raise
        logger.warning(
            "slack webhook failed for vm_id=%s engine=%s: %s",
            vm_id,
            engine,
            exc,
        )
        return False
