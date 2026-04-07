"""
视觉验证码求解器 —— 使用 Vision LLM 识别图形点选验证码

DeepSeek 登录时的验证码类型：3D 图形点选
  - 显示多个 3D 几何体（长方体、圆锥、球体等）
  - 题目要求点击特定颜色/大小/形状的目标
  - 例："Click on the smallest blue cuboid in the picture"

求解流程：
  1. 截图验证码区域
  2. 提取题目文字
  3. 调用 Doubao-Seed-2.0-pro (火山引擎 Ark API) 的视觉能力分析图片
  4. 返回目标物体的坐标
  5. 模拟点击
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ── 火山引擎 Ark API 配置 ──────────────────────────────────────────────────
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL = os.getenv("ARK_MODEL", "doubao-seed-2-0-pro-260215")

# 验证码区域选择器（DeepSeek 3D 图形验证码）
CAPTCHA_CONTAINER_SELECTORS = [
    "[class*='captcha']",
    "[class*='verify']",
    "[class*='CAPTCHA']",
    "div:has(> img):has(> [class*='click'])",
]

# 验证码题目选择器
CAPTCHA_PROMPT_SELECTORS = [
    "[class*='captcha'] [class*='tip']",
    "[class*='captcha'] [class*='title']",
    "[class*='captcha'] [class*='prompt']",
    "[class*='captcha'] [class*='text']",
    "[class*='verify'] [class*='tip']",
    "[class*='verify'] [class*='title']",
]

# 验证码图片选择器
CAPTCHA_IMAGE_SELECTORS = [
    "[class*='captcha'] img",
    "[class*='verify'] img",
    "[class*='captcha'] canvas",
]


def _get_vision_client():
    """获取 OpenAI 兼容客户端（火山引擎 Ark API）"""
    if not ARK_API_KEY:
        logger.warning("[vision_captcha] ARK_API_KEY 未配置")
        return None
    try:
        from openai import OpenAI
        return OpenAI(
            api_key=ARK_API_KEY,
            base_url=ARK_BASE_URL,
        )
    except ImportError:
        logger.error("[vision_captcha] openai SDK 未安装，请 pip install openai")
        return None


async def detect_vision_captcha(page: Page) -> Optional[dict]:
    """
    检测页面上是否存在图形点选验证码。

    Returns:
        dict with keys: container_el, image_el, prompt_text, bbox
        None if no captcha detected
    """
    # 检测验证码容器
    result = await page.evaluate("""
        () => {
            // 检测包含 3D 图形验证码的弹窗
            const selectors = [
                '[class*="captcha"]',
                '[class*="verify"]',
                '[class*="CAPTCHA"]',
            ];

            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    if (!el.offsetParent) continue;  // 不可见
                    // 必须包含图片
                    const img = el.querySelector('img');
                    if (!img) continue;
                    // 必须有文字提示（题目）
                    const text = el.innerText || '';
                    if (text.length < 5) continue;

                    const rect = img.getBoundingClientRect();
                    if (rect.width < 50 || rect.height < 50) continue;

                    // 尝试提取题目文字（通常在图片下方或上方）
                    let prompt = '';
                    const tipEls = el.querySelectorAll(
                        '[class*="tip"], [class*="title"], [class*="prompt"], '
                        + '[class*="text"], span, p'
                    );
                    for (const t of tipEls) {
                        const txt = (t.textContent || '').trim();
                        if (txt.length > 10 && txt.length < 200) {
                            prompt = txt;
                            break;
                        }
                    }
                    if (!prompt) {
                        // fallback: 用容器的全部文本
                        const lines = text.split('\\n').filter(l => l.trim().length > 10);
                        prompt = lines[lines.length - 1] || text.slice(0, 200);
                    }

                    return {
                        found: true,
                        prompt: prompt.trim(),
                        imgRect: {
                            x: rect.x, y: rect.y,
                            width: rect.width, height: rect.height
                        },
                        containerClass: el.className.slice(0, 100),
                    };
                }
            }
            return { found: false };
        }
    """)

    if not result or not result.get("found"):
        return None

    logger.info(
        f"[vision_captcha] 检测到图形验证码: prompt='{result.get('prompt')}', "
        f"imgRect={result.get('imgRect')}"
    )
    return result


async def _screenshot_captcha_image(page: Page, img_rect: dict) -> Optional[str]:
    """
    截取验证码图片区域，返回 base64 编码。
    """
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
        return base64.b64encode(screenshot).decode("utf-8")
    except Exception as e:
        logger.error(f"[vision_captcha] 截图失败: {e}")
        return None


def _call_vision_model(image_base64: str, prompt_text: str, img_width: float, img_height: float) -> Optional[dict]:
    """
    调用 Doubao-Seed-2.0-pro 视觉模型，分析验证码图片并返回点击坐标。

    Returns:
        {"x": float, "y": float} 相对于图片的归一化坐标 (0-1)
        None if failed
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


async def solve_vision_captcha(page: Page, max_retries: int = 3) -> bool:
    """
    检测并求解图形点选验证码。

    流程:
      1. 检测验证码弹窗
      2. 截图图片区域
      3. 调用视觉模型获取点击坐标
      4. 模拟点击
      5. 检查是否通过，失败则重试

    Returns:
        True if solved, False if failed
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

        # 2. 截图验证码图片
        image_b64 = await _screenshot_captcha_image(page, img_rect)
        if not image_b64:
            continue

        # 3. 调用视觉模型（同步调用，在线程池中执行避免阻塞事件循环）
        coords = await asyncio.get_event_loop().run_in_executor(
            None,
            _call_vision_model,
            image_b64,
            prompt_text,
            img_rect["width"],
            img_rect["height"],
        )
        if not coords:
            logger.warning(f"[vision_captcha] 第 {attempt} 次视觉模型未返回有效坐标")
            # 点击刷新按钮换一题
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

        # 模拟自然点击（先移动再点击）
        await page.mouse.move(click_x, click_y, steps=10)
        await page.wait_for_timeout(200)
        await page.mouse.click(click_x, click_y)

        # 5. 等待验证结果
        await page.wait_for_timeout(3000)

        # 检查验证码是否消失
        still_visible = await detect_vision_captcha(page)
        if not still_visible:
            logger.info(f"[vision_captcha] 验证码求解成功（第 {attempt} 次尝试）")
            return True

        logger.info(f"[vision_captcha] 第 {attempt} 次点击未通过，重试...")
        await page.wait_for_timeout(1000)

    logger.warning(f"[vision_captcha] {max_retries} 次尝试均失败")
    return False


async def _click_refresh(page: Page) -> None:
    """点击验证码刷新按钮（换一题）"""
    refresh_selectors = [
        "[class*='captcha'] [class*='refresh']",
        "[class*='captcha'] [class*='reload']",
        "[class*='verify'] [class*='refresh']",
        "[class*='captcha'] svg",  # 刷新图标通常是 SVG
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
