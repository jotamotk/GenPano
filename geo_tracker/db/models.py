from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, JSON, Text,
    ForeignKey, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
import enum


class Base(DeclarativeBase):
    pass


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    BANNED = "banned"


class QueryStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ProxyType(str, enum.Enum):
    RESIDENTIAL = "residential"
    DATACENTER = "datacenter"
    MOBILE = "mobile"


# ─── Brand ────────────────────────────────────────────────────────────────────

class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class PromptIntent(str, enum.Enum):
    BRAND = "brand"
    NON_BRAND = "non_brand"
    COMPARISON = "comparison"


# ─── Brand ────────────────────────────────────────────────────────────────────

class Brand(Base):
    __tablename__ = "brands"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(256), nullable=False)
    website      = Column(String(512))
    industry     = Column(String(128))
    description  = Column(Text)
    target_market = Column(String(128), default="中国大陆")
    aliases      = Column(JSON, nullable=True)
    created_at   = Column(DateTime, server_default=func.now())

    topics      = relationship("Topic",      back_populates="brand", cascade="all, delete-orphan")
    competitors = relationship("Competitor", back_populates="brand", cascade="all, delete-orphan")
    queries     = relationship("Query",      back_populates="brand")


# ─── Topic ────────────────────────────────────────────────────────────────────

class Topic(Base):
    __tablename__ = "topics"

    id           = Column(Integer, primary_key=True)
    brand_id     = Column(Integer, ForeignKey("brands.id"), nullable=False)
    text         = Column(String(256), nullable=False)
    category     = Column(String(64))   # awareness|comparison|recommendation|problem_solving
    generated_by = Column(String(64))   # claude-opus-4-6
    status       = Column(String(16), default="active")  # active|archived
    created_at   = Column(DateTime, server_default=func.now())

    brand   = relationship("Brand",  back_populates="topics")
    prompts = relationship("Prompt", back_populates="topic", cascade="all, delete-orphan")


# ─── Prompt ───────────────────────────────────────────────────────────────────

class Prompt(Base):
    __tablename__ = "prompts"

    id           = Column(Integer, primary_key=True)
    topic_id     = Column(Integer, ForeignKey("topics.id"), nullable=False)
    text         = Column(Text, nullable=False)
    intent       = Column(String(64))   # brand|non_brand|comparison
    language     = Column(String(8), default="zh")   # zh | en
    tags         = Column(JSON, nullable=True)   # ["list", "scenario", "negative", "review"]
    created_at   = Column(DateTime, server_default=func.now())

    topic   = relationship("Topic", back_populates="prompts")
    queries = relationship("Query", back_populates="prompt")


# ─── Competitor ───────────────────────────────────────────────────────────────

class Competitor(Base):
    __tablename__ = "competitors"

    id               = Column(Integer, primary_key=True)
    brand_id         = Column(Integer, ForeignKey("brands.id"), nullable=False)
    name             = Column(String(256), nullable=False)
    website          = Column(String(512))
    aliases          = Column(JSON, nullable=True)
    source           = Column(String(32), default="auto_generated")  # auto_generated|manual
    confidence_score = Column(Float, default=0.8)
    created_at       = Column(DateTime, server_default=func.now())

    brand = relationship("Brand", back_populates="competitors")

    __table_args__ = (UniqueConstraint("brand_id", "name", name="uq_competitor_brand_name"),)


# ─── Proxy ────────────────────────────────────────────────────────────────────

class Proxy(Base):
    __tablename__ = "proxies"

    id             = Column(Integer, primary_key=True)
    provider       = Column(String(64))                        # brightdata | oxylabs
    proxy_url      = Column(String(256), unique=True)          # http://user:pass@host:port
    type           = Column(String(16))
    country        = Column(String(8))
    city           = Column(String(64), nullable=True)
    last_used_at   = Column(DateTime, nullable=True)
    success_count  = Column(Integer, default=0)
    fail_count     = Column(Integer, default=0)
    is_banned      = Column(Boolean, default=False)
    cooldown_until = Column(DateTime, nullable=True)

    accounts       = relationship("LLMAccount", back_populates="proxy")

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total else 0.0


# ─── Browser Profile ──────────────────────────────────────────────────────────

class BrowserProfile(Base):
    __tablename__ = "browser_profiles"

    id                    = Column(Integer, primary_key=True)
    profile_id            = Column(Integer, ForeignKey("profiles.id"))
    user_agent            = Column(String(512))
    viewport_width        = Column(Integer, default=1920)
    viewport_height       = Column(Integer, default=1080)
    timezone              = Column(String(64))                 # Asia/Shanghai
    language              = Column(String(16))                 # zh-CN
    platform              = Column(String(32))                 # Win32 | MacIntel
    webgl_vendor          = Column(String(128))
    canvas_noise_seed     = Column(Integer)
    fonts                 = Column(JSON)                       # list of font names
    persistent_context_dir = Column(String(512), nullable=True)  # 存cookies目录

    profile               = relationship("Profile", back_populates="browser_profile")


# ─── Profile ──────────────────────────────────────────────────────────────────

class Profile(Base):
    __tablename__ = "profiles"

    id              = Column(Integer, primary_key=True)
    name            = Column(String(128))
    age_range       = Column(String(16))       # 25-34
    location        = Column(String(64))       # Shanghai, CN
    country_code    = Column(String(8))        # CN | US | GB
    profession      = Column(String(64))
    language        = Column(String(16))       # zh | en
    device_type     = Column(String(16))       # mobile | desktop
    persona_traits  = Column(JSON)             # {"tone": "casual", "verbosity": "short"}

    browser_profile = relationship("BrowserProfile", back_populates="profile", uselist=False)
    accounts        = relationship("LLMAccount", back_populates="profile")
    queries         = relationship("Query", back_populates="profile")


# ─── LLM Account ──────────────────────────────────────────────────────────────

class LLMAccount(Base):
    __tablename__ = "llm_accounts"

    id                  = Column(Integer, primary_key=True)
    llm_name            = Column(String(64))           # chatgpt | gemini | claude | ...
    email               = Column(String(256))
    password_encrypted  = Column(String(512))
    phone_number        = Column(String(32), nullable=True)
    cookies_json        = Column(Text, nullable=True)  # 序列化的登录态cookies
    last_used_at        = Column(DateTime, nullable=True)
    query_count_today   = Column(Integer, default=0)
    daily_limit         = Column(Integer, default=20)
    status              = Column(String(16), default=AccountStatus.ACTIVE.value)
    cooldown_until      = Column(DateTime, nullable=True)
    consecutive_fails   = Column(Integer, default=0)
    created_at          = Column(DateTime, server_default=func.now())
    cookies_updated_at  = Column(DateTime, nullable=True)  # cookies最后更新/验证时间

    proxy_id            = Column(Integer, ForeignKey("proxies.id"), nullable=True)
    profile_id          = Column(Integer, ForeignKey("profiles.id"), nullable=True)

    proxy               = relationship("Proxy", back_populates="accounts")
    profile             = relationship("Profile", back_populates="accounts")
    rotation_logs       = relationship("AccountRotationLog", back_populates="account")
    profile_bindings    = relationship("AccountProfileMap", back_populates="account",
                                       cascade="all, delete-orphan")


# ─── Account ↔ Profile (many-to-many with per-binding daily quota) ───────────
# A single LLM account may serve dozens of Profiles. The legacy
# llm_accounts.profile_id stays as the "primary" profile for backward compat;
# this table is the additive layer the Scheduler reads to know how many queries
# each (account, profile) pair should run per day.
class AccountProfileMap(Base):
    __tablename__ = "account_profile_map"

    id                    = Column(Integer, primary_key=True)
    account_id            = Column(Integer, ForeignKey("llm_accounts.id", ondelete="CASCADE"),
                                   nullable=False)
    # profiles.id in production is VARCHAR(64) ('pf_xxxx'); we don't enforce
    # the FK here so the ORM stays compatible with both schemas (legacy int +
    # current string). Referential integrity is enforced in the DB DDL.
    profile_id            = Column(String(64), nullable=False)
    daily_quota           = Column(Integer, default=1, nullable=False)
    conflict_acknowledged = Column(Boolean, default=False)
    created_at            = Column(DateTime, server_default=func.now())

    account               = relationship("LLMAccount", back_populates="profile_bindings")

    __table_args__ = (
        UniqueConstraint("account_id", "profile_id", name="uq_apm_account_profile"),
    )


# ─── Scheduler Config (single row) ───────────────────────────────────────────
class SchedulerConfig(Base):
    __tablename__ = "scheduler_config"

    id               = Column(Integer, primary_key=True)
    mode             = Column(String(16), default="auto")    # auto | manual | paused
    daily_time       = Column(String(8),  default="09:00")   # HH:MM
    timezone         = Column(String(64), default="Asia/Shanghai")
    temp_global_cap  = Column(Integer, nullable=True)        # null = disabled
    engine_caps      = Column(JSON, nullable=True)           # {"doubao":50, ...}; null/missing per engine = no cap
    retry_max        = Column(Integer, default=3)
    paused_engines   = Column(JSON, nullable=True)           # ["chatgpt", ...]
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── Scheduler Run History ───────────────────────────────────────────────────
class SchedulerRun(Base):
    __tablename__ = "scheduler_runs"

    id              = Column(Integer, primary_key=True)
    started_at      = Column(DateTime, server_default=func.now())
    finished_at     = Column(DateTime, nullable=True)
    mode            = Column(String(16))                     # auto | manual
    target_total    = Column(Integer, default=0)
    queries_created = Column(Integer, default=0)
    note            = Column(Text, nullable=True)


class AccountRotationLog(Base):
    __tablename__ = "account_rotation_logs"

    id          = Column(Integer, primary_key=True)
    account_id  = Column(Integer, ForeignKey("llm_accounts.id"))
    rotated_at  = Column(DateTime, server_default=func.now())
    reason      = Column(String(64))    # rate_limit | ban | scheduled | captcha_fail

    account     = relationship("LLMAccount", back_populates="rotation_logs")


# ─── Query & Response ─────────────────────────────────────────────────────────

class Query(Base):
    __tablename__ = "queries"

    id           = Column(Integer, primary_key=True)
    prompt_id    = Column(Integer, ForeignKey("prompts.id"))
    profile_id   = Column(Integer, ForeignKey("profiles.id"))
    brand_id     = Column(Integer, ForeignKey("brands.id"))
    account_id   = Column(Integer, ForeignKey("llm_accounts.id"), nullable=True)  # 执行时分配的账号
    query_text   = Column(Text)
    target_llm   = Column(String(64))
    status       = Column(String(16), default=QueryStatus.PENDING.value)
    retry_count  = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=True)
    executed_at  = Column(DateTime, nullable=True)
    created_at   = Column(DateTime, server_default=func.now())

    profile      = relationship("Profile",    back_populates="queries")
    prompt       = relationship("Prompt",     back_populates="queries")
    brand        = relationship("Brand",      back_populates="queries")
    account      = relationship("LLMAccount")
    response     = relationship("LLMResponse", back_populates="query", uselist=False)


class LLMResponse(Base):
    __tablename__ = "llm_responses"

    id               = Column(Integer, primary_key=True)
    query_id         = Column(Integer, ForeignKey("queries.id"), unique=True)
    raw_text         = Column(Text)
    response_html    = Column(Text, nullable=True)    # 响应区域原始 HTML（保留 <a href> 等标签）
    citations_json   = Column(JSON, nullable=True)   # [{url, title, index}]
    response_time_ms = Column(Integer)
    screenshot_path  = Column(String(512), nullable=True)
    collected_at     = Column(DateTime, server_default=func.now())
    llm_version      = Column(String(64), nullable=True)   # gpt-4o | gemini-1.5-pro
    analysis_status  = Column(String(16), default=AnalysisStatus.PENDING.value)
    analyzed_at      = Column(DateTime, nullable=True)

    query            = relationship("Query", back_populates="response")
    mentions         = relationship("BrandMention", back_populates="response",
                                    cascade="all, delete-orphan")
    citation_details = relationship("CitationSource", back_populates="response",
                                    cascade="all, delete-orphan")


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis Layer Models
# ═══════════════════════════════════════════════════════════════════════════════

# ─── BrandMention ─────────────────────────────────────────────────────────────

class BrandMention(Base):
    __tablename__ = "brand_mentions"

    id              = Column(Integer, primary_key=True)
    response_id     = Column(Integer, ForeignKey("llm_responses.id"), nullable=False)
    brand_id        = Column(Integer, ForeignKey("brands.id"), nullable=True)
    brand_name      = Column(String(256), nullable=False)
    product_name    = Column(String(256), nullable=True)
    is_target       = Column(Boolean, default=False)

    position_type   = Column(String(32))
    position_rank   = Column(Integer, nullable=True)
    detail_level    = Column(String(16))

    sentiment       = Column(String(16))
    sentiment_score = Column(Float)

    context_snippet = Column(Text)
    mention_count   = Column(Integer, default=1)

    created_at      = Column(DateTime, server_default=func.now())

    response        = relationship("LLMResponse", back_populates="mentions")
    brand           = relationship("Brand")
    drivers         = relationship("SentimentDriver", back_populates="mention",
                                   cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint(
            "response_id", "brand_name", "product_name",
            name="uq_mention_response_brand_product",
        ),
    )


# ─── SentimentDriver ─────────────────────────────────────────────────────────

class SentimentDriver(Base):
    __tablename__ = "sentiment_drivers"

    id            = Column(Integer, primary_key=True)
    mention_id    = Column(Integer, ForeignKey("brand_mentions.id"), nullable=False)
    response_id   = Column(Integer, ForeignKey("llm_responses.id"), nullable=False)
    brand_name    = Column(String(256), nullable=False)

    driver_text   = Column(String(512), nullable=False)
    polarity      = Column(String(8), nullable=False)
    category      = Column(String(64))
    strength      = Column(Float, default=0.5)
    source_quote  = Column(Text, nullable=True)

    created_at    = Column(DateTime, server_default=func.now())

    mention       = relationship("BrandMention", back_populates="drivers")
    response      = relationship("LLMResponse")


# ─── CitationSource ───────────────────────────────────────────────────────────

class CitationSource(Base):
    __tablename__ = "citation_sources"

    id             = Column(Integer, primary_key=True)
    response_id    = Column(Integer, ForeignKey("llm_responses.id"), nullable=False)
    mention_id     = Column(Integer, ForeignKey("brand_mentions.id"), nullable=True)
    url            = Column(String(2048), nullable=False)
    domain         = Column(String(256))
    title          = Column(String(512))
    citation_index = Column(Integer)
    source_type    = Column(String(32))
    created_at     = Column(DateTime, server_default=func.now())

    response       = relationship("LLMResponse", back_populates="citation_details")
    mention        = relationship("BrandMention")


# ─── ResponseAnalysis ─────────────────────────────────────────────────────────

class ResponseAnalysis(Base):
    __tablename__ = "response_analyses"

    id                     = Column(Integer, primary_key=True)
    response_id            = Column(Integer, ForeignKey("llm_responses.id"), unique=True)

    dimension_industry     = Column(String(128))
    dimension_company      = Column(String(128))
    dimension_product      = Column(String(128))
    dimension_category     = Column(String(128))

    total_brands_mentioned = Column(Integer, default=0)
    target_brand_mentioned = Column(Boolean, default=False)
    target_brand_position  = Column(String(32), nullable=True)
    target_brand_rank      = Column(Integer, nullable=True)
    target_brand_sentiment = Column(String(16), nullable=True)
    target_brand_detail    = Column(String(16), nullable=True)

    visibility_score       = Column(Float, default=0.0)
    sentiment_score        = Column(Float, default=0.0)
    sov_score              = Column(Float, default=0.0)
    citation_score         = Column(Float, default=0.0)

    geo_score              = Column(Float, default=0.0)

    analyzed_at            = Column(DateTime, server_default=func.now())
    analyzer_model         = Column(String(64))
    raw_analysis_json      = Column(JSON, nullable=True)

    response               = relationship("LLMResponse", backref="analysis")
    feature_mentions       = relationship("ProductFeatureMention",
                                          back_populates="analysis",
                                          cascade="all, delete-orphan")


# ─── ProductFeatureMention ────────────────────────────────────────────────────

class ProductFeatureMention(Base):
    __tablename__ = "product_feature_mentions"

    id                = Column(Integer, primary_key=True)
    analysis_id       = Column(Integer, ForeignKey("response_analyses.id"), nullable=False)
    brand_name        = Column(String(256), nullable=False)
    product_name      = Column(String(256), nullable=False)

    feature_name      = Column(String(128), nullable=False)
    feature_sentiment = Column(String(16), nullable=True)
    context_snippet   = Column(Text, nullable=True)

    scenario          = Column(String(128), nullable=True)
    price_positioning = Column(String(32), nullable=True)

    created_at        = Column(DateTime, server_default=func.now())

    analysis          = relationship("ResponseAnalysis", back_populates="feature_mentions")


# ─── GEOScoreDaily ────────────────────────────────────────────────────────────

class GEOScoreDaily(Base):
    __tablename__ = "geo_score_daily"

    id             = Column(Integer, primary_key=True)
    brand_id       = Column(Integer, ForeignKey("brands.id"), nullable=False)
    date           = Column(DateTime, nullable=False)
    target_llm     = Column(String(64), nullable=True)
    intent         = Column(String(64), nullable=True)
    language       = Column(String(8), nullable=True)

    total_queries       = Column(Integer, default=0)
    mention_count       = Column(Integer, default=0)
    mention_rate        = Column(Float, default=0.0)
    avg_position_rank   = Column(Float, nullable=True)
    first_place_count   = Column(Integer, default=0)
    first_place_rate    = Column(Float, default=0.0)
    positive_rate       = Column(Float, default=0.0)
    negative_rate       = Column(Float, default=0.0)
    avg_sentiment_score = Column(Float, default=0.0)
    citation_rate       = Column(Float, default=0.0)
    avg_sov             = Column(Float, default=0.0)

    avg_visibility      = Column(Float, default=0.0)
    avg_sentiment       = Column(Float, default=0.0)
    avg_sov_score       = Column(Float, default=0.0)
    avg_citation_score  = Column(Float, default=0.0)

    avg_geo_score       = Column(Float, default=0.0)

    industry            = Column(String(128), nullable=True)
    industry_rank       = Column(Integer, nullable=True)
    industry_sov_pct    = Column(Float, nullable=True)

    created_at          = Column(DateTime, server_default=func.now())
    updated_at          = Column(DateTime, onupdate=func.now(), nullable=True)

    brand               = relationship("Brand")

    __table_args__ = (
        UniqueConstraint("brand_id", "date", "target_llm", "intent", "language",
                         name="uq_geo_daily_dims"),
    )


# ─── IndustryBenchmarkDaily ──────────────────────────────────────────────────

class IndustryBenchmarkDaily(Base):
    __tablename__ = "industry_benchmark_daily"

    id              = Column(Integer, primary_key=True)
    industry        = Column(String(128), nullable=False)
    date            = Column(DateTime, nullable=False)
    target_llm      = Column(String(64), nullable=True)

    total_brands    = Column(Integer, default=0)
    total_queries   = Column(Integer, default=0)
    avg_mention_rate = Column(Float, default=0.0)
    avg_geo_score   = Column(Float, default=0.0)
    avg_sentiment   = Column(Float, default=0.0)

    score_p25       = Column(Float, nullable=True)
    score_p50       = Column(Float, nullable=True)
    score_p75       = Column(Float, nullable=True)

    top_brands_json = Column(JSON, nullable=True)

    created_at      = Column(DateTime, server_default=func.now())
    updated_at      = Column(DateTime, onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("industry", "date", "target_llm", name="uq_industry_daily"),
    )


# ─── ProductScoreDaily ────────────────────────────────────────────────────────

class ProductScoreDaily(Base):
    __tablename__ = "product_score_daily"

    id               = Column(Integer, primary_key=True)
    brand_id         = Column(Integer, ForeignKey("brands.id"), nullable=False)
    product_name     = Column(String(256), nullable=False)
    category         = Column(String(128), nullable=True)
    date             = Column(DateTime, nullable=False)
    target_llm       = Column(String(64), nullable=True)

    total_queries    = Column(Integer, default=0)
    mention_count    = Column(Integer, default=0)
    mention_rate     = Column(Float, default=0.0)
    avg_position_rank = Column(Float, nullable=True)
    first_place_count = Column(Integer, default=0)
    first_place_rate = Column(Float, default=0.0)
    avg_sentiment_score = Column(Float, default=0.0)
    avg_geo_score    = Column(Float, default=0.0)

    category_sov_pct = Column(Float, nullable=True)
    category_rank    = Column(Integer, nullable=True)

    comparison_wins  = Column(Integer, default=0)
    comparison_total = Column(Integer, default=0)
    win_rate         = Column(Float, default=0.0)

    top_features_json     = Column(JSON, nullable=True)
    top_scenarios_json    = Column(JSON, nullable=True)
    price_positioning     = Column(String(32), nullable=True)
    price_positioning_json = Column(JSON, nullable=True)
    top_drivers_json      = Column(JSON, nullable=True)

    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, onupdate=func.now(), nullable=True)

    brand            = relationship("Brand")

    __table_args__ = (
        UniqueConstraint("brand_id", "product_name", "date", "target_llm",
                         name="uq_product_daily"),
    )
