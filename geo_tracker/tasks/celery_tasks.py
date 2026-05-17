"""
Celery 任务定义
- execute_query: 单条 Query 执行（无账号模式优先）
- dispatch_batch: 批量分发 pending queries
- reset_daily_counts: 每日重置账号计数（Beat调度）
- cookie_keep_alive: 定期访问 LLM 保持 cookies 活跃
- auto_login: 自动 SMS 登录/注册（独立于 query 执行）
"""
from __future__ import annotations

import asyncio
import json as json_mod
import logging
import os
import re
import time
import uuid
from urllib.parse import urlparse

from celery import Celery
from celery.schedules import crontab
from billiard.exceptions import SoftTimeLimitExceeded
import redis.asyncio as aioredis
from sqlalchemy import delete as sa_delete, select

from geo_tracker.agent.browser_lifecycle import (
    cleanup_browser_resources,
    install_resource_blocker,
)
from geo_tracker.agent.guest_executor import GuestQueryExecutor, GUEST_LLM_CONFIG, DOMESTIC_LLMS
from geo_tracker.agent.response_validation import (
    chatgpt_auth_state_reason,
    doubao_auth_state_reason,
    doubao_persistence_auth_reason,
    invalid_response_reason,
)
from geo_tracker.agent.sms_login.registration_lock import (
    should_enqueue_new_account,
    should_enqueue_relogin,
    release_new_account_lock,
    release_relogin_lock,
)
from geo_tracker.agent.sms_redaction import mask_phone
from geo_tracker.db.models import (
    Query, QueryStatus, LLMResponse, LLMAccount, AccountStatus,
    AnalysisStatus, Brand, Competitor, Prompt,
    BrandMention, SentimentDriver, CitationSource,
    ResponseAnalysis, ProductFeatureMention,
)
from geo_tracker.pool.account_pool import (
    AccountPool,
    EXPIRED_ACCOUNT_REASONS,
    count_acquirable_accounts,
    snapshot_pool_health,
)

# 数据库 & Redis 连接（实际项目从 config 读取）
from geo_tracker.config import create_task_engine, get_task_async_session, REDIS_URL
from geo_tracker.tasks._loop_utils import safe_dispose_engine
from geo_tracker.tasks.account_assignment import (
    acquire_query_account,
    diagnose_account_unavailable,
)
from geo_tracker.tasks.account_quota_settlement import AccountQuotaSettlement
from geo_tracker.tasks.query_failure import (
    browser_execution_timeout_reason,
    _empty_response_failure_reason,
)
from geo_tracker.tasks.query_lifecycle import mark_query_finished, mark_query_started
from geo_tracker.tasks.no_account_requeue import (
    NO_ACCOUNT_REQUEUE_REASONS,
    NO_ACCOUNT_REQUEUE_REASON_TAG,
    maybe_requeue_for_no_account,
)
from geo_tracker.tasks.stale_running_repair import (
    DEFAULT_STALE_RUNNING_SECONDS,
    repair_stale_running_queries,
)

logger = logging.getLogger(__name__)


def _browser_execution_timeout_seconds(llm_name: str | None) -> float | None:
    if (llm_name or "").lower() != "doubao":
        return None
    raw = os.getenv("DOUBAO_BROWSER_EXECUTION_TIMEOUT_SECONDS") or os.getenv(
        "SCRAPER_BROWSER_EXECUTION_TIMEOUT_SECONDS"
    )
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            logger.warning("Invalid Doubao browser execution timeout: %r", raw)
    return 480.0


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _keep_alive_auto_relogin_enabled() -> bool:
    return _env_flag("COOKIE_KEEP_ALIVE_AUTO_RELOGIN", False)


def _doubao_uses_proxy_route() -> bool:
    # Refs #963: Doubao defaults to direct connect from the China-hosted
    # worker; see ``geo_tracker.agent.guest_executor._doubao_proxy_enabled``
    # for the routing rationale. Keep the env flag so dev/overseas hosts can
    # opt in.
    return _env_flag("DOUBAO_USE_PROXY", False)


def _keep_alive_proxy_url(llm_name: str) -> str | None:
    proxy_url = (
        os.getenv("CLASH_PROXY_URL")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
    )
    if not proxy_url:
        return None
    llm = (llm_name or "").lower()
    if llm == "doubao" and _doubao_uses_proxy_route():
        return proxy_url
    if llm not in DOMESTIC_LLMS:
        return proxy_url
    return None


def _keep_alive_should_enqueue_relogin(
    llm_name: str | None,
    failure_reason: str | None,
) -> bool:
    if _keep_alive_auto_relogin_enabled():
        return True
    return (
        (llm_name or "").lower() == "doubao"
        and failure_reason in DOUBAO_REAUTH_FAILURE_REASONS
    )


def _safe_url_host(url: str | None) -> str:
    if not url:
        return "unknown"
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return "unknown"
    return host.split("@")[-1].split(":")[0] or "unknown"


def _keep_alive_body_marker(reason: str | None) -> str:
    return {
        "chatgpt_auth_redirect": "auth_redirect",
        "chatgpt_login_page": "login_page",
        "chatgpt_not_logged_in": "logged_out_shell",
        "cookies_expired": "session_expired",
        "doubao_auth_state_missing": "auth_state_missing",
        "doubao_not_logged_in": "login_chrome",
        "login_redirect": "login_redirect",
        "session_expired": "session_expired",
        "token_invalidated": "token_invalidated",
    }.get(reason or "", "auth_loss")


async def _page_text_title_html(page) -> tuple[str, str, str]:
    body_text = ""
    page_title = ""
    html = ""
    try:
        body_text = await page.evaluate("document.body?.innerText || ''")
    except Exception:
        pass
    try:
        page_title = await page.title()
    except Exception:
        pass
    try:
        html = await page.evaluate("document.body?.outerHTML || ''")
    except Exception:
        pass
    return body_text or "", page_title or "", html or ""


async def _keep_alive_probe_failure_reason(
    llm_name: str, config: dict, page
) -> tuple[str | None, str]:
    """Classify keep-alive auth loss without logging page bodies or cookies."""
    current_url = getattr(page, "url", None)
    url_host = _safe_url_host(current_url)
    body_text, page_title, html = await _page_text_title_html(page)
    llm = (llm_name or "").lower()

    if llm == "chatgpt":
        reason = chatgpt_auth_state_reason(
            body_text,
            url=current_url,
            title=page_title,
        )
        if reason:
            return reason, f"url_host={url_host} body_marker={_keep_alive_body_marker(reason)}"

    if llm == "doubao":
        reason = doubao_auth_state_reason(body_text, html)
        if reason:
            return reason, f"url_host={url_host} body_marker={_keep_alive_body_marker(reason)}"

    reason = invalid_response_reason(llm, body_text)
    if reason in EXPIRED_ACCOUNT_REASONS:
        return reason, f"url_host={url_host} body_marker={_keep_alive_body_marker(reason)}"

    login_domains = config.get("login_redirect_domains", [])
    if current_url and any(domain in current_url for domain in login_domains):
        reason = "login_redirect"
        return reason, f"url_host={url_host} body_marker={_keep_alive_body_marker(reason)}"

    return None, f"url_host={url_host} body_marker=none"


async def _chatgpt_keep_alive_session_failure_reason(page) -> tuple[str | None, str]:
    """Validate ChatGPT session endpoint without exposing the response body."""
    try:
        resp = await page.goto(
            "https://chatgpt.com/api/auth/session",
            wait_until="domcontentloaded",
            timeout=30000,
        )
    except Exception:
        return "chatgpt_auth_redirect", "session_probe=exception"

    if not resp:
        return "chatgpt_auth_redirect", "session_probe=no_response"

    status = getattr(resp, "status", "unknown")
    if not getattr(resp, "ok", False):
        return "chatgpt_auth_redirect", f"session_http_status={status}"

    try:
        body = await page.inner_text("body")
        session_data = json_mod.loads(body)
    except Exception:
        return "chatgpt_auth_redirect", f"session_http_status={status} session_json=false"

    if not isinstance(session_data, dict) or not session_data.get("accessToken"):
        return (
            "chatgpt_not_logged_in",
            f"session_http_status={status} session_access_token=false",
        )

    return None, f"session_http_status={status} session_access_token=true"


def _merge_refreshed_cookie_payload(
    previous_cookies_json: str | None,
    refreshed_cookies: list,
) -> str:
    try:
        old_data = json_mod.loads(previous_cookies_json or "")
    except Exception:
        old_data = None

    if isinstance(old_data, dict):
        payload = {"cookies": refreshed_cookies}
        for key in ("localStorage", "storageState"):
            if key in old_data:
                payload[key] = old_data[key]
        return json_mod.dumps(payload)

    return json_mod.dumps(refreshed_cookies)


DOUBAO_REAUTH_FAILURE_REASONS = frozenset(
    {
        "cookies_expired",
        "doubao_not_logged_in",
        "doubao_auth_state_missing",
        # Refs #963 / Codex P1 on PR #1037: ``doubao_homepage_content`` is
        # now in EXPIRED_ACCOUNT_REASONS, so a shadow-banned account is
        # removed from rotation. But the reauth handoff at
        # ``_handle_doubao_account_failure_handoff`` (and the cookie
        # keep-alive relogin gate) only queues ``auto_login.apply_async``
        # when the reason is in THIS set. Without adding the reason here,
        # the account is expired silently and no auto_login fires — the
        # self-healing chain never starts and the pool can drain to zero
        # active accounts with no recovery. Keep both sets in sync so
        # the expired marking and the reauth queue are wired through the
        # same failure modes.
        "doubao_homepage_content",
    }
)
DOUBAO_REAUTH_RETRY_REASON_PREFIX = "doubao_reauth_retry:"
DOUBAO_POST_REAUTH_FAILURE_PREFIX = "doubao_post_reauth_"
DOUBAO_NEW_ACCOUNT_RETRY_REASON_PREFIX = "doubao_new_account_retry:"


def _is_doubao_post_reauth_attempt(retry_reason: str | None) -> bool:
    return bool(
        retry_reason and retry_reason.startswith(DOUBAO_REAUTH_RETRY_REASON_PREFIX)
    )


def _doubao_post_reauth_failure_reason(
    initial_retry_reason: str | None,
    failure_reason: str | None,
) -> str | None:
    if (
        _is_doubao_post_reauth_attempt(initial_retry_reason)
        and failure_reason in DOUBAO_REAUTH_FAILURE_REASONS
    ):
        return f"{DOUBAO_POST_REAUTH_FAILURE_PREFIX}{failure_reason}"
    return failure_reason


async def _requeue_doubao_query_after_reauth(
    db,
    *,
    account_id: int,
    query_id: int | None,
) -> bool:
    if not query_id:
        return False

    retry_max = _env_int("DOUBAO_REAUTH_QUERY_RETRY_MAX", 11)
    if retry_max <= 0:
        return False

    result = await db.execute(select(Query).where(Query.id == query_id))
    query = result.scalar_one_or_none()
    if not query:
        return False

    if query.target_llm != "doubao" or query.account_id != account_id:
        return False
    if query.status != QueryStatus.FAILED.value:
        return False
    if query.retry_reason not in DOUBAO_REAUTH_FAILURE_REASONS:
        return False

    response_result = await db.execute(
        select(LLMResponse.id).where(LLMResponse.query_id == query_id)
    )
    if response_result.scalar_one_or_none() is not None:
        return False

    from datetime import datetime as dt

    query.status = QueryStatus.PENDING.value
    query.retry_count = int(query.retry_count or 0) + 1
    query.retry_reason = f"doubao_reauth_retry:{account_id}"
    query.queued_at = dt.utcnow()
    query.started_at = None
    query.finished_at = None
    query.executed_at = None
    query.latency_ms = None
    await db.commit()

    execute_query.apply_async(args=[query_id], queue="llm_doubao")
    logger.warning(
        "Query %s: requeued after Doubao account %s reauth success "
        "(retry_count=%s reauth_requeue_enabled=%s)",
        query_id,
        account_id,
        query.retry_count,
        retry_max,
    )
    return True


_NEW_ACCOUNT_REQUEUE_ELIGIBLE_RETRY_REASONS = (
    set(NO_ACCOUNT_REQUEUE_REASONS) | {NO_ACCOUNT_REQUEUE_REASON_TAG}
)


async def _query_eligible_for_new_account_requeue(db, query) -> bool:
    if not query:
        return False
    if query.target_llm != "doubao":
        return False
    if query.status not in {QueryStatus.FAILED.value, QueryStatus.PENDING.value}:
        return False
    if query.retry_reason not in _NEW_ACCOUNT_REQUEUE_ELIGIBLE_RETRY_REASONS:
        return False
    response_result = await db.execute(
        select(LLMResponse.id).where(LLMResponse.query_id == query.id)
    )
    return response_result.scalar_one_or_none() is None


def _apply_new_account_requeue(query, account_id: int) -> None:
    from datetime import datetime as dt

    query.account_id = account_id
    query.status = QueryStatus.PENDING.value
    query.retry_count = int(query.retry_count or 0) + 1
    query.retry_reason = f"{DOUBAO_NEW_ACCOUNT_RETRY_REASON_PREFIX}{account_id}"
    query.queued_at = dt.utcnow()
    query.started_at = None
    query.finished_at = None
    query.executed_at = None
    query.latency_ms = None


async def _claim_oldest_no_account_doubao_query(db, *, exclude_query_id: int | None):
    """Find the oldest waiting Doubao no-account query for new-account handoff.

    Refs #963 handoff: query rows that exhausted the bounded no-account
    requeue budget land in FAILED with retry_reason in
    NO_ACCOUNT_REQUEUE_REASONS. Without this fallback, a new Doubao
    account that comes in without the original query_id (or in flight
    while a different request was failing) will not claim those stuck
    rows, and operators must retry by hand.
    """
    response_subq = select(LLMResponse.id).where(LLMResponse.query_id == Query.id)
    stmt = (
        select(Query)
        .where(Query.target_llm == "doubao")
        .where(Query.status == QueryStatus.FAILED.value)
        .where(Query.retry_reason.in_(_NEW_ACCOUNT_REQUEUE_ELIGIBLE_RETRY_REASONS))
        .where(~response_subq.exists())
        .order_by(Query.created_at.asc(), Query.id.asc())
        .limit(1)
    )
    if exclude_query_id is not None:
        stmt = stmt.where(Query.id != exclude_query_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _requeue_doubao_query_after_new_account(
    db,
    *,
    account_id: int,
    query_id: int | None,
) -> int | None:
    """Requeue a Doubao no-account query after new-account login.

    Returns the claimed query id (which may differ from ``query_id`` when
    the caller's row is no longer eligible and the fallback claims the
    oldest stuck no-account query) or ``None`` if nothing was claimed.
    """
    target_query = None

    if query_id:
        result = await db.execute(select(Query).where(Query.id == query_id))
        candidate = result.scalar_one_or_none()
        if await _query_eligible_for_new_account_requeue(db, candidate):
            target_query = candidate

    if target_query is None:
        # Refs #963: any Doubao new-account success should claim the oldest
        # waiting no-account row even when this auto_login was not started
        # with the matching query_id (e.g. it was already in flight when
        # the failing query landed, or a sibling failure issued the call).
        target_query = await _claim_oldest_no_account_doubao_query(
            db,
            exclude_query_id=query_id,
        )
        if target_query is None:
            return None
        logger.warning(
            "auto_login: no explicit query_id requeue (passed=%s); "
            "claiming oldest stuck Doubao query %s for new account %s",
            query_id,
            target_query.id,
            account_id,
        )

    _apply_new_account_requeue(target_query, account_id)
    await db.commit()

    execute_query.apply_async(args=[target_query.id], queue="llm_doubao")
    logger.warning(
        "Query %s: assigned new Doubao account %s and requeued after "
        "new-account login success (retry_count=%s)",
        target_query.id,
        account_id,
        target_query.retry_count,
    )
    return target_query.id


async def _handle_doubao_account_failure_handoff(
    *,
    db,
    pool: AccountPool | None,
    query: Query,
    account_id: int | None,
    failure_reason: str | None,
) -> None:
    if query.target_llm != "doubao" or not account_id or not failure_reason:
        return

    if failure_reason == "page_unavailable" and pool is not None:
        await pool.report_failure(account_id, reason="doubao_page_unavailable")
        await db.commit()

    if failure_reason not in DOUBAO_REAUTH_FAILURE_REASONS:
        return

    if await should_enqueue_relogin(account_id):
        auto_login.apply_async(
            kwargs={"account_id": account_id, "query_id": query.id},
            queue="account_login",
        )
        logger.warning(
            "Query %s: Doubao account %s queued for reauth after %s",
            query.id,
            account_id,
            failure_reason,
        )


class AccountSessionLockTimeout(TimeoutError):
    """Raised when a query cannot enter a serialized account browser session."""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer env %s=%r; using %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float env %s=%r; using %s", name, raw, default)
        return default


def _session_lock_llms() -> set[str]:
    raw = os.getenv("SCRAPER_SESSION_LOCK_LLMS", "deepseek")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _should_lock_account_session(llm_name: str | None, account_id: int | None) -> bool:
    if not account_id:
        return False
    return str(llm_name or "").lower() in _session_lock_llms()


def _account_session_lock_key(llm_name: str, account_id: int) -> str:
    llm = str(llm_name or "").lower()
    return f"genpano:scraper:session:{llm}:{int(account_id)}"


async def _release_account_session_lock(client, key: str, token: str) -> None:
    try:
        current = await client.get(key)
        if current == token:
            await client.delete(key)
    except Exception as exc:
        logger.warning("Failed to release scraper session lock %s: %s", key, exc)


async def _run_with_account_session_lock(
    llm_name: str,
    account_id: int | None,
    query_id: int,
    operation,
    *,
    poll_interval_s: float | None = None,
    wait_timeout_s: float | None = None,
    lock_ttl_s: int | None = None,
):
    """Serialize browser sessions for account-backed engines that need it."""
    if not _should_lock_account_session(llm_name, account_id):
        return await operation()

    ttl_s = lock_ttl_s or _env_int("SCRAPER_SESSION_LOCK_TTL_S", 600)
    timeout_s = (
        wait_timeout_s
        if wait_timeout_s is not None
        else _env_float("SCRAPER_SESSION_LOCK_WAIT_TIMEOUT_S", 420.0)
    )
    poll_s = (
        poll_interval_s
        if poll_interval_s is not None
        else _env_float("SCRAPER_SESSION_LOCK_POLL_S", 1.0)
    )
    key = _account_session_lock_key(llm_name, int(account_id))
    token = f"{os.getpid()}:{query_id}:{uuid.uuid4().hex}"
    deadline = time.monotonic() + max(0.0, timeout_s)
    try:
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.warning(
            "Query %s: could not create scraper session lock client for %s "
            "account=%s; continuing fail-open: %s",
            query_id,
            llm_name,
            account_id,
            exc,
        )
        return await operation()
    acquired = False

    try:
        while True:
            try:
                acquired = bool(await client.set(key, token, nx=True, ex=ttl_s))
            except Exception as exc:
                logger.warning(
                    "Query %s: scraper session lock unavailable for %s account=%s; "
                    "continuing fail-open: %s",
                    query_id,
                    llm_name,
                    account_id,
                    exc,
                )
                return await operation()

            if acquired:
                logger.info(
                    "Query %s: acquired scraper session lock for %s account=%s",
                    query_id,
                    llm_name,
                    account_id,
                )
                return await operation()

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AccountSessionLockTimeout(
                    f"{llm_name} account {account_id} session lock wait timed out"
                )

            await asyncio.sleep(min(max(poll_s, 0.01), remaining))
    finally:
        try:
            if acquired:
                await _release_account_session_lock(client, key, token)
        finally:
            try:
                await client.aclose()
            except Exception:
                pass


app = Celery("geo_tracker", broker=REDIS_URL, backend=REDIS_URL)

_beat_schedule = {
    "reset-daily-counts": {
        "task":     "geo_tracker.tasks.celery_tasks.reset_daily_counts",
        "schedule": crontab(hour=0, minute=0),
    },
    "cookie-keep-alive": {
        "task":     "geo_tracker.tasks.celery_tasks.cookie_keep_alive",
        "schedule": crontab(hour="*/6", minute=30),
    },
    # Refs #963 audit pain point #1 (proactive pool pre-warming).
    # 10-min cadence: the SMS-register round-trip is ~60-120s end-to-end,
    # and the 30-min failure cooldown in registration_lock means a too-fast
    # cadence would just trip the cooldown gate over and over. 10 min is
    # the smallest cadence that lets the lock + cooldown semantics work
    # naturally while still refilling the pool well before a typical
    # user-query batch arrives.
    "prewarm-account-pool": {
        "task":     "geo_tracker.tasks.celery_tasks.prewarm_account_pool",
        "schedule": crontab(minute="*/10"),
    },
}

# Auto-schedule daily analysis in production (opt-in via env var)
if os.getenv("ANALYZER_AUTO_SCHEDULE", "false").lower() == "true":
    _beat_schedule["daily-analysis"] = {
        "task":     "geo_tracker.tasks.celery_tasks.run_daily_analysis",
        "schedule": crontab(hour=2, minute=0),
    }
    # Issue #1040: previously the daily aggregation Celery task (which
    # populates GEOScoreDaily / ProductScoreDaily / TopicScoreDaily /
    # IndustryBenchmarkDaily) had no beat schedule, so `product_score_daily`
    # stayed empty and the /projects/:id/products endpoint fell back to
    # ProductFeatureMention with all per-product metric columns NULL —
    # exactly the BestCoffer screenshot pattern reproduced in
    # `backend/scripts/inspect_products_response.py` scenario (e).
    #
    # Schedule it once per day at 04:00 UTC, two hours AFTER run_daily_analysis
    # at 02:00 UTC so the analyzer has finished writing today's BrandMentions /
    # ResponseAnalysis rows before we roll them up.
    #
    # `brand_id=None` triggers the aggregator's auto-discovery
    # (`Aggregator._brand_ids_for_aggregation`, aggregator.py:968-980), which
    # walks today's queries+mentions and produces rollup rows for every brand
    # that actually has activity — no need to iterate brand_ids explicitly
    # here. Re-runs for the same day are safe because `aggregate_daily`
    # calls `_clear_existing_daily_aggregates` before re-inserting.
    _beat_schedule["aggregate-daily-scores"] = {
        "task":     "geo_tracker.tasks.celery_tasks.aggregate_daily_scores",
        "schedule": crontab(hour=4, minute=0),
    }

if os.getenv("HOTSPOT_AUTO_SCHEDULE", "false").lower() == "true":
    _beat_schedule["hotspots-douyin"] = {
        "task":     "geo_tracker.tasks.celery_tasks.collect_hotspot_source",
        "schedule": crontab(hour="*/6", minute=5),
        "args":     ("douyin",),
    }
    _beat_schedule["hotspots-xhs"] = {
        "task":     "geo_tracker.tasks.celery_tasks.collect_hotspot_source",
        "schedule": crontab(hour="*/6", minute=20),
        "args":     ("xhs",),
    }

app.conf.update(
    task_serializer   = "json",
    result_serializer = "json",
    timezone          = "UTC",
    task_max_retries  = 3,
    task_default_retry_delay = 60,
    worker_concurrency = 5,
    worker_prefetch_multiplier = 1,
    # 硬超时：Playwright/代理极端 hang 时强杀 worker child，避免 query 永久停在 running
    task_time_limit      = 600,
    task_soft_time_limit = 540,
    beat_schedule = _beat_schedule,
    task_routes = {
        "geo_tracker.tasks.celery_tasks.analyze_response": {"queue": "analysis"},
        "geo_tracker.tasks.celery_tasks.run_daily_analysis": {"queue": "analysis"},
        "geo_tracker.tasks.celery_tasks.aggregate_daily_scores": {"queue": "analysis"},
    },
)


@app.task(name="geo_tracker.tasks.celery_tasks.collect_hotspot_source", queue="celery")
def collect_hotspot_source(
    source: str,
    *,
    industry: str | None = None,
    brand_id: int | None = None,
    brand_context: dict | None = None,
) -> dict:
    """Collect one hotspot source in the worker image.

    Browser-backed sources such as Douyin and Xiaohongshu need the worker's
    browser stack and the uploaded ``llm_accounts`` cookies, so Admin queues
    them here instead of importing geo_tracker from the Admin image.
    """
    from geo_tracker.hotspots.pipeline import run_collection_cycle

    result = run_collection_cycle(
        sources=[source],
        industry_filter=industry,
        brand_context=brand_context,
        brand_id=brand_id,
    )
    logger.info("collect_hotspot_source(%s) -> %s", source, result)
    return result


async def _cleanup_previous_response(db, query_id: int) -> None:
    """
    按外键拓扑顺序清空一条 query 的旧 response 及其所有派生行。
    llm_responses 有多张子表持有 response_id / mention_id / analysis_id，
    bulk DELETE 不触发 ORM cascade，这里显式依序删除避免 FK 违约。
    """
    old_resp_ids_subq = select(LLMResponse.id).where(LLMResponse.query_id == query_id)
    old_analysis_ids_subq = select(ResponseAnalysis.id).where(
        ResponseAnalysis.response_id.in_(old_resp_ids_subq)
    )

    await db.execute(
        sa_delete(ProductFeatureMention).where(
            ProductFeatureMention.analysis_id.in_(old_analysis_ids_subq)
        )
    )
    await db.execute(
        sa_delete(SentimentDriver).where(
            SentimentDriver.response_id.in_(old_resp_ids_subq)
        )
    )
    await db.execute(
        sa_delete(CitationSource).where(
            CitationSource.response_id.in_(old_resp_ids_subq)
        )
    )
    await db.execute(
        sa_delete(BrandMention).where(
            BrandMention.response_id.in_(old_resp_ids_subq)
        )
    )
    await db.execute(
        sa_delete(ResponseAnalysis).where(
            ResponseAnalysis.response_id.in_(old_resp_ids_subq)
        )
    )
    await db.execute(
        sa_delete(LLMResponse).where(LLMResponse.query_id == query_id)
    )


def _enqueue_response_analysis(response_id: int | None) -> bool:
    """Queue analysis for a saved response without failing the scraper result."""
    if not response_id:
        return False
    try:
        analyze_response.apply_async(args=[response_id], queue="analysis")
        logger.info("Queued analysis for response_id=%s", response_id)
        return True
    except Exception as exc:
        logger.warning(
            "Failed to queue analysis for response_id=%s: %s",
            response_id,
            exc,
        )
        return False


async def _mark_query_failed_after_task_abort_async(
    query_id: int,
    reason: str,
    *,
    quota_settlement: AccountQuotaSettlement | None = None,
) -> None:
    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as db:
            result = await db.execute(select(Query).where(Query.id == query_id))
            query = result.scalar_one_or_none()
            if query is None or query.status == QueryStatus.DONE.value:
                return
            effective_reason = reason
            if reason == "soft_time_limit" and query.target_llm == "doubao":
                response_result = await db.execute(
                    select(LLMResponse.id).where(LLMResponse.query_id == query_id).limit(1)
                )
                effective_reason = browser_execution_timeout_reason(
                    query.target_llm,
                    stage="task_soft_limit",
                    has_existing_response=response_result.scalar_one_or_none()
                    is not None,
                )
            mark_query_finished(
                query,
                status=QueryStatus.FAILED.value,
                started_at=query.started_at,
                reason=effective_reason,
            )
            if quota_settlement is not None:
                await quota_settlement.settle_failure(
                    db,
                    AccountPool(db),
                    reason=effective_reason,
                )
            await db.commit()
    finally:
        await engine.dispose()


def _mark_query_failed_after_task_abort(
    query_id: int,
    reason: str,
    *,
    quota_settlement: AccountQuotaSettlement | None = None,
) -> None:
    cleanup_loop = asyncio.new_event_loop()
    try:
        cleanup_loop.run_until_complete(
            _mark_query_failed_after_task_abort_async(
                query_id,
                reason,
                quota_settlement=quota_settlement,
            )
        )
    finally:
        cleanup_loop.close()


@app.task(bind=True, max_retries=2)
def execute_query(self, query_id: int) -> dict:
    """
    执行单条查询（仅无账号模式）
    """
    # 为每个任务创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    task_engine = create_task_engine()
    quota_settlement = AccountQuotaSettlement()

    async def _run():
        async with get_task_async_session(task_engine) as db:
            # 直接通过 ID 查询，不加载关系
            result = await db.execute(select(Query).where(Query.id == query_id))
            query = result.scalar_one_or_none()

            if not query:
                return {"skipped": True, "reason": "query_not_found"}

            if query.status == QueryStatus.DONE.value:
                return {"skipped": True, "reason": "already_done"}

            # 更新状态为 RUNNING
            initial_retry_reason = query.retry_reason
            started_at = mark_query_started(query)
            await db.commit()

            llm_config = GUEST_LLM_CONFIG.get(query.target_llm, {})

            # 从 AccountPool 获取账号 cookies
            account = None
            account_id = None
            account_cookies = None
            pool = None
            requires_login = llm_config.get("requires_login", True)

            pool = AccountPool(db)
            account = await acquire_query_account(db, query, pool=pool)
            if account and account.cookies_json:
                account_cookies = account.cookies_json
                account_id = account.id
                quota_settlement.reserve(account_id)
                query.account_id = account_id
                await db.commit()
                logger.info(
                    f"Query {query_id}: acquired account id={account_id} "
                    f"for {query.target_llm}"
                )
            elif requires_login:
                # 必须登录但无可用账号:
                # - 历史行为是直接 FAILED，避免无限重试。
                # - 现在改为 bounded re-queue（仅 Doubao，且失败原因属于 pool 类）:
                #   下一轮 dispatch 可以在 cooldown 自动恢复 / auto_login 完成后
                #   重新承接，operator 不用手工 retry。预算用尽后才走 FAILED。
                failure_reason = await diagnose_account_unavailable(db, query.target_llm)
                requeued, retry_count, retry_max = maybe_requeue_for_no_account(
                    query, failure_reason
                )
                if requeued:
                    await db.commit()
                    logger.warning(
                        "Query %s: %s no account available (%s); re-queued attempt %s/%s",
                        query_id,
                        query.target_llm,
                        failure_reason,
                        retry_count,
                        retry_max,
                    )
                    # 仍然按原有逻辑触发 auto_login（带分布式锁，参考 2026-04-27 SMS 修复）。
                    if (
                        query.target_llm in {"doubao", "deepseek", "chatgpt"}
                        and failure_reason in NO_ACCOUNT_REQUEUE_REASONS
                        and await should_enqueue_new_account(query.target_llm)
                    ):
                        login_kwargs = {
                            "platform": query.target_llm,
                            "new_account": True,
                        }
                        if query.target_llm == "doubao":
                            login_kwargs["query_id"] = query.id
                        auto_login.apply_async(
                            kwargs=login_kwargs,
                            queue="account_login",
                        )
                    return {
                        "query_id": query_id,
                        "status": "requeued",
                        "reason": failure_reason,
                        "retry_count": retry_count,
                        "retry_max": retry_max,
                    }

                mark_query_finished(
                    query,
                    status=QueryStatus.FAILED.value,
                    started_at=started_at,
                    reason=failure_reason,
                )
                await db.commit()
                logger.warning(
                    f"Query {query_id}: {query.target_llm} requires login "
                    f"but no account available ({failure_reason}), marking FAILED "
                    f"(retry_count={retry_count}, retry_max={retry_max})"
                )
                # 生产事故 2026-04-27 SMS 浪费根因修复:
                # 原代码无锁直接 enqueue, 同时间窗多个 query 失败会喷多个 auto_login,
                # 每个都向鲁班要新手机号 (~1元/条). 加分布式锁 + 失败 cooldown.
                auto_register_engines = {"doubao", "deepseek", "chatgpt"}
                if (
                    query.target_llm in auto_register_engines
                    and failure_reason in NO_ACCOUNT_REQUEUE_REASONS
                    and await should_enqueue_new_account(query.target_llm)
                ):
                    login_kwargs = {"platform": query.target_llm, "new_account": True}
                    if query.target_llm == "doubao":
                        login_kwargs["query_id"] = query.id
                    auto_login.apply_async(
                        kwargs=login_kwargs,
                        queue="account_login",
                    )
                return {
                    "query_id": query_id,
                    "status": "failed",
                    "reason": failure_reason,
                }
            else:
                # 不需要登录（guest 可用），无 cookie 也继续
                logger.info(
                    f"Query {query_id}: no account for {query.target_llm}, "
                    f"proceeding with guest mode"
                )

            logger.info(f"Query {query_id}: Using {'account' if account_cookies else 'guest'} mode for {query.target_llm}")

            guest_executor: GuestQueryExecutor | None = None

            try:
                proxy_url = os.getenv("CLASH_PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
                logger.info(f"Query {query_id}: Using proxy URL: {proxy_url}")

                async def _execute_browser_session() -> LLMResponse | None:
                    nonlocal guest_executor
                    guest_executor = GuestQueryExecutor(
                        proxy_url=proxy_url,
                        account_cookies=account_cookies,
                    )
                    timeout_s = _browser_execution_timeout_seconds(query.target_llm)
                    try:
                        if timeout_s:
                            return await asyncio.wait_for(
                                guest_executor.execute(query),
                                timeout=timeout_s,
                            )
                        return await guest_executor.execute(query)
                    except asyncio.TimeoutError:
                        # Refs #963 follow-up to PR #1005 (run 25919843002,
                        # query 184968): a doubao_browser_timeout:cleanup
                        # was being reported even when the work was actually
                        # stuck in response_wait — the inner _execute_once
                        # finally block sets execution_stage="cleanup" before
                        # the outer wait_for raises here, so the post-finally
                        # value clobbers the real stage. Prefer the
                        # ``stage_at_failure`` attribute latched by the
                        # CancelledError / except Exception handlers BEFORE
                        # the finally ran, falling back to execution_stage
                        # only when nothing was latched (e.g., the timeout
                        # fired before any handler ran).
                        stage = getattr(
                            guest_executor, "stage_at_failure", None
                        ) or getattr(guest_executor, "execution_stage", None)
                        failure_reason = browser_execution_timeout_reason(
                            query.target_llm,
                            stage=stage,
                        )
                        guest_executor.last_error_reason = failure_reason
                        # Refs #963 handoff: the executor preserves last
                        # URL/title/body and may have written a runtime
                        # snapshot before its finally-block cleanup tore the
                        # page down. Surface those on the operator log so
                        # browser_timeout failures stop reading as a bare
                        # reason code.
                        last_url = getattr(guest_executor, "last_page_url", None)
                        last_title = getattr(guest_executor, "last_page_title", None)
                        last_body = getattr(
                            guest_executor, "last_page_body_snippet", None
                        )
                        snapshot_path = getattr(
                            guest_executor, "last_snapshot_path", None
                        )
                        logger.warning(
                            "Query %s: %s browser execution timed out after %.1fs "
                            "(stage=%s, reason=%s, url=%s, title=%s, "
                            "snapshot=%s, body_snippet=%r)",
                            query_id,
                            query.target_llm,
                            timeout_s,
                            stage,
                            failure_reason,
                            last_url,
                            (last_title[:120] if last_title else None),
                            snapshot_path,
                            (last_body[:300] if last_body else None),
                        )
                        return None

                response: LLMResponse | None = await _run_with_account_session_lock(
                    query.target_llm,
                    account_id,
                    query_id,
                    _execute_browser_session,
                )
                if response is not None:
                    quota_settlement.mark_platform_consumed()

                # Require a meaningful response (guards against login redirects returning 1 char)
                MIN_RESPONSE_LEN = 20
                # 检测无效响应（登录页、session 过期等 UI 文字）
                INVALID_RESPONSE_MARKERS = [
                    "your session has expired",
                    "please log in again to continue using the app",
                ]

                def _is_invalid_response(text: str) -> str | None:
                    """返回匹配的无效标记，或 None"""
                    lower = text.lower()
                    for marker in INVALID_RESPONSE_MARKERS:
                        if marker in lower:
                            return marker
                    return None

                if response and len(response.raw_text) >= MIN_RESPONSE_LEN:
                    auth_failure_reason = doubao_persistence_auth_reason(
                        query.target_llm,
                        response.raw_text,
                        response.response_html,
                    )
                    if auth_failure_reason:
                        failure_reason = _doubao_post_reauth_failure_reason(
                            initial_retry_reason,
                            auth_failure_reason,
                        )
                        mark_query_finished(
                            query,
                            status=QueryStatus.FAILED.value,
                            started_at=started_at,
                            reason=failure_reason,
                        )
                        await quota_settlement.settle_failure(
                            db,
                            pool,
                            reason=auth_failure_reason,
                        )
                        await _handle_doubao_account_failure_handoff(
                            db=db,
                            pool=pool,
                            query=query,
                            account_id=account_id,
                            failure_reason=failure_reason,
                        )
                        await db.commit()
                        logger.warning(
                            "Query %s failed: Doubao auth state rejected before DONE (%s), "
                            "account %s",
                            query_id,
                            failure_reason,
                            account_id,
                        )
                        return {
                            "query_id": query_id,
                            "status": "failed",
                            "reason": failure_reason,
                        }

                    invalid_reason = invalid_response_reason(query.target_llm, response.raw_text)
                    if invalid_reason:
                        # 响应内容是登录页/过期页，不是 AI 回答
                        failure_reason = _doubao_post_reauth_failure_reason(
                            initial_retry_reason,
                            invalid_reason,
                        )
                        mark_query_finished(
                            query,
                            status=QueryStatus.FAILED.value,
                            started_at=started_at,
                            reason=failure_reason,
                        )
                        await quota_settlement.settle_failure(
                            db,
                            pool,
                            reason=invalid_reason,
                        )
                        await _handle_doubao_account_failure_handoff(
                            db=db,
                            pool=pool,
                            query=query,
                            account_id=account_id,
                            failure_reason=failure_reason,
                        )
                        await db.commit()
                        if (
                            failure_reason
                            in {
                                "cookies_expired",
                                "token_invalidated",
                                "chatgpt_not_logged_in",
                                "chatgpt_auth_redirect",
                            }
                            and account_id
                            and query.target_llm != "doubao"
                        ):
                            if query.target_llm == "chatgpt":
                                logger.warning(
                                    "Query %s: ChatGPT account %s requires manual reauth "
                                    "after %s; no SMS auto-login handler is registered",
                                    query_id,
                                    account_id,
                                    failure_reason,
                                )
                            elif await should_enqueue_relogin(account_id):
                                auto_login.apply_async(
                                    kwargs={"account_id": account_id},
                                    queue="account_login",
                                )
                        logger.warning(
                            f"Query {query_id} failed: invalid response ({invalid_reason}), "
                            f"account {account_id}"
                        )
                        return {"query_id": query_id, "status": "failed", "reason": failure_reason}

                    # 重试场景：清理旧 response 及其所有派生行（mentions/drivers/
                    # citations/analyses/feature_mentions），避免 FK 违约
                    await _cleanup_previous_response(db, query_id)
                    db.add(response)
                    await db.flush()
                    response_id = response.id
                    mark_query_finished(
                        query,
                        status=QueryStatus.DONE.value,
                        started_at=started_at,
                        reason=None,
                    )
                    await quota_settlement.settle_success(pool)
                    await db.commit()
                    analysis_enqueued = _enqueue_response_analysis(response_id)
                    logger.info(f"Query {query_id} DONE, response len={len(response.raw_text)}")
                    return {
                        "query_id": query_id,
                        "status": "done",
                        "mode": "guest",
                        "analysis_enqueued": analysis_enqueued,
                    }
                else:
                    resp_len = len(response.raw_text) if response else 0
                    failure_reason = _empty_response_failure_reason(
                        response,
                        executor=guest_executor,
                        account_cookies=account_cookies,
                    )
                    original_failure_reason = failure_reason
                    failure_reason = _doubao_post_reauth_failure_reason(
                        initial_retry_reason,
                        original_failure_reason,
                    )
                    mark_query_finished(
                        query,
                        status=QueryStatus.FAILED.value,
                        started_at=started_at,
                        reason=failure_reason,
                    )
                    # 区分 cookies 过期和其他失败：response 为 None 通常是登录重定向
                    await quota_settlement.settle_failure(
                        db,
                        pool,
                        reason=original_failure_reason,
                    )
                    await _handle_doubao_account_failure_handoff(
                        db=db,
                        pool=pool,
                        query=query,
                        account_id=account_id,
                        failure_reason=failure_reason,
                    )
                    await db.commit()
                    # 触发自动重新登录 (re-login 用已存号码不花 SMS, 但仍需去重锁)
                    if (
                        failure_reason
                        in {
                            "cookies_expired",
                            "token_invalidated",
                            "chatgpt_not_logged_in",
                            "chatgpt_auth_redirect",
                        }
                        and account_id
                        and query.target_llm != "doubao"
                    ):
                        if query.target_llm == "chatgpt":
                            logger.warning(
                                "Query %s: ChatGPT account %s requires manual reauth "
                                "after %s; no SMS auto-login handler is registered",
                                query_id,
                                account_id,
                                failure_reason,
                            )
                        elif await should_enqueue_relogin(account_id):
                            auto_login.apply_async(
                                kwargs={"account_id": account_id},
                                queue="account_login",
                            )
                    logger.warning(f"Query {query_id} failed ({failure_reason}: {resp_len} chars)")
                    return {"query_id": query_id, "status": "failed", "reason": f"{failure_reason}:{resp_len}"}

            except AccountSessionLockTimeout as e:
                # Refs #928: AccountSessionLockTimeout means the Celery task could
                # not enter the per-account scraper session lock within the deadline
                # (Redis lock contention from concurrent Doubao queries on the same
                # account). It is NOT a browser timeout, so do not mislabel it as
                # "browser_timeout" — that hides the real lock-contention signal
                # operators need to size accounts / worker pool. See related #920.
                failure_reason = "scraper_session_lock_timeout"
                logger.warning(
                    "Query %s delayed by scraper account session lock: %s",
                    query_id,
                    e,
                )
                mark_query_finished(
                    query,
                    status=QueryStatus.FAILED.value,
                    started_at=started_at,
                    reason=failure_reason,
                )
                await quota_settlement.settle_failure(
                    db,
                    pool,
                    reason=failure_reason,
                )
                await db.commit()
                return {
                    "query_id": query_id,
                    "status": "failed",
                    "reason": failure_reason,
                }

            except Exception as e:
                logger.exception(f"Query {query_id} exception: {e}")
                # 原事务可能已被 aborted（例如 FK 违约），先回滚让 session 可写
                try:
                    await db.rollback()
                except Exception:
                    pass
                # 重新读取 query 实体，再写回 FAILED，保证 status 一定离开 running
                try:
                    refetched = await db.execute(
                        select(Query).where(Query.id == query_id)
                    )
                    q_obj = refetched.scalar_one_or_none()
                    if q_obj is not None:
                        mark_query_finished(
                            q_obj,
                            status=QueryStatus.FAILED.value,
                            started_at=started_at,
                            reason="exception",
                        )
                    await db.commit()
                except Exception as commit_err:
                    logger.error(
                        f"Query {query_id}: failed to write FAILED status "
                        f"after rollback: {commit_err}"
                    )
                # 账号失败上报走独立 try，避免把主状态写回再次打断
                if account_id and pool:
                    try:
                        await quota_settlement.settle_failure(
                            db,
                            pool,
                            reason="exception",
                        )
                    except Exception as pool_err:
                        logger.error(
                            f"Query {query_id}: account failure settlement raised: {pool_err}"
                        )
                return {"query_id": query_id, "status": "failed", "error": str(e)}

    try:
        result = loop.run_until_complete(_run())
        return result
    except SoftTimeLimitExceeded:
        logger.exception("execute_query %s exceeded soft time limit", query_id)
        try:
            _mark_query_failed_after_task_abort(
                query_id,
                "soft_time_limit",
                quota_settlement=quota_settlement,
            )
        except Exception as cleanup_exc:
            logger.error(
                "execute_query %s failed to mark soft-timeout failure: %s",
                query_id,
                cleanup_exc,
            )
        return {
            "query_id": query_id,
            "status": "failed",
            "reason": "soft_time_limit",
        }
    except Exception as exc:
        logger.exception(f"execute_query {query_id} raised: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        safe_dispose_engine(loop, task_engine, logger)
        loop.close()


@app.task(queue="celery")
def dispatch_batch(limit: int = 50) -> dict:
    """扫描 pending queries，分发到 execute_query"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        from sqlalchemy import text as sa_text
        async with get_task_async_session(task_engine) as db:
            stale_report = await repair_stale_running_queries(
                db,
                max_age_seconds=_env_int(
                    "QUERY_STALE_RUNNING_SECONDS",
                    DEFAULT_STALE_RUNNING_SECONDS,
                ),
            )
            if stale_report.repaired:
                logger.warning(
                    "Repaired %s stale running queries before dispatch_batch: %s",
                    stale_report.repaired,
                    stale_report.to_dict(),
                )
            # Debug: raw SQL count to verify DB connectivity and status values
            raw = await db.execute(
                sa_text("SELECT status, COUNT(*) as n FROM queries GROUP BY status ORDER BY n DESC LIMIT 10")
            )
            status_counts = {r[0]: r[1] for r in raw.fetchall()}
            logger.info(f"dispatch_batch DB status counts: {status_counts}")

            result = await db.execute(
                select(Query)
                .where(Query.status == QueryStatus.PENDING.value)
                .limit(limit)
            )
            queries = result.scalars().all()

            dispatched = 0
            for q in queries:
                execute_query.apply_async(
                    args=[q.id],
                    queue=f"llm_{q.target_llm}",
                )
                dispatched += 1

            logger.info(f"Dispatched {dispatched} queries (pending_value={QueryStatus.PENDING.value!r})")
            return {"dispatched": dispatched}

    try:
        return loop.run_until_complete(_run())
    finally:
        safe_dispose_engine(loop, task_engine, logger)
        loop.close()


@app.task(queue="celery")
def reset_daily_counts() -> dict:
    """每日 UTC 00:00 重置所有账号的查询计数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        async with get_task_async_session(task_engine) as db:
            pool = AccountPool(db)
            await pool.reset_daily_counts()
            return {"status": "ok"}

    try:
        return loop.run_until_complete(_run())
    finally:
        safe_dispose_engine(loop, task_engine, logger)
        loop.close()


@app.task(queue="celery")
def cookie_keep_alive() -> dict:
    """
    定期访问各 LLM 页面保持 cookies 活跃，防止 session 过期。
    只访问页面、不发送消息，模拟正常用户浏览行为。
    每 6 小时运行一次（Celery Beat 调度）。
    """
    import random

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        results = {"refreshed": 0, "failed": 0, "skipped": 0, "details": []}
        run_id = f"cookie_keep_alive:{uuid.uuid4().hex[:12]}"

        async with get_task_async_session(task_engine) as db:
            pool = AccountPool(db)
            # 获取所有有 cookies 的活跃账号
            stmt = select(LLMAccount).where(
                LLMAccount.status == AccountStatus.ACTIVE.value,
                LLMAccount.cookies_json != None,
                LLMAccount.cookies_json != "",
            )
            result = await db.execute(stmt)
            accounts = result.scalars().all()

            if not accounts:
                logger.info("cookie_keep_alive: no active accounts with cookies")
                return results

            logger.info(f"cookie_keep_alive: checking {len(accounts)} accounts")

            for account in accounts:
                llm_name = account.llm_name
                config = GUEST_LLM_CONFIG.get(llm_name)
                if not config or not config.get("url"):
                    results["skipped"] += 1
                    continue

                try:
                    proxy_url = _keep_alive_proxy_url(llm_name)
                    executor = GuestQueryExecutor(
                        proxy_url=proxy_url,
                        account_cookies=account.cookies_json,
                    )

                    refreshed_cookies = await _visit_and_refresh(
                        executor, config, llm_name
                    )

                    if refreshed_cookies:
                        from datetime import datetime as dt
                        # 保留 localStorage 数据（新格式）
                        previous_status = str(account.status or "")
                        account.cookies_json = _merge_refreshed_cookie_payload(
                            account.cookies_json,
                            refreshed_cookies,
                        )
                        account.cookies_updated_at = dt.utcnow()
                        await db.commit()
                        results["refreshed"] += 1
                        results["details"].append(
                            f"#{account.id} {llm_name}: refreshed {len(refreshed_cookies)} cookies"
                        )
                        logger.info(
                            "cookie_keep_alive lifecycle account_id=%s engine=%s "
                            "previous_status=%s new_status=%s reason=%s "
                            "run_id=%s evidence=%s account_ref=%s",
                            account.id,
                            llm_name,
                            previous_status or "unknown",
                            str(account.status or ""),
                            "keep_alive_refreshed",
                            run_id,
                            f"cookie_count={len(refreshed_cookies)}",
                            f"id:{account.id}",
                        )
                    else:
                        results["failed"] += 1
                        failure_reason = (
                            getattr(executor, "last_error_reason", None)
                            or "cookie_keep_alive_probe_failed"
                        )
                        evidence = (
                            getattr(executor, "keep_alive_evidence", None)
                            or "probe_result=none"
                        )
                        results["details"].append(
                            f"#{account.id} {llm_name}: refresh failed reason={failure_reason}"
                        )
                        logger.warning(
                            "cookie_keep_alive lifecycle account_id=%s engine=%s "
                            "previous_status=%s new_status=%s reason=%s "
                            "run_id=%s evidence=%s account_ref=%s",
                            account.id,
                            llm_name,
                            str(account.status or "unknown"),
                            (
                                AccountStatus.EXPIRED.value
                                if failure_reason in EXPIRED_ACCOUNT_REASONS
                                else str(account.status or "unknown")
                            ),
                            failure_reason,
                            run_id,
                            evidence,
                            f"id:{account.id}",
                        )
                        if failure_reason in EXPIRED_ACCOUNT_REASONS:
                            await pool.report_failure(
                                account.id,
                                reason=failure_reason,
                                evidence=evidence,
                                provider="cookie_keep_alive",
                                run_id=run_id,
                            )
                            await db.refresh(account)
                        # 触发自动重新登录 (生产事故 2026-04-27: 加去重锁,
                        # 防止 keep-alive 周期性反复触发同账号登录)
                        if (
                            _keep_alive_should_enqueue_relogin(
                                llm_name,
                                failure_reason,
                            )
                            and await should_enqueue_relogin(account.id)
                        ):
                            auto_login.apply_async(
                                kwargs={"account_id": account.id},
                                queue="account_login",
                            )
                        else:
                            logger.info(
                                "cookie_keep_alive: auto re-login skipped "
                                "after refresh failure"
                            )

                    # 随机间隔，避免同时访问多个平台被检测
                    await asyncio.sleep(random.uniform(10, 30))

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(f"#{account.id} {llm_name}: error {e}")
                    logger.exception(
                        f"cookie_keep_alive: #{account.id} {llm_name} exception: {e}"
                    )

        return results

    try:
        return loop.run_until_complete(_run())
    finally:
        safe_dispose_engine(loop, task_engine, logger)
        loop.close()


# Refs #963 audit pain point #1: proactive pool pre-warming.
# Today new-account registration is REACTIVE — ``execute_query`` only enqueues
# ``auto_login(new_account=True)`` after a query has already failed because the
# active pool is empty. When the pool collapses (e.g. production verify dump
# 2026-05-16T15:09:58Z showed ``active=0, cooldown=1, expired=22, banned=3``),
# the next user query has to wait the full SMS-register round-trip (~60s of
# browser + LubanSMS) before it can run, and during that window every other
# query for that engine also fails. Pre-warming runs every N minutes, checks
# per-engine *usable* counts (predicates match ``AccountPool.acquire()``), and
# enqueues at most ONE new-account registration per beat per engine: the
# platform-wide in-flight lock ``genpano:autologin:newaccount:{platform}``
# (10-min TTL) serializes new-account registration intentionally, so a deficit
# of N is drained across N beat cycles rather than burned in a single tight
# loop. Respects ``should_enqueue_new_account()`` so it cannot double up with
# the reactive path or skip the 30-min failure cooldown.
PREWARM_DEFAULT_TARGETS_BY_ENGINE = {
    "doubao": 3,
    # DeepSeek / ChatGPT are not the immediate #963 bottleneck but the pre-warm
    # loop scans them too so operators can flip a target on via env without a
    # code change. Default target=0 means "do not pre-warm" — pre-existing
    # reactive behavior is unchanged for them.
    "deepseek": 0,
    "chatgpt": 0,
}


def _prewarm_target_active(engine: str) -> int:
    # Doubao has a dedicated env so operators can tune it independently.
    if engine == "doubao":
        return _env_int(
            "DOUBAO_TARGET_ACTIVE_POOL",
            PREWARM_DEFAULT_TARGETS_BY_ENGINE.get("doubao", 0),
        )
    env_name = f"{engine.upper()}_TARGET_ACTIVE_POOL"
    return _env_int(
        env_name,
        PREWARM_DEFAULT_TARGETS_BY_ENGINE.get(engine, 0),
    )


@app.task(queue="celery")
def prewarm_account_pool() -> dict:
    """Proactive pool pre-warming (Refs #963 audit pain point #1).

    Every N minutes (Celery Beat), for each engine in
    ``PREWARM_DEFAULT_TARGETS_BY_ENGINE``:

    1. Compute ``usable_count`` via :func:`count_acquirable_accounts`,
       which mirrors :meth:`AccountPool.acquire`'s predicate set
       (status='active' AND cookies_json present AND cooldown elapsed AND
       query_count_today < daily_limit). Plain ``status='active'`` count is
       NOT enough — rows with NULL cookies or exhausted quota are labeled
       active but ``acquire()`` would skip them. Refs Codex P2 review
       https://github.com/jotamotk/trash_test/pull/1102#discussion_r3253924434.
    2. If ``usable_count < TARGET_ACTIVE``, enqueue at most ONE
       ``auto_login(platform=engine, new_account=True)`` per beat per
       engine.

       Why at most one and not ``deficit``-many: the gate
       :func:`should_enqueue_new_account` acquires a platform-wide SETNX
       lock (``genpano:autologin:newaccount:{platform}``, TTL 10 min) so
       the FIRST enqueue takes the lock and any second iteration of the
       loop would immediately see the lock held and break. Looping past
       a closed gate is a no-op; emit a single enqueue and let the next
       beat run drain the remaining deficit. With a 10-min beat cadence
       and ~60s typical SMS registration latency, a pool that has fallen
       to ``deficit=3`` is fully refilled in ~30–40 min — acceptable given
       the platform-wide lock's purpose (prevent parallel SMS spend on the
       same engine — see PR #1042 / #1097 territory). Refs Codex P2 review
       https://github.com/jotamotk/trash_test/pull/1102#discussion_r3253924436.
    3. The enqueue goes through :func:`should_enqueue_new_account` so we
       inherit the in-flight lock + 30-min failure cooldown that already
       exists on the reactive path — no double registration, no SMS waste
       during a failure cooldown.
    4. Emit one INFO summary line so operators can confirm the loop fired.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run() -> dict:
        run_id = f"prewarm_pool:{uuid.uuid4().hex[:12]}"
        per_engine: dict[str, dict] = {}
        total_enqueued = 0

        async with get_task_async_session(task_engine) as db:
            for engine in sorted(PREWARM_DEFAULT_TARGETS_BY_ENGINE.keys()):
                target = _prewarm_target_active(engine)
                snap = await snapshot_pool_health(db, engine)
                # P2 #1 fix: deficit must be based on the count
                # ``AccountPool.acquire()`` would actually return — not just
                # ``status='active'``. A row labeled active but with
                # ``cookies_json=NULL`` or ``query_count_today >= daily_limit``
                # is NOT acquirable, so it must not count toward the deficit.
                usable = await count_acquirable_accounts(db, engine)
                deficit = max(0, target - usable)
                enqueued_for_engine = 0
                lock_skips = 0

                # When target<=0 the engine is opted out of pre-warming;
                # snapshot the pool anyway so operators can grep the same log
                # line for every engine.
                #
                # P2 #2 (Option A): enqueue AT MOST ONE per engine per beat
                # because ``should_enqueue_new_account`` acquires the
                # platform-wide in-flight lock; further iterations would
                # only spin against a closed gate. The remaining deficit is
                # drained over subsequent beat cycles.
                if target > 0 and deficit > 0:
                    if await should_enqueue_new_account(engine):
                        auto_login.apply_async(
                            kwargs={
                                "platform": engine,
                                "new_account": True,
                            },
                            queue="account_login",
                        )
                        enqueued_for_engine = 1
                        total_enqueued += 1
                    else:
                        # In-flight lock held OR failure cooldown is active.
                        # Nothing to do this beat; next beat will retry.
                        lock_skips = 1

                per_engine[engine] = {
                    "target_active": target,
                    "active": snap.active,
                    "usable": usable,
                    "cooldown": snap.cooldown,
                    "expired": snap.expired,
                    "banned": snap.banned,
                    "with_cookies": snap.with_cookies,
                    "deficit": deficit,
                    "enqueued": enqueued_for_engine,
                    "lock_skipped": lock_skips,
                }

        logger.info(
            "prewarm_account_pool run_id=%s total_enqueued=%s per_engine=%s",
            run_id,
            total_enqueued,
            per_engine,
        )
        return {
            "run_id": run_id,
            "total_enqueued": total_enqueued,
            "per_engine": per_engine,
        }

    try:
        return loop.run_until_complete(_run())
    finally:
        safe_dispose_engine(loop, task_engine, logger)
        loop.close()


@app.task(queue="account_login", bind=True, max_retries=1)
def auto_login(
    self,
    account_id: int = None,
    platform: str = None,
    new_account: bool = False,
    query_id: int | None = None,
) -> dict:
    """
    自动 SMS 登录/注册，独立于 query 执行。

    场景 1: account_id 有值 → 已有账号重新登录（用 DB 里的 phone_number）
    场景 2: new_account=True → 注册新账号（LubanSMS 获取新号码，每次 ~1元）

    生产事故 2026-04-27 SMS 浪费根因修复:
      1. 任务结束 (success/failure/exception) 必须释放 in-flight 锁
      2. 新注册失败必须设 30 min cooldown, 防止 query 风暴期反复扣费
      3. retry 进入任务体时先检查 cooldown, 命中则跳过避免再扣费
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        from geo_tracker.agent.sms_login import get_handler
        from geo_tracker.agent.sms_login.registration_lock import _redis_url, _cooldown_key
        import redis.asyncio as aioredis

        # 任务体内 cooldown 双重保护: Celery retry 不经过 enqueue 锁,
        # 必须在这里再查一次, 避免 max_retries 期间继续扣费.
        if new_account and platform:
            try:
                _client = aioredis.from_url(_redis_url(), decode_responses=True)
                _on_cooldown = await _client.exists(_cooldown_key(platform))
                await _client.aclose()
                if _on_cooldown:
                    logger.warning(
                        f"auto_login: {platform} new-account in cooldown, "
                        f"aborting to save SMS"
                    )
                    return {"status": "skipped", "reason": "cooldown_active"}
            except Exception as e:
                logger.warning(f"auto_login: cooldown check failed (fail-open): {e}")

        async with get_task_async_session(task_engine) as db:
            pool = AccountPool(db)

            # 场景 1: 已有账号重新登录
            if account_id:
                result = await db.execute(
                    select(LLMAccount).where(LLMAccount.id == account_id)
                )
                account = result.scalar_one_or_none()
                if not account:
                    return {"status": "error", "reason": f"account {account_id} not found"}

                handler = get_handler(account.llm_name)
                if not handler:
                    return {"status": "error", "reason": f"no handler for {account.llm_name}"}

                # Refs #963: existing production rows (accounts 43/44/45 etc.)
                # already have masked values like "147****0231" stored in
                # ``phone_number``. PR #1086 stopped the write-time bleed,
                # but the rows that pre-date it can never re-login because
                # ``BaseSMSLoginHandler.login_or_register`` rejects any phone
                # that fails the handler's ``phone_relogin_pattern`` when
                # ``existing_cookies`` is set, leaving the account stuck in
                # ``expired`` forever. When the stored phone is
                # masked/invalid we cannot recover the original number, so
                # the only path back to a working state is a fresh
                # registration: call ``login_or_register`` with
                # ``existing_cookies=None, phone=None`` so the handler
                # allocates a brand-new SMS number and cookies, and the
                # bot-flagged row is overwritten in place.
                #
                # Codex P2 review on PR #1088: the pattern is handler-
                # specific (Doubao=``\d{11}``, ChatGPT=``\+?1\d{10}``).
                # Validating against a hardcoded ``\d{11}`` here would
                # misclassify a valid stored ChatGPT number like
                # ``+17000007065`` as unavailable and discard reusable
                # cookies. Mirror BaseSMSLoginHandler.login_or_register's
                # own validation by using the handler's pattern.
                stored_phone_raw = account.phone_number or ""
                phone_is_masked = "*" in stored_phone_raw
                handler_phone_pattern = getattr(
                    handler, "phone_relogin_pattern", r"\d{11}"
                )
                phone_matches_handler_pattern = bool(
                    stored_phone_raw
                    and re.fullmatch(handler_phone_pattern, stored_phone_raw)
                )
                # Empty phone or any phone that doesn't match the selected
                # handler's pattern means the handler would reject it on the
                # re-login path; fall back to new-account registration.
                phone_unavailable = phone_is_masked or not phone_matches_handler_pattern
                if phone_unavailable:
                    logger.warning(
                        "auto_login: account #%s stored phone=%s is "
                        "masked/invalid; falling back to new-account "
                        "registration flow (Refs #963)",
                        account_id,
                        mask_phone(stored_phone_raw) if stored_phone_raw else "<empty>",
                    )

                logger.info(
                    f"auto_login: re-login account #{account_id} "
                    f"({account.llm_name}, phone={mask_phone(account.phone_number)})"
                )
                if phone_unavailable:
                    login_result = await handler.login_or_register(
                        existing_cookies=None,
                        phone=None,
                    )
                else:
                    login_result = await handler.login_or_register(
                        existing_cookies=account.cookies_json,
                        phone=account.phone_number,
                    )

                if login_result and login_result.get("cookies"):
                    from datetime import datetime as dt
                    previous_status = str(account.status or "")
                    # 打包 cookies + localStorage + storageState + Camoufox
                    # fingerprint (如有) 为新格式. Refs #963: the Camoufox
                    # fingerprint is the key piece — without it, every query
                    # opens with a NEW random Firefox fingerprint and Doubao
                    # invalidates the session within seconds. Persisting it
                    # alongside cookies makes the fingerprint sticky per
                    # account.
                    cookies_data = login_result["cookies"]
                    local_storage = login_result.get("localStorage", {})
                    storage_state = login_result.get("storageState", {})
                    camoufox_fp = login_result.get("camoufoxFingerprint")
                    if local_storage or storage_state or camoufox_fp:
                        cookie_payload = {"cookies": cookies_data}
                        if local_storage:
                            cookie_payload["localStorage"] = local_storage
                        if storage_state:
                            cookie_payload["storageState"] = storage_state
                        if camoufox_fp:
                            cookie_payload["camoufoxFingerprint"] = camoufox_fp
                        account.cookies_json = json_mod.dumps(cookie_payload)
                    else:
                        account.cookies_json = json_mod.dumps(cookies_data)
                    account.cookies_updated_at = dt.utcnow()
                    account.status = AccountStatus.ACTIVE.value
                    account.cooldown_until = None
                    account.consecutive_fails = 0
                    if login_result.get("phone"):
                        # Refs #963: the re-login handler returns the raw
                        # SMS lease phone here, but we still guard against
                        # any future regression that swaps in mask_phone()
                        # output. Storing the masked form (e.g.
                        # ``"147****0231"``) would break the
                        # ``\\d{11}``-fullmatch in
                        # ``BaseSMSLoginHandler.login_or_register`` on the
                        # NEXT re-login attempt, leaving the account
                        # permanently stuck on a Doubao-bot-flagged
                        # cookie set with no recovery path.
                        relogin_phone = login_result["phone"]
                        if "*" in str(relogin_phone):
                            logger.error(
                                "auto_login: refusing to overwrite "
                                "account #%s phone_number with masked "
                                "value %r (re-login handler returned "
                                "mask_phone() output instead of the raw "
                                "SMS lease); keeping prior phone_number "
                                "intact",
                                account_id,
                                mask_phone(relogin_phone),
                            )
                        else:
                            account.phone_number = relogin_phone
                    await db.commit()
                    if previous_status != AccountStatus.ACTIVE.value:
                        logger.info(
                            "Account lifecycle transition account_id=%s engine=%s "
                            "previous_status=%s new_status=%s reason=%s evidence=%s "
                            "provider=shared_login price_bucket=none run_id=none account_ref=%s",
                            account_id,
                            account.llm_name,
                            previous_status or "unknown",
                            AccountStatus.ACTIVE.value,
                            "auto_login_success",
                            "cookie_write_back",
                            f"id:{account_id}",
                        )
                    logger.info(f"auto_login: account #{account_id} re-login SUCCESS")
                    result_payload = {"status": "success", "account_id": account_id}
                    if account.llm_name == "doubao":
                        requeued = await _requeue_doubao_query_after_reauth(
                            db,
                            account_id=account_id,
                            query_id=query_id,
                        )
                        if requeued:
                            result_payload["requeued_query_id"] = query_id
                    return result_payload
                else:
                    reason = (login_result or {}).get("reason", "unknown")
                    logger.warning(f"auto_login: account #{account_id} re-login FAILED: {reason}")
                    return {"status": "failed", "account_id": account_id, "reason": reason}

            # 场景 2: 注册新账号
            elif new_account and platform:
                handler = get_handler(platform)
                if not handler:
                    return {"status": "error", "reason": f"no handler for {platform}"}

                logger.info(f"auto_login: registering new {platform} account")
                login_result = await handler.login_or_register()

                if login_result and login_result.get("cookies"):
                    # 打包 cookies + localStorage + storageState + Camoufox
                    # fingerprint (如有) 为新格式. Refs #963: same fingerprint
                    # persistence as the re-login branch — see comment above.
                    cookies_data = login_result["cookies"]
                    local_storage = login_result.get("localStorage", {})
                    storage_state = login_result.get("storageState", {})
                    camoufox_fp = login_result.get("camoufoxFingerprint")
                    if local_storage or storage_state or camoufox_fp:
                        cookie_payload = {"cookies": cookies_data}
                        if local_storage:
                            cookie_payload["localStorage"] = local_storage
                        if storage_state:
                            cookie_payload["storageState"] = storage_state
                        if camoufox_fp:
                            cookie_payload["camoufoxFingerprint"] = camoufox_fp
                        cookies_json_str = json_mod.dumps(cookie_payload)
                    else:
                        cookies_json_str = json_mod.dumps(cookies_data)
                    new_account_obj = await pool.create_account(
                        llm_name=platform,
                        phone=login_result["phone"],
                        cookies_json=cookies_json_str,
                    )
                    logger.info(
                        f"auto_login: new {platform} account #{new_account_obj.id} "
                        f"created (phone={mask_phone(login_result['phone'])})"
                    )
                    result_payload = {
                        "status": "success",
                        "account_id": new_account_obj.id,
                        "phone": login_result["phone"],
                    }
                    if platform == "doubao":
                        requeued_id = await _requeue_doubao_query_after_new_account(
                            db,
                            account_id=new_account_obj.id,
                            query_id=query_id,
                        )
                        if requeued_id is not None:
                            result_payload["requeued_query_id"] = requeued_id
                    return result_payload
                else:
                    reason = (login_result or {}).get("reason", "unknown")
                    logger.warning(f"auto_login: new {platform} registration FAILED: {reason}")
                    return {"status": "failed", "platform": platform, "reason": reason}

            else:
                return {"status": "error", "reason": "invalid arguments"}

    succeeded = False
    cooldown_skipped = False
    try:
        result = loop.run_until_complete(_run())
        # success 判断: status 字段 == 'success'. skipped/failed/error 都视为非成功.
        succeeded = isinstance(result, dict) and result.get("status") == "success"
        cooldown_skipped = (
            isinstance(result, dict)
            and result.get("status") == "skipped"
            and result.get("reason") == "cooldown_active"
        )
        return result
    except Exception as exc:
        logger.exception(f"auto_login exception: {exc}")
        raise self.retry(exc=exc, countdown=120)
    finally:
        # 生产事故 2026-04-27 SMS 浪费根因修复: 释放锁 + 失败时设 cooldown.
        # 必须在 task_engine.dispose() 前完成, 不依赖 DB.
        try:
            if account_id is not None:
                loop.run_until_complete(release_relogin_lock(account_id))
            elif new_account and platform:
                loop.run_until_complete(
                    release_new_account_lock(
                        platform,
                        failed=not succeeded and not cooldown_skipped,
                    )
                )
        except Exception as e:
            logger.warning(f"auto_login: lock release best-effort failed: {e}")
        safe_dispose_engine(loop, task_engine, logger)
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis Tasks
# ═══════════════════════════════════════════════════════════════════════════════

@app.task(bind=True, max_retries=2, queue="analysis")
def analyze_response(self, response_id: int, analyzer_run_id: int | None = None) -> dict:
    """Run the 3-stage analysis pipeline on a single LLMResponse."""
    logger.info(f"analyze_response started for response_id={response_id}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        from geo_tracker.analyzer.cli import analyze_single_response
        from geo_tracker.tasks.analyzer_handoff import mark_analyzer_run_handoff_failed

        async with get_task_async_session(task_engine) as db:
            resp = await db.get(LLMResponse, response_id)
            if not resp:
                if analyzer_run_id is not None:
                    return await mark_analyzer_run_handoff_failed(
                        db,
                        analyzer_run_id=int(analyzer_run_id),
                        response_id=response_id,
                        failure_code="response_not_found",
                        failure_message=(
                            f"LLMResponse {response_id} was not found before analyzer handoff."
                        ),
                    )
                return {"skipped": True, "reason": "response_not_found"}

            if resp.analysis_status == AnalysisStatus.DONE.value and analyzer_run_id is None:
                return {"skipped": True, "reason": "already_analyzed"}

            query = await db.get(Query, resp.query_id)
            if not query:
                if analyzer_run_id is not None:
                    return await mark_analyzer_run_handoff_failed(
                        db,
                        analyzer_run_id=int(analyzer_run_id),
                        response_id=response_id,
                        failure_code="query_not_found",
                        failure_message=(
                            f"Query {resp.query_id} was not found before analyzer handoff."
                        ),
                        previous_analysis_status=resp.analysis_status,
                    )
                return {"skipped": True, "reason": "query_not_found"}
            brand = await db.get(Brand, query.brand_id)
            if not brand:
                if analyzer_run_id is not None:
                    return await mark_analyzer_run_handoff_failed(
                        db,
                        analyzer_run_id=int(analyzer_run_id),
                        response_id=response_id,
                        failure_code="brand_not_found",
                        failure_message=(
                            f"Brand {query.brand_id} was not found before analyzer handoff."
                        ),
                        previous_analysis_status=resp.analysis_status,
                    )
                return {"skipped": True, "reason": "brand_not_found"}

            comp_result = await db.execute(
                select(Competitor).where(Competitor.brand_id == brand.id)
            )
            competitors = comp_result.scalars().all()

            intent = "non_brand"
            if query.prompt_id:
                prompt = await db.get(Prompt, query.prompt_id)
                if prompt and prompt.intent:
                    intent = prompt.intent

            return await analyze_single_response(
                db,
                resp,
                brand,
                competitors,
                intent,
                analyzer_run_id=analyzer_run_id,
                trigger_source="admin_submit" if analyzer_run_id is not None else "pipeline",
            )

    try:
        return loop.run_until_complete(_run())
    except Exception as exc:
        logger.exception(f"analyze_response {response_id} raised: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        try:
            loop.run_until_complete(task_engine.dispose())
        except Exception:
            pass
        loop.close()


@app.task(queue="analysis")
def run_daily_analysis(date_str: str = None, brand_id: int = None) -> dict:
    """
    每日分析主入口：分析当天所有 PENDING 响应，然后聚合。

    Args:
        date_str: YYYY-MM-DD，默认今天
        brand_id: 指定品牌，None = 所有品牌
    """
    from datetime import datetime as dt

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _run():
        from geo_tracker.analyzer.cli import run_daily
        if not date_str:
            d = dt.utcnow().strftime("%Y-%m-%d")
        else:
            d = date_str
        await run_daily(d, brand_id)
        return {"status": "done", "date": d, "brand_id": brand_id}

    try:
        return loop.run_until_complete(_run())
    except Exception as exc:
        logger.exception(f"run_daily_analysis failed: {exc}")
        return {"status": "failed", "error": str(exc)}
    finally:
        loop.close()


@app.task(queue="analysis")
def aggregate_daily_scores(date_str: str = None, brand_id: int = None) -> dict:
    """
    每日聚合三张表（UPSERT）：
    1. GEOScoreDaily — 品牌级聚合
    2. IndustryBenchmarkDaily — 行业基准聚合
    3. ProductScoreDaily — 产品级聚合
    """
    from datetime import datetime as dt

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        from geo_tracker.analyzer.aggregator import Aggregator

        date = dt.strptime(date_str, "%Y-%m-%d") if date_str else dt.utcnow()
        async with get_task_async_session(task_engine) as db:
            aggregator = Aggregator(db)
            stats = await aggregator.aggregate_daily(date, brand_id)
            return {"status": "done", "stats": stats}

    try:
        return loop.run_until_complete(_run())
    except Exception as exc:
        logger.exception(f"aggregate_daily_scores failed: {exc}")
        return {"status": "failed", "error": str(exc)}
    finally:
        try:
            loop.run_until_complete(task_engine.dispose())
        except Exception:
            pass
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════════

async def _visit_and_refresh(
    executor: GuestQueryExecutor, config: dict, llm_name: str
) -> list | None:
    """
    仅访问 LLM 页面（不发送消息），检查 cookies 是否有效，
    返回刷新后的 cookies 列表，失败返回 None。
    """
    import random
    from playwright.async_api import async_playwright

    try:
        from camoufox.async_api import AsyncCamoufox
        has_camoufox = True
    except ImportError:
        has_camoufox = False

    use_proxy = bool(
        executor.proxy_url
        and (llm_name not in DOMESTIC_LLMS or llm_name == "doubao")
    )
    needs_stealth = bool(executor.account_cookies)
    use_camoufox = has_camoufox and (use_proxy or needs_stealth)

    page = None
    context = None
    browser = None
    _camoufox_ctx = None
    _playwright = None

    try:
        is_domestic = llm_name in DOMESTIC_LLMS

        if use_camoufox:
            camoufox_kwargs = {
                "headless": True,
                "humanize": True,
                "block_images": True,
                "os": "windows",
                "locale": "zh-CN" if is_domestic else "en-US",
            }
            if use_proxy:
                camoufox_kwargs["proxy"] = {"server": executor.proxy_url}

            _camoufox_ctx = AsyncCamoufox(**camoufox_kwargs)
            browser = await _camoufox_ctx.__aenter__()
            context = await browser.new_context()
            await install_resource_blocker(context)
        else:
            _playwright = await async_playwright().start()
            browser = await _playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu", "--no-zygote",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN" if is_domestic else "en-US",
                timezone_id="Asia/Shanghai" if is_domestic else "America/New_York",
            )
            await install_resource_blocker(context)

        # 注入 cookies（支持新旧两种格式）
        parsed = json_mod.loads(executor.account_cookies)
        if isinstance(parsed, dict) and "cookies" in parsed:
            cookies = parsed["cookies"]
        elif isinstance(parsed, list):
            cookies = parsed
        else:
            cookies = []
        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        if not use_camoufox:
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                delete navigator.__proto__.webdriver;
            """)

        # 访问页面
        url = config["url"]
        logger.info(f"cookie_keep_alive: visiting {url} for {llm_name}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # 等待页面加载
        await page.wait_for_timeout(random.randint(3000, 6000))

        # 检查是否被重定向到登录页
        auth_reason, evidence = await _keep_alive_probe_failure_reason(
            llm_name,
            config,
            page,
        )
        if auth_reason:
            executor.last_error_reason = auth_reason
            executor.keep_alive_evidence = evidence
            logger.warning(
                "cookie_keep_alive: %s auth probe failed reason=%s evidence=%s",
                llm_name,
                auth_reason,
                evidence,
            )
            return None

        # 豆包特殊检测
        if llm_name == "doubao":
            body_text = await page.evaluate("document.body?.innerText || ''")
            login_keywords = [
                "登录后免费使用", "用户协议", "隐私政策",
                "抖音一键登录", "豆包账号服务须知",
                "下载豆包电脑版", "你好，我是豆包",
            ]
            matched = [kw for kw in login_keywords if kw in body_text]
            if len(matched) >= 2:
                executor.last_error_reason = "doubao_not_logged_in"
                executor.keep_alive_evidence = (
                    f"url_host={_safe_url_host(getattr(page, 'url', None))} "
                    "body_marker=login_chrome"
                )
                logger.warning(
                    f"cookie_keep_alive: {llm_name} login page detected "
                    f"(matched: {matched})"
                )
                return None

        # 模拟人类浏览：随机滚动
        if llm_name == "chatgpt":
            auth_reason, evidence = await _chatgpt_keep_alive_session_failure_reason(page)
            if auth_reason:
                executor.last_error_reason = auth_reason
                executor.keep_alive_evidence = evidence
                logger.warning(
                    "cookie_keep_alive: %s session probe failed reason=%s evidence=%s",
                    llm_name,
                    auth_reason,
                    evidence,
                )
                return None
            try:
                await page.goto(config["url"], wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(random.randint(1000, 3000))
            except Exception:
                pass

        try:
            await page.mouse.move(
                random.randint(200, 800), random.randint(200, 500),
                steps=random.randint(3, 8),
            )
            await page.wait_for_timeout(random.randint(1000, 3000))
            await page.mouse.wheel(0, random.randint(100, 300))
            await page.wait_for_timeout(random.randint(1000, 2000))
        except Exception:
            pass

        # 获取刷新后的 cookies
        new_cookies = await context.cookies()
        if new_cookies:
            refreshed = []
            for c in new_cookies:
                entry = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c.get("path", "/"),
                }
                if c.get("expires", -1) > 0:
                    entry["expires"] = c["expires"]
                if c.get("httpOnly"):
                    entry["httpOnly"] = True
                if c.get("secure"):
                    entry["secure"] = True
                if c.get("sameSite") and c["sameSite"] != "None":
                    entry["sameSite"] = c["sameSite"]
                refreshed.append(entry)
            logger.info(
                f"cookie_keep_alive: {llm_name} got {len(refreshed)} cookies after visit"
            )
            return refreshed

        return None

    except Exception as e:
        logger.exception(f"cookie_keep_alive: {llm_name} visit error: {e}")
        return None
    finally:
        # 生产事故 2026-04-27 根因修复 (与 guest_executor.py 同根因):
        # browser.close() 偶尔 hang, 原 try/except 捕不了 → finally 链断 → 进程泄漏.
        await cleanup_browser_resources(
            page=page,
            context=context,
            browser=browser,
            camoufox_ctx=_camoufox_ctx,
            playwright=_playwright,
        )
