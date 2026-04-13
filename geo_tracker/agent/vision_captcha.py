"""
视觉验证码求解器 —— 使用 Vision LLM 识别数美 (Shumei) 图形点选验证码

DeepSeek 登录使用数美验证码 (spatial_select 模式):
  - 容器: #sm-captcha > .shumei_captcha_wrapper
  - 图片: .shumei_captcha_loaded_img_bg (有直接 URL)
  - 题目: .shumei_captcha_slide_tips ("Click on the smallest blue sphere in the picture")
  - 刷新: .shumei_captcha_img_refresh_btn
  - 整体弹窗: .ds-modal-content

求解流程：
  1. 检测数美验证码弹窗
  2. 获取图片 URL 或截图
  3. 提取题目文字
  4. 调用 Doubao-Seed-2.0-pro 视觉能力分析图片
  5. 返回目标物体的坐标
  6. 在图片区域内模拟点击
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ── 火山引擎 Ark API 配置 ──────────────────────────────────────────────────
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.getenv("ARK_MODEL", "doubao-seed-2-0-pro-260215")

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/data/screenshots"))


def _get_vision_client():
    """获取 OpenAI 兼容客户端（火山引擎 Ark API）"""
    if not ARK_API_KEY:
        logger.warning("[vision_captcha] ARK_API_KEY 未配置")
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)
    except ImportError:
        logger.error("[vision_captcha] openai SDK 未安装，请 pip install openai")
        return None


# ── 检测 ──────────────────────────────────────────────────────────────────

async def detect_vision_captcha(page: Page) -> Optional[dict]:
    """
    检测页面上是否存在数美 (Shumei) 图形点选验证码。

    Returns:
        dict: {found, prompt, imgRect, imgUrl, containerClass}
        None if no captcha detected
    """
    result = await page.evaluate("""
        () => {
            // ── 数美验证码精确检测 ──
            const shumeiWrapper = document.querySelector(
                '.shumei_captcha_wrapper, #sm-captcha'
            );
            if (shumeiWrapper && shumeiWrapper.offsetParent !== null) {
                // 图片
                const img = shumeiWrapper.querySelector('.shumei_captcha_loaded_img_bg');
                if (!img) return { found: false, reason: 'shumei_no_img' };

                const rect = img.getBoundingClientRect();
                if (rect.width < 30 || rect.height < 30)
                    return { found: false, reason: 'shumei_img_too_small' };

                // 题目
                const tipsEl = shumeiWrapper.querySelector('.shumei_captcha_slide_tips');
                const prompt = tipsEl
                    ? (tipsEl.textContent || '').trim()
                    : '';

                return {
                    found: true,
                    type: 'shumei',
                    prompt: prompt,
                    imgUrl: img.src || '',
                    imgRect: {
                        x: rect.x, y: rect.y,
                        width: rect.width, height: rect.height,
                    },
                    containerClass: shumeiWrapper.className.slice(0, 120),
                };
            }

            // ── 通用 fallback（其他验证码平台）──
            const genericSelectors = [
                '[class*="captcha"]',
                '[class*="verify"]',
            ];
            for (const sel of genericSelectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    if (!el.offsetParent) continue;
                    const img = el.querySelector('img');
                    if (!img) continue;
                    const text = el.innerText || '';
                    if (text.length < 5) continue;
                    const rect = img.getBoundingClientRect();
                    if (rect.width < 50 || rect.height < 50) continue;

                    // 提取题目
                    let prompt = '';
                    const tipEls = el.querySelectorAll(
                        '[class*="tip"], [class*="title"], [class*="prompt"], span, p'
                    );
                    for (const t of tipEls) {
                        const txt = (t.textContent || '').trim();
                        if (txt.length > 10 && txt.length < 200) {
                            prompt = txt;
                            break;
                        }
                    }
                    if (!prompt) {
                        const lines = text.split('\\n').filter(l => l.trim().length > 10);
                        prompt = lines[lines.length - 1] || text.slice(0, 200);
                    }

                    return {
                        found: true,
                        type: 'generic',
                        prompt: prompt.trim(),
                        imgUrl: img.src || '',
                        imgRect: {
                            x: rect.x, y: rect.y,
                            width: rect.width, height: rect.height,
                        },
                        containerClass: el.className.slice(0, 120),
                    };
                }
            }

            return { found: false };
        }
    """)

    if not result or not result.get("found"):
        return None

    logger.info(
        f"[vision_captcha] 检测到验证码: type={result.get('type')}, "
        f"prompt='{result.get('prompt')}', imgUrl={result.get('imgUrl', '')[:80]}"
    )
    return result


# ── 截图 / 获取图片 ───────────────────────────────────────────────────────

async def _get_captcha_image_b64(page: Page, captcha_info: dict) -> Optional[str]:
    """
    获取验证码图片的 base64 编码。
    优先用图片 URL 直接下载（更清晰），降级为截图。
    """
    img_url = captcha_info.get("imgUrl", "")
    img_rect = captcha_info["imgRect"]

    # 方式 1: 直接从页面获取图片 base64（通过 canvas 转换，避免跨域问题）
    if img_url:
        try:
            b64 = await page.evaluate("""
                (imgUrl) => {
                    return new Promise((resolve) => {
                        const img = new Image();
                        img.crossOrigin = 'anonymous';
                        img.onload = () => {
                            const canvas = document.createElement('canvas');
                            canvas.width = img.naturalWidth;
                            canvas.height = img.naturalHeight;
                            canvas.getContext('2d').drawImage(img, 0, 0);
                            resolve(canvas.toDataURL('image/png').split(',')[1]);
                        };
                        img.onerror = () => resolve(null);
                        img.src = imgUrl;
                        setTimeout(() => resolve(null), 5000);
                    });
                }
            """, img_url)
            if b64:
                logger.info(f"[vision_captcha] 通过 URL 获取图片成功 ({len(b64)} bytes)")
                return b64
        except Exception as e:
            logger.debug(f"[vision_captcha] URL 获取图片失败: {e}")

    # 方式 2: 截图图片区域
    try:
        screenshot = await page.screenshot(
            clip={
                "x": img_rect["x"],
                "y": img_rect["y"],
                "width": img_rect["width"],
                "height": img_rect["height"],
            },
            type="png",
        )
        b64 = base64.b64encode(screenshot).decode("utf-8")
        logger.info(f"[vision_captcha] 通过截图获取图片成功 ({len(b64)} bytes)")
        return b64
    except Exception as e:
        logger.error(f"[vision_captcha] 截图失败: {e}")
        return None


# ── 视觉模型调用 ──────────────────────────────────────────────────────────

def _call_vision_model(image_base64: str, prompt_text: str) -> Optional[dict]:
    """
    调用 Doubao-Seed-2.0-pro 视觉模型，分析验证码图片并返回点击坐标。

    Returns:
        {"x": float, "y": float} 相对于图片的归一化坐标 (0-1)
    """
    client = _get_vision_client()
    if not client:
        return None

    instructions = (
        "你是一个验证码识别助手。用户会给你一张包含多个 3D 几何体的图片，以及一个指令要求你点击特定的物体。"
        "请分析图片中所有物体的颜色、形状和大小，然后找到符合指令描述的目标物体。"
        "你必须以 JSON 格式返回目标物体中心点的坐标，格式为：{\"x\": 0.XX, \"y\": 0.XX}。"
        "其中 x 和 y 是相对于图片宽高的归一化坐标（0-1 范围）。"
        "x=0 表示图片最左边，x=1 表示最右边；y=0 表示图片最上边，y=1 表示最下边。"
        "只返回 JSON，不要其他文字。"
    )

    user_prompt = f"指令：{prompt_text}\n\n请找到目标物体并返回其中心点坐标。"

    try:
        response = client.responses.create(
            model=ARK_MODEL,
            instructions=instructions,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{image_base64}",
                        },
                        {
                            "type": "input_text",
                            "text": user_prompt,
                        },
                    ],
                },
            ],
        )

        content = response.output_text.strip()
        logger.info(f"[vision_captcha] 模型返回: {content}")

        # 提取 JSON
        json_match = re.search(r'\{[^}]+\}', content)
        if json_match:
            import json
            coords = json.loads(json_match.group())
            x = float(coords.get("x", 0))
            y = float(coords.get("y", 0))
            if 0 <= x <= 1 and 0 <= y <= 1:
                return {"x": x, "y": y}
            else:
                logger.warning(f"[vision_captcha] 坐标超出范围: x={x}, y={y}")
                return None

        logger.warning(f"[vision_captcha] 无法解析模型返回的坐标: {content}")
        return None

    except Exception as e:
        logger.error(f"[vision_captcha] 调用视觉模型失败: {e}")
        return None


# ── 主流程 ────────────────────────────────────────────────────────────────

async def solve_vision_captcha(page: Page, max_retries: int = 3) -> bool:
    """
    检测并求解数美图形点选验证码。

    Returns:
        True if solved or no captcha, False if all retries failed
    """
    if not ARK_API_KEY:
        logger.warning("[vision_captcha] ARK_API_KEY 未配置，跳过视觉验证码求解")
        return False

    for attempt in range(1, max_retries + 1):
        logger.info(f"[vision_captcha] 求解尝试 {attempt}/{max_retries}")

        # 1. 检测验证码
        captcha_info = await detect_vision_captcha(page)
        if not captcha_info:
            logger.info("[vision_captcha] 未检测到验证码（可能已通过）")
            return True

        img_rect = captcha_info["imgRect"]
        prompt_text = captcha_info["prompt"]

        logger.info(
            f"[vision_captcha] 人机验证详情: "
            f"type={captcha_info.get('type')}, "
            f"题目='{prompt_text}', "
            f"图片尺寸={img_rect['width']:.0f}x{img_rect['height']:.0f}, "
            f"图片URL={captcha_info.get('imgUrl', '')[:60]}"
        )

        # 2. 获取验证码图片
        image_b64 = await _get_captcha_image_b64(page, captcha_info)
        if not image_b64:
            continue

        # 保存截图用于调试
        try:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            captcha_path = SCREENSHOT_DIR / f"captcha_vision_{int(time.time())}_{attempt}.png"
            captcha_path.write_bytes(base64.b64decode(image_b64))
            logger.info(f"[vision_captcha] 验证码截图已保存: {captcha_path}")
        except Exception:
            pass

        # 3. 调用视觉模型
        coords = await asyncio.get_event_loop().run_in_executor(
            None, _call_vision_model, image_b64, prompt_text,
        )
        if not coords:
            logger.warning(f"[vision_captcha] 第 {attempt} 次视觉模型未返回有效坐标")
            await _click_refresh(page)
            await page.wait_for_timeout(2000)
            continue

        # 4. 计算页面绝对坐标并点击
        click_x = img_rect["x"] + coords["x"] * img_rect["width"]
        click_y = img_rect["y"] + coords["y"] * img_rect["height"]
        logger.info(
            f"[vision_captcha] 点击坐标: ({click_x:.0f}, {click_y:.0f}) "
            f"[归一化: ({coords['x']:.2f}, {coords['y']:.2f})]"
        )

        # 模拟自然点击
        await page.mouse.move(click_x, click_y, steps=10)
        await page.wait_for_timeout(200)
        await page.mouse.click(click_x, click_y)

        # 5. 等待验证结果
        await page.wait_for_timeout(3000)

        # 检查验证码是否消失（数美验证码通过后整个 wrapper 会隐藏）
        still_visible = await detect_vision_captcha(page)
        if not still_visible:
            logger.info(f"[vision_captcha] 验证码求解成功（第 {attempt} 次尝试）")
            return True

        logger.info(f"[vision_captcha] 第 {attempt} 次点击未通过，刷新换题...")
        await _click_refresh(page)
        await page.wait_for_timeout(2000)

    logger.warning(f"[vision_captcha] {max_retries} 次尝试均失败")
    return False


async def _click_refresh(page: Page) -> None:
    """点击数美验证码刷新按钮（换一题）"""
    refresh_selectors = [
        ".shumei_captcha_img_refresh_btn",          # 数美刷新按钮
        "#sm-captcha [class*='refresh']",            # 数美 ID 下的刷新
        "[class*='captcha'] [class*='refresh']",     # 通用 fallback
    ]
    for sel in refresh_selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                logger.info(f"[vision_captcha] 点击刷新按钮: {sel}")
                return
        except Exception:
            continue
    logger.debug("[vision_captcha] 未找到刷新按钮")
