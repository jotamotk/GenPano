"""
Fanout 引擎
Prompt × Profile → 用 GLM 改写成符合该 Profile 口吻的自然 Query
再按 LLM 分配矩阵展开为 Query 记录写入 DB
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from zhipuai import ZhipuAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import Profile, Prompt, Query, QueryStatus
from geo_tracker.generation.brand_analyzer import BrandAnalysisResult

logger = logging.getLogger(__name__)

GLM_MODEL     = os.getenv("GLM_MODEL", "glm-5")
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")

# 每次批量改写的 prompt 数量（节省 API 调用次数）
REWRITE_BATCH_SIZE = 10


# ─── LLM 分配矩阵 ─────────────────────────────────────────────────────────────

LLM_BY_COUNTRY: dict[str, list[str]] = {
    "CN": ["chatgpt", "kimi", "doubao", "zhipu", "perplexity"],
    "US": ["chatgpt", "gemini", "claude", "perplexity", "grok"],
    "GB": ["chatgpt", "gemini", "claude", "perplexity"],
    "DE": ["chatgpt", "gemini", "claude", "perplexity"],
    "SG": ["chatgpt", "gemini", "perplexity", "kimi"],
    "AU": ["chatgpt", "gemini", "claude", "perplexity"],
}
LLM_DEFAULT = ["chatgpt", "gemini", "perplexity"]

def get_target_llms(profile: Profile) -> list[str]:
    """按 profile 地区 + segment 偏好决定目标 LLM 列表"""
    country_llms   = LLM_BY_COUNTRY.get(profile.country_code, LLM_DEFAULT)
    segment_llms   = profile.persona_traits.get("target_llms", [])
    # 取交集，保留顺序；若交集为空则退回 country_llms
    merged = [l for l in segment_llms if l in country_llms]
    return merged if merged else country_llms[:4]


# ─── Claude 改写 Prompt ───────────────────────────────────────────────────────

REWRITE_SYSTEM = """你是一个真实用户，请将用户发来的每条问题，
改写成符合你当前身份和习惯的自然提问方式。
严格按照JSON数组格式输出，数组中每个元素是改写后的字符串，顺序与输入一致。
不要解释，不要加序号，只输出JSON数组。"""


def _build_rewrite_user_msg(profile: Profile, base_prompts: list[str]) -> str:
    traits = profile.persona_traits
    lang   = profile.language

    identity_lines = [
        f"- 你是一名{traits.get('age', '30多岁')}岁的{profile.profession}",
        f"- 所在城市：{profile.location}",
        f"- 公司规模：{traits.get('company_size', '中型企业')}",
        f"- 语气风格：{'口语化随意' if traits.get('tone') == 'casual' else '较正式专业'}",
        f"- 问题长度：{'简短直接' if traits.get('verbosity') == 'short' else '中等详细' if traits.get('verbosity') == 'medium' else '详细描述'}",
    ]

    if traits.get("add_role_context"):
        identity_lines.append(f"- 你的痛点：{', '.join(traits.get('pain_points', []))}")
        identity_lines.append("- 在提问时可以带上你的身份背景和具体场景")
    else:
        identity_lines.append("- 不要在提问中暴露你的职业身份")

    if traits.get("use_buzzwords"):
        identity_lines.append("- 可以使用行业术语和专业词汇")
    else:
        identity_lines.append("- 使用普通人的日常语言，避免行业术语")

    if lang == "en":
        identity_lines.append("- 请用英文改写所有问题")
    else:
        identity_lines.append("- 请用中文改写所有问题")

    prompts_json = json.dumps(base_prompts, ensure_ascii=False)

    return (
        "你的身份：\n" + "\n".join(identity_lines) +
        f"\n\n需要改写的问题列表（JSON数组）：\n{prompts_json}"
    )


@dataclass
class RewriteResult:
    profile_id: int
    prompt_id:  int
    query_text: str


class FanoutEngine:
    def __init__(self):
        self.client = ZhipuAI(api_key=ZHIPU_API_KEY)

    # ── 主入口：为一个品牌生成全部 Query ───────────────────────────────────────

    async def generate_queries(
        self,
        db: AsyncSession,
        brand_id: int,
        analysis: BrandAnalysisResult,
        prompt_ids: list[int],   # 已写入DB的 Prompt 记录ID列表
        dry_run: bool = False,   # True时只返回数量不写DB
    ) -> int:
        """
        核心流程：
        1. 加载所有 Profiles
        2. 按 REWRITE_BATCH_SIZE 批量调用 Claude 改写
        3. 幂等写入 Query 记录
        """
        # 加载 Prompt 记录
        result  = await db.execute(select(Prompt).where(Prompt.id.in_(prompt_ids)))
        prompts = {p.id: p for p in result.scalars().all()}

        # 加载所有 Profile
        result   = await db.execute(select(Profile))
        profiles = result.scalars().all()

        logger.info(f"Fanout: {len(prompts)} prompts × {len(profiles)} profiles")

        total_created = 0

        # 按 Profile 为单位批量处理（避免 Claude API 调用过于碎片化）
        for profile in profiles:
            target_llms = get_target_llms(profile)
            created = await self._process_profile(
                db, brand_id, profile, list(prompts.values()), target_llms, dry_run
            )
            total_created += created

        return total_created

    # ── 处理单个 Profile 的全部 Prompt ────────────────────────────────────────

    async def _process_profile(
        self,
        db: AsyncSession,
        brand_id: int,
        profile: Profile,
        prompts: list[Prompt],
        target_llms: list[str],
        dry_run: bool,
    ) -> int:
        created = 0

        # 分批（REWRITE_BATCH_SIZE 条一批）调用 Claude
        for batch_start in range(0, len(prompts), REWRITE_BATCH_SIZE):
            batch = prompts[batch_start: batch_start + REWRITE_BATCH_SIZE]

            # 幂等检查：已存在的 (prompt_id, profile_id) 跳过
            existing_prompt_ids = await self._get_existing_prompt_ids(
                db, profile.id, [p.id for p in batch], target_llms[0]
            )
            new_batch = [p for p in batch if p.id not in existing_prompt_ids]
            if not new_batch:
                continue

            rewritten = await self._rewrite_batch(profile, new_batch)
            if not rewritten:
                continue

            if not dry_run:
                for rewrite in rewritten:
                    for llm in target_llms:
                        query = Query(
                            prompt_id=rewrite.prompt_id,
                            profile_id=rewrite.profile_id,
                            brand_id=brand_id,
                            query_text=rewrite.query_text,
                            target_llm=llm,
                            status=QueryStatus.PENDING,
                        )
                        db.add(query)
                        created += 1

                await db.commit()

            # 礼貌性延迟，避免 GLM API 频率限制（glm-5 限制较严）
            await asyncio.sleep(2.0)

        return created

    # ── Claude 批量改写 ────────────────────────────────────────────────────────

    async def _rewrite_batch(
        self,
        profile: Profile,
        prompts: list[Prompt],
    ) -> list[RewriteResult]:

        base_texts = [p.text for p in prompts]
        user_msg   = _build_rewrite_user_msg(profile, base_texts)

        import time
        response = None
        for attempt in range(5):
            try:
                response = self.client.chat.completions.create(
                    model=GLM_MODEL,
                    messages=[
                        {"role": "system", "content": REWRITE_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                )
                break
            except Exception as e:
                if "429" in str(e) or "1302" in str(e):
                    wait = 60 * (attempt + 1)
                    logger.warning(f"GLM 429 rate limit, waiting {wait}s (attempt {attempt+1}/5)…")
                    time.sleep(wait)
                else:
                    raise

        if response is None:
            raise RuntimeError("GLM API failed after 5 retries")

        try:
            raw = response.choices[0].message.content.strip()

            # 清理 markdown
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            rewritten_texts: list[str] = json.loads(raw)

            if len(rewritten_texts) != len(prompts):
                logger.warning(
                    f"Rewrite count mismatch: expected {len(prompts)}, got {len(rewritten_texts)}"
                )
                # fallback：用原文
                rewritten_texts = base_texts

            return [
                RewriteResult(
                    profile_id=profile.id,
                    prompt_id=prompts[i].id,
                    query_text=rewritten_texts[i],
                )
                for i in range(len(prompts))
            ]

        except Exception as e:
            logger.error(f"Claude rewrite failed for profile {profile.id}: {e}")
            # fallback：直接用原始 prompt 文本
            return [
                RewriteResult(
                    profile_id=profile.id,
                    prompt_id=p.id,
                    query_text=p.text,
                )
                for p in prompts
            ]

    # ── 幂等查询 ──────────────────────────────────────────────────────────────

    async def _get_existing_prompt_ids(
        self,
        db: AsyncSession,
        profile_id: int,
        prompt_ids: list[int],
        any_llm: str,
    ) -> set[int]:
        result = await db.execute(
            select(Query.prompt_id).where(
                Query.profile_id == profile_id,
                Query.prompt_id.in_(prompt_ids),
                Query.target_llm == any_llm,
            )
        )
        return {row[0] for row in result.all()}
