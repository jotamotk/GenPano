"""
SMS 登录模块 — 平台注册表 + 工厂函数

使用方式:
    from geo_tracker.agent.sms_login import get_handler
    handler = get_handler("doubao")
    result = await handler.login_or_register(phone="138xxx")
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from geo_tracker.agent.sms_login.base import BaseSMSLoginHandler

_HANDLERS: dict[str, type[BaseSMSLoginHandler]] = {}


def register(platform: str):
    """装饰器，注册平台登录处理器"""
    def decorator(cls):
        _HANDLERS[platform] = cls
        return cls
    return decorator


def get_handler(platform: str) -> BaseSMSLoginHandler | None:
    """获取平台对应的登录处理器实例，未注册则返回 None"""
    cls = _HANDLERS.get(platform)
    return cls() if cls else None


# 导入时自动注册各平台处理器
from geo_tracker.agent.sms_login.doubao_login import DoubaoLoginHandler  # noqa: E402, F401
