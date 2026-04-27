"""
Nike GEO Tracker 端到端测试脚本
使用 SQLite 替代 PostgreSQL，不需要 Redis/Celery

运行方式：
  cd genpano
  ANTHROPIC_API_KEY=sk-xxx python geo_tracker/run_nike_test.py

阶段：
  1. 建库建表（幂等）
  2. Brand Analyzer → Topics + Prompts + Competitors 写入 DB（幂等，已存在则跳过）
  3. Profile Generator → 生成用户画像写入 DB（幂等，已存在则跳过）
  4. Fanout Engine → Query 改写写入 DB（抽样 FANOUT_PROFILE_SAMPLE 个 Profile）
  5. LLM API 爬取 → 无需 cookies，直接调用各 LLM API
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import random

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select, func, text

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from geo_tracker.db.models import (
    Base, Brand, Topic, Prompt, Competitor,
    Profile, BrowserProfile, Query, QueryStatus, LLMResponse,
)
from geo_tracker.generation.brand_analyzer import BrandAnalyzer
from geo_tracker.generation.profile_generator import ProfileGenerator
from geo_tracker.generation.fanout_engine import FanoutEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nike_test")

# ── 配置 ─────────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "nike_test.db")
DB_URL  = f"sqlite+aiosqlite:///{DB_PATH}"

NIKE_INFO = dict(
    brand_name    = "Nike",
    website       = "nike.com",
    industry      = "运动服装与装备",
    description   = "全球领先的运动品牌，专注于运动鞋、运动服装及运动装备的设计与销售，"
                    "代表性产品包括 Air Max、Jordan、Dri-FIT 系列。",
    target_market = "中国大陆及海外华人市场",
)

# Fanout 阶段只抽取多少个 Profile（避免 API 费用过高）
FANOUT_PROFILE_SAMPLE = 5

# LLM 爬取：每个 LLM 最多执行多少条 Query（测试阶段）
CRAWL_QUERIES_PER_LLM = 5

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")


# ── 主流程 ────────────────────────────────────────────────────────────────────

async def main():
    api_key = os.getenv("ZHIPU_API_KEY", "")
    if not api_key:
        logger.error("未设置 ZHIPU_API_KEY，请先 export ZHIPU_API_KEY=xxx")
        sys.exit(1)

    logger.info(f"Step 1: 初始化数据库 → {DB_PATH}")
    engine = create_async_engine(DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        # ── 直接跳到 Step 5：数据已存在，只跑浏览器爬取 ────────────────────
        brand = (await db.execute(select(Brand).where(Brand.name == NIKE_INFO["brand_name"]))).scalar_one()
        logger.info(f"Step 5: 浏览器爬取（Playwright，无账号）brand_id={brand.id}")
        await _crawl_via_browser(db, brand.id)

        # ── 最终统计 ────────────────────────────────────────────────────────
        await _print_summary(db, brand.id)

    await engine.dispose()
    logger.info(f"完成！数据库: {DB_PATH}")


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

async def _get_or_create_brand(db: AsyncSession) -> Brand:
    result = await db.execute(select(Brand).where(Brand.name == NIKE_INFO["brand_name"]))
    brand = result.scalar_one_or_none()
    if brand:
        logger.info(f"  Brand 已存在 (id={brand.id})")
        return brand
    brand = Brand(**{k: v for k, v in NIKE_INFO.items() if k not in ("brand_name",)},
                  name=NIKE_INFO["brand_name"])
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    logger.info(f"  Brand 创建 (id={brand.id})")
    return brand


async def _ensure_topics_prompts(db: AsyncSession, brand: Brand):
    """幂等：已存在则直接从 DB 重建 analysis 对象，不再调 Claude"""
    from geo_tracker.generation.brand_analyzer import (
        BrandAnalysisResult, TopicResult, PromptResult, CompetitorResult
    )

    topics_db = (await db.execute(select(Topic).where(Topic.brand_id == brand.id))).scalars().all()

    if topics_db:
        logger.info("  Topics/Prompts 已存在，跳过 Claude 调用")
        prompt_ids = []
        prompts_list = []
        for i, t in enumerate(topics_db):
            ps = (await db.execute(select(Prompt).where(Prompt.topic_id == t.id))).scalars().all()
            for p in ps:
                prompt_ids.append(p.id)
                prompts_list.append(PromptResult(topic_index=i, text=p.text, intent=p.intent or "", language=p.language or "zh"))
        comps_db = (await db.execute(select(Competitor).where(Competitor.brand_id == brand.id))).scalars().all()
        analysis = BrandAnalysisResult(
            topics=[TopicResult(text=t.text, category=t.category or "") for t in topics_db],
            prompts=prompts_list,
            competitors=[CompetitorResult(name=c.name, website=c.website or "", confidence=c.confidence_score or 0.8) for c in comps_db],
        )
        return analysis, prompt_ids

    # 首次：调 Claude API
    analyzer = BrandAnalyzer()
    analysis = await analyzer.analyze(**NIKE_INFO)

    prompt_ids = []
    for i, t in enumerate(analysis.topics):
        topic = Topic(brand_id=brand.id, text=t.text, category=t.category,
                      generated_by=os.getenv("GLM_MODEL", "glm-4-flash"))
        db.add(topic)
        await db.flush()
        for p in analysis.prompts:
            if p.topic_index == i:
                prompt = Prompt(topic_id=topic.id, text=p.text, intent=p.intent, language=p.language)
                db.add(prompt)
                await db.flush()
                prompt_ids.append(prompt.id)

    for c in analysis.competitors:
        db.add(Competitor(brand_id=brand.id, name=c.name, website=c.website,
                          confidence_score=c.confidence))
    await db.commit()
    return analysis, prompt_ids


async def _ensure_profiles(db: AsyncSession) -> int:
    n = (await db.execute(select(func.count()).select_from(Profile))).scalar()
    if n > 0:
        logger.info(f"  Profiles 已存在 ({n} 条)，跳过生成")
        return n
    return await ProfileGenerator.generate_all(db)


async def _run_fanout_sampled(
    db: AsyncSession, brand_id: int, analysis, prompt_ids: list[int]
) -> int:
    """只抽取 FANOUT_PROFILE_SAMPLE 个 Profile 做 Fanout（避免爆 API 费用）"""
    all_profiles = (await db.execute(select(Profile))).scalars().all()

    # 随机抽样（固定 seed 保证可复现）
    rng = random.Random(42)
    sample = rng.sample(all_profiles, min(FANOUT_PROFILE_SAMPLE, len(all_profiles)))

    from geo_tracker.generation.fanout_engine import get_target_llms, FanoutEngine
    engine = FanoutEngine()

    # 加载 Prompt 记录
    prompts_db = {p.id: p for p in (await db.execute(
        select(Prompt).where(Prompt.id.in_(prompt_ids))
    )).scalars().all()}

    total = 0
    for idx, profile in enumerate(sample):
        target_llms = get_target_llms(profile)
        created = await engine._process_profile(
            db, brand_id, profile, list(prompts_db.values()), target_llms, dry_run=False
        )
        total += created
        if (idx + 1) % 10 == 0:
            logger.info(f"  Fanout 进度: {idx+1}/{len(sample)} profiles, 累计 {total} queries")

    logger.info(f"  Fanout 完成: {total} 新 queries")
    return total


# ── 浏览器爬取（无账号，Playwright）─────────────────────────────────────────

# 各 LLM 的浏览器操作配置（无账号 guest 模式）
BROWSER_LLM_CONFIG = {
    "chatgpt": {
        "url":              "https://chatgpt.com",
        # ChatGPT 无账号时 URL 跳转到 /auth，需先等待加载
        "input_selector":   "#prompt-textarea, [data-testid='prompt-textarea'], textarea",
        "submit_key":       "Enter",
        "response_selector": "[data-message-author-role='assistant'] .markdown, article",
        "wait_after_submit": 20000,
        "load_wait":        5000,
        "requires_login":   False,
    },
    "gemini": {
        "url":              "https://gemini.google.com",
        "input_selector":   "rich-textarea .ql-editor, textarea, [contenteditable='true']",
        "submit_key":       "Enter",
        "response_selector": "message-content, .response-container, model-response",
        "wait_after_submit": 20000,
        "load_wait":        5000,
        "requires_login":   False,
    },
    "perplexity": {
        "url":              "https://www.perplexity.ai",
        "input_selector":   "textarea, [placeholder*='Ask'], input[type='text']",
        "submit_key":       "Enter",
        "response_selector": ".prose, [class*='answer'], [class*='response']",
        "wait_after_submit": 15000,
        "load_wait":        4000,
        "requires_login":   False,
    },
    "kimi": {
        "url":              "https://kimi.moonshot.cn",
        "input_selector":   ".chat-input-editor",
        "submit_key":       "Enter",
        "response_selector": "[class*='segment-content'], [class*='message-content'], .chat-message",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   False,
        "contenteditable":  True,
    },
    "doubao": {
        "url":              "https://www.doubao.com/chat",
        "input_selector":   "textarea",
        "submit_key":       "Enter",
        "response_selector": "[class*='message'], [class*='content']",
        "wait_after_submit": 20000,
        "load_wait":        10000,
        "requires_login":   False,
    },
    "deepseek": {
        "url":              "https://chat.deepseek.com",
        "input_selector":   "textarea, [contenteditable=true], input[type=text]",
        "submit_key":       "Enter",
        "response_selector": "[class*='message'], [class*='content'], .markdown",
        "wait_after_submit": 20000,
        "load_wait":        8000,
        "requires_login":   False,
    },
}

# 代理配置（从环境变量读）
BROWSER_PROXY = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or None


async def _crawl_via_browser(db: AsyncSession, brand_id: int):
    """
    浏览器自动化爬取（Playwright + Chromium，无账号）
    第一组：chatgpt、gemini（国际主流）
    """
    from playwright.async_api import async_playwright

    # 国内主流 LLM（直连，不走代理）
    TARGET_LLMS = ["kimi", "doubao", "deepseek"]
    DOMESTIC_LLMS = {"kimi", "doubao", "deepseek"}

    pending = (await db.execute(
        select(Query).where(
            Query.brand_id == brand_id,
            Query.status == QueryStatus.PENDING,
            Query.target_llm.in_(TARGET_LLMS),
        )
    )).scalars().all()

    if not pending:
        logger.info("  没有 PENDING queries，跳过爬取")
        return

    by_llm: dict[str, list[Query]] = {}
    for q in pending:
        by_llm.setdefault(q.target_llm, []).append(q)

    logger.info(f"  目标 LLM: {TARGET_LLMS}，PENDING: { {k: len(v) for k, v in by_llm.items()} }")

    done_count = 0

    # 代理配置
    proxy_cfg = {"server": BROWSER_PROXY} if BROWSER_PROXY else None
    if proxy_cfg:
        logger.info(f"  使用代理: {BROWSER_PROXY}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            proxy=proxy_cfg,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
            ],
        )

        for llm_name in TARGET_LLMS:
            if llm_name not in by_llm:
                logger.info(f"  [{llm_name}] 无 PENDING queries，跳过")
                continue

            cfg = BROWSER_LLM_CONFIG[llm_name]
            sample_q = by_llm[llm_name][:CRAWL_QUERIES_PER_LLM]

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                ignore_https_errors=True,
            )
            page = await context.new_page()

            # 隐藏 webdriver 特征
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            logger.info(f"  [{llm_name}] 打开: {cfg['url']}")
            try:
                await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(cfg.get("load_wait", 4000))
                logger.info(f"  [{llm_name}] 页面标题: {await page.title()}")
            except Exception as e:
                logger.error(f"  [{llm_name}] 页面加载失败: {e}")
                await context.close()
                continue

            # 尝试找输入框
            input_el = None
            for sel in cfg["input_selector"].split(", "):
                try:
                    input_el = await page.wait_for_selector(sel.strip(), timeout=8000, state="visible")
                    logger.info(f"  [{llm_name}] 输入框找到: {sel.strip()}")
                    break
                except Exception:
                    continue

            if not input_el:
                logger.error(f"  [{llm_name}] 找不到输入框，截图后跳过")
                await page.screenshot(path=f"geo_tracker/{llm_name}_debug.png")
                await context.close()
                continue

            for q in sample_q:
                try:
                    resp_text = await _browser_query(page, cfg, q.query_text, llm_name, input_el)
                    await _save_response(db, q, resp_text, llm_name, f"browser_{llm_name}")
                    done_count += 1
                    logger.info(f"    [{llm_name}] Q{q.id}: {q.query_text[:55]}… → {len(resp_text)} chars")
                    # 重新找输入框（提交后可能刷新）
                    for sel in cfg["input_selector"].split(", "):
                        try:
                            input_el = await page.wait_for_selector(sel.strip(), timeout=5000, state="visible")
                            break
                        except Exception:
                            continue
                except Exception as e:
                    logger.error(f"    [{llm_name}] Q{q.id} 失败: {e}")
                    await page.screenshot(path=f"geo_tracker/{llm_name}_error_q{q.id}.png")

            await context.close()

        await browser.close()

    logger.info(f"  浏览器爬取完成: {done_count} 条 responses 写入 DB")


async def _browser_query(page, cfg: dict, query_text: str, llm_name: str, input_el=None) -> str:
    """在已打开的页面里输入 query，等待响应，抓取文本"""
    if input_el is None:
        input_el = await page.wait_for_selector(cfg["input_selector"].split(", ")[0], timeout=10000)
    await input_el.click()
    await page.wait_for_timeout(500)

    # contenteditable div 不支持 fill()，用 Ctrl+A 清空后直接 type()
    if cfg.get("contenteditable"):
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
    else:
        await input_el.fill("")
    await page.keyboard.type(query_text, delay=25)
    await page.wait_for_timeout(500)

    # 提交
    await page.keyboard.press("Enter")
    logger.debug(f"    [{llm_name}] 已提交 Query，等待响应…")

    # 等待响应生成
    await page.wait_for_timeout(cfg["wait_after_submit"])

    # 抓取响应文本
    try:
        elements = await page.query_selector_all(cfg["response_selector"])
        if elements:
            texts = [await el.inner_text() for el in elements]
            return "\n".join(t for t in texts if t.strip())[-3000:]  # 最多保留 3000 字符
        else:
            # fallback：取页面主体文本
            return (await page.inner_text("body"))[:3000]
    except Exception:
        return (await page.inner_text("body"))[:3000]




async def _save_response(
    db: AsyncSession, query: Query, text: str, llm_name: str, llm_version: str
):
    """保存 LLMResponse，更新 Query 状态"""
    # 检查是否已有 response
    existing = (await db.execute(
        select(LLMResponse).where(LLMResponse.query_id == query.id)
    )).scalar_one_or_none()
    if existing:
        return

    resp = LLMResponse(
        query_id       = query.id,
        raw_text       = text,
        response_time_ms = 0,
        llm_version    = llm_version,
    )
    db.add(resp)
    query.status = QueryStatus.DONE
    await db.commit()


# ── 统计 ──────────────────────────────────────────────────────────────────────

async def _print_summary(db: AsyncSession, brand_id: int):
    logger.info("\n========== 数据库统计 ==========")
    for label, q in [
        ("Topics",      select(func.count()).where(Topic.brand_id == brand_id)),
        ("Prompts",     select(func.count()).select_from(Prompt).join(Topic).where(Topic.brand_id == brand_id)),
        ("Competitors", select(func.count()).where(Competitor.brand_id == brand_id)),
        ("Profiles",    select(func.count()).select_from(Profile)),
        ("Queries",     select(func.count()).where(Query.brand_id == brand_id)),
        ("Responses",   select(func.count()).select_from(LLMResponse).join(Query).where(Query.brand_id == brand_id)),
    ]:
        n = (await db.execute(q)).scalar()
        logger.info(f"  {label:12s}: {n}")

    rows = (await db.execute(text(
        "SELECT target_llm, status, COUNT(*) FROM queries WHERE brand_id=:bid "
        "GROUP BY target_llm, status ORDER BY target_llm, status"
    ), {"bid": brand_id})).all()

    logger.info("  Queries by LLM/status:")
    for llm, status, cnt in rows:
        logger.info(f"    {llm:12s} [{status}]: {cnt}")
    logger.info("=================================\n")

    # 打印几条 Response 样例
    samples = (await db.execute(
        select(Query, LLMResponse)
        .join(LLMResponse, Query.id == LLMResponse.query_id)
        .where(Query.brand_id == brand_id)
        .limit(3)
    )).all()
    if samples:
        logger.info("── Response 样例 ──")
        for q, r in samples:
            logger.info(f"[{q.target_llm}] Q: {q.query_text[:60]}…")
            logger.info(f"         A: {r.raw_text[:120]}…\n")


def _print_topics(analysis):
    logger.info("  Topics 列表：")
    for i, t in enumerate(analysis.topics):
        logger.info(f"    [{i}] [{t.category:18s}] {t.text}")


if __name__ == "__main__":
    asyncio.run(main())
