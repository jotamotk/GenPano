"""
Profile 生成器
- 基于 Segment 定义，通过笛卡尔积 × 随机属性生成 100 个 Profile/Segment
- 姓名、年龄在范围内随机生成
- 一次性写入 DB，后续可复现对比
"""
from __future__ import annotations

import hashlib
import random
from itertools import product
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import BrowserProfile, Profile
from geo_tracker.generation.segments.definitions import (
    CITY_TIERS, OVERSEAS_REGIONS, SEGMENTS, SegmentDef, AgeRange, RoleVariant,
)

# ─── 中文姓名库 ───────────────────────────────────────────────────────────────

SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
    "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
    "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕",
]

GIVEN_NAMES_MALE = [
    "伟", "芳", "磊", "洋", "勇", "艳", "杰", "娟", "涛", "明",
    "静", "强", "军", "霞", "平", "燕", "辉", "龙", "亮", "超",
    "浩", "晨", "宇", "文", "博", "志", "鑫", "峰", "凯", "云",
    "思远", "子豪", "嘉豪", "浩然", "宇轩", "晓东", "建国", "永强",
]

GIVEN_NAMES_FEMALE = [
    "芳", "娟", "艳", "静", "霞", "燕", "丽", "敏", "雪", "玲",
    "婷", "慧", "洁", "萍", "美", "英", "珍", "华", "云", "梅",
    "晓雪", "雨欣", "思琪", "佳颖", "雅婷", "梦琪", "紫薇", "若曦",
]

ENGLISH_FIRST_NAMES = [
    "Wei", "Fang", "Lei", "Yang", "Yong", "Jie", "Tao", "Ming",
    "Hao", "Chen", "Lin", "Kai", "Zhi", "Bo", "Jun", "Hui",
    "Alice", "Bob", "Chris", "Diana", "Eric", "Fiona", "Grace",
]

ENGLISH_LAST_NAMES = [
    "Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Zhao", "Huang",
    "Zhou", "Wu", "Xu", "Sun", "Ma", "Lin", "Gao",
]

# UA 池（真实浏览器UA）
USER_AGENTS = {
    "windows_chrome": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    ],
    "mac_chrome": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ],
    "mac_safari": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    ],
    "ios_safari": [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    ],
    "android_chrome": [
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    ],
}

WEBGL_VENDORS = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Google Inc. (AMD)",    "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ("Apple",                "Apple GPU"),
    ("Google Inc. (Intel)",  "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
]


# ─── 随机工具 ─────────────────────────────────────────────────────────────────

def _random_chinese_name(gender: str) -> str:
    surname = random.choice(SURNAMES)
    given   = random.choice(GIVEN_NAMES_MALE if gender == "male" else GIVEN_NAMES_FEMALE)
    return surname + given


def _random_english_name() -> str:
    return f"{random.choice(ENGLISH_FIRST_NAMES)} {random.choice(ENGLISH_LAST_NAMES)}"


def _random_age(age_range: AgeRange) -> int:
    return random.randint(age_range.min_age, age_range.max_age)


def _random_gender(segment: SegmentDef) -> str:
    # 技术岗偏男性，市场运营偏女性，其余均衡
    male_rate = {
        # B2B 通用
        "seg_tech_lead":             0.80,
        "seg_enterprise_decision":   0.70,
        "seg_mid_manager":           0.55,
        "seg_marketing_ops":         0.40,
        "seg_young_professional":    0.50,
        "seg_finance_legal":         0.45,
        "seg_sme_owner":             0.65,
        "seg_overseas_chinese":      0.60,
        "seg_gov_institutional":     0.55,
        "seg_cross_border_biz":      0.55,
        # 联蔚目标行业
        "seg_sports_enthusiast":     0.65,
        "seg_health_conscious":      0.40,
        "seg_luxury_consumer":       0.30,   # 奢品消费以女性为主
        "seg_wine_spirits_drinker":  0.65,
        "seg_young_affluent":        0.50,
        "seg_kol_creator":           0.35,   # KOL 女性偏多
        "seg_brand_marketer":        0.45,
        "seg_ecom_operator":         0.48,
        "seg_retail_buyer":          0.40,
        "seg_industry_analyst":      0.60,
    }.get(segment.id, 0.5)
    return "male" if random.random() < male_rate else "female"


def _build_browser_profile(
    segment: SegmentDef,
    city_info: dict,
    device_type: str,
    language: str,
) -> dict:
    is_mobile = (device_type == "mobile")
    country   = city_info["country_code"]

    if is_mobile:
        ua_key = "ios_safari" if random.random() < 0.5 else "android_chrome"
        platform = "iPhone" if ua_key == "ios_safari" else "Linux armv8l"
        vp = random.choice([(390, 844), (393, 852), (412, 915), (360, 800)])
    else:
        if country in ("US", "GB", "DE", "AU", "SG"):
            ua_key = random.choice(["mac_chrome", "mac_safari", "windows_chrome"])
        else:
            ua_key = random.choice(["windows_chrome", "mac_chrome"])
        platform = "MacIntel" if "mac" in ua_key else "Win32"
        vp = random.choice([(1920, 1080), (1440, 900), (1366, 768), (2560, 1440)])

    webgl_vendor, webgl_renderer = random.choice(WEBGL_VENDORS)

    # 语言格式化
    lang_map = {
        "zh":    "zh-CN",
        "en":    "en-US",
        "zh_en": random.choice(["zh-CN", "en-US"]),
    }

    return dict(
        user_agent=random.choice(USER_AGENTS[ua_key]),
        viewport_width=vp[0],
        viewport_height=vp[1],
        timezone=city_info["timezone"],
        language=lang_map.get(language, "zh-CN"),
        platform=platform,
        webgl_vendor=f"{webgl_vendor}|{webgl_renderer}",
        canvas_noise_seed=random.randint(1_000, 9_999_999),
        fonts=_random_font_list(platform),
    )


def _random_font_list(platform: str) -> list[str]:
    base = ["Arial", "Helvetica", "Times New Roman", "Courier New"]
    if "Win" in platform:
        extra = ["Microsoft YaHei", "SimSun", "SimHei", "KaiTi", "FangSong",
                 "Calibri", "Segoe UI", "Consolas", "Verdana"]
    elif "Mac" in platform or "iPhone" in platform:
        extra = ["PingFang SC", "Hiragino Sans GB", "STHeiti", "STSong",
                 "Helvetica Neue", "SF Pro Display", "Menlo"]
    else:
        extra = ["Noto Sans CJK SC", "WenQuanYi Micro Hei", "Ubuntu", "DejaVu Sans"]
    random.shuffle(extra)
    return base + extra[:random.randint(4, 8)]


def _stable_seed(segment_id: str, tier: str, age_label: str, role_label: str) -> int:
    """根据组合key生成稳定种子，保证相同组合始终生成相同的随机属性"""
    key = f"{segment_id}|{tier}|{age_label}|{role_label}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % (2 ** 31)


# ─── 主生成器 ─────────────────────────────────────────────────────────────────

class ProfileGenerator:

    @staticmethod
    async def generate_all(db: AsyncSession) -> int:
        """生成全部 10 × 100 = 1000 个 Profile 并写入 DB（幂等：已存在则跳过）"""
        total = 0
        for segment in SEGMENTS:
            count = await ProfileGenerator.generate_segment(db, segment)
            total += count
        return total

    @staticmethod
    async def generate_segment(db: AsyncSession, segment: SegmentDef) -> int:
        """生成单个 Segment 的 100 个 Profile"""
        # 选城市池
        city_pool_map = OVERSEAS_REGIONS if segment.id == "seg_overseas_chinese" else CITY_TIERS

        created = 0
        for tier_key, age_range, role_variant in product(
            segment.city_tiers,
            segment.age_ranges,
            segment.role_variants,
        ):
            seed = _stable_seed(segment.id, tier_key, age_range.label, role_variant.label)
            rng  = random.Random(seed)

            city_options = city_pool_map.get(tier_key, [])
            if not city_options:
                continue
            city_info = rng.choice(city_options)

            gender      = _random_gender_with_rng(segment, rng)
            age         = rng.randint(age_range.min_age, age_range.max_age)
            device_type = "mobile" if rng.random() < segment.device_mobile_rate else "desktop"

            # 双语 segment 随机决定本次 query 用中文还是英文
            lang = segment.language
            if lang == "zh_en":
                lang = rng.choice(["zh", "en"])

            name = (
                _random_english_name_with_rng(rng)
                if city_info["country_code"] != "CN" and lang == "en"
                else _random_chinese_name_with_rng(gender, rng)
            )

            # persona traits 随机抽取
            persona_traits = {
                "tone":             rng.choice(segment.tone_pool),
                "verbosity":        rng.choice(segment.verbosity_pool),
                "search_style":     rng.choice(segment.search_style_pool),
                "add_role_context": rng.random() < segment.add_role_context_rate,
                "use_buzzwords":    role_variant.use_buzzwords and rng.random() < 0.7,
                "pain_points":      rng.sample(
                    role_variant.pain_points,
                    k=min(2, len(role_variant.pain_points))
                ),
            }

            profile = Profile(
                name=name,
                age_range=f"{age_range.min_age}-{age_range.max_age}",
                location=city_info["city"],
                country_code=city_info["country_code"],
                profession=role_variant.profession,
                language=lang,
                device_type=device_type,
                persona_traits={
                    **persona_traits,
                    "segment_id":   segment.id,
                    "segment_name": segment.name,
                    "company_size": role_variant.company_size,
                    "income_level": role_variant.income_level,
                    "age":          age,
                    "gender":       gender,
                    "target_llms":  segment.target_llms,
                    "tier_key":     tier_key,
                },
            )
            db.add(profile)
            await db.flush()   # 获取 profile.id

            # 同步创建 BrowserProfile
            bp_data = _build_browser_profile(segment, city_info, device_type, lang)
            bp = BrowserProfile(profile_id=profile.id, **bp_data)
            db.add(bp)

            created += 1

        await db.commit()
        return created


# ─── 带 rng 的工具函数 ────────────────────────────────────────────────────────

def _random_gender_with_rng(segment: SegmentDef, rng: random.Random) -> str:
    male_rate = {
        # B2B 通用
        "seg_tech_lead":             0.80,
        "seg_enterprise_decision":   0.70,
        "seg_mid_manager":           0.55,
        "seg_marketing_ops":         0.40,
        "seg_young_professional":    0.50,
        "seg_finance_legal":         0.45,
        "seg_sme_owner":             0.65,
        "seg_overseas_chinese":      0.60,
        "seg_gov_institutional":     0.55,
        "seg_cross_border_biz":      0.55,
        # 联蔚目标行业
        "seg_sports_enthusiast":     0.65,
        "seg_health_conscious":      0.40,
        "seg_luxury_consumer":       0.30,
        "seg_wine_spirits_drinker":  0.65,
        "seg_young_affluent":        0.50,
        "seg_kol_creator":           0.35,
        "seg_brand_marketer":        0.45,
        "seg_ecom_operator":         0.48,
        "seg_retail_buyer":          0.40,
        "seg_industry_analyst":      0.60,
    }.get(segment.id, 0.5)
    return "male" if rng.random() < male_rate else "female"


def _random_chinese_name_with_rng(gender: str, rng: random.Random) -> str:
    surname = rng.choice(SURNAMES)
    given   = rng.choice(GIVEN_NAMES_MALE if gender == "male" else GIVEN_NAMES_FEMALE)
    return surname + given


def _random_english_name_with_rng(rng: random.Random) -> str:
    return f"{rng.choice(ENGLISH_FIRST_NAMES)} {rng.choice(ENGLISH_LAST_NAMES)}"
