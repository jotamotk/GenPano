"""
SMS 注册 / 重新登录的分布式锁与失败 cooldown.

背景: 生产事故 2026-04-27 — 鲁班 SMS 4 小时被消耗 10 条 DeepSeek 验证码 (一条 ~1元),
根因不是浏览器泄漏直接导致, 而是 fire-and-forget enqueue 没有去重锁:
  - execute_query L170: 没账号就 enqueue auto_login(new_account=True)
  - cookie_keep_alive L454: 保活失败就 enqueue auto_login(account_id=...)
  - 同时间窗多个 query 失败时多次 enqueue, 每次都向鲁班要新手机号
本模块提供两类锁, 由 enqueue 方在调 apply_async 前先 acquire:

  1. in-flight lock (TTL 10 min): 防止同 account_id / 同 platform 短期内
     被并发 enqueue 多个注册任务. 任务开始时 acquire, 任务结束 (含异常) 释放.
  2. failure cooldown (TTL 30 min): 注册失败后 30 分钟内不再尝试同 platform
     新注册, 避免反复花 SMS. 重新登录路径不进 cooldown (无 SMS 成本).

设计原则 (与决策 #25 Rule 1 单一真相源一致):
  - 单一入口 should_enqueue_*() 由调用方在 enqueue 前调
  - 失败/成功后由 auto_login 任务自身负责释放锁 + (失败时) 设 cooldown
  - 复用现有 Redis broker 连接, 不新增基础设施

锁 key 命名 (带 'genpano:' 前缀, 与 Celery Redis broker key 隔离):
  - in-flight 新注册:  genpano:autologin:newaccount:{platform}
  - in-flight 重登录:  genpano:autologin:relogin:{account_id}
  - 失败 cooldown:    genpano:autologin:cooldown:{platform}
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# 锁 TTL (秒). 调大会让卡死的 in-flight 锁久滞留, 调小会失去保护.
# 当前 10 min 经验值: 正常 SMS 注册 < 60s, 留 10x 余量。
INFLIGHT_LOCK_TTL_S = 10 * 60
# Cooldown TTL (秒). 失败后 30 min 内不再尝试同 platform 注册.
# 30 min 是鲁班号码池循环周期的合理估计, 避免连续耗号。
FAILURE_COOLDOWN_TTL_S = 30 * 60


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _new_account_lock_key(platform: str) -> str:
    return f"genpano:autologin:newaccount:{platform}"


def _relogin_lock_key(account_id: int) -> str:
    return f"genpano:autologin:relogin:{account_id}"


def _cooldown_key(platform: str) -> str:
    return f"genpano:autologin:cooldown:{platform}"


async def should_enqueue_new_account(platform: str) -> bool:
    """
    判断是否应该 enqueue 一个新注册任务. 同时做两件事:
      1. 检查 platform 是否在 cooldown — 在则拒绝 (返回 False)
      2. 尝试获取 in-flight 锁 — 已被占用则拒绝 (返回 False)
    成功获取锁返回 True, 调用方应立即 apply_async, 任务完成后调
    release_new_account_lock() 释放锁.

    注意: 这是 fail-open 设计 — Redis 不可达时返回 True 让任务正常入队,
    避免 Redis 故障阻塞所有注册. 锁是优化不是强一致, 漏一两条可接受。
    """
    client = aioredis.from_url(_redis_url(), decode_responses=True)
    try:
        # 检查 cooldown
        cooldown_active = await client.exists(_cooldown_key(platform))
        if cooldown_active:
            logger.warning(
                f"[reg_lock] {platform} new-account in cooldown, "
                f"skipping enqueue to save SMS"
            )
            return False
        # 尝试获取 in-flight 锁 (NX = only set if not exists)
        acquired = await client.set(
            _new_account_lock_key(platform),
            "1",
            nx=True,
            ex=INFLIGHT_LOCK_TTL_S,
        )
        if not acquired:
            logger.warning(
                f"[reg_lock] {platform} new-account already in-flight, "
                f"skipping duplicate enqueue (saved 1 SMS)"
            )
            return False
        return True
    except Exception as e:
        logger.warning(f"[reg_lock] redis check failed (fail-open): {e}")
        return True
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def should_enqueue_relogin(account_id: int) -> bool:
    """
    判断是否 enqueue 一个 re-login 任务. 重登录用已存手机号, 不花 SMS,
    但仍然需要去重避免并发再登录浪费浏览器资源.
    """
    client = aioredis.from_url(_redis_url(), decode_responses=True)
    try:
        acquired = await client.set(
            _relogin_lock_key(account_id),
            "1",
            nx=True,
            ex=INFLIGHT_LOCK_TTL_S,
        )
        if not acquired:
            logger.info(
                f"[reg_lock] account #{account_id} re-login already in-flight, "
                f"skipping duplicate enqueue"
            )
            return False
        return True
    except Exception as e:
        logger.warning(f"[reg_lock] redis check failed (fail-open): {e}")
        return True
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def release_new_account_lock(
    platform: str,
    *,
    failed: bool,
) -> None:
    """
    释放新注册的 in-flight 锁. 失败时同时设置 cooldown.
    auto_login 任务的 finally 块必须调一次 (无论 success/failure/exception).
    """
    client = aioredis.from_url(_redis_url(), decode_responses=True)
    try:
        await client.delete(_new_account_lock_key(platform))
        if failed:
            await client.set(
                _cooldown_key(platform),
                "1",
                ex=FAILURE_COOLDOWN_TTL_S,
            )
            logger.warning(
                f"[reg_lock] {platform} new-account FAILED, "
                f"cooldown set for {FAILURE_COOLDOWN_TTL_S // 60} min"
            )
    except Exception as e:
        logger.warning(f"[reg_lock] release lock failed (best-effort): {e}")
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def release_relogin_lock(account_id: int) -> None:
    """释放 re-login 的 in-flight 锁. auto_login finally 必调."""
    client = aioredis.from_url(_redis_url(), decode_responses=True)
    try:
        await client.delete(_relogin_lock_key(account_id))
    except Exception as e:
        logger.warning(f"[reg_lock] release relogin lock failed: {e}")
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


def should_enqueue_new_account_sync(platform: str) -> bool:
    """
    同步版本, 给非 async 的 enqueue 调用点用 (Celery prefork worker
    调 apply_async 时常处于 sync context).
    """
    import redis  # type: ignore[import-not-found]

    try:
        client = redis.from_url(_redis_url(), decode_responses=True)
        if client.exists(_cooldown_key(platform)):
            logger.warning(
                f"[reg_lock] {platform} new-account in cooldown, "
                f"skipping enqueue to save SMS"
            )
            return False
        acquired = client.set(
            _new_account_lock_key(platform),
            "1",
            nx=True,
            ex=INFLIGHT_LOCK_TTL_S,
        )
        if not acquired:
            logger.warning(
                f"[reg_lock] {platform} new-account already in-flight, "
                f"skipping duplicate enqueue (saved 1 SMS)"
            )
            return False
        return True
    except Exception as e:
        logger.warning(f"[reg_lock] sync redis check failed (fail-open): {e}")
        return True


def should_enqueue_relogin_sync(account_id: int) -> bool:
    """同步版本 of should_enqueue_relogin."""
    import redis  # type: ignore[import-not-found]

    try:
        client = redis.from_url(_redis_url(), decode_responses=True)
        acquired = client.set(
            _relogin_lock_key(account_id),
            "1",
            nx=True,
            ex=INFLIGHT_LOCK_TTL_S,
        )
        if not acquired:
            logger.info(
                f"[reg_lock] account #{account_id} re-login already in-flight, "
                f"skipping duplicate enqueue"
            )
            return False
        return True
    except Exception as e:
        logger.warning(f"[reg_lock] sync redis check failed (fail-open): {e}")
        return True
