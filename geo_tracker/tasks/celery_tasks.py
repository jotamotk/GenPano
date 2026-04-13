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

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import delete as sa_delete, select

from geo_tracker.agent.guest_executor import GuestQueryExecutor, GUEST_LLM_CONFIG, DOMESTIC_LLMS
from geo_tracker.db.models import (
    Query, QueryStatus, LLMResponse, LLMAccount, AccountStatus,
    AnalysisStatus, Brand, Competitor, Prompt,
)
from geo_tracker.pool.account_pool import AccountPool

# 数据库 & Redis 连接（实际项目从 config 读取）
from geo_tracker.config import create_task_engine, get_task_async_session, REDIS_URL

logger = logging.getLogger(__name__)

app = Celery("geo_tracker", broker=REDIS_URL, backend=REDIS_URL)

_beat_schedule = {
    "reset-daily-counts": {
        "task":     "geo_tracker.tasks.celery_tasks.reset_daily_counts",
        "schedule": crontab(hour=0, minute=0),
    },
    "cookie-keep-alive": {
        "task":     "geo_tracker.tasks.celery_tasks.cookie_keep_alive",
        "schedule": crontab(hour="*/2", minute=30),
    },
}

# Auto-schedule daily analysis in production (opt-in via env var)
if os.getenv("ANALYZER_AUTO_SCHEDULE", "false").lower() == "true":
    _beat_schedule["daily-analysis"] = {
        "task":     "geo_tracker.tasks.celery_tasks.run_daily_analysis",
        "schedule": crontab(hour=2, minute=0),
    }

app.conf.update(
    task_serializer   = "json",
    result_serializer = "json",
    timezone          = "UTC",
    task_max_retries  = 3,
    task_default_retry_delay = 60,
    worker_concurrency = 2,
    beat_schedule = _beat_schedule,
    task_routes = {
        "geo_tracker.tasks.celery_tasks.analyze_response": {"queue": "analysis"},
        "geo_tracker.tasks.celery_tasks.run_daily_analysis": {"queue": "analysis"},
        "geo_tracker.tasks.celery_tasks.aggregate_daily_scores": {"queue": "analysis"},
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

            # 从 AccountPool 获取账号 cookies
            account = None
            account_id = None
            account_cookies = None
            pool = None
            requires_login = llm_config.get("requires_login", True)

            pool = AccountPool(db)
            account = await pool.acquire(query.target_llm)
            if account and account.cookies_json:
                account_cookies = account.cookies_json
                account_id = account.id
                query.account_id = account_id
                await db.commit()
                logger.info(
                    f"Query {query_id}: acquired account id={account_id} "
                    f"for {query.target_llm}"
                )
            elif requires_login:
                # 必须登录但无可用账号 → 标记 FAILED（不再设回 pending 避免无限循环）
                query.status = QueryStatus.FAILED.value
                await db.commit()
                logger.warning(
                    f"Query {query_id}: {query.target_llm} requires login "
                    f"but no account available, marking FAILED"
                )
                auto_login.apply_async(
                    kwargs={"platform": query.target_llm, "new_account": True},
                    queue="account_login",
                )
                return {
                    "query_id": query_id,
                    "status": "failed",
                    "reason": "no_account_available",
                }
            else:
                # 不需要登录（guest 可用），无 cookie 也继续
                logger.info(
                    f"Query {query_id}: no account for {query.target_llm}, "
                    f"proceeding with guest mode"
                )

            logger.info(f"Query {query_id}: Using {'account' if account_cookies else 'guest'} mode for {query.target_llm}")

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
                    invalid_marker = _is_invalid_response(response.raw_text)
                    if invalid_marker:
                        # 响应内容是登录页/过期页，不是 AI 回答
                        query.status = QueryStatus.FAILED.value
                        failure_reason = "cookies_expired"
                        if account_id and pool:
                            await pool.report_failure(account_id, reason=failure_reason)
                        await db.commit()
                        logger.warning(
                            f"Query {query_id} failed: response contains '{invalid_marker}', "
                            f"cookie expired for account {account_id}"
                        )
                        return {"query_id": query_id, "status": "failed", "reason": failure_reason}

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
                    # 区分 cookies 过期和其他失败：response 为 None 通常是登录重定向
                    failure_reason = "cookies_expired" if response is None else "response_too_short"
                    if account_id and pool:
                        await pool.report_failure(account_id, reason=failure_reason)
                    await db.commit()
                    # 触发自动重新登录
                    if failure_reason == "cookies_expired" and account_id:
                        auto_login.apply_async(
                            kwargs={"account_id": account_id},
                            queue="account_login",
                        )
                    logger.warning(f"Query {query_id} failed ({failure_reason}: {resp_len} chars)")
                    return {"query_id": query_id, "status": "failed", "reason": f"{failure_reason}:{resp_len}"}

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

        async with get_task_async_session(task_engine) as db:
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
                    proxy_url = (
                        os.getenv("CLASH_PROXY_URL") or os.getenv("HTTPS_PROXY")
                        if llm_name not in DOMESTIC_LLMS else None
                    )
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
                        try:
                            old_data = json_mod.loads(account.cookies_json)
                            if isinstance(old_data, dict) and "localStorage" in old_data:
                                account.cookies_json = json_mod.dumps({
                                    "cookies": refreshed_cookies,
                                    "localStorage": old_data["localStorage"],
                                })
                            else:
                                account.cookies_json = json_mod.dumps(refreshed_cookies)
                        except Exception:
                            account.cookies_json = json_mod.dumps(refreshed_cookies)
                        account.cookies_updated_at = dt.utcnow()
                        await db.commit()
                        results["refreshed"] += 1
                        results["details"].append(
                            f"#{account.id} {llm_name}: refreshed {len(refreshed_cookies)} cookies"
                        )
                        logger.info(
                            f"cookie_keep_alive: #{account.id} {llm_name} refreshed "
                            f"({len(refreshed_cookies)} cookies)"
                        )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            f"#{account.id} {llm_name}: refresh failed (cookies may be expired)"
                        )
                        logger.warning(
                            f"cookie_keep_alive: #{account.id} {llm_name} refresh failed"
                        )
                        # 触发自动重新登录
                        auto_login.apply_async(
                            kwargs={"account_id": account.id},
                            queue="account_login",
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
        try:
            loop.run_until_complete(task_engine.dispose())
        except:
            pass
        loop.close()


@app.task(queue="account_login", bind=True, max_retries=1)
def auto_login(self, account_id: int = None, platform: str = None, new_account: bool = False) -> dict:
    """
    自动 SMS 登录/注册，独立于 query 执行。

    场景 1: account_id 有值 → 已有账号重新登录（用 DB 里的 phone_number）
    场景 2: new_account=True → 注册新账号（LubanSMS 获取新号码）
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        from geo_tracker.agent.sms_login import get_handler

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

                logger.info(
                    f"auto_login: re-login account #{account_id} "
                    f"({account.llm_name}, phone={account.phone_number})"
                )
                login_result = await handler.login_or_register(
                    existing_cookies=account.cookies_json,
                    phone=account.phone_number,
                )

                if login_result and login_result.get("cookies"):
                    from datetime import datetime as dt
                    # 打包 cookies + localStorage（如有）为新格式
                    cookies_data = login_result["cookies"]
                    local_storage = login_result.get("localStorage", {})
                    if local_storage:
                        account.cookies_json = json_mod.dumps({
                            "cookies": cookies_data,
                            "localStorage": local_storage,
                        })
                    else:
                        account.cookies_json = json_mod.dumps(cookies_data)
                    account.cookies_updated_at = dt.utcnow()
                    account.status = AccountStatus.ACTIVE.value
                    account.cooldown_until = None
                    account.consecutive_fails = 0
                    if login_result.get("phone"):
                        account.phone_number = login_result["phone"]
                    await db.commit()
                    logger.info(f"auto_login: account #{account_id} re-login SUCCESS")
                    return {"status": "success", "account_id": account_id}
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
                    # 打包 cookies + localStorage（如有）为新格式
                    cookies_data = login_result["cookies"]
                    local_storage = login_result.get("localStorage", {})
                    if local_storage:
                        cookies_json_str = json_mod.dumps({
                            "cookies": cookies_data,
                            "localStorage": local_storage,
                        })
                    else:
                        cookies_json_str = json_mod.dumps(cookies_data)
                    new_account_obj = await pool.create_account(
                        llm_name=platform,
                        phone=login_result["phone"],
                        cookies_json=cookies_json_str,
                    )
                    logger.info(
                        f"auto_login: new {platform} account #{new_account_obj.id} "
                        f"created (phone={login_result['phone']})"
                    )
                    return {
                        "status": "success",
                        "account_id": new_account_obj.id,
                        "phone": login_result["phone"],
                    }
                else:
                    reason = (login_result or {}).get("reason", "unknown")
                    logger.warning(f"auto_login: new {platform} registration FAILED: {reason}")
                    return {"status": "failed", "platform": platform, "reason": reason}

            else:
                return {"status": "error", "reason": "invalid arguments"}

    try:
        result = loop.run_until_complete(_run())
        return result
    except Exception as exc:
        logger.exception(f"auto_login exception: {exc}")
        raise self.retry(exc=exc, countdown=120)
    finally:
        try:
            loop.run_until_complete(task_engine.dispose())
        except:
            pass
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis Tasks
# ═══════════════════════════════════════════════════════════════════════════════

@app.task(bind=True, max_retries=2, queue="analysis")
def analyze_response(self, response_id: int) -> dict:
    """Run the 3-stage analysis pipeline on a single LLMResponse."""
    logger.info(f"analyze_response started for response_id={response_id}")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_engine = create_task_engine()

    async def _run():
        from geo_tracker.analyzer.cli import analyze_single_response

        async with get_task_async_session(task_engine) as db:
            resp = await db.get(LLMResponse, response_id)
            if not resp:
                return {"skipped": True, "reason": "response_not_found"}

            if resp.analysis_status == AnalysisStatus.DONE.value:
                return {"skipped": True, "reason": "already_analyzed"}

            query = await db.get(Query, resp.query_id)
            brand = await db.get(Brand, query.brand_id)

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
                db, resp, brand, competitors, intent,
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

    use_proxy = executor.proxy_url and llm_name not in DOMESTIC_LLMS
    needs_stealth = bool(executor.account_cookies)
    use_camoufox = has_camoufox and (use_proxy or needs_stealth)

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
        current_url = page.url
        login_domains = config.get("login_redirect_domains", [])
        if any(d in current_url for d in login_domains):
            logger.warning(
                f"cookie_keep_alive: {llm_name} redirected to login: {current_url}"
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
                logger.warning(
                    f"cookie_keep_alive: {llm_name} login page detected "
                    f"(matched: {matched})"
                )
                return None

        # 模拟人类浏览：随机滚动
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
        if browser:
            try:
                await browser.close()
            except:
                pass
        if _camoufox_ctx:
            try:
                await _camoufox_ctx.__aexit__(None, None, None)
            except:
                pass
        if _playwright:
            try:
                await _playwright.stop()
            except:
                pass
