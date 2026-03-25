"""
20个 Segment 的完整定义
前10个：通用 B2B 企业用户
后10个：联蔚集团目标行业（运动/健康/奢侈品/酒水）+ 联蔚直接客户侧
每个 Segment 包含三个生成维度，笛卡尔积 = 100 个 Profile
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

SearchStyle = Literal["solution_oriented", "comparison", "exploratory"]
Tone        = Literal["casual", "semi_formal", "formal"]
Verbosity   = Literal["short", "medium", "long"]


# ─── 城市池（按层级）────────────────────────────────────────────────────────────

CITY_TIERS: dict[str, list[dict]] = {
    "T1_north": [
        {"city": "北京", "country_code": "CN", "timezone": "Asia/Shanghai"},
    ],
    "T1_south": [
        {"city": "上海", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "深圳", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "广州", "country_code": "CN", "timezone": "Asia/Shanghai"},
    ],
    "T2_east": [
        {"city": "杭州", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "南京", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "苏州", "country_code": "CN", "timezone": "Asia/Shanghai"},
    ],
    "T2_west": [
        {"city": "成都", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "重庆", "country_code": "CN", "timezone": "Asia/Chongqing"},
        {"city": "西安", "country_code": "CN", "timezone": "Asia/Shanghai"},
    ],
    "T3_other": [
        {"city": "武汉", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "长沙", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "郑州", "country_code": "CN", "timezone": "Asia/Shanghai"},
        {"city": "合肥", "country_code": "CN", "timezone": "Asia/Shanghai"},
    ],
}

# 海外地区（用于 seg_overseas_chinese）
OVERSEAS_REGIONS: dict[str, list[dict]] = {
    "NA_west": [
        {"city": "San Francisco", "country_code": "US", "timezone": "America/Los_Angeles"},
        {"city": "Seattle",       "country_code": "US", "timezone": "America/Los_Angeles"},
    ],
    "NA_east": [
        {"city": "New York",  "country_code": "US", "timezone": "America/New_York"},
        {"city": "Boston",    "country_code": "US", "timezone": "America/New_York"},
    ],
    "EU": [
        {"city": "London",  "country_code": "GB", "timezone": "Europe/London"},
        {"city": "Berlin",  "country_code": "DE", "timezone": "Europe/Berlin"},
    ],
    "SEA": [
        {"city": "Singapore", "country_code": "SG", "timezone": "Asia/Singapore"},
    ],
    "ANZ": [
        {"city": "Sydney",    "country_code": "AU", "timezone": "Australia/Sydney"},
        {"city": "Melbourne", "country_code": "AU", "timezone": "Australia/Melbourne"},
    ],
}


# ─── 数据类 ──────────────────────────────────────────────────────────────────

@dataclass
class AgeRange:
    label: str
    min_age: int
    max_age: int


@dataclass
class RoleVariant:
    label: str
    profession: str
    company_size: str
    income_level: str
    pain_points: list[str]
    use_buzzwords: bool = True


@dataclass
class SegmentDef:
    id: str
    name: str
    description: str
    language: str                          # zh | en | zh_en
    target_llms: list[str]
    tone_pool: list[Tone]
    verbosity_pool: list[Verbosity]
    search_style_pool: list[SearchStyle]
    add_role_context_rate: float           # 0.0~1.0，在query里暗示身份的概率
    city_tiers: list[str]                  # 从 CITY_TIERS 取，5个
    age_ranges: list[AgeRange]             # 4个年龄段
    role_variants: list[RoleVariant]       # 5个职能细分
    device_mobile_rate: float = 0.6        # 移动端比例


# ─── 10 个 Segment 定义 ───────────────────────────────────────────────────────

SEGMENTS: list[SegmentDef] = [

    # ── 1. 企业决策层 ──────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_enterprise_decision",
        name="企业决策层",
        description="CEO/COO/VP级高管，关注战略价值、ROI、竞争壁垒",
        language="zh",
        target_llms=["chatgpt", "claude", "kimi"],
        tone_pool=["formal", "semi_formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["comparison", "solution_oriented"],
        add_role_context_rate=0.7,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("40s_early",  40, 44),
            AgeRange("40s_late",   45, 49),
            AgeRange("50s_early",  50, 54),
            AgeRange("50s_late",   55, 60),
        ],
        role_variants=[
            RoleVariant("ceo_tech",     "科技公司CEO",      "1000人以上",  "200万+/年",
                        ["数字化转型", "降本增效", "AI战略落地"],          use_buzzwords=True),
            RoleVariant("ceo_mfg",      "制造业CEO",         "500-2000人",  "150万+/年",
                        ["供应链优化", "智能制造", "出海拓展"],             use_buzzwords=True),
            RoleVariant("coo",          "集团COO",           "1000人以上",  "200万+/年",
                        ["流程自动化", "管理效率", "人效提升"],             use_buzzwords=True),
            RoleVariant("vp_strategy",  "战略副总裁",         "500人以上",   "120万+/年",
                        ["市场竞争分析", "新业务拓展", "资源整合"],         use_buzzwords=True),
            RoleVariant("founder",      "创始人/董事长",      "200-1000人",  "100万+/年",
                        ["业务增长", "融资准备", "行业地位"],               use_buzzwords=False),
        ],
        device_mobile_rate=0.4,
    ),

    # ── 2. 中层管理者 ──────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_mid_manager",
        name="中层管理者",
        description="部门总监/经理级，关注落地工具、团队协作、汇报材料",
        language="zh",
        target_llms=["chatgpt", "doubao", "kimi"],
        tone_pool=["semi_formal", "casual"],
        verbosity_pool=["short", "medium"],
        search_style_pool=["solution_oriented", "comparison"],
        add_role_context_rate=0.5,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("late_20s", 27, 30),
            AgeRange("early_30s",31, 34),
            AgeRange("mid_30s",  35, 38),
            AgeRange("early_40s",39, 44),
        ],
        role_variants=[
            RoleVariant("mgr_sales",    "销售总监",    "100-500人",  "40-80万/年",
                        ["客户转化率低", "销售效率", "提案质量"],           use_buzzwords=True),
            RoleVariant("mgr_mkt",      "市场总监",    "100-500人",  "35-70万/年",
                        ["内容产出慢", "品牌声量", "ROI难衡量"],            use_buzzwords=True),
            RoleVariant("mgr_ops",      "运营总监",    "50-300人",   "30-60万/年",
                        ["流程混乱", "数据分散", "人效不足"],               use_buzzwords=True),
            RoleVariant("mgr_hr",       "HR总监",      "200-1000人", "30-50万/年",
                        ["招聘效率", "员工培训", "人才盘点"],               use_buzzwords=False),
            RoleVariant("mgr_finance",  "财务总监",    "100-500人",  "35-60万/年",
                        ["报告准备耗时", "数据准确性", "审计合规"],         use_buzzwords=False),
        ],
        device_mobile_rate=0.6,
    ),

    # ── 3. 技术负责人 ──────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_tech_lead",
        name="技术负责人",
        description="CTO/架构师/技术总监，关注技术栈深度、集成能力、安全合规",
        language="zh",
        target_llms=["chatgpt", "claude", "perplexity"],
        tone_pool=["semi_formal", "casual"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["comparison", "exploratory"],
        add_role_context_rate=0.6,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("late_20s", 27, 30),
            AgeRange("early_30s",31, 34),
            AgeRange("mid_30s",  35, 38),
            AgeRange("early_40s",39, 43),
        ],
        role_variants=[
            RoleVariant("cto",          "CTO",          "100人以上",  "80-200万/年",
                        ["技术选型风险", "团队能力建设", "AI落地"],         use_buzzwords=True),
            RoleVariant("architect",    "系统架构师",   "500人以上",  "60-120万/年",
                        ["系统性能", "可扩展性", "技术债"],                 use_buzzwords=True),
            RoleVariant("ai_engineer",  "AI工程师/负责人","50人以上",  "50-100万/年",
                        ["模型效果", "推理成本", "数据质量"],               use_buzzwords=True),
            RoleVariant("dev_manager",  "研发经理",     "50-300人",   "40-80万/年",
                        ["交付效率", "代码质量", "工具链"],                 use_buzzwords=True),
            RoleVariant("data_lead",    "数据负责人",   "100人以上",  "50-100万/年",
                        ["数据治理", "分析效率", "数据安全"],               use_buzzwords=True),
        ],
        device_mobile_rate=0.35,
    ),

    # ── 4. 中小企业主 ──────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_sme_owner",
        name="中小企业主",
        description="50人以下企业老板，关注性价比、快速上手、实际效果",
        language="zh",
        target_llms=["doubao", "kimi", "zhipu"],
        tone_pool=["casual", "semi_formal"],
        verbosity_pool=["short", "medium"],
        search_style_pool=["solution_oriented", "comparison"],
        add_role_context_rate=0.4,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("30s_early", 30, 34),
            AgeRange("30s_late",  35, 39),
            AgeRange("40s_early", 40, 44),
            AgeRange("40s_late",  45, 50),
        ],
        role_variants=[
            RoleVariant("ecom_owner",   "电商老板",     "10-50人",  "20-80万/年",
                        ["运营成本高", "内容不够", "获客贵"],               use_buzzwords=False),
            RoleVariant("agency_owner", "广告/设计公司老板","5-30人", "15-50万/年",
                        ["产能不足", "客户满意度", "提案速度"],             use_buzzwords=True),
            RoleVariant("trade_owner",  "贸易公司老板",  "10-50人",  "20-60万/年",
                        ["找客户难", "报价效率", "外贸文书"],               use_buzzwords=False),
            RoleVariant("service_owner","本地服务业老板", "5-30人",   "10-40万/年",
                        ["口碑营销", "客户复购", "节省人力"],               use_buzzwords=False),
            RoleVariant("startup_ceo",  "早期创业者",   "5-20人",   "10-30万/年",
                        ["快速验证", "融资材料", "冷启动"],                 use_buzzwords=True),
        ],
        device_mobile_rate=0.75,
    ),

    # ── 5. 职场新人 ────────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_young_professional",
        name="职场新人",
        description="1-3年经验，22-28岁，口语化搜索，追求快速解决方案",
        language="zh",
        target_llms=["doubao", "chatgpt", "kimi"],
        tone_pool=["casual"],
        verbosity_pool=["short", "medium"],
        search_style_pool=["solution_oriented", "exploratory"],
        add_role_context_rate=0.3,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("fresh_grad",  22, 23),
            AgeRange("year_1_2",    24, 25),
            AgeRange("year_2_3",    26, 27),
            AgeRange("year_3_4",    27, 28),
        ],
        role_variants=[
            RoleVariant("jr_mkt",    "初级市场/运营",  "50人以上",  "8-15万/年",
                        ["不知道怎么写文案", "做报告没思路", "想涨薪"],     use_buzzwords=False),
            RoleVariant("jr_sales",  "销售专员",       "50人以上",  "8-20万/年",
                        ["客户跟进话术", "销售方案", "提高成单率"],         use_buzzwords=False),
            RoleVariant("jr_design", "设计/创意",      "20人以上",  "8-15万/年",
                        ["灵感不够", "改稿太多", "效率低"],                 use_buzzwords=False),
            RoleVariant("jr_admin",  "行政/助理",      "100人以上", "6-12万/年",
                        ["会议纪要", "写PPT", "邮件回复"],                  use_buzzwords=False),
            RoleVariant("jr_product","初级产品经理",   "50人以上",  "12-20万/年",
                        ["写PRD没思路", "竞品分析", "需求整理"],            use_buzzwords=True),
        ],
        device_mobile_rate=0.85,
    ),

    # ── 6. 市场/运营从业者 ─────────────────────────────────────────────────────
    SegmentDef(
        id="seg_marketing_ops",
        name="市场/运营从业者",
        description="品牌、内容、增长、私域运营，关注创意效率和数据效果",
        language="zh",
        target_llms=["doubao", "chatgpt", "kimi"],
        tone_pool=["casual", "semi_formal"],
        verbosity_pool=["short", "medium"],
        search_style_pool=["solution_oriented", "comparison"],
        add_role_context_rate=0.55,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("early_career", 24, 27),
            AgeRange("mid_career",   28, 31),
            AgeRange("senior",       32, 36),
            AgeRange("lead",         37, 42),
        ],
        role_variants=[
            RoleVariant("content_creator", "内容运营",    "50人以上",  "10-25万/年",
                        ["每天写不完的内容", "爆款难复制", "选题没灵感"],   use_buzzwords=True),
            RoleVariant("brand_mgr",       "品牌经理",    "100人以上", "15-35万/年",
                        ["品牌声量低", "内容调性统一", "竞品分析"],         use_buzzwords=True),
            RoleVariant("growth_hacker",   "增长运营",    "50人以上",  "15-35万/年",
                        ["获客成本高", "转化率优化", "A/B测试效率"],        use_buzzwords=True),
            RoleVariant("private_domain",  "私域运营",    "20人以上",  "10-20万/年",
                        ["社群活跃度低", "用户留存", "朋友圈内容"],         use_buzzwords=True),
            RoleVariant("pr_specialist",   "公关/媒介",   "100人以上", "12-25万/年",
                        ["稿件质量", "媒体关系", "舆情监测"],               use_buzzwords=False),
        ],
        device_mobile_rate=0.7,
    ),

    # ── 7. 财务/法务专业人士 ───────────────────────────────────────────────────
    SegmentDef(
        id="seg_finance_legal",
        name="财务/法务专业人士",
        description="财务、审计、法务人员，关注合规、精确性、数据安全",
        language="zh",
        target_llms=["claude", "chatgpt", "zhipu"],
        tone_pool=["formal", "semi_formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["solution_oriented", "comparison"],
        add_role_context_rate=0.65,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("junior",  28, 32),
            AgeRange("mid",     33, 37),
            AgeRange("senior",  38, 43),
            AgeRange("partner", 44, 50),
        ],
        role_variants=[
            RoleVariant("cfo",          "CFO/财务总监",  "100人以上", "60-150万/年",
                        ["财报准备效率", "预算分析", "投资人汇报"],         use_buzzwords=True),
            RoleVariant("accountant",   "会计/财务经理", "50人以上",  "15-35万/年",
                        ["报表制作耗时", "数据核对", "税务申报"],           use_buzzwords=False),
            RoleVariant("auditor",      "审计师",        "会计师事务所","20-50万/年",
                        ["底稿整理", "风险识别", "报告撰写"],               use_buzzwords=True),
            RoleVariant("legal_counsel","法务/律师",     "100人以上", "25-80万/年",
                        ["合同审查效率", "法规检索", "风险条款"],           use_buzzwords=True),
            RoleVariant("compliance",   "合规专员",      "200人以上", "20-45万/年",
                        ["政策解读", "合规文档", "监管要求变化"],           use_buzzwords=True),
        ],
        device_mobile_rate=0.4,
    ),

    # ── 8. 海外华人 ────────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_overseas_chinese",
        name="海外华人",
        description="北美/欧洲/东南亚华人，双语，偏西方LLM，关注中西方信息差",
        language="zh_en",
        target_llms=["chatgpt", "claude", "gemini", "perplexity"],
        tone_pool=["casual", "semi_formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["exploratory", "comparison"],
        add_role_context_rate=0.4,
        city_tiers=["NA_west", "NA_east", "EU", "SEA", "ANZ"],
        age_ranges=[
            AgeRange("late_20s",  25, 29),
            AgeRange("early_30s", 30, 34),
            AgeRange("mid_30s",   35, 39),
            AgeRange("early_40s", 40, 45),
        ],
        role_variants=[
            RoleVariant("eng_big_tech",  "大厂软件工程师",  "500人以上", "$12-25万USD/年",
                        ["关注国内AI发展", "技术选型", "副业探索"],         use_buzzwords=True),
            RoleVariant("phd_researcher","博士/研究员",     "高校/研究所","$6-12万USD/年",
                        ["学术写作", "文献综述", "研究效率"],               use_buzzwords=True),
            RoleVariant("fin_analyst",   "金融分析师",      "金融机构",   "$15-30万USD/年",
                        ["中国市场研究", "报告撰写", "数据分析"],           use_buzzwords=True),
            RoleVariant("entrepreneur",  "海外创业者",      "自己创业",   "不定",
                        ["跨境业务", "中美两端资源对接", "产品推广"],       use_buzzwords=False),
            RoleVariant("freelancer",    "自由职业者",      "独立工作",   "$5-15万USD/年",
                        ["提升生产力", "客户沟通", "作品集"],               use_buzzwords=False),
        ],
        device_mobile_rate=0.5,
    ),

    # ── 9. 政府/机构从业者 ─────────────────────────────────────────────────────
    SegmentDef(
        id="seg_gov_institutional",
        name="政府/机构从业者",
        description="国企、事业单位、政府部门，正式语言，重视数据安全和国产化",
        language="zh",
        target_llms=["zhipu", "kimi", "doubao"],
        tone_pool=["formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["solution_oriented", "comparison"],
        add_role_context_rate=0.5,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("junior",   28, 33),
            AgeRange("mid",      34, 39),
            AgeRange("senior",   40, 45),
            AgeRange("director", 46, 55),
        ],
        role_variants=[
            RoleVariant("gov_official",  "政府工作人员",  "政府部门",   "15-30万/年",
                        ["公文写作", "政策解读", "材料准备"],               use_buzzwords=False),
            RoleVariant("soe_manager",   "国企中层管理",  "国有企业",   "20-50万/年",
                        ["汇报材料", "方案撰写", "数字化转型"],             use_buzzwords=True),
            RoleVariant("researcher",    "科研院所研究员","科研机构",   "15-40万/年",
                        ["课题申请", "论文写作", "成果转化"],               use_buzzwords=True),
            RoleVariant("edu_admin",     "高校行政人员",  "高校",       "10-25万/年",
                        ["通知公告", "项目申报", "学生管理"],               use_buzzwords=False),
            RoleVariant("hospital_mgr",  "医院管理人员",  "医疗机构",   "20-50万/年",
                        ["医疗文书", "科室管理", "信息化"],                 use_buzzwords=False),
        ],
        device_mobile_rate=0.5,
    ),

    # ── 10. 跨境/出海业务方 ────────────────────────────────────────────────────
    SegmentDef(
        id="seg_cross_border_biz",
        name="跨境/出海业务方",
        description="做跨境电商或业务出海的企业，中英双语，关注全球市场洞察",
        language="zh_en",
        target_llms=["chatgpt", "gemini", "perplexity", "claude"],
        tone_pool=["casual", "semi_formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["solution_oriented", "exploratory"],
        add_role_context_rate=0.6,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("early_career", 26, 30),
            AgeRange("mid_career",   31, 35),
            AgeRange("senior",       36, 40),
            AgeRange("director",     41, 48),
        ],
        role_variants=[
            RoleVariant("ecom_seller",   "跨境电商卖家",  "10-100人",  "30-200万/年",
                        ["选品研究", "亚马逊listing优化", "竞品分析"],      use_buzzwords=True),
            RoleVariant("brand_oversea", "品牌出海负责人","100人以上",  "40-100万/年",
                        ["海外内容本土化", "媒体投放", "品牌定位"],         use_buzzwords=True),
            RoleVariant("foreign_trade", "外贸业务员",    "20-200人",   "15-40万/年",
                        ["开发信写作", "报价单", "客户沟通"],               use_buzzwords=False),
            RoleVariant("localization",  "本土化/翻译",   "50人以上",   "15-30万/年",
                        ["翻译质量", "文化适配", "多语言内容"],             use_buzzwords=False),
            RoleVariant("global_mkt",    "全球市场经理",  "500人以上",  "50-120万/年",
                        ["市场洞察", "竞争格局", "增长策略"],               use_buzzwords=True),
        ],
        device_mobile_rate=0.6,
    ),
]

# 方便按ID查找

# ═══════════════════════════════════════════════════════════════════════════════
# 后10个 Segment：联蔚目标行业（运动/健康/奢侈品/酒水）+ 联蔚直接客户侧
# ═══════════════════════════════════════════════════════════════════════════════

SEGMENTS += [

    # ── 11. 运动爱好者 ─────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_sports_enthusiast",
        name="运动爱好者",
        description="跑步/健身/户外/球类爱好者，关注装备选购、训练方法、品牌对比",
        language="zh",
        target_llms=["doubao", "chatgpt", "kimi", "perplexity"],
        tone_pool=["casual"],
        verbosity_pool=["short", "medium"],
        search_style_pool=["comparison", "solution_oriented", "exploratory"],
        add_role_context_rate=0.35,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("gen_z",     18, 24),
            AgeRange("millennial",25, 32),
            AgeRange("mid_30s",   33, 39),
            AgeRange("active_40s",40, 48),
        ],
        role_variants=[
            RoleVariant("runner",      "跑步爱好者",   "不限",  "10-30万/年",
                        ["跑鞋选购", "PB提升", "跑步装备性价比"],            use_buzzwords=False),
            RoleVariant("gym_goer",    "健身房常客",   "不限",  "10-25万/年",
                        ["增肌减脂", "训练计划", "运动装备推荐"],            use_buzzwords=False),
            RoleVariant("outdoor",     "户外运动者",   "不限",  "15-40万/年",
                        ["冲锋衣推荐", "装备对比", "徒步/露营攻略"],         use_buzzwords=False),
            RoleVariant("ball_sports", "球类运动者",   "不限",  "10-30万/年",
                        ["球鞋推荐", "装备升级", "专业vs入门"],              use_buzzwords=False),
            RoleVariant("triathlon",   "铁三/马拉松选手","不限", "20-60万/年",
                        ["专业装备", "训练辅助科技", "品牌赞助"],            use_buzzwords=True),
        ],
        device_mobile_rate=0.82,
    ),

    # ── 12. 健康关注者 ─────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_health_conscious",
        name="健康关注者",
        description="关注营养、补剂、体重管理、康复、中高端养生的消费者",
        language="zh",
        target_llms=["doubao", "kimi", "chatgpt", "perplexity"],
        tone_pool=["casual", "semi_formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["solution_oriented", "exploratory", "comparison"],
        add_role_context_rate=0.45,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("gen_z",      20, 26),
            AgeRange("millennial", 27, 34),
            AgeRange("mid_career", 35, 42),
            AgeRange("midlife",    43, 52),
        ],
        role_variants=[
            RoleVariant("weight_mgmt",  "体重管理者",     "不限",  "8-25万/年",
                        ["减肥方法", "代餐选择", "运动饮食配合"],            use_buzzwords=False),
            RoleVariant("supplement",   "补剂/营养品消费者","不限", "15-40万/年",
                        ["蛋白粉品牌对比", "补剂安全性", "性价比"],          use_buzzwords=False),
            RoleVariant("sports_rehab", "运动康复关注者",  "不限",  "15-40万/年",
                        ["伤后恢复", "康复设备", "专业建议"],                use_buzzwords=True),
            RoleVariant("wellness",     "中高端养生人群",  "不限",  "30-100万/年",
                        ["高端保健品", "功能性食品", "抗衰老"],              use_buzzwords=False),
            RoleVariant("parent_child", "亲子健康关注父母","不限",  "20-50万/年",
                        ["儿童营养", "家庭运动", "安全成分"],                use_buzzwords=False),
        ],
        device_mobile_rate=0.78,
    ),

    # ── 13. 奢侈品消费者 ──────────────────────────────────────────────────────
    SegmentDef(
        id="seg_luxury_consumer",
        name="奢侈品消费者",
        description="首购族/成熟买手/二奢玩家，关注品牌价值、保值率、鉴别真伪",
        language="zh",
        target_llms=["chatgpt", "kimi", "doubao", "perplexity"],
        tone_pool=["semi_formal", "casual"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["comparison", "exploratory", "solution_oriented"],
        add_role_context_rate=0.3,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("gen_z_luxury",   20, 26),
            AgeRange("young_affluent", 27, 33),
            AgeRange("mid_affluent",   34, 42),
            AgeRange("mature_buyer",   43, 55),
        ],
        role_variants=[
            RoleVariant("first_buyer",   "奢侈品首购者",  "不限",  "30-80万/年",
                        ["入门款推荐", "买包攻略", "哪个品牌更值"],          use_buzzwords=False),
            RoleVariant("bag_collector", "包包收藏者",    "不限",  "50-200万/年",
                        ["LV vs Chanel保值率", "限量款信息", "二手行情"],    use_buzzwords=True),
            RoleVariant("secondhand",    "二奢买卖玩家",  "不限",  "30-100万/年",
                        ["鉴定技巧", "平台选择", "成色定价"],                use_buzzwords=True),
            RoleVariant("fashion_kol",   "时尚博主/KOL",  "不限",  "20-150万/年",
                        ["新款测评", "穿搭搭配", "品牌合作价值"],            use_buzzwords=True),
            RoleVariant("gift_buyer",    "商务礼品采购",  "企业",  "50-200万/年",
                        ["送礼选择", "定制服务", "预算分配"],                use_buzzwords=False),
        ],
        device_mobile_rate=0.75,
    ),

    # ── 14. 酒水爱好者 ─────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_wine_spirits_drinker",
        name="酒水爱好者",
        description="葡萄酒/白酒收藏/威士忌/精酿消费者，商务宴请及个人收藏场景",
        language="zh",
        target_llms=["chatgpt", "kimi", "doubao", "perplexity"],
        tone_pool=["casual", "semi_formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["exploratory", "comparison", "solution_oriented"],
        add_role_context_rate=0.4,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("young_drinker",  25, 31),
            AgeRange("mid_drinker",    32, 38),
            AgeRange("mature_drinker", 39, 46),
            AgeRange("collector",      47, 58),
        ],
        role_variants=[
            RoleVariant("wine_novice",   "葡萄酒入门者",  "不限",  "20-50万/年",
                        ["红白葡萄酒区别", "入门酒款推荐", "如何品酒"],      use_buzzwords=False),
            RoleVariant("wine_expert",   "葡萄酒爱好者",  "不限",  "50-200万/年",
                        ["年份对比", "酒庄评级", "收藏投资价值"],            use_buzzwords=True),
            RoleVariant("baijiu_fan",    "白酒收藏者",    "不限",  "30-200万/年",
                        ["茅台飞天行情", "老酒鉴别", "收藏建议"],            use_buzzwords=False),
            RoleVariant("whisky_fan",    "威士忌爱好者",  "不限",  "30-100万/年",
                        ["单一麦芽vs调和", "品牌推荐", "入门选购"],          use_buzzwords=True),
            RoleVariant("biz_host",      "商务宴请场景",  "企业",  "50-300万/年",
                        ["商务用酒选择", "预算分配", "档次匹配"],            use_buzzwords=False),
        ],
        device_mobile_rate=0.65,
    ),

    # ── 15. 新富年轻消费者 ────────────────────────────────────────────────────
    SegmentDef(
        id="seg_young_affluent",
        name="新富年轻消费者",
        description="25-35岁消费升级人群，跨运动/健康/奢侈品多品类，重视品质与个性",
        language="zh",
        target_llms=["doubao", "chatgpt", "kimi", "perplexity"],
        tone_pool=["casual"],
        verbosity_pool=["short", "medium"],
        search_style_pool=["comparison", "exploratory"],
        add_role_context_rate=0.25,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("early_25",  25, 27),
            AgeRange("late_20s",  28, 30),
            AgeRange("early_30s", 31, 33),
            AgeRange("mid_30s",   34, 36),
        ],
        role_variants=[
            RoleVariant("internet_worker", "互联网从业者",  "50人以上", "30-100万/年",
                        ["生活品质提升", "消费升级", "好物推荐"],            use_buzzwords=False),
            RoleVariant("finance_young",   "金融从业者",    "50人以上", "40-150万/年",
                        ["高端品牌入手", "理财+消费平衡", "稀缺品"],         use_buzzwords=False),
            RoleVariant("creative",        "创意/设计行业", "不限",     "20-60万/年",
                        ["独特设计款", "小众品牌", "审美提升"],              use_buzzwords=False),
            RoleVariant("influencer",      "博主/内容创作者","不限",    "20-200万/年",
                        ["开箱测评", "品牌故事", "粉丝种草内容"],            use_buzzwords=True),
            RoleVariant("doctor_lawyer",   "医生/律师等专业人士","不限","40-150万/年",
                        ["高端运动装备", "健康产品", "礼品选择"],            use_buzzwords=False),
        ],
        device_mobile_rate=0.88,
    ),

    # ── 16. KOL / 内容创作者 ──────────────────────────────────────────────────
    SegmentDef(
        id="seg_kol_creator",
        name="KOL/内容创作者",
        description="小红书/抖音/B站垂类博主，做运动/健康/奢品/美食酒水测评种草",
        language="zh",
        target_llms=["doubao", "chatgpt", "kimi"],
        tone_pool=["casual"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["exploratory", "comparison"],
        add_role_context_rate=0.5,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("micro_kol_young", 20, 25),
            AgeRange("micro_kol_mid",   26, 30),
            AgeRange("mid_kol",         31, 36),
            AgeRange("top_kol",         37, 42),
        ],
        role_variants=[
            RoleVariant("fitness_kol",  "健身/运动博主",   "不限",  "10-300万/年",
                        ["内容选题", "品牌合作价值", "测评角度"],            use_buzzwords=True),
            RoleVariant("health_kol",   "健康/营养博主",   "不限",  "10-200万/年",
                        ["产品成分解读", "测评公正性", "粉丝信任"],          use_buzzwords=True),
            RoleVariant("luxury_kol",   "奢品/时尚博主",   "不限",  "20-500万/年",
                        ["新款速递", "真假鉴别内容", "穿搭攻略"],            use_buzzwords=True),
            RoleVariant("food_wine_kol","美食/酒水博主",   "不限",  "10-200万/年",
                        ["品鉴内容创作", "酒庄探访", "新品测评"],            use_buzzwords=True),
            RoleVariant("lifestyle_kol","生活方式博主",    "不限",  "10-300万/年",
                        ["跨品类种草", "精致生活内容", "品牌合作筛选"],      use_buzzwords=True),
        ],
        device_mobile_rate=0.90,
    ),

    # ── 17. 品牌市场人员（联蔚直接客户）─────────────────────────────────────
    SegmentDef(
        id="seg_brand_marketer",
        name="品牌市场人员",
        description="运动/健康/奢品/酒水品牌的市场、品牌、数字营销负责人，联蔚的直接使用者",
        language="zh",
        target_llms=["chatgpt", "kimi", "claude", "perplexity"],
        tone_pool=["semi_formal", "formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["solution_oriented", "comparison"],
        add_role_context_rate=0.7,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("junior_mkt",  26, 30),
            AgeRange("mid_mkt",     31, 35),
            AgeRange("senior_mkt",  36, 40),
            AgeRange("director_mkt",41, 48),
        ],
        role_variants=[
            RoleVariant("sports_brand_mkt",  "运动品牌市场经理", "100人以上", "25-60万/年",
                        ["品牌在AI中的可见度", "竞品在LLM里的表现", "GEO策略"],   use_buzzwords=True),
            RoleVariant("health_brand_mkt",  "健康品牌营销负责人","50人以上",  "20-50万/年",
                        ["消费者AI搜索行为", "内容策略", "品牌声量监测"],         use_buzzwords=True),
            RoleVariant("luxury_brand_mkt",  "奢品品牌数字营销",  "100人以上", "35-80万/年",
                        ["高端人群触达", "AI时代品牌叙事", "竞品监测"],           use_buzzwords=True),
            RoleVariant("spirits_brand_mkt", "酒水品牌市场总监",  "50人以上",  "30-80万/年",
                        ["消费者教育内容", "品牌推荐率", "LLM中的品类占位"],      use_buzzwords=True),
            RoleVariant("crm_loyalty_mgr",   "CRM/会员运营经理",  "100人以上", "20-45万/年",
                        ["会员洞察", "个性化运营", "全生命周期管理"],             use_buzzwords=True),
        ],
        device_mobile_rate=0.55,
    ),

    # ── 18. 电商运营 ──────────────────────────────────────────────────────────
    SegmentDef(
        id="seg_ecom_operator",
        name="电商运营",
        description="做品牌天猫/京东/小红书/抖音店铺运营，关注流量、转化、选品",
        language="zh",
        target_llms=["doubao", "chatgpt", "kimi"],
        tone_pool=["casual", "semi_formal"],
        verbosity_pool=["short", "medium"],
        search_style_pool=["solution_oriented", "comparison"],
        add_role_context_rate=0.55,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("fresh",      23, 27),
            AgeRange("mid",        28, 32),
            AgeRange("senior",     33, 37),
            AgeRange("lead",       38, 44),
        ],
        role_variants=[
            RoleVariant("tmall_ops",    "天猫/京东运营",   "50人以上",  "15-35万/年",
                        ["店铺流量下滑", "大促备货", "竞品价格监控"],        use_buzzwords=True),
            RoleVariant("douyin_ops",   "抖音电商运营",    "20人以上",  "12-30万/年",
                        ["达人选品", "直播脚本", "爆款复制"],                use_buzzwords=True),
            RoleVariant("xiaohongshu",  "小红书运营",      "10人以上",  "10-25万/年",
                        ["笔记种草", "KOC合作", "搜索SEO"],                  use_buzzwords=True),
            RoleVariant("private_ops",  "私域/会员运营",   "50人以上",  "12-28万/年",
                        ["会员活跃度", "复购提升", "社群运营"],              use_buzzwords=True),
            RoleVariant("data_ops",     "电商数据分析",    "50人以上",  "15-35万/年",
                        ["转化漏斗", "用户画像", "竞品监测数据"],            use_buzzwords=True),
        ],
        device_mobile_rate=0.72,
    ),

    # ── 19. 零售采购/买手 ─────────────────────────────────────────────────────
    SegmentDef(
        id="seg_retail_buyer",
        name="零售采购/买手",
        description="品牌零售店、买手店、百货采购，关注选品趋势、品牌资质、供货条件",
        language="zh",
        target_llms=["chatgpt", "kimi", "perplexity"],
        tone_pool=["semi_formal", "formal"],
        verbosity_pool=["medium", "long"],
        search_style_pool=["comparison", "solution_oriented"],
        add_role_context_rate=0.6,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("junior",  25, 30),
            AgeRange("mid",     31, 36),
            AgeRange("senior",  37, 42),
            AgeRange("director",43, 50),
        ],
        role_variants=[
            RoleVariant("sports_buyer",   "运动品类买手",   "百货/连锁", "20-50万/年",
                        ["品牌趋势判断", "新品引入", "库存周转"],            use_buzzwords=True),
            RoleVariant("health_buyer",   "健康/营养品采购","药店/商超", "15-40万/年",
                        ["品牌资质审核", "市场需求判断", "供货稳定性"],      use_buzzwords=True),
            RoleVariant("luxury_buyer",   "奢品买手",       "买手店",    "30-100万/年",
                        ["品牌组合策略", "小众品牌发掘", "客群匹配"],        use_buzzwords=True),
            RoleVariant("wine_buyer",     "酒水采购经理",   "餐饮/零售", "20-60万/年",
                        ["酒单搭配", "性价比评估", "新品引入"],              use_buzzwords=True),
            RoleVariant("dept_buyer",     "百货综合采购",   "百货公司",  "20-50万/年",
                        ["品类结构优化", "品牌引入谈判", "消费者趋势"],      use_buzzwords=True),
        ],
        device_mobile_rate=0.5,
    ),

    # ── 20. 行业研究/咨询分析师 ───────────────────────────────────────────────
    SegmentDef(
        id="seg_industry_analyst",
        name="行业研究/咨询分析师",
        description="消费品/零售/健康行业研究员、咨询顾问，关注市场洞察与竞争格局",
        language="zh_en",
        target_llms=["chatgpt", "perplexity", "claude", "gemini"],
        tone_pool=["semi_formal", "formal"],
        verbosity_pool=["long", "medium"],
        search_style_pool=["exploratory", "comparison"],
        add_role_context_rate=0.65,
        city_tiers=["T1_north", "T1_south", "T2_east", "T2_west", "T3_other"],
        age_ranges=[
            AgeRange("junior",   24, 28),
            AgeRange("mid",      29, 33),
            AgeRange("senior",   34, 39),
            AgeRange("partner",  40, 48),
        ],
        role_variants=[
            RoleVariant("consumer_analyst",  "消费品行业研究员",  "券商/咨询",  "25-80万/年",
                        ["品牌竞争格局", "消费趋势洞察", "市场份额"],        use_buzzwords=True),
            RoleVariant("sports_consultant", "运动健康咨询顾问",  "咨询公司",  "30-100万/年",
                        ["行业报告", "品牌战略建议", "市场进入研究"],        use_buzzwords=True),
            RoleVariant("luxury_researcher", "奢侈品市场研究员",  "研究机构",  "20-60万/年",
                        ["消费者行为研究", "品牌价值分析", "渠道趋势"],      use_buzzwords=True),
            RoleVariant("vc_analyst",        "消费赛道投资分析师","VC/PE",     "30-120万/年",
                        ["赛道研究", "品牌估值逻辑", "竞品对标"],            use_buzzwords=True),
            RoleVariant("brand_strategist",  "品牌战略顾问",      "品牌咨询",  "35-100万/年",
                        ["品牌定位诊断", "AI时代品牌策略", "竞争壁垒"],      use_buzzwords=True),
        ],
        device_mobile_rate=0.42,
    ),
]


SEGMENT_MAP: dict[str, SegmentDef] = {s.id: s for s in SEGMENTS}
