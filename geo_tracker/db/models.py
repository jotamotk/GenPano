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

class Brand(Base):
    __tablename__ = "brands"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(256), nullable=False)
    website      = Column(String(512))
    industry     = Column(String(128))
    description  = Column(Text)
    target_market = Column(String(128), default="中国大陆")
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
    intent       = Column(String(64))   # awareness|comparison|recommendation|problem_solving
    language     = Column(String(8), default="zh")   # zh | en
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

    proxy_id            = Column(Integer, ForeignKey("proxies.id"), nullable=True)
    profile_id          = Column(Integer, ForeignKey("profiles.id"), nullable=True)

    proxy               = relationship("Proxy", back_populates="accounts")
    profile             = relationship("Profile", back_populates="accounts")
    rotation_logs       = relationship("AccountRotationLog", back_populates="account")


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
    query_text   = Column(Text)
    target_llm   = Column(String(64))
    status       = Column(String(16), default=QueryStatus.PENDING.value)
    retry_count  = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=True)
    executed_at  = Column(DateTime, nullable=True)
    created_at   = Column(DateTime, server_default=func.now())

    profile      = relationship("Profile",  back_populates="queries")
    prompt       = relationship("Prompt",   back_populates="queries")
    brand        = relationship("Brand",    back_populates="queries")
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

    query            = relationship("Query", back_populates="response")
