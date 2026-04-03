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
from geo_tracker.db.models import Query, QueryStatus, LLMResponse, LLMAccount, AccountStatus
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
        "cookie-keep-alive": {
            "task":     "geo_tracker.tasks.celery_tasks.cookie_keep_alive",
            "schedule": crontab(hour="*/2", minute=30),  # 每2小时保活（DeepSeek session 较短）
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
                    # 记录 query 使用的账号
                    query.account_id = account_id
                    await db.commit()
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
                    # deepseek 的 CAPTCHA 暂无法自动求解，跳过自动注册
                    if query.target_llm != "deepseek":
                        auto_login.apply_async(
                            kwargs={"platform": query.target_llm, "new_account": True},
                            queue="account_login",
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
                    # 区分 cookies 过期和其他失败：response 为 None 通常是登录重定向
                    failure_reason = "cookies_expired" if response is None else "response_too_short"
                    if account_id and pool:
                        await pool.report_failure(account_id, reason=failure_reason)
                    await db.commit()
                    # 触发自动重新登录（deepseek 暂跳过，CAPTCHA 无法自动求解）
                    if failure_reason == "cookies_expired" and account_id and query.target_llm != "deepseek":
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
                    account.cookies_json = json_mod.dumps(login_result["cookies"])
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
                    new_account_obj = await pool.create_account(
                        llm_name=platform,
                        phone=login_result["phone"],
                        cookies_json=json_mod.dumps(login_result["cookies"]),
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

        # 注入 cookies
        cookies = json_mod.loads(executor.account_cookies)
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
