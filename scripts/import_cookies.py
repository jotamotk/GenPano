"""
将 auto_register.py 输出的 cookie JSON 文件批量导入到 llm_accounts 表。

用法:
    # 导入目录下所有 JSON 文件
    python scripts/import_cookies.py ./cookies/

    # 导入单个文件
    python scripts/import_cookies.py ./cookies/doubao_1234_20260331.json

    # 试运行（只打印，不写入数据库）
    python scripts/import_cookies.py ./cookies/ --dry-run

    # 指定每日查询限额
    python scripts/import_cookies.py ./cookies/ --daily-limit 30

环境变量:
    DATABASE_URL  数据库连接（默认 postgresql+asyncpg://postgres:password@localhost:5432/geo_tracker）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import select, and_

# 添加项目根目录到 sys.path，以便直接 python scripts/import_cookies.py 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import LLMAccount, AccountStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_cookie_file(filepath: Path) -> dict | None:
    """
    读取 auto_register.py 输出的 JSON 文件。
    期望格式: {"platform": "doubao", "phone": "138xxx", "cookies": [...]}
    """
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"跳过无法解析的文件 {filepath}: {e}")
        return None

    if "platform" not in data or "cookies" not in data:
        logger.warning(f"跳过格式不符的文件 {filepath}（缺少 platform 或 cookies 字段）")
        return None

    if not isinstance(data["cookies"], list) or len(data["cookies"]) == 0:
        logger.warning(f"跳过空 cookies 文件 {filepath}")
        return None

    return data


def collect_files(path: Path) -> list[Path]:
    """收集要导入的 JSON 文件列表"""
    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted(path.glob("*.json"))
        if not files:
            logger.warning(f"目录 {path} 中没有 JSON 文件")
        return files
    logger.error(f"路径不存在: {path}")
    return []


async def import_cookies(
    files: list[Path],
    daily_limit: int = 20,
    dry_run: bool = False,
) -> dict:
    """导入 cookie 文件到数据库"""
    engine = create_task_engine()
    created = 0
    updated = 0
    skipped = 0

    try:
        async with get_task_async_session(engine) as db:
            for filepath in files:
                data = load_cookie_file(filepath)
                if not data:
                    skipped += 1
                    continue

                platform = data["platform"]
                phone = data.get("phone", "")
                cookies_json = json.dumps(data["cookies"])

                # 查找是否已有同 llm_name + phone_number 的记录
                result = await db.execute(
                    select(LLMAccount).where(
                        and_(
                            LLMAccount.llm_name == platform,
                            LLMAccount.phone_number == phone,
                        )
                    )
                )
                existing = result.scalar_one_or_none()

                if dry_run:
                    action = "UPDATE" if existing else "CREATE"
                    logger.info(f"[DRY RUN] {action}: {platform} / {phone} ({filepath.name})")
                    if existing:
                        updated += 1
                    else:
                        created += 1
                    continue

                if existing:
                    # 更新 cookies
                    existing.cookies_json = cookies_json
                    existing.status = AccountStatus.ACTIVE.value
                    existing.consecutive_fails = 0
                    updated += 1
                    logger.info(f"UPDATE: account id={existing.id} ({platform} / {phone})")
                else:
                    # 新建账号
                    account = LLMAccount(
                        llm_name=platform,
                        email=f"{phone}@{platform}.local",
                        password_encrypted="",
                        phone_number=phone,
                        cookies_json=cookies_json,
                        daily_limit=daily_limit,
                        status=AccountStatus.ACTIVE.value,
                    )
                    db.add(account)
                    created += 1
                    logger.info(f"CREATE: {platform} / {phone} ({filepath.name})")

            if not dry_run:
                await db.commit()

    finally:
        await engine.dispose()

    return {"created": created, "updated": updated, "skipped": skipped}


async def main():
    parser = argparse.ArgumentParser(
        description="将 cookie JSON 文件导入到 llm_accounts 数据库表"
    )
    parser.add_argument(
        "path",
        type=str,
        help="Cookie JSON 文件或目录路径",
    )
    parser.add_argument(
        "--daily-limit",
        type=int,
        default=20,
        help="新建账号的每日查询限额（默认 20）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行，只打印操作不写入数据库",
    )
    args = parser.parse_args()

    path = Path(args.path)
    files = collect_files(path)
    if not files:
        print("没有找到可导入的文件")
        sys.exit(1)

    print(f"找到 {len(files)} 个 JSON 文件")
    if args.dry_run:
        print("[DRY RUN 模式]\n")

    result = await import_cookies(
        files,
        daily_limit=args.daily_limit,
        dry_run=args.dry_run,
    )

    print(f"\n完成: 新建 {result['created']}, 更新 {result['updated']}, 跳过 {result['skipped']}")


if __name__ == "__main__":
    asyncio.run(main())
