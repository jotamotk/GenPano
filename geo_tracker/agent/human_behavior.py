"""
拟人行为模拟
- 随机化打字速度、错误率
- 鼠标 Bezier 曲线移动
- 随机阅读停留时间
"""
from __future__ import annotations

import asyncio
import random
import math
from typing import Tuple

from playwright.async_api import Page


# ─── 打字模拟 ─────────────────────────────────────────────────────────────────

async def human_type(page: Page, selector: str, text: str, wpm: int = 60) -> None:
    """
    模拟人类打字，含偶发错误 & 退格修正
    wpm: 目标速度，会在 ±20% 范围内随机浮动
    """
    element = await page.query_selector(selector)
    if not element:
        return

    await element.click()
    await asyncio.sleep(random.uniform(0.3, 0.8))

    chars_per_sec = (wpm * 5) / 60   # 平均每字5字符
    base_delay = 1.0 / chars_per_sec

    i = 0
    while i < len(text):
        char = text[i]

        # 5% 概率打错一个字符
        if random.random() < 0.05 and char.isalpha():
            wrong_char = random.choice("qwertyuiopasdfghjklzxcvbnm")
            await element.type(wrong_char)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.05, 0.15))

        await element.type(char)

        # 随机化每个字符的延迟
        delay = base_delay * random.uniform(0.6, 1.8)

        # 空格和标点后停顿更长（模拟思考）
        if char in " ，。？！,.?!":
            delay *= random.uniform(1.5, 3.0)

        await asyncio.sleep(delay)
        i += 1


# ─── 鼠标移动 ─────────────────────────────────────────────────────────────────

def _bezier_curve(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    steps: int = 30,
) -> list[Tuple[float, float]]:
    """三次贝塞尔曲线，生成自然鼠标轨迹点"""
    points = []
    for t_int in range(steps + 1):
        t = t_int / steps
        x = (
            (1 - t) ** 3 * p0[0]
            + 3 * (1 - t) ** 2 * t * p1[0]
            + 3 * (1 - t) * t ** 2 * p2[0]
            + t ** 3 * p3[0]
        )
        y = (
            (1 - t) ** 3 * p0[1]
            + 3 * (1 - t) ** 2 * t * p1[1]
            + 3 * (1 - t) * t ** 2 * p2[1]
            + t ** 3 * p3[1]
        )
        points.append((x, y))
    return points


async def human_move_to(page: Page, x: int, y: int) -> None:
    """从当前鼠标位置沿贝塞尔曲线移动到目标坐标"""
    vp = page.viewport_size or {"width": 1920, "height": 1080}

    # 随机起点（假设在屏幕中间附近）
    start_x = random.randint(vp["width"] // 4, vp["width"] * 3 // 4)
    start_y = random.randint(vp["height"] // 4, vp["height"] * 3 // 4)

    # 随机控制点（产生自然弯曲）
    cp1 = (
        start_x + random.randint(-200, 200),
        start_y + random.randint(-200, 200),
    )
    cp2 = (
        x + random.randint(-100, 100),
        y + random.randint(-100, 100),
    )

    points = _bezier_curve((start_x, start_y), cp1, cp2, (x, y), steps=25)

    for px, py in points:
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(0.008, 0.025))


# ─── 滚动 & 阅读停留 ──────────────────────────────────────────────────────────

async def human_scroll_read(page: Page, min_sec: float = 3.0, max_sec: float = 12.0) -> None:
    """
    模拟阅读：随机滚动 + 停留，总时长在 [min_sec, max_sec] 之间
    """
    total = random.uniform(min_sec, max_sec)
    elapsed = 0.0

    while elapsed < total:
        scroll_amount = random.randint(80, 350)
        await page.mouse.wheel(0, scroll_amount)

        pause = random.uniform(0.5, 2.5)
        await asyncio.sleep(pause)
        elapsed += pause

        # 偶尔向上回滚（模拟重读）
        if random.random() < 0.2:
            await page.mouse.wheel(0, -random.randint(50, 150))
            await asyncio.sleep(random.uniform(0.3, 1.0))
            elapsed += 0.5


async def pre_query_pause() -> None:
    """打开页面后、开始输入前的自然停顿"""
    await asyncio.sleep(random.uniform(1.5, 4.0))


async def post_submit_wait() -> None:
    """提交后等待响应生成的随机时长"""
    await asyncio.sleep(random.uniform(2.0, 5.0))


async def inter_query_delay() -> None:
    """两次查询之间的间隔（避免高频触发风控）"""
    await asyncio.sleep(random.uniform(25.0, 90.0))
