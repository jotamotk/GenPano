"""
将 cookie JSON 文件批量导入到 llm_accounts 表。

支持两种格式:
  1. auto_register.py 输出: {"platform": "doubao", "phone": "138xxx", "cookies": [...]}
  2. EditThisCookie 导出: [{"domain": ".doubao.com", "name": "xxx", "value": "yyy", ...}, ...]

用法:
    # 导入 auto_register.py 输出的文件
    python scripts/import_cookies.py ./cookies/

    # 导入 EditThisCookie 导出的文件（需指定 --platform）
    python scripts/import_cookies.py doubao_raw.json --platform doubao

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


def _convert_editthiscookie(cookies: list[dict]) -> list[dict]:
    """将 EditThisCookie 格式转换为 Playwright add_cookies 格式"""
    SAME_SITE_MAP = {
        "unspecified": "Lax",
        "no_restriction": "None",
        "lax": "Lax",
        "strict": "Strict",
    }
    import time as _time
    result = []
    for c in cookies:
        entry = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
        }
        if c.get("expirationDate"):
            entry["expires"] = c["expirationDate"]
        elif c.get("session"):
            # Session cookie 没有过期时间，给 30 天有效期
            entry["expires"] = _time.time() + 30 * 86400
        if c.get("httpOnly"):
            entry["httpOnly"] = True
        if c.get("secure"):
            entry["secure"] = True
        same_site = c.get("sameSite", "unspecified")
        entry["sameSite"] = SAME_SITE_MAP.get(same_site, "Lax")
        result.append(entry)
    return result


def _is_editthiscookie(data) -> bool:
    """检测是否为 EditThisCookie 导出格式（JSON 数组，含 storeId/hostOnly）"""
    return (
        isinstance(data, list)
        and len(data) > 0
        and isinstance(data[0], dict)
        and ("storeId" in data[0] or "hostOnly" in data[0])
    )


def _guess_platform_from_cookies(cookies: list[dict]) -> str | None:
    """从 cookie domain 猜测平台名"""
    domains = {c.get("domain", "") for c in cookies}
    for d in domains:
        if "doubao" in d:
            return "doubao"
        if "deepseek" in d:
            return "deepseek"
        if "gemini" in d or "google" in d:
            return "gemini"
        if "kimi" in d or "moonshot" in d:
            return "kimi"
        if "chatgpt" in d or "openai" in d:
            return "chatgpt"
    return None


def load_cookie_file(filepath: Path, default_platform: str | None = None) -> dict | None:
    """
    读取 cookie JSON 文件，支持两种格式:
    1. auto_register.py: {"platform": "doubao", "phone": "138xxx", "cookies": [...]}
    2. EditThisCookie: [{"domain": "...", "name": "...", "value": "...", ...}, ...]
    """
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"跳过无法解析的文件 {filepath}: {e}")
        return None

    # 格式 1: auto_register.py 输出
    if isinstance(data, dict) and "platform" in data and "cookies" in data:
        if not isinstance(data["cookies"], list) or len(data["cookies"]) == 0:
            logger.warning(f"跳过空 cookies 文件 {filepath}")
            return None
        return data

    # 格式 2: EditThisCookie 导出
    if _is_editthiscookie(data):
        platform = default_platform or _guess_platform_from_cookies(data)
        if not platform:
            logger.warning(
                f"跳过 {filepath}: EditThisCookie 格式但无法识别平台，"
                f"请使用 --platform 参数指定"
            )
            return None
        cookies = _convert_editthiscookie(data)
        logger.info(f"EditThisCookie 格式，已转换 {len(cookies)} 个 cookies → {platform}")
        return {
            "platform": platform,
            "phone": filepath.stem,  # 用文件名作为标识
            "cookies": cookies,
        }

    logger.warning(f"跳过格式不符的文件 {filepath}")
    return None


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
    default_platform: str | None = None,
) -> dict:
    """导入 cookie 文件到数据库"""
    engine = create_task_engine()
    created = 0
    updated = 0
    skipped = 0

    try:
        async with get_task_async_session(engine) as db:
            for filepath in files:
                data = load_cookie_file(filepath, default_platform=default_platform)
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
        "--platform",
        type=str,
        default=None,
        help="指定平台名（导入 EditThisCookie 格式时使用，如 doubao, deepseek）",
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
        default_platform=args.platform,
    )

    print(f"\n完成: 新建 {result['created']}, 更新 {result['updated']}, 跳过 {result['skipped']}")


if __name__ == "__main__":
    asyncio.run(main())
