"""
LLM 响应查询工具 - 带手动触发 Query
"""
import os
import re
import sys
import uuid
import json
import threading
from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse
from flask import Flask, render_template, render_template_string, request, jsonify, Response, session, has_request_context

try:
    from .topic_plan import (
        DoubaoTopicPlanClient,
        TopicPlanLLMError,
        dedupe_topic_candidates,
        is_natural_consumer_topic,
        load_doubao_config,
        normalize_topic_title,
        transition_candidate_status,
    )
    from .prompt_matrix import (
        ALLOWED_INTENTS,
        ALLOWED_LANGUAGES,
        PromptMatrixClient,
        PromptMatrixError,
        dedupe_prompt_candidates,
        detect_brand_leaks,
        estimate_generation_count,
        has_prompt_language_mismatch,
        intent_language_combinations,
        is_natural_user_prompt,
        is_valid_prompt_for_language,
        merge_usage,
        normalize_prompt_text,
        prompt_generation_config,
        selected_intents,
        selected_languages,
        transition_candidate_status as transition_prompt_candidate_status,
    )
    from .segment_profiles import (
        SegmentProfileGenerationError,
        SegmentProfileGenerationService,
    )
except ImportError:
    from topic_plan import (
        DoubaoTopicPlanClient,
        TopicPlanLLMError,
        dedupe_topic_candidates,
        is_natural_consumer_topic,
        load_doubao_config,
        normalize_topic_title,
        transition_candidate_status,
    )
    from prompt_matrix import (
        ALLOWED_INTENTS,
        ALLOWED_LANGUAGES,
        PromptMatrixClient,
        PromptMatrixError,
        dedupe_prompt_candidates,
        detect_brand_leaks,
        estimate_generation_count,
        has_prompt_language_mismatch,
        intent_language_combinations,
        is_natural_user_prompt,
        is_valid_prompt_for_language,
        merge_usage,
        normalize_prompt_text,
        prompt_generation_config,
        selected_intents,
        selected_languages,
        transition_candidate_status as transition_prompt_candidate_status,
    )
    from segment_profiles import (
        SegmentProfileGenerationError,
        SegmentProfileGenerationService,
    )

# Add parent directory to path so we can import geo_tracker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__)
app.secret_key = os.getenv(
    "ADMIN_SESSION_SECRET",
    os.getenv("FLASK_SECRET_KEY", "admin-console-dev-secret-change-me"),
)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.getenv("ADMIN_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

DATABASE_URL = "postgresql://genpano:genpano2026@localhost:5432/genpano"
DB_USER = "genpano"
DB_PASS = "genpano2026"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "genpano"


def _configure_database_url(url):
    global DATABASE_URL, DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME

    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL must include host and database name")

    DATABASE_URL = url
    DB_USER = unquote(parsed.username or "")
    DB_PASS = unquote(parsed.password or "")
    DB_HOST = parsed.hostname
    DB_PORT = str(parsed.port or 5432)
    DB_NAME = unquote(parsed.path.lstrip("/"))


_configure_database_url(os.getenv("DATABASE_URL", DATABASE_URL))

# HTML debug files directory
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "/data/screenshots")

# Celery setup
HAS_CELERY = False
celery_app = None
try:
    from celery import Celery
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    celery_app = Celery(
        "geo_tracker",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        broker_connection_retry_on_startup=True,
    )
    HAS_CELERY = True
except Exception as e:
    print(f"Celery not available: {e}")


def _ensure_citations_column():
    """确保 llm_responses 表有 citations_json 和 response_html 列"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE llm_responses
                    ADD COLUMN IF NOT EXISTS citations_json JSONB
                """)
                cur.execute("""
                    ALTER TABLE llm_responses
                    ADD COLUMN IF NOT EXISTS response_html TEXT
                """)
                # cookies 时间追踪字段
                cur.execute("""
                    ALTER TABLE llm_accounts
                    ADD COLUMN IF NOT EXISTS cookies_updated_at TIMESTAMP
                """)
                # query 关联的账号
                cur.execute("""
                    ALTER TABLE queries
                    ADD COLUMN IF NOT EXISTS account_id INTEGER REFERENCES llm_accounts(id)
                """)
            conn.commit()
            print("DB migration: citations_json + response_html + cookies_updated_at columns ensured")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


def _ensure_analyzer_tables():
    """确保 Analyzer 数据层的表和字段存在（PR #104）"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # ── 现有表新增字段 ──
                cur.execute("""
                    ALTER TABLE llm_responses
                    ADD COLUMN IF NOT EXISTS analysis_status VARCHAR(16) DEFAULT 'pending'
                """)
                cur.execute("""
                    ALTER TABLE llm_responses
                    ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP
                """)
                cur.execute("""
                    ALTER TABLE brands
                    ADD COLUMN IF NOT EXISTS aliases JSONB
                """)
                cur.execute("""
                    ALTER TABLE competitors
                    ADD COLUMN IF NOT EXISTS aliases JSONB
                """)
                cur.execute("""
                    ALTER TABLE prompts
                    ADD COLUMN IF NOT EXISTS tags JSONB
                """)

                # ── 新建分析表 ──
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS brand_mentions (
                        id SERIAL PRIMARY KEY,
                        response_id INTEGER NOT NULL REFERENCES llm_responses(id),
                        brand_id INTEGER REFERENCES brands(id),
                        brand_name VARCHAR(256) NOT NULL,
                        product_name VARCHAR(256),
                        is_target BOOLEAN DEFAULT FALSE,
                        position_type VARCHAR(32),
                        position_rank INTEGER,
                        detail_level VARCHAR(16),
                        sentiment VARCHAR(16),
                        sentiment_score FLOAT,
                        context_snippet TEXT,
                        mention_count INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT NOW(),
                        CONSTRAINT uq_mention_response_brand_product UNIQUE (response_id, brand_name, product_name)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sentiment_drivers (
                        id SERIAL PRIMARY KEY,
                        mention_id INTEGER NOT NULL REFERENCES brand_mentions(id),
                        response_id INTEGER NOT NULL REFERENCES llm_responses(id),
                        brand_name VARCHAR(256) NOT NULL,
                        driver_text VARCHAR(512) NOT NULL,
                        polarity VARCHAR(8) NOT NULL,
                        category VARCHAR(64),
                        strength FLOAT DEFAULT 0.5,
                        source_quote TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS citation_sources (
                        id SERIAL PRIMARY KEY,
                        response_id INTEGER NOT NULL REFERENCES llm_responses(id),
                        mention_id INTEGER REFERENCES brand_mentions(id),
                        url VARCHAR(2048) NOT NULL,
                        domain VARCHAR(256),
                        title VARCHAR(512),
                        citation_index INTEGER,
                        source_type VARCHAR(32),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS response_analyses (
                        id SERIAL PRIMARY KEY,
                        response_id INTEGER UNIQUE REFERENCES llm_responses(id),
                        dimension_industry VARCHAR(128),
                        dimension_company VARCHAR(128),
                        dimension_product VARCHAR(128),
                        dimension_category VARCHAR(128),
                        total_brands_mentioned INTEGER DEFAULT 0,
                        target_brand_mentioned BOOLEAN DEFAULT FALSE,
                        target_brand_position VARCHAR(32),
                        target_brand_rank INTEGER,
                        target_brand_sentiment VARCHAR(16),
                        target_brand_detail VARCHAR(16),
                        visibility_score FLOAT DEFAULT 0.0,
                        sentiment_score FLOAT DEFAULT 0.0,
                        sov_score FLOAT DEFAULT 0.0,
                        citation_score FLOAT DEFAULT 0.0,
                        geo_score FLOAT DEFAULT 0.0,
                        analyzed_at TIMESTAMP DEFAULT NOW(),
                        analyzer_model VARCHAR(64),
                        raw_analysis_json JSONB
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS product_feature_mentions (
                        id SERIAL PRIMARY KEY,
                        analysis_id INTEGER NOT NULL REFERENCES response_analyses(id),
                        brand_name VARCHAR(256) NOT NULL,
                        product_name VARCHAR(256) NOT NULL,
                        feature_name VARCHAR(128) NOT NULL,
                        feature_sentiment VARCHAR(16),
                        context_snippet TEXT,
                        scenario VARCHAR(128),
                        price_positioning VARCHAR(32),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS geo_score_daily (
                        id SERIAL PRIMARY KEY,
                        brand_id INTEGER NOT NULL REFERENCES brands(id),
                        date TIMESTAMP NOT NULL,
                        target_llm VARCHAR(64),
                        intent VARCHAR(64),
                        language VARCHAR(8),
                        total_queries INTEGER DEFAULT 0,
                        mention_count INTEGER DEFAULT 0,
                        mention_rate FLOAT DEFAULT 0.0,
                        avg_position_rank FLOAT,
                        first_place_count INTEGER DEFAULT 0,
                        first_place_rate FLOAT DEFAULT 0.0,
                        positive_rate FLOAT DEFAULT 0.0,
                        negative_rate FLOAT DEFAULT 0.0,
                        avg_sentiment_score FLOAT DEFAULT 0.0,
                        citation_rate FLOAT DEFAULT 0.0,
                        avg_sov FLOAT DEFAULT 0.0,
                        avg_visibility FLOAT DEFAULT 0.0,
                        avg_sentiment FLOAT DEFAULT 0.0,
                        avg_sov_score FLOAT DEFAULT 0.0,
                        avg_citation_score FLOAT DEFAULT 0.0,
                        avg_geo_score FLOAT DEFAULT 0.0,
                        industry VARCHAR(128),
                        industry_rank INTEGER,
                        industry_sov_pct FLOAT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP,
                        CONSTRAINT uq_geo_daily_dims UNIQUE (brand_id, date, target_llm, intent, language)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS industry_benchmark_daily (
                        id SERIAL PRIMARY KEY,
                        industry VARCHAR(128) NOT NULL,
                        date TIMESTAMP NOT NULL,
                        target_llm VARCHAR(64),
                        total_brands INTEGER DEFAULT 0,
                        total_queries INTEGER DEFAULT 0,
                        avg_mention_rate FLOAT DEFAULT 0.0,
                        avg_geo_score FLOAT DEFAULT 0.0,
                        avg_sentiment FLOAT DEFAULT 0.0,
                        score_p25 FLOAT,
                        score_p50 FLOAT,
                        score_p75 FLOAT,
                        top_brands_json JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP,
                        CONSTRAINT uq_industry_daily UNIQUE (industry, date, target_llm)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS product_score_daily (
                        id SERIAL PRIMARY KEY,
                        brand_id INTEGER NOT NULL REFERENCES brands(id),
                        product_name VARCHAR(256) NOT NULL,
                        category VARCHAR(128),
                        date TIMESTAMP NOT NULL,
                        target_llm VARCHAR(64),
                        total_queries INTEGER DEFAULT 0,
                        mention_count INTEGER DEFAULT 0,
                        mention_rate FLOAT DEFAULT 0.0,
                        avg_position_rank FLOAT,
                        first_place_count INTEGER DEFAULT 0,
                        first_place_rate FLOAT DEFAULT 0.0,
                        avg_sentiment_score FLOAT DEFAULT 0.0,
                        avg_geo_score FLOAT DEFAULT 0.0,
                        category_sov_pct FLOAT,
                        category_rank INTEGER,
                        comparison_wins INTEGER DEFAULT 0,
                        comparison_total INTEGER DEFAULT 0,
                        win_rate FLOAT DEFAULT 0.0,
                        top_features_json JSONB,
                        top_scenarios_json JSONB,
                        price_positioning VARCHAR(32),
                        price_positioning_json JSONB,
                        top_drivers_json JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP,
                        CONSTRAINT uq_product_daily UNIQUE (brand_id, product_name, date, target_llm)
                    )
                """)
                # ── Migrate unique constraint: (response_id, brand_name) → (response_id, brand_name, product_name) ──
                cur.execute("""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM information_schema.table_constraints
                            WHERE constraint_name = 'uq_mention_response_brand'
                              AND table_name = 'brand_mentions'
                        ) THEN
                            ALTER TABLE brand_mentions DROP CONSTRAINT uq_mention_response_brand;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.table_constraints
                            WHERE constraint_name = 'uq_mention_response_brand_product'
                              AND table_name = 'brand_mentions'
                        ) THEN
                            ALTER TABLE brand_mentions ADD CONSTRAINT uq_mention_response_brand_product
                                UNIQUE (response_id, brand_name, product_name);
                        END IF;
                    END $$
                """)

            conn.commit()
            print("DB migration: analyzer tables ensured (brand_mentions, sentiment_drivers, "
                  "citation_sources, response_analyses, product_feature_mentions, "
                  "geo_score_daily, industry_benchmark_daily, product_score_daily)")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


def _ensure_preview_columns():
    """Additive columns for the preview admin console's 执行追踪 view.
    Worker is NOT being upgraded for the preview rollout, so these fields
    stay NULL until the worker starts populating them — the UI renders '—'
    for NULL values.
    """
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP")
                cur.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS started_at TIMESTAMP")
                cur.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP")
                cur.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS latency_ms INTEGER")
                cur.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS retry_reason VARCHAR(256)")
            conn.commit()
            print("DB migration: preview columns ensured on queries "
                  "(queued_at, started_at, finished_at, latency_ms, retry_reason)")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


# Engines we want to keep in the preview DB. Anything else gets pruned so the
# 执行追踪 table only shows supported engines (Gemini is kept in the DB but
# hidden in the UI per product decision).
APPROVED_ENGINES = ('chatgpt', 'doubao', 'deepseek', 'gemini')


def _normalize_query_data():
    """One-shot cleanup run at startup:
    1) Lowercase queries.status, queries.target_llm, llm_accounts.llm_name.
    2) Cascade-delete queries whose target_llm is not in APPROVED_ENGINES
       (llm_responses + all analyzer descendants reference queries via FKs
       without ON DELETE CASCADE, so we must walk the chain manually).
    Uses IS DISTINCT FROM so already-lowercased rows aren't touched.
    """
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE queries SET status = LOWER(status) "
                    "WHERE status IS DISTINCT FROM LOWER(status)"
                )
                status_fixed = cur.rowcount
                cur.execute(
                    "UPDATE queries SET target_llm = LOWER(target_llm) "
                    "WHERE target_llm IS DISTINCT FROM LOWER(target_llm)"
                )
                llm_fixed = cur.rowcount
                cur.execute(
                    "UPDATE llm_accounts SET llm_name = LOWER(llm_name) "
                    "WHERE llm_name IS DISTINCT FROM LOWER(llm_name)"
                )
                accounts_fixed = cur.rowcount

                # Cascade delete. Chain:
                # queries → llm_responses → {brand_mentions, response_analyses,
                # sentiment_drivers, citation_sources} → product_feature_mentions
                cur.execute(
                    "CREATE TEMP TABLE _bad_q ON COMMIT DROP AS "
                    "SELECT id FROM queries "
                    "WHERE LOWER(COALESCE(target_llm, '')) NOT IN %s",
                    (APPROVED_ENGINES,)
                )
                cur.execute("SELECT COUNT(*) FROM _bad_q")
                pruned = cur.fetchone()[0]
                if pruned > 0:
                    cur.execute(
                        "CREATE TEMP TABLE _bad_r ON COMMIT DROP AS "
                        "SELECT id FROM llm_responses WHERE query_id IN (SELECT id FROM _bad_q)"
                    )
                    cur.execute("""
                        DELETE FROM product_feature_mentions
                        WHERE analysis_id IN (
                            SELECT id FROM response_analyses
                            WHERE response_id IN (SELECT id FROM _bad_r)
                        )
                    """)
                    cur.execute(
                        "DELETE FROM sentiment_drivers WHERE response_id IN (SELECT id FROM _bad_r)"
                    )
                    cur.execute(
                        "DELETE FROM citation_sources WHERE response_id IN (SELECT id FROM _bad_r)"
                    )
                    cur.execute(
                        "DELETE FROM response_analyses WHERE response_id IN (SELECT id FROM _bad_r)"
                    )
                    cur.execute(
                        "DELETE FROM brand_mentions WHERE response_id IN (SELECT id FROM _bad_r)"
                    )
                    cur.execute(
                        "DELETE FROM llm_responses WHERE query_id IN (SELECT id FROM _bad_q)"
                    )
                    cur.execute("DELETE FROM queries WHERE id IN (SELECT id FROM _bad_q)")
            conn.commit()
            print(
                f"DB normalize: status_lowered={status_fixed}, "
                f"target_llm_lowered={llm_fixed}, accounts_lowered={accounts_fixed}, "
                f"pruned_non_approved={pruned}"
            )
        finally:
            conn.close()
    except Exception as e:
        print(f"DB normalize warning (non-fatal): {e}")


def get_db():
    import psycopg2
    import time
    last_err = None
    for attempt in range(5):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                dbname=DB_NAME,
                connect_timeout=5,
            )
            return conn
        except psycopg2.OperationalError as e:
            last_err = e
            time.sleep(2 ** attempt)  # 1, 2, 4, 8, 16 秒
    raise last_err


def _isoformat(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _client_ip():
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr


def _table_exists(cur, table_name):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (table_name,),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        return bool(row.get("exists"))
    return bool(row[0])


def _table_columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    cols = set()
    for row in cur.fetchall():
        cols.add(row.get("column_name") if isinstance(row, dict) else row[0])
    return cols


def _ensure_admin_tables():
    """Ensure additive user-admin tables/columns used by the Admin console.

    `admin_audit_log` is append-only by application convention: this module only
    inserts through `_insert_admin_audit_log` and never exposes update/delete
    code paths. Product user status is deliberately derived, not stored on
    `users`.
    """
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                if _table_exists(cur, "users"):
                    cur.execute(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMP"
                    )
                    cur.execute(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_confirmed_at TIMESTAMP"
                    )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_moderation_actions (
                        id VARCHAR(36) PRIMARY KEY,
                        user_id VARCHAR(36) NOT NULL,
                        operator_id VARCHAR(36),
                        action VARCHAR(32) NOT NULL
                            CHECK (action IN (
                                'freeze',
                                'unfreeze',
                                'force_password_reset',
                                'soft_delete'
                            )),
                        reason TEXT,
                        expires_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_user_moderation_user_created
                    ON user_moderation_actions (user_id, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_user_moderation_action_created
                    ON user_moderation_actions (action, created_at DESC)
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_audit_log (
                        id VARCHAR(36) PRIMARY KEY,
                        operator_id VARCHAR(36),
                        action VARCHAR(64) NOT NULL,
                        target_type VARCHAR(64) NOT NULL,
                        target_id VARCHAR(255),
                        diff_json JSONB,
                        reason TEXT,
                        ip VARCHAR(45),
                        ua TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_admin_audit_target_created
                    ON admin_audit_log (target_type, target_id, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_admin_audit_operator_created
                    ON admin_audit_log (operator_id, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_login_attempts (
                        id VARCHAR(36) PRIMARY KEY,
                        email VARCHAR(255) NOT NULL,
                        ip_address VARCHAR(45),
                        success BOOLEAN NOT NULL,
                        failure_code VARCHAR(32),
                        user_agent VARCHAR(512),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "ALTER TABLE admin_login_attempts ADD COLUMN IF NOT EXISTS user_agent VARCHAR(512)"
                )
            conn.commit()
            print("DB migration: query admin user-management tables ensured")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


def _verify_admin_password(password, password_hash):
    if not password or not password_hash:
        return False
    try:
        if password_hash.startswith("$2"):
            import bcrypt
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        from werkzeug.security import check_password_hash
        return check_password_hash(password_hash, password)
    except Exception:
        return False


def _record_admin_login_attempt(cur, email, success, failure_code=None):
    cur.execute(
        """
        INSERT INTO admin_login_attempts
            (id, email, ip_address, success, failure_code, user_agent, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            str(uuid.uuid4()),
            email,
            _client_ip(),
            success,
            failure_code,
            (request.headers.get("user-agent") or "")[:512],
        ),
    )


def _current_admin():
    admin_user_id = session.get("admin_user_id")
    if not admin_user_id:
        return None
    conn = get_db()
    try:
        from psycopg2.extras import RealDictCursor
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, email, role, status
                FROM admin_users
                WHERE id = %s
                """,
                (admin_user_id,),
            )
            admin = cur.fetchone()
            if not admin or admin.get("status") != "active":
                session.clear()
                return None
            return dict(admin)
    finally:
        conn.close()


def _require_admin():
    admin = _current_admin()
    if admin is None:
        return None, (jsonify({"error": "admin_session_required"}), 401)
    return admin, None


def _insert_admin_audit_log(cur, *, operator_id, action, target_type, target_id, diff, reason):
    import json as json_mod
    ip = _client_ip() if has_request_context() else None
    user_agent = request.headers.get("user-agent") if has_request_context() else None
    cur.execute(
        """
        INSERT INTO admin_audit_log
            (id, operator_id, action, target_type, target_id, diff_json,
             reason, ip, ua, created_at)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, NOW())
        """,
        (
            str(uuid.uuid4()),
            operator_id,
            action,
            target_type,
            str(target_id) if target_id is not None else None,
            json_mod.dumps(diff or {}, default=_json_default),
            reason,
            ip,
            user_agent,
        ),
    )


def _ensure_topic_plan_tables():
    """Ensure the minimal Topic Plan persistence tables exist."""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS topic_plan_runs (
                        id VARCHAR(36) PRIMARY KEY,
                        admin_id VARCHAR(36),
                        industry_id VARCHAR(128),
                        category_id VARCHAR(128),
                        brand_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        status VARCHAR(16) NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running', 'completed', 'failed')),
                        request_config JSONB NOT NULL DEFAULT '{}'::jsonb,
                        coverage_snapshot JSONB,
                        llm_model VARCHAR(128),
                        llm_usage_json JSONB,
                        llm_error TEXT,
                        candidates_generated INTEGER NOT NULL DEFAULT 0,
                        started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        completed_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_topic_plan_runs_created
                    ON topic_plan_runs (created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS topic_candidates (
                        id VARCHAR(36) PRIMARY KEY,
                        run_id VARCHAR(36) REFERENCES topic_plan_runs(id),
                        brand_id INTEGER,
                        brand_name VARCHAR(256) NOT NULL,
                        title VARCHAR(256) NOT NULL,
                        dimension VARCHAR(32) NOT NULL,
                        reason TEXT,
                        confidence FLOAT,
                        coverage_gap VARCHAR(256),
                        normalized_title VARCHAR(256) NOT NULL,
                        status VARCHAR(16) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'approved', 'rejected')),
                        reviewed_by VARCHAR(36),
                        reviewed_at TIMESTAMP,
                        review_reason TEXT,
                        approved_topic_id INTEGER,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_topic_candidates_status_created
                    ON topic_candidates (status, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_topic_candidates_brand_status
                    ON topic_candidates (brand_id, status)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_topic_candidates_run
                    ON topic_candidates (run_id)
                    """
                )
            conn.commit()
            print("DB migration: topic plan tables ensured")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


def _ensure_prompt_matrix_tables():
    """Ensure additive Prompt Matrix tables and prompt metadata columns exist."""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prompt_generation_runs (
                        id VARCHAR(36) PRIMARY KEY,
                        admin_id VARCHAR(36),
                        status VARCHAR(16) NOT NULL DEFAULT 'running'
                            CHECK (status IN ('running', 'completed', 'failed')),
                        request_config JSONB NOT NULL DEFAULT '{}'::jsonb,
                        selected_topic_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        estimated_prompts INTEGER NOT NULL DEFAULT 0,
                        candidates_generated INTEGER NOT NULL DEFAULT 0,
                        llm_model VARCHAR(128),
                        llm_usage_json JSONB,
                        llm_error TEXT,
                        started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        completed_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_prompt_generation_runs_created
                    ON prompt_generation_runs (created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prompt_candidates (
                        id VARCHAR(36) PRIMARY KEY,
                        run_id VARCHAR(36) REFERENCES prompt_generation_runs(id),
                        topic_id INTEGER NOT NULL,
                        topic_text TEXT,
                        brand_id INTEGER,
                        brand_name VARCHAR(256),
                        dimension VARCHAR(32),
                        intent VARCHAR(32) NOT NULL,
                        language VARCHAR(16) NOT NULL,
                        template_strategy VARCHAR(64),
                        template_version VARCHAR(64),
                        text TEXT NOT NULL,
                        status VARCHAR(16) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'approved', 'rejected')),
                        confidence FLOAT,
                        reason TEXT,
                        duplicate_of VARCHAR(64),
                        tags JSONB NOT NULL DEFAULT '{}'::jsonb,
                        reviewed_by VARCHAR(36),
                        reviewed_at TIMESTAMP,
                        review_reason TEXT,
                        approved_prompt_id INTEGER,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_prompt_candidates_status_created
                    ON prompt_candidates (status, created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_prompt_candidates_topic_status
                    ON prompt_candidates (topic_id, status)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_prompt_candidates_run
                    ON prompt_candidates (run_id)
                    """
                )
                if _table_exists(cur, "prompts"):
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS intent VARCHAR(32)")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS language VARCHAR(16)")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS template_strategy VARCHAR(64)")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS template_version VARCHAR(64)")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'active'")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS tags JSONB")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS generated_by VARCHAR(64)")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
                    cur.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()")
            conn.commit()
            print("DB migration: prompt matrix tables ensured")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


def _topic_plan_json(value):
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _parse_int_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value).split(",")
    result = []
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        try:
            result.append(int(text))
        except ValueError:
            raise ValueError("invalid integer list")
    return list(dict.fromkeys(result))


def _clamp_int(value, default, min_value, max_value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(min_value, min(number, max_value))


def _topic_plan_dimension(raw_category):
    value = (raw_category or "").strip().lower()
    if value in {"brand", "product", "category", "scenario", "question"}:
        return value
    legacy_map = {
        "awareness": "brand",
        "comparison": "category",
        "recommendation": "scenario",
        "problem_solving": "question",
        "problem-solving": "question",
        "non_brand": "category",
        "brand": "brand",
    }
    return legacy_map.get(value, "brand")


def _fetch_topic_plan_brands(cur):
    if not _table_exists(cur, "brands"):
        return []

    cols = _table_columns(cur, "brands")
    name_expr = "name" if "name" in cols else "('Brand #' || id::text)"
    industry_expr = (
        "COALESCE(NULLIF(industry, ''), 'Uncategorized')"
        if "industry" in cols
        else "'Uncategorized'"
    )
    target_market_expr = (
        "COALESCE(NULLIF(target_market, ''), '')"
        if "target_market" in cols
        else "''"
    )
    description_expr = "COALESCE(description, '')" if "description" in cols else "''"
    aliases_expr = "aliases" if "aliases" in cols else "NULL::jsonb AS aliases"

    cur.execute(
        f"""
        SELECT id, {name_expr} AS name, {industry_expr} AS industry,
               {target_market_expr} AS target_market,
               {description_expr} AS description,
               {aliases_expr}
        FROM brands
        ORDER BY id
        """
    )
    rows = [dict(row) for row in cur.fetchall()]

    topic_counts = {}
    primary_categories = {}
    if _table_exists(cur, "topics"):
        topic_cols = _table_columns(cur, "topics")
        if "brand_id" in topic_cols:
            cur.execute(
                """
                SELECT brand_id, COUNT(*) AS topic_count
                FROM topics
                GROUP BY brand_id
                """
            )
            topic_counts = {row["brand_id"]: row["topic_count"] for row in cur.fetchall()}
            if "category" in topic_cols:
                cur.execute(
                    """
                    SELECT DISTINCT ON (brand_id) brand_id, category
                    FROM topics
                    WHERE category IS NOT NULL AND category <> ''
                    ORDER BY brand_id, created_at DESC NULLS LAST, id DESC
                    """
                )
                primary_categories = {row["brand_id"]: row["category"] for row in cur.fetchall()}

    for row in rows:
        industry = row.get("industry") or "Uncategorized"
        category = primary_categories.get(row["id"]) or ""
        row["id"] = int(row["id"])
        row["industry_id"] = industry
        row["industry_name"] = industry
        row["category_id"] = category
        row["category_name"] = category
        row["topic_count"] = int(topic_counts.get(row["id"], 0) or 0)
        aliases = row.get("aliases") or []
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except Exception:
                aliases = [aliases]
        row["aliases"] = aliases if isinstance(aliases, list) else []
        row["selected"] = False
    return rows


def _fetch_topic_plan_categories(cur):
    if not _table_exists(cur, "topics"):
        return []
    cols = _table_columns(cur, "topics")
    if "category" not in cols:
        return []
    cur.execute(
        """
        SELECT DISTINCT category
        FROM topics
        WHERE category IS NOT NULL AND category <> ''
        ORDER BY category
        LIMIT 200
        """
    )
    return [{"id": row["category"], "name": row["category"]} for row in cur.fetchall()]


def _fetch_topic_rows_for_brands(cur, brand_ids, category_id=None):
    if not brand_ids or not _table_exists(cur, "topics"):
        return []
    cols = _table_columns(cur, "topics")
    if not {"id", "brand_id", "text"}.issubset(cols):
        return []
    category_select = "category" if "category" in cols else "NULL::text AS category"
    where = ["brand_id = ANY(%s)"]
    params = [brand_ids]
    if category_id and "category" in cols:
        where.append("category = %s")
        params.append(category_id)
    cur.execute(
        f"""
        SELECT id, brand_id, text, {category_select}
        FROM topics
        WHERE {" AND ".join(where)}
        ORDER BY brand_id, id
        """,
        params,
    )
    return [dict(row) for row in cur.fetchall()]


def _topic_plan_no_prompt_count(cur, brand_ids):
    if not brand_ids or not _table_exists(cur, "topics") or not _table_exists(cur, "prompts"):
        return 0
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM topics t
        LEFT JOIN prompts p ON p.topic_id = t.id
        WHERE t.brand_id = ANY(%s) AND p.id IS NULL
        """,
        (brand_ids,),
    )
    return int(cur.fetchone()["cnt"] or 0)


def _topic_plan_pending_summary(cur, brand_ids):
    if not _table_exists(cur, "topic_candidates"):
        return {"pending": 0, "low_confidence": 0}
    params = []
    where = ["status = 'pending'"]
    if brand_ids:
        where.append("brand_id = ANY(%s)")
        params.append(brand_ids)
    cur.execute(
        f"""
        SELECT COUNT(*) AS pending,
               SUM(CASE WHEN COALESCE(confidence, 0) < 0.75 THEN 1 ELSE 0 END) AS low_confidence
        FROM topic_candidates
        WHERE {" AND ".join(where)}
        """,
        params,
    )
    row = cur.fetchone()
    return {
        "pending": int(row["pending"] or 0),
        "low_confidence": int(row["low_confidence"] or 0),
    }


def _build_topic_plan_coverage(cur, brands, category_id=None, max_per_brand=40):
    selected_brand_ids = [int(b["id"]) for b in brands]
    topic_rows = _fetch_topic_rows_for_brands(cur, selected_brand_ids, category_id)
    topics_by_brand = {brand_id: [] for brand_id in selected_brand_ids}
    for topic in topic_rows:
        topics_by_brand.setdefault(int(topic["brand_id"]), []).append(topic)

    desired_dimensions = ["brand", "product", "category", "scenario", "question"]
    per_dimension_target = max(1, round(max_per_brand / len(desired_dimensions)))
    rows = []
    gaps = []
    total_rate = 0
    for brand in brands:
        brand_id = int(brand["id"])
        brand_topics = topics_by_brand.get(brand_id, [])
        dim_counts = {dimension: 0 for dimension in desired_dimensions}
        for topic in brand_topics:
            dim = _topic_plan_dimension(topic.get("category"))
            dim_counts[dim] = dim_counts.get(dim, 0) + 1

        coverage_rate = min(1.0, len(brand_topics) / max(max_per_brand, 1))
        total_rate += coverage_rate
        brand_gap_count = 0
        for dimension in desired_dimensions:
            missing = max(per_dimension_target - dim_counts.get(dimension, 0), 0)
            if missing <= 0:
                continue
            brand_gap_count += missing
            priority = "P1" if coverage_rate < 0.6 else "P2"
            gaps.append(
                {
                    "brand_id": brand_id,
                    "brand": brand["name"],
                    "type": dimension,
                    "count": missing,
                    "priority": priority,
                    "coverage_gap": f"{brand['name']}:{dimension}",
                }
            )

        rows.append(
            {
                "brand_id": brand_id,
                "brand": brand["name"],
                "topics": len(brand_topics),
                "coverage_rate": round(coverage_rate, 4),
                "coverage": f"{round(coverage_rate * 100)}%",
                "gaps": brand_gap_count,
                "status": "达标" if coverage_rate >= 0.8 else "待补齐",
                "status_key": "ok" if coverage_rate >= 0.8 else "gap",
                "dimension_counts": dim_counts,
            }
        )

    pending = _topic_plan_pending_summary(cur, selected_brand_ids)
    no_prompt = _topic_plan_no_prompt_count(cur, selected_brand_ids)
    avg_rate = total_rate / len(brands) if brands else 0
    summary = {
        "brand_count": len(brands),
        "topic_count": sum(row["topics"] for row in rows),
        "average_coverage": round(avg_rate, 4),
        "coverage_label": f"{round(avg_rate * 100)}%",
        "gap_count": sum(row["gaps"] for row in rows),
        "pending_candidates": pending["pending"],
        "low_confidence": pending["low_confidence"],
        "no_prompt_topics": no_prompt,
    }
    return {"rows": rows, "gaps": gaps, "summary": summary, "existing_topics": topic_rows}


def _topic_plan_scope_brands(all_brands, industry_id=None, brand_ids=None):
    brand_id_set = {int(x) for x in brand_ids or []}
    result = []
    for brand in all_brands:
        if industry_id and brand.get("industry_id") != industry_id:
            continue
        if brand_id_set and int(brand["id"]) not in brand_id_set:
            continue
        result.append(brand)
    return result


def _topic_plan_candidate_row(row):
    item = dict(row)
    return {
        "id": item.get("id"),
        "run_id": item.get("run_id"),
        "title": item.get("title"),
        "brand_id": item.get("brand_id"),
        "brand": item.get("brand_name"),
        "dimension": item.get("dimension"),
        "reason": item.get("reason"),
        "confidence": float(item.get("confidence") or 0),
        "coverage_gap": item.get("coverage_gap"),
        "status": item.get("status"),
        "review_reason": item.get("review_reason"),
        "approved_topic_id": item.get("approved_topic_id"),
        "created_at": _isoformat(item.get("created_at")),
        "reviewed_at": _isoformat(item.get("reviewed_at")),
    }


def _topic_plan_dimension_label(dimension):
    return {
        "brand": "品牌",
        "product": "产品",
        "category": "品类",
        "scenario": "场景",
        "question": "问题",
    }.get(dimension or "", dimension or "未分类")


def _topic_plan_source_label(generated_by):
    value = (generated_by or "").strip().lower()
    if value == "topic_plan":
        return "审核通过"
    if value.startswith("seed"):
        return "初始化"
    return "已有 Topic"


def _topic_plan_topics_summary(rows):
    total = len(rows)
    with_prompt = sum(1 for row in rows if row.get("promptCount", 0) > 0)
    category_count = sum(1 for row in rows if row.get("dimension_key") == "category")
    generated_count = sum(
        1 for row in rows
        if row.get("source") in {"初始化", "审核通过"}
    )
    prompt_rate = (with_prompt / total) if total else 0
    category_rate = (category_count / total) if total else 0
    generated_rate = (generated_count / total) if total else 0
    return {
        "totalTopics": total,
        "visibleTopics": total,
        "promptCoverageLabel": f"{round(prompt_rate * 100)}%",
        "promptCoverageMeta": f"{with_prompt} / {total}",
        "categoryShareLabel": f"{round(category_rate * 100)}%",
        "llmGeneratedLabel": f"{round(generated_rate * 100)}%",
    }


def _topic_plan_topic_row(row):
    item = dict(row)
    dimension = _topic_plan_dimension(item.get("category"))
    prompt_count = int(item.get("prompt_count") or 0)
    query_count = int(item.get("query_count") or 0)
    brand_name = item.get("brand_name") or f"Brand #{item.get('brand_id')}"
    return {
        "id": f"T-{item.get('id')}",
        "raw_id": item.get("id"),
        "title": item.get("text") or "",
        "dimension": _topic_plan_dimension_label(dimension),
        "dimension_key": dimension,
        "industry": item.get("industry") or "Uncategorized",
        "source": _topic_plan_source_label(item.get("generated_by")),
        "status": item.get("status") or "active",
        "promptCount": prompt_count,
        "queryCount": query_count,
        "brands": [brand_name],
        "brand": brand_name,
        "brand_id": item.get("brand_id"),
        "createdAt": _isoformat(item.get("created_at")),
        "confidence": 1.0,
    }


def _fetch_topic_plan_topics(
    cur,
    industry_id=None,
    category_id=None,
    brand_ids=None,
    dimension=None,
    status=None,
    query=None,
    limit=200,
):
    if not _table_exists(cur, "topics") or not _table_exists(cur, "brands"):
        return [], _topic_plan_topics_summary([])

    topic_cols = _table_columns(cur, "topics")
    if not {"id", "brand_id", "text"}.issubset(topic_cols):
        return [], _topic_plan_topics_summary([])

    category_select = "t.category" if "category" in topic_cols else "NULL::text AS category"
    generated_select = (
        "t.generated_by" if "generated_by" in topic_cols else "NULL::text AS generated_by"
    )
    status_select = (
        "COALESCE(t.status, 'active') AS status"
        if "status" in topic_cols
        else "'active'::text AS status"
    )
    created_select = (
        "t.created_at" if "created_at" in topic_cols else "NULL::timestamp AS created_at"
    )

    prompt_join = "LEFT JOIN (SELECT NULL::int AS topic_id, 0::int AS prompt_count WHERE FALSE) pc ON pc.topic_id = t.id"
    query_join = "LEFT JOIN (SELECT NULL::int AS topic_id, 0::int AS query_count WHERE FALSE) qc ON qc.topic_id = t.id"
    if _table_exists(cur, "prompts") and {"id", "topic_id"}.issubset(_table_columns(cur, "prompts")):
        prompt_join = """
            LEFT JOIN (
                SELECT topic_id, COUNT(*)::int AS prompt_count
                FROM prompts
                GROUP BY topic_id
            ) pc ON pc.topic_id = t.id
        """
        if _table_exists(cur, "queries") and "prompt_id" in _table_columns(cur, "queries"):
            query_join = """
                LEFT JOIN (
                    SELECT p.topic_id, COUNT(q.id)::int AS query_count
                    FROM prompts p
                    LEFT JOIN queries q ON q.prompt_id = p.id
                    GROUP BY p.topic_id
                ) qc ON qc.topic_id = t.id
            """

    where = ["1=1"]
    params = []
    if brand_ids:
        where.append("t.brand_id = ANY(%s)")
        params.append(brand_ids)
    if industry_id:
        where.append("b.industry = %s")
        params.append(industry_id)
    if category_id and "category" in topic_cols:
        where.append("t.category = %s")
        params.append(category_id)
    if status and status != "all" and "status" in topic_cols:
        where.append("COALESCE(t.status, 'active') = %s")
        params.append(status)
    if query:
        like = f"%{query}%"
        where.append("(t.text ILIKE %s OR b.name ILIKE %s OR ('T-' || t.id::text) ILIKE %s)")
        params.extend([like, like, like])

    cur.execute(
        f"""
        SELECT t.id, t.brand_id, t.text, {category_select}, {generated_select},
               {status_select}, {created_select},
               b.name AS brand_name,
               COALESCE(NULLIF(b.industry, ''), 'Uncategorized') AS industry,
               COALESCE(pc.prompt_count, 0) AS prompt_count,
               COALESCE(qc.query_count, 0) AS query_count
        FROM topics t
        JOIN brands b ON b.id = t.brand_id
        {prompt_join}
        {query_join}
        WHERE {" AND ".join(where)}
        ORDER BY t.created_at DESC NULLS LAST, t.id DESC
        LIMIT %s
        """,
        params + [limit],
    )
    rows = [_topic_plan_topic_row(row) for row in cur.fetchall()]
    if dimension:
        rows = [row for row in rows if row.get("dimension_key") == dimension]
    return rows, _topic_plan_topics_summary(rows)


def _parse_topic_plan_topic_id(value):
    text = str(value or "").strip()
    if text.upper().startswith("T-"):
        text = text[2:]
    if not text.isdigit():
        raise ValueError("invalid_topic_id")
    return int(text)


def _parse_topic_plan_topic_ids(value):
    if not isinstance(value, list):
        raise ValueError("topic_ids_required")
    topic_ids = []
    for item in value:
        topic_id = _parse_topic_plan_topic_id(item)
        if topic_id not in topic_ids:
            topic_ids.append(topic_id)
    return topic_ids


def _topic_plan_topic_dependency_counts(cur, topic_ids):
    counts = {int(topic_id): {"prompt_count": 0, "query_count": 0} for topic_id in topic_ids}
    if not topic_ids or not _table_exists(cur, "prompts"):
        return counts
    prompt_cols = _table_columns(cur, "prompts")
    if not {"id", "topic_id"}.issubset(prompt_cols):
        return counts
    has_queries = _table_exists(cur, "queries") and "prompt_id" in _table_columns(cur, "queries")
    query_count_expr = "COUNT(q.id)::int" if has_queries else "0::int"
    query_join = "LEFT JOIN queries q ON q.prompt_id = p.id" if has_queries else ""
    cur.execute(
        f"""
        SELECT p.topic_id,
               COUNT(DISTINCT p.id)::int AS prompt_count,
               {query_count_expr} AS query_count
        FROM prompts p
        {query_join}
        WHERE p.topic_id = ANY(%s)
        GROUP BY p.topic_id
        """,
        (topic_ids,),
    )
    for row in cur.fetchall():
        topic_id = int(row["topic_id"])
        counts[topic_id] = {
            "prompt_count": int(row.get("prompt_count") or 0),
            "query_count": int(row.get("query_count") or 0),
        }
    return counts


def _delete_topic_plan_topics(cur, topic_ids):
    if not topic_ids or not _table_exists(cur, "topics"):
        return {"deleted": [], "blocked": [], "missing": topic_ids or []}

    cur.execute(
        """
        SELECT t.id, t.brand_id, t.text, t.category, t.status,
               b.name AS brand_name,
               COALESCE(NULLIF(b.industry, ''), 'Uncategorized') AS industry
        FROM topics t
        LEFT JOIN brands b ON b.id = t.brand_id
        WHERE t.id = ANY(%s)
        ORDER BY t.id
        """,
        (topic_ids,),
    )
    rows = [dict(row) for row in cur.fetchall()]
    found_ids = {int(row["id"]) for row in rows}
    missing = [topic_id for topic_id in topic_ids if topic_id not in found_ids]
    dependencies = _topic_plan_topic_dependency_counts(cur, list(found_ids))

    blocked = []
    deletable_ids = []
    for row in rows:
        topic_id = int(row["id"])
        dep = dependencies.get(topic_id, {"prompt_count": 0, "query_count": 0})
        if dep["prompt_count"] > 0 or dep["query_count"] > 0:
            blocked.append(
                {
                    "id": f"T-{topic_id}",
                    "raw_id": topic_id,
                    "title": row.get("text"),
                    "brand": row.get("brand_name"),
                    "prompt_count": dep["prompt_count"],
                    "query_count": dep["query_count"],
                    "reason": "has_downstream_dependencies",
                }
            )
        else:
            deletable_ids.append(topic_id)

    deleted = []
    if deletable_ids:
        if _table_exists(cur, "topic_candidates"):
            cur.execute(
                """
                UPDATE topic_candidates
                SET approved_topic_id = NULL,
                    updated_at = NOW()
                WHERE approved_topic_id = ANY(%s)
                """,
                (deletable_ids,),
            )
        cur.execute(
            """
            DELETE FROM topics
            WHERE id = ANY(%s)
            RETURNING id
            """,
            (deletable_ids,),
        )
        deleted_ids = {int(row["id"]) for row in cur.fetchall()}
        deleted = [
            {
                "id": f"T-{int(row['id'])}",
                "raw_id": int(row["id"]),
                "title": row.get("text"),
                "brand": row.get("brand_name"),
                "industry": row.get("industry"),
            }
            for row in rows
            if int(row["id"]) in deleted_ids
        ]

    return {"deleted": deleted, "blocked": blocked, "missing": missing}


def _fetch_topic_plan_candidates(cur, status="pending", brand_ids=None, query=None, limit=100):
    if not _table_exists(cur, "topic_candidates"):
        return []
    where = []
    params = []
    if status and status != "all":
        where.append("status = %s")
        params.append(status)
    if brand_ids:
        where.append("brand_id = ANY(%s)")
        params.append(brand_ids)
    if query:
        like = f"%{query}%"
        where.append(
            "(title ILIKE %s OR brand_name ILIKE %s OR reason ILIKE %s OR coverage_gap ILIKE %s OR id ILIKE %s)"
        )
        params.extend([like, like, like, like, like])
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    cur.execute(
        f"""
        SELECT *
        FROM topic_candidates
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        params + [limit],
    )
    return [_topic_plan_candidate_row(row) for row in cur.fetchall()]


def _review_topic_plan_candidate(cur, candidate_id, requested_status, admin_id, reason=None):
    cur.execute(
        "SELECT * FROM topic_candidates WHERE id = %s FOR UPDATE",
        (candidate_id,),
    )
    candidate = cur.fetchone()
    if not candidate:
        return None

    new_status = transition_candidate_status(candidate["status"], requested_status)
    approved_topic_id = candidate.get("approved_topic_id")
    if new_status == "approved":
        if not _table_exists(cur, "topics"):
            raise TopicPlanLLMError("topics_table_missing", "Topics table is missing")
        existing = _fetch_topic_rows_for_brands(cur, [int(candidate["brand_id"])])
        duplicate = next(
            (
                row
                for row in existing
                if normalize_topic_title(row.get("text") or "")
                == candidate.get("normalized_title")
            ),
            None,
        )
        if duplicate:
            approved_topic_id = duplicate["id"]
        else:
            topic_cols = _table_columns(cur, "topics")
            columns = ["brand_id", "text"]
            values = [candidate["brand_id"], candidate["title"]]
            placeholders = ["%s", "%s"]
            if "category" in topic_cols:
                columns.append("category")
                values.append(candidate["dimension"])
                placeholders.append("%s")
            if "generated_by" in topic_cols:
                columns.append("generated_by")
                values.append("topic-plan")
                placeholders.append("%s")
            if "status" in topic_cols:
                columns.append("status")
                values.append("active")
                placeholders.append("%s")
            if "created_at" in topic_cols:
                columns.append("created_at")
                placeholders.append("NOW()")
            cur.execute(
                f"""
                INSERT INTO topics ({", ".join(columns)})
                VALUES ({", ".join(placeholders)})
                RETURNING id
                """,
                values,
            )
            approved_topic_id = cur.fetchone()["id"]

    cur.execute(
        """
        UPDATE topic_candidates
        SET status = %s,
            reviewed_by = %s,
            reviewed_at = NOW(),
            review_reason = %s,
            approved_topic_id = %s,
            updated_at = NOW()
        WHERE id = %s
        RETURNING *
        """,
        (
            new_status,
            admin_id,
            reason,
            approved_topic_id,
            candidate_id,
        ),
    )
    updated = _topic_plan_candidate_row(cur.fetchone())
    _insert_admin_audit_log(
        cur,
        operator_id=admin_id,
        action="review_topic_candidate",
        target_type="topic_candidate",
        target_id=candidate_id,
        diff={
            "status": {"before": candidate["status"], "after": new_status},
            "approved_topic_id": approved_topic_id,
        },
        reason=reason or "topic_candidate_review",
    )
    return updated


def _topic_plan_error_response(error, status_code=400):
    if isinstance(error, TopicPlanLLMError):
        return jsonify({"success": False, "error": error.code, "message": error.message}), status_code
    return jsonify({"success": False, "error": str(error)}), status_code


def _prompt_matrix_json(value):
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _prompt_matrix_error_response(error, status_code=400):
    if isinstance(error, PromptMatrixError):
        return jsonify({"success": False, "error": error.code, "message": error.message}), status_code
    return jsonify({"success": False, "error": str(error)}), status_code


def _prompt_matrix_json_value(value, default=None):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def _prompt_matrix_parse_topic_id(value):
    text = str(value or "").strip()
    if text.upper().startswith("T-"):
        text = text[2:]
    if not text.isdigit():
        raise ValueError("invalid_topic_id")
    return int(text)


def _prompt_matrix_parse_topic_ids(value):
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else str(value).split(",")
    result = []
    for item in raw_items:
        if str(item).strip() == "":
            continue
        topic_id = _prompt_matrix_parse_topic_id(item)
        if topic_id not in result:
            result.append(topic_id)
    return result


def _prompt_matrix_filter_payload(source):
    try:
        brand_id = source.get("brand_id")
        if brand_id in ("", None, "all"):
            brand_id = None
        elif isinstance(brand_id, list):
            brand_id = None
        else:
            brand_id = int(brand_id)
    except (TypeError, ValueError):
        raise ValueError("invalid_brand_id")

    dimension = (source.get("dimension") or "").strip().lower() or None
    if dimension and dimension not in {"brand", "product", "category", "scenario", "question"}:
        raise ValueError("invalid_dimension")

    coverage = (source.get("coverage") or "all").strip().lower()
    if coverage not in {"all", "gap", "partial", "covered", "risk"}:
        raise ValueError("invalid_coverage")

    return {
        "q": (source.get("q") or source.get("search") or "").strip(),
        "brand_id": brand_id,
        "industry_id": (source.get("industry_id") or "").strip() or None,
        "dimension": dimension,
        "coverage": coverage,
        "intent_count": _clamp_int(source.get("intent_count"), 4, 1, len(ALLOWED_INTENTS)),
        "language_count": _clamp_int(source.get("language_count"), 2, 1, len(ALLOWED_LANGUAGES)),
    }


def _prompt_matrix_topic_required(filters_or_config):
    intent_count = filters_or_config.get("intent_count") or len(ALLOWED_INTENTS)
    language_count = filters_or_config.get("language_count") or len(ALLOWED_LANGUAGES)
    return set(selected_intents(intent_count)), set(selected_languages(language_count))


def _prompt_matrix_brand_rows(cur):
    if not _table_exists(cur, "brands"):
        return []
    cols = _table_columns(cur, "brands")
    name_expr = "name" if "name" in cols else "('Brand #' || id::text)"
    industry_expr = (
        "COALESCE(NULLIF(industry, ''), 'Uncategorized')"
        if "industry" in cols
        else "'Uncategorized'"
    )
    aliases_expr = "aliases" if "aliases" in cols else "NULL::jsonb AS aliases"
    cur.execute(
        f"""
        SELECT id, {name_expr} AS name, {industry_expr} AS industry, {aliases_expr}
        FROM brands
        ORDER BY name
        """
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        rows.append(
            {
                "id": int(item.get("id")),
                "name": item.get("name") or f"Brand #{item.get('id')}",
                "industry_id": item.get("industry") or "Uncategorized",
                "industry_name": item.get("industry") or "Uncategorized",
                "aliases": _prompt_matrix_json_value(item.get("aliases"), []),
            }
        )
    return rows


def _prompt_matrix_prompt_meta_join(cur):
    if not _table_exists(cur, "prompts"):
        return "LEFT JOIN (SELECT NULL::int AS topic_id, 0::int AS prompt_count WHERE FALSE) pm ON pm.topic_id = t.id"
    prompt_cols = _table_columns(cur, "prompts")
    if not {"id", "topic_id"}.issubset(prompt_cols):
        return "LEFT JOIN (SELECT NULL::int AS topic_id, 0::int AS prompt_count WHERE FALSE) pm ON pm.topic_id = t.id"
    intent_expr = "NULLIF(intent, '')" if "intent" in prompt_cols else "NULL::text"
    language_expr = "NULLIF(language, '')" if "language" in prompt_cols else "NULL::text"
    status_where = "WHERE COALESCE(status, 'active') = 'active'" if "status" in prompt_cols else ""
    return f"""
        LEFT JOIN (
            SELECT topic_id,
                   COUNT(id)::int AS prompt_count,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT {intent_expr}), NULL) AS prompt_intents,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT {language_expr}), NULL) AS prompt_languages
            FROM prompts
            {status_where}
            GROUP BY topic_id
        ) pm ON pm.topic_id = t.id
    """


def _prompt_matrix_topic_row(row, required_intents, required_languages, known_brands=None):
    item = dict(row)
    raw_id = int(item.get("id"))
    dimension = _topic_plan_dimension(item.get("category"))
    prompt_intents = {
        str(value)
        for value in (item.get("prompt_intents") or [])
        if value and str(value) in ALLOWED_INTENTS
    }
    prompt_languages = {
        str(value)
        for value in (item.get("prompt_languages") or [])
        if value and str(value) in ALLOWED_LANGUAGES
    }
    prompt_count = int(item.get("prompt_count") or 0)
    missing_intents = sorted(required_intents - prompt_intents)
    missing_languages = sorted(required_languages - prompt_languages)
    coverage = "covered"
    if prompt_count == 0:
        coverage = "gap"
    elif missing_intents or missing_languages:
        coverage = "partial"
    leak_count = int(item.get("brand_leak_count") or 0)
    if dimension == "category" and leak_count > 0:
        coverage = "risk"

    updated = item.get("updated_at") or item.get("created_at")
    return {
        "id": f"T-{raw_id}",
        "raw_id": raw_id,
        "title": item.get("text") or "",
        "brand": item.get("brand_name") or f"Brand #{item.get('brand_id')}",
        "brand_id": item.get("brand_id"),
        "industry": item.get("industry") or "Uncategorized",
        "industry_id": item.get("industry") or "Uncategorized",
        "dimension": _topic_plan_dimension_label(dimension),
        "dimension_key": dimension,
        "coverage": coverage,
        "coverageLabel": {
            "gap": "No Prompt",
            "partial": "Intent / language gap",
            "risk": "Quality risk",
            "covered": "Covered",
        }.get(coverage, coverage),
        "priority": "P0" if coverage == "risk" else "P1" if coverage == "gap" else "P2" if coverage == "partial" else "P3",
        "updatedAt": _isoformat(updated) or "",
        "prompt_count": prompt_count,
        "prompt_intents": sorted(prompt_intents),
        "prompt_languages": sorted(prompt_languages),
        "missing_intents": missing_intents,
        "missing_languages": missing_languages,
        "brand_leak_count": leak_count,
        "selected": False,
    }


def _fetch_prompt_matrix_topics(cur, filters=None, page=1, per_page=20, topic_ids=None):
    filters = filters or {}
    required_intents, required_languages = _prompt_matrix_topic_required(filters)
    if not _table_exists(cur, "topics") or not _table_exists(cur, "brands"):
        return [], 0, {"topicsTotal": 0, "matchingTopics": 0}

    topic_cols = _table_columns(cur, "topics")
    if not {"id", "brand_id", "text"}.issubset(topic_cols):
        return [], 0, {"topicsTotal": 0, "matchingTopics": 0}

    category_select = "t.category" if "category" in topic_cols else "NULL::text AS category"
    created_select = "t.created_at AS created_at" if "created_at" in topic_cols else "NULL::timestamp AS created_at"
    if "updated_at" in topic_cols:
        updated_select = "t.updated_at AS updated_at"
    elif "created_at" in topic_cols:
        updated_select = "t.created_at AS updated_at"
    else:
        updated_select = "NULL::timestamp AS updated_at"
    order_expr = "t.created_at DESC NULLS LAST, t.id DESC" if "created_at" in topic_cols else "t.id DESC"
    status_condition = ""
    if "status" in topic_cols:
        status_condition = "AND COALESCE(t.status, 'active') <> 'archived'"

    where = ["1=1"]
    params = []
    if topic_ids:
        where.append("t.id = ANY(%s)")
        params.append(topic_ids)
    if filters.get("brand_id"):
        where.append("t.brand_id = %s")
        params.append(filters["brand_id"])
    if filters.get("industry_id"):
        where.append("COALESCE(NULLIF(b.industry, ''), 'Uncategorized') = %s")
        params.append(filters["industry_id"])
    query = filters.get("q")
    if query:
        like = f"%{query}%"
        where.append("(t.text ILIKE %s OR b.name ILIKE %s OR ('T-' || t.id::text) ILIKE %s)")
        params.extend([like, like, like])

    prompt_join = _prompt_matrix_prompt_meta_join(cur)
    cur.execute(
        f"""
        SELECT t.id, t.brand_id, t.text, {category_select},
               {created_select}, {updated_select},
               b.name AS brand_name,
               COALESCE(NULLIF(b.industry, ''), 'Uncategorized') AS industry,
               COALESCE(pm.prompt_count, 0) AS prompt_count,
               COALESCE(pm.prompt_intents, ARRAY[]::text[]) AS prompt_intents,
               COALESCE(pm.prompt_languages, ARRAY[]::text[]) AS prompt_languages,
               0::int AS brand_leak_count
        FROM topics t
        JOIN brands b ON b.id = t.brand_id
        {prompt_join}
        WHERE {" AND ".join(where)}
        {status_condition}
        ORDER BY {order_expr}
        """,
        params,
    )
    rows = [
        _prompt_matrix_topic_row(row, required_intents, required_languages)
        for row in cur.fetchall()
    ]
    dimension = filters.get("dimension")
    if dimension:
        rows = [row for row in rows if row.get("dimension_key") == dimension]
    coverage = filters.get("coverage") or "all"
    if coverage != "all":
        rows = [row for row in rows if row.get("coverage") == coverage]

    total = len(rows)
    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 20), 20000))
    start = (page - 1) * per_page
    paged = rows[start:start + per_page]
    summary = {
        "topicsTotal": total,
        "matchingTopics": total,
        "topicsNoPrompt": sum(1 for row in rows if row["coverage"] == "gap"),
        "topicsPartialIntent": sum(1 for row in rows if row["coverage"] == "partial"),
        "topicsRisk": sum(1 for row in rows if row["coverage"] == "risk"),
    }
    return paged, total, summary


def _fetch_prompt_matrix_topic_ids(cur, filters):
    rows, total, _summary = _fetch_prompt_matrix_topics(cur, filters=filters, page=1, per_page=100)
    if len(rows) < total:
        # Use a large server-side page only for explicit "all matching" operations.
        rows, _total, _summary = _fetch_prompt_matrix_topics(
            cur,
            filters=filters,
            page=1,
            per_page=min(max(total, 1), 20000),
        )
    return [int(row["raw_id"]) for row in rows]


def _fetch_prompt_matrix_topics_by_ids(cur, topic_ids, config=None):
    if not topic_ids:
        return []
    filters = {
        "intent_count": (config or {}).get("intent_count", len(ALLOWED_INTENTS)),
        "language_count": (config or {}).get("language_count", len(ALLOWED_LANGUAGES)),
    }
    rows, _total, _summary = _fetch_prompt_matrix_topics(
        cur,
        filters=filters,
        page=1,
        per_page=min(max(len(topic_ids), 1), 20000),
        topic_ids=topic_ids,
    )
    by_id = {int(row["raw_id"]): row for row in rows}
    return [by_id[topic_id] for topic_id in topic_ids if topic_id in by_id]


def _fetch_prompt_matrix_prompt_texts(cur, topic_ids=None):
    if not _table_exists(cur, "prompts"):
        return []
    cols = _table_columns(cur, "prompts")
    if "text" not in cols:
        return []
    where = []
    params = []
    if topic_ids and "topic_id" in cols:
        where.append("topic_id = ANY(%s)")
        params.append(topic_ids)
    if "status" in cols:
        where.append("COALESCE(status, 'active') = 'active'")
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    cur.execute(f"SELECT text FROM prompts {where_clause}", params)
    return [row["text"] for row in cur.fetchall() if row.get("text")]


def _prompt_matrix_selection_from_payload(cur, payload):
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    mode = selection.get("mode") or payload.get("selection_mode") or "explicit"
    if mode == "all_matching":
        try:
            filters = _prompt_matrix_filter_payload(selection.get("filters") or payload.get("filters") or {})
            excluded = set(_prompt_matrix_parse_topic_ids(selection.get("excluded_topic_ids") or []))
        except ValueError as error:
            raise PromptMatrixError(str(error), str(error)) from error
        topic_ids = [topic_id for topic_id in _fetch_prompt_matrix_topic_ids(cur, filters) if topic_id not in excluded]
        return topic_ids, {"mode": "all_matching", "filters": filters, "excluded_topic_ids": sorted(excluded)}
    try:
        topic_ids = _prompt_matrix_parse_topic_ids(selection.get("topic_ids") or payload.get("topic_ids") or [])
    except ValueError as error:
        raise PromptMatrixError(str(error), str(error)) from error
    return topic_ids, {"mode": "explicit", "topic_ids": topic_ids}


def _prompt_matrix_candidate_row(row):
    item = dict(row)
    tags = _prompt_matrix_json_value(item.get("tags"), {}) or {}
    display_tags = {key: value for key, value in tags.items() if key != "engines"}
    return {
        "id": item.get("id"),
        "run_id": item.get("run_id"),
        "topic_id": item.get("topic_id"),
        "topicId": f"T-{item.get('topic_id')}",
        "topic": item.get("topic_text") or "",
        "brand_id": item.get("brand_id"),
        "brand": item.get("brand_name"),
        "dimension": item.get("dimension"),
        "intent": item.get("intent"),
        "language": item.get("language"),
        "lang": item.get("language"),
        "template_strategy": item.get("template_strategy"),
        "template_version": item.get("template_version"),
        "text": item.get("text"),
        "status": item.get("status"),
        "confidence": float(item.get("confidence") or 0),
        "reason": item.get("reason") or item.get("review_reason") or "",
        "duplicate_of": item.get("duplicate_of"),
        "tags": display_tags,
        "engines": [],
        "routing": display_tags.get("routing") or "deferred_to_query_pool",
        "source": display_tags.get("source") or "prompt_matrix",
        "approved_prompt_id": item.get("approved_prompt_id"),
        "created_at": _isoformat(item.get("created_at")),
        "reviewed_at": _isoformat(item.get("reviewed_at")),
    }


def _prompt_matrix_candidate_where(status="pending", query=None):
    where = []
    params = []
    if status and status != "all":
        where.append("status = %s")
        params.append(status)
    if query:
        like = f"%{query}%"
        where.append("(text ILIKE %s OR topic_text ILIKE %s OR reason ILIKE %s OR id ILIKE %s)")
        params.extend([like, like, like, like])
    return where, params


def _fetch_prompt_matrix_candidates(
    cur,
    status="pending",
    query=None,
    limit=100,
    offset=0,
    include_total=False,
):
    if not _table_exists(cur, "prompt_candidates"):
        return ([], 0) if include_total else []
    where, params = _prompt_matrix_candidate_where(status=status, query=query)
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    cur.execute(
        f"""
        SELECT *, COUNT(*) OVER() AS __total
        FROM prompt_candidates
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )
    raw_rows = cur.fetchall()
    rows = [_prompt_matrix_candidate_row(row) for row in raw_rows]
    total = int(raw_rows[0].get("__total") or 0) if raw_rows else 0
    return (rows, total) if include_total else rows


def _prompt_matrix_candidate_status_counts(cur, query=None):
    counts = {"pending": 0, "approved": 0, "rejected": 0, "all": 0}
    if not _table_exists(cur, "prompt_candidates"):
        return counts
    where, params = _prompt_matrix_candidate_where(status="all", query=query)
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    cur.execute(
        f"""
        SELECT status, COUNT(*)::int AS count
        FROM prompt_candidates
        {where_clause}
        GROUP BY status
        """,
        params,
    )
    for row in cur.fetchall():
        status = row.get("status")
        count = int(row.get("count") or 0)
        if status in counts:
            counts[status] = count
        counts["all"] += count
    return counts


def _prompt_matrix_category_purity(cur, known_brands):
    if not _table_exists(cur, "topics") or not _table_exists(cur, "prompts"):
        return {"total": 0, "brandLeaks": 0, "status": "pass"}
    topic_cols = _table_columns(cur, "topics")
    prompt_cols = _table_columns(cur, "prompts")
    if "category" not in topic_cols or not {"topic_id", "text"}.issubset(prompt_cols):
        return {"total": 0, "brandLeaks": 0, "status": "pass"}
    status_where = "AND COALESCE(p.status, 'active') = 'active'" if "status" in prompt_cols else ""
    cur.execute(
        f"""
        SELECT p.id, p.text, t.category
        FROM prompts p
        JOIN topics t ON t.id = p.topic_id
        WHERE t.category IS NOT NULL
        {status_where}
        """
    )
    total = 0
    leaks = 0
    for row in cur.fetchall():
        if _topic_plan_dimension(row.get("category")) != "category":
            continue
        total += 1
        if detect_brand_leaks(row.get("text") or "", known_brands):
            leaks += 1
    return {"total": total, "brandLeaks": leaks, "status": "pass" if leaks == 0 else "fail"}


def _prompt_matrix_distribution(cur, column, allowed_values):
    if not _table_exists(cur, "prompts"):
        return {value: 0 for value in allowed_values}
    cols = _table_columns(cur, "prompts")
    if column not in cols:
        return {value: 0 for value in allowed_values}
    status_where = "WHERE COALESCE(status, 'active') = 'active'" if "status" in cols else ""
    cur.execute(
        f"""
        SELECT {column} AS value, COUNT(*)::int AS count
        FROM prompts
        {status_where}
        GROUP BY {column}
        """
    )
    result = {value: 0 for value in allowed_values}
    for row in cur.fetchall():
        value = row.get("value")
        if value in result:
            result[value] = int(row.get("count") or 0)
    return result


def _prompt_matrix_stats(cur):
    known_brands = _prompt_matrix_brand_rows(cur)
    all_rows, total_topics, topic_summary = _fetch_prompt_matrix_topics(
        cur,
        filters={"intent_count": len(ALLOWED_INTENTS), "language_count": len(ALLOWED_LANGUAGES)},
        page=1,
        per_page=20000,
    )
    total_prompts = 0
    if _table_exists(cur, "prompts"):
        cols = _table_columns(cur, "prompts")
        if "id" in cols:
            status_where = "WHERE COALESCE(status, 'active') = 'active'" if "status" in cols else ""
            cur.execute(f"SELECT COUNT(*) AS cnt FROM prompts {status_where}")
            total_prompts = int(cur.fetchone()["cnt"] or 0)

    topics_with_prompt = sum(1 for row in all_rows if int(row.get("prompt_count") or 0) > 0)
    coverage_pct = round((topics_with_prompt / total_topics) * 100, 1) if total_topics else 0
    intent_counts = _prompt_matrix_distribution(cur, "intent", ALLOWED_INTENTS)
    lang_counts = _prompt_matrix_distribution(cur, "language", ALLOWED_LANGUAGES)
    total_intent = sum(intent_counts.values()) or 1
    total_lang = sum(lang_counts.values()) or 1
    colors = {
        "informational": "#3B82F6",
        "commercial": "#8B5CF6",
        "transactional": "#0ABB87",
        "navigational": "#F5A623",
    }
    labels = {
        "informational": "信息了解",
        "commercial": "购买决策",
        "transactional": "行动导向",
        "navigational": "定向查找",
    }
    lang_labels = {"zh-CN": "中文", "en-US": "英文"}
    lang_routing = {"zh-CN": "调度时路由", "en-US": "调度时路由"}

    last_run_at = None
    if _table_exists(cur, "prompt_generation_runs"):
        cur.execute("SELECT created_at FROM prompt_generation_runs ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            last_run_at = _isoformat(row.get("created_at"))

    return {
        "lastRunAt": last_run_at or "Never",
        "topicsWithPrompt": topics_with_prompt,
        "topicsTotal": total_topics,
        "topicsNoPrompt": topic_summary.get("topicsNoPrompt", 0),
        "topicsPartialIntent": topic_summary.get("topicsPartialIntent", 0),
        "coveragePct": coverage_pct,
        "totalPrompts": total_prompts,
        "intentDist": [
            {
                "intent": intent,
                "label": labels[intent],
                "count": intent_counts[intent],
                "pct": round((intent_counts[intent] / total_intent) * 100),
                "color": colors[intent],
            }
            for intent in ALLOWED_INTENTS
        ],
        "langDist": [
            {
                "lang": language,
                "label": lang_labels[language],
                "count": lang_counts[language],
                "pct": round((lang_counts[language] / total_lang) * 100),
                "engines": lang_routing[language],
                "routing": "deferred_to_query_pool",
            }
            for language in ALLOWED_LANGUAGES
        ],
        "categoryPromptPurity": _prompt_matrix_category_purity(cur, known_brands),
    }


def _prompt_matrix_quality_gates(stats, pending_count=0, duplicate_count=0):
    purity = stats.get("categoryPromptPurity") or {}
    brand_leaks = int(purity.get("brandLeaks") or 0)
    return [
        {
            "title": "矩阵覆盖",
            "value": f"{stats.get('coveragePct', 0)}%",
            "tone": "success" if float(stats.get("coveragePct") or 0) >= 80 else "warning",
            "meta": f"{stats.get('topicsWithPrompt', 0)} / {stats.get('topicsTotal', 0)} topics",
        },
        {
            "title": "待审核",
            "value": str(pending_count),
            "tone": "warning" if pending_count else "success",
            "meta": "Prompt candidates",
        },
        {
            "title": "品类纯净",
            "value": "0 泄露" if brand_leaks == 0 else f"{brand_leaks} 泄露",
            "tone": "success" if brand_leaks == 0 else "danger",
            "meta": "Category topics must not mention brands",
        },
        {
            "title": "相似重复",
            "value": str(duplicate_count),
            "tone": "warning" if duplicate_count else "success",
            "meta": "Duplicate candidates / prompts",
        },
    ]


def _prompt_matrix_gaps_for_topics(cur, topic_ids=None, filters=None, config=None, limit=200):
    config = config or {"intent_count": len(ALLOWED_INTENTS), "language_count": len(ALLOWED_LANGUAGES)}
    if topic_ids:
        topics = _fetch_prompt_matrix_topics_by_ids(cur, topic_ids, config)
    else:
        merged_filters = {
            **(filters or {}),
            "intent_count": config.get("intent_count", len(ALLOWED_INTENTS)),
            "language_count": config.get("language_count", len(ALLOWED_LANGUAGES)),
        }
        topics, _total, _summary = _fetch_prompt_matrix_topics(cur, filters=merged_filters, page=1, per_page=limit)
    combo_count = len(intent_language_combinations(
        config.get("intent_count"),
        config.get("language_count"),
        config.get("max_per_topic", 4),
    ))
    gaps = []
    for topic in topics:
        reasons = []
        if topic["coverage"] == "gap":
            reasons.append("No Prompt")
        if topic.get("missing_intents"):
            reasons.append("Missing intent: " + ", ".join(topic["missing_intents"]))
        if topic.get("missing_languages"):
            reasons.append("Missing language: " + ", ".join(topic["missing_languages"]))
        if topic.get("brand_leak_count"):
            reasons.append("Category brand leak risk")
        if not reasons:
            continue
        gaps.append(
            {
                "id": f"PG-{topic['raw_id']}",
                "topic_id": topic["raw_id"],
                "topic": topic["title"],
                "gap": " / ".join(reasons),
                "priority": topic["priority"],
                "estimate": combo_count if topic["coverage"] == "gap" else max(1, len(topic.get("missing_intents") or []) + len(topic.get("missing_languages") or [])),
            }
        )
    return gaps[:limit]


def _fetch_prompt_matrix_prompts(cur, intent=None, language=None, query=None, page=1, per_page=50):
    if not _table_exists(cur, "prompts"):
        return [], 0
    prompt_cols = _table_columns(cur, "prompts")
    if not {"id", "topic_id", "text"}.issubset(prompt_cols):
        return [], 0
    topic_join = ""
    topic_select = "NULL::text AS topic_text"
    if _table_exists(cur, "topics") and "id" in _table_columns(cur, "topics"):
        topic_join = "LEFT JOIN topics t ON t.id = p.topic_id"
        topic_select = "t.text AS topic_text"
    intent_select = "p.intent" if "intent" in prompt_cols else "NULL::text AS intent"
    language_select = "p.language" if "language" in prompt_cols else "NULL::text AS language"
    template_strategy_select = "p.template_strategy" if "template_strategy" in prompt_cols else "NULL::text AS template_strategy"
    template_version_select = "p.template_version" if "template_version" in prompt_cols else "NULL::text AS template_version"
    status_select = "COALESCE(p.status, 'active') AS status" if "status" in prompt_cols else "'active'::text AS status"
    tags_select = "p.tags" if "tags" in prompt_cols else "NULL::jsonb AS tags"
    created_select = "p.created_at AS created_at" if "created_at" in prompt_cols else "NULL::timestamp AS created_at"
    order_expr = "p.created_at DESC NULLS LAST, p.id DESC" if "created_at" in prompt_cols else "p.id DESC"

    where = []
    params = []
    if intent and "intent" in prompt_cols:
        where.append("p.intent = %s")
        params.append(intent)
    if language and "language" in prompt_cols:
        where.append("p.language = %s")
        params.append(language)
    query = (query or "").strip()
    if query:
        like_query = f"%{query}%"
        search_parts = ["p.text ILIKE %s", "CAST(p.id AS TEXT) ILIKE %s"]
        params.extend([like_query, like_query])
        if topic_join:
            search_parts.append("t.text ILIKE %s")
            params.append(like_query)
        where.append("(" + " OR ".join(search_parts) + ")")
    if "status" in prompt_cols:
        where.append("COALESCE(p.status, 'active') <> 'rejected'")
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 50), 100))
    offset = (page - 1) * per_page

    cur.execute(f"SELECT COUNT(*) AS cnt FROM prompts p {topic_join} {where_clause}", params)
    total = int(cur.fetchone()["cnt"] or 0)
    cur.execute(
        f"""
        SELECT p.id, p.topic_id, p.text, {topic_select}, {intent_select}, {language_select},
               {template_strategy_select}, {template_version_select}, {status_select},
               {tags_select}, {created_select}
        FROM prompts p
        {topic_join}
        {where_clause}
        ORDER BY {order_expr}
        LIMIT %s OFFSET %s
        """,
        params + [per_page, offset],
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        tags = _prompt_matrix_json_value(item.get("tags"), {}) or {}
        display_tags = {key: value for key, value in tags.items() if key != "engines"}
        language_value = item.get("language") or "zh-CN"
        rows.append(
            {
                "id": item.get("id"),
                "topicId": f"T-{item.get('topic_id')}",
                "topic_id": item.get("topic_id"),
                "topicTitle": item.get("topic_text") or "",
                "intent": item.get("intent") or "informational",
                "lang": language_value,
                "language": language_value,
                "engines": [],
                "routing": display_tags.get("routing") or "deferred_to_query_pool",
                "tags": display_tags,
                "source": display_tags.get("source") or "prompt_matrix",
                "run_id": display_tags.get("run_id"),
                "candidate_id": display_tags.get("candidate_id"),
                "confidence": float(display_tags.get("confidence") or 0),
                "version": item.get("template_version") or "v1",
                "templateStrategy": item.get("template_strategy") or "latest",
                "status": item.get("status") or "active",
                "templateText": item.get("text") or "",
                "resolvedExample": item.get("text") or "",
                "createdAt": _isoformat(item.get("created_at")),
            }
        )
    return rows, total


def _review_prompt_matrix_candidate(cur, candidate_id, requested_status, admin_id, reason=None):
    cur.execute("SELECT * FROM prompt_candidates WHERE id = %s FOR UPDATE", (candidate_id,))
    candidate = cur.fetchone()
    if not candidate:
        return None
    new_status = transition_prompt_candidate_status(candidate["status"], requested_status)
    approved_prompt_id = candidate.get("approved_prompt_id")
    if new_status == "approved":
        if not _table_exists(cur, "prompts"):
            raise PromptMatrixError("prompts_table_missing", "Prompts table is missing")
        prompt_cols = _table_columns(cur, "prompts")
        if not {"topic_id", "text"}.issubset(prompt_cols):
            raise PromptMatrixError("prompts_schema_invalid", "Prompts table must contain topic_id and text")
        if not is_natural_user_prompt(candidate.get("text") or ""):
            raise PromptMatrixError("prompt_not_natural", "Prompt must be a natural consumer question")
        if has_prompt_language_mismatch(candidate.get("text") or "", candidate.get("language") or ""):
            raise PromptMatrixError(
                "prompt_language_mismatch",
                "Prompt language does not match its text",
            )
        if _table_exists(cur, "topics"):
            topic_cols = _table_columns(cur, "topics")
            if "category" in topic_cols:
                cur.execute("SELECT category FROM topics WHERE id = %s", (candidate["topic_id"],))
                topic_row = cur.fetchone()
                if topic_row and _topic_plan_dimension(topic_row.get("category")) == "category":
                    if detect_brand_leaks(candidate.get("text") or "", _prompt_matrix_brand_rows(cur)):
                        raise PromptMatrixError(
                            "category_brand_leak",
                            "Category prompt leaks a known brand name",
                        )
        raw_tags = _prompt_matrix_json_value(candidate.get("tags"), {}) or {}
        tags = {key: value for key, value in raw_tags.items() if key != "engines"}
        tags.update(
            {
                "source": "prompt_matrix",
                "routing": "deferred_to_query_pool",
                "run_id": candidate.get("run_id"),
                "candidate_id": candidate.get("id"),
                "confidence": candidate.get("confidence"),
            }
        )
        columns = ["topic_id", "text"]
        placeholders = ["%s", "%s"]
        values = [candidate["topic_id"], candidate["text"]]
        optional_values = {
            "intent": candidate.get("intent"),
            "language": candidate.get("language"),
            "template_strategy": candidate.get("template_strategy"),
            "template_version": candidate.get("template_version"),
            "status": "active",
            "tags": _prompt_matrix_json(tags),
            "generated_by": "prompt-matrix",
        }
        for col, value in optional_values.items():
            if col not in prompt_cols:
                continue
            columns.append(col)
            if col == "tags":
                placeholders.append("%s::jsonb")
            else:
                placeholders.append("%s")
            values.append(value)
        if "created_at" in prompt_cols:
            columns.append("created_at")
            placeholders.append("NOW()")
        if "updated_at" in prompt_cols:
            columns.append("updated_at")
            placeholders.append("NOW()")
        cur.execute(
            f"""
            INSERT INTO prompts ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            RETURNING id
            """,
            values,
        )
        approved_prompt_id = cur.fetchone()["id"]

    cur.execute(
        """
        UPDATE prompt_candidates
        SET status = %s,
            reviewed_by = %s,
            reviewed_at = NOW(),
            review_reason = %s,
            approved_prompt_id = %s,
            updated_at = NOW()
        WHERE id = %s
        RETURNING *
        """,
        (new_status, admin_id, reason, approved_prompt_id, candidate_id),
    )
    updated = _prompt_matrix_candidate_row(cur.fetchone())
    _insert_admin_audit_log(
        cur,
        operator_id=admin_id,
        action="review_prompt_candidate",
        target_type="prompt_candidate",
        target_id=candidate_id,
        diff={
            "status": {"before": candidate["status"], "after": new_status},
            "approved_prompt_id": approved_prompt_id,
        },
        reason=reason or "prompt_candidate_review",
    )
    return updated


def _user_name_expr(columns):
    candidates = []
    if "name" in columns:
        candidates.append("NULLIF(u.name, '')")
    if "name_zh" in columns:
        candidates.append("NULLIF(u.name_zh, '')")
    if "name_en" in columns:
        candidates.append("NULLIF(u.name_en, '')")
    if not candidates:
        return "NULL::text"
    return "COALESCE(" + ", ".join(candidates) + ")"


def _user_company_expr(columns):
    candidates = []
    if "company" in columns:
        candidates.append("NULLIF(u.company, '')")
    if "preferences" in columns:
        candidates.append("NULLIF(u.preferences->>'company', '')")
    if not candidates:
        return "NULL::text"
    return "COALESCE(" + ", ".join(candidates) + ")"


def _user_locale_expr(columns):
    candidates = []
    if "locale" in columns:
        candidates.append("NULLIF(u.locale, '')")
    if "preferences" in columns:
        candidates.append("NULLIF(u.preferences->>'locale', '')")
    if not candidates:
        return "'zh-CN'::text"
    return "COALESCE(" + ", ".join(candidates) + ", 'zh-CN')"


def _user_provider_expr(columns):
    candidates = []
    if "provider" in columns:
        candidates.append("NULLIF(u.provider, '')")
    if "preferences" in columns:
        candidates.append("NULLIF(u.preferences->>'provider', '')")
    if not candidates:
        return "'email'::text"
    return "COALESCE(" + ", ".join(candidates) + ", 'email')"


def _user_email_verified_expr(columns):
    if "email_verified" in columns:
        return "COALESCE(u.email_verified, FALSE)"
    if "email_verified_at" in columns:
        return "(u.email_verified_at IS NOT NULL)"
    return "FALSE"


def _build_project_counts_cte(cur):
    if not _table_exists(cur, "projects"):
        return (
            "project_counts AS ("
            "SELECT NULL::varchar AS user_id, 0::int AS project_count, "
            "NULL::text AS industry WHERE FALSE)"
        )
    cols = _table_columns(cur, "projects")
    user_id_expr = "p.user_id::text" if "user_id" in cols else "NULL::text"
    if "industry_id" in cols and _table_exists(cur, "kg_industries"):
        industry_expr = "MIN(COALESCE(ki.name_zh, ki.name_en, p.industry_id::text))"
        join_sql = "LEFT JOIN kg_industries ki ON ki.id::text = p.industry_id::text"
    elif "industry_id" in cols:
        industry_expr = "MIN(p.industry_id::text)"
        join_sql = ""
    else:
        industry_expr = "NULL::text"
        join_sql = ""
    return f"""
        project_counts AS (
            SELECT {user_id_expr} AS user_id,
                   COUNT(*)::int AS project_count,
                   {industry_expr} AS industry
            FROM projects p
            {join_sql}
            GROUP BY {user_id_expr}
        )
    """


def _build_activity_cte(cur):
    if not _table_exists(cur, "user_activity_stats"):
        return (
            "activity_stats AS ("
            "SELECT NULL::varchar AS user_id, NULL::timestamp AS last_login_at, "
            "0::int AS login_count_30d, 0::int AS query_count_30d, "
            "NULL::timestamp AS last_active_at WHERE FALSE)"
        )
    return """
        activity_stats AS (
            SELECT user_id::text AS user_id,
                   last_login_at,
                   COALESCE(login_count_30d, 0)::int AS login_count_30d,
                   COALESCE(query_count_30d, 0)::int AS query_count_30d,
                   last_active_at
            FROM user_activity_stats
        )
    """


def _users_base_sql(cur):
    user_cols = _table_columns(cur, "users")
    name_expr = _user_name_expr(user_cols)
    company_expr = _user_company_expr(user_cols)
    locale_expr = _user_locale_expr(user_cols)
    provider_expr = _user_provider_expr(user_cols)
    verified_expr = _user_email_verified_expr(user_cols)
    last_login_expr = (
        "COALESCE(u.last_login_at, ast.last_login_at)"
        if "last_login_at" in user_cols
        else "ast.last_login_at"
    )
    deleted_expr = (
        "u.deletion_requested_at"
        if "deletion_requested_at" in user_cols
        else "NULL::timestamp"
    )
    updated_expr = "u.updated_at" if "updated_at" in user_cols else "NULL::timestamp"
    project_cte = _build_project_counts_cte(cur)
    activity_cte = _build_activity_cte(cur)

    return f"""
        WITH
        {project_cte},
        {activity_cte},
        user_base AS (
            SELECT
                u.id::text AS id,
                u.email,
                {name_expr} AS name,
                {company_expr} AS company,
                {locale_expr} AS locale,
                {provider_expr} AS provider,
                {verified_expr} AS email_verified,
                u.created_at,
                {updated_expr} AS updated_at,
                {deleted_expr} AS deletion_requested_at,
                {last_login_expr} AS last_login_at,
                COALESCE(pc.project_count, 0)::int AS project_count,
                pc.industry,
                COALESCE(ast.login_count_30d, 0)::int AS login_count_30d,
                COALESCE(ast.query_count_30d, 0)::int AS query_count_30d,
                ast.last_active_at,
                latest_mod.action AS latest_moderation_action,
                latest_mod.reason AS latest_moderation_reason,
                latest_mod.expires_at AS latest_moderation_expires_at,
                latest_mod.created_at AS latest_moderation_at
            FROM users u
            LEFT JOIN project_counts pc ON pc.user_id = u.id::text
            LEFT JOIN activity_stats ast ON ast.user_id = u.id::text
            LEFT JOIN LATERAL (
                SELECT action, reason, expires_at, created_at
                FROM user_moderation_actions uma
                WHERE uma.user_id = u.id::text
                  AND uma.action IN ('freeze', 'unfreeze')
                ORDER BY uma.created_at DESC
                LIMIT 1
            ) latest_mod ON TRUE
        ),
        users_enriched AS (
            SELECT *,
                CASE
                    WHEN deletion_requested_at IS NOT NULL THEN 'deleted'
                    WHEN latest_moderation_action = 'freeze'
                         AND (latest_moderation_expires_at IS NULL
                              OR latest_moderation_expires_at > NOW()) THEN 'frozen'
                    ELSE 'active'
                END AS status,
                CASE
                    WHEN last_login_at IS NULL THEN 'dormant'
                    WHEN last_login_at >= NOW() - INTERVAL '7 days' THEN 'hot'
                    WHEN last_login_at >= NOW() - INTERVAL '30 days' THEN 'warm'
                    WHEN last_login_at >= NOW() - INTERVAL '90 days' THEN 'cold'
                    ELSE 'dormant'
                END AS activity_level
            FROM user_base
        )
    """


def _normalize_user_row(row):
    email = row.get("email") or ""
    name = row.get("name") or (email.split("@", 1)[0] if email else row.get("id"))
    initials = "".join(part[:1] for part in str(name).replace(".", " ").split()[:2]).upper()
    if not initials:
        initials = (email[:2] or "U").upper()
    return {
        "id": row.get("id"),
        "email": email,
        "name": name,
        "company": row.get("company"),
        "initials": initials[:2],
        "status": row.get("status") or "active",
        "industry": row.get("industry"),
        "project_count": row.get("project_count") or 0,
        "projects": row.get("project_count") or 0,
        "last_login_at": _isoformat(row.get("last_login_at")),
        "last_active_at": _isoformat(row.get("last_active_at")),
        "created_at": _isoformat(row.get("created_at")),
        "updated_at": _isoformat(row.get("updated_at")),
        "deletion_requested_at": _isoformat(row.get("deletion_requested_at")),
        "activity_level": row.get("activity_level") or "dormant",
        "login_count_30d": row.get("login_count_30d") or 0,
        "query_count_30d": row.get("query_count_30d") or 0,
        "provider": row.get("provider") or "email",
        "locale": row.get("locale") or "zh-CN",
        "email_verified": bool(row.get("email_verified")),
        "moderation": {
            "is_frozen": row.get("status") == "frozen",
            "latest_action": row.get("latest_moderation_action"),
            "reason": row.get("latest_moderation_reason"),
            "expires_at": _isoformat(row.get("latest_moderation_expires_at")),
            "created_at": _isoformat(row.get("latest_moderation_at")),
        },
    }


def _fetch_user_rows(cur, *, user_id=None, limit=20, offset=0, include_count=True):
    if not _table_exists(cur, "users"):
        return [], 0, ["users table is not present"]

    base_sql = _users_base_sql(cur)
    where = []
    params = []
    q = (request.args.get("q") or request.args.get("search") or "").strip()
    email = (request.args.get("email") or "").strip()
    name = (request.args.get("name") or "").strip()
    company = (request.args.get("company") or "").strip()
    status_filter = (request.args.get("status") or "").strip()
    activity = (request.args.get("activity") or "").strip()
    industry = (request.args.get("industry") or "").strip()
    created_from = (
        request.args.get("created_from")
        or request.args.get("created_at_from")
        or request.args.get("date_from")
    )
    created_to = (
        request.args.get("created_to")
        or request.args.get("created_at_to")
        or request.args.get("date_to")
    )

    if user_id:
        where.append("id = %s")
        params.append(str(user_id))
    if q:
        where.append("(email ILIKE %s OR COALESCE(name, '') ILIKE %s OR COALESCE(company, '') ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if email:
        where.append("email ILIKE %s")
        params.append(f"%{email}%")
    if name:
        where.append("COALESCE(name, '') ILIKE %s")
        params.append(f"%{name}%")
    if company:
        where.append("COALESCE(company, '') ILIKE %s")
        params.append(f"%{company}%")
    if status_filter:
        where.append("status = %s")
        params.append(status_filter)
    if activity:
        where.append("activity_level = %s")
        params.append(activity)
    if industry:
        where.append("COALESCE(industry, '') ILIKE %s")
        params.append(f"%{industry}%")
    if created_from:
        where.append("created_at >= %s")
        params.append(created_from)
    if created_to:
        where.append("created_at < (%s::date + INTERVAL '1 day')")
        params.append(created_to)

    where_clause = "WHERE " + " AND ".join(where) if where else ""
    sort_param = (request.args.get("sort") or "created_at_desc").strip()
    direction = (request.args.get("order") or request.args.get("direction") or "").lower()
    if sort_param.endswith("_asc"):
        sort_key = sort_param[:-4]
        direction = "asc"
    elif sort_param.endswith("_desc"):
        sort_key = sort_param[:-5]
        direction = "desc"
    else:
        sort_key = sort_param
    sort_map = {
        "created_at": "created_at",
        "last_login_at": "last_login_at",
        "project_count": "project_count",
    }
    sort_sql = sort_map.get(sort_key, "created_at")
    direction_sql = "ASC" if direction == "asc" else "DESC"
    order_sql = f"{sort_sql} {direction_sql} NULLS LAST, created_at DESC, id ASC"

    if include_count:
        cur.execute(
            f"{base_sql} SELECT COUNT(*) AS cnt FROM users_enriched {where_clause}",
            params,
        )
        total = cur.fetchone()["cnt"]
    else:
        total = None

    cur.execute(
        f"""
        {base_sql}
        SELECT *
        FROM users_enriched
        {where_clause}
        ORDER BY {order_sql}
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )
    return [_normalize_user_row(dict(row)) for row in cur.fetchall()], total, []


def _fetch_user_projects(cur, user_id):
    if not _table_exists(cur, "projects"):
        return [], ["projects table is not present; returning an empty read-only list"]

    cols = _table_columns(cur, "projects")
    select_parts = ["p.id::text AS id"]
    for col in ("name", "status", "description"):
        select_parts.append(f"p.{col} AS {col}" if col in cols else f"NULL::text AS {col}")
    select_parts.append(
        "p.industry_id::text AS industry_id" if "industry_id" in cols else "NULL::text AS industry_id"
    )
    select_parts.append(
        "p.primary_brand_id::text AS primary_brand_id"
        if "primary_brand_id" in cols
        else "NULL::text AS primary_brand_id"
    )
    select_parts.append(
        "p.competitor_brand_ids::text AS competitor_brand_ids"
        if "competitor_brand_ids" in cols
        else "NULL::text AS competitor_brand_ids"
    )
    select_parts.append(
        "p.preferences::text AS preferences" if "preferences" in cols else "NULL::text AS preferences"
    )
    select_parts.append(
        "p.created_at AS created_at" if "created_at" in cols else "NULL::timestamp AS created_at"
    )
    select_parts.append(
        "p.updated_at AS updated_at" if "updated_at" in cols else "NULL::timestamp AS updated_at"
    )
    joins = []
    if "primary_brand_id" in cols and _table_exists(cur, "brands"):
        select_parts.append("b.name AS primary_brand_name")
        joins.append("LEFT JOIN brands b ON b.id::text = p.primary_brand_id::text")
    else:
        select_parts.append("NULL::text AS primary_brand_name")

    where_user = "p.user_id::text = %s" if "user_id" in cols else "FALSE"
    cur.execute(
        f"""
        SELECT {", ".join(select_parts)}
        FROM projects p
        {" ".join(joins)}
        WHERE {where_user}
        ORDER BY p.created_at DESC NULLS LAST, p.id
        LIMIT 100
        """,
        (str(user_id),),
    )
    projects = []
    for row in cur.fetchall():
        item = dict(row)
        item["created_at"] = _isoformat(item.get("created_at"))
        item["updated_at"] = _isoformat(item.get("updated_at"))
        projects.append(item)
    return projects, []


def _fetch_user_actions(cur, user_id=None, limit=50, offset=0):
    conditions = ["target_type = 'user'"]
    params = []
    if user_id:
        conditions.append("target_id = %s")
        params.append(str(user_id))
    where_clause = " AND ".join(conditions)
    cur.execute(
        f"""
        SELECT al.id, al.operator_id, au.email AS operator_email, au.role AS operator_role,
               al.action, al.target_type, al.target_id, al.diff_json,
               al.reason, al.ip, al.ua, al.created_at
        FROM admin_audit_log al
        LEFT JOIN admin_users au ON au.id = al.operator_id
        WHERE {where_clause}
        ORDER BY al.created_at DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["created_at"] = _isoformat(item.get("created_at"))
        item["operator"] = item.get("operator_email") or item.get("operator_id") or "system"
        item["source"] = "admin_audit_log"
        rows.append(item)

    cur.execute(f"SELECT COUNT(*) AS cnt FROM admin_audit_log WHERE {where_clause}", params)
    total = cur.fetchone()["cnt"]
    if rows or total:
        return rows, total

    mod_conditions = []
    mod_params = []
    if user_id:
        mod_conditions.append("uma.user_id = %s")
        mod_params.append(str(user_id))
    mod_where = "WHERE " + " AND ".join(mod_conditions) if mod_conditions else ""
    cur.execute(
        f"""
        SELECT uma.id, uma.operator_id, au.email AS operator_email, au.role AS operator_role,
               uma.action, 'user'::text AS target_type, uma.user_id AS target_id,
               NULL::jsonb AS diff_json, uma.reason, NULL::text AS ip,
               NULL::text AS ua, uma.created_at
        FROM user_moderation_actions uma
        LEFT JOIN admin_users au ON au.id = uma.operator_id
        {mod_where}
        ORDER BY uma.created_at DESC
        LIMIT %s OFFSET %s
        """,
        mod_params + [limit, offset],
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["created_at"] = _isoformat(item.get("created_at"))
        item["operator"] = item.get("operator_email") or item.get("operator_id") or "system"
        item["source"] = "user_moderation_actions"
        rows.append(item)
    cur.execute(
        f"SELECT COUNT(*) AS cnt FROM user_moderation_actions uma {mod_where}",
        mod_params,
    )
    return rows, cur.fetchone()["cnt"]


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>GEN Pipeline</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1600px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 20px; }
        h2 { color: #333; margin: 20px 0 10px; font-size: 18px; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .filter-row { display: flex; gap: 15px; flex-wrap: wrap; align-items: flex-end; }
        .form-row { display: flex; gap: 15px; flex-wrap: wrap; align-items: flex-start; }
        .form-group { display: flex; flex-direction: column; gap: 5px; flex: 1; min-width: 200px; }
        .form-group label { font-size: 12px; color: #666; font-weight: 600; }
        .form-group select, .form-group input, .form-group textarea { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-family: inherit; font-size: 14px; }
        .form-group textarea { min-height: 80px; resize: vertical; }
        button { padding: 8px 20px; background: #4f46e5; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; }
        button:hover { background: #4338ca; }
        button.secondary { background: #6b7280; }
        button.secondary:hover { background: #4b5563; }
        button.success { background: #059669; }
        button.success:hover { background: #047857; }
        button.danger { background: #dc2626; }
        button.danger:hover { background: #b91c1c; }
        button.small { padding: 4px 10px; font-size: 12px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
        .stat-card { background: white; padding: 15px 25px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-value { font-size: 28px; font-weight: 700; color: #4f46e5; }
        .stat-value.failed { color: #dc2626; }
        .stat-value.pending { color: #d97706; }
        .stat-value.done { color: #059669; }
        .stat-label { font-size: 12px; color: #666; margin-top: 4px; }
        table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8fafc; font-weight: 600; color: #374151; font-size: 13px; }
        td { font-size: 14px; color: #4b5563; }
        tr:hover { background: #f9fafb; }
        .status-DONE { color: #059669; font-weight: 600; }
        .status-PENDING { color: #d97706; font-weight: 600; }
        .status-FAILED { color: #dc2626; font-weight: 600; }
        .status-RUNNING { color: #2563eb; font-weight: 600; }
        .llm-badge { display: inline-block; padding: 2px 8px; background: #e0e7ff; color: #4f46e5; border-radius: 999px; font-size: 12px; font-weight: 600; }
        .text-preview { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
        .html-link { color: #059669; cursor: pointer; text-decoration: underline; font-size: 12px; }
        .html-link:hover { color: #047857; }
        .html-viewer { background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 4px; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.6; overflow-x: auto; white-space: pre-wrap; word-break: break-all; max-height: 70vh; overflow-y: auto; }
        .html-search { display: flex; gap: 8px; margin-bottom: 10px; }
        .html-search input { flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; }
        .html-search span { font-size: 12px; color: #666; align-self: center; }
        mark { background: #ff0; color: #000; }
        /* Tabs */
        .tab-container { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .tab-header { padding: 0 20px; border-bottom: 2px solid #e5e7eb; }
        .tabs { display: flex; gap: 0; }
        .tab-btn { padding: 12px 24px; background: none; color: #6b7280; border: none; border-bottom: 3px solid transparent; border-radius: 0; cursor: pointer; font-weight: 600; font-size: 15px; margin-bottom: -2px; transition: color 0.15s, border-color 0.15s; }
        .tab-btn:hover { color: #4f46e5; background: none; }
        .tab-btn.active { color: #4f46e5; border-bottom-color: #4f46e5; background: none; }
        .tab-content { padding: 20px; }
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }
        /* Pagination */
        .pagination { display: flex; justify-content: center; gap: 6px; margin-top: 20px; flex-wrap: wrap; }
        .pagination button { background: white; color: #4f46e5; border: 1px solid #ddd; min-width: 36px; padding: 6px 10px; font-size: 13px; }
        .pagination button:hover:not(:disabled) { background: #f0f0ff; }
        .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
        .pagination button.active { background: #4f46e5; color: white; border-color: #4f46e5; }
        /* Modal */
        .modal-backdrop { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 1000; }
        .modal-backdrop.show { display: flex; align-items: center; justify-content: center; }
        .modal { background: white; border-radius: 8px; max-width: 1200px; max-height: 90vh; width: 95%; overflow: hidden; display: flex; flex-direction: column; }
        .modal.large { max-width: 1600px; }
        .modal-header { padding: 15px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .modal-header h3 { margin: 0; }
        .modal-close { background: none; border: none; font-size: 24px; cursor: pointer; color: #666; padding: 0; width: 30px; height: 30px; }
        .modal-body { padding: 20px; overflow-y: auto; flex: 1; }
        .modal-body pre { background: #f5f5f5; padding: 15px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
        .modal-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .modal-meta-item { background: #f8fafc; padding: 10px 15px; border-radius: 4px; }
        .modal-meta-label { font-size: 12px; color: #666; margin-bottom: 4px; }
        .modal-meta-value { font-weight: 600; color: #333; }
        .refresh-btn { margin-left: 10px; }
        .auto-refresh { display: flex; align-items: center; gap: 10px; margin-left: auto; }
        .auto-refresh label { font-size: 14px; color: #666; display: flex; align-items: center; gap: 5px; }
        .alert { padding: 12px 16px; border-radius: 4px; margin-bottom: 15px; }
        .alert.success { background: #dcfce7; color: #166534; }
        .alert.error { background: #fee2e2; color: #991b1b; }
        /* Analyzer styles */
        .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
        .badge-done { background: #d1fae5; color: #059669; }
        .badge-pending { background: #fef3c7; color: #d97706; }
        .badge-failed { background: #fee2e2; color: #dc2626; }
        .badge-running { background: #dbeafe; color: #2563eb; }
        .badge-positive { background: #d1fae5; color: #059669; }
        .badge-negative { background: #fee2e2; color: #dc2626; }
        .badge-neutral { background: #f3f4f6; color: #6b7280; }
        .score-bar { display: inline-block; height: 8px; border-radius: 4px; background: #e5e7eb; width: 80px; vertical-align: middle; }
        .score-fill { height: 100%; border-radius: 4px; }
        .score-high .score-fill { background: #059669; }
        .score-mid .score-fill { background: #d97706; }
        .score-low .score-fill { background: #dc2626; }
        .geo-score { font-size: 18px; font-weight: 700; }
        .geo-score.high { color: #059669; }
        .geo-score.mid { color: #d97706; }
        .geo-score.low { color: #dc2626; }
        .detail-panel { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; padding: 15px; margin: 10px 0; }
        .detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; }
        .detail-section { background: white; padding: 12px; border-radius: 6px; border: 1px solid #e5e7eb; }
        .detail-section h4 { font-size: 13px; color: #6b7280; margin-bottom: 8px; }
        .mention-item { padding: 8px 0; border-bottom: 1px solid #f3f4f6; }
        .mention-item:last-child { border-bottom: none; }
        .driver-tag { display: inline-block; padding: 2px 6px; margin: 2px; border-radius: 4px; font-size: 11px; }
        .driver-pos { background: #d1fae5; color: #059669; }
        .driver-neg { background: #fee2e2; color: #dc2626; }
        .sub-scores { display: flex; gap: 12px; flex-wrap: wrap; }
        .sub-score { text-align: center; }
        .sub-score-value { font-size: 14px; font-weight: 700; }
        .sub-score-label { font-size: 10px; color: #9ca3af; }
        .text-muted { color: #9ca3af; font-size: 12px; }
        .empty-state { text-align: center; padding: 40px; color: #9ca3af; }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
            <h1>GEN Pipeline <small style="font-size:14px;color:#888;font-weight:normal;">query & analysis monitor</small></h1>
            <button class="secondary refresh-btn" onclick="loadStats(); loadQueries();">Refresh</button>
            <button class="secondary refresh-btn" onclick="backfillCitations()">Backfill Citations</button>
            <div class="auto-refresh">
                <label><input type="checkbox" id="auto-refresh" onchange="toggleAutoRefresh()"> Auto-refresh (5s)</label>
            </div>
        </div>

        <div class="stats" id="tracker-stats">
            <div class="stat-card"><div class="stat-value" id="total-queries">-</div><div class="stat-label">Total Queries</div></div>
            <div class="stat-card"><div class="stat-value done" id="done-queries">-</div><div class="stat-label">Done</div></div>
            <div class="stat-card"><div class="stat-value pending" id="pending-queries">-</div><div class="stat-label">Pending</div></div>
            <div class="stat-card"><div class="stat-value" id="running-queries">-</div><div class="stat-label">Running</div></div>
            <div class="stat-card"><div class="stat-value failed" id="failed-queries">-</div><div class="stat-label">Failed</div></div>
        </div>
        <div id="analyzer-stats" class="stats" style="display:none;"></div>

        <!-- Create New Query Section -->
        <div class="card">
            <h2>Create New Query</h2>
            <div id="create-alert"></div>
            <form id="create-form" onsubmit="createQuery(event)">
                <div class="form-row">
                    <div class="form-group">
                        <label>LLM *</label>
                        <select id="new-llm" required>
                            <option value="">Select LLM</option>
                            <option value="chatgpt">ChatGPT</option>
                            <option value="gemini" selected>Gemini</option>
                            <option value="doubao">Doubao</option>
                            <option value="deepseek">DeepSeek</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Brand ID (optional)</label>
                        <input type="number" id="new-brand" placeholder="Brand ID">
                    </div>
                </div>
                <div class="form-row" style="margin-top: 10px;">
                    <div class="form-group" style="flex: 3;">
                        <label>Query Text *</label>
                        <textarea id="new-query" placeholder="Enter your query here..." required></textarea>
                    </div>
                </div>
                <div style="margin-top: 15px; display: flex; gap: 10px;">
                    <button type="submit" class="success">Create &amp; Queue Query</button>
                    <button type="button" class="secondary" onclick="fillExample()">Fill Example</button>
                </div>
            </form>
        </div>

        <!-- Filters -->
        <div class="card">
            <h2>Filters</h2>
            <div class="filter-row">
                <div class="form-group">
                    <label>LLM</label>
                    <select id="filter-llm">
                        <option value="">All</option>
                        <option value="chatgpt">ChatGPT</option>
                        <option value="gemini">Gemini</option>
                        <option value="doubao">Doubao</option>
                        <option value="deepseek">DeepSeek</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Status</label>
                    <select id="filter-status">
                        <option value="">All</option>
                        <option value="DONE">Done</option>
                        <option value="PENDING">Pending</option>
                        <option value="RUNNING">Running</option>
                        <option value="FAILED">Failed</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Query ID</label>
                    <input type="number" id="filter-id" placeholder="Query ID">
                </div>
                <div class="form-group">
                    <label>Brand ID</label>
                    <input type="number" id="filter-brand" placeholder="Brand ID">
                </div>
                <div class="form-group">
                    <label>Limit</label>
                    <select id="filter-limit">
                        <option value="20">20</option>
                        <option value="50" selected>50</option>
                        <option value="100">100</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Sort by</label>
                    <select id="filter-sort">
                        <option value="id_desc">ID (newest first)</option>
                        <option value="id_asc">ID (oldest first)</option>
                        <option value="status">Status</option>
                    </select>
                </div>
                <button onclick="currentPage=1; loadQueries();">Search</button>
            </div>
        </div>

        <!-- Tabs: Queries / Debug HTML Files -->
        <div class="tab-container">
            <div class="tab-header">
                <div class="tabs">
                    <button class="tab-btn active" id="tab-queries-btn" onclick="switchTab('queries')">Queries</button>
                    <button class="tab-btn" id="tab-accounts-btn" onclick="switchTab('accounts')">Accounts</button>
                    <button class="tab-btn" id="tab-segments-btn" onclick="switchTab('segments')">Segments</button>
                    <button class="tab-btn" id="tab-profiles-btn" onclick="switchTab('profiles')">Profiles</button>
                    <button class="tab-btn" id="tab-html-btn" onclick="switchTab('html')">Debug HTML</button>
                    <span style="border-left:2px solid #ddd; margin:0 8px; height:24px;"></span>
                    <button class="tab-btn" id="tab-analyzer-btn" onclick="switchTab('analyzer')" style="color:#7c3aed;">Analyzer</button>
                    <button class="tab-btn" id="tab-daily-btn" onclick="switchTab('daily')" style="color:#7c3aed;">Daily GEO</button>
                    <button class="tab-btn" id="tab-trigger-btn" onclick="switchTab('trigger')" style="color:#7c3aed;">Trigger</button>
                </div>
            </div>
            <div class="tab-content">
                <!-- Queries Tab -->
                <div class="tab-panel active" id="tab-queries">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>LLM</th>
                                <th>Status</th>
                                <th>Profile</th>
                                <th>Account</th>
                                <th>Retry</th>
                                <th>Query</th>
                                <th>Citations</th>
                                <th>Brand</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="results-body">
                        </tbody>
                    </table>
                    <div class="pagination" id="pagination"></div>
                </div>

                <!-- Accounts Tab -->
                <div class="tab-panel" id="tab-accounts">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
                        <h3 style="margin:0; font-size:16px; color:#333;">LLM Accounts</h3>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <button class="secondary small" onclick="loadAccounts();">Refresh</button>
                            <button class="success small" onclick="showCookieUpload();">Upload Cookies</button>
                            <button class="small" style="background:#7c3aed;color:#fff;border:none;" onclick="showSmsRegister();">SMS Register</button>
                        </div>
                    </div>
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Platform</th>
                                <th>Phone</th>
                                <th>Status</th>
                                <th>Daily Used / Limit</th>
                                <th>Fails</th>
                                <th>Cookies</th>
                                <th>Cookie Age</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="accounts-body"></tbody>
                    </table>

                    <!-- Cookie Upload Form (hidden by default) -->
                    <div id="cookie-upload-form" style="display:none; margin-top:20px; padding:20px; background:#f9fafb; border-radius:8px; border:1px solid #e5e7eb;">
                        <h4 style="margin:0 0 12px; font-size:15px;">Upload Cookies</h4>
                        <div class="form-row">
                            <div class="form-group">
                                <label>Platform</label>
                                <select id="cookie-platform">
                                    <option value="doubao">Doubao (豆包)</option>
                                    <option value="chatgpt">ChatGPT</option>
                                    <option value="gemini">Gemini</option>
                                    <option value="doubao">Doubao</option>
                                    <option value="deepseek">DeepSeek</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label>Account Label (optional)</label>
                                <input type="text" id="cookie-label" placeholder="e.g. phone number or email">
                            </div>
                            <div class="form-group">
                                <label>Daily Limit</label>
                                <input type="number" id="cookie-daily-limit" value="20" min="1">
                            </div>
                        </div>
                        <div class="form-group" style="margin-top:12px;">
                            <label>Cookies JSON (paste EditThisCookie export or Playwright format)</label>
                            <textarea id="cookie-json" style="min-height:120px; font-family:monospace; font-size:12px;" placeholder='Paste cookies JSON here...'></textarea>
                        </div>
                        <div class="form-group" style="margin-top:8px;">
                            <label>localStorage JSON <span style="color:#999;">(optional, for DeepSeek etc.)</span></label>
                            <textarea id="local-storage-json" style="min-height:60px; font-family:monospace; font-size:12px;" placeholder='{"userToken": "...", ...}'></textarea>
                            <div style="font-size:11px; color:#888; margin-top:4px;">
                                DeepSeek: F12 Console → JSON.stringify({userToken: localStorage.getItem("userToken")})
                            </div>
                        </div>
                        <div style="margin-top:8px; display:flex; gap:8px; align-items:center;">
                            <label style="cursor:pointer; padding:8px 16px; background:#e5e7eb; border-radius:4px; font-size:13px;">
                                Or upload .json file
                                <input type="file" id="cookie-file" accept=".json" style="display:none;" onchange="loadCookieFile(this)">
                            </label>
                            <div style="flex:1;"></div>
                            <button class="secondary" onclick="hideCookieUpload();">Cancel</button>
                            <button class="success" onclick="submitCookies();">Import</button>
                        </div>
                    </div>

                    <!-- SMS Register Form (hidden by default) -->
                    <div id="sms-register-form" style="display:none; margin-top:20px; padding:20px; background:#f5f3ff; border-radius:8px; border:1px solid #ddd6fe;">
                        <h4 style="margin:0 0 12px; font-size:15px; color:#7c3aed;">SMS Auto Register / Login</h4>
                        <div class="form-row" style="align-items:flex-end;">
                            <div class="form-group">
                                <label>Platform</label>
                                <select id="sms-platform">
                                    <option value="doubao">Doubao</option>
                                    <option value="deepseek">DeepSeek</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <button style="background:#7c3aed;color:#fff;border:none;padding:8px 20px;border-radius:4px;cursor:pointer;font-size:13px;" onclick="triggerSmsRegister();">Register New Account</button>
                            </div>
                            <div class="form-group">
                                <button class="secondary" onclick="hideSmsRegister();">Cancel</button>
                            </div>
                        </div>
                        <div id="sms-task-status" style="margin-top:12px; display:none; padding:12px; background:#fff; border-radius:6px; border:1px solid #e5e7eb; font-size:13px;"></div>
                    </div>
                </div>

                <!-- Segments Tab -->
                <div class="tab-panel" id="tab-segments">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
                        <h3 style="margin:0; font-size:16px; color:#333;">Segment Definitions</h3>
                        <button class="secondary small" onclick="loadSegments();">Refresh</button>
                    </div>
                    <div id="segments-body">
                        <div style="color:#999; font-size:13px;">Loading...</div>
                    </div>
                </div>

                <!-- Profiles Tab -->
                <div class="tab-panel" id="tab-profiles">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
                        <h3 style="margin:0; font-size:16px; color:#333;">User Profiles</h3>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <button class="secondary small" onclick="loadProfiles();">Refresh</button>
                            <button class="success small" onclick="showProfileForm();">+ New Profile</button>
                        </div>
                    </div>

                    <!-- Profile Create/Edit Form (hidden by default) -->
                    <div id="profile-form-container" style="display:none; margin-bottom:20px; padding:20px; background:#f9fafb; border-radius:8px; border:1px solid #e5e7eb;">
                        <h4 style="margin:0 0 12px; font-size:15px;" id="profile-form-title">Create New Profile</h4>
                        <div id="profile-alert"></div>
                        <form id="profile-form" onsubmit="submitProfile(event)">
                            <input type="hidden" id="profile-edit-id">
                            <div class="form-row">
                                <div class="form-group">
                                    <label>Name *</label>
                                    <input type="text" id="profile-name" placeholder="e.g. 张明" required>
                                </div>
                                <div class="form-group">
                                    <label>Age Range</label>
                                    <input type="text" id="profile-age-range" placeholder="e.g. 25-34">
                                </div>
                                <div class="form-group">
                                    <label>Location</label>
                                    <input type="text" id="profile-location" placeholder="e.g. Shanghai">
                                </div>
                                <div class="form-group">
                                    <label>Country Code</label>
                                    <input type="text" id="profile-country" placeholder="e.g. CN" maxlength="8">
                                </div>
                            </div>
                            <div class="form-row" style="margin-top:10px;">
                                <div class="form-group">
                                    <label>Profession</label>
                                    <input type="text" id="profile-profession" placeholder="e.g. Software Engineer">
                                </div>
                                <div class="form-group">
                                    <label>Language</label>
                                    <select id="profile-language">
                                        <option value="zh">Chinese (zh)</option>
                                        <option value="en">English (en)</option>
                                        <option value="zh_en">Bilingual (zh_en)</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label>Device Type</label>
                                    <select id="profile-device">
                                        <option value="desktop">Desktop</option>
                                        <option value="mobile">Mobile</option>
                                    </select>
                                </div>
                            </div>
                            <div class="form-row" style="margin-top:10px;">
                                <div class="form-group">
                                    <label>Tone</label>
                                    <select id="profile-tone">
                                        <option value="casual">Casual</option>
                                        <option value="semi_formal">Semi-formal</option>
                                        <option value="formal">Formal</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label>Verbosity</label>
                                    <select id="profile-verbosity">
                                        <option value="short">Short</option>
                                        <option value="medium">Medium</option>
                                        <option value="long">Long</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label>Search Style</label>
                                    <select id="profile-search-style">
                                        <option value="solution_oriented">Solution Oriented</option>
                                        <option value="comparison">Comparison</option>
                                        <option value="exploratory">Exploratory</option>
                                    </select>
                                </div>
                            </div>
                            <div style="margin-top:15px; display:flex; gap:10px;">
                                <button type="submit" class="success">Save Profile</button>
                                <button type="button" class="secondary" onclick="hideProfileForm();">Cancel</button>
                            </div>
                        </form>
                    </div>

                    <!-- Profile Filters -->
                    <div style="display:flex; gap:10px; margin-bottom:12px; flex-wrap:wrap; align-items:flex-end;">
                        <div class="form-group" style="min-width:150px; flex:0;">
                            <label>Segment</label>
                            <select id="profile-filter-segment" onchange="filterProfiles()">
                                <option value="">All Segments</option>
                            </select>
                        </div>
                        <div class="form-group" style="min-width:120px; flex:0;">
                            <label>Language</label>
                            <select id="profile-filter-lang" onchange="filterProfiles()">
                                <option value="">All</option>
                                <option value="zh">zh</option>
                                <option value="en">en</option>
                            </select>
                        </div>
                        <div class="form-group" style="min-width:120px; flex:0;">
                            <label>Device</label>
                            <select id="profile-filter-device" onchange="filterProfiles()">
                                <option value="">All</option>
                                <option value="desktop">Desktop</option>
                                <option value="mobile">Mobile</option>
                            </select>
                        </div>
                        <span id="profile-count-label" style="font-size:12px; color:#888; padding-bottom:8px;"></span>
                    </div>

                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Segment</th>
                                <th>Age Range</th>
                                <th>Location</th>
                                <th>Country</th>
                                <th>Profession</th>
                                <th>Language</th>
                                <th>Device</th>
                                <th>Tone / Verbosity / Style</th>
                                <th>Queries</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="profiles-body">
                        </tbody>
                    </table>
                    <div class="pagination" id="profiles-pagination"></div>
                </div>

                <!-- Debug HTML Files Tab -->
                <div class="tab-panel" id="tab-html">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; flex-wrap:wrap; gap:10px;">
                        <span style="color:#666;font-size:14px;">Debug artifacts (HTML / Screenshots / JSON snapshots) from /data/screenshots, newest first</span>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <label style="font-size:13px;color:#666;">Filter:</label>
                            <select id="html-filter-type" onchange="htmlFilesCurrentPage=1; loadHtmlFiles();" style="padding:4px 8px;font-size:13px;">
                                <option value="all">All</option>
                                <option value="html">HTML</option>
                                <option value="image">Images</option>
                                <option value="json">JSON</option>
                            </select>
                            <label style="font-size:13px;color:#666;">Per page:</label>
                            <select id="html-per-page" onchange="htmlFilesCurrentPage=1; loadHtmlFiles();" style="padding:4px 8px;font-size:13px;">
                                <option value="10">10</option>
                                <option value="20" selected>20</option>
                                <option value="50">50</option>
                                <option value="100">100</option>
                            </select>
                            <button class="secondary small" onclick="loadHtmlFiles();">Refresh</button>
                        </div>
                    </div>
                    <div id="html-files-body">
                        <div style="color:#999; font-size:13px;">Loading...</div>
                    </div>
                    <div class="pagination" id="html-files-pagination" style="margin-top:16px;"></div>
                </div>

                <!-- Analyzer Responses Tab -->
                <div class="tab-panel" id="tab-analyzer">
                    <div class="card">
                        <div class="filter-row" style="margin-bottom:15px;">
                            <div class="form-group">
                                <label>Status</label>
                                <select id="f-status"><option value="">All</option><option value="done">Done</option><option value="pending">Pending</option><option value="running">Running</option><option value="failed">Failed</option></select>
                            </div>
                            <div class="form-group">
                                <label>Brand</label>
                                <select id="f-brand"><option value="">All</option></select>
                            </div>
                            <div class="form-group">
                                <label>LLM</label>
                                <select id="f-llm"><option value="">All</option></select>
                            </div>
                            <div class="form-group">
                                <label>From</label>
                                <input type="date" id="f-date-from">
                            </div>
                            <div class="form-group">
                                <label>To</label>
                                <input type="date" id="f-date-to">
                            </div>
                            <button onclick="loadAnalyzerResponses()">Filter</button>
                        </div>
                        <div id="responses-table"></div>
                        <div style="margin-top:10px;display:flex;gap:10px;">
                            <button class="small" onclick="loadAnalyzerResponses(analyzerCurrentPage-1)">&#8592; Prev</button>
                            <span id="page-info" class="text-muted" style="line-height:28px;"></span>
                            <button class="small" onclick="loadAnalyzerResponses(analyzerCurrentPage+1)">Next &#8594;</button>
                        </div>
                    </div>
                </div>

                <!-- Daily GEO Tab -->
                <div class="tab-panel" id="tab-daily">
                    <div class="card">
                        <div class="filter-row" style="margin-bottom:15px;">
                            <div class="form-group">
                                <label>Brand</label>
                                <select id="d-brand"><option value="">All</option></select>
                            </div>
                            <div class="form-group">
                                <label>LLM</label>
                                <select id="d-llm"><option value="">All</option></select>
                            </div>
                            <div class="form-group">
                                <label>Days</label>
                                <select id="d-days"><option value="7">7</option><option value="14">14</option><option value="30" selected>30</option></select>
                            </div>
                            <button onclick="loadDaily()">Filter</button>
                        </div>
                        <div id="daily-table"></div>
                    </div>
                </div>

                <!-- Trigger Analysis Tab -->
                <div class="tab-panel" id="tab-trigger">
                    <div class="card">
                        <h2>Trigger Analysis</h2>
                        <p class="text-muted" style="margin-bottom:15px;">Run the analysis pipeline on pending responses for a given date.</p>
                        <div class="filter-row">
                            <div class="form-group">
                                <label>Date</label>
                                <input type="date" id="t-date">
                            </div>
                            <div class="form-group">
                                <label>Brand (optional)</label>
                                <select id="t-brand"><option value="">All Brands</option></select>
                            </div>
                            <div class="form-group">
                                <label>Action</label>
                                <div style="display:flex;gap:8px;">
                                    <button class="success" onclick="triggerAnalysis('analyze')">Run Analysis</button>
                                    <button onclick="triggerAnalysis('aggregate')">Aggregate Only</button>
                                    <button class="danger" onclick="triggerAnalysis('reanalyze')">Re-analyze</button>
                                </div>
                            </div>
                        </div>
                        <div id="trigger-result" style="margin-top:15px;"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Query Detail Modal -->
    <div class="modal-backdrop" id="modal-backdrop" onclick="if(event.target === this) closeModal()">
        <div class="modal" id="modal">
            <div class="modal-header">
                <h3 id="modal-title">Response Details</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modal-body"></div>
        </div>
    </div>

    <!-- HTML Source Modal -->
    <div class="modal-backdrop" id="html-modal" onclick="if(event.target === this) closeHtmlModal()">
        <div class="modal large" style="max-width:1400px;">
            <div class="modal-header">
                <h3 id="html-modal-title">HTML Source</h3>
                <button class="modal-close" onclick="closeHtmlModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="html-search">
                    <input type="text" id="html-search-input" placeholder="Search in HTML..." oninput="searchHtml(this.value)">
                    <span id="html-search-count"></span>
                    <button class="secondary small" onclick="searchHtml(document.getElementById('html-search-input').value)">Find</button>
                    <button class="secondary small" onclick="document.getElementById('html-search-input').value=''; searchHtml('')">Clear</button>
                </div>
                <div class="html-viewer" id="html-viewer-content"></div>
            </div>
        </div>
    </div>

    <!-- Image Viewer Modal -->
    <div class="modal-backdrop" id="image-modal" onclick="if(event.target === this) closeImageModal()">
        <div class="modal large" style="max-width:1400px;">
            <div class="modal-header">
                <h3 id="image-modal-title">Screenshot</h3>
                <button class="modal-close" onclick="closeImageModal()">&times;</button>
            </div>
            <div class="modal-body" style="text-align:center; background:#1e293b;">
                <img id="image-viewer-content" style="max-width:100%; max-height:80vh; cursor:zoom-in;" onclick="this.style.maxWidth = this.style.maxWidth === 'none' ? '100%' : 'none'; this.style.cursor = this.style.maxWidth === 'none' ? 'zoom-out' : 'zoom-in';">
            </div>
        </div>
    </div>

    <script>
        let currentPage = 1;
        let totalCount = 0;
        let currentData = [];
        let autoRefreshInterval = null;
        let rawHtmlContent = '';

        // ---- Tab switcher ----
        function switchTab(tab) {
            ['queries', 'accounts', 'segments', 'profiles', 'html', 'analyzer', 'daily', 'trigger'].forEach(t => {
                document.getElementById('tab-' + t).classList.toggle('active', tab === t);
                document.getElementById('tab-' + t + '-btn').classList.toggle('active', tab === t);
            });
            // Tracker tabs
            if (tab === 'html') loadHtmlFiles();
            if (tab === 'accounts') loadAccounts();
            if (tab === 'segments') loadSegments();
            if (tab === 'profiles') loadProfiles();
            // Analyzer tabs
            const isAnalyzer = ['analyzer', 'daily', 'trigger'].includes(tab);
            document.getElementById('tracker-stats').style.display = isAnalyzer ? 'none' : 'flex';
            document.getElementById('analyzer-stats').style.display = isAnalyzer ? 'flex' : 'none';
            if (tab === 'analyzer') { loadAnalyzerStats(); loadAnalyzerResponses(0); }
            if (tab === 'daily') { loadAnalyzerStats(); loadDaily(); }
            if (tab === 'trigger') loadAnalyzerStats();
        }

        // ---- Stats ----
        async function loadStats() {
            const res = await fetch('./api/stats');
            const data = await res.json();
            document.getElementById('total-queries').textContent = data.total;
            document.getElementById('done-queries').textContent = data.done;
            document.getElementById('pending-queries').textContent = data.pending;
            document.getElementById('running-queries').textContent = data.running;
            document.getElementById('failed-queries').textContent = data.failed;
        }

        // ---- Queries ----
        async function loadQueries() {
            const llm = document.getElementById('filter-llm').value;
            const status = document.getElementById('filter-status').value;
            const brand = document.getElementById('filter-brand').value;
            const queryId = document.getElementById('filter-id').value;
            const limit = parseInt(document.getElementById('filter-limit').value);
            const sort = document.getElementById('filter-sort').value;

            const params = new URLSearchParams();
            if (llm) params.append('llm', llm);
            if (status) params.append('status', status);
            if (brand) params.append('brand_id', brand);
            if (queryId) params.append('id', queryId);
            params.append('limit', limit);
            params.append('offset', (currentPage - 1) * limit);
            params.append('sort', sort);
            params.append('count', '1');

            const res = await fetch('./api/queries?' + params.toString());
            const json = await res.json();
            if (json && json.rows !== undefined) {
                currentData = json.rows;
                totalCount = json.total;
            } else {
                currentData = json;
                totalCount = json.length;
            }
            renderTable(currentData);
            renderPagination(limit);
        }

        function renderTable(data) {
            const tbody = document.getElementById('results-body');
            tbody.innerHTML = data.map(q => {
                const statusUp = (q.status || '').toUpperCase();
                const profileInfo = q.profile_name
                    ? `<span title="ID:${q.profile_id} ${q.profile_location || ''}">${q.profile_name}${q.profile_country ? ' (' + q.profile_country + ')' : ''}</span>`
                    : '<span style="color:#999;">-</span>';
                const accountInfo = q.account_id
                    ? `<span title="Account #${q.account_id}">${q.account_label || '#' + q.account_id}</span>`
                    : '<span style="color:#999;">-</span>';
                return `
                <tr>
                    <td>${q.id}</td>
                    <td><span class="llm-badge">${q.target_llm}</span></td>
                    <td><span class="status-${statusUp}">${statusUp}</span></td>
                    <td style="font-size:12px;">${profileInfo}</td>
                    <td style="font-size:12px;">${accountInfo}</td>
                    <td>${q.retry_count || 0}</td>
                    <td class="text-preview" title="${escapeHtml(q.query_text)}" onclick="showResponse(${q.id})">${escapeHtml(q.query_text || '')}</td>
                    <td>${q.citations && q.citations.length ? q.citations.length : '-'}</td>
                    <td>${q.brand_id || '-'}</td>
                    <td>${q.created_at ? new Date(q.created_at).toLocaleString() : '-'}</td>
                    <td>
                        <button class="secondary small" onclick="showResponse(${q.id})">View</button>
                        ${statusUp === 'FAILED' || statusUp === 'PENDING' ?
                            `<button class="success small" onclick="retryQuery(${q.id})">Retry</button>` : ''}
                        ${statusUp === 'DONE' ?
                            `<button class="danger small" onclick="markFailed(${q.id})">Mark Failed</button>` : ''}
                    </td>
                </tr>`;
            }).join('');
        }

        function renderPagination(limit) {
            const pag = document.getElementById('pagination');
            if (!totalCount || totalCount <= limit) {
                pag.innerHTML = '';
                return;
            }
            const totalPages = Math.ceil(totalCount / limit);
            const page = currentPage;

            let startPage = Math.max(1, page - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            if (endPage - startPage < 4) {
                startPage = Math.max(1, endPage - 4);
            }

            let html = '';
            html += `<button ${page === 1 ? 'disabled' : ''} onclick="goToPage(${page - 1})">&laquo; Prev</button>`;
            for (let p = startPage; p <= endPage; p++) {
                html += `<button class="${p === page ? 'active' : ''}" onclick="goToPage(${p})">${p}</button>`;
            }
            html += `<button ${page === totalPages ? 'disabled' : ''} onclick="goToPage(${page + 1})">Next &raquo;</button>`;
            pag.innerHTML = html;
        }

        function goToPage(page) {
            currentPage = page;
            loadQueries();
        }

        async function showResponse(id) {
            const q = currentData.find(x => x.id === id);
            if (!q) return;

            const statusUp = (q.status || '').toUpperCase();
            document.getElementById('modal-title').textContent = `Query #${q.id} - ${q.target_llm}`;
            const statusClass = `status-${statusUp}`;
            document.getElementById('modal-body').innerHTML = `
                <div class="modal-meta">
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Status</div>
                        <div class="modal-meta-value ${statusClass}">${statusUp}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">LLM</div>
                        <div class="modal-meta-value">${q.target_llm}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Retry Count</div>
                        <div class="modal-meta-value">${q.retry_count || 0}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Brand ID</div>
                        <div class="modal-meta-value">${q.brand_id || '-'}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Profile</div>
                        <div class="modal-meta-value">${q.profile_name ? q.profile_name + (q.profile_country ? ' (' + q.profile_country + ')' : '') : '-'}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Account</div>
                        <div class="modal-meta-value">${q.account_id ? (q.account_label || '#' + q.account_id) : '-'}</div>
                    </div>
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Created</div>
                        <div class="modal-meta-value">${q.created_at ? new Date(q.created_at).toLocaleString() : '-'}</div>
                    </div>
                    ${q.executed_at ? `
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">Executed</div>
                        <div class="modal-meta-value">${new Date(q.executed_at).toLocaleString()}</div>
                    </div>
                    ` : ''}
                    ${q.llm_version ? `
                    <div class="modal-meta-item">
                        <div class="modal-meta-label">LLM Version</div>
                        <div class="modal-meta-value">${q.llm_version}</div>
                    </div>
                    ` : ''}
                </div>
                <div class="modal-meta-item" style="margin-bottom:15px;">
                    <div class="modal-meta-label">Query</div>
                    <div class="modal-meta-value" style="font-weight: normal;"><pre>${escapeHtml(q.query_text || '')}</pre></div>
                </div>
                <div style="margin-top: 20px;">
                    <div class="modal-meta-label" style="margin-bottom: 8px;">Response</div>
                    <pre>${escapeHtml(q.response || '(no response)')}</pre>
                </div>
                ${q.citations && q.citations.length ? `
                <div style="margin-top: 20px;">
                    <div class="modal-meta-label" style="margin-bottom: 8px;">Citations (${q.citations.length})</div>
                    <div style="background:#1e1e2e;border:1px solid #333;border-radius:6px;padding:10px;">
                        ${q.citations.map((c, i) => `
                            <div style="margin-bottom:6px;font-size:13px;">
                                <span style="color:#888;">[${c.index || i+1}]</span>
                                <a href="${escapeHtml(c.url)}" target="_blank" rel="noopener" style="color:#58a6ff;text-decoration:none;">${escapeHtml(c.title || c.url)}</a>
                            </div>
                        `).join('')}
                    </div>
                </div>
                ` : ''}
                ${statusUp === 'FAILED' || statusUp === 'PENDING' ? `
                <div style="margin-top: 20px;">
                    <button class="success" onclick="retryQuery(${q.id}); closeModal();">Retry This Query</button>
                </div>
                ` : ''}
                ${statusUp === 'DONE' ? `
                <div style="margin-top: 20px;">
                    <button class="danger" onclick="markFailed(${q.id}); closeModal();">Mark as Failed</button>
                </div>
                ` : ''}
                <div style="margin-top: 20px;">
                    <div class="modal-meta-label" style="margin-bottom: 8px;">Debug HTML Files</div>
                    <div id="modal-html-files">Loading...</div>
                </div>
            `;
            document.getElementById('modal-backdrop').classList.add('show');

            // Load HTML files for this query
            fetch('./api/html_files?query_id=' + q.id).then(r => r.json()).then(files => {
                const el = document.getElementById('modal-html-files');
                if (!el) return;
                if (!files || !files.length) {
                    el.innerHTML = '<span style="color:#999;font-size:12px;">No HTML files found for this query</span>';
                    return;
                }
                el.innerHTML = files.map(f =>
                    '<div style="margin-bottom:4px;">' +
                    "<span class='html-link' onclick='showHtmlSource(" + JSON.stringify(f.path) + ", " + JSON.stringify(f.name) + ")'>" + escapeHtml(f.name) + '</span>' +
                    ' <span style="color:#999;font-size:11px;">(' + (f.size / 1024).toFixed(1) + ' KB)</span>' +
                    '</div>'
                ).join('');
            }).catch(() => {
                const el = document.getElementById('modal-html-files');
                if (el) el.innerHTML = '<span style="color:#999;font-size:12px;">Failed to load HTML files</span>';
            });
        }

        function closeModal() {
            document.getElementById('modal-backdrop').classList.remove('show');
        }

        function toggleAutoRefresh() {
            const checkbox = document.getElementById('auto-refresh');
            if (checkbox.checked) {
                autoRefreshInterval = setInterval(() => {
                    loadStats();
                    loadQueries();
                }, 5000);
            } else {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function fillExample() {
            document.getElementById('new-llm').value = 'gemini';
            document.getElementById('new-query').value = 'Hello, please introduce yourself in one sentence.';
        }

        async function createQuery(event) {
            event.preventDefault();
            const alertDiv = document.getElementById('create-alert');
            alertDiv.innerHTML = '';

            const llm = document.getElementById('new-llm').value;
            const queryText = document.getElementById('new-query').value;
            const brandId = document.getElementById('new-brand').value;

            try {
                const res = await fetch('./api/queries', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        target_llm: llm,
                        query_text: queryText,
                        brand_id: brandId ? parseInt(brandId) : null
                    })
                });
                const data = await res.json();
                if (data.success) {
                    alertDiv.innerHTML = `<div class="alert success">Query #${data.query_id} created successfully! It has been queued for execution.</div>`;
                    document.getElementById('create-form').reset();
                    loadStats();
                    loadQueries();
                } else {
                    alertDiv.innerHTML = `<div class="alert error">Error: ${data.error || 'Unknown error'}</div>`;
                }
            } catch (e) {
                alertDiv.innerHTML = `<div class="alert error">Error: ${e.message}</div>`;
            }
        }

        async function retryQuery(queryId) {
            try {
                const res = await fetch(`./api/queries/${queryId}/retry`, {
                    method: 'POST'
                });
                if (!res.ok) {
                    alert(`Server error: ${res.status} ${res.statusText}`);
                    return;
                }
                const text = await res.text();
                if (!text) {
                    alert('Error: Empty response from server');
                    return;
                }
                const data = JSON.parse(text);
                if (data.success) {
                    alert(`Query #${queryId} has been requeued!`);
                    loadStats();
                    loadQueries();
                } else {
                    alert(`Error: ${data.error || 'Unknown error'}`);
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        }

        async function markFailed(queryId) {
            if (!confirm(`确定将 Query #${queryId} 标记为 Failed？`)) return;
            try {
                const res = await fetch(`./api/queries/${queryId}/mark_failed`, {
                    method: 'POST'
                });
                if (!res.ok) {
                    alert(`Server error: ${res.status} ${res.statusText}`);
                    return;
                }
                const data = await res.json();
                if (data.success) {
                    alert(`Query #${queryId} 已标记为 Failed`);
                    loadStats();
                    loadQueries();
                } else {
                    alert(`Error: ${data.error || 'Unknown error'}`);
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        }

        // ---- Accounts ----
        function getCookieAgeInfo(cookiesUpdatedAt) {
            if (!cookiesUpdatedAt) return { text: 'Unknown', color: '#999', icon: '?' };
            const now = new Date();
            const updated = new Date(cookiesUpdatedAt);
            const hoursAgo = (now - updated) / (1000 * 60 * 60);
            const daysAgo = hoursAgo / 24;

            if (hoursAgo < 6) return { text: `${Math.round(hoursAgo)}h ago`, color: '#16a34a', icon: '&#9679;' };  // green
            if (hoursAgo < 24) return { text: `${Math.round(hoursAgo)}h ago`, color: '#f59e0b', icon: '&#9679;' };  // yellow
            if (daysAgo < 3) return { text: `${Math.round(daysAgo)}d ago`, color: '#f97316', icon: '&#9679;' };  // orange
            if (daysAgo < 7) return { text: `${Math.round(daysAgo)}d ago`, color: '#ef4444', icon: '&#9888;' };  // red warning
            return { text: `${Math.round(daysAgo)}d ago`, color: '#dc2626', icon: '&#9888;' };  // red expired
        }

        async function loadAccounts() {
            try {
                const res = await fetch('./api/accounts');
                const data = await res.json();
                const body = document.getElementById('accounts-body');
                if (!data.length) {
                    body.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#999;">No accounts found</td></tr>';
                    return;
                }
                body.innerHTML = data.map(a => {
                    const statusCls = a.status === 'active' ? 'status-DONE' :
                                      a.status === 'banned' ? 'status-FAILED' : 'status-PENDING';
                    const cookieCount = a.cookie_count || 0;
                    const cookieAge = getCookieAgeInfo(a.cookies_updated_at);
                    const toggleLabel = a.status === 'active' ? 'Disable' : 'Enable';
                    const toggleClass = a.status === 'active' ? 'secondary' : 'success';
                    return `<tr>
                        <td>${a.id}</td>
                        <td><span class="llm-badge">${a.llm_name}</span></td>
                        <td>${a.phone_number || '-'}</td>
                        <td><span class="${statusCls}">${a.status.toUpperCase()}</span></td>
                        <td>${a.daily_used || 0} / ${a.daily_limit || 20}</td>
                        <td>${a.consecutive_fails || 0}</td>
                        <td>${cookieCount} cookies</td>
                        <td><span style="color:${cookieAge.color}; font-weight:500;" title="Last refreshed: ${a.cookies_updated_at || 'never'}">${cookieAge.icon} ${cookieAge.text}</span></td>
                        <td>
                            <button class="${toggleClass} small" onclick="toggleAccount(${a.id}, '${a.status}')">${toggleLabel}</button>
                            <button class="small" onclick="resetAccountFails(${a.id})">Reset</button>
                            <button class="small" style="background:#7c3aed;color:#fff;border:none;" onclick="triggerAutoLogin(${a.id})">Auto Login</button>
                            <button class="danger small" onclick="deleteAccount(${a.id})">Delete</button>
                        </td>
                    </tr>`;
                }).join('');
            } catch (e) {
                console.error('loadAccounts error:', e);
            }
        }

        async function toggleAccount(id, currentStatus) {
            const newStatus = currentStatus === 'active' ? 'banned' : 'active';
            try {
                const res = await fetch(`./api/accounts/${id}/status`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({status: newStatus})
                });
                const data = await res.json();
                if (data.success) loadAccounts();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) { alert('Error: ' + e.message); }
        }

        async function resetAccountFails(id) {
            try {
                const res = await fetch(`./api/accounts/${id}/reset`, { method: 'POST' });
                const data = await res.json();
                if (data.success) loadAccounts();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) { alert('Error: ' + e.message); }
        }

        async function deleteAccount(id) {
            if (!confirm(`确定删除账号 #${id}？此操作不可撤销。`)) return;
            try {
                const res = await fetch(`./api/accounts/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) loadAccounts();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) { alert('Error: ' + e.message); }
        }

        function showCookieUpload() {
            document.getElementById('cookie-upload-form').style.display = 'block';
        }
        function hideCookieUpload() {
            document.getElementById('cookie-upload-form').style.display = 'none';
        }

        function loadCookieFile(input) {
            const file = input.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = e => {
                document.getElementById('cookie-json').value = e.target.result;
            };
            reader.readAsText(file);
        }

        async function submitCookies() {
            const platform = document.getElementById('cookie-platform').value;
            const label = document.getElementById('cookie-label').value.trim();
            const dailyLimit = parseInt(document.getElementById('cookie-daily-limit').value) || 20;
            const jsonText = document.getElementById('cookie-json').value.trim();
            if (!jsonText) { alert('Please paste or upload cookies JSON'); return; }

            try {
                JSON.parse(jsonText);
            } catch (e) {
                alert('Invalid JSON: ' + e.message);
                return;
            }

            const lsEl = document.getElementById('local-storage-json');
            let localStorageText = lsEl ? lsEl.value.trim() : '';
            if (localStorageText) {
                // 清理常见格式问题：去掉首尾单引号、反引号
                localStorageText = localStorageText.replace(/^['`]+|['`]+$/g, '').trim();
                // 将单引号 key/value 替换为双引号（简单场景）
                if (localStorageText.includes("'") && !localStorageText.includes('"')) {
                    localStorageText = localStorageText.replace(/'/g, '"');
                }
                try {
                    const parsed = JSON.parse(localStorageText);
                    if (typeof parsed !== 'object' || Array.isArray(parsed)) {
                        alert('localStorage JSON must be an object like {"userToken": "..."}');
                        return;
                    }
                    localStorageText = JSON.stringify(parsed);  // normalize
                } catch (e) {
                    alert('localStorage JSON is invalid: ' + e.message + '\\n\\nExpected format:\\n{"userToken": "..."}')
                    return;
                }
            }

            try {
                const res = await fetch('./api/accounts/import_cookies', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        platform: platform,
                        label: label,
                        daily_limit: dailyLimit,
                        cookies_json: jsonText,
                        local_storage: localStorageText || '',
                    })
                });
                const data = await res.json();
                if (data.success) {
                    alert(data.message || 'Cookies imported successfully!');
                    document.getElementById('cookie-json').value = '';
                    document.getElementById('cookie-label').value = '';
                    if (document.getElementById('local-storage-json'))
                        document.getElementById('local-storage-json').value = '';
                    hideCookieUpload();
                    loadAccounts();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        // ── SMS Register / Auto Login ──────────────────────────────
        function showSmsRegister() {
            document.getElementById('sms-register-form').style.display = 'block';
        }
        function hideSmsRegister() {
            document.getElementById('sms-register-form').style.display = 'none';
            document.getElementById('sms-task-status').style.display = 'none';
        }

        async function triggerSmsRegister() {
            const platform = document.getElementById('sms-platform').value;
            const statusDiv = document.getElementById('sms-task-status');
            statusDiv.style.display = 'block';
            statusDiv.innerHTML = '<span style="color:#7c3aed;">Triggering registration for ' + platform + '...</span>';
            try {
                const res = await fetch('./api/sms_register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({platform: platform})
                });
                const data = await res.json();
                if (data.success && data.task_id) {
                    pollTaskStatus(data.task_id, statusDiv);
                } else {
                    statusDiv.innerHTML = '<span style="color:#dc2626;">Error: ' + (data.error || 'Unknown') + '</span>';
                }
            } catch (e) {
                statusDiv.innerHTML = '<span style="color:#dc2626;">Error: ' + e.message + '</span>';
            }
        }

        async function triggerAutoLogin(accountId) {
            if (!confirm('Trigger auto SMS login for account #' + accountId + '?')) return;
            try {
                const res = await fetch('./api/accounts/' + accountId + '/auto_login', { method: 'POST' });
                const data = await res.json();
                if (data.success && data.task_id) {
                    alert('Auto login triggered! Task ID: ' + data.task_id + '\\nCheck task status in the SMS Register panel.');
                    // Show the status panel
                    document.getElementById('sms-register-form').style.display = 'block';
                    const statusDiv = document.getElementById('sms-task-status');
                    statusDiv.style.display = 'block';
                    statusDiv.innerHTML = '<span style="color:#7c3aed;">Auto login for account #' + accountId + ' started...</span>';
                    pollTaskStatus(data.task_id, statusDiv);
                } else {
                    alert('Error: ' + (data.error || 'Unknown'));
                }
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        function pollTaskStatus(taskId, statusDiv) {
            let attempts = 0;
            const maxAttempts = 60; // 3 minutes max (60 * 3s)
            const interval = setInterval(async () => {
                attempts++;
                if (attempts > maxAttempts) {
                    clearInterval(interval);
                    statusDiv.innerHTML = '<span style="color:#d97706;">Timeout: task is still running. Check worker logs.</span>';
                    return;
                }
                try {
                    const res = await fetch('./api/task_status/' + taskId);
                    const data = await res.json();
                    if (data.state === 'PENDING' || data.state === 'RECEIVED') {
                        statusDiv.innerHTML = '<span style="color:#7c3aed;">Waiting for worker to pick up task...</span>';
                    } else if (data.state === 'STARTED' || data.state === 'RETRY') {
                        statusDiv.innerHTML = '<span style="color:#2563eb;">Logging in... (SMS verification in progress)</span>';
                    } else if (data.state === 'SUCCESS') {
                        clearInterval(interval);
                        const r = data.result || {};
                        if (r.status === 'success') {
                            statusDiv.innerHTML = '<span style="color:#059669;">Login successful! Account #' + (r.account_id || '') + (r.phone ? ' (' + r.phone + ')' : '') + '</span>';
                        } else {
                            statusDiv.innerHTML = '<span style="color:#dc2626;">Task completed but login failed: ' + (r.reason || r.status || 'unknown') + '</span>';
                        }
                        loadAccounts();
                    } else if (data.state === 'FAILURE') {
                        clearInterval(interval);
                        statusDiv.innerHTML = '<span style="color:#dc2626;">Task failed: ' + (data.error || 'Unknown error') + '</span>';
                    }
                } catch (e) {
                    // Network error, keep polling
                }
            }, 3000);
        }

        async function backfillCitations() {
            try {
                const res = await fetch('./api/backfill_citations', { method: 'POST' });
                const data = await res.json();
                if (data.success) {
                    alert(`Backfill complete: scanned ${data.scanned} responses, updated ${data.updated} with citations`);
                    loadQueries();
                } else {
                    alert(`Error: ${data.error || 'Unknown error'}`);
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }
        }

        // ---- Debug Files Viewer (HTML + Screenshots + JSON) ----
        let htmlFilesCurrentPage = 1;
        let htmlFilesQueryId = null;

        async function loadHtmlFiles(queryId) {
            // Only update queryId when explicitly passed; otherwise keep current filter context.
            if (queryId !== undefined) {
                htmlFilesQueryId = queryId;
                htmlFilesCurrentPage = 1;
            }
            const body = document.getElementById('html-files-body');
            body.innerHTML = '<div style="color:#999;font-size:13px;">Loading...</div>';
            const perPage = parseInt(document.getElementById('html-per-page').value || '20', 10);
            const typeFilter = document.getElementById('html-filter-type').value || 'all';
            const params = new URLSearchParams();
            params.append('page', htmlFilesCurrentPage);
            params.append('per_page', perPage);
            if (htmlFilesQueryId) params.append('query_id', htmlFilesQueryId);
            const res = await fetch('./api/html_files?' + params.toString());
            const data = await res.json();
            let items = data.items || [];
            const total = data.total || 0;
            const pages = data.pages || 1;

            if (typeFilter !== 'all') {
                items = items.filter(f => f.type === typeFilter);
            }

            if (!items.length) {
                body.innerHTML = '<div style="color:#999;font-size:13px;">No debug files match the current filter.</div>';
                document.getElementById('html-files-pagination').innerHTML = '';
                return;
            }

            const typeBadge = t => {
                const colors = {html:'#4f46e5', image:'#059669', json:'#d97706', other:'#64748b'};
                const c = colors[t] || colors.other;
                return '<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:' +
                    c + '22;color:' + c + ';font-size:11px;font-weight:600;text-transform:uppercase;">' +
                    t + '</span>';
            };

            const actionFor = f => {
                if (f.type === 'image') {
                    return "<span class='html-link' onclick='showImage(" +
                        JSON.stringify(f.path) + ", " + JSON.stringify(f.name) + ")'>View Image</span>";
                }
                if (f.type === 'html' || f.type === 'json') {
                    return "<span class='html-link' onclick='showHtmlSource(" +
                        JSON.stringify(f.path) + ", " + JSON.stringify(f.name) + ")'>View Source</span>";
                }
                return '<span style="color:#999;">—</span>';
            };

            body.innerHTML = '<table style="font-size:13px;width:100%;"><thead><tr>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;width:70px;">Type</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;width:80px;">Preview</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;">File</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;width:80px;">Size</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;width:160px;">Modified</th>' +
                '<th style="text-align:left;padding:6px 10px;background:#f8fafc;width:100px;">Action</th>' +
                '</tr></thead><tbody>' +
                items.map(f => {
                    const kb = (f.size / 1024).toFixed(1);
                    const dt = new Date(f.mtime * 1000).toLocaleString();
                    let preview = '<span style="color:#ccc;">—</span>';
                    if (f.type === 'image') {
                        const src = './api/screenshot?path=' + encodeURIComponent(f.path);
                        preview = "<img src='" + src + "' style='width:60px;height:40px;object-fit:cover;border-radius:4px;cursor:pointer;border:1px solid #e2e8f0;' onclick='showImage(" +
                            JSON.stringify(f.path) + ", " + JSON.stringify(f.name) + ")' loading='lazy'>";
                    }
                    return '<tr>' +
                        '<td style="padding:6px 10px;">' + typeBadge(f.type) + '</td>' +
                        '<td style="padding:6px 10px;">' + preview + '</td>' +
                        '<td style="padding:6px 10px;font-family:monospace;max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + escapeHtml(f.path) + '">' + escapeHtml(f.name) + '</td>' +
                        '<td style="padding:6px 10px;white-space:nowrap;">' + kb + ' KB</td>' +
                        '<td style="padding:6px 10px;white-space:nowrap;">' + dt + '</td>' +
                        "<td style='padding:6px 10px;'>" + actionFor(f) + "</td>" +
                        '</tr>';
                }).join('') + '</tbody></table>';

            renderHtmlFilesPagination(htmlFilesCurrentPage, pages, total);
        }

        function renderHtmlFilesPagination(page, totalPages, total) {
            const pag = document.getElementById('html-files-pagination');
            if (totalPages <= 1) {
                pag.innerHTML = total
                    ? '<div style="color:#999;font-size:12px;">' + total + ' file' + (total !== 1 ? 's' : '') + '</div>'
                    : '';
                return;
            }
            let startPage = Math.max(1, page - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);
            let html = '';
            html += '<button ' + (page === 1 ? 'disabled' : '') + ' onclick="goToHtmlFilesPage(' + (page - 1) + ')">&laquo; Prev</button>';
            if (startPage > 1) {
                html += '<button onclick="goToHtmlFilesPage(1)">1</button>';
                if (startPage > 2) html += '<span style="padding:6px 4px;color:#999;">…</span>';
            }
            for (let p = startPage; p <= endPage; p++) {
                html += '<button class="' + (p === page ? 'active' : '') + '" onclick="goToHtmlFilesPage(' + p + ')">' + p + '</button>';
            }
            if (endPage < totalPages) {
                if (endPage < totalPages - 1) html += '<span style="padding:6px 4px;color:#999;">…</span>';
                html += '<button onclick="goToHtmlFilesPage(' + totalPages + ')">' + totalPages + '</button>';
            }
            html += '<button ' + (page === totalPages ? 'disabled' : '') + ' onclick="goToHtmlFilesPage(' + (page + 1) + ')">Next &raquo;</button>';
            html += '<span style="padding:6px 12px;color:#666;font-size:12px;">Page ' + page + ' / ' + totalPages + ' · ' + total + ' total</span>';
            pag.innerHTML = html;
        }

        function goToHtmlFilesPage(page) {
            htmlFilesCurrentPage = page;
            loadHtmlFiles();
        }

        function showImage(path, name) {
            document.getElementById('image-modal-title').textContent = name || path;
            const img = document.getElementById('image-viewer-content');
            img.src = './api/screenshot?path=' + encodeURIComponent(path);
            img.style.maxWidth = '100%';
            img.style.cursor = 'zoom-in';
            document.getElementById('image-modal').classList.add('show');
        }

        function closeImageModal() {
            document.getElementById('image-modal').classList.remove('show');
            document.getElementById('image-viewer-content').src = '';
        }

        async function showHtmlSource(path, name) {
            document.getElementById('html-modal-title').textContent = name || path;
            document.getElementById('html-viewer-content').textContent = 'Loading...';
            document.getElementById('html-search-input').value = '';
            document.getElementById('html-search-count').textContent = '';
            document.getElementById('html-modal').classList.add('show');
            const res = await fetch('./api/html?path=' + encodeURIComponent(path));
            if (!res.ok) {
                rawHtmlContent = 'Error loading file: ' + res.status;
            } else {
                rawHtmlContent = await res.text();
            }
            document.getElementById('html-viewer-content').textContent = rawHtmlContent;
        }

        function searchHtml(term) {
            const viewer = document.getElementById('html-viewer-content');
            const countEl = document.getElementById('html-search-count');
            if (!term) {
                viewer.textContent = rawHtmlContent;
                countEl.textContent = '';
                return;
            }
            const escaped = term.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
            const regex = new RegExp(escaped, 'gi');
            const matches = rawHtmlContent.match(regex);
            const count = matches ? matches.length : 0;
            countEl.textContent = count + ' match' + (count !== 1 ? 'es' : '');
            if (count === 0) {
                viewer.textContent = rawHtmlContent;
                return;
            }
            const parts = rawHtmlContent.split(regex);
            const matchArr = rawHtmlContent.match(regex) || [];
            viewer.innerHTML = '';
            parts.forEach((part, i) => {
                viewer.appendChild(document.createTextNode(part));
                if (i < matchArr.length) {
                    const mark = document.createElement('mark');
                    mark.textContent = matchArr[i];
                    viewer.appendChild(mark);
                }
            });
            const firstMark = viewer.querySelector('mark');
            if (firstMark) firstMark.scrollIntoView({ block: 'center' });
        }

        function closeHtmlModal() {
            document.getElementById('html-modal').classList.remove('show');
        }

        // ---- Segments ----
        let segmentsData = [];
        let segCurrentPage = 1;
        const segPerPage = 5;

        async function loadSegments() {
            const body = document.getElementById('segments-body');
            body.innerHTML = '<div style="color:#999;font-size:13px;">Loading...</div>';
            try {
                const res = await fetch('./api/segments');
                const data = await res.json();
                if (data.error) {
                    body.innerHTML = '<div style="color:#dc2626;font-size:13px;">Error: ' + escapeHtml(data.error) + '</div>';
                    return;
                }
                if (!Array.isArray(data) || !data.length) {
                    body.innerHTML = '<div style="color:#999;font-size:13px;">No segments defined</div>';
                    return;
                }
                segmentsData = data;
                segCurrentPage = 1;
                renderSegments();
            } catch (e) {
                body.innerHTML = '<div style="color:#dc2626;font-size:13px;">Error loading segments: ' + escapeHtml(e.message) + '</div>';
            }
        }

        function renderSegments() {
            const totalPages = Math.ceil(segmentsData.length / segPerPage);
            if (segCurrentPage > totalPages) segCurrentPage = totalPages;
            if (segCurrentPage < 1) segCurrentPage = 1;
            const start = (segCurrentPage - 1) * segPerPage;
            const pageData = segmentsData.slice(start, start + segPerPage);

            const body = document.getElementById('segments-body');
            body.innerHTML = '<div style="margin-bottom:8px;font-size:12px;color:#888;">Showing ' + (start+1) + '-' + (start+pageData.length) + ' of ' + segmentsData.length + ' segments</div>' +
            pageData.map(seg => `
                    <div style="background:white; border:1px solid #e5e7eb; border-radius:8px; padding:16px; margin-bottom:12px;">
                        <div style="display:flex; align-items:center; gap:12px; margin-bottom:10px;">
                            <span style="font-weight:700; font-size:16px; color:#333;">${escapeHtml(seg.name)}</span>
                            <span style="font-size:12px; color:#888; font-family:monospace;">${escapeHtml(seg.id)}</span>
                            <span class="llm-badge">${escapeHtml(seg.language)}</span>
                            ${seg.profile_count !== undefined ? '<span style="font-size:12px; color:#059669; font-weight:600;">' + seg.profile_count + ' profiles</span>' : ''}
                        </div>
                        <div style="color:#666; font-size:13px; margin-bottom:12px;">${escapeHtml(seg.description)}</div>
                        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px; font-size:13px;">
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Target LLMs</div>
                                <div>${seg.target_llms.map(l => '<span class="llm-badge" style="margin:2px;">' + escapeHtml(l) + '</span>').join(' ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Tone</div>
                                <div style="color:#333;">${seg.tone_pool.join(', ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Verbosity</div>
                                <div style="color:#333;">${seg.verbosity_pool.join(', ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Search Style</div>
                                <div style="color:#333;">${seg.search_style_pool.join(', ')}</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Role Context Rate</div>
                                <div style="color:#333;">${(seg.add_role_context_rate * 100).toFixed(0)}%</div>
                            </div>
                            <div style="background:#f8fafc; padding:8px 12px; border-radius:4px;">
                                <div style="color:#888; font-size:11px; margin-bottom:4px;">Mobile Rate</div>
                                <div style="color:#333;">${(seg.device_mobile_rate * 100).toFixed(0)}%</div>
                            </div>
                        </div>
                        <div style="margin-top:10px; display:flex; gap:16px; flex-wrap:wrap;">
                            <div style="flex:1; min-width:250px;">
                                <div style="color:#888; font-size:11px; margin-bottom:6px;">Age Ranges (${seg.age_ranges.length})</div>
                                <div style="display:flex; flex-wrap:wrap; gap:4px;">
                                    ${seg.age_ranges.map(a => '<span style="display:inline-block;padding:2px 8px;background:#e0e7ff;color:#4f46e5;border-radius:999px;font-size:12px;">' + a.min_age + '-' + a.max_age + '</span>').join('')}
                                </div>
                            </div>
                            <div style="flex:1; min-width:250px;">
                                <div style="color:#888; font-size:11px; margin-bottom:6px;">City Tiers (${seg.city_tiers.length})</div>
                                <div style="display:flex; flex-wrap:wrap; gap:4px;">
                                    ${seg.city_tiers.map(c => '<span style="display:inline-block;padding:2px 8px;background:#dcfce7;color:#166534;border-radius:999px;font-size:12px;">' + escapeHtml(c) + '</span>').join('')}
                                </div>
                            </div>
                        </div>
                        <div style="margin-top:10px;">
                            <div style="color:#888; font-size:11px; margin-bottom:6px;">Role Variants (${seg.role_variants.length})</div>
                            <table style="width:100%; font-size:12px; border-collapse:collapse;">
                                <thead>
                                    <tr style="background:#f8fafc;">
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Role</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Profession</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Company Size</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Income</th>
                                        <th style="padding:4px 8px; text-align:left; font-weight:600; color:#666;">Pain Points</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${seg.role_variants.map(rv => '<tr style="border-top:1px solid #eee;">' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.label) + '</td>' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.profession) + '</td>' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.company_size) + '</td>' +
                                        '<td style="padding:4px 8px;">' + escapeHtml(rv.income_level) + '</td>' +
                                        '<td style="padding:4px 8px;">' + rv.pain_points.map(p => escapeHtml(p)).join(', ') + '</td>' +
                                    '</tr>').join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `).join('');

            // Segment pagination
            if (segmentsData.length > segPerPage) {
                const totalPages = Math.ceil(segmentsData.length / segPerPage);
                let pagHtml = '<div class="pagination" style="margin-top:16px;">';
                pagHtml += '<button ' + (segCurrentPage === 1 ? 'disabled' : '') + ' onclick="segCurrentPage--; renderSegments();">&laquo; Prev</button>';
                for (let p = 1; p <= totalPages; p++) {
                    pagHtml += '<button class="' + (p === segCurrentPage ? 'active' : '') + '" onclick="segCurrentPage=' + p + '; renderSegments();">' + p + '</button>';
                }
                pagHtml += '<button ' + (segCurrentPage === totalPages ? 'disabled' : '') + ' onclick="segCurrentPage++; renderSegments();">Next &raquo;</button>';
                pagHtml += '</div>';
                body.innerHTML += pagHtml;
            }
        }

        // ---- Profiles ----
        let profilesData = [];
        let profilesFiltered = [];
        let profCurrentPage = 1;
        const profPerPage = 20;

        async function loadProfiles() {
            try {
                const res = await fetch('./api/profiles');
                const data = await res.json();
                if (data.error) {
                    document.getElementById('profiles-body').innerHTML =
                        '<tr><td colspan="12" style="text-align:center;color:#dc2626;">Error: ' + escapeHtml(data.error) + '</td></tr>';
                    return;
                }
                profilesData = Array.isArray(data) ? data : [];

                // Populate segment filter dropdown
                const segFilter = document.getElementById('profile-filter-segment');
                const currentVal = segFilter.value;
                const segments = [...new Set(profilesData.map(p => (p.persona_traits || {}).segment_name).filter(Boolean))];
                segFilter.innerHTML = '<option value="">All Segments</option>' +
                    segments.map(s => '<option value="' + escapeHtml(s) + '">' + escapeHtml(s) + '</option>').join('');
                segFilter.value = currentVal;

                profCurrentPage = 1;
                filterProfiles();
            } catch (e) {
                console.error('loadProfiles error:', e);
                document.getElementById('profiles-body').innerHTML =
                    '<tr><td colspan="12" style="text-align:center;color:#dc2626;">Error loading profiles: ' + escapeHtml(e.message) + '</td></tr>';
            }
        }

        function filterProfiles() {
            const segFilter = document.getElementById('profile-filter-segment').value;
            const langFilter = document.getElementById('profile-filter-lang').value;
            const deviceFilter = document.getElementById('profile-filter-device').value;

            profilesFiltered = profilesData;
            if (segFilter) {
                profilesFiltered = profilesFiltered.filter(p => (p.persona_traits || {}).segment_name === segFilter);
            }
            if (langFilter) {
                profilesFiltered = profilesFiltered.filter(p => p.language === langFilter);
            }
            if (deviceFilter) {
                profilesFiltered = profilesFiltered.filter(p => p.device_type === deviceFilter);
            }

            profCurrentPage = 1;
            renderProfiles();
        }

        function renderProfiles() {
            const data = profilesFiltered;
            const body = document.getElementById('profiles-body');

            document.getElementById('profile-count-label').textContent =
                data.length + ' / ' + profilesData.length + ' profiles';

            if (!data.length) {
                body.innerHTML = '<tr><td colspan="12" style="text-align:center;color:#999;">No profiles found</td></tr>';
                document.getElementById('profiles-pagination').innerHTML = '';
                return;
            }

            const totalPages = Math.ceil(data.length / profPerPage);
            if (profCurrentPage > totalPages) profCurrentPage = totalPages;
            if (profCurrentPage < 1) profCurrentPage = 1;
            const start = (profCurrentPage - 1) * profPerPage;
            const pageData = data.slice(start, start + profPerPage);

            body.innerHTML = pageData.map(p => {
                const traits = p.persona_traits || {};
                const segName = traits.segment_name || '-';
                const traitStr = [traits.tone, traits.verbosity, traits.search_style].filter(Boolean).join(' / ') || '-';
                return `<tr>
                    <td>${p.id}</td>
                    <td>${escapeHtml(p.name || '-')}</td>
                    <td style="font-size:12px;"><span style="display:inline-block;padding:2px 8px;background:#fef3c7;color:#92400e;border-radius:999px;font-size:11px;">${escapeHtml(segName)}</span></td>
                    <td>${escapeHtml(p.age_range || '-')}</td>
                    <td>${escapeHtml(p.location || '-')}</td>
                    <td>${escapeHtml(p.country_code || '-')}</td>
                    <td style="font-size:12px;">${escapeHtml(p.profession || '-')}</td>
                    <td><span class="llm-badge">${escapeHtml(p.language || '-')}</span></td>
                    <td>${escapeHtml(p.device_type || '-')}</td>
                    <td style="font-size:12px;" title="${escapeHtml(JSON.stringify(traits))}">${escapeHtml(traitStr)}</td>
                    <td>${p.query_count || 0}</td>
                    <td>
                        <button class="small" onclick="editProfile(${p.id})">Edit</button>
                        <button class="danger small" onclick="deleteProfile(${p.id})">Delete</button>
                    </td>
                </tr>`;
            }).join('');

            // Pagination
            const pagEl = document.getElementById('profiles-pagination');
            if (totalPages <= 1) {
                pagEl.innerHTML = '';
                return;
            }
            let startPage = Math.max(1, profCurrentPage - 2);
            let endPage = Math.min(totalPages, startPage + 4);
            if (endPage - startPage < 4) startPage = Math.max(1, endPage - 4);

            let html = '<button ' + (profCurrentPage === 1 ? 'disabled' : '') + ' onclick="profCurrentPage--; renderProfiles();">&laquo; Prev</button>';
            for (let p = startPage; p <= endPage; p++) {
                html += '<button class="' + (p === profCurrentPage ? 'active' : '') + '" onclick="profCurrentPage=' + p + '; renderProfiles();">' + p + '</button>';
            }
            html += '<button ' + (profCurrentPage === totalPages ? 'disabled' : '') + ' onclick="profCurrentPage++; renderProfiles();">Next &raquo;</button>';
            pagEl.innerHTML = html;
        }

        function showProfileForm(profile) {
            document.getElementById('profile-form-container').style.display = 'block';
            document.getElementById('profile-alert').innerHTML = '';
            if (profile) {
                document.getElementById('profile-form-title').textContent = 'Edit Profile #' + profile.id;
                document.getElementById('profile-edit-id').value = profile.id;
                document.getElementById('profile-name').value = profile.name || '';
                document.getElementById('profile-age-range').value = profile.age_range || '';
                document.getElementById('profile-location').value = profile.location || '';
                document.getElementById('profile-country').value = profile.country_code || '';
                document.getElementById('profile-profession').value = profile.profession || '';
                document.getElementById('profile-language').value = profile.language || 'zh';
                document.getElementById('profile-device').value = profile.device_type || 'desktop';
                const traits = profile.persona_traits || {};
                document.getElementById('profile-tone').value = traits.tone || 'casual';
                document.getElementById('profile-verbosity').value = traits.verbosity || 'medium';
                document.getElementById('profile-search-style').value = traits.search_style || 'solution_oriented';
            } else {
                document.getElementById('profile-form-title').textContent = 'Create New Profile';
                document.getElementById('profile-edit-id').value = '';
                document.getElementById('profile-form').reset();
            }
        }

        function hideProfileForm() {
            document.getElementById('profile-form-container').style.display = 'none';
        }

        function editProfile(id) {
            const profile = profilesData.find(p => p.id === id);
            if (profile) showProfileForm(profile);
        }

        async function submitProfile(event) {
            event.preventDefault();
            const alertDiv = document.getElementById('profile-alert');
            alertDiv.innerHTML = '';

            const editId = document.getElementById('profile-edit-id').value;
            const payload = {
                name: document.getElementById('profile-name').value,
                age_range: document.getElementById('profile-age-range').value,
                location: document.getElementById('profile-location').value,
                country_code: document.getElementById('profile-country').value,
                profession: document.getElementById('profile-profession').value,
                language: document.getElementById('profile-language').value,
                device_type: document.getElementById('profile-device').value,
                persona_traits: {
                    tone: document.getElementById('profile-tone').value,
                    verbosity: document.getElementById('profile-verbosity').value,
                    search_style: document.getElementById('profile-search-style').value,
                }
            };

            try {
                const url = editId ? './api/profiles/' + editId : './api/profiles';
                const method = editId ? 'PUT' : 'POST';
                const res = await fetch(url, {
                    method: method,
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    alertDiv.innerHTML = '<div class="alert success">' + (editId ? 'Profile updated!' : 'Profile created!') + '</div>';
                    hideProfileForm();
                    loadProfiles();
                } else {
                    alertDiv.innerHTML = '<div class="alert error">Error: ' + (data.error || 'Unknown') + '</div>';
                }
            } catch (e) {
                alertDiv.innerHTML = '<div class="alert error">Error: ' + e.message + '</div>';
            }
        }

        async function deleteProfile(id) {
            if (!confirm('Delete profile #' + id + '? This cannot be undone.')) return;
            try {
                const res = await fetch('./api/profiles/' + id, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) loadProfiles();
                else alert('Error: ' + (data.error || 'Unknown'));
            } catch (e) {
                alert('Error: ' + e.message);
            }
        }

        // Load on page load
        loadStats();
        loadQueries();

        // ---- Analyzer functions ----
        let analyzerCurrentPage = 0;
        const ANALYZER_PAGE_SIZE = 30;

        function scoreClass(v) { return v >= 60 ? 'high' : v >= 35 ? 'mid' : 'low'; }
        function scoreBar(v, max=100) {
            const cls = scoreClass(v);
            return `<span class="score-bar score-${cls}"><span class="score-fill" style="width:${Math.min(v/max*100,100)}%"></span></span> ${v.toFixed(1)}`;
        }
        function badge(text, cls) { return `<span class="badge badge-${cls}">${text}</span>`; }
        function statusBadge(s) {
            const m = {done:'done',pending:'pending',failed:'failed',running:'running'};
            return badge(s, m[s] || 'neutral');
        }
        function sentimentBadge(s) {
            const m = {positive:'positive',negative:'negative',neutral:'neutral'};
            return badge(s || '-', m[s] || 'neutral');
        }

        async function loadAnalyzerStats() {
            try {
                const r = await fetch('./api/analyzer/stats');
                const d = await r.json();
                document.getElementById('analyzer-stats').innerHTML = `
                    <div class="stat-card"><div class="stat-value">${d.total}</div><div class="stat-label">Total Responses</div></div>
                    <div class="stat-card"><div class="stat-value done">${d.done}</div><div class="stat-label">Analyzed</div></div>
                    <div class="stat-card"><div class="stat-value pending">${d.pending}</div><div class="stat-label">Pending</div></div>
                    <div class="stat-card"><div class="stat-value failed">${d.failed}</div><div class="stat-label">Failed</div></div>
                    <div class="stat-card"><div class="stat-value" style="color:#7c3aed;">${d.avg_geo_score != null ? d.avg_geo_score.toFixed(1) : '-'}</div><div class="stat-label">Avg GEO Score</div></div>
                    <div class="stat-card"><div class="stat-value">${d.total_brands_tracked}</div><div class="stat-label">Brands Tracked</div></div>
                `;
            } catch(e) { console.error('loadAnalyzerStats:', e); }
        }

        async function loadBrands() {
            try {
                const r = await fetch('./api/analyzer/brands');
                const d = await r.json();
                ['f-brand','d-brand','t-brand'].forEach(id => {
                    const sel = document.getElementById(id);
                    if (!sel) return;
                    const first = sel.options[0];
                    sel.innerHTML = '';
                    sel.appendChild(first);
                    d.forEach(b => { const o = document.createElement('option'); o.value = b.id; o.textContent = b.name; sel.appendChild(o); });
                });
            } catch(e) { console.error('loadBrands:', e); }
        }

        async function loadLLMs() {
            try {
                const r = await fetch('./api/analyzer/llms');
                const d = await r.json();
                ['f-llm','d-llm'].forEach(id => {
                    const sel = document.getElementById(id);
                    if (!sel) return;
                    const first = sel.options[0];
                    sel.innerHTML = '';
                    sel.appendChild(first);
                    d.forEach(l => { const o = document.createElement('option'); o.value = l; o.textContent = l; sel.appendChild(o); });
                });
            } catch(e) { console.error('loadLLMs:', e); }
        }

        async function loadAnalyzerResponses(page) {
            if (page === undefined) page = 0;
            if (page < 0) page = 0;
            analyzerCurrentPage = page;
            const p = new URLSearchParams();
            p.set('limit', ANALYZER_PAGE_SIZE);
            p.set('offset', page * ANALYZER_PAGE_SIZE);
            const status = document.getElementById('f-status').value;
            const brand = document.getElementById('f-brand').value;
            const llm = document.getElementById('f-llm').value;
            const dateFrom = document.getElementById('f-date-from').value;
            const dateTo = document.getElementById('f-date-to').value;
            if (status) p.set('status', status);
            if (brand) p.set('brand_id', brand);
            if (llm) p.set('llm', llm);
            if (dateFrom) p.set('date_from', dateFrom);
            if (dateTo) p.set('date_to', dateTo);

            const r = await fetch('./api/analyzer/responses?' + p.toString());
            const d = await r.json();
            document.getElementById('page-info').textContent = `Page ${page+1} (${d.length} results)`;

            if (!d.length) {
                document.getElementById('responses-table').innerHTML = '<div class="empty-state">No responses found</div>';
                return;
            }

            let html = `<table><thead><tr>
                <th>ID</th><th>Brand</th><th>LLM</th><th>Status</th>
                <th>GEO Score</th><th>Visibility</th><th>Sentiment</th><th>SOV</th><th>Citations</th>
                <th>Brands</th><th>Target</th><th>Date</th><th></th>
            </tr></thead><tbody>`;
            d.forEach(r => {
                const geo = r.geo_score != null ? `<span class="geo-score ${scoreClass(r.geo_score)}">${r.geo_score.toFixed(1)}</span>` : '-';
                html += `<tr>
                    <td>${r.response_id}</td>
                    <td>${r.brand_name || '-'}</td>
                    <td>${r.target_llm || '-'}</td>
                    <td>${statusBadge(r.analysis_status)}</td>
                    <td>${geo}</td>
                    <td>${r.visibility_score != null ? scoreBar(r.visibility_score) : '-'}</td>
                    <td>${r.sentiment_score != null ? scoreBar(r.sentiment_score) : '-'}</td>
                    <td>${r.sov_score != null ? scoreBar(r.sov_score) : '-'}</td>
                    <td>${r.citation_score != null ? scoreBar(r.citation_score) : '-'}</td>
                    <td>${r.total_brands_mentioned ?? '-'}</td>
                    <td>${r.target_brand_mentioned ? sentimentBadge(r.target_brand_sentiment) : badge('No','neutral')}</td>
                    <td class="text-muted">${r.collected_at ? r.collected_at.substring(0,10) : '-'}</td>
                    <td>
                        <button class="small" onclick="toggleDetail(${r.response_id},this)">Detail</button>
                        <button class="small" style="margin-left:4px;background:#7c3aed;color:#fff;" onclick="rerunAnalysis(${r.response_id},this)">Rerun</button>
                    </td>
                </tr>
                <tr id="detail-${r.response_id}" style="display:none"><td colspan="13"><div class="detail-panel" id="dp-${r.response_id}">Loading...</div></td></tr>`;
            });
            html += '</tbody></table>';
            document.getElementById('responses-table').innerHTML = html;
        }

        async function toggleDetail(rid, btn) {
            const row = document.getElementById('detail-' + rid);
            if (row.style.display !== 'none') { row.style.display = 'none'; return; }
            row.style.display = '';
            const dp = document.getElementById('dp-' + rid);
            dp.innerHTML = 'Loading...';
            const r = await fetch('./api/analyzer/response/' + rid);
            const d = await r.json();

            if (d.no_analysis) {
                dp.innerHTML = `
                    <div style="color:#d97706;font-weight:600;margin-bottom:10px;">Not analyzed yet (status: ${d.analysis_status || 'pending'})</div>
                    ${d.query_text ? '<div class="detail-section"><h4>Query</h4><div>'+escapeHtml(d.query_text)+'</div></div>' : ''}
                    ${d.raw_text ? '<details open style="margin-top:10px;"><summary style="cursor:pointer;font-weight:600;">Raw Response Text</summary><pre style="font-size:11px;max-height:400px;overflow:auto;background:#f1f5f9;padding:10px;border-radius:4px;margin-top:5px;">'+escapeHtml(d.raw_text)+'</pre></details>' : '<div class="text-muted">No response text available</div>'}
                `;
                return;
            }

            if (d.error) { dp.innerHTML = '<div class="text-muted">' + d.error + '</div>'; return; }

            let mentionsHtml = '';
            if (d.mentions && d.mentions.length) {
                mentionsHtml = d.mentions.map(m => `
                    <div class="mention-item">
                        <strong>${m.brand_name}</strong>${m.product_name ? ' / '+m.product_name : ''}
                        ${m.is_target ? badge('TARGET','done') : ''}
                        ${badge(m.position_type || '-', 'neutral')}
                        ${m.position_rank ? '#'+m.position_rank : ''}
                        ${sentimentBadge(m.sentiment)}
                        <span class="text-muted">(score: ${m.sentiment_score?.toFixed(2) ?? '-'}, mentions: ${m.mention_count})</span>
                        ${m.drivers && m.drivers.length ? '<div style="margin-top:4px;">' + m.drivers.map(dr =>
                            `<span class="driver-tag ${dr.polarity==='positive'?'driver-pos':'driver-neg'}">${dr.driver_text}</span>`
                        ).join('') + '</div>' : ''}
                        ${m.context_snippet ? '<div class="text-muted" style="margin-top:4px;font-style:italic;">"'+m.context_snippet.substring(0,150)+'..."</div>' : ''}
                    </div>
                `).join('');
            } else {
                mentionsHtml = '<div class="text-muted">No brand mentions</div>';
            }

            let citationsHtml = '';
            if (d.citations && d.citations.length) {
                citationsHtml = d.citations.map(c =>
                    `<div style="padding:4px 0;"><a href="${c.url}" target="_blank">${c.domain || c.url}</a> ${badge(c.source_type||'other','neutral')} <span class="text-muted">${c.title||''}</span></div>`
                ).join('');
            } else {
                citationsHtml = '<div class="text-muted">No citations</div>';
            }

            let featuresHtml = '';
            if (d.features && d.features.length) {
                featuresHtml = d.features.map(f =>
                    `<div style="padding:4px 0;">${f.brand_name}/${f.product_name}: <strong>${f.feature_name}</strong> ${sentimentBadge(f.feature_sentiment)} ${f.scenario ? badge(f.scenario,'neutral') : ''} ${f.price_positioning ? badge(f.price_positioning,'neutral') : ''}</div>`
                ).join('');
            }

            dp.innerHTML = `
                <div class="detail-grid">
                    <div class="detail-section">
                        <h4>Dimensions</h4>
                        <div>Industry: <strong>${d.dimension_industry || '-'}</strong></div>
                        <div>Company: <strong>${d.dimension_company || '-'}</strong></div>
                        <div>Product: <strong>${d.dimension_product || '-'}</strong></div>
                        <div>Category: <strong>${d.dimension_category || '-'}</strong></div>
                        <div class="text-muted" style="margin-top:8px;">Model: ${d.analyzer_model || '-'}</div>
                    </div>
                    <div class="detail-section">
                        <h4>Brand Mentions (${d.mentions ? d.mentions.length : 0})</h4>
                        ${mentionsHtml}
                    </div>
                    <div class="detail-section">
                        <h4>Citations (${d.citations ? d.citations.length : 0})</h4>
                        ${citationsHtml}
                    </div>
                    ${featuresHtml ? '<div class="detail-section"><h4>Product Features</h4>'+featuresHtml+'</div>' : ''}
                </div>
                ${d.query_text ? '<div class="detail-section" style="margin-top:10px;"><h4>Query</h4><div>'+escapeHtml(d.query_text)+'</div></div>' : ''}
                ${d.raw_text ? '<details style="margin-top:10px;"><summary class="text-muted" style="cursor:pointer;">Raw Response Text</summary><pre style="font-size:11px;max-height:300px;overflow:auto;background:#f1f5f9;padding:10px;border-radius:4px;margin-top:5px;">'+escapeHtml(d.raw_text)+'</pre></details>' : ''}
                ${d.raw_analysis_json ? '<details style="margin-top:10px;"><summary class="text-muted" style="cursor:pointer;">Raw LLM JSON</summary><pre style="font-size:11px;max-height:300px;overflow:auto;background:#f1f5f9;padding:10px;border-radius:4px;margin-top:5px;">'+JSON.stringify(d.raw_analysis_json,null,2)+'</pre></details>' : ''}
            `;
        }

        async function rerunAnalysis(rid, btn) {
            if (!confirm('Re-analyze response #' + rid + '?')) return;
            btn.disabled = true;
            btn.textContent = '...';
            try {
                const r = await fetch('./api/analyzer/rerun/' + rid, {method: 'POST'});
                const d = await r.json();
                if (d.error) { alert('Error: ' + d.error); }
                else { alert('Queued: ' + (d.task_id || 'ok')); }
            } catch(e) { alert('Failed: ' + e); }
            btn.disabled = false;
            btn.textContent = 'Rerun';
        }

        async function loadDaily() {
            const p = new URLSearchParams();
            const brand = document.getElementById('d-brand').value;
            const llm = document.getElementById('d-llm').value;
            const days = document.getElementById('d-days').value;
            if (brand) p.set('brand_id', brand);
            if (llm) p.set('llm', llm);
            p.set('days', days);

            const r = await fetch('./api/analyzer/daily?' + p.toString());
            const d = await r.json();
            if (!d.length) {
                document.getElementById('daily-table').innerHTML = '<div class="empty-state">No daily data</div>';
                return;
            }
            let html = `<table><thead><tr>
                <th>Date</th><th>Brand</th><th>LLM</th><th>GEO Score</th>
                <th>Queries</th><th>Mention Rate</th><th>1st Place</th>
                <th>Sentiment</th><th>SOV</th><th>Industry Rank</th>
            </tr></thead><tbody>`;
            d.forEach(r => {
                html += `<tr>
                    <td>${r.date ? r.date.substring(0,10) : '-'}</td>
                    <td>${r.brand_name || '-'}</td>
                    <td>${r.target_llm || '<em>all</em>'}</td>
                    <td><span class="geo-score ${scoreClass(r.avg_geo_score)}">${r.avg_geo_score.toFixed(1)}</span></td>
                    <td>${r.total_queries}</td>
                    <td>${(r.mention_rate*100).toFixed(1)}%</td>
                    <td>${(r.first_place_rate*100).toFixed(1)}%</td>
                    <td>${r.avg_sentiment_score.toFixed(2)}</td>
                    <td>${r.industry_sov_pct != null ? r.industry_sov_pct.toFixed(1)+'%' : '-'}</td>
                    <td>${r.industry_rank || '-'}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            document.getElementById('daily-table').innerHTML = html;
        }

        async function triggerAnalysis(action) {
            const date = document.getElementById('t-date').value;
            if (!date) { alert('Please select a date'); return; }
            const brand = document.getElementById('t-brand').value;
            const div = document.getElementById('trigger-result');
            div.innerHTML = '<div class="text-muted">Triggering...</div>';

            const r = await fetch('./api/analyzer/trigger', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action, date, brand_id: brand ? parseInt(brand) : null})
            });
            const d = await r.json();
            if (d.success) {
                div.innerHTML = '<div style="color:#059669;font-weight:600;">Triggered: ' + (d.task_id || d.message || 'OK') + '</div>';
                setTimeout(loadAnalyzerStats, 3000);
            } else {
                div.innerHTML = '<div style="color:#dc2626;">Error: ' + (d.error || 'Unknown') + '</div>';
            }
        }

        // Pre-load analyzer filter options
        loadBrands();
        loadLLMs();
        // Set default trigger date
        const tDateEl = document.getElementById('t-date');
        if (tDateEl) tDateEl.value = new Date().toISOString().split('T')[0];
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/admin')
@app.route('/admin/<path:admin_path>')
def admin_page(admin_path=None):
    """Serve the Admin console shell and its sub-routes."""
    return render_template('admin.html')


@app.route('/api/admin/session')
def admin_session_api():
    admin = _current_admin()
    if not admin:
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "admin": admin})


@app.route('/api/admin/login', methods=['POST'])
def admin_login_api():
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        return jsonify({"success": False, "error": "email_and_password_required"}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, email, password_hash, role, status
                FROM admin_users
                WHERE LOWER(email) = LOWER(%s)
                """,
                (email,),
            )
            admin = cur.fetchone()
            if not admin:
                _record_admin_login_attempt(cur, email, False, "UNKNOWN_EMAIL")
                conn.commit()
                return jsonify({"success": False, "error": "invalid_credentials"}), 401

            if admin.get("status") != "active":
                _record_admin_login_attempt(cur, email, False, "USER_SUSPENDED")
                conn.commit()
                return jsonify({"success": False, "error": "admin_suspended"}), 403

            if not _verify_admin_password(password, admin.get("password_hash")):
                _record_admin_login_attempt(cur, email, False, "WRONG_PASSWORD")
                conn.commit()
                return jsonify({"success": False, "error": "invalid_credentials"}), 401

            cur.execute(
                "UPDATE admin_users SET last_login_at = NOW(), updated_at = NOW() WHERE id = %s",
                (admin["id"],),
            )
            _record_admin_login_attempt(cur, email, True, None)
            conn.commit()

            session.clear()
            session.permanent = True
            session["admin_user_id"] = admin["id"]
            return jsonify({
                "success": True,
                "admin": {
                    "id": admin["id"],
                    "email": admin["email"],
                    "role": admin["role"],
                    "status": admin["status"],
                },
            })
    finally:
        conn.close()


@app.route('/api/admin/logout', methods=['POST'])
def admin_logout_api():
    session.clear()
    return jsonify({"success": True})


@app.route('/api/admin/brands')
def admin_brand_options_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            brands = _fetch_topic_plan_brands(cur)
        return jsonify({"success": True, "brands": brands})
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/config')
def admin_topic_plan_config_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            brands = _fetch_topic_plan_brands(cur)
            industries = [
                {"id": value, "name": value}
                for value in sorted({b.get("industry_id") or "Uncategorized" for b in brands})
            ]
            categories = _fetch_topic_plan_categories(cur)
            default_industry = request.args.get("industry_id") or (
                industries[0]["id"] if industries else ""
            )
            default_category = request.args.get("category_id") or ""
            scoped = _topic_plan_scope_brands(brands, industry_id=default_industry)
            selected_ids = {
                int(b["id"])
                for b in sorted(scoped, key=lambda item: item.get("topic_count", 0), reverse=True)[:4]
            }
            for brand in brands:
                brand["selected"] = int(brand["id"]) in selected_ids

            pending = _topic_plan_pending_summary(cur, [int(x) for x in selected_ids])
            try:
                load_doubao_config()
                llm_configured = True
            except TopicPlanLLMError:
                llm_configured = False

        return jsonify(
            {
                "success": True,
                "industries": industries,
                "categories": categories,
                "brands": brands,
                "defaults": {
                    "industryId": default_industry,
                    "categoryId": default_category,
                    "maxPerBrand": 40,
                    "maxTopics": 180,
                    "gapPriority": "p12",
                    "overflowPolicy": "review",
                },
                "summary": {
                    "pending_candidates": pending["pending"],
                    "low_confidence": pending["low_confidence"],
                    "llm_configured": llm_configured,
                },
            }
        )
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/coverage')
def admin_topic_plan_coverage_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    try:
        brand_ids = _parse_int_list(request.args.get("brand_ids"))
    except ValueError:
        return jsonify({"success": False, "error": "invalid_brand_ids"}), 400

    industry_id = (request.args.get("industry_id") or "").strip() or None
    category_id = (request.args.get("category_id") or "").strip() or None
    max_per_brand = _clamp_int(request.args.get("max_per_brand"), 40, 1, 200)

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            all_brands = _fetch_topic_plan_brands(cur)
            brands = _topic_plan_scope_brands(
                all_brands,
                industry_id=industry_id,
                brand_ids=brand_ids,
            )
            coverage = _build_topic_plan_coverage(
                cur,
                brands,
                category_id=category_id,
                max_per_brand=max_per_brand,
            )
        return jsonify(
            {
                "success": True,
                "rows": coverage["rows"],
                "gaps": coverage["gaps"],
                "summary": coverage["summary"],
            }
        )
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/candidates')
def admin_topic_plan_candidates_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    status = (request.args.get("status") or "pending").strip().lower()
    if status not in {"pending", "approved", "rejected", "all"}:
        return jsonify({"success": False, "error": "invalid_status"}), 400
    try:
        brand_ids = _parse_int_list(request.args.get("brand_ids"))
        limit = _clamp_int(request.args.get("limit"), 100, 1, 500)
    except ValueError:
        return jsonify({"success": False, "error": "invalid_brand_ids"}), 400
    query = (request.args.get("q") or "").strip() or None

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows = _fetch_topic_plan_candidates(
                cur,
                status=status,
                brand_ids=brand_ids,
                query=query,
                limit=limit,
            )
            pending = _topic_plan_pending_summary(cur, brand_ids)
        return jsonify(
            {
                "success": True,
                "rows": rows,
                "summary": {
                    "pending_candidates": pending["pending"],
                    "low_confidence": pending["low_confidence"],
                },
            }
        )
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/topics')
def admin_topic_plan_topics_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    try:
        brand_ids = _parse_int_list(request.args.get("brand_ids"))
        limit = _clamp_int(request.args.get("limit"), 200, 1, 500)
    except ValueError:
        return jsonify({"success": False, "error": "invalid_brand_ids"}), 400

    industry_id = (request.args.get("industry_id") or "").strip() or None
    category_id = (request.args.get("category_id") or "").strip() or None
    dimension = (request.args.get("dimension") or "").strip().lower() or None
    if dimension and dimension not in {"brand", "product", "category", "scenario", "question"}:
        return jsonify({"success": False, "error": "invalid_dimension"}), 400
    status = (request.args.get("status") or "all").strip().lower()
    if status not in {"active", "draft", "archived", "all"}:
        return jsonify({"success": False, "error": "invalid_status"}), 400
    query = (request.args.get("q") or "").strip() or None

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, summary = _fetch_topic_plan_topics(
                cur,
                industry_id=industry_id,
                category_id=category_id,
                brand_ids=brand_ids,
                dimension=dimension,
                status=status,
                query=query,
                limit=limit,
            )
        return jsonify({"success": True, "rows": rows, "summary": summary})
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/topics/bulk-delete', methods=['POST'])
def admin_topic_plan_topics_bulk_delete_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    try:
        topic_ids = _parse_topic_plan_topic_ids(payload.get("topic_ids"))
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    if not topic_ids:
        return jsonify({"success": False, "error": "topic_ids_required"}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _delete_topic_plan_topics(cur, topic_ids)
            if result["deleted"]:
                _insert_admin_audit_log(
                    cur,
                    operator_id=admin["id"],
                    action="delete_topic_plan_topics",
                    target_type="topic",
                    target_id="bulk",
                    diff={
                        "deleted": result["deleted"],
                        "blocked": result["blocked"],
                        "missing": result["missing"],
                    },
                    reason="topic_plan_delete",
                )
        conn.commit()
        success = bool(result["deleted"]) or not result["blocked"]
        status_code = 200 if success else 409
        return jsonify(
            {
                "success": success,
                "deleted": result["deleted"],
                "blocked": result["blocked"],
                "missing": result["missing"],
                "summary": {
                    "deleted_count": len(result["deleted"]),
                    "blocked_count": len(result["blocked"]),
                    "missing_count": len(result["missing"]),
                },
            }
        ), status_code
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/topics/<topic_id>', methods=['DELETE'])
def admin_topic_plan_topic_delete_api(topic_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    try:
        parsed_id = _parse_topic_plan_topic_id(topic_id)
    except ValueError:
        return jsonify({"success": False, "error": "invalid_topic_id"}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            result = _delete_topic_plan_topics(cur, [parsed_id])
            if result["missing"]:
                conn.rollback()
                return jsonify({"success": False, "error": "topic_not_found"}), 404
            if result["blocked"]:
                conn.rollback()
                return jsonify(
                    {
                        "success": False,
                        "error": "topic_has_downstream_dependencies",
                        "blocked": result["blocked"],
                    }
                ), 409
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="delete_topic_plan_topic",
                target_type="topic",
                target_id=str(parsed_id),
                diff={"deleted": result["deleted"]},
                reason="topic_plan_delete",
            )
        conn.commit()
        return jsonify({"success": True, "deleted": result["deleted"]})
    finally:
        conn.close()


def _topic_plan_run_row(row):
    item = dict(row)
    request_config = _prompt_matrix_json_value(item.get("request_config"), {}) or {}
    return {
        "id": item.get("id"),
        "status": item.get("status"),
        "admin_id": item.get("admin_id"),
        "industry_id": item.get("industry_id"),
        "category_id": item.get("category_id"),
        "brand_ids": _prompt_matrix_json_value(item.get("brand_ids"), []) or [],
        "request_config": request_config,
        "estimated_topics": int(request_config.get("max_topics") or 0),
        "candidates_generated": int(item.get("candidates_generated") or 0),
        "llm_model": item.get("llm_model"),
        "llm_usage": _prompt_matrix_json_value(item.get("llm_usage_json"), {}) or {},
        "llm_error": item.get("llm_error"),
        "started_at": _isoformat(item.get("started_at")),
        "completed_at": _isoformat(item.get("completed_at")),
        "created_at": _isoformat(item.get("created_at")),
        "updated_at": _isoformat(item.get("updated_at")),
        "elapsed_seconds": float(item.get("elapsed_seconds") or 0),
    }


def _topic_plan_brand_batches(brands, gaps, *, max_topics, max_per_brand):
    batch_size = _clamp_int(os.getenv("TOPIC_PLAN_LLM_BRANDS_PER_REQUEST"), 1, 1, 5)
    for index in range(0, len(brands), batch_size):
        batch_brands = brands[index : index + batch_size]
        batch_brand_ids = {int(brand["id"]) for brand in batch_brands}
        batch_gaps = [
            gap for gap in gaps
            if str(gap.get("brand_id") or "").isdigit() and int(gap.get("brand_id")) in batch_brand_ids
        ]
        batch_cap = min(max_topics, max_per_brand * max(len(batch_brands), 1))
        yield batch_brands, batch_gaps, batch_cap


def _insert_topic_plan_candidate_batch(
    cur,
    *,
    run_id,
    candidates,
    brands,
    existing_titles,
    remaining,
    skipped,
):
    if remaining <= 0:
        return []
    accepted, batch_skipped = dedupe_topic_candidates(candidates, existing_titles, remaining)
    skipped.extend(batch_skipped)
    brand_by_norm = {
        normalize_topic_title(brand["name"]): brand
        for brand in brands
        if normalize_topic_title(brand["name"])
    }
    inserted = []
    for item in accepted:
        if not is_natural_consumer_topic(item.title):
            skipped.append({"title": item.title, "reason": "topic_not_natural"})
            continue
        brand = brand_by_norm.get(normalize_topic_title(item.brand))
        if brand is None:
            item_norm = normalize_topic_title(item.brand)
            matches = [
                candidate
                for candidate in brands
                if item_norm
                and (
                    item_norm in normalize_topic_title(candidate["name"])
                    or normalize_topic_title(candidate["name"]) in item_norm
                )
            ]
            if len(matches) == 1:
                brand = matches[0]
            elif len(brands) == 1:
                brand = brands[0]
        if brand is None:
            skipped.append({"title": item.title, "reason": "brand_not_selected"})
            continue
        candidate_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO topic_candidates
                (id, run_id, brand_id, brand_name, title, dimension,
                 reason, confidence, coverage_gap, normalized_title,
                 status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'pending', NOW(), NOW())
            RETURNING *
            """,
            (
                candidate_id,
                run_id,
                int(brand["id"]),
                brand["name"],
                item.title,
                item.dimension,
                item.reason,
                item.confidence,
                item.coverage_gap,
                normalize_topic_title(item.title),
            ),
        )
        inserted.append(_topic_plan_candidate_row(cur.fetchone()))
    return inserted


def _topic_plan_run_failed_status(error):
    return 503 if error.code in {"llm_config_missing", "llm_call_failed"} else 502


def _execute_topic_plan_generation(
    *,
    run_id,
    admin_id,
    industry_id,
    category_id,
    brands,
    llm_gaps,
    max_per_brand,
    max_topics,
    existing_titles,
    request_config,
    coverage_summary,
    conn=None,
):
    from psycopg2.extras import RealDictCursor

    own_conn = conn is None
    conn = conn or get_db()
    inserted = []
    skipped = []
    usage = {}
    batches = 0
    llm_model = os.getenv("ARK_MODEL") or os.getenv("DOUBAO_MODEL") or os.getenv("LLM_MODEL")
    try:
        doubao_config = load_doubao_config()
        client = DoubaoTopicPlanClient(doubao_config)
        llm_model = doubao_config.model
        for batch_brands, batch_gaps, batch_cap in _topic_plan_brand_batches(
            brands,
            llm_gaps,
            max_topics=max_topics,
            max_per_brand=max_per_brand,
        ):
            remaining = max_topics - len(inserted)
            if remaining <= 0:
                break
            batch_max = min(remaining, batch_cap)
            llm_topics, llm_meta = client.generate_topics(
                industry=industry_id or "All industries",
                category=category_id or "All categories",
                brands=[
                    {
                        "id": brand["id"],
                        "name": brand["name"],
                        "industry": brand.get("industry_name") or brand.get("industry_id"),
                        "topic_count": brand.get("topic_count", 0),
                    }
                    for brand in batch_brands
                ],
                coverage_gaps=batch_gaps,
                max_topics=batch_max,
                existing_topics=existing_titles,
            )
            batches += 1
            llm_model = (llm_meta or {}).get("model") or llm_model
            usage = merge_usage(usage, (llm_meta or {}).get("usage") or {})
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                batch_inserted = _insert_topic_plan_candidate_batch(
                    cur,
                    run_id=run_id,
                    candidates=llm_topics,
                    brands=batch_brands,
                    existing_titles=existing_titles,
                    remaining=remaining,
                    skipped=skipped,
                )
                inserted.extend(batch_inserted)
                existing_titles.extend([row["title"] for row in batch_inserted if row.get("title")])
                cur.execute(
                    """
                    UPDATE topic_plan_runs
                    SET llm_model = %s,
                        llm_usage_json = %s::jsonb,
                        candidates_generated = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        llm_model,
                        _topic_plan_json(usage),
                        len(inserted),
                        run_id,
                    ),
                )
            conn.commit()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE topic_plan_runs
                SET status = 'completed',
                    llm_model = %s,
                    llm_usage_json = %s::jsonb,
                    candidates_generated = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    llm_model,
                    _topic_plan_json(usage),
                    len(inserted),
                    run_id,
                ),
            )
            _insert_admin_audit_log(
                cur,
                operator_id=admin_id,
                action="generate_topic_plan",
                target_type="topic_plan_run",
                target_id=run_id,
                diff={
                    "request_config": request_config,
                    "candidates_generated": len(inserted),
                    "batches": batches,
                    "skipped": skipped,
                },
                reason="topic_plan_generate",
            )
        conn.commit()
        return {
            "inserted": inserted,
            "skipped": skipped,
            "usage": usage,
            "model": llm_model,
            "batches": batches,
            "coverage": coverage_summary,
        }
    except Exception as error:
        topic_error = error if isinstance(error, TopicPlanLLMError) else TopicPlanLLMError(
            "topic_plan_generation_failed",
            str(error)[:500] or "Topic Plan generation failed",
        )
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE topic_plan_runs
                    SET status = 'failed',
                        llm_model = %s,
                        llm_error = %s,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        llm_model,
                        topic_error.code,
                        run_id,
                    ),
                )
                _insert_admin_audit_log(
                    cur,
                    operator_id=admin_id,
                    action="generate_topic_plan_failed",
                    target_type="topic_plan_run",
                    target_id=run_id,
                    diff={"request_config": request_config, "error": topic_error.code},
                    reason="topic_plan_generate",
                )
            conn.commit()
        except Exception:
            conn.rollback()
        raise topic_error from error
    finally:
        if own_conn:
            conn.close()


def _start_topic_plan_generation_thread(**kwargs):
    def worker():
        try:
            _execute_topic_plan_generation(**kwargs)
        except Exception as error:
            app.logger.exception("Topic Plan generation worker failed: %s", error)

    thread = threading.Thread(target=worker, name=f"topic-plan-{kwargs.get('run_id')}", daemon=True)
    thread.start()
    return thread


@app.route('/api/admin/topic-plan/runs/<run_id>')
def admin_topic_plan_run_api(run_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if not _table_exists(cur, "topic_plan_runs"):
                return jsonify({"success": False, "error": "run_not_found"}), 404
            cur.execute(
                """
                SELECT *,
                       EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - COALESCE(started_at, created_at, NOW()))) AS elapsed_seconds
                FROM topic_plan_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"success": False, "error": "run_not_found"}), 404
            return jsonify({"success": True, "run": _topic_plan_run_row(row)})
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/generate', methods=['POST'])
def admin_topic_plan_generate_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    try:
        brand_ids = _parse_int_list(payload.get("brand_ids"))
    except ValueError:
        return jsonify({"success": False, "error": "invalid_brand_ids"}), 400
    if not brand_ids:
        return jsonify({"success": False, "error": "brand_ids_required"}), 400

    industry_id = (payload.get("industry_id") or "").strip() or None
    category_id = (payload.get("category_id") or "").strip() or None
    max_per_brand = _clamp_int(payload.get("max_per_brand"), 40, 1, 200)
    max_topics = _clamp_int(payload.get("max_topics"), 180, 1, 300)
    gap_priority = (payload.get("gap_priority") or "p12").strip()
    overflow_policy = (payload.get("overflow_policy") or "review").strip()
    request_config = {
        "industry_id": industry_id,
        "category_id": category_id,
        "brand_ids": brand_ids,
        "max_per_brand": max_per_brand,
        "max_topics": max_topics,
        "gap_priority": gap_priority,
        "overflow_policy": overflow_policy,
    }

    run_id = str(uuid.uuid4())
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            all_brands = _fetch_topic_plan_brands(cur)
            brands = _topic_plan_scope_brands(
                all_brands,
                industry_id=industry_id,
                brand_ids=brand_ids,
            )
            if not brands:
                return jsonify({"success": False, "error": "selected_brands_not_found"}), 404

            coverage = _build_topic_plan_coverage(
                cur,
                brands,
                category_id=category_id,
                max_per_brand=max_per_brand,
            )
            allowed_priorities = {
                "p1": {"P1"},
                "p12": {"P1", "P2"},
            }.get(gap_priority)
            llm_gaps = [
                gap for gap in coverage["gaps"]
                if allowed_priorities is None or gap.get("priority") in allowed_priorities
            ]
            if not llm_gaps:
                llm_gaps = coverage["gaps"]
            existing_titles = [row.get("text") or "" for row in coverage["existing_topics"]]
            if _table_exists(cur, "topic_candidates"):
                cur.execute(
                    """
                    SELECT title
                    FROM topic_candidates
                    WHERE brand_id = ANY(%s) AND status = 'pending'
                    """,
                    (brand_ids,),
                )
                existing_titles.extend([row["title"] for row in cur.fetchall()])

            cur.execute(
                """
                INSERT INTO topic_plan_runs
                    (id, admin_id, industry_id, category_id, brand_ids, status,
                     request_config, coverage_snapshot, started_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, 'running',
                        %s::jsonb, %s::jsonb, NOW(), NOW(), NOW())
                """,
                (
                    run_id,
                    admin["id"],
                    industry_id,
                    category_id,
                    _topic_plan_json(brand_ids),
                    _topic_plan_json(request_config),
                    _topic_plan_json(
                        {
                            "rows": coverage["rows"],
                            "gaps": coverage["gaps"],
                            "summary": coverage["summary"],
                        }
                    ),
                ),
            )
        conn.commit()

        generation_kwargs = {
            "run_id": run_id,
            "admin_id": admin["id"],
            "industry_id": industry_id,
            "category_id": category_id,
            "brands": brands,
            "llm_gaps": llm_gaps,
            "max_per_brand": max_per_brand,
            "max_topics": max_topics,
            "existing_titles": existing_titles,
            "request_config": request_config,
            "coverage_summary": coverage["summary"],
        }
        if app.config.get("TESTING") or os.getenv("TOPIC_PLAN_SYNC_GENERATE") == "1":
            try:
                result = _execute_topic_plan_generation(**generation_kwargs, conn=conn)
            except TopicPlanLLMError as error:
                code = _topic_plan_run_failed_status(error)
                return jsonify(
                    {
                        "success": False,
                        "run_id": run_id,
                        "error": error.code,
                        "message": error.message,
                    }
                ), code
            inserted = result["inserted"]
            return jsonify(
                {
                    "success": True,
                    "run_id": run_id,
                    "status": "completed",
                    "candidates": inserted,
                    "summary": {
                        "generated": len(inserted),
                        "skipped": result["skipped"],
                        "coverage": coverage["summary"],
                    },
                }
            )
        _start_topic_plan_generation_thread(**generation_kwargs)
        return jsonify(
            {
                "success": True,
                "run_id": run_id,
                "status": "running",
                "summary": {
                    "generated": 0,
                    "estimated": max_topics,
                    "coverage": coverage["summary"],
                },
            }
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/candidates/<candidate_id>/review', methods=['POST'])
def admin_topic_plan_candidate_review_api(candidate_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                updated = _review_topic_plan_candidate(
                    cur,
                    candidate_id,
                    requested_status,
                    admin["id"],
                    reason=reason,
                )
            except TopicPlanLLMError as error:
                return _topic_plan_error_response(error, 400)
            if not updated:
                return jsonify({"success": False, "error": "candidate_not_found"}), 404
        conn.commit()
        return jsonify({"success": True, "candidate": updated})
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/api/admin/topic-plan/candidates/bulk-review', methods=['POST'])
def admin_topic_plan_candidates_bulk_review_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    candidate_ids = payload.get("candidate_ids") or []
    if not isinstance(candidate_ids, list) or not candidate_ids:
        return jsonify({"success": False, "error": "candidate_ids_required"}), 400
    candidate_ids = [str(item).strip() for item in candidate_ids if str(item).strip()]
    if not candidate_ids:
        return jsonify({"success": False, "error": "candidate_ids_required"}), 400
    if len(candidate_ids) > 200:
        return jsonify({"success": False, "error": "too_many_candidates"}), 400

    conn = get_db()
    updated = []
    missing = []
    failed = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for candidate_id in candidate_ids:
                try:
                    row = _review_topic_plan_candidate(
                        cur,
                        candidate_id,
                        requested_status,
                        admin["id"],
                        reason=reason,
                    )
                    if row:
                        updated.append(row)
                    else:
                        missing.append(candidate_id)
                except TopicPlanLLMError as error:
                    failed.append(
                        {
                            "id": candidate_id,
                            "error": error.code,
                            "message": error.message,
                        }
                    )
        conn.commit()
        return jsonify(
            {
                "success": len(failed) == 0,
                "rows": updated,
                "summary": {
                    "updated_count": len(updated),
                    "missing_count": len(missing),
                    "failed_count": len(failed),
                },
                "missing": missing,
                "failed": failed,
            }
        ), 200 if not failed else 409
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/config')
def admin_prompt_matrix_config_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            brands = _prompt_matrix_brand_rows(cur)
            industries = [
                {"id": value, "name": value}
                for value in sorted({brand.get("industry_id") or "Uncategorized" for brand in brands})
            ]
            stats = _prompt_matrix_stats(cur)
            pending = 0
            duplicates = 0
            if _table_exists(cur, "prompt_candidates"):
                cur.execute("SELECT COUNT(*) AS cnt FROM prompt_candidates WHERE status = 'pending'")
                pending = int(cur.fetchone()["cnt"] or 0)
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM prompt_candidates
                    WHERE status = 'pending' AND duplicate_of IS NOT NULL
                    """
                )
                duplicates = int(cur.fetchone()["cnt"] or 0)
            try:
                load_doubao_config()
                llm_configured = True
            except TopicPlanLLMError:
                llm_configured = False
        return jsonify(
            {
                "success": True,
                "brands": brands,
                "industries": industries,
                "defaults": {
                    "intentCount": 4,
                    "languageCount": 2,
                    "topicPriority": "gap_first",
                    "templateStrategy": "latest",
                    "promptStyle": "natural",
                    "audienceMode": "general",
                    "maxPerTopic": 4,
                    "maxPrompts": 8000,
                    "overflowPolicy": "split",
                },
                "summary": {
                    "pending_candidates": pending,
                    "duplicate_candidates": duplicates,
                    "llm_configured": llm_configured,
                },
                "stats": stats,
                "qualityGates": _prompt_matrix_quality_gates(stats, pending, duplicates),
            }
        )
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/topics')
def admin_prompt_matrix_topics_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    try:
        filters = _prompt_matrix_filter_payload(request.args)
        page = _clamp_int(request.args.get("page"), 1, 1, 100000)
        per_page = _clamp_int(request.args.get("per_page"), 20, 1, 100)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total, summary = _fetch_prompt_matrix_topics(
                cur,
                filters=filters,
                page=page,
                per_page=per_page,
            )
        return jsonify(
            {
                "success": True,
                "rows": rows,
                "summary": summary,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": max(1, (total + per_page - 1) // per_page),
                },
            }
        )
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/gaps')
def admin_prompt_matrix_gaps_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    try:
        filters = _prompt_matrix_filter_payload(request.args)
        topic_ids = _prompt_matrix_parse_topic_ids(request.args.get("topic_ids"))
        config = {
            **prompt_generation_config(
                {
                    "intent_count": request.args.get("intent_count"),
                    "language_count": request.args.get("language_count"),
                    "max_per_topic": request.args.get("max_per_topic"),
                    "max_prompts": request.args.get("max_prompts") or 8000,
                    "template_strategy": request.args.get("template_strategy") or "latest",
                    "prompt_style": request.args.get("prompt_style") or "natural",
                    "audience_mode": request.args.get("audience_mode") or "general",
                    "overflow_policy": request.args.get("overflow_policy") or "split",
                }
            )
        }
        limit = _clamp_int(request.args.get("limit"), 200, 1, 500)
    except (ValueError, PromptMatrixError) as error:
        return jsonify({"success": False, "error": getattr(error, "code", str(error))}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            gaps = _prompt_matrix_gaps_for_topics(
                cur,
                topic_ids=topic_ids,
                filters=filters,
                config=config,
                limit=limit,
            )
        return jsonify(
            {
                "success": True,
                "rows": gaps,
                "summary": {
                    "gap_count": len(gaps),
                    "estimated_prompts": sum(int(item.get("estimate") or 0) for item in gaps),
                },
            }
        )
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/prompts')
def admin_prompt_matrix_prompts_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    intent = (request.args.get("intent") or "").strip().lower() or None
    if intent and intent not in ALLOWED_INTENTS:
        return jsonify({"success": False, "error": "invalid_intent"}), 400
    language = (request.args.get("language") or request.args.get("lang") or "").strip() or None
    if language and language not in ALLOWED_LANGUAGES:
        return jsonify({"success": False, "error": "invalid_language"}), 400
    query = (request.args.get("q") or "").strip() or None
    page = _clamp_int(request.args.get("page"), 1, 1, 100000)
    per_page = _clamp_int(request.args.get("per_page"), 50, 1, 100)

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total = _fetch_prompt_matrix_prompts(
                cur,
                intent=intent,
                language=language,
                query=query,
                page=page,
                per_page=per_page,
            )
            stats = _prompt_matrix_stats(cur)
        return jsonify(
            {
                "success": True,
                "rows": rows,
                "stats": stats,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": max(1, (total + per_page - 1) // per_page),
                },
            }
        )
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/candidates')
def admin_prompt_matrix_candidates_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    status = (request.args.get("status") or "pending").strip().lower()
    if status not in {"pending", "approved", "rejected", "all"}:
        return jsonify({"success": False, "error": "invalid_status"}), 400
    query = (request.args.get("q") or "").strip() or None
    page = _clamp_int(request.args.get("page"), 1, 1, 100000)
    per_page = _clamp_int(request.args.get("per_page") or request.args.get("limit"), 20, 1, 100)
    offset = (page - 1) * per_page

    conn = None
    try:
        conn = get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total = _fetch_prompt_matrix_candidates(
                cur,
                status=status,
                query=query,
                limit=per_page,
                offset=offset,
                include_total=True,
            )
            status_counts = _prompt_matrix_candidate_status_counts(cur, query=query)
        return jsonify(
            {
                "success": True,
                "rows": rows,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": max(1, (total + per_page - 1) // per_page),
                },
                "summary": {
                    "pending_candidates": status_counts.get("pending", 0),
                    "approved_candidates": status_counts.get("approved", 0),
                    "rejected_candidates": status_counts.get("rejected", 0),
                    "all_candidates": status_counts.get("all", 0),
                    "duplicate_candidates": sum(1 for row in rows if row.get("duplicate_of")),
                    "status_counts": status_counts,
                },
            }
        )
    except Exception as exc:
        app.logger.exception("Prompt Matrix candidates load failed: %s", exc)
        return jsonify(
            {
                "success": False,
                "error": "candidate_load_failed",
                "message": "候选 Prompt 加载失败，请检查数据库连接后重试",
            }
        ), 503
    finally:
        if conn is not None:
            conn.close()


def _prompt_matrix_run_row(row):
    item = dict(row)
    return {
        "id": item.get("id"),
        "status": item.get("status"),
        "admin_id": item.get("admin_id"),
        "request_config": _prompt_matrix_json_value(item.get("request_config"), {}) or {},
        "selected_topic_ids": _prompt_matrix_json_value(item.get("selected_topic_ids"), []) or [],
        "estimated_prompts": int(item.get("estimated_prompts") or 0),
        "candidates_generated": int(item.get("candidates_generated") or 0),
        "llm_model": item.get("llm_model"),
        "llm_usage": _prompt_matrix_json_value(item.get("llm_usage_json"), {}) or {},
        "llm_error": item.get("llm_error"),
        "started_at": _isoformat(item.get("started_at")),
        "completed_at": _isoformat(item.get("completed_at")),
        "created_at": _isoformat(item.get("created_at")),
        "updated_at": _isoformat(item.get("updated_at")),
        "elapsed_seconds": float(item.get("elapsed_seconds") or 0),
    }


def _prompt_matrix_candidate_batches(client, *, topics, config, known_brands, existing_prompts):
    batch_method = getattr(client, "generate_prompt_batches", None)
    if callable(batch_method):
        yield from batch_method(
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_prompts,
        )
        return
    prompts, meta = client.generate_prompts(
        topics=topics,
        config=config,
        known_brands=known_brands,
        existing_prompts=existing_prompts,
    )
    yield prompts, meta


def _insert_prompt_matrix_candidate_batch(
    cur,
    *,
    run_id,
    candidates,
    topic_by_id,
    config,
    known_brands,
    existing_prompts,
    remaining,
    skipped,
):
    if remaining <= 0:
        return []
    accepted, batch_skipped = dedupe_prompt_candidates(
        candidates,
        existing_prompts,
        max_count=remaining,
    )
    skipped.extend(batch_skipped)
    inserted = []
    for candidate in accepted:
        item = candidate.as_dict() if hasattr(candidate, "as_dict") else dict(candidate)
        try:
            topic_id = int(item.get("topic_id"))
        except (TypeError, ValueError):
            skipped.append({"text": item.get("text", ""), "reason": "invalid_topic_id"})
            continue
        topic = topic_by_id.get(topic_id)
        if topic is None:
            skipped.append({"text": item.get("text", ""), "reason": "topic_not_selected"})
            continue
        text = item.get("text") or ""
        language = item.get("language") or ""
        if not is_natural_user_prompt(text):
            skipped.append({"text": text, "reason": "prompt_not_natural"})
            continue
        if has_prompt_language_mismatch(text, language):
            skipped.append({"text": text, "reason": "prompt_language_mismatch"})
            continue
        if topic.get("dimension_key") == "category":
            leaked_terms = detect_brand_leaks(text, known_brands)
            if leaked_terms:
                skipped.append(
                    {
                        "text": text,
                        "reason": "category_brand_leak",
                        "leaks": leaked_terms[:5],
                    }
                )
                continue
        candidate_id = str(uuid.uuid4())
        raw_tags = item.get("tags") if isinstance(item.get("tags"), dict) else {}
        tags = {key: value for key, value in raw_tags.items() if key != "engines"}
        tags = {
            **tags,
            "source": "prompt_matrix",
            "routing": "deferred_to_query_pool",
        }
        cur.execute(
            """
            INSERT INTO prompt_candidates
                (id, run_id, topic_id, topic_text, brand_id, brand_name,
                 dimension, intent, language, template_strategy, template_version,
                 text, status, confidence, reason, duplicate_of, tags,
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, 'pending', %s, %s, %s, %s::jsonb,
                    NOW(), NOW())
            RETURNING *
            """,
            (
                candidate_id,
                run_id,
                topic_id,
                topic["title"],
                topic.get("brand_id"),
                topic.get("brand"),
                topic.get("dimension_key"),
                item.get("intent"),
                language,
                item.get("template_strategy") or config["template_strategy"],
                item.get("template_version") or "v1",
                text,
                item.get("confidence", 0.75),
                item.get("reason") or "",
                item.get("duplicate_of"),
                _prompt_matrix_json(tags),
            ),
        )
        inserted.append(_prompt_matrix_candidate_row(cur.fetchone()))
    return inserted


def _prompt_matrix_run_failed_status(error):
    return 503 if error.code in {"llm_config_missing", "llm_call_failed"} else 502


def _execute_prompt_matrix_generation(
    *,
    run_id,
    admin_id,
    topics,
    config,
    known_brands,
    existing_prompts,
    estimated,
    request_config,
    conn=None,
):
    from psycopg2.extras import RealDictCursor

    own_conn = conn is None
    conn = conn or get_db()
    topic_by_id = {int(topic["raw_id"]): topic for topic in topics}
    inserted = []
    skipped = []
    usage = {}
    batches = 0
    llm_model = os.getenv("ARK_MODEL") or os.getenv("DOUBAO_MODEL") or os.getenv("LLM_MODEL")
    try:
        client = PromptMatrixClient()
        llm_model = getattr(getattr(client, "config", None), "model", None) or llm_model
        for llm_candidates, llm_meta in _prompt_matrix_candidate_batches(
            client,
            topics=topics,
            config=config,
            known_brands=known_brands,
            existing_prompts=existing_prompts,
        ):
            batches += 1
            llm_model = (llm_meta or {}).get("model") or llm_model
            usage = merge_usage(usage, (llm_meta or {}).get("usage") or {})
            remaining = estimated - len(inserted)
            if remaining <= 0:
                break
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                batch_inserted = _insert_prompt_matrix_candidate_batch(
                    cur,
                    run_id=run_id,
                    candidates=llm_candidates,
                    topic_by_id=topic_by_id,
                    config=config,
                    known_brands=known_brands,
                    existing_prompts=existing_prompts,
                    remaining=remaining,
                    skipped=skipped,
                )
                inserted.extend(batch_inserted)
                existing_prompts.extend([row["text"] for row in batch_inserted if row.get("text")])
                cur.execute(
                    """
                    UPDATE prompt_generation_runs
                    SET llm_model = %s,
                        llm_usage_json = %s::jsonb,
                        candidates_generated = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        llm_model,
                        _prompt_matrix_json(usage),
                        len(inserted),
                        run_id,
                    ),
                )
            conn.commit()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE prompt_generation_runs
                SET status = 'completed',
                    llm_model = %s,
                    llm_usage_json = %s::jsonb,
                    llm_error = NULL,
                    candidates_generated = %s,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    llm_model,
                    _prompt_matrix_json(usage),
                    len(inserted),
                    run_id,
                ),
            )
            _insert_admin_audit_log(
                cur,
                operator_id=admin_id,
                action="generate_prompt_matrix",
                target_type="prompt_generation_run",
                target_id=run_id,
                diff={
                    "request_config": request_config,
                    "estimated_prompts": estimated,
                    "candidates_generated": len(inserted),
                    "batches": batches,
                    "skipped": skipped,
                },
                reason="prompt_matrix_generate",
            )
        conn.commit()
        return {"inserted": inserted, "skipped": skipped, "usage": usage, "model": llm_model, "batches": batches}
    except Exception as error:
        prompt_error = error if isinstance(error, PromptMatrixError) else PromptMatrixError(
            "prompt_matrix_generation_failed",
            str(error)[:500] or "Prompt Matrix generation failed",
        )
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE prompt_generation_runs
                    SET status = 'failed',
                        llm_model = %s,
                        llm_error = %s,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        llm_model,
                        prompt_error.code,
                        run_id,
                    ),
                )
                _insert_admin_audit_log(
                    cur,
                    operator_id=admin_id,
                    action="generate_prompt_matrix_failed",
                    target_type="prompt_generation_run",
                    target_id=run_id,
                    diff={"request_config": request_config, "error": prompt_error.code},
                    reason="prompt_matrix_generate",
                )
            conn.commit()
        except Exception:
            conn.rollback()
        raise prompt_error from error
    finally:
        if own_conn:
            conn.close()


def _start_prompt_matrix_generation_thread(**kwargs):
    def worker():
        try:
            _execute_prompt_matrix_generation(**kwargs)
        except Exception as error:
            app.logger.exception("Prompt Matrix generation worker failed: %s", error)

    thread = threading.Thread(target=worker, name=f"prompt-matrix-{kwargs.get('run_id')}", daemon=True)
    thread.start()
    return thread


@app.route('/api/admin/prompt-matrix/runs/<run_id>')
def admin_prompt_matrix_run_api(run_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if not _table_exists(cur, "prompt_generation_runs"):
                return jsonify({"success": False, "error": "run_not_found"}), 404
            cur.execute(
                """
                SELECT *,
                       EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - COALESCE(started_at, created_at, NOW()))) AS elapsed_seconds
                FROM prompt_generation_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"success": False, "error": "run_not_found"}), 404
            return jsonify({"success": True, "run": _prompt_matrix_run_row(row)})
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/generate', methods=['POST'])
def admin_prompt_matrix_generate_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    config = prompt_generation_config(
        {
            "intent_count": payload.get("intent_count") or payload.get("intentCount"),
            "language_count": payload.get("language_count") or payload.get("languageCount"),
            "topic_priority": payload.get("topic_priority") or payload.get("topicPriority"),
            "template_strategy": payload.get("template_strategy") or payload.get("templateStrategy"),
            "prompt_style": payload.get("prompt_style") or payload.get("promptStyle"),
            "audience_mode": payload.get("audience_mode") or payload.get("audienceMode"),
            "max_per_topic": payload.get("max_per_topic") or payload.get("maxPerTopic"),
            "max_prompts": payload.get("max_prompts") or payload.get("maxPrompts"),
            "overflow_policy": payload.get("overflow_policy") or payload.get("overflowPolicy"),
        }
    )

    run_id = str(uuid.uuid4())
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                topic_ids, selection_snapshot = _prompt_matrix_selection_from_payload(cur, payload)
            except PromptMatrixError as error:
                return _prompt_matrix_error_response(error, 400)
            if not topic_ids:
                return jsonify({"success": False, "error": "topic_ids_required"}), 400
            topics = _fetch_prompt_matrix_topics_by_ids(cur, topic_ids, config)
            if not topics:
                return jsonify({"success": False, "error": "selected_topics_not_found"}), 404
            topic_ids = [int(topic["raw_id"]) for topic in topics]
            estimated = estimate_generation_count(
                selected_topics=len(topics),
                intent_count=config["intent_count"],
                language_count=config["language_count"],
                max_per_topic=config["max_per_topic"],
                max_prompts=config["max_prompts"],
            )
            if estimated <= 0:
                return jsonify({"success": False, "error": "no_prompt_combinations"}), 400
            known_brands = _prompt_matrix_brand_rows(cur)
            existing_prompts = _fetch_prompt_matrix_prompt_texts(cur, topic_ids=topic_ids)
            if _table_exists(cur, "prompt_candidates"):
                cur.execute(
                    """
                    SELECT text
                    FROM prompt_candidates
                    WHERE topic_id = ANY(%s) AND status = 'pending'
                    """,
                    (topic_ids,),
                )
                existing_prompts.extend([row["text"] for row in cur.fetchall()])
            request_config = {
                **config,
                "selection": selection_snapshot,
            }
            cur.execute(
                """
                INSERT INTO prompt_generation_runs
                    (id, admin_id, status, request_config, selected_topic_ids,
                     estimated_prompts, started_at, created_at, updated_at)
                VALUES (%s, %s, 'running', %s::jsonb, %s::jsonb,
                        %s, NOW(), NOW(), NOW())
                """,
                (
                    run_id,
                    admin["id"],
                    _prompt_matrix_json(request_config),
                    _prompt_matrix_json(topic_ids),
                    estimated,
                ),
            )
        conn.commit()

        generation_kwargs = {
            "run_id": run_id,
            "admin_id": admin["id"],
            "topics": topics,
            "config": config,
            "known_brands": known_brands,
            "existing_prompts": existing_prompts,
            "estimated": estimated,
            "request_config": request_config,
        }
        if app.config.get("TESTING") or os.getenv("PROMPT_MATRIX_SYNC_GENERATE") == "1":
            try:
                result = _execute_prompt_matrix_generation(**generation_kwargs, conn=conn)
            except PromptMatrixError as error:
                code = _prompt_matrix_run_failed_status(error)
                return jsonify(
                    {
                        "success": False,
                        "run_id": run_id,
                        "error": error.code,
                        "message": error.message,
                    }
                ), code
            inserted = result["inserted"]
            return jsonify(
                {
                    "success": True,
                    "run_id": run_id,
                    "status": "completed",
                    "candidates": inserted,
                    "summary": {
                        "estimated": estimated,
                        "generated": len(inserted),
                        "skipped": result["skipped"],
                    },
                }
            )
        _start_prompt_matrix_generation_thread(**generation_kwargs)
        return jsonify(
            {
                "success": True,
                "run_id": run_id,
                "status": "running",
                "summary": {
                    "estimated": estimated,
                    "generated": 0,
                    "skipped": [],
                },
            }
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/candidates/<candidate_id>/review', methods=['POST'])
def admin_prompt_matrix_candidate_review_api(candidate_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                updated = _review_prompt_matrix_candidate(
                    cur,
                    candidate_id,
                    requested_status,
                    admin["id"],
                    reason=reason,
                )
            except PromptMatrixError as error:
                return _prompt_matrix_error_response(error, 400)
            if not updated:
                return jsonify({"success": False, "error": "candidate_not_found"}), 404
        conn.commit()
        return jsonify({"success": True, "candidate": updated})
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/api/admin/prompt-matrix/candidates/bulk-review', methods=['POST'])
def admin_prompt_matrix_candidates_bulk_review_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    requested_status = (payload.get("status") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    candidate_ids = payload.get("candidate_ids") or []
    if not isinstance(candidate_ids, list) or not candidate_ids:
        return jsonify({"success": False, "error": "candidate_ids_required"}), 400
    candidate_ids = [str(item).strip() for item in candidate_ids if str(item).strip()]
    if len(candidate_ids) > 200:
        return jsonify({"success": False, "error": "too_many_candidates"}), 400

    conn = get_db()
    updated = []
    failed = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for candidate_id in candidate_ids:
                try:
                    row = _review_prompt_matrix_candidate(
                        cur,
                        candidate_id,
                        requested_status,
                        admin["id"],
                        reason=reason,
                    )
                    if row:
                        updated.append(row)
                    else:
                        failed.append({"id": candidate_id, "error": "candidate_not_found"})
                except PromptMatrixError as error:
                    failed.append(
                        {
                            "id": candidate_id,
                            "error": error.code,
                            "message": error.message,
                        }
                    )
        conn.commit()
        return jsonify(
            {
                "success": len(failed) == 0,
                "rows": updated,
                "failed": failed,
                "summary": {
                    "updated_count": len(updated),
                    "failed_count": len(failed),
                },
            }
        ), 200 if not failed else 409
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/api/users')
def admin_users_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", request.args.get("limit", 20))), 1), 100)
        if request.args.get("offset") is not None:
            offset = max(int(request.args.get("offset", 0)), 0)
            page = (offset // per_page) + 1
        else:
            offset = (page - 1) * per_page
    except ValueError:
        return jsonify({"error": "invalid_pagination"}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total, notes = _fetch_user_rows(
                cur,
                limit=per_page,
                offset=offset,
                include_count=True,
            )
        return jsonify({
            "rows": rows,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "notes": notes,
        })
    finally:
        conn.close()


@app.route('/api/users/actions')
def admin_user_actions_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "invalid_pagination"}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total = _fetch_user_actions(cur, limit=limit, offset=offset)
        return jsonify({"rows": rows, "total": total, "limit": limit, "offset": offset})
    finally:
        conn.close()


@app.route('/api/users/login-audit')
def admin_user_login_audit_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            audit_table = None
            for candidate in ("user_login_audit", "user_login_attempts"):
                if _table_exists(cur, candidate):
                    audit_table = candidate
                    break

            if not audit_table:
                # Product auth currently records users.last_login_at / user_activity_stats
                # only. Keep a stable empty shape until per-login audit persistence lands.
                return jsonify({
                    "rows": [],
                    "total": 0,
                    "available": False,
                    "message": "No user login audit table is present yet.",
                })

            limit = min(max(int(request.args.get("limit", 50)), 1), 100)
            offset = max(int(request.args.get("offset", 0)), 0)
            cols = _table_columns(cur, audit_table)
            select_parts = [
                "id::text AS id" if "id" in cols else "NULL::text AS id",
                "user_id::text AS user_id" if "user_id" in cols else "NULL::text AS user_id",
                "email" if "email" in cols else "NULL::text AS email",
                "ip_address" if "ip_address" in cols else ("ip AS ip_address" if "ip" in cols else "NULL::text AS ip_address"),
                "user_agent" if "user_agent" in cols else ("ua AS user_agent" if "ua" in cols else "NULL::text AS user_agent"),
                "result" if "result" in cols else ("status AS result" if "status" in cols else "NULL::text AS result"),
                "failure_reason" if "failure_reason" in cols else ("failure_code AS failure_reason" if "failure_code" in cols else "NULL::text AS failure_reason"),
                "created_at" if "created_at" in cols else "NULL::timestamp AS created_at",
            ]
            filters = []
            params = []
            if request.args.get("user_id") and "user_id" in cols:
                filters.append("user_id::text = %s")
                params.append(request.args["user_id"])
            if request.args.get("ip") and ("ip_address" in cols or "ip" in cols):
                filters.append(("ip_address" if "ip_address" in cols else "ip") + " = %s")
                params.append(request.args["ip"])
            where_clause = "WHERE " + " AND ".join(filters) if filters else ""
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM {audit_table} {where_clause}",
                params,
            )
            total = cur.fetchone()["cnt"]
            cur.execute(
                f"""
                SELECT {", ".join(select_parts)}
                FROM {audit_table}
                {where_clause}
                ORDER BY created_at DESC NULLS LAST
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = []
            for row in cur.fetchall():
                item = dict(row)
                item["created_at"] = _isoformat(item.get("created_at"))
                rows.append(item)
            return jsonify({
                "rows": rows,
                "total": total,
                "available": True,
                "limit": limit,
                "offset": offset,
            })
    finally:
        conn.close()


@app.route('/api/users/<user_id>')
def admin_user_detail_api(user_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total, notes = _fetch_user_rows(
                cur,
                user_id=user_id,
                limit=1,
                offset=0,
                include_count=False,
            )
            if not rows:
                return jsonify({"error": "user_not_found"}), 404
            projects, project_notes = _fetch_user_projects(cur, user_id)
            actions, _ = _fetch_user_actions(cur, user_id=user_id, limit=10, offset=0)
            user = rows[0]
        return jsonify({
            "user": user,
            "projects": projects,
            "activity": {
                "level": user["activity_level"],
                "last_login_at": user["last_login_at"],
                "last_active_at": user["last_active_at"],
                "login_count_30d": user["login_count_30d"],
                "query_count_30d": user["query_count_30d"],
            },
            "moderation": user["moderation"],
            "recent_admin_actions": actions,
            "notes": notes + project_notes,
        })
    finally:
        conn.close()


@app.route('/api/users/<user_id>/actions')
def admin_user_detail_actions_api(user_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response

    from psycopg2.extras import RealDictCursor
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "invalid_pagination"}), 400

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total = _fetch_user_actions(cur, user_id=user_id, limit=limit, offset=offset)
        return jsonify({"rows": rows, "total": total, "limit": limit, "offset": offset})
    finally:
        conn.close()


def _moderate_user(user_id, action):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    if action not in ("freeze", "unfreeze"):
        return jsonify({"error": "unsupported_action"}), 400

    payload = request.get_json(silent=True) or {}
    reason = (payload.get("reason") or "").strip()
    if not reason:
        return jsonify({"success": False, "error": "reason_required"}), 400

    from psycopg2.extras import RealDictCursor
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, _, _ = _fetch_user_rows(
                cur,
                user_id=user_id,
                limit=1,
                offset=0,
                include_count=False,
            )
            if not rows:
                return jsonify({"success": False, "error": "user_not_found"}), 404
            before = rows[0]
            moderation_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO user_moderation_actions
                    (id, user_id, operator_id, action, reason, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s, NULL, NOW())
                """,
                (moderation_id, str(user_id), admin["id"], action, reason),
            )
            after_status = "frozen" if action == "freeze" else "active"
            audit_action = "freeze_user" if action == "freeze" else "unfreeze_user"
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action=audit_action,
                target_type="user",
                target_id=user_id,
                diff={
                    "status": {"before": before["status"], "after": after_status},
                    "moderation_action_id": moderation_id,
                },
                reason=reason,
            )
        conn.commit()
        return jsonify({"success": True, "user_id": str(user_id), "status": after_status})
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.route('/api/users/<user_id>/freeze', methods=['POST'])
def admin_user_freeze_api(user_id):
    return _moderate_user(user_id, "freeze")


@app.route('/api/users/<user_id>/unfreeze', methods=['POST'])
def admin_user_unfreeze_api(user_id):
    return _moderate_user(user_id, "unfreeze")


@app.route('/api/stats')
def stats():
    conn = get_db()
    try:
        from psycopg2.extras import RealDictCursor
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT UPPER(status) as status, COUNT(*) as count
                FROM queries
                GROUP BY UPPER(status)
            """)
            rows = cur.fetchall()
        stats_dict = {r['status']: r['count'] for r in rows}
        total = sum(stats_dict.values())
        return jsonify({
            'total': total,
            'done': stats_dict.get('DONE', 0),
            'pending': stats_dict.get('PENDING', 0),
            'running': stats_dict.get('RUNNING', 0),
            'failed': stats_dict.get('FAILED', 0)
        })
    finally:
        conn.close()


@app.route('/api/queries')
def queries():
    from psycopg2.extras import RealDictCursor
    llm = request.args.get('llm')
    status = request.args.get('status')
    brand_id = request.args.get('brand_id')
    topic_id = request.args.get('topic_id')
    prompt_id = request.args.get('prompt_id')
    query_id = request.args.get('id')
    prompt_q = (request.args.get('q') or '').strip()
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    sort = request.args.get('sort', 'id_desc')
    include_count = request.args.get('count', '0') == '1'

    sort_map = {
        'id_desc': 'q.id DESC',
        'id_asc': 'q.id ASC',
        'status': 'UPPER(q.status) ASC, q.id DESC',
    }
    order_clause = sort_map.get(sort, 'q.id DESC')

    conn = get_db()
    try:
        where = []
        params = []

        if query_id:
            where.append("q.id = %s")
            params.append(int(query_id))
        if llm:
            where.append("q.target_llm = %s")
            params.append(llm)
        if status:
            where.append("UPPER(q.status) = UPPER(%s)")
            params.append(status)
        if brand_id:
            where.append("q.brand_id = %s")
            params.append(int(brand_id))
        if topic_id:
            where.append("q.prompt_id IN (SELECT id FROM prompts WHERE topic_id = %s)")
            params.append(int(topic_id))
        if prompt_id:
            where.append("q.prompt_id = %s")
            params.append(int(prompt_id))
        if prompt_q:
            where.append("q.query_text ILIKE %s")
            params.append(f"%{prompt_q}%")

        where_clause = " AND ".join(where) if where else "1=1"

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            by_status = None
            if include_count:
                cur.execute(
                    f"SELECT COUNT(*) as cnt FROM queries q WHERE {where_clause}",
                    params
                )
                total = cur.fetchone()['cnt']
                # Full-dataset status breakdown so the UI summary isn't capped at
                # the current page size (e.g. 50 rows can't represent 166 done).
                cur.execute(
                    f"""SELECT LOWER(q.status) AS st, COUNT(*) AS cnt
                        FROM queries q WHERE {where_clause}
                        GROUP BY LOWER(q.status)""",
                    params
                )
                by_status = {row['st'] or 'unknown': row['cnt'] for row in cur.fetchall()}
            else:
                total = None

            cur.execute(f"""
                SELECT
                    q.id,
                    q.target_llm,
                    q.status,
                    q.query_text,
                    q.brand_id,
                    q.profile_id,
                    q.account_id,
                    q.created_at,
                    q.executed_at,
                    q.retry_count,
                    q.queued_at,
                    q.started_at,
                    q.finished_at,
                    q.latency_ms,
                    q.retry_reason,
                    q.prompt_id,
                    pr.text as prompt_text,
                    t.id as topic_id,
                    t.text as topic_text,
                    r.raw_text as response,
                    r.llm_version,
                    r.citations_json as citations,
                    p.name as profile_name,
                    p.location as profile_location,
                    p.country_code as profile_country,
                    a.phone_number as account_label,
                    a.llm_name as account_llm
                FROM queries q
                LEFT JOIN llm_responses r ON q.id = r.query_id
                LEFT JOIN profiles p ON q.profile_id = p.id
                LEFT JOIN llm_accounts a ON q.account_id = a.id
                LEFT JOIN prompts pr ON q.prompt_id = pr.id
                LEFT JOIN topics t ON pr.topic_id = t.id
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            rows = cur.fetchall()

        result = [dict(r) for r in rows]
        if include_count:
            return jsonify({'rows': result, 'total': total, 'by_status': by_status})
        return jsonify(result)
    finally:
        conn.close()


@app.route('/api/queries', methods=['POST'])
def create_query():
    try:
        data = request.get_json()
        target_llm = data.get('target_llm')
        query_text = data.get('query_text')
        brand_id = data.get('brand_id')

        if not target_llm or not query_text:
            return jsonify({'success': False, 'error': 'target_llm and query_text are required'})

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO queries (target_llm, query_text, brand_id, status, created_at, queued_at)
                    VALUES (%s, %s, %s, 'pending', NOW(), NOW())
                    RETURNING id
                """, (target_llm, query_text, brand_id))
                query_id = cur.fetchone()[0]
            conn.commit()

            if HAS_CELERY and celery_app is not None:
                try:
                    celery_app.send_task(
                        'geo_tracker.tasks.celery_tasks.execute_query',
                        args=[query_id],
                        queue='celery'
                    )
                except Exception as e:
                    print(f"Failed to send Celery task: {e}")

            return jsonify({'success': True, 'query_id': query_id})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/queries/<int:query_id>/retry', methods=['POST'])
def retry_query(query_id):
    try:
        from psycopg2.extras import RealDictCursor
        payload = request.get_json(silent=True) or {}
        retry_reason = (payload.get('reason') or '').strip() or None
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, target_llm, query_text, brand_id FROM queries WHERE id = %s",
                    (query_id,)
                )
                query = cur.fetchone()
                if not query:
                    return jsonify({'success': False, 'error': 'Query not found'})

                # Reset timing fields so the new attempt reports fresh latency.
                # started_at / finished_at / latency_ms are owned by the worker;
                # clearing them here keeps a clean slate per retry.
                cur.execute("""
                    UPDATE queries
                    SET status = 'pending',
                        retry_count = COALESCE(retry_count, 0) + 1,
                        queued_at = NOW(),
                        started_at = NULL,
                        finished_at = NULL,
                        latency_ms = NULL,
                        retry_reason = %s
                    WHERE id = %s
                """, (retry_reason, query_id))
            conn.commit()

            if HAS_CELERY and celery_app is not None:
                try:
                    celery_app.send_task(
                        'geo_tracker.tasks.celery_tasks.execute_query',
                        args=[query_id],
                        queue='celery'
                    )
                except Exception as e:
                    print(f"Failed to send Celery task: {e}")

            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/queries/batch_trigger', methods=['POST'])
def batch_trigger_queries():
    """Reset matching queries to pending and dispatch them to Celery.

    Accepts JSON body matching /api/queries GET filters:
      brand_id, topic_id, prompt_id, llm, status, id, q
    Optional:
      max (int, default 2000) — hard cap; refuse if match count exceeds it
      dry_run (bool) — return count only, no writes
      reason (str) — stored in retry_reason (default 'batch_trigger')
    Default status filter: only 'pending' or 'failed' queries.
    """
    from psycopg2.extras import RealDictCursor
    payload = request.get_json(silent=True) or {}

    ids = payload.get('ids')
    brand_id = payload.get('brand_id')
    topic_id = payload.get('topic_id')
    prompt_id = payload.get('prompt_id')
    llm = (payload.get('llm') or '').strip() or None
    status = (payload.get('status') or '').strip() or None
    query_id = payload.get('id')
    prompt_q = (payload.get('q') or '').strip() or None
    max_count = int(payload.get('max') or 2000)
    dry_run = bool(payload.get('dry_run'))
    reason = (payload.get('reason') or 'batch_trigger').strip() or 'batch_trigger'

    where = []
    params = []
    if isinstance(ids, list) and ids:
        clean_ids = [int(x) for x in ids if str(x).strip().lstrip('-').isdigit()]
        if not clean_ids:
            return jsonify({'success': False, 'error': 'ids 列表为空或无效'}), 400
        where.append("id = ANY(%s)")
        params.append(clean_ids)
    else:
        if query_id:
            where.append("id = %s"); params.append(int(query_id))
        if llm:
            where.append("target_llm = %s"); params.append(llm)
        if status:
            where.append("UPPER(status) = UPPER(%s)"); params.append(status)
        else:
            where.append("LOWER(status) IN ('pending','failed')")
        if brand_id:
            where.append("brand_id = %s"); params.append(int(brand_id))
        if topic_id:
            where.append("prompt_id IN (SELECT id FROM prompts WHERE topic_id = %s)")
            params.append(int(topic_id))
        if prompt_id:
            where.append("prompt_id = %s"); params.append(int(prompt_id))
        if prompt_q:
            where.append("query_text ILIKE %s"); params.append(f"%{prompt_q}%")

    where_clause = " AND ".join(where) if where else "1=1"

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM queries WHERE {where_clause}", params)
            total = cur.fetchone()[0]
            if dry_run:
                return jsonify({'success': True, 'count': total, 'dry_run': True})
            if total == 0:
                return jsonify({'success': True, 'count': 0, 'dispatched': 0})
            if total > max_count:
                return jsonify({
                    'success': False,
                    'error': f'匹配 {total} 条，超过上限 {max_count}，请缩小筛选或传入更大的 max',
                    'count': total,
                }), 400
            cur.execute(f"""
                UPDATE queries
                SET status = 'pending',
                    retry_count = COALESCE(retry_count, 0) + 1,
                    queued_at = NOW(),
                    started_at = NULL,
                    finished_at = NULL,
                    latency_ms = NULL,
                    retry_reason = %s
                WHERE {where_clause}
                RETURNING id
            """, [reason, *params])
            ids = [r[0] for r in cur.fetchall()]
        conn.commit()
    finally:
        conn.close()

    dispatched = 0
    dispatch_failed = 0
    if HAS_CELERY and celery_app is not None:
        for qid in ids:
            try:
                celery_app.send_task(
                    'geo_tracker.tasks.celery_tasks.execute_query',
                    args=[qid],
                    queue='celery',
                )
                dispatched += 1
            except Exception as e:
                dispatch_failed += 1
                print(f"batch_trigger: celery dispatch failed for q={qid}: {e}")
    else:
        print("batch_trigger: Celery not available; queries reset but not dispatched")

    return jsonify({
        'success': True,
        'count': len(ids),
        'dispatched': dispatched,
        'dispatch_failed': dispatch_failed,
    })


@app.route('/api/queries/<int:query_id>/mark_failed', methods=['POST'])
def mark_failed(query_id):
    try:
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "UPDATE queries SET status = 'failed' WHERE id = %s AND status = 'done'",
                    (query_id,)
                )
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Query not found or not in done status'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts')
def list_accounts():
    """列出所有 LLM 账号"""
    try:
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, llm_name, phone_number, status,
                           query_count_today AS daily_used, daily_limit,
                           consecutive_fails,
                           CASE WHEN cookies_json IS NOT NULL AND cookies_json != ''
                                THEN CASE
                                    WHEN cookies_json::text LIKE '[%'
                                    THEN json_array_length(cookies_json::json)
                                    WHEN cookies_json::text LIKE '{%'
                                    THEN json_array_length((cookies_json::json->'cookies'))
                                    ELSE 0 END
                                ELSE 0 END AS cookie_count,
                           cookies_updated_at,
                           created_at AS updated_at
                    FROM llm_accounts
                    ORDER BY llm_name, id
                """)
                rows = cur.fetchall()
            # Convert datetime for JSON serialization
            for row in rows:
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat()
                if row.get('cookies_updated_at'):
                    row['cookies_updated_at'] = row['cookies_updated_at'].isoformat()
            return jsonify(rows)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/import_cookies', methods=['POST'])
def import_cookies_api():
    """通过 Web UI 导入 cookies 到 llm_accounts"""
    import json as json_mod
    try:
        data = request.get_json()
        platform = data.get('platform', '').strip()
        label = data.get('label', '').strip() or 'web_upload'
        daily_limit = data.get('daily_limit', 20)
        cookies_raw = data.get('cookies_json', '')
        local_storage_raw = data.get('local_storage', '')

        import logging as _logging
        _logging.getLogger(__name__).info(
            f"import_cookies: platform={platform}, label={label}, "
            f"cookies_raw_len={len(cookies_raw)}, local_storage_raw_len={len(local_storage_raw)}, "
            f"local_storage_raw={local_storage_raw[:200] if local_storage_raw else '(empty)'}"
        )

        if not platform:
            return jsonify({'success': False, 'error': 'Platform is required'})

        cookies = json_mod.loads(cookies_raw)

        # Auto-detect and convert EditThisCookie format
        SAME_SITE_MAP = {
            'unspecified': 'Lax', 'no_restriction': 'None',
            'lax': 'Lax', 'strict': 'Strict',
        }
        if (isinstance(cookies, list) and len(cookies) > 0
                and isinstance(cookies[0], dict)
                and ('storeId' in cookies[0] or 'hostOnly' in cookies[0])):
            import time as _time
            converted = []
            for c in cookies:
                entry = {
                    'name': c['name'], 'value': c['value'],
                    'domain': c['domain'], 'path': c.get('path', '/'),
                }
                if c.get('expirationDate'):
                    entry['expires'] = c['expirationDate']
                elif c.get('session'):
                    # Session cookie 没有过期时间，给它 30 天有效期
                    # 避免 Playwright 注入后立即过期
                    entry['expires'] = _time.time() + 30 * 86400
                if c.get('httpOnly'):
                    entry['httpOnly'] = True
                if c.get('secure'):
                    entry['secure'] = True
                ss = c.get('sameSite', 'unspecified')
                entry['sameSite'] = SAME_SITE_MAP.get(ss, 'Lax')
                converted.append(entry)
            cookies = converted

        if not isinstance(cookies, list) or len(cookies) == 0:
            return jsonify({'success': False, 'error': 'No valid cookies found'})

        # 如果有 localStorage 数据，打包为新格式
        local_storage = {}
        if local_storage_raw:
            try:
                local_storage = json_mod.loads(local_storage_raw)
                if not isinstance(local_storage, dict):
                    local_storage = {}
            except Exception:
                local_storage = {}

        if local_storage:
            cookies_json_str = json_mod.dumps({
                "cookies": cookies,
                "localStorage": local_storage,
            })
        else:
            cookies_json_str = json_mod.dumps(cookies)

        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if account with same platform + label exists
                cur.execute(
                    "SELECT id FROM llm_accounts WHERE llm_name = %s AND phone_number = %s",
                    (platform, label)
                )
                existing = cur.fetchone()

                if existing:
                    cur.execute(
                        """UPDATE llm_accounts
                           SET cookies_json = %s, status = 'active',
                               consecutive_fails = 0,
                               cookies_updated_at = NOW()
                           WHERE id = %s""",
                        (cookies_json_str, existing['id'])
                    )
                    msg = f'Updated account #{existing["id"]} with {len(cookies)} cookies'
                    if local_storage:
                        msg += f' + {len(local_storage)} localStorage items'
                else:
                    cur.execute(
                        """INSERT INTO llm_accounts
                           (llm_name, email, password_encrypted, phone_number,
                            cookies_json, daily_limit, status, cookies_updated_at)
                           VALUES (%s, %s, '', %s, %s, %s, 'active', NOW())""",
                        (platform, f'{label}@{platform}.local', label,
                         cookies_json_str, daily_limit)
                    )
                    msg = f'Created new {platform} account with {len(cookies)} cookies'
                    if local_storage:
                        msg += f' + {len(local_storage)} localStorage items'

            conn.commit()
            return jsonify({'success': True, 'message': msg})
        finally:
            conn.close()
    except json_mod.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Invalid JSON: {e}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>/status', methods=['POST'])
def update_account_status(account_id):
    """启用/禁用账号"""
    try:
        data = request.get_json()
        new_status = data.get('status', 'active')
        if new_status not in ('active', 'banned', 'cooldown'):
            return jsonify({'success': False, 'error': 'Invalid status'})
        conn = get_db()
        try:
            with conn.cursor() as cur:
                if new_status == 'active':
                    # 启用时清除 cooldown 和失败计数
                    cur.execute(
                        "UPDATE llm_accounts SET status = %s, cooldown_until = NULL, "
                        "consecutive_fails = 0 WHERE id = %s",
                        (new_status, account_id)
                    )
                else:
                    cur.execute(
                        "UPDATE llm_accounts SET status = %s WHERE id = %s",
                        (new_status, account_id)
                    )
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Account not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>/reset', methods=['POST'])
def reset_account_fails(account_id):
    """重置连续失败次数和每日用量"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE llm_accounts
                       SET consecutive_fails = 0, query_count_today = 0,
                           status = 'active', cooldown_until = NULL
                       WHERE id = %s""",
                    (account_id,)
                )
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Account not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """删除账号"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM llm_accounts WHERE id = %s", (account_id,))
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Account not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/accounts/<int:account_id>/auto_login', methods=['POST'])
def trigger_auto_login(account_id):
    """手动触发已有账号的自动重新登录"""
    if not HAS_CELERY:
        return jsonify({'success': False, 'error': 'Celery not available'})
    try:
        result = celery_app.send_task(
            'geo_tracker.tasks.celery_tasks.auto_login',
            kwargs={'account_id': account_id},
            queue='account_login',
        )
        return jsonify({'success': True, 'task_id': result.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/sms_register', methods=['POST'])
def trigger_sms_register():
    """手动触发新账号注册"""
    if not HAS_CELERY:
        return jsonify({'success': False, 'error': 'Celery not available'})
    data = request.get_json(force=True)
    platform = data.get('platform', 'doubao')
    try:
        result = celery_app.send_task(
            'geo_tracker.tasks.celery_tasks.auto_login',
            kwargs={'platform': platform, 'new_account': True},
            queue='account_login',
        )
        return jsonify({'success': True, 'task_id': result.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/task_status/<task_id>')
def task_status(task_id):
    """查询 celery task 执行状态"""
    if not HAS_CELERY:
        return jsonify({'state': 'UNKNOWN', 'error': 'Celery not available'})
    try:
        result = celery_app.AsyncResult(task_id)
        response = {
            'state': result.state,
            'task_id': task_id,
        }
        if result.state == 'SUCCESS':
            response['result'] = result.result
        elif result.state == 'FAILURE':
            response['error'] = str(result.result)
        return jsonify(response)
    except Exception as e:
        return jsonify({'state': 'ERROR', 'error': str(e)})


_DEBUG_FILE_EXTS = ('.html', '.png', '.jpg', '.jpeg', '.json')


def _classify_debug_file(fname: str) -> str:
    lower = fname.lower()
    if lower.endswith('.html'):
        return 'html'
    if lower.endswith('.png') or lower.endswith('.jpg') or lower.endswith('.jpeg'):
        return 'image'
    if lower.endswith('.json'):
        return 'json'
    return 'other'


@app.route('/api/html_files')
def html_files():
    """List debug artifacts in SCREENSHOT_DIR (HTML + PNG + JSON snapshots),
    sorted by mtime descending, with optional pagination."""
    query_id = request.args.get('query_id')
    # When include_images=false, behave like the legacy HTML-only endpoint.
    include_images = request.args.get('include_images', '1') not in ('0', 'false', 'False')
    try:
        page = max(1, int(request.args.get('page', 1)))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get('per_page', 20))
    except ValueError:
        per_page = 20
    per_page = max(1, min(per_page, 200))

    try:
        entries = []
        if os.path.isdir(SCREENSHOT_DIR):
            for fname in os.listdir(SCREENSHOT_DIR):
                lower = fname.lower()
                if not lower.endswith(_DEBUG_FILE_EXTS):
                    continue
                if not include_images and not lower.endswith('.html'):
                    continue
                if query_id and f'query_{query_id}_' not in fname and f'query_{query_id}.' not in fname:
                    continue
                fpath = os.path.join(SCREENSHOT_DIR, fname)
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue
                entries.append({
                    'name': fname,
                    'path': fpath,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'type': _classify_debug_file(fname),
                })

        # Sort by mtime descending (newest first)
        entries.sort(key=lambda e: e['mtime'], reverse=True)

        total = len(entries)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = entries[start:end]

        # Accept-based response: legacy clients that don't pass page still get the
        # full array; paginated clients get {items, total, page, per_page}.
        if request.args.get('page') is None and request.args.get('per_page') is None:
            return jsonify(entries)
        return jsonify({
            'items': page_items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page else 1,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _validate_screenshot_path(path: str):
    """Validate path is under SCREENSHOT_DIR. Returns (real_path, error_response)."""
    if not path:
        return None, ("Path required", 400)
    real_path = os.path.realpath(path)
    real_dir = os.path.realpath(SCREENSHOT_DIR)
    if not real_path.startswith(real_dir + os.sep) and real_path != real_dir:
        return None, ("Access denied", 403)
    if not os.path.isfile(real_path):
        return None, ("File not found", 404)
    return real_path, None


@app.route('/api/html')
def serve_html_source():
    path = request.args.get('path')
    real_path, err = _validate_screenshot_path(path)
    if err:
        return err
    with open(real_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    return Response(content, mimetype='text/plain; charset=utf-8')


@app.route('/api/screenshot')
def serve_screenshot():
    """Serve binary image files (PNG/JPG) from SCREENSHOT_DIR."""
    path = request.args.get('path')
    real_path, err = _validate_screenshot_path(path)
    if err:
        return err
    lower = real_path.lower()
    if lower.endswith('.png'):
        mime = 'image/png'
    elif lower.endswith('.jpg') or lower.endswith('.jpeg'):
        mime = 'image/jpeg'
    else:
        return "Unsupported file type", 415
    with open(real_path, 'rb') as f:
        data = f.read()
    return Response(data, mimetype=mime)


@app.route('/api/backfill_citations', methods=['POST'])
def backfill_citations():
    """从历史 raw_text 和保存的 HTML 文件中提取 URL 作为 citations"""
    from psycopg2.extras import RealDictCursor
    import re
    import json as json_mod
    url_pattern = re.compile(
        r'https?://[^\s<>"\')\]},;]+',
        re.IGNORECASE,
    )
    # href 提取
    href_pattern = re.compile(
        r'<a\s[^>]*href=["\']?(https?://[^"\'>\s]+)',
        re.IGNORECASE,
    )
    skip_domains = {
        'chatgpt.com', 'gemini.google.com', 'accounts.google.com',
        'cdn.oaistatic.com', 'oaiusercontent.com', 'cdn-cgi',
        'gstatic.com', 'googleapis.com', 'google.com/gsi',
        'statsig', 'sentry', 'intercom',
    }

    def extract_urls_from_html_file(query_id):
        """从保存的 HTML debug 文件中提取链接"""
        urls = []
        if not os.path.isdir(SCREENSHOT_DIR):
            return urls
        for fname in os.listdir(SCREENSHOT_DIR):
            if not fname.endswith('.html'):
                continue
            if f'query_{query_id}_' not in fname:
                continue
            if 'extract_fail' in fname or 'content' in fname:
                # 这些是完整页面 HTML，可以从中提取
                fpath = os.path.join(SCREENSHOT_DIR, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        html = f.read()
                    urls.extend(href_pattern.findall(html))
                except Exception:
                    pass
        return urls

    try:
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT r.id, r.query_id, r.raw_text, r.response_html
                    FROM llm_responses r
                    WHERE r.citations_json IS NULL
                      AND r.raw_text IS NOT NULL
                      AND LENGTH(r.raw_text) > 20
                """)
                rows = cur.fetchall()

                updated = 0
                for row in rows:
                    # 从 raw_text 提取 URL
                    all_urls = url_pattern.findall(row['raw_text'] or '')
                    # 优先从 response_html 列提取（比文件更可靠）
                    if row.get('response_html'):
                        all_urls.extend(href_pattern.findall(row['response_html']))
                    # 再从 HTML debug 文件提取
                    all_urls.extend(extract_urls_from_html_file(row['query_id']))

                    seen = set()
                    citations = []
                    for u in all_urls:
                        u = u.rstrip('.,;:!?)]}')
                        if u in seen:
                            continue
                        if any(d in u for d in skip_domains):
                            continue
                        seen.add(u)
                        citations.append({
                            'url': u,
                            'title': '',
                            'index': len(citations) + 1,
                        })

                    if citations:
                        cur.execute(
                            "UPDATE llm_responses SET citations_json = %s WHERE id = %s",
                            (json_mod.dumps(citations), row['id'])
                        )
                        updated += 1

                conn.commit()
                return jsonify({'success': True, 'scanned': len(rows), 'updated': updated})
        finally:
            conn.close()
    except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# --- Segment/Profile Admin API ----------------------------------------------

SEGMENT_STATUSES = {"active", "draft", "paused"}
PROFILE_STATUSES = {"active", "draft", "paused"}


def _ensure_segment_profile_tables():
    """Ensure additive Segment/Profile tables and compatibility columns exist."""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS segments (
                        id VARCHAR(64) PRIMARY KEY,
                        code VARCHAR(64) UNIQUE,
                        name TEXT NOT NULL,
                        industry_id VARCHAR(128),
                        industry TEXT,
                        status VARCHAR(16) NOT NULL DEFAULT 'draft',
                        weight NUMERIC NOT NULL DEFAULT 0,
                        age_range TEXT,
                        income TEXT,
                        regions TEXT,
                        sampling_rate TEXT,
                        note TEXT,
                        is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                        deleted_at TIMESTAMP,
                        created_by VARCHAR(36),
                        updated_by VARCHAR(36),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS code VARCHAR(64)")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS name TEXT")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS industry_id VARCHAR(128)")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS industry TEXT")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'draft'")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS weight NUMERIC NOT NULL DEFAULT 0")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS age_range TEXT")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS income TEXT")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS regions TEXT")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS sampling_rate TEXT")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS note TEXT")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS created_by VARCHAR(36)")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS updated_by VARCHAR(36)")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()")
                cur.execute("ALTER TABLE segments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()")
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_segments_status_industry
                    ON segments (status, industry_id)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_segments_deleted_updated
                    ON segments (is_deleted, updated_at DESC)
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS profiles (
                        id VARCHAR(64) PRIMARY KEY DEFAULT (
                            'pf_' || substr(md5(random()::text || clock_timestamp()::text), 1, 16)
                        ),
                        segment_id VARCHAR(64),
                        code VARCHAR(64),
                        name TEXT NOT NULL,
                        demographic TEXT,
                        need TEXT,
                        weight NUMERIC NOT NULL DEFAULT 1,
                        status VARCHAR(16) NOT NULL DEFAULT 'draft',
                        persona_json JSONB,
                        is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                        deleted_at TIMESTAMP,
                        created_by VARCHAR(36),
                        updated_by VARCHAR(36),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS segment_id VARCHAR(64)")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS code VARCHAR(64)")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS demographic TEXT")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS need TEXT")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS weight NUMERIC NOT NULL DEFAULT 1")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'draft'")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS persona_json JSONB")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS created_by VARCHAR(36)")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS updated_by VARCHAR(36)")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()")
                cur.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()")
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_profiles_segment_status
                    ON profiles (segment_id, status)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_profiles_deleted_updated
                    ON profiles (is_deleted, updated_at DESC)
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS segment_generation_logs (
                        id VARCHAR(36) PRIMARY KEY,
                        brand_id VARCHAR(128),
                        brand_name TEXT,
                        industry_id VARCHAR(128),
                        llm_model TEXT NOT NULL,
                        prompt_used TEXT,
                        input_params JSONB,
                        output_json JSONB,
                        segments_generated INTEGER DEFAULT 0,
                        segments_skipped INTEGER DEFAULT 0,
                        tokens_used INTEGER DEFAULT 0,
                        estimated_cost NUMERIC,
                        created_by VARCHAR(36),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS profile_generation_logs (
                        id VARCHAR(36) PRIMARY KEY,
                        segment_id VARCHAR(64) NOT NULL,
                        llm_model TEXT NOT NULL,
                        prompt_used TEXT,
                        input_params JSONB,
                        output_json JSONB,
                        profiles_generated INTEGER DEFAULT 0,
                        profiles_skipped INTEGER DEFAULT 0,
                        tokens_used INTEGER DEFAULT 0,
                        estimated_cost NUMERIC,
                        created_by VARCHAR(36),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                )
            conn.commit()
            print("DB migration: Segment/Profile Admin tables ensured")
        finally:
            conn.close()
    except Exception as e:
        print(f"DB migration warning (non-fatal): {e}")


def _admin_float(value, default=0.0):
    if value in (None, ""):
        return default
    raw = str(value).strip()
    try:
        number = float(raw.rstrip("%"))
    except (TypeError, ValueError):
        return default
    if raw.endswith("%"):
        number = number / 100.0
    return max(0.0, number)


def _admin_json(value, default=None):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _pagination(page, per_page, total):
    total_pages = (int(total) + per_page - 1) // per_page if per_page else 0
    return {
        "page": page,
        "per_page": per_page,
        "total": int(total or 0),
        "total_pages": total_pages,
    }


def _segment_payload(data, existing_id=None):
    data = data or {}
    segment_id = str(data.get("id") or data.get("code") or existing_id or "").strip().upper()
    if not segment_id:
        segment_id = "SEG-" + str(uuid.uuid4())[:8].upper()
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("segment_name_required")
    status = str(data.get("status") or "draft").strip().lower()
    if status == "deleted":
        status = "paused"
    if status not in SEGMENT_STATUSES:
        raise ValueError("invalid_segment_status")
    return {
        "id": segment_id,
        "code": str(data.get("code") or segment_id).strip().upper(),
        "name": name,
        "industry_id": str(data.get("industry_id") or "").strip() or None,
        "industry": str(data.get("industry") or data.get("industry_name") or "").strip(),
        "status": status,
        "weight": _admin_float(data.get("weight"), 0.0),
        "age_range": str(data.get("age_range") or data.get("ageRange") or "").strip(),
        "income": str(data.get("income") or "").strip(),
        "regions": str(data.get("regions") or "").strip(),
        "sampling_rate": str(data.get("sampling_rate") or data.get("samplingRate") or "").strip(),
        "note": str(data.get("note") or "").strip(),
    }


def _profile_payload(data, segment_id, existing_id=None):
    data = data or {}
    profile_id = str(data.get("id") or data.get("code") or existing_id or "").strip().upper()
    if not profile_id:
        suffix = str(segment_id or "SEG").replace("SEG-", "").replace(" ", "-")
        profile_id = f"P-{suffix}-{str(uuid.uuid4())[:6].upper()}"
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("profile_name_required")
    status = str(data.get("status") or "draft").strip().lower()
    if status == "deleted":
        status = "paused"
    if status not in PROFILE_STATUSES:
        raise ValueError("invalid_profile_status")
    return {
        "id": profile_id,
        "code": str(data.get("code") or profile_id).strip().upper(),
        "segment_id": str(segment_id).strip().upper(),
        "name": name,
        "demographic": str(data.get("demographic") or "").strip(),
        "need": str(data.get("need") or "").strip(),
        "weight": _admin_float(data.get("weight"), 1.0),
        "status": status,
        "persona_json": _admin_json(data.get("persona_json"), {}) or {},
    }


def _segment_row(row):
    item = dict(row or {})
    weight = item.get("weight")
    try:
        weight = float(weight or 0)
    except (TypeError, ValueError):
        weight = 0.0
    profile_count = int(item.get("profile_count") or 0)
    active_profile_count = int(item.get("active_profile_count") or 0)
    return {
        "id": item.get("id"),
        "code": item.get("code") or item.get("id"),
        "name": item.get("name"),
        "industry_id": item.get("industry_id"),
        "industry": item.get("industry") or item.get("industry_id") or "",
        "status": item.get("status") or "draft",
        "weight": weight,
        "age_range": item.get("age_range") or "",
        "ageRange": item.get("age_range") or "",
        "income": item.get("income") or "",
        "regions": item.get("regions") or "",
        "sampling_rate": item.get("sampling_rate") or "",
        "samplingRate": item.get("sampling_rate") or "",
        "note": item.get("note") or "",
        "profile_count": profile_count,
        "profileCount": profile_count,
        "active_profile_count": active_profile_count,
        "activeProfileCount": active_profile_count,
        "created_at": _isoformat(item.get("created_at")),
        "updated_at": _isoformat(item.get("updated_at")),
    }


def _profile_row(row):
    item = dict(row or {})
    weight = item.get("weight")
    try:
        weight = float(weight or 0)
    except (TypeError, ValueError):
        weight = 0.0
    persona_json = _admin_json(item.get("persona_json"), {}) or {}
    api_id = item.get("api_id") or item.get("code") or item.get("id")
    return {
        "id": str(api_id),
        "code": item.get("code") or str(api_id),
        "segment_id": item.get("segment_id"),
        "name": item.get("name"),
        "demographic": item.get("demographic") or "",
        "need": item.get("need") or "",
        "weight": weight,
        "status": item.get("status") or "draft",
        "persona_json": persona_json,
        "created_at": _isoformat(item.get("created_at")),
        "updated_at": _isoformat(item.get("updated_at")),
    }


def _fetch_segments(cur, *, page=1, per_page=50, q=None, status=None, industry_id=None):
    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 50), 200))
    offset = (page - 1) * per_page
    where = ["COALESCE(s.is_deleted, FALSE) = FALSE", "COALESCE(s.status, 'draft') <> 'deleted'"]
    params = []
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        where.append(
            "(s.id ILIKE %s OR COALESCE(s.code, '') ILIKE %s OR s.name ILIKE %s "
            "OR COALESCE(s.industry, '') ILIKE %s OR COALESCE(s.status, '') ILIKE %s "
            "OR COALESCE(s.note, '') ILIKE %s)"
        )
        params.extend([like, like, like, like, like, like])
    status = (status or "").strip().lower()
    if status and status != "all":
        where.append("s.status = %s")
        params.append(status)
    industry_id = (industry_id or "").strip()
    if industry_id:
        where.append("(COALESCE(s.industry_id, '') = %s OR COALESCE(s.industry, '') = %s)")
        params.extend([industry_id, industry_id])
    where_clause = "WHERE " + " AND ".join(where)
    cur.execute(f"SELECT COUNT(*) AS cnt FROM segments s {where_clause}", params)
    total = int(cur.fetchone()["cnt"] or 0)
    cur.execute(
        f"""
        SELECT s.*,
               COALESCE(pc.profile_count, 0) AS profile_count,
               COALESCE(pc.active_profile_count, 0) AS active_profile_count
        FROM segments s
        LEFT JOIN (
            SELECT segment_id,
                   COUNT(*) AS profile_count,
                   COUNT(*) FILTER (WHERE status = 'active') AS active_profile_count
            FROM profiles
            WHERE COALESCE(is_deleted, FALSE) = FALSE
            GROUP BY segment_id
        ) pc ON pc.segment_id = s.id
        {where_clause}
        ORDER BY s.updated_at DESC NULLS LAST, s.created_at DESC NULLS LAST, s.id
        LIMIT %s OFFSET %s
        """,
        params + [per_page, offset],
    )
    rows = [_segment_row(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT
            COUNT(*) AS segment_count,
            COUNT(*) FILTER (WHERE status = 'active') AS active_segment_count,
            COALESCE(SUM(weight) FILTER (WHERE status = 'active'), 0) AS active_weight_sum
        FROM segments
        WHERE COALESCE(is_deleted, FALSE) = FALSE AND COALESCE(status, 'draft') <> 'deleted'
        """
    )
    summary = dict(cur.fetchone() or {})
    cur.execute(
        """
        SELECT
            COUNT(*) AS profile_count,
            COUNT(*) FILTER (WHERE status = 'active') AS active_profile_count
        FROM profiles
        WHERE COALESCE(is_deleted, FALSE) = FALSE
        """
    )
    profile_summary = dict(cur.fetchone() or {})
    summary.update(profile_summary)
    summary["active_weight_sum"] = float(summary.get("active_weight_sum") or 0)
    return rows, total, summary


def _get_segment(cur, segment_id):
    cur.execute(
        """
        SELECT s.*,
               COALESCE(pc.profile_count, 0) AS profile_count,
               COALESCE(pc.active_profile_count, 0) AS active_profile_count
        FROM segments s
        LEFT JOIN (
            SELECT segment_id,
                   COUNT(*) AS profile_count,
                   COUNT(*) FILTER (WHERE status = 'active') AS active_profile_count
            FROM profiles
            WHERE COALESCE(is_deleted, FALSE) = FALSE
            GROUP BY segment_id
        ) pc ON pc.segment_id = s.id
        WHERE s.id = %s AND COALESCE(s.is_deleted, FALSE) = FALSE
          AND COALESCE(s.status, 'draft') <> 'deleted'
        """,
        (str(segment_id).strip().upper(),),
    )
    row = cur.fetchone()
    return _segment_row(row) if row else None


def _create_segment(cur, payload, admin_id):
    data = _segment_payload(payload)
    cur.execute(
        """
        SELECT 1
        FROM segments
        WHERE id = %s AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (data["id"],),
    )
    if cur.fetchone():
        raise ValueError("segment_id_exists")
    cur.execute(
        """
        INSERT INTO segments
            (id, code, name, industry_id, industry, status, weight, age_range,
             income, regions, sampling_rate, note, is_deleted, created_by,
             updated_by, created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, NOW(), NOW())
        """,
        (
            data["id"],
            data["code"],
            data["name"],
            data["industry_id"],
            data["industry"],
            data["status"],
            data["weight"],
            data["age_range"],
            data["income"],
            data["regions"],
            data["sampling_rate"],
            data["note"],
            admin_id,
            admin_id,
        ),
    )
    return _get_segment(cur, data["id"])


def _update_segment(cur, segment_id, payload, admin_id):
    data = _segment_payload(payload, existing_id=segment_id)
    data["id"] = str(segment_id).strip().upper()
    cur.execute(
        """
        UPDATE segments
        SET code = %s, name = %s, industry_id = %s, industry = %s, status = %s,
            weight = %s, age_range = %s, income = %s, regions = %s,
            sampling_rate = %s, note = %s, updated_by = %s, updated_at = NOW()
        WHERE id = %s AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (
            data["code"],
            data["name"],
            data["industry_id"],
            data["industry"],
            data["status"],
            data["weight"],
            data["age_range"],
            data["income"],
            data["regions"],
            data["sampling_rate"],
            data["note"],
            admin_id,
            data["id"],
        ),
    )
    if cur.rowcount == 0:
        return None
    return _get_segment(cur, data["id"])


def _soft_delete_segment(cur, segment_id, admin_id):
    segment_id = str(segment_id).strip().upper()
    before = _get_segment(cur, segment_id)
    if not before:
        return None
    cur.execute(
        """
        UPDATE segments
        SET status = 'deleted', is_deleted = TRUE, deleted_at = NOW(),
            updated_by = %s, updated_at = NOW()
        WHERE id = %s AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (admin_id, segment_id),
    )
    cur.execute(
        """
        UPDATE profiles
        SET status = 'deleted', is_deleted = TRUE, deleted_at = NOW(),
            updated_by = %s, updated_at = NOW()
        WHERE segment_id = %s AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (admin_id, segment_id),
    )
    return before


def _upsert_segment(cur, payload, admin_id):
    data = _segment_payload(payload)
    cur.execute("SELECT 1 FROM segments WHERE id = %s", (data["id"],))
    exists = bool(cur.fetchone())
    if exists:
        cur.execute(
            """
            UPDATE segments
            SET code = %s, name = %s, industry_id = %s, industry = %s, status = %s,
                weight = %s, age_range = %s, income = %s, regions = %s,
                sampling_rate = %s, note = %s, is_deleted = FALSE, deleted_at = NULL,
                updated_by = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (
                data["code"],
                data["name"],
                data["industry_id"],
                data["industry"],
                data["status"],
                data["weight"],
                data["age_range"],
                data["income"],
                data["regions"],
                data["sampling_rate"],
                data["note"],
                admin_id,
                data["id"],
            ),
        )
        return "updated", _get_segment(cur, data["id"])
    return "added", _create_segment(cur, data, admin_id)


def _import_segments(cur, rows, admin_id):
    added = updated = skipped = 0
    output = []
    for row in rows or []:
        try:
            outcome, segment = _upsert_segment(cur, row, admin_id)
            if outcome == "added":
                added += 1
            else:
                updated += 1
            output.append(segment)
        except ValueError:
            skipped += 1
    return {"added": added, "updated": updated, "skipped": skipped, "rows": output}


def _fetch_profiles(cur, segment_id, *, page=1, per_page=100, q=None, status=None):
    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 100), 100000))
    offset = (page - 1) * per_page
    where = ["p.segment_id = %s", "COALESCE(p.is_deleted, FALSE) = FALSE", "COALESCE(p.status, 'draft') <> 'deleted'"]
    params = [str(segment_id).strip().upper()]
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        where.append(
            "(COALESCE(p.code, '') ILIKE %s OR CAST(p.id AS TEXT) ILIKE %s OR p.name ILIKE %s "
            "OR COALESCE(p.demographic, '') ILIKE %s OR COALESCE(p.need, '') ILIKE %s "
            "OR COALESCE(p.status, '') ILIKE %s)"
        )
        params.extend([like, like, like, like, like, like])
    status = (status or "").strip().lower()
    if status and status != "all":
        where.append("p.status = %s")
        params.append(status)
    where_clause = "WHERE " + " AND ".join(where)
    cur.execute(f"SELECT COUNT(*) AS cnt FROM profiles p {where_clause}", params)
    total = int(cur.fetchone()["cnt"] or 0)
    cur.execute(
        f"""
        SELECT COALESCE(p.code, CAST(p.id AS TEXT)) AS api_id, p.*
        FROM profiles p
        {where_clause}
        ORDER BY p.updated_at DESC NULLS LAST, p.created_at DESC NULLS LAST, p.id
        LIMIT %s OFFSET %s
        """,
        params + [per_page, offset],
    )
    return [_profile_row(row) for row in cur.fetchall()], total


def _get_profile(cur, segment_id, profile_id):
    cur.execute(
        """
        SELECT COALESCE(code, CAST(id AS TEXT)) AS api_id, *
        FROM profiles
        WHERE segment_id = %s
          AND (code = %s OR CAST(id AS TEXT) = %s)
          AND COALESCE(is_deleted, FALSE) = FALSE
          AND COALESCE(status, 'draft') <> 'deleted'
        """,
        (
            str(segment_id).strip().upper(),
            str(profile_id).strip().upper(),
            str(profile_id).strip(),
        ),
    )
    row = cur.fetchone()
    return _profile_row(row) if row else None


def _create_profile(cur, segment_id, payload, admin_id):
    segment = _get_segment(cur, segment_id)
    if not segment:
        raise ValueError("segment_not_found")
    data = _profile_payload(payload, segment_id)
    cur.execute(
        """
        SELECT 1
        FROM profiles
        WHERE segment_id = %s
          AND (code = %s OR CAST(id AS TEXT) = %s)
          AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (data["segment_id"], data["code"], data["id"]),
    )
    if cur.fetchone():
        raise ValueError("profile_id_exists")
    cur.execute(
        """
        INSERT INTO profiles
            (code, segment_id, name, demographic, need, weight, status,
             persona_json, is_deleted, created_by, updated_by, created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, FALSE, %s, %s, NOW(), NOW())
        RETURNING COALESCE(code, CAST(id AS TEXT)) AS api_id, *
        """,
        (
            data["code"],
            data["segment_id"],
            data["name"],
            data["demographic"],
            data["need"],
            data["weight"],
            data["status"],
            json.dumps(data["persona_json"], default=_json_default),
            admin_id,
            admin_id,
        ),
    )
    return _profile_row(cur.fetchone())


def _update_profile(cur, segment_id, profile_id, payload, admin_id):
    if not _get_segment(cur, segment_id):
        raise ValueError("segment_not_found")
    existing = _get_profile(cur, segment_id, profile_id)
    if not existing:
        return None
    data = _profile_payload(payload, segment_id, existing_id=profile_id)
    cur.execute(
        """
        UPDATE profiles
        SET code = %s, name = %s, demographic = %s, need = %s, weight = %s,
            status = %s, persona_json = %s::jsonb, updated_by = %s, updated_at = NOW()
        WHERE segment_id = %s
          AND (code = %s OR CAST(id AS TEXT) = %s)
          AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (
            data["code"],
            data["name"],
            data["demographic"],
            data["need"],
            data["weight"],
            data["status"],
            json.dumps(data["persona_json"], default=_json_default),
            admin_id,
            data["segment_id"],
            str(profile_id).strip().upper(),
            str(profile_id).strip(),
        ),
    )
    return _get_profile(cur, segment_id, data["code"])


def _soft_delete_profile(cur, segment_id, profile_id, admin_id):
    before = _get_profile(cur, segment_id, profile_id)
    if not before:
        return None
    cur.execute(
        """
        UPDATE profiles
        SET status = 'deleted', is_deleted = TRUE, deleted_at = NOW(),
            updated_by = %s, updated_at = NOW()
        WHERE segment_id = %s
          AND (code = %s OR CAST(id AS TEXT) = %s)
          AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (
            admin_id,
            str(segment_id).strip().upper(),
            str(profile_id).strip().upper(),
            str(profile_id).strip(),
        ),
    )
    return before


def _import_profiles(cur, segment_id, rows, admin_id):
    if not _get_segment(cur, segment_id):
        raise ValueError("segment_not_found")
    added = updated = skipped = 0
    output = []
    for row in rows or []:
        try:
            payload = {**dict(row), "segment_id": segment_id}
            data = _profile_payload(payload, segment_id)
            existing = _get_profile(cur, segment_id, data["id"])
            if existing:
                output.append(_update_profile(cur, segment_id, data["id"], data, admin_id))
                updated += 1
            else:
                output.append(_create_profile(cur, segment_id, data, admin_id))
                added += 1
        except ValueError:
            skipped += 1
    return {"added": added, "updated": updated, "skipped": skipped, "rows": output}


def _write_segment_generation_log(cur, admin_id, payload, result):
    cur.execute(
        """
        INSERT INTO segment_generation_logs
            (id, brand_id, brand_name, industry_id, llm_model, prompt_used,
             input_params, output_json, segments_generated, segments_skipped,
             tokens_used, estimated_cost, created_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, NOW())
        """,
        (
            str(uuid.uuid4()),
            payload.get("brand_id"),
            payload.get("brand_name") or payload.get("brand"),
            payload.get("industry_id"),
            result.model,
            result.prompt,
            json.dumps(payload, default=_json_default),
            json.dumps(result.items, default=_json_default),
            len(result.items),
            0,
            int((result.usage or {}).get("total_tokens") or 0),
            result.estimated_cost,
            admin_id,
        ),
    )


def _write_profile_generation_log(cur, admin_id, segment_id, payload, result):
    cur.execute(
        """
        INSERT INTO profile_generation_logs
            (id, segment_id, llm_model, prompt_used, input_params, output_json,
             profiles_generated, profiles_skipped, tokens_used, estimated_cost,
             created_by, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, NOW())
        """,
        (
            str(uuid.uuid4()),
            str(segment_id).strip().upper(),
            result.model,
            result.prompt,
            json.dumps(payload, default=_json_default),
            json.dumps(result.items, default=_json_default),
            len(result.items),
            0,
            int((result.usage or {}).get("total_tokens") or 0),
            result.estimated_cost,
            admin_id,
        ),
    )


def _segment_profile_generation_status(error):
    return 503 if error.code in {"llm_config_missing", "llm_client_unavailable", "llm_call_failed"} else 502


@app.route('/api/segments')
def admin_segments_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    page = _clamp_int(request.args.get("page"), 1, 1, 100000)
    per_page = _clamp_int(request.args.get("per_page"), 50, 1, 200)
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows, total, summary = _fetch_segments(
                cur,
                page=page,
                per_page=per_page,
                q=request.args.get("q"),
                status=request.args.get("status"),
                industry_id=request.args.get("industry_id"),
            )
        return jsonify({"success": True, "rows": rows, "pagination": _pagination(page, per_page, total), "summary": summary})
    finally:
        conn.close()


@app.route('/api/segments', methods=['POST'])
def admin_segment_create_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                row = _create_segment(cur, payload, admin["id"])
            except ValueError as error:
                conn.rollback()
                return jsonify({"success": False, "error": str(error)}), 400
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="create_segment",
                target_type="segment",
                target_id=row["id"],
                diff={"after": row},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True, "segment": row}), 201
    finally:
        conn.close()


@app.route('/api/segments/import', methods=['POST'])
def admin_segments_import_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows") or payload.get("segments") or []
    if not isinstance(rows, list):
        return jsonify({"success": False, "error": "rows_must_be_array"}), 400
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                result = _import_segments(cur, rows, admin["id"])
            except Exception as error:
                conn.rollback()
                app.logger.exception("Segment import failed: %s", error)
                return jsonify(
                    {
                        "success": False,
                        "error": "segment_import_failed",
                        "message": "Segment import failed. Please check generated draft fields and database schema.",
                    }
                ), 500
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="import_segments",
                target_type="segment",
                target_id=None,
                diff={"summary": {k: result[k] for k in ("added", "updated", "skipped")}},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True, **result})
    finally:
        conn.close()


@app.route('/api/segments/generate', methods=['POST'])
def admin_segments_generate_api():
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    brand_name = (payload.get("brand_name") or payload.get("brand") or "").strip()
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name_required"}), 400
    service = SegmentProfileGenerationService(model=payload.get("llm_model"))
    try:
        result = service.generate_segments(
            brand_name=brand_name,
            industry=(payload.get("industry") or payload.get("industry_id") or "").strip(),
            count=_clamp_int(payload.get("count"), 6, 1, 20),
            status=(payload.get("status") or "draft").strip().lower(),
            positioning=payload.get("positioning") or "",
            goal=payload.get("goal") or "",
            constraints=payload.get("constraints") or "",
        )
    except SegmentProfileGenerationError as error:
        return jsonify({"success": False, "error": error.code, "message": error.message}), _segment_profile_generation_status(error)
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _write_segment_generation_log(cur, admin["id"], payload, result)
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="generate_segments",
                target_type="segment",
                target_id=None,
                diff={"count": len(result.items), "model": result.model},
                reason=payload.get("reason"),
            )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"success": True, "drafts": result.items, "model": result.model, "usage": result.usage})


@app.route('/api/segments/<segment_id>')
def admin_segment_detail_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            row = _get_segment(cur, segment_id)
        if not row:
            return jsonify({"success": False, "error": "segment_not_found"}), 404
        return jsonify({"success": True, "segment": row})
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>', methods=['PUT'])
def admin_segment_update_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            before = _get_segment(cur, segment_id)
            if not before:
                conn.rollback()
                return jsonify({"success": False, "error": "segment_not_found"}), 404
            try:
                row = _update_segment(cur, segment_id, payload, admin["id"])
            except ValueError as error:
                conn.rollback()
                return jsonify({"success": False, "error": str(error)}), 400
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="update_segment",
                target_type="segment",
                target_id=segment_id,
                diff={"before": before, "after": row},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True, "segment": row})
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>', methods=['DELETE'])
def admin_segment_delete_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            before = _soft_delete_segment(cur, segment_id, admin["id"])
            if not before:
                conn.rollback()
                return jsonify({"success": False, "error": "segment_not_found"}), 404
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="delete_segment",
                target_type="segment",
                target_id=segment_id,
                diff={"before": before, "after": {"is_deleted": True, "status": "deleted"}},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>/profiles')
def admin_segment_profiles_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    page = _clamp_int(request.args.get("page"), 1, 1, 100000)
    per_page = _clamp_int(request.args.get("per_page"), 100, 1, 500)
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            segment = _get_segment(cur, segment_id)
            if not segment:
                return jsonify({"success": False, "error": "segment_not_found"}), 404
            rows, total = _fetch_profiles(
                cur,
                segment_id,
                page=page,
                per_page=per_page,
                q=request.args.get("q"),
                status=request.args.get("status"),
            )
        return jsonify({"success": True, "segment": segment, "rows": rows, "pagination": _pagination(page, per_page, total)})
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>/profiles', methods=['POST'])
def admin_segment_profile_create_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                row = _create_profile(cur, segment_id, payload, admin["id"])
            except ValueError as error:
                conn.rollback()
                status_code = 404 if str(error) == "segment_not_found" else 400
                return jsonify({"success": False, "error": str(error)}), status_code
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="create_profile",
                target_type="profile",
                target_id=row["id"],
                diff={"after": row},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True, "profile": row}), 201
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>/profiles/import', methods=['POST'])
def admin_segment_profiles_import_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows") or payload.get("profiles") or []
    if not isinstance(rows, list):
        return jsonify({"success": False, "error": "rows_must_be_array"}), 400
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                result = _import_profiles(cur, segment_id, rows, admin["id"])
            except ValueError as error:
                conn.rollback()
                return jsonify({"success": False, "error": str(error)}), 404
            except Exception as error:
                conn.rollback()
                app.logger.exception("Profile import failed: %s", error)
                return jsonify(
                    {
                        "success": False,
                        "error": "profile_import_failed",
                        "message": "Profile import failed. Please check generated draft fields and database schema.",
                    }
                ), 500
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="import_profiles",
                target_type="segment",
                target_id=segment_id,
                diff={"summary": {k: result[k] for k in ("added", "updated", "skipped")}},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True, **result})
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>/profiles/export')
def admin_segment_profiles_export_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor
    import csv
    import io

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            segment = _get_segment(cur, segment_id)
            if not segment:
                return jsonify({"success": False, "error": "segment_not_found"}), 404
            rows, _total = _fetch_profiles(cur, segment_id, page=1, per_page=100000)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "segment_id", "name", "demographic", "need", "weight", "status"])
        for profile in rows:
            writer.writerow([
                profile["id"],
                segment["id"],
                profile["name"],
                profile["demographic"],
                profile["need"],
                profile["weight"],
                profile["status"],
            ])
        filename = f"{segment['id']}-profiles.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>/profiles/generate', methods=['POST'])
def admin_segment_profiles_generate_api(segment_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    brand_name = (payload.get("brand_name") or payload.get("brand") or "").strip()
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name_required"}), 400
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            segment = _get_segment(cur, segment_id)
            if not segment:
                return jsonify({"success": False, "error": "segment_not_found"}), 404
            service = SegmentProfileGenerationService(model=payload.get("llm_model"))
            try:
                result = service.generate_profiles(
                    segment=segment,
                    brand_name=brand_name,
                    count=_clamp_int(payload.get("count"), 6, 1, 50),
                    goal=payload.get("goal") or "",
                    constraints=payload.get("constraints") or payload.get("notes") or "",
                )
            except SegmentProfileGenerationError as error:
                conn.rollback()
                return jsonify({"success": False, "error": error.code, "message": error.message}), _segment_profile_generation_status(error)
            _write_profile_generation_log(cur, admin["id"], segment_id, payload, result)
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="generate_profiles",
                target_type="segment",
                target_id=segment_id,
                diff={"count": len(result.items), "model": result.model},
                reason=payload.get("reason"),
            )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"success": True, "drafts": result.items, "model": result.model, "usage": result.usage})


@app.route('/api/segments/<segment_id>/profiles/<profile_id>', methods=['PUT'])
def admin_segment_profile_update_api(segment_id, profile_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            before = _get_profile(cur, segment_id, profile_id)
            if not before:
                conn.rollback()
                return jsonify({"success": False, "error": "profile_not_found"}), 404
            try:
                row = _update_profile(cur, segment_id, profile_id, payload, admin["id"])
            except ValueError as error:
                conn.rollback()
                status_code = 404 if str(error) == "segment_not_found" else 400
                return jsonify({"success": False, "error": str(error)}), status_code
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="update_profile",
                target_type="profile",
                target_id=profile_id,
                diff={"before": before, "after": row},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True, "profile": row})
    finally:
        conn.close()


@app.route('/api/segments/<segment_id>/profiles/<profile_id>', methods=['DELETE'])
def admin_segment_profile_delete_api(segment_id, profile_id):
    admin, error_response = _require_admin()
    if error_response:
        return error_response
    from psycopg2.extras import RealDictCursor

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            before = _soft_delete_profile(cur, segment_id, profile_id, admin["id"])
            if not before:
                conn.rollback()
                return jsonify({"success": False, "error": "profile_not_found"}), 404
            _insert_admin_audit_log(
                cur,
                operator_id=admin["id"],
                action="delete_profile",
                target_type="profile",
                target_id=profile_id,
                diff={"before": before, "after": {"is_deleted": True, "status": "deleted"}},
                reason=payload.get("reason"),
            )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


# ─── Segments API ─────────────────────────────────────────────────────────────

@app.route('/api/segments')
def list_segments():
    """列出所有 Segment 定义（优先从 Python 代码，失败则从 DB profiles 提取）"""
    # 尝试从 Python 定义导入
    try:
        from geo_tracker.generation.segments.definitions import SEGMENTS
        result = []
        for seg in SEGMENTS:
            result.append({
                'id': seg.id,
                'name': seg.name,
                'description': seg.description,
                'language': seg.language,
                'target_llms': seg.target_llms,
                'tone_pool': list(seg.tone_pool),
                'verbosity_pool': list(seg.verbosity_pool),
                'search_style_pool': list(seg.search_style_pool),
                'add_role_context_rate': seg.add_role_context_rate,
                'device_mobile_rate': seg.device_mobile_rate,
                'city_tiers': seg.city_tiers,
                'age_ranges': [
                    {'label': a.label, 'min_age': a.min_age, 'max_age': a.max_age}
                    for a in seg.age_ranges
                ],
                'role_variants': [
                    {
                        'label': rv.label,
                        'profession': rv.profession,
                        'company_size': rv.company_size,
                        'income_level': rv.income_level,
                        'pain_points': rv.pain_points,
                        'use_buzzwords': rv.use_buzzwords,
                    }
                    for rv in seg.role_variants
                ],
            })
        return jsonify(result)
    except ImportError:
        pass  # Fall through to DB extraction

    # 从数据库 profiles 的 persona_traits 中提取 segment 信息
    try:
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT DISTINCT
                        persona_traits->>'segment_id' AS id,
                        persona_traits->>'segment_name' AS name,
                        persona_traits->'target_llms' AS target_llms
                    FROM profiles
                    WHERE persona_traits->>'segment_id' IS NOT NULL
                    ORDER BY persona_traits->>'segment_id'
                """)
                seg_rows = cur.fetchall()

                if not seg_rows:
                    return jsonify([])

                # 对每个 segment 聚合 profile 信息
                segments = []
                for seg_row in seg_rows:
                    seg_id = seg_row['id']
                    cur.execute("""
                        SELECT
                            COUNT(*) AS profile_count,
                            array_agg(DISTINCT profession) AS professions,
                            array_agg(DISTINCT age_range) AS age_ranges,
                            array_agg(DISTINCT location) AS locations,
                            array_agg(DISTINCT country_code) AS countries,
                            array_agg(DISTINCT language) AS languages,
                            array_agg(DISTINCT device_type) AS device_types,
                            array_agg(DISTINCT persona_traits->>'tone') AS tones,
                            array_agg(DISTINCT persona_traits->>'verbosity') AS verbosities,
                            array_agg(DISTINCT persona_traits->>'search_style') AS search_styles
                        FROM profiles
                        WHERE persona_traits->>'segment_id' = %s
                    """, (seg_id,))
                    agg = cur.fetchone()

                    import json as json_mod
                    target_llms = seg_row['target_llms']
                    if isinstance(target_llms, str):
                        target_llms = json_mod.loads(target_llms)

                    segments.append({
                        'id': seg_id,
                        'name': seg_row['name'] or seg_id,
                        'description': f"从数据库提取 - {agg['profile_count']} 个 profiles",
                        'language': (agg['languages'] or ['zh'])[0] if agg['languages'] else 'zh',
                        'target_llms': target_llms or [],
                        'tone_pool': [t for t in (agg['tones'] or []) if t],
                        'verbosity_pool': [v for v in (agg['verbosities'] or []) if v],
                        'search_style_pool': [s for s in (agg['search_styles'] or []) if s],
                        'add_role_context_rate': 0,
                        'device_mobile_rate': 0,
                        'city_tiers': [],
                        'age_ranges': [
                            {'label': ar, 'min_age': int(ar.split('-')[0]) if '-' in ar else 0,
                             'max_age': int(ar.split('-')[1]) if '-' in ar else 0}
                            for ar in (agg['age_ranges'] or []) if ar and '-' in ar
                        ],
                        'role_variants': [
                            {'label': p, 'profession': p, 'company_size': '', 'income_level': '',
                             'pain_points': [], 'use_buzzwords': False}
                            for p in (agg['professions'] or []) if p
                        ],
                        'profile_count': agg['profile_count'],
                    })

                return jsonify(segments)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── Profiles API ────────────────────────────────────────────────────────────

@app.route('/api/profiles')
def list_profiles():
    """列出所有 Profile"""
    try:
        import json as json_mod
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Use subquery for query_count to avoid GROUP BY issues with JSON
                cur.execute("""
                    SELECT p.id, p.name, p.age_range, p.location, p.country_code,
                           p.profession, p.language, p.device_type, p.persona_traits,
                           COALESCE(qc.cnt, 0) AS query_count
                    FROM profiles p
                    LEFT JOIN (
                        SELECT profile_id, COUNT(*) AS cnt
                        FROM queries
                        GROUP BY profile_id
                    ) qc ON p.id = qc.profile_id
                    ORDER BY p.id
                """)
                rows = cur.fetchall()

            result = []
            for r in rows:
                row = dict(r)
                # Ensure persona_traits is a proper dict for JSON serialization
                if row.get('persona_traits') and isinstance(row['persona_traits'], str):
                    try:
                        row['persona_traits'] = json_mod.loads(row['persona_traits'])
                    except (json_mod.JSONDecodeError, TypeError):
                        row['persona_traits'] = {}
                elif not row.get('persona_traits'):
                    row['persona_traits'] = {}
                result.append(row)

            return jsonify(result)
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/profiles', methods=['POST'])
def create_profile():
    """创建新 Profile"""
    try:
        import json as json_mod
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'})

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO profiles (name, age_range, location, country_code,
                                         profession, language, device_type, persona_traits)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    name,
                    data.get('age_range', ''),
                    data.get('location', ''),
                    data.get('country_code', ''),
                    data.get('profession', ''),
                    data.get('language', 'zh'),
                    data.get('device_type', 'desktop'),
                    json_mod.dumps(data.get('persona_traits', {})),
                ))
                profile_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({'success': True, 'profile_id': profile_id})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/profiles/<int:profile_id>', methods=['PUT'])
def update_profile(profile_id):
    """更新 Profile"""
    try:
        import json as json_mod
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'})

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE profiles
                    SET name = %s, age_range = %s, location = %s, country_code = %s,
                        profession = %s, language = %s, device_type = %s, persona_traits = %s
                    WHERE id = %s
                """, (
                    name,
                    data.get('age_range', ''),
                    data.get('location', ''),
                    data.get('country_code', ''),
                    data.get('profession', ''),
                    data.get('language', 'zh'),
                    data.get('device_type', 'desktop'),
                    json_mod.dumps(data.get('persona_traits', {})),
                    profile_id,
                ))
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Profile not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/profiles/<int:profile_id>', methods=['DELETE'])
def delete_profile(profile_id):
    """删除 Profile"""
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # Check if profile has associated queries
                cur.execute("SELECT COUNT(*) FROM queries WHERE profile_id = %s", (profile_id,))
                query_count = cur.fetchone()[0]
                if query_count > 0:
                    # Nullify profile_id in queries rather than blocking delete
                    cur.execute("UPDATE queries SET profile_id = NULL WHERE profile_id = %s", (profile_id,))

                # Delete associated browser profile first
                cur.execute("DELETE FROM browser_profiles WHERE profile_id = %s", (profile_id,))

                # Nullify profile_id in llm_accounts
                cur.execute("UPDATE llm_accounts SET profile_id = NULL WHERE profile_id = %s", (profile_id,))

                cur.execute("DELETE FROM profiles WHERE id = %s", (profile_id,))
                if cur.rowcount == 0:
                    return jsonify({'success': False, 'error': 'Profile not found'})
            conn.commit()
            return jsonify({'success': True})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



# Old ANALYZER_TEMPLATE and /analyzer route removed -- merged into main page as tabs


@app.route('/api/analyzer/stats')
def analyzer_stats():
    conn = get_db()
    try:
        from psycopg2.extras import RealDictCursor
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE analysis_status = 'done') AS done,
                    COUNT(*) FILTER (WHERE analysis_status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE analysis_status = 'running') AS running,
                    COUNT(*) FILTER (WHERE analysis_status = 'failed') AS failed
                FROM llm_responses
            """)
            row = cur.fetchone()

            avg_geo = None
            try:
                cur.execute("SELECT AVG(geo_score) FROM response_analyses WHERE geo_score > 0")
                r = cur.fetchone()
                if r and r['avg'] is not None:
                    avg_geo = float(r['avg'])
            except Exception:
                pass

            brands = 0
            try:
                cur.execute("SELECT COUNT(*) FROM brands")
                brands = cur.fetchone()['count']
            except Exception:
                pass

        return jsonify({
            'total': row['total'],
            'done': row['done'],
            'pending': row['pending'],
            'running': row['running'],
            'failed': row['failed'],
            'avg_geo_score': avg_geo,
            'total_brands_tracked': brands,
        })
    finally:
        conn.close()


@app.route('/api/analyzer/brands')
def analyzer_brands():
    conn = get_db()
    try:
        from psycopg2.extras import RealDictCursor
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, name FROM brands ORDER BY name")
            return jsonify(cur.fetchall())
    finally:
        conn.close()


@app.route('/api/topics')
def list_topics():
    """Topics filtered by brand_id (optional). Used by the attempt-tracker
    filter dropdown, which cascades from the brand selector."""
    brand_id = request.args.get('brand_id')
    conn = get_db()
    try:
        from psycopg2.extras import RealDictCursor
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if brand_id:
                cur.execute(
                    "SELECT id, brand_id, text, category FROM topics "
                    "WHERE brand_id = %s ORDER BY id",
                    (int(brand_id),),
                )
            else:
                cur.execute(
                    "SELECT id, brand_id, text, category FROM topics ORDER BY brand_id, id"
                )
            return jsonify(cur.fetchall())
    finally:
        conn.close()


@app.route('/api/prompts')
def list_prompts():
    """Prompts filtered by brand_id and/or topic_id. Used by the attempt
    tracker's searchable prompt picker — client filters in-memory by text."""
    brand_id = request.args.get('brand_id')
    topic_id = request.args.get('topic_id')
    conn = get_db()
    try:
        from psycopg2.extras import RealDictCursor
        where = []
        params = []
        if brand_id:
            where.append("t.brand_id = %s")
            params.append(int(brand_id))
        if topic_id:
            where.append("pr.topic_id = %s")
            params.append(int(topic_id))
        where_clause = " AND ".join(where) if where else "1=1"
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""SELECT pr.id, pr.topic_id, pr.text, t.text AS topic_text
                    FROM prompts pr
                    LEFT JOIN topics t ON pr.topic_id = t.id
                    WHERE {where_clause}
                    ORDER BY pr.topic_id, pr.id""",
                params,
            )
            return jsonify(cur.fetchall())
    finally:
        conn.close()


@app.route('/api/analyzer/llms')
def analyzer_llms():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT target_llm FROM queries WHERE target_llm IS NOT NULL ORDER BY target_llm")
            return jsonify([r[0] for r in cur.fetchall()])
    finally:
        conn.close()


@app.route('/api/analyzer/responses')
def analyzer_responses():
    from psycopg2.extras import RealDictCursor
    status = request.args.get('status')
    brand_id = request.args.get('brand_id')
    llm = request.args.get('llm')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    limit = min(int(request.args.get('limit', 30)), 100)
    offset = int(request.args.get('offset', 0))

    conn = get_db()
    try:
        where = []
        params = []

        if status:
            where.append("lr.analysis_status = %s")
            params.append(status)
        if brand_id:
            where.append("q.brand_id = %s")
            params.append(int(brand_id))
        if llm:
            where.append("q.target_llm = %s")
            params.append(llm)
        if date_from:
            where.append("lr.collected_at::date >= %s")
            params.append(date_from)
        if date_to:
            where.append("lr.collected_at::date <= %s")
            params.append(date_to)

        where_clause = ("WHERE " + " AND ".join(where)) if where else ""

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT lr.id AS response_id, lr.analysis_status, lr.collected_at,
                       q.target_llm, b.name AS brand_name,
                       ra.geo_score, ra.visibility_score, ra.sentiment_score,
                       ra.sov_score, ra.citation_score,
                       ra.total_brands_mentioned, ra.target_brand_mentioned,
                       ra.target_brand_sentiment
                FROM llm_responses lr
                JOIN queries q ON q.id = lr.query_id
                LEFT JOIN brands b ON b.id = q.brand_id
                LEFT JOIN response_analyses ra ON ra.response_id = lr.id
                {where_clause}
                ORDER BY lr.id DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            rows = cur.fetchall()

        # Convert datetime to string for JSON
        for r in rows:
            if r.get('collected_at'):
                r['collected_at'] = r['collected_at'].isoformat()

        return jsonify(rows)
    finally:
        conn.close()


@app.route('/api/analyzer/response/<int:response_id>')
def analyzer_response_detail(response_id):
    from psycopg2.extras import RealDictCursor
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Analysis summary
            cur.execute("""
                SELECT * FROM response_analyses WHERE response_id = %s
            """, (response_id,))
            analysis = cur.fetchone()

            # Always fetch raw response data
            cur.execute("""
                SELECT lr.raw_text, lr.analysis_status, lr.collected_at,
                       q.query_text, q.target_llm, b.name AS brand_name
                FROM llm_responses lr
                JOIN queries q ON q.id = lr.query_id
                LEFT JOIN brands b ON b.id = q.brand_id
                WHERE lr.id = %s
            """, (response_id,))
            raw_resp = cur.fetchone()

            if not analysis:
                if not raw_resp:
                    return jsonify({'error': 'Response not found'})
                result = dict(raw_resp)
                if result.get('collected_at'):
                    result['collected_at'] = result['collected_at'].isoformat()
                if result.get('raw_text') and len(result['raw_text']) > 3000:
                    result['raw_text'] = result['raw_text'][:3000]
                result['no_analysis'] = True
                result['mentions'] = []
                result['citations'] = []
                result['features'] = []
                return jsonify(result)

            # Brand mentions + drivers
            cur.execute("""
                SELECT * FROM brand_mentions WHERE response_id = %s ORDER BY is_target DESC, mention_count DESC
            """, (response_id,))
            mentions = cur.fetchall()

            for m in mentions:
                cur.execute("""
                    SELECT driver_text, polarity, category, strength, source_quote
                    FROM sentiment_drivers WHERE mention_id = %s ORDER BY strength DESC
                """, (m['id'],))
                m['drivers'] = cur.fetchall()
                if m.get('created_at'):
                    m['created_at'] = m['created_at'].isoformat()

            # Citations
            cur.execute("""
                SELECT url, domain, title, citation_index, source_type
                FROM citation_sources WHERE response_id = %s ORDER BY citation_index
            """, (response_id,))
            citations = cur.fetchall()

            # Product features
            cur.execute("""
                SELECT brand_name, product_name, feature_name, feature_sentiment,
                       context_snippet, scenario, price_positioning
                FROM product_feature_mentions WHERE analysis_id = %s
            """, (analysis['id'],))
            features = cur.fetchall()

        result = dict(analysis)
        if result.get('analyzed_at'):
            result['analyzed_at'] = result['analyzed_at'].isoformat()
        if result.get('created_at'):
            result['created_at'] = result['created_at'].isoformat()
        result['mentions'] = mentions
        result['citations'] = citations
        result['features'] = features
        if raw_resp:
            result['query_text'] = raw_resp.get('query_text')
            raw_text = raw_resp.get('raw_text')
            result['raw_text'] = raw_text[:3000] if raw_text and len(raw_text) > 3000 else raw_text
        return jsonify(result)
    finally:
        conn.close()


@app.route('/api/analyzer/daily')
def analyzer_daily():
    from psycopg2.extras import RealDictCursor
    brand_id = request.args.get('brand_id')
    llm = request.args.get('llm')
    days = min(int(request.args.get('days', 30)), 90)

    conn = get_db()
    try:
        where = ["gd.intent IS NULL", "gd.language IS NULL"]
        params = []

        if brand_id:
            where.append("gd.brand_id = %s")
            params.append(int(brand_id))
        if llm:
            where.append("gd.target_llm = %s")
            params.append(llm)
        else:
            where.append("gd.target_llm IS NULL")

        where.append("gd.date >= NOW() - INTERVAL '%s days'")
        params.append(days)

        where_clause = "WHERE " + " AND ".join(where)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT gd.*, b.name AS brand_name
                FROM geo_score_daily gd
                JOIN brands b ON b.id = gd.brand_id
                {where_clause}
                ORDER BY gd.date DESC, gd.avg_geo_score DESC
                LIMIT 200
            """, params)
            rows = cur.fetchall()

        for r in rows:
            if r.get('date'):
                r['date'] = r['date'].isoformat()
            if r.get('created_at'):
                r['created_at'] = r['created_at'].isoformat()
            if r.get('updated_at'):
                r['updated_at'] = r['updated_at'].isoformat()
        return jsonify(rows)
    finally:
        conn.close()


@app.route('/api/analyzer/trigger', methods=['POST'])
def analyzer_trigger():
    data = request.json or {}
    action = data.get('action', 'analyze')
    date_str = data.get('date')
    brand_id = data.get('brand_id')

    if not date_str:
        return jsonify({'success': False, 'error': 'date is required'})

    # Try Celery first
    if HAS_CELERY and celery_app:
        try:
            if action == 'analyze':
                task = celery_app.send_task(
                    'geo_tracker.tasks.celery_tasks.run_daily_analysis',
                    kwargs={'date_str': date_str, 'brand_id': brand_id},
                    queue='analysis',
                )
                return jsonify({'success': True, 'task_id': task.id, 'message': f'Analysis queued for {date_str}'})
            elif action == 'aggregate':
                task = celery_app.send_task(
                    'geo_tracker.tasks.celery_tasks.aggregate_daily_scores',
                    kwargs={'date_str': date_str, 'brand_id': brand_id},
                    queue='analysis',
                )
                return jsonify({'success': True, 'task_id': task.id, 'message': f'Aggregation queued for {date_str}'})
            elif action == 'reanalyze':
                # Reset status first
                conn = get_db()
                try:
                    with conn.cursor() as cur:
                        sql = """
                            UPDATE llm_responses SET analysis_status = 'pending'
                            WHERE collected_at::date = %s AND analysis_status IN ('done', 'failed')
                        """
                        cur.execute(sql, (date_str,))
                        reset_count = cur.rowcount
                    conn.commit()
                finally:
                    conn.close()
                # Then trigger analysis
                task = celery_app.send_task(
                    'geo_tracker.tasks.celery_tasks.run_daily_analysis',
                    kwargs={'date_str': date_str, 'brand_id': brand_id},
                    queue='analysis',
                )
                return jsonify({'success': True, 'task_id': task.id, 'message': f'Reset {reset_count} responses, analysis queued'})
        except Exception as e:
            return jsonify({'success': False, 'error': f'Celery error: {e}'})
    else:
        return jsonify({'success': False, 'error': 'Celery not available. Use CLI: python -m geo_tracker.analyzer.cli run-daily --date ' + date_str})


@app.route('/api/analyzer/rerun/<int:response_id>', methods=['POST'])
def analyzer_rerun_single(response_id):
    """Reset a single response to pending and queue analysis."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE llm_responses SET analysis_status = 'pending' WHERE id = %s",
                (response_id,),
            )
            if cur.rowcount == 0:
                return jsonify({'error': 'Response not found'})
        conn.commit()
    finally:
        conn.close()

    if HAS_CELERY and celery_app:
        try:
            task = celery_app.send_task(
                'geo_tracker.tasks.celery_tasks.analyze_response',
                args=[response_id],
                queue='analysis',
            )
            return jsonify({'success': True, 'task_id': task.id})
        except Exception as e:
            return jsonify({'error': f'Celery error: {e}'})
    else:
        return jsonify({'error': 'Celery not available'})


def _run_startup_migrations():
    _ensure_citations_column()
    _ensure_analyzer_tables()
    _ensure_preview_columns()
    _ensure_admin_tables()
    _ensure_topic_plan_tables()
    _ensure_prompt_matrix_tables()
    _ensure_segment_profile_tables()
    _normalize_query_data()


if os.getenv("ADMIN_CONSOLE_SKIP_STARTUP_MIGRATIONS") != "1" and "pytest" not in sys.modules:
    _run_startup_migrations()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        _configure_database_url(sys.argv[1])
    debug = os.getenv("ADMIN_CONSOLE_DEBUG", "0") == "1"
    app.run(host='0.0.0.0', port=5000, debug=debug, use_reloader=debug)
