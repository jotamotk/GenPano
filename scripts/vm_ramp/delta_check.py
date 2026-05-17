"""Operator quick-check for the VM-per-account ramp 3-gate indicator (Issue #1117).

Computes, for a given engine and time window, the same `Q-3GATE` indicator
defined in `docs/monitoring/vm_per_account_queries.md` §3, prints a single-screen
PASS / NO-GO verdict the operator can paste into the Epic #1110 EVIDENCE
comment. SSOT is the SQL query in monitoring doc; this script is a thin Python
wrapper that reuses `backend/app/db/session.py`'s async engine machinery so the
operator does not need a separate psql session.

Usage (run from repo root with the backend venv active):

    python scripts/vm_ramp/delta_check.py --engine doubao --window-hours 24
    python scripts/vm_ramp/delta_check.py --engine deepseek-CN --window-hours 24

Exits with code 0 if all 3 gates PASS, 1 if any gate fails NO-GO, 2 if
under-sampled (< 30/30), and 3 on input/connection errors. Operator should
treat exit 1 as "rollback per RUNBOOK §1.6" and exit 2 as "extend window".

Why this exists (vs the operator just running the SQL): the monitoring doc has
the SQL but the operator must (a) connect to read replica, (b) replace the
`engine_id IN (...)` filter, (c) eyeball the verdict column. This script makes
one engine's check a single command and returns an exit code so the operator
can chain it in a shell loop if needed (e.g. nightly cron during 30-day Step 6
observation).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy import text


# Allowed engine_id values per ADR-016 (ChatGPT not in ramp, kept out of allow-list)
ALLOWED_ENGINES = frozenset({"doubao", "deepseek-CN"})

# 3-gate thresholds per ADR-016 + ADAPTER_CONTRACT.md §10.4 (engine_health_5min
# success_rate denominator excludes NO_ACCOUNT_AVAILABLE / COOKIE_EXPIRED).
THRESHOLD_ERR_RATIO_MAX = 0.5
THRESHOLD_CAPTCHA_RATIO_REGRESSION = 1.0  # vm > local => regression
THRESHOLD_P95_RATIO_MAX = 1.5
MIN_SAMPLE_PER_SLICE = 30


# SQL is the same Q-3GATE query as in docs/monitoring/vm_per_account_queries.md §3,
# parameterised on engine_id + window_hours. Inlined so this script is runnable
# without a separate `.sql` file.
Q_3GATE_SQL = """
WITH attempt_unfold AS (
  SELECT
    r.engine_id,
    r.created_at,
    r.status,
    r.error_code,
    r.latency_ms,
    (att->>'execution_mode') AS exec_mode,
    (att->>'vm_id') AS vm_id
  FROM ai_responses r,
       LATERAL jsonb_array_elements(r.attempts) att
  WHERE r.engine_id = :engine_id
    AND r.created_at > NOW() - (:window_hours || ' hours')::interval
    AND (att->>'execution_mode') IN ('local_cookie', 'vm_session')
),
slice_metrics AS (
  SELECT
    engine_id,
    exec_mode,
    COUNT(*) AS sample_count,
    COUNT(*) FILTER (WHERE status <> 'SUCCESS'
                       AND error_code NOT IN ('NO_ACCOUNT_AVAILABLE', 'COOKIE_EXPIRED')) * 1.0
      / NULLIF(COUNT(*) FILTER (WHERE error_code NOT IN ('NO_ACCOUNT_AVAILABLE', 'COOKIE_EXPIRED')), 0)
      AS error_rate,
    COUNT(*) FILTER (WHERE error_code = 'CAPTCHA_REQUIRED') * 1.0 / NULLIF(COUNT(*), 0)
      AS captcha_rate,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)
      FILTER (WHERE status = 'SUCCESS') AS p95_latency_ms
  FROM attempt_unfold
  GROUP BY engine_id, exec_mode
)
SELECT
  engine_id,
  MAX(sample_count) FILTER (WHERE exec_mode = 'local_cookie') AS local_n,
  MAX(sample_count) FILTER (WHERE exec_mode = 'vm_session')   AS vm_n,
  MAX(error_rate)   FILTER (WHERE exec_mode = 'local_cookie') AS local_err,
  MAX(error_rate)   FILTER (WHERE exec_mode = 'vm_session')   AS vm_err,
  MAX(captcha_rate) FILTER (WHERE exec_mode = 'local_cookie') AS local_cap,
  MAX(captcha_rate) FILTER (WHERE exec_mode = 'vm_session')   AS vm_cap,
  MAX(p95_latency_ms) FILTER (WHERE exec_mode = 'local_cookie') AS local_p95,
  MAX(p95_latency_ms) FILTER (WHERE exec_mode = 'vm_session')   AS vm_p95
FROM slice_metrics
GROUP BY engine_id;
"""


@dataclass
class GateResult:
    """Container for a single engine's 3-gate computation output."""

    engine_id: str
    local_n: int
    vm_n: int
    local_err: float | None
    vm_err: float | None
    local_cap: float | None
    vm_cap: float | None
    local_p95: float | None
    vm_p95: float | None

    @property
    def err_ratio(self) -> float | None:
        if self.local_err in (None, 0) or self.vm_err is None:
            return None
        return self.vm_err / self.local_err

    @property
    def p95_ratio(self) -> float | None:
        if self.local_p95 in (None, 0) or self.vm_p95 is None:
            return None
        return self.vm_p95 / self.local_p95

    @property
    def under_sampled(self) -> bool:
        return self.local_n < MIN_SAMPLE_PER_SLICE or self.vm_n < MIN_SAMPLE_PER_SLICE

    def verdict(self) -> tuple[str, str]:
        """Return (verdict, reason) tuple. verdict in {PASS, NO-GO, UNDER-SAMPLE}."""
        if self.under_sampled:
            return (
                "UNDER-SAMPLE",
                f"need ≥ {MIN_SAMPLE_PER_SLICE}/{MIN_SAMPLE_PER_SLICE}, "
                f"got local={self.local_n}, vm={self.vm_n}",
            )
        # 0-baseline captcha case: any vm_session captcha is regression.
        if self.vm_cap is not None and (self.local_cap or 0) < self.vm_cap:
            return (
                "NO-GO",
                f"captcha regression: vm={self.vm_cap:.4f} > local={self.local_cap or 0:.4f}",
            )
        err_ratio = self.err_ratio
        if err_ratio is not None and err_ratio > THRESHOLD_ERR_RATIO_MAX:
            return (
                "NO-GO",
                f"error ratio: vm/local={err_ratio:.3f} > "
                f"threshold {THRESHOLD_ERR_RATIO_MAX}",
            )
        p95_ratio = self.p95_ratio
        if p95_ratio is not None and p95_ratio > THRESHOLD_P95_RATIO_MAX:
            return (
                "NO-GO",
                f"p95 latency ratio: vm/local={p95_ratio:.3f} > "
                f"threshold {THRESHOLD_P95_RATIO_MAX}",
            )
        return ("PASS", "all 3 gates green")


def _fmt(value: float | None, fmt: str = ".4f") -> str:
    if value is None:
        return "—"
    return f"{value:{fmt}}"


def render_report(result: GateResult, window_hours: int) -> str:
    """Render a single-screen text report the operator can paste into Epic #1110."""
    verdict, reason = result.verdict()
    lines = [
        f"=== VM ramp delta_check — engine={result.engine_id} window={window_hours}h ===",
        "",
        f"  Sample sizes:   local={result.local_n:>6}   vm={result.vm_n:>6}",
        f"  Error rate:     local={_fmt(result.local_err)}   vm={_fmt(result.vm_err)}   "
        f"ratio={_fmt(result.err_ratio, '.3f')} (threshold ≤ {THRESHOLD_ERR_RATIO_MAX})",
        f"  Captcha rate:   local={_fmt(result.local_cap)}   vm={_fmt(result.vm_cap)}   "
        f"(must not regress; vm ≤ local)",
        f"  P95 latency ms: local={_fmt(result.local_p95, '.0f')}   vm={_fmt(result.vm_p95, '.0f')}   "
        f"ratio={_fmt(result.p95_ratio, '.3f')} (threshold ≤ {THRESHOLD_P95_RATIO_MAX})",
        "",
        f"  Verdict: {verdict}",
        f"  Reason:  {reason}",
    ]
    return "\n".join(lines)


async def run_check(engine_id: str, window_hours: int) -> GateResult:
    """Open an async session, run Q_3GATE, return a GateResult."""
    # Import at call-time so a misconfigured DSN does not break `--help`.
    from app.db.session import AsyncSessionLocal  # type: ignore[import-not-found]

    async with AsyncSessionLocal() as session:
        row = (
            (
                await session.execute(
                    text(Q_3GATE_SQL),
                    {"engine_id": engine_id, "window_hours": str(window_hours)},
                )
            )
            .mappings()
            .first()
        )

    if row is None:
        # No rows means no attempts in the window for either slice.
        return GateResult(
            engine_id=engine_id,
            local_n=0,
            vm_n=0,
            local_err=None,
            vm_err=None,
            local_cap=None,
            vm_cap=None,
            local_p95=None,
            vm_p95=None,
        )

    return GateResult(
        engine_id=row["engine_id"],
        local_n=int(row["local_n"] or 0),
        vm_n=int(row["vm_n"] or 0),
        local_err=float(row["local_err"]) if row["local_err"] is not None else None,
        vm_err=float(row["vm_err"]) if row["vm_err"] is not None else None,
        local_cap=float(row["local_cap"]) if row["local_cap"] is not None else None,
        vm_cap=float(row["vm_cap"]) if row["vm_cap"] is not None else None,
        local_p95=float(row["local_p95"]) if row["local_p95"] is not None else None,
        vm_p95=float(row["vm_p95"]) if row["vm_p95"] is not None else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VM-per-account ramp 3-gate quick-check. See "
            "docs/RUNBOOK_vm_per_account_ramp.md §1.4 + "
            "docs/monitoring/vm_per_account_queries.md §3."
        ),
    )
    parser.add_argument(
        "--engine",
        required=True,
        choices=sorted(ALLOWED_ENGINES),
        help="Engine id (only the engines in the ramp scope are allowed).",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Window size in hours (default: 24, matches RUNBOOK §1.4 observation window).",
    )
    args = parser.parse_args(argv)

    if args.window_hours <= 0 or args.window_hours > 24 * 30:
        print(
            "ERROR: --window-hours must be between 1 and 720 (30 days)", file=sys.stderr
        )
        return 3

    try:
        result = asyncio.run(run_check(args.engine, args.window_hours))
    except Exception as exc:  # noqa: BLE001 — operator-facing diagnostic
        print(f"ERROR: query failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 3

    print(render_report(result, args.window_hours))
    verdict, _ = result.verdict()
    if verdict == "PASS":
        return 0
    if verdict == "UNDER-SAMPLE":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
