"""
Clash (Mihomo) RESTful API 客户端
用于查询代理节点列表、切换节点，实现被 Cloudflare 拦截时自动换节点重试
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CLASH_API_URL = os.getenv("CLASH_API_URL", "http://host.docker.internal:9098")


async def get_proxy_group(api_url: str, group_name: str) -> Optional[dict]:
    """获取代理组信息（包含所有节点和当前选中节点）"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{api_url}/proxies/{group_name}")
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Clash API 获取代理组失败: {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"Clash API 连接失败: {e}")
        return None


async def get_current_node(api_url: str, group_name: str) -> Optional[str]:
    """获取当前选中的代理节点名称"""
    group = await get_proxy_group(api_url, group_name)
    if group:
        return group.get("now")
    return None


async def get_all_nodes(api_url: str, group_name: str) -> list[str]:
    """获取代理组中所有可用节点名称（排除 DIRECT 和 REJECT）"""
    group = await get_proxy_group(api_url, group_name)
    if not group:
        return []
    excluded = {"DIRECT", "REJECT"}
    return [n for n in group.get("all", []) if n not in excluded]


async def switch_node(api_url: str, group_name: str, node_name: str) -> bool:
    """切换到指定代理节点"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.put(
                f"{api_url}/proxies/{group_name}",
                json={"name": node_name},
            )
            if resp.status_code == 204:
                logger.info(f"Clash 切换节点成功: {node_name}")
                return True
            logger.warning(f"Clash 切换节点失败: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Clash API 切换节点失败: {e}")
        return False


async def switch_to_next_node(
    api_url: str, group_name: str, exclude: set[str] | None = None
) -> Optional[str]:
    """
    切换到下一个可用节点（跳过 exclude 集合中的节点）
    返回切换后的节点名，如果没有可用节点返回 None
    """
    exclude = exclude or set()
    nodes = await get_all_nodes(api_url, group_name)
    current = await get_current_node(api_url, group_name)

    available = [n for n in nodes if n not in exclude and n != current]
    if not available:
        logger.error(f"没有更多可用节点（已排除 {len(exclude)} 个）")
        return None

    next_node = available[0]
    ok = await switch_node(api_url, group_name, next_node)
    return next_node if ok else None
