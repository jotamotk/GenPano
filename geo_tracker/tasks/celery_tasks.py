"""
Celery 任务定义
- execute_query: 单条 Query 执行（无账号模式优先）
- dispatch_batch: 批量分发 pending queries
- reset_daily_counts: 每日重置账号计数（Beat调度）
"""
from __future__ import annotations

import asyncio
import logging
import os

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import delete as sa_delete, select

from geo_tracker.agent.guest_executor import GuestQueryExecutor, GUEST_LLM_CONFIG
from geo_tracker.db.models import Query, QueryStatus, LLMResponse
from geo_tracker.pool.account_pool import AccountPool

# 数据库 & Redis 连接（实际项目从 config 读取）
from geo_tracker.config import create_task_engine, get_task_async_session, REDIS_URL

logger = logging.getLogger(__name__)

app = Celery("geo_tracker", broker=REDIS_URL, backend=REDIS_URL)

app.conf.update(
    task_serializer   = "json",
    result_serializer = "json",
    timezone          = "UTC",
    task_max_retries  = 3,
    task_default_retry_delay = 60,
    worker_concurrency = 2,
    beat_schedule = {
        "reset-daily-counts": {
            "task":     "geo_tracker.tasks.celery_tasks.reset_daily_counts",
            "schedule": crontab(hour=0, minute=0),
        },
        # dispatch-pending-queries 已禁用：所有 query 需手动触发
        # "dispatch-pending-queries": {
        #     "task":     "geo_tracker.tasks.celery_tasks.dispatch_batch",
        #     "schedule": crontab(minute="*/5"),
        # },
    },
)


@app.task(bind=True, max_retries=2)
def execute_query(self, query_id: int) -> dict:
    """
    执行单条查询（仅无账号模式）
    """
    # 为每个任务创建新的事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    task_engine = create_task_engine()

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
            query.status = QueryStatus.RUNNING.value
            await db.commit()

            llm_config = GUEST_LLM_CONFIG.get(query.target_llm, {})

            # 对需要登录的 LLM，从 AccountPool 获取账号 cookies
            account = None
            account_id = None
            account_cookies = None
            pool = None

            if llm_config.get("requires_login", True):
                pool = AccountPool(db)
                account = await pool.acquire(query.target_llm)
                if account and account.cookies_json:
                    account_cookies = account.cookies_json
                    account_id = account.id
                    logger.info(
                        f"Query {query_id}: acquired account id={account_id} "
                        f"for {query.target_llm}"
                    )
                else:
                    # 无可用账号，设回 PENDING 等下次重试
                    query.status = QueryStatus.PENDING.value
                    await db.commit()
                    logger.warning(
                        f"Query {query_id}: {query.target_llm} requires login "
                        f"but no account available, returning to PENDING"
                    )
                    return {
                        "query_id": query_id,
                        "status": "pending",
                        "reason": "no_account_available",
                    }

            logger.info(f"Query {query_id}: Using guest mode for {query.target_llm}")

            try:
                proxy_url = os.getenv("CLASH_PROXY_URL") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
                logger.info(f"Query {query_id}: Using proxy URL: {proxy_url}")
                guest_executor = GuestQueryExecutor(
                    proxy_url=proxy_url,
                    account_cookies=account_cookies,
                )
                response: LLMResponse | None = await guest_executor.execute(query)

                # Require a meaningful response (guards against login redirects returning 1 char)
                MIN_RESPONSE_LEN = 20
                if response and len(response.raw_text) >= MIN_RESPONSE_LEN:
                    # 删除旧 response（重试场景），避免唯一约束冲突
                    await db.execute(
                        sa_delete(LLMResponse).where(LLMResponse.query_id == query_id)
                    )
                    db.add(response)
                    query.status = QueryStatus.DONE.value
                    if account_id and pool:
                        await pool.report_success(account_id)
                    await db.commit()
                    logger.info(f"Query {query_id} DONE, response len={len(response.raw_text)}")
                    return {"query_id": query_id, "status": "done", "mode": "guest"}
                else:
                    resp_len = len(response.raw_text) if response else 0
                    query.status = QueryStatus.FAILED.value
                    if account_id and pool:
                        await pool.report_failure(account_id, reason="response_too_short")
                    await db.commit()
                    logger.warning(f"Query {query_id} failed (response too short: {resp_len} chars, likely login redirect)")
                    return {"query_id": query_id, "status": "failed", "reason": f"response_too_short:{resp_len}"}

            except Exception as e:
                logger.exception(f"Query {query_id} exception: {e}")
                query.status = QueryStatus.FAILED.value
                if account_id and pool:
                    await pool.report_failure(account_id, reason="exception")
                await db.commit()
                return {"query_id": query_id, "status": "failed", "error": str(e)}

    try:
        result = loop.run_until_complete(_run())
        return result
    except Exception as exc:
        logger.exception(f"execute_query {query_id} raised: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        try:
            loop.run_until_complete(task_engine.dispose())
        except:
            pass
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
        try:
            loop.run_until_complete(task_engine.dispose())
        except:
            pass
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
        try:
            loop.run_until_complete(task_engine.dispose())
        except:
            pass
        loop.close()
