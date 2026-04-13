"""
滑块验证码本地求解器（不依赖第三方打码服务）

原理：
1. 截图 CAPTCHA 背景图，用 Pillow 分析像素找到缺口（gap）位置
2. 计算滑块需要拖拽的水平距离
3. 用贝塞尔曲线模拟人类拖拽轨迹（加速→匀速→减速 + 微抖动）

支持常见滑块验证码类型：
- GeeTest (极验) V3/V4
- 自研滑块（DeepSeek、字节跳动等）
"""
from __future__ import annotations

import asyncio
import io
import logging
import random
import math
from typing import Optional, Tuple

from playwright.async_api import Page, ElementHandle

logger = logging.getLogger(__name__)

# ─── 滑块 DOM 选择器（按优先级排列）─────────────────────────────────────────────

# 背景图（含缺口的大图）
BG_IMAGE_SELECTORS = [
    # GeeTest
    ".geetest_canvas_bg canvas",
    ".geetest_bg",
    "canvas.geetest_canvas_bg",
    # 通用
    "[class*='captcha'] img[class*='bg']",
    "[class*='verify'] img[class*='bg']",
    "[class*='slider'] img[class*='bg']",
    "[class*='captcha-bg']",
    "[class*='verify-image']",
    "[class*='captcha'] canvas",
    "[class*='verify'] canvas",
    # img fallback
    "[class*='captcha'] img",
    "[class*='verify'] img:not([class*='piece']):not([class*='slice'])",
]

# 拼图块（需要被拖到缺口位置的小块）
PIECE_IMAGE_SELECTORS = [
    ".geetest_canvas_slice canvas",
    ".geetest_slice",
    "[class*='captcha'] img[class*='piece']",
    "[class*='captcha'] img[class*='slice']",
    "[class*='verify'] img[class*='piece']",
    "[class*='verify'] img[class*='slice']",
    "[class*='jigsaw']",
    "[class*='puzzle-piece']",
]

# 滑块手柄（用户拖拽的圆形/方形按钮）
SLIDER_HANDLE_SELECTORS = [
    # GeeTest
    ".geetest_slider_button",
    ".geetest_btn",
    # 通用
    "[class*='slider'] [class*='handler']",
    "[class*='slider'] [class*='handle']",
    "[class*='slider'] [class*='btn']",
    "[class*='slider'] [class*='drag']",
    "[class*='verify'] [class*='handler']",
    "[class*='verify'] [class*='handle']",
    "[class*='captcha'] [class*='handler']",
    "[class*='captcha'] [class*='handle']",
    "[class*='slide-bar'] [class*='btn']",
    "[class*='drag-btn']",
    "[class*='slider-btn']",
]

# 滑块轨道
SLIDER_TRACK_SELECTORS = [
    ".geetest_slider",
    "[class*='slider'][class*='track']",
    "[class*='slider-bar']",
    "[class*='slide-bar']",
    "[class*='verify'][class*='bar']",
    "[class*='slider'][class*='container']",
]

# CAPTCHA 容器（用于截图）
CAPTCHA_CONTAINER_SELECTORS = [
    ".geetest_widget",
    ".geetest_panel_box",
    "[class*='captcha-container']",
    "[class*='verify-wrap']",
    "[class*='captcha-wrap']",
    "[class*='slider-verify']",
    "[class*='slide-verify']",
    "[class*='captcha'][class*='modal']",
    "[class*='verify'][class*='modal']",
    "[class*='captcha'][class*='box']",
    "[class*='verify'][class*='box']",
]


async def solve_slider_captcha(page: Page, max_attempts: int = 3) -> bool:
    """
    检测并求解滑块验证码。

    Returns:
        True  — 验证码已解决或不存在
        False — 多次尝试后仍失败
    """
    for attempt in range(max_attempts):
        # 1. 找到滑块手柄
        handle = await _find_element(page, SLIDER_HANDLE_SELECTORS)
        if not handle:
            logger.info("未检测到滑块手柄，跳过")
            return True  # 没有滑块验证码

        logger.info(f"检测到滑块验证码 (尝试 {attempt + 1}/{max_attempts})")

        # 2. 确定缺口位置
        gap_offset = await _detect_gap_offset(page)
        if gap_offset is None:
            # fallback: 截图整个容器，用像素分析
            gap_offset = await _detect_gap_from_screenshot(page)

        if gap_offset is None:
            logger.warning("无法检测缺口位置，使用随机偏移")
            gap_offset = random.randint(100, 250)

        logger.info(f"缺口偏移量: {gap_offset}px")

        # 3. 执行拖拽
        success = await _drag_slider(page, handle, gap_offset)
        if not success:
            logger.warning(f"拖拽失败 (尝试 {attempt + 1})")
            await asyncio.sleep(random.uniform(1.0, 2.0))
            continue

        # 4. 等待验证结果
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # 检查验证码是否消失
        handle_after = await _find_element(page, SLIDER_HANDLE_SELECTORS)
        if not handle_after:
            logger.info("滑块验证码已通过！")
            return True

        # 检查是否有成功标记
        success_el = await _find_element(page, [
            "[class*='success']",
            "[class*='geetest_success']",
            "[class*='verify-success']",
        ])
        if success_el:
            logger.info("滑块验证码已通过（成功标记）！")
            return True

        logger.warning(f"验证未通过，可能偏移不准确 (尝试 {attempt + 1})")
        # 等待验证码刷新
        await asyncio.sleep(random.uniform(2.0, 3.0))

    logger.error(f"滑块验证码 {max_attempts} 次尝试均失败")
    return False


# ─── 缺口检测 ────────────────────────────────────────────────────────────────────


async def _detect_gap_offset(page: Page) -> Optional[int]:
    """
    尝试从 DOM 中直接获取拼图块位置来推算缺口偏移。
    许多滑块验证码会把拼图块的 left/transform 设置为缺口位置。
    """
    piece = await _find_element(page, PIECE_IMAGE_SELECTORS)
    if not piece:
        return None

    try:
        # 通过拼图块的位置推算缺口 X 坐标
        piece_box = await piece.bounding_box()
        if piece_box and piece_box["x"] > 0:
            # 获取滑块轨道起点
            track = await _find_element(page, SLIDER_TRACK_SELECTORS)
            if track:
                track_box = await track.bounding_box()
                if track_box:
                    # 缺口偏移 = 拼图块中心X - 轨道起点X
                    offset = int(piece_box["x"] - track_box["x"])
                    if 20 < offset < 400:
                        logger.info(f"从拼图块位置推算缺口偏移: {offset}px")
                        return offset

        # 尝试从 style 属性获取 left 值
        style = await piece.get_attribute("style") or ""
        if "left:" in style:
            import re
            match = re.search(r"left:\s*(\d+(?:\.\d+)?)\s*px", style)
            if match:
                offset = int(float(match.group(1)))
                if 20 < offset < 400:
                    logger.info(f"从 CSS left 推算缺口偏移: {offset}px")
                    return offset
    except Exception as e:
        logger.debug(f"DOM 缺口检测失败: {e}")

    return None


async def _detect_gap_from_screenshot(page: Page) -> Optional[int]:
    """
    截图 CAPTCHA 区域，用像素分析找到缺口位置。

    原理：滑块背景图的缺口通常是一个明显的暗色矩形区域，
    通过检测每列像素的亮度突变来定位。
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow 未安装，无法进行截图分析")
        return None

    # 找到验证码容器
    container = await _find_element(page, CAPTCHA_CONTAINER_SELECTORS)
    if not container:
        # fallback: 找背景图
        container = await _find_element(page, BG_IMAGE_SELECTORS)
    if not container:
        logger.warning("未找到验证码容器")
        return None

    try:
        # 截图
        screenshot_bytes = await container.screenshot()
        img = Image.open(io.BytesIO(screenshot_bytes)).convert("L")  # 灰度图
        width, height = img.size

        if width < 50 or height < 30:
            logger.warning(f"截图尺寸过小: {width}x{height}")
            return None

        pixels = img.load()

        # 分析策略：计算每列像素的平均亮度变化率
        # 缺口区域的边缘会有明显的亮度突变
        col_diffs = []
        # 只分析中间区域（排除顶部/底部的滑块轨道）
        y_start = int(height * 0.1)
        y_end = int(height * 0.75)
        sample_rows = range(y_start, y_end, max(1, (y_end - y_start) // 30))

        for x in range(1, width - 1):
            diff_sum = 0
            count = 0
            for y in sample_rows:
                # 水平梯度（相邻像素差）
                left_px = pixels[x - 1, y]
                curr_px = pixels[x, y]
                right_px = pixels[x + 1, y]
                diff_sum += abs(curr_px - left_px) + abs(curr_px - right_px)
                count += 1
            avg_diff = diff_sum / count if count > 0 else 0
            col_diffs.append((x, avg_diff))

        if not col_diffs:
            return None

        # 计算全局平均差异和标准差
        all_diffs = [d for _, d in col_diffs]
        mean_diff = sum(all_diffs) / len(all_diffs)
        std_diff = (sum((d - mean_diff) ** 2 for d in all_diffs) / len(all_diffs)) ** 0.5

        if std_diff < 1:
            logger.warning("图像对比度过低，无法定位缺口")
            return None

        # 找到高于 2 个标准差的列（边缘突变点）
        threshold = mean_diff + 2.0 * std_diff
        edge_cols = [x for x, d in col_diffs if d > threshold]

        if not edge_cols:
            logger.warning("未检测到边缘突变")
            return None

        # 找到最左边的一组连续边缘（缺口左边缘）
        # 跳过图像最左侧 15%（通常是拼图块起始位置）
        min_x = int(width * 0.15)
        edge_cols = [x for x in edge_cols if x > min_x]

        if not edge_cols:
            return None

        # 聚类连续的边缘列，找第一个聚类的中心
        clusters = _cluster_points(edge_cols, gap=5)
        if not clusters:
            return None

        # 第一个聚类通常是缺口左边缘
        gap_left = clusters[0][0]
        logger.info(
            f"截图分析: 图片 {width}x{height}, "
            f"检测到缺口左边缘 x={gap_left}, "
            f"边缘聚类数={len(clusters)}"
        )

        # 返回缺口中心位置（左边缘 + 大约半个缺口宽度）
        # 典型缺口宽度约 40-60px
        gap_center = gap_left + 25
        return min(gap_center, width - 20)

    except Exception as e:
        logger.warning(f"截图分析失败: {e}")
        return None


def _cluster_points(points: list[int], gap: int = 5) -> list[list[int]]:
    """将相近的点聚类"""
    if not points:
        return []
    points = sorted(points)
    clusters = [[points[0]]]
    for p in points[1:]:
        if p - clusters[-1][-1] <= gap:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return clusters


# ─── 拖拽模拟 ────────────────────────────────────────────────────────────────────


async def _drag_slider(
    page: Page, handle: ElementHandle, distance: int
) -> bool:
    """
    模拟人类拖拽滑块。

    轨迹特征（模拟真人）：
    - 先加速后减速（非匀速）
    - 到达目标附近时会有微调（略微过头再回退）
    - Y 轴有小幅随机抖动
    - 每步之间有不均匀的时间间隔
    """
    box = await handle.bounding_box()
    if not box:
        return False

    start_x = box["x"] + box["width"] / 2
    start_y = box["y"] + box["height"] / 2

    # 生成人类轨迹
    track_points = _generate_human_track(distance)

    try:
        # 移动到滑块上方
        await page.mouse.move(start_x, start_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # 按下鼠标
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # 沿轨迹移动
        for dx, dy, dt in track_points:
            await page.mouse.move(start_x + dx, start_y + dy)
            await asyncio.sleep(dt)

        # 松开鼠标
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()

        return True
    except Exception as e:
        logger.error(f"拖拽操作失败: {e}")
        # 确保鼠标释放
        try:
            await page.mouse.up()
        except Exception:
            pass
        return False


def _generate_human_track(distance: int) -> list[Tuple[float, float, float]]:
    """
    生成模拟人类拖拽的轨迹点列表。

    Returns:
        [(dx, dy, dt), ...] — 每步的 X偏移、Y偏移、等待时间
    """
    track = []
    current_x = 0.0
    current_y = 0.0

    # 总步数 30-50
    num_steps = random.randint(30, 50)

    # 先快后慢的 easing（三次缓出）
    for i in range(num_steps):
        progress = (i + 1) / num_steps
        # ease-out-cubic: 1 - (1-t)^3
        eased = 1 - (1 - progress) ** 3

        # 目标X（加一点过冲：先超过再回来）
        overshoot = distance * 1.05 if progress < 0.85 else distance
        target_x = overshoot * eased

        dx = target_x - current_x
        current_x = target_x

        # Y 轴随机抖动 ±3px
        dy = random.uniform(-2, 2)
        current_y += dy

        # 时间间隔：快的阶段间隔短，慢的阶段间隔长
        if progress < 0.3:
            dt = random.uniform(0.005, 0.015)   # 加速阶段：快
        elif progress < 0.7:
            dt = random.uniform(0.010, 0.025)   # 匀速阶段
        else:
            dt = random.uniform(0.020, 0.045)   # 减速阶段：慢

        track.append((current_x, current_y, dt))

    # 在末尾加几步微调（模拟精确对齐）
    for _ in range(random.randint(2, 4)):
        jitter_x = random.uniform(-2, 2)
        jitter_y = random.uniform(-1, 1)
        current_x = distance + jitter_x
        current_y += jitter_y
        dt = random.uniform(0.03, 0.08)
        track.append((current_x, current_y, dt))

    # 最后一步精确到目标
    track.append((float(distance), current_y, random.uniform(0.02, 0.05)))

    return track


# ─── 工具函数 ─────────────────────────────────────────────────────────────────────


async def _find_element(page: Page, selectors: list[str]) -> Optional[ElementHandle]:
    """依次尝试多个选择器，返回第一个可见的匹配元素"""
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                visible = await el.is_visible()
                if visible:
                    return el
        except Exception:
            continue
    return None
