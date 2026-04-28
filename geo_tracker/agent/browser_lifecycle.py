"""
浏览器生命周期安全清理工具 (Session 1.2 Operational Hardening)

背景: 生产事故 2026-04-27 — genpano-worker-1 容器累积到 458 个进程 / 2.2GB 内存,
根因是 `await browser.close()` 偶尔会 HANG (不抛异常,而是无限等待),
原 finally 块用 `try/except: pass` 只能捕抛出的异常,捕不了 hang。
后续 _camoufox_ctx.__aexit__ / _playwright.stop() 因此永远不执行,
Celery 主进程超时发 SIGTERM,asyncio loop 被强杀在 await 里,
Chromium 子进程被 init 收养成孤儿 → 进程数雪崩。

修复策略 (与决策 #25 Rule 1 "真相源锚定" 一致, 单一入口避免漂移):
  - 用 asyncio.wait_for 把 hang 转成 TimeoutError, 强制 finally 后续段执行
  - 每段独立 timeout, 整体清理预算可控
  - 失败只记 warning 不再传播, 由调用方的 try/finally 决定语义
  - 配合 docker-compose `--max-tasks-per-child=20`, OS 级孤儿进程在 worker
    周期性回收时被 reap, 彻底闭环

调用方契约: 使用本模块的 cleanup_browser_resources() 替代裸 try/except: pass。
未来加密码 / 加 page.close() / 加 context.close() 都从这一处扩展。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 单段清理预算 (秒). 调大会拖慢任务收尾, 调小可能导致正常关闭被误杀.
# 当前值经验依据: Playwright browser.close() 正常路径 < 2s, Camoufox < 3s,
# driver.stop() < 1s. 留 3-5x 余量。
BROWSER_CLOSE_TIMEOUT_S = 10.0
CAMOUFOX_EXIT_TIMEOUT_S = 10.0
PLAYWRIGHT_STOP_TIMEOUT_S = 5.0
PAGE_CLOSE_TIMEOUT_S = 5.0
CONTEXT_CLOSE_TIMEOUT_S = 5.0


async def _await_with_timeout(
    coro: Any,
    timeout: float,
    label: str,
) -> bool:
    """
    超时受控等待。返回 True 表示干净结束, False 表示 timeout/异常 (但已被吞掉)。
    在何种情况下都不会重新抛出, 调用方的 finally 链可以放心继续。
    """
    try:
        await asyncio.wait_for(coro, timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.warning(
            f"[browser_lifecycle] {label} timed out after {timeout}s; "
            f"underlying resource may leak until worker process recycle"
        )
        return False
    except asyncio.CancelledError:
        # 任务被外部取消 (Celery SIGTERM 之类) — 重新抛, 让 asyncio 能退出
        raise
    except Exception as e:
        logger.warning(
            f"[browser_lifecycle] {label} raised "
            f"{type(e).__name__}: {e}; continuing cleanup"
        )
        return False


async def safe_close_page(page: Optional[Any]) -> None:
    """
    安全关闭 Playwright Page。Page 卡死通常是因为 onbeforeunload 挂钩或
    pending dialog, run_until_complete 永远等不到关闭事件。
    """
    if page is None:
        return
    try:
        if getattr(page, "is_closed", lambda: False)():
            return
    except Exception:
        pass
    await _await_with_timeout(
        page.close(run_before_unload=False),
        PAGE_CLOSE_TIMEOUT_S,
        "page.close",
    )


async def safe_close_context(context: Optional[Any]) -> None:
    """安全关闭 BrowserContext。"""
    if context is None:
        return
    await _await_with_timeout(
        context.close(),
        CONTEXT_CLOSE_TIMEOUT_S,
        "context.close",
    )


async def safe_close_browser(browser: Optional[Any]) -> None:
    """
    安全关闭 Browser。这是最容易 hang 的路径 — Chromium 偶尔会因为
    pending IPC / GPU 进程死锁而无法响应 close 请求。
    """
    if browser is None:
        return
    try:
        if not getattr(browser, "is_connected", lambda: True)():
            return
    except Exception:
        pass
    await _await_with_timeout(
        browser.close(),
        BROWSER_CLOSE_TIMEOUT_S,
        "browser.close",
    )


async def safe_exit_camoufox(camoufox_ctx: Optional[Any]) -> None:
    """
    安全退出 AsyncCamoufox 上下文管理器。Camoufox 在底层包装了
    自己的 firefox 驱动, __aexit__ 偶尔会卡在驱动握手关闭。
    """
    if camoufox_ctx is None:
        return
    await _await_with_timeout(
        camoufox_ctx.__aexit__(None, None, None),
        CAMOUFOX_EXIT_TIMEOUT_S,
        "camoufox.__aexit__",
    )


async def safe_stop_playwright(playwright: Optional[Any]) -> None:
    """安全停止 Playwright 驱动 (async_playwright().start() 的对偶)。"""
    if playwright is None:
        return
    await _await_with_timeout(
        playwright.stop(),
        PLAYWRIGHT_STOP_TIMEOUT_S,
        "playwright.stop",
    )


async def cleanup_browser_resources(
    *,
    page: Optional[Any] = None,
    context: Optional[Any] = None,
    browser: Optional[Any] = None,
    camoufox_ctx: Optional[Any] = None,
    playwright: Optional[Any] = None,
) -> None:
    """
    标准浏览器资源清理编排, 按依赖顺序逐段超时受控关闭。

    顺序: page → context → browser → camoufox_ctx → playwright
    每段都是 best-effort, 任何一段 hang/异常都不影响后续段执行。
    最长总耗时 = sum(各段 timeout) ≈ 35 秒 (理论上限, 通常 < 2 秒)。

    用法:
        page = browser = ctx = pw = camoufox = None
        try:
            ...
        finally:
            await cleanup_browser_resources(
                page=page,
                context=context,
                browser=browser,
                camoufox_ctx=camoufox,
                playwright=pw,
            )
    """
    await safe_close_page(page)
    await safe_close_context(context)
    await safe_close_browser(browser)
    await safe_exit_camoufox(camoufox_ctx)
    await safe_stop_playwright(playwright)
