"""Read-only App analytics evidence helpers for issue #537.

This module has no repair/backfill path. It only emits SELECT probes and
performs authenticated GET requests for App analytics payload evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple

UUID_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
WRITE_SQL_RE = re.compile(
    r"\b("
    r"insert|alter|call|copy|create|delete|do|drop|execute|grant|merge|"
    r"refresh|reindex|replace|revoke|truncate|update|vacuum"
    r")\b",
    re.IGNORECASE,
)
RESPONSE_DATE_EXPR = "COALESCE(r.collected_at, q.finished_at, q.created_at)::date"


class EvidenceConfig(NamedTuple):
    project_id: str
    brand_id: int
    competitor_brand_ids: tuple[int, ...] = ()
    date_from: str = ""
    date_to: str = ""
    base_url: str = "http://116.62.36.173"
    timeout_seconds: int = 20


class ApiProbe(NamedTuple):
    name: str
    method: str
    path: str


def _require_uuid(value: str, name: str) -> str:
    if not UUID_RE.match(value):
        raise ValueError(f"{name} must be UUID-shaped, got {value!r}")
    return value


def _require_date(value: str, name: str) -> str:
    if value and not DATE_RE.match(value):
        raise ValueError(f"{name} must be YYYY-MM-DD, got {value!r}")
    return value


def _require_positive_int(value: int, name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return value


def _validate_config(config: EvidenceConfig) -> EvidenceConfig:
    _require_uuid(config.project_id, "project_id")
    _require_positive_int(config.brand_id, "brand_id")
    for brand_id in config.competitor_brand_ids:
        _require_positive_int(brand_id, "competitor_brand_ids")
    _require_date(config.date_from, "date_from")
    _require_date(config.date_to, "date_to")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    return config


def _int_array(values: tuple[int, ...]) -> str:
    if not values:
        return "ARRAY[]::int[]"
    return "ARRAY[" + ",".join(str(value) for value in values) + "]::int[]"


def _all_brand_array(config: EvidenceConfig) -> str:
    return _int_array((config.brand_id, *config.competitor_brand_ids))


def build_db_sql(config: EvidenceConfig) -> str:
    """Return a psql script containing SELECT-only evidence probes."""

    config = _validate_config(config)
    competitor_array = _int_array(config.competitor_brand_ids)
    all_brand_array = _all_brand_array(config)
    date_from = config.date_from or "1900-01-01"
    date_to = config.date_to or "2999-12-31"
    response_date_expr = RESPONSE_DATE_EXPR

    sql = f"""
\\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;

\\echo '--- readonly probe context ---'
SELECT
  NOW() AS captured_at,
  '{config.project_id}'::text AS project_id,
  {config.brand_id}::int AS brand_id,
  {competitor_array} AS competitor_brand_ids,
  '{date_from}'::date AS date_from,
  '{date_to}'::date AS date_to;

\\echo '--- project and competitor context ---'
SELECT
  p.id,
  p.user_id,
  p.name,
  p.industry_id,
  p.primary_brand_id,
  p.is_active,
  COUNT(pc.brand_id) AS competitor_count,
  COALESCE(STRING_AGG(pc.brand_id::text, ',' ORDER BY pc.brand_id), '') AS competitor_brand_ids
FROM projects p
LEFT JOIN project_competitors pc ON pc.project_id = p.id
WHERE p.id::text = '{config.project_id}'
   OR p.primary_brand_id = {config.brand_id}
   OR pc.brand_id = ANY({competitor_array})
GROUP BY p.id, p.user_id, p.name, p.industry_id, p.primary_brand_id, p.is_active
ORDER BY (p.id::text = '{config.project_id}') DESC, p.created_at DESC
LIMIT 25;

\\echo '--- response counts by engine/date ---'
WITH scoped_responses AS (
  SELECT
    r.id AS response_id,
    q.id AS query_id,
    COALESCE(q.target_llm, 'unknown') AS engine,
    {response_date_expr} AS response_date,
    q.brand_id AS query_brand_id,
    r.analysis_status
  FROM llm_responses r
  JOIN queries q ON q.id = r.query_id
  WHERE q.brand_id = ANY({all_brand_array})
    AND {response_date_expr}
      BETWEEN '{date_from}'::date AND '{date_to}'::date
)
SELECT
  response_date,
  engine,
  query_brand_id,
  COUNT(*) AS responses,
  COUNT(*) FILTER (WHERE analysis_status = 'done') AS done_responses,
  COUNT(*) FILTER (
    WHERE analysis_status IS NULL OR analysis_status <> 'done'
  ) AS not_done_responses
FROM scoped_responses
GROUP BY response_date, engine, query_brand_id
ORDER BY response_date, engine, query_brand_id;

\\echo '--- analyzer run/failure counts ---'
WITH scoped_responses AS (
  SELECT
    r.id AS response_id,
    COALESCE(q.target_llm, 'unknown') AS engine,
    {response_date_expr} AS response_date,
    r.analysis_status
  FROM llm_responses r
  JOIN queries q ON q.id = r.query_id
  WHERE q.brand_id = ANY({all_brand_array})
    AND {response_date_expr}
      BETWEEN '{date_from}'::date AND '{date_to}'::date
)
SELECT
  response_date,
  engine,
  COUNT(ra.id) AS analysis_rows,
  COUNT(DISTINCT ra.response_id) AS analyzed_responses,
  COUNT(*) FILTER (WHERE sr.analysis_status IN ('failed', 'error')) AS failed_response_statuses,
  COUNT(*) FILTER (WHERE ra.id IS NULL) AS missing_analysis_rows,
  MIN(ra.analyzed_at) AS first_analyzed_at,
  MAX(ra.analyzed_at) AS last_analyzed_at
FROM scoped_responses sr
LEFT JOIN response_analyses ra ON ra.response_id = sr.response_id
GROUP BY response_date, engine
ORDER BY response_date, engine;

\\echo '--- brand_mentions coverage ---'
WITH scoped_mentions AS (
  SELECT
    bm.id,
    bm.response_id,
    bm.brand_id,
    bm.brand_name,
    COALESCE(bm.mention_count, 1) AS mention_count
  FROM brand_mentions bm
  JOIN llm_responses r ON r.id = bm.response_id
  JOIN queries q ON q.id = r.query_id
  WHERE {response_date_expr}
    BETWEEN '{date_from}'::date AND '{date_to}'::date
)
SELECT
  CASE
    WHEN brand_id = {config.brand_id} THEN 'target'
    WHEN brand_id = ANY({competitor_array}) THEN 'configured_competitor'
    WHEN brand_id IS NULL THEN 'unresolved_brand'
    ELSE 'unconfigured_competitor'
  END AS coverage_bucket,
  brand_id,
  COALESCE(brand_name, '<unresolved>') AS brand_name,
  COUNT(*) AS rows,
  COUNT(DISTINCT response_id) AS responses,
  SUM(mention_count)::bigint AS mentions
FROM scoped_mentions
WHERE brand_id = {config.brand_id}
   OR brand_id = ANY({competitor_array})
   OR brand_id IS NULL
   OR brand_id <> ALL({all_brand_array})
GROUP BY coverage_bucket, brand_id, brand_name
ORDER BY coverage_bucket, rows DESC, responses DESC, brand_name
LIMIT 80;

\\echo '--- citation_sources and official domains ---'
WITH scoped_citations AS (
  SELECT
    cs.id,
    cs.response_id,
    cs.mention_id,
    cs.domain,
    cs.source_type,
    bm.brand_id,
    bm.brand_name
  FROM citation_sources cs
  LEFT JOIN brand_mentions bm ON bm.id = cs.mention_id
  LEFT JOIN llm_responses r ON r.id = cs.response_id
  LEFT JOIN queries q ON q.id = r.query_id
  WHERE {response_date_expr}
    BETWEEN '{date_from}'::date AND '{date_to}'::date
)
SELECT
  CASE
    WHEN sc.brand_id = {config.brand_id} THEN 'target'
    WHEN sc.brand_id = ANY({competitor_array}) THEN 'configured_competitor'
    WHEN sc.brand_id IS NULL THEN 'unresolved_brand'
    ELSE 'unconfigured_competitor'
  END AS coverage_bucket,
  sc.brand_id,
  COALESCE(sc.brand_name, '<unresolved>') AS brand_name,
  COUNT(*) AS citation_rows,
  COUNT(DISTINCT sc.response_id) AS cited_responses,
  COUNT(DISTINCT sc.domain) AS domains,
  COUNT(*) FILTER (WHERE bod.domain IS NOT NULL) AS official_domain_rows,
  COUNT(*) FILTER (
    WHERE COALESCE(sc.source_type, '') ILIKE 'official%'
  ) AS official_source_type_rows
FROM scoped_citations sc
LEFT JOIN brand_official_domains bod
  ON bod.brand_id = sc.brand_id
 AND LOWER(bod.domain) = LOWER(sc.domain)
GROUP BY coverage_bucket, sc.brand_id, sc.brand_name
ORDER BY coverage_bucket, citation_rows DESC, domains DESC
LIMIT 80;

\\echo '--- sentiment_drivers and brand-linked sentiment ---'
WITH scoped_mentions AS (
  SELECT
    bm.id,
    bm.response_id,
    bm.brand_id,
    bm.brand_name,
    bm.sentiment,
    bm.sentiment_score
  FROM brand_mentions bm
  JOIN llm_responses r ON r.id = bm.response_id
  JOIN queries q ON q.id = r.query_id
  WHERE {response_date_expr}
    BETWEEN '{date_from}'::date AND '{date_to}'::date
)
SELECT
  CASE
    WHEN sm.brand_id = {config.brand_id} THEN 'target'
    WHEN sm.brand_id = ANY({competitor_array}) THEN 'configured_competitor'
    WHEN sm.brand_id IS NULL THEN 'unresolved_brand'
    ELSE 'unconfigured_competitor'
  END AS coverage_bucket,
  sm.brand_id,
  COALESCE(sm.brand_name, '<unresolved>') AS brand_name,
  COUNT(*) AS mention_rows,
  COUNT(*) FILTER (
    WHERE sm.sentiment IS NOT NULL OR sm.sentiment_score IS NOT NULL
  ) AS sentiment_rows,
  COUNT(sd.id) AS driver_rows,
  COUNT(sd.id) FILTER (WHERE sd.polarity = 'positive') AS positive_drivers,
  COUNT(sd.id) FILTER (WHERE sd.polarity = 'negative') AS negative_drivers
FROM scoped_mentions sm
LEFT JOIN sentiment_drivers sd ON sd.mention_id = sm.id
GROUP BY coverage_bucket, sm.brand_id, sm.brand_name
ORDER BY coverage_bucket, mention_rows DESC, driver_rows DESC
LIMIT 80;

\\echo '--- topic -> prompt -> query -> response linkage ---'
SELECT
  COALESCE(t.brand_id, q.brand_id, bm.brand_id) AS scope_brand_id,
  COUNT(DISTINCT t.id) AS topics,
  COUNT(DISTINCT p.id) AS prompts,
  COUNT(DISTINCT q.id) AS queries,
  COUNT(DISTINCT r.id) AS responses,
  COUNT(DISTINCT ra.id) AS analysis_rows,
  COUNT(DISTINCT bm.id) AS brand_mention_rows,
  COUNT(DISTINCT cs.id) AS citation_rows
FROM topics t
LEFT JOIN prompts p ON p.topic_id = t.id
LEFT JOIN queries q ON q.prompt_id = p.id
LEFT JOIN llm_responses r ON r.query_id = q.id
LEFT JOIN response_analyses ra ON ra.response_id = r.id
LEFT JOIN brand_mentions bm ON bm.response_id = r.id
LEFT JOIN citation_sources cs ON cs.response_id = r.id
WHERE COALESCE(t.brand_id, q.brand_id, bm.brand_id) = ANY({all_brand_array})
  AND (
    r.id IS NULL
    OR {response_date_expr}
       BETWEEN '{date_from}'::date AND '{date_to}'::date
  )
GROUP BY scope_brand_id
ORDER BY responses DESC NULLS LAST, queries DESC NULLS LAST, scope_brand_id;

\\echo '--- daily score/component aggregate counts ---'
SELECT
  'geo_score_daily' AS table_name,
  brand_id,
  COUNT(*) AS rows,
  MIN(date::date) AS first_date,
  MAX(date::date) AS last_date,
  COALESCE(SUM(total_queries), 0)::bigint AS denominator_count,
  COALESCE(SUM(mention_count), 0)::bigint AS mention_count,
  ROUND(AVG(mention_rate)::numeric, 4) AS avg_mention_rate,
  COUNT(mention_rate) AS mention_rate_non_null_count,
  COUNT(*) FILTER (WHERE mention_rate IS NULL) AS mention_rate_null_count,
  ROUND(AVG(avg_visibility)::numeric, 4) AS avg_visibility_component,
  COUNT(avg_visibility) AS visibility_non_null_count,
  COUNT(*) FILTER (WHERE avg_visibility IS NULL) AS visibility_null_count,
  ROUND(AVG(avg_sentiment)::numeric, 4) AS avg_sentiment_component,
  COUNT(avg_sentiment) AS sentiment_non_null_count,
  COUNT(*) FILTER (WHERE avg_sentiment IS NULL) AS sentiment_null_count,
  ROUND(AVG(avg_sov_score)::numeric, 4) AS avg_sov_component,
  COUNT(avg_sov_score) AS sov_non_null_count,
  COUNT(*) FILTER (WHERE avg_sov_score IS NULL) AS sov_null_count,
  ROUND(AVG(avg_citation_score)::numeric, 4) AS avg_citation_component,
  COUNT(avg_citation_score) AS citation_non_null_count,
  COUNT(*) FILTER (WHERE avg_citation_score IS NULL) AS citation_null_count,
  ROUND(AVG(avg_geo_score)::numeric, 4) AS avg_geo_score,
  COUNT(avg_geo_score) AS geo_score_non_null_count,
  COUNT(*) FILTER (WHERE avg_geo_score IS NULL) AS geo_score_null_count
FROM geo_score_daily
WHERE brand_id = ANY({all_brand_array})
  AND date::date BETWEEN '{date_from}'::date AND '{date_to}'::date
GROUP BY brand_id
UNION ALL
SELECT
  'topic_score_daily' AS table_name,
  brand_id,
  COUNT(*) AS rows,
  MIN(date::date) AS first_date,
  MAX(date::date) AS last_date,
  COALESCE(SUM(total_responses), 0)::bigint AS denominator_count,
  COALESCE(SUM(mention_count), 0)::bigint AS mention_count,
  ROUND(AVG(mention_rate)::numeric, 4) AS avg_mention_rate,
  COUNT(mention_rate) AS mention_rate_non_null_count,
  COUNT(*) FILTER (WHERE mention_rate IS NULL) AS mention_rate_null_count,
  NULL::numeric AS avg_visibility_component,
  0::bigint AS visibility_non_null_count,
  COUNT(*) AS visibility_null_count,
  ROUND(AVG(avg_sentiment_score)::numeric, 4) AS avg_sentiment_component,
  COUNT(avg_sentiment_score) AS sentiment_non_null_count,
  COUNT(*) FILTER (WHERE avg_sentiment_score IS NULL) AS sentiment_null_count,
  NULL::numeric AS avg_sov_component,
  0::bigint AS sov_non_null_count,
  COUNT(*) AS sov_null_count,
  NULL::numeric AS avg_citation_component,
  0::bigint AS citation_non_null_count,
  COUNT(*) AS citation_null_count,
  ROUND(AVG(avg_geo_score)::numeric, 4) AS avg_geo_score,
  COUNT(avg_geo_score) AS geo_score_non_null_count,
  COUNT(*) FILTER (WHERE avg_geo_score IS NULL) AS geo_score_null_count
FROM topic_score_daily
WHERE brand_id = ANY({all_brand_array})
  AND date::date BETWEEN '{date_from}'::date AND '{date_to}'::date
GROUP BY brand_id
UNION ALL
SELECT
  'product_score_daily' AS table_name,
  brand_id,
  COUNT(*) AS rows,
  MIN(date::date) AS first_date,
  MAX(date::date) AS last_date,
  COALESCE(SUM(total_queries), 0)::bigint AS denominator_count,
  COALESCE(SUM(mention_count), 0)::bigint AS mention_count,
  ROUND(AVG(mention_rate)::numeric, 4) AS avg_mention_rate,
  COUNT(mention_rate) AS mention_rate_non_null_count,
  COUNT(*) FILTER (WHERE mention_rate IS NULL) AS mention_rate_null_count,
  NULL::numeric AS avg_visibility_component,
  0::bigint AS visibility_non_null_count,
  COUNT(*) AS visibility_null_count,
  ROUND(AVG(avg_sentiment_score)::numeric, 4) AS avg_sentiment_component,
  COUNT(avg_sentiment_score) AS sentiment_non_null_count,
  COUNT(*) FILTER (WHERE avg_sentiment_score IS NULL) AS sentiment_null_count,
  NULL::numeric AS avg_sov_component,
  0::bigint AS sov_non_null_count,
  COUNT(*) AS sov_null_count,
  NULL::numeric AS avg_citation_component,
  0::bigint AS citation_non_null_count,
  COUNT(*) AS citation_null_count,
  ROUND(AVG(avg_geo_score)::numeric, 4) AS avg_geo_score,
  COUNT(avg_geo_score) AS geo_score_non_null_count,
  COUNT(*) FILTER (WHERE avg_geo_score IS NULL) AS geo_score_null_count
FROM product_score_daily
WHERE brand_id = ANY({all_brand_array})
  AND date::date BETWEEN '{date_from}'::date AND '{date_to}'::date
GROUP BY brand_id
ORDER BY table_name, brand_id;

ROLLBACK;
""".strip()
    assert_read_only_sql(sql)
    return sql + "\n"


def assert_read_only_sql(sql: str) -> None:
    match = WRITE_SQL_RE.search(sql)
    if match:
        raise ValueError(f"write-capable SQL keyword is not allowed: {match.group(1)}")


def _query(base: dict[str, str | int | None]) -> str:
    clean = {key: value for key, value in base.items() if value not in (None, "")}
    return urllib.parse.urlencode(clean)


def build_api_probe_plan(config: EvidenceConfig) -> list[ApiProbe]:
    config = _validate_config(config)
    project = urllib.parse.quote(config.project_id, safe="")
    compare_with = ",".join(str(value) for value in config.competitor_brand_ids)
    common = {
        "brand_id": config.brand_id,
        "from": config.date_from,
        "to": config.date_to,
    }
    no_brand_common = {
        "from": config.date_from,
        "to": config.date_to,
    }
    metric_series = "mention_rate,sov,rank,sentiment,citation"
    metrics_query = _query({**common, "series": metric_series})
    trends_query = _query({**common, "metric": "geo_score"})
    heatmap_query = _query(
        {**no_brand_common, "metric": "mention_rate", "compare_with": compare_with}
    )
    sentiment_query = _query(no_brand_common)

    return [
        ApiProbe("overview", "GET", f"/api/v1/projects/{project}/overview?{_query(common)}"),
        ApiProbe(
            "metrics",
            "GET",
            f"/api/v1/projects/{project}/metrics?{metrics_query}",
        ),
        ApiProbe(
            "competitors_metrics",
            "GET",
            f"/api/v1/projects/{project}/competitors/metrics?{_query(common)}",
        ),
        ApiProbe(
            "pano_geo_trend",
            "GET",
            f"/api/v1/projects/{project}/competitors/trends?{trends_query}",
        ),
        ApiProbe(
            "topics_monitoring",
            "GET",
            f"/api/v1/projects/{project}/topics/monitoring?{_query(common)}",
        ),
        ApiProbe(
            "topic_heatmap",
            "GET",
            f"/api/v1/projects/{project}/topic-heatmap?{heatmap_query}",
        ),
        ApiProbe(
            "sentiment",
            "GET",
            f"/api/v1/projects/{project}/sentiment?{sentiment_query}",
        ),
        ApiProbe(
            "sentiment_by_engine",
            "GET",
            f"/api/v1/projects/{project}/sentiment/by-engine?{_query(no_brand_common)}",
        ),
        ApiProbe(
            "sentiment_trend_by_engine",
            "GET",
            f"/api/v1/projects/{project}/sentiment/trend-by-engine?{_query(no_brand_common)}",
        ),
        ApiProbe(
            "sentiment_topic_attribution",
            "GET",
            f"/api/v1/projects/{project}/sentiment/topic-attribution?{_query(no_brand_common)}",
        ),
        ApiProbe(
            "citations",
            "GET",
            f"/api/v1/projects/{project}/citations?{_query({**no_brand_common, 'page_size': 25})}",
        ),
        ApiProbe(
            "citations_authority_trend",
            "GET",
            f"/api/v1/projects/{project}/citations/authority-trend?{_query(no_brand_common)}",
        ),
        ApiProbe(
            "citations_composition",
            "GET",
            f"/api/v1/projects/{project}/citations/composition?{_query(no_brand_common)}",
        ),
        ApiProbe(
            "metrics_by_engine",
            "GET",
            f"/api/v1/projects/{project}/metrics/by-engine?{_query(no_brand_common)}",
        ),
        ApiProbe(
            "position_distribution",
            "GET",
            f"/api/v1/projects/{project}/position-distribution?{_query(no_brand_common)}",
        ),
    ]


def mask_secret(value: str, *, visible: int = 4) -> str:
    if not value:
        return "<empty>"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"


def missing_secret_report(env: dict[str, str]) -> str:
    missing = [name for name, value in env.items() if not value]
    if not missing:
        return "All configured secrets are present."
    return "Missing secret(s): " + ", ".join(missing)


def _summarize_json(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    summary: dict[str, object] = {}
    for key in ("state", "state_reason", "missing_inputs", "formula_status", "evidence_counts"):
        if key in payload:
            summary[key] = payload[key]
    if "kpi_cards" in payload and isinstance(payload["kpi_cards"], list):
        summary["kpi_cards_count"] = len(payload["kpi_cards"])
    if "series" in payload and isinstance(payload["series"], list):
        summary["series_count"] = len(payload["series"])
    if "items" in payload and isinstance(payload["items"], list):
        summary["items_count"] = len(payload["items"])
    if "rows" in payload and isinstance(payload["rows"], list):
        summary["rows_count"] = len(payload["rows"])
    if "points" in payload and isinstance(payload["points"], list):
        summary["points_count"] = len(payload["points"])
    return summary


def _body_snippet(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    return " ".join(text.split())[:600]


def run_api_probes(config: EvidenceConfig, bearer_token: str) -> int:
    config = _validate_config(config)
    if not bearer_token:
        print("BLOCKED: missing secret APP_ANALYTICS_BEARER_TOKEN")
        return 0

    base_url = config.base_url.rstrip("/")
    print(f"API probe token={mask_secret(bearer_token)}")
    failures = 0
    for probe in build_api_probe_plan(config):
        url = base_url + probe.path
        request = urllib.request.Request(
            url,
            method=probe.method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {bearer_token}",
            },
        )
        status = 0
        headers: dict[str, str] = {}
        body = b""
        error: str | None = None
        try:
            with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
                status = response.status
                headers = dict(response.headers.items())
                body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            headers = dict(exc.headers.items())
            body = exc.read()
        except urllib.error.URLError as exc:
            failures += 1
            error = f"{type(exc.reason).__name__}: {exc.reason}"

        request_id = (
            headers.get("X-Request-ID")
            or headers.get("x-request-id")
            or headers.get("Request-ID")
            or ""
        )
        payload_summary: dict[str, object] = {}
        try:
            payload_summary = _summarize_json(json.loads(body.decode("utf-8"))) if body else {}
        except json.JSONDecodeError:
            payload_summary = {}

        row = {
            "probe": probe.name,
            "method": probe.method,
            "url": url,
            "status": status,
            "request_id": request_id,
            "body_sha256": hashlib.sha256(body).hexdigest() if body else "",
            "summary": payload_summary,
            "body_snippet": _body_snippet(body),
        }
        if error:
            row["error"] = error
        if status >= 500:
            failures += 1
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 1 if failures else 0


def _parse_competitors(value: str) -> tuple[int, ...]:
    if not value.strip():
        return ()
    out: list[int] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        out.append(_require_positive_int(int(item), "competitor_brand_ids"))
    return tuple(out)


def _config_from_args(args: argparse.Namespace) -> EvidenceConfig:
    return EvidenceConfig(
        project_id=args.project_id,
        brand_id=int(args.brand_id),
        competitor_brand_ids=_parse_competitors(args.competitor_brand_ids),
        date_from=args.date_from,
        date_to=args.date_to,
        base_url=args.base_url,
        timeout_seconds=int(args.timeout_seconds),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue #537 read-only App analytics evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--project-id", required=True)
        subparser.add_argument("--brand-id", required=True, type=int)
        subparser.add_argument("--competitor-brand-ids", default="")
        subparser.add_argument("--date-from", default="")
        subparser.add_argument("--date-to", default="")
        subparser.add_argument("--base-url", default="http://116.62.36.173")
        subparser.add_argument("--timeout-seconds", type=int, default=20)

    db_sql = subparsers.add_parser("db-sql", help="Emit SELECT-only SQL for psql")
    add_common(db_sql)

    api_probes = subparsers.add_parser("api-probes", help="Run authenticated GET probes")
    add_common(api_probes)
    api_probes.add_argument("--bearer-token-env", default="APP_ANALYTICS_BEARER_TOKEN")

    secrets = subparsers.add_parser("secrets-report", help="Report missing named env vars")
    secrets.add_argument("names", nargs="+")

    args = parser.parse_args(argv)

    if args.command == "db-sql":
        print(build_db_sql(_config_from_args(args)), end="")
        return 0
    if args.command == "api-probes":
        token = os.environ.get(args.bearer_token_env, "")
        return run_api_probes(_config_from_args(args), token)
    if args.command == "secrets-report":
        print(missing_secret_report({name: os.environ.get(name, "") for name in args.names}))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
