"""
将 Doubao 账号从 cooldown / expired / banned 重置回 active。

只对仍持有 cookies 的账号生效。cookies 已删除的账号需要重新导入
（参考 scripts/import_cookies.py），不在本脚本职责范围。

用法:
    # 列出 cooldown 状态的账号 (默认 dry-run, 不写库)
    python scripts/reset_doubao_accounts.py

    # 列出全部非 active 账号
    python scripts/reset_doubao_accounts.py --filter all

    # 只重置 cooldown
    python scripts/reset_doubao_accounts.py --filter cooldown --apply --confirm

    # 把 cooldown + expired + banned 都拉回 active (需要 cookies 仍在)
    python scripts/reset_doubao_accounts.py --filter all --apply --confirm

    # 一并重置 cookie-less 账号 (一般不建议)
    python scripts/reset_doubao_accounts.py --filter all --include-cookieless

环境变量:
    DATABASE_URL  数据库连接 (默认 geo_tracker config)

退出码:
    0  成功 (含 dry-run)
    1  执行错误
    2  参数错误
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import AccountStatus, LLMAccount

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


VALID_FILTERS = {
    "cooldown": AccountStatus.COOLDOWN.value,
    "expired": AccountStatus.EXPIRED.value,
    "banned": AccountStatus.BANNED.value,
}


def _parse_filter(raw: str) -> list[str]:
    raw = raw.strip().lower()
    if raw == "all":
        return [
            AccountStatus.COOLDOWN.value,
            AccountStatus.EXPIRED.value,
            AccountStatus.BANNED.value,
        ]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    statuses: list[str] = []
    for part in parts:
        if part not in VALID_FILTERS:
            raise SystemExit(
                f"Invalid filter '{part}'. Use cooldown, expired, banned, or all."
            )
        statuses.append(VALID_FILTERS[part])
    if not statuses:
        raise SystemExit("Filter is empty. Use cooldown, expired, banned, or all.")
    return statuses


async def reset_doubao_accounts(
    *,
    target_statuses: list[str],
    apply: bool,
    require_cookies: bool = True,
) -> dict:
    """List or reset Doubao accounts in the requested non-active states."""
    engine = create_task_engine()
    reset: list[dict] = []
    skipped_no_cookies = 0

    try:
        async with get_task_async_session(engine) as db:
            rows = (
                await db.execute(
                    select(LLMAccount).where(
                        LLMAccount.llm_name == "doubao",
                        LLMAccount.status.in_(target_statuses),
                    )
                )
            ).scalars().all()

            for acc in rows:
                has_cookies = bool(acc.cookies_json)
                if require_cookies and not has_cookies:
                    skipped_no_cookies += 1
                    logger.info(
                        "SKIP (no cookies) account id=%s status=%s",
                        acc.id,
                        acc.status,
                    )
                    continue

                previous_status = acc.status
                if apply:
                    acc.status = AccountStatus.ACTIVE.value
                    acc.cooldown_until = None
                    acc.consecutive_fails = 0
                    acc.query_count_today = 0
                    logger.info(
                        "RESET account id=%s status=%s -> active",
                        acc.id,
                        previous_status,
                    )
                else:
                    logger.info(
                        "[DRY RUN] account id=%s status=%s would be reset to active",
                        acc.id,
                        previous_status,
                    )
                reset.append({"id": int(acc.id), "previous_status": previous_status})

            if apply and reset:
                await db.commit()
    finally:
        await engine.dispose()

    return {
        "candidates": len(reset),
        "applied": apply,
        "skipped_no_cookies": skipped_no_cookies,
        "details": reset,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset Doubao accounts from cooldown/expired/banned back to active.",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default="cooldown",
        help="Comma-separated states to reset (cooldown,expired,banned,all). Default: cooldown.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the reset. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required together with --apply to actually write to the DB.",
    )
    parser.add_argument(
        "--include-cookieless",
        action="store_true",
        help="Also reset accounts whose cookies_json is empty (default: skip).",
    )
    args = parser.parse_args()

    try:
        target_statuses = _parse_filter(args.filter)
    except SystemExit as exc:
        logger.error(str(exc))
        return 2

    if args.apply and not args.confirm:
        logger.error("--apply requires --confirm to take effect.")
        return 2

    result = await reset_doubao_accounts(
        target_statuses=target_statuses,
        apply=args.apply,
        require_cookies=not args.include_cookieless,
    )

    print()
    print(f"Filter statuses: {target_statuses}")
    print(f"Candidates: {result['candidates']}")
    print(f"Skipped (no cookies): {result['skipped_no_cookies']}")
    print(f"Applied: {result['applied']}")
    if not result["applied"]:
        print("Dry run only. Add --apply --confirm to write.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
