#!/usr/bin/env python3
"""Clash 订阅更新器

定期下载机场订阅链接，提取 proxies 段，转换为 proxy-provider 格式。
解决订阅返回完整 Clash 配置但 proxy-provider 期望纯代理列表的兼容性问题。

环境变量:
  CLASH_SUB_URL     - 订阅链接（必填）
  UPDATE_INTERVAL   - 更新间隔秒数（默认 3600 = 1小时）
  PROVIDER_FILE     - 输出文件路径（默认 /data/proxies/ninja.yaml）
  CLASH_API         - Clash API 地址（默认 http://clash:9090）
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

# pyyaml 可能不可用，用简单的 YAML 解析/生成
def parse_proxies_from_yaml(text: str) -> list:
    """从订阅 YAML 中提取 proxies 列表（简易解析，不依赖 pyyaml）"""
    try:
        import yaml
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data.get("proxies", [])
    except ImportError:
        pass

    # Fallback: 手动提取 proxies 段
    # 找到 "proxies:" 行，然后提取后续所有 "  -" 开头的块
    lines = text.split("\n")
    in_proxies = False
    proxy_lines = []

    for line in lines:
        stripped = line.rstrip()
        if stripped == "proxies:":
            in_proxies = True
            continue
        if in_proxies:
            # 新的顶级 key（不以空格开头）→ 结束
            if stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                break
            proxy_lines.append(line)

    if not proxy_lines:
        return []

    # 重新拼成 YAML 并解析
    proxy_yaml = "proxies:\n" + "\n".join(proxy_lines)
    try:
        import yaml
        data = yaml.safe_load(proxy_yaml)
        return data.get("proxies", [])
    except ImportError:
        # 无 pyyaml，返回原始行（让调用方处理）
        return proxy_lines

    return []


def dump_proxies_yaml(proxies: list) -> str:
    """将 proxies 列表序列化为 YAML"""
    try:
        import yaml
        return yaml.dump({"proxies": proxies}, allow_unicode=True, default_flow_style=False)
    except ImportError:
        pass

    # Fallback: 手动生成简单 YAML
    # 如果 proxies 是字符串行列表（从 fallback 解析来的），直接拼接
    if proxies and isinstance(proxies[0], str):
        return "proxies:\n" + "\n".join(proxies) + "\n"

    # 否则手动序列化 dict 列表
    lines = ["proxies:"]
    for p in proxies:
        if isinstance(p, dict):
            lines.append("  -")
            for k, v in p.items():
                if isinstance(v, str):
                    # 需要引号的值
                    lines.append(f"    {k}: '{v}'")
                elif isinstance(v, bool):
                    lines.append(f"    {k}: {'true' if v else 'false'}")
                else:
                    lines.append(f"    {k}: {v}")
    return "\n".join(lines) + "\n"


def download_subscription(url: str, timeout: int = 30) -> str:
    """下载订阅内容"""
    req = urllib.request.Request(url, headers={"User-Agent": "ClashForAndroid/2.5.12"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def reload_provider(clash_api: str, provider_name: str = "ninja-sub"):
    """通知 Clash 重新加载 provider"""
    try:
        url = f"{clash_api}/providers/proxies/{provider_name}"
        req = urllib.request.Request(url, method="PUT")
        urllib.request.urlopen(req, timeout=5)
        print(f"  Clash provider '{provider_name}' 已重新加载")
    except Exception as e:
        print(f"  ⚠ Clash reload 失败（Clash 可能还没启动）: {e}")


def update_once(sub_url: str, provider_file: str, clash_api: str) -> bool:
    """执行一次订阅更新"""
    print(f"\n{'='*50}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始更新订阅")

    # 下载
    try:
        content = download_subscription(sub_url)
        print(f"  ✓ 下载成功 ({len(content)} bytes)")
    except Exception as e:
        print(f"  ✗ 下载失败: {e}")
        return False

    # 提取 proxies
    proxies = parse_proxies_from_yaml(content)
    if not proxies:
        print("  ✗ 订阅中未找到有效的 proxies 段")
        return False

    # 验证节点（如果是 dict 列表）
    if isinstance(proxies[0], dict):
        valid = [p for p in proxies if p.get("server") and p.get("port")]
        print(f"  总节点: {len(proxies)}, 有效: {len(valid)}")
        if not valid:
            print("  ✗ 没有有效节点")
            return False
        proxies = valid
    else:
        print(f"  提取到 {len(proxies)} 行代理配置")

    # 写入文件
    os.makedirs(os.path.dirname(provider_file), exist_ok=True)
    yaml_content = dump_proxies_yaml(proxies)
    with open(provider_file, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"  ✓ 已写入 {provider_file}")

    # 通知 Clash 重新加载
    reload_provider(clash_api)

    return True


def main():
    sub_url = os.environ.get("CLASH_SUB_URL", "")
    if not sub_url:
        print("✗ 环境变量 CLASH_SUB_URL 未设置")
        sys.exit(1)

    interval = int(os.environ.get("UPDATE_INTERVAL", "3600"))
    provider_file = os.environ.get("PROVIDER_FILE", "/data/proxies/ninja.yaml")
    clash_api = os.environ.get("CLASH_API", "http://clash:9090")

    print(f"Clash 订阅更新器启动")
    print(f"  订阅链接: {sub_url[:50]}...")
    print(f"  更新间隔: {interval}s")
    print(f"  输出文件: {provider_file}")
    print(f"  Clash API: {clash_api}")

    # 启动时立即更新一次
    update_once(sub_url, provider_file, clash_api)

    # 定期更新
    while True:
        time.sleep(interval)
        try:
            update_once(sub_url, provider_file, clash_api)
        except Exception as e:
            print(f"  ✗ 更新异常: {e}")


if __name__ == "__main__":
    main()
