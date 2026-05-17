#!/usr/bin/env python3
"""
M1 PoC runner: connect to a remote Chrome (manually logged in on a cloud VM)
over CDP, run a single LLM query, and capture artifacts.

This is an experiment under experiments/vm_per_account/ that validates the
"VM-per-account persistent browser session" architecture for Issue #963 (Doubao
scraping failures). The PoC deliberately AVOIDS cookie injection: it attaches
to an already-running Chrome that the operator manually logged in via VNC.

Usage:
    python poc_runner.py \\
        --cdp-endpoint http://vm-doubao-01.tail-xxx.ts.net:9222 \\
        --engine doubao \\
        --prompt-text "推荐一个性价比高的国产手机品牌" \\
        --prompt-id m1_smoke

Exit code: 0 if all reps succeeded, 1 otherwise.

Forbidden by design (see experiments/vm_per_account/README.md):
    - No imports from geo_tracker/ (this experiment is fully standalone)
    - No context.add_cookies() (the persistent profile owns the cookies)
    - No reading of DOUBAO_COOKIES_JSON / DEEPSEEK_COOKIES_JSON
    - No browser.new_context() (must reuse existing persistent context)
    - No parallel reps (single-threaded sequential)
    - No database writes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import (
    BrowserContext,
    Page,
    async_playwright,
)


# Engine config — selectors copied verbatim from
# geo_tracker/agent/guest_executor.py (lines ~474-501) on purpose so this
# experiment has no runtime dependency on the main package.
ENGINE_CONFIG: dict[str, dict[str, Any]] = {
    "doubao": {
        "url": "https://www.doubao.com/chat",
        "input_selector": (
            "#input-engine-container textarea.semi-input-textarea:not([aria-hidden='true']), "
            "textarea.semi-input-textarea:not([aria-hidden='true']), "
            "textarea:not([aria-hidden='true']), "
            "[contenteditable='true']"
        ),
        "submit_button": (
            "#flow-end-msg-send:not([aria-disabled='true']):not([data-disabled='true']), "
            "button[id='flow-end-msg-send']"
        ),
        "response_selector": (
            ".flow-markdown-body, "
            "[data-testid='receive_message'] .flow-markdown-body"
        ),
        "login_redirect_domains": [
            "passport.volcengine.com",
            "sso.volcengine.com",
            "passport.douyin.com",
        ],
    },
    "deepseek": {
        "url": "https://chat.deepseek.com",
        "input_selector": "textarea, [contenteditable=true], input[type=text]",
        # TODO(operator): verify DeepSeek's send button selector against the
        # live UI; the Chinese-text selector below is a best-guess fallback.
        "submit_button": "div[role='button']:has-text('发送')",
        "response_selector": ".ds-markdown, [class*='message-content'] .markdown",
        "login_redirect_domains": [
            "login.deepseek.com",
            "deepseek.com/sign_in",
        ],
    },
}


# --- failure-signal helpers --------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _url_hits_login_redirect(url: str, login_domains: list[str]) -> bool:
    """Return True if the URL contains any known login-redirect domain
    (or, for DeepSeek, a known sign-in path fragment)."""
    if not url:
        return False
    lower = url.lower()
    for d in login_domains:
        if d.lower() in lower:
            return True
    return False


async def _dom_has_captcha(page: Page) -> bool:
    """Return True if the DOM appears to contain a captcha / verify widget."""
    try:
        return await page.evaluate(
            """() => {
                const sel = [
                    "[class*='captcha']",
                    "[class*='verify']",
                    "iframe[src*='captcha']",
                ];
                for (const s of sel) {
                    const el = document.querySelector(s);
                    if (el) {
                        // visible-ish heuristic: has layout or is an iframe
                        const r = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
                        if (!r || (r.width > 0 && r.height > 0)) {
                            return true;
                        }
                    }
                }
                return false;
            }"""
        )
    except Exception:
        # If the page is gone we cannot tell — caller handles closed-page case.
        return False


# --- main run loop ----------------------------------------------------------


async def _wait_for_response_stable(
    page: Page,
    response_selector: str,
    timeout_secs: int,
    *,
    stable_window_secs: float = 3.0,
    poll_interval_secs: float = 0.5,
) -> str:
    """Poll the response container until its textContent length stops growing
    for ``stable_window_secs`` seconds, or ``timeout_secs`` elapses.

    Returns the final textContent (may be empty string on timeout)."""
    deadline = time.monotonic() + timeout_secs
    last_len = -1
    last_change = time.monotonic()
    last_text = ""
    while time.monotonic() < deadline:
        try:
            text = await page.evaluate(
                """(sel) => {
                    const nodes = document.querySelectorAll(sel);
                    if (!nodes || nodes.length === 0) return "";
                    // last receive_message is the latest reply
                    return nodes[nodes.length - 1].textContent || "";
                }""",
                response_selector,
            )
        except Exception:
            text = ""
        text = text or ""
        if len(text) != last_len:
            last_len = len(text)
            last_change = time.monotonic()
            last_text = text
        elif text and (time.monotonic() - last_change) >= stable_window_secs:
            return text
        await asyncio.sleep(poll_interval_secs)
    return last_text


async def _run_one_rep(
    context: BrowserContext,
    engine: str,
    prompt_text: str,
    timeout_secs: int,
    artifact_dir: Path,
    cdp_endpoint: str,
    prompt_id: str,
) -> dict[str, Any]:
    """Execute one query against the already-attached browser. Captures
    artifacts into ``artifact_dir`` and returns a result dict."""
    cfg = ENGINE_CONFIG[engine]
    started_at = _utc_now_iso()
    t0 = time.monotonic()
    failure_signals: list[str] = []
    raw_text = ""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    trace_path = artifact_dir / "trace.zip"
    screenshot_path = artifact_dir / "screenshot.png"
    raw_text_path = artifact_dir / "rawText.txt"
    result_path = artifact_dir / "result.json"

    # Start tracing on the persistent context so we get a HAR + screenshots
    # bundle without creating a new context.
    tracing_started = False
    try:
        await context.tracing.start(
            name=f"{engine}-{prompt_id}",
            screenshots=True,
            snapshots=True,
            sources=False,
        )
        tracing_started = True
    except Exception as e:
        # Tracing may already be running on the persistent context across reps;
        # not fatal for the M1 binary check.
        failure_signals.append(f"tracing_start_warning: {e!r}")

    page: Page | None = None
    try:
        page = await context.new_page()
        await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=timeout_secs * 1000)

        # Step 4: wait for input to be visible
        try:
            await page.wait_for_selector(
                cfg["input_selector"],
                state="visible",
                timeout=min(30_000, timeout_secs * 1000),
            )
        except Exception as e:
            failure_signals.append(f"input_selector_not_visible: {e!r}")

        # Failure detection block #1 — login redirect / blank title / captcha
        current_url = page.url
        if _url_hits_login_redirect(current_url, cfg["login_redirect_domains"]):
            failure_signals.append(f"login_redirect_url: {current_url}")

        try:
            title = await page.title()
        except Exception:
            title = ""
        if not title:
            failure_signals.append("blank_page_title")

        if await _dom_has_captcha(page):
            failure_signals.append("captcha_widget_detected")

        # Even if early signals fired, attempt the query so the artifact
        # captures what the page looked like during the run.
        # Step 5: type humanly
        try:
            await page.type(
                cfg["input_selector"],
                prompt_text,
                delay=random.randint(20, 80),
            )
        except Exception as e:
            failure_signals.append(f"type_failed: {e!r}")

        # Step 6: 2-5s pause then click. Try several click strategies because
        # Doubao SPA has a `semi-modal-wrap` element that intercepts pointer
        # events even when it's not visually rendered (Semi Design transition
        # artifact). Strategies in order:
        #   1. ESC to dismiss any visible/invisible modal
        #   2. Normal click (passes Playwright actionability checks)
        #   3. force=True click (bypasses intercept check)
        #   4. keyboard Enter (Doubao accepts this since textarea has focus)
        await asyncio.sleep(random.uniform(2.0, 5.0))
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception:
            pass
        submitted = False
        try:
            await page.click(cfg["submit_button"], timeout=8_000)
            submitted = True
        except Exception as e:
            failure_signals.append(f"submit_click_failed: {e!r}")
        if not submitted:
            try:
                await page.click(cfg["submit_button"], force=True, timeout=4_000)
                submitted = True
            except Exception as e:
                failure_signals.append(f"submit_force_click_failed: {e!r}")
        if not submitted:
            try:
                await page.keyboard.press("Enter")
                submitted = True
            except Exception as e2:
                failure_signals.append(f"submit_enter_failed: {e2!r}")

        # Step 7: poll response until stable
        remaining = max(10, timeout_secs - int(time.monotonic() - t0))
        raw_text = await _wait_for_response_stable(
            page,
            cfg["response_selector"],
            timeout_secs=remaining,
        )

        # Step 7b: if the primary response_selector returned empty, dump
        # the page HTML + a heuristic scan to artifact so the operator
        # can identify the correct selector without re-tunneling VNC.
        if not raw_text or len(raw_text) < 50:
            try:
                html_path = artifact_dir / "page.html"
                content = await page.content()
                html_path.write_text(content, encoding="utf-8")
            except Exception as e:
                failure_signals.append(f"page_content_dump_failed: {e!r}")
            try:
                # Heuristic: find any DIV with >= 100 chars textContent that's
                # not a global container; print the first 5 candidates with
                # their class lists so we know which selector to use next.
                candidates = await page.evaluate(
                    """() => {
                        const out = [];
                        const all = document.querySelectorAll("div, article, section");
                        for (const el of all) {
                            const t = (el.textContent || "").trim();
                            if (t.length >= 100 && t.length <= 5000) {
                                out.push({
                                    cls: el.className || "",
                                    id: el.id || "",
                                    testid: el.getAttribute("data-testid") || "",
                                    role: el.getAttribute("role") || "",
                                    chars: t.length,
                                    snippet: t.slice(0, 80),
                                });
                                if (out.length >= 10) break;
                            }
                        }
                        return out;
                    }"""
                )
                cand_path = artifact_dir / "response_candidates.json"
                cand_path.write_text(
                    json.dumps(candidates, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                failure_signals.append(f"candidate_scan_failed: {e!r}")
            # Also try a permissive fallback selector that's MUCH wider.
            try:
                fallback_text = await page.evaluate(
                    """() => {
                        const sels = [
                            "[data-testid='receive_message']",
                            "div[class*='markdown']",
                            "div[class*='message-content']",
                            "div[class*='assistant']",
                            "div[class*='reply']",
                        ];
                        for (const s of sels) {
                            const nodes = document.querySelectorAll(s);
                            if (nodes.length > 0) {
                                const last = nodes[nodes.length - 1];
                                const t = (last.textContent || "").trim();
                                if (t.length >= 50) return { sel: s, text: t };
                            }
                        }
                        return null;
                    }"""
                )
                if fallback_text and fallback_text.get("text"):
                    raw_text = fallback_text["text"]
                    failure_signals.append(
                        f"recovered_via_fallback_selector: {fallback_text.get('sel')}"
                    )
            except Exception as e:
                failure_signals.append(f"fallback_selector_failed: {e!r}")

        # Failure detection block #2 — check URL again post-submit + captcha
        try:
            post_url = page.url
            if _url_hits_login_redirect(post_url, cfg["login_redirect_domains"]):
                failure_signals.append(f"login_redirect_url_post_submit: {post_url}")
            if await _dom_has_captcha(page):
                failure_signals.append("captcha_widget_detected_post_submit")
        except Exception as e:
            failure_signals.append(f"post_submit_inspect_failed: {e!r}")

        # Step 9: screenshot
        try:
            await page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception as e:
            failure_signals.append(f"screenshot_failed: {e!r}")

    except Exception as e:
        # Top-level Playwright failure (e.g. "Target page, context or browser
        # has been closed") — record it explicitly.
        failure_signals.append(f"page_lifecycle_error: {e!r}")
    finally:
        if tracing_started:
            try:
                await context.tracing.stop(path=str(trace_path))
            except Exception as e:
                failure_signals.append(f"tracing_stop_warning: {e!r}")
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass

    # Step 10 (final check): rawText length gate
    raw_len = len(raw_text or "")
    if raw_len < 30:
        failure_signals.append(f"raw_text_too_short: {raw_len} chars")

    success = not failure_signals
    completed_at = _utc_now_iso()
    latency_ms = int((time.monotonic() - t0) * 1000)

    # Write rawText and result.json
    try:
        raw_text_path.write_text(raw_text or "", encoding="utf-8")
    except Exception as e:
        failure_signals.append(f"rawtext_write_failed: {e!r}")
        success = False

    result: dict[str, Any] = {
        "success": success,
        "failure_signals": failure_signals,
        "latency_ms": latency_ms,
        "rawText_len": raw_len,
        "started_at": started_at,
        "completed_at": completed_at,
        "engine": engine,
        "cdp_endpoint": cdp_endpoint,
        "prompt_id": prompt_id,
    }
    try:
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        # Last-ditch fallback to stderr
        print(f"WARN: failed to write result.json: {e!r}", file=sys.stderr)

    return result


async def _run(args: argparse.Namespace) -> int:
    if args.engine not in ENGINE_CONFIG:
        print(f"ERROR: unknown engine {args.engine!r}", file=sys.stderr)
        return 2

    prompt_id = args.prompt_id or f"adhoc-{uuid.uuid4().hex[:8]}"
    output_root = Path(args.output_dir).resolve()
    artifact_base = output_root / args.engine / prompt_id

    succeeded = 0
    rep_results: list[dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(args.cdp_endpoint)
        # Reuse the existing persistent context — DO NOT create a new context
        # and DO NOT call add_cookies(). The point of this experiment is that
        # the cookies are owned by the manually-logged-in profile on the VM.
        if not browser.contexts:
            print(
                "ERROR: remote Chrome has no default context; "
                "is it really running with --remote-debugging-port?",
                file=sys.stderr,
            )
            return 2
        context = browser.contexts[0]

        for rep in range(1, args.reps + 1):
            artifact_dir = artifact_base / str(rep)
            print(
                f"[rep {rep}/{args.reps}] engine={args.engine} "
                f"prompt_id={prompt_id} artifact_dir={artifact_dir}",
                file=sys.stderr,
            )
            result = await _run_one_rep(
                context=context,
                engine=args.engine,
                prompt_text=args.prompt_text,
                timeout_secs=args.timeout_secs,
                artifact_dir=artifact_dir,
                cdp_endpoint=args.cdp_endpoint,
                prompt_id=prompt_id,
            )
            rep_results.append(result)
            if result["success"]:
                succeeded += 1
                print(
                    f"[rep {rep}] OK rawText_len={result['rawText_len']} "
                    f"latency_ms={result['latency_ms']}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[rep {rep}] FAIL signals={result['failure_signals']}",
                    file=sys.stderr,
                )

        # connect_over_cdp returns a Browser we explicitly close (does NOT
        # terminate the remote Chrome — just detaches our CDP session).
        try:
            await browser.close()
        except Exception:
            pass

    print(
        f"M1 result: {succeeded}/{args.reps} succeeded, artifact dir: {artifact_base}"
    )
    return 0 if succeeded == args.reps else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "M1 PoC: drive a manually-logged-in remote Chrome over CDP and "
            "extract one LLM response. See experiments/vm_per_account/README.md."
        ),
    )
    parser.add_argument(
        "--cdp-endpoint",
        required=True,
        help="Remote Chrome CDP URL, e.g. http://vm-doubao-01.tail-xxx.ts.net:9222",
    )
    parser.add_argument(
        "--engine",
        required=True,
        choices=sorted(ENGINE_CONFIG.keys()),
        help="Which engine UI to drive.",
    )
    parser.add_argument(
        "--prompt-text",
        required=True,
        help="Prompt text to send. M1 simplification: passed directly, no DB lookup.",
    )
    parser.add_argument(
        "--prompt-id",
        default=None,
        help="Optional id used for the artifact directory name.",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=1,
        help="How many sequential reps to run with the same prompt (default 1).",
    )
    parser.add_argument(
        "--output-dir",
        default="experiments/vm_per_account/runs",
        help="Artifact root directory (default: experiments/vm_per_account/runs).",
    )
    parser.add_argument(
        "--timeout-secs",
        type=int,
        default=180,
        help="Overall budget per rep in seconds (default 180).",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
