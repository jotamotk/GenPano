#!/usr/bin/env python3
"""Clash 订阅更新器

定期下载机场订阅链接，提取 proxies 段，转换为 proxy-provider 格式。
解决订阅返回完整 Clash 配置但 proxy-provider 期望纯代理列表的兼容性问题。

支持两种数据源：
  1. 从 CLASH_SUB_URL 下载订阅（自动模式）
  2. 从 RAW_SUB_FILE 读取本地文件（手动模式，下载失败时 fallback）

对于 Ninja 代理节点（使用 cnameip.xyz 域名），自动生成 hosts 映射
写入 Clash 配置文件，解决 Docker 环境无法解析 CNAME 域名的问题。

环境变量:
  CLASH_SUB_URL     - 订阅链接（可选，下载失败会 fallback 到本地文件）
  RAW_SUB_FILE      - 本地原始订阅文件路径（默认 /data/clash/raw_sub.yaml）
  UPDATE_INTERVAL   - 更新间隔秒数（默认 3600 = 1小时）
  PROVIDER_FILE     - 输出文件路径（默认 /data/proxies/ninja.yaml）
  CLASH_API         - Clash API 地址（默认 http://clash:9090）
  CLASH_CONFIG_DIR  - Clash 配置目录（默认 /data/clash）
  NINJA_RELAY_IP    - Ninja CNAME 域名的 relay IP（默认空，不生成 hosts）
"""

import json
import os
import re
import ssl
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
    req = urllib.request.Request(url, headers={"User-Agent": "V-Ninja/2.3.1"})
    # 跳过 SSL 验证（Ninja 订阅服务器可能使用自签名证书）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8")


def read_local_subscription(file_path: str) -> str:
    """从本地文件读取订阅内容"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_cname_hosts(proxies: list) -> list:
    """从代理列表中提取 cnameip.xyz 域名"""
    hosts = set()
    for p in proxies:
        if isinstance(p, dict):
            server = p.get("server", "")
            if "cnameip.xyz" in server:
                hosts.add(server)
    return sorted(hosts)


def patch_config_hosts(config_dir: str, cname_hosts: list, relay_ip: str):
    """将 cnameip.xyz hosts 映射写入 Clash 配置文件

    读取 config.yaml，添加/更新 hosts 段，将 cnameip.xyz 域名映射到 relay IP。
    使用 pyyaml 保证 YAML 格式正确。
    """
    config_path = os.path.join(config_dir, "config.yaml")
    if not os.path.exists(config_path):
        print(f"  ⚠ 配置文件不存在: {config_path}")
        return

    try:
        import yaml
    except ImportError:
        print("  ⚠ pyyaml 不可用，无法更新 hosts 映射（使用 pip install pyyaml）")
        return

    # 读取现有配置
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        print("  ⚠ 配置文件格式错误")
        return

    # 生成 hosts 映射
    hosts_map = {}
    for h in cname_hosts:
        hosts_map[h] = relay_ip

    # 合并到现有 hosts（保留手动添加的映射）
    existing_hosts = config.get("hosts", {}) or {}
    # 清除旧的 cnameip.xyz 映射，重新生成
    existing_hosts = {k: v for k, v in existing_hosts.items() if "cnameip.xyz" not in k}
    existing_hosts.update(hosts_map)
    config["hosts"] = existing_hosts

    # 写回配置文件
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"  ✓ 已更新 hosts 映射: {len(hosts_map)} 个 cnameip.xyz 域名 → {relay_ip}")


def reload_provider(clash_api: str, provider_name: str = "ninja-sub"):
    """通知 Clash 重新加载 provider"""
    try:
        url = f"{clash_api}/providers/proxies/{provider_name}"
        req = urllib.request.Request(url, method="PUT")
        urllib.request.urlopen(req, timeout=5)
        print(f"  Clash provider '{provider_name}' 已重新加载")
    except Exception as e:
        print(f"  ⚠ Clash reload 失败（Clash 可能还没启动）: {e}")


def reload_full_config(clash_api: str):
    """通知 Clash 重新加载整个配置（用于 hosts 更新后）"""
    try:
        url = f"{clash_api}/configs"
        data = json.dumps({"path": ""}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="PUT",
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
        print(f"  ✓ Clash 配置已重新加载")
    except Exception as e:
        print(f"  ⚠ Clash 配置重载失败: {e}")


def update_once(sub_url: str, raw_sub_file: str, provider_file: str,
                clash_api: str, config_dir: str, relay_ip: str) -> bool:
    """执行一次订阅更新"""
    print(f"\n{'='*50}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始更新订阅")

    content = None

    # 尝试下载
    if sub_url:
        try:
            content = download_subscription(sub_url)
            print(f"  ✓ 下载成功 ({len(content)} bytes)")
            # 下载成功后，保存一份到本地（作为备份）
            if raw_sub_file:
                try:
                    os.makedirs(os.path.dirname(raw_sub_file), exist_ok=True)
                    with open(raw_sub_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"  ✓ 已备份到 {raw_sub_file}")
                except Exception as e:
                    print(f"  ⚠ 备份失败: {e}")
        except Exception as e:
            print(f"  ✗ 下载失败: {e}")

    # 下载失败，尝试本地文件
    if content is None and raw_sub_file and os.path.exists(raw_sub_file):
        try:
            content = read_local_subscription(raw_sub_file)
            print(f"  ✓ 从本地文件读取: {raw_sub_file} ({len(content)} bytes)")
        except Exception as e:
            print(f"  ✗ 本地文件读取失败: {e}")

    if content is None:
        print("  ✗ 无可用的订阅数据（下载失败且无本地文件）")
        print(f"  提示: 手动上传订阅文件到 {raw_sub_file}")
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

    # 写入 provider 文件
    os.makedirs(os.path.dirname(provider_file), exist_ok=True)
    yaml_content = dump_proxies_yaml(proxies)
    with open(provider_file, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"  ✓ 已写入 {provider_file}")

    # 处理 cnameip.xyz hosts 映射
    hosts_updated = False
    if isinstance(proxies[0], dict) and relay_ip:
        cname_hosts = extract_cname_hosts(proxies)
        if cname_hosts:
            print(f"  发现 {len(cname_hosts)} 个 cnameip.xyz 域名，生成 hosts 映射")
            patch_config_hosts(config_dir, cname_hosts, relay_ip)
            hosts_updated = True

    # 通知 Clash 重新加载
    if hosts_updated:
        # hosts 变更需要重载整个配置
        reload_full_config(clash_api)
    reload_provider(clash_api)

    return True


def main():
    sub_url = os.environ.get("CLASH_SUB_URL", "")
    raw_sub_file = os.environ.get("RAW_SUB_FILE", "/data/clash/raw_sub.yaml")
    interval = int(os.environ.get("UPDATE_INTERVAL", "3600"))
    provider_file = os.environ.get("PROVIDER_FILE", "/data/proxies/ninja.yaml")
    clash_api = os.environ.get("CLASH_API", "http://clash:9090")
    config_dir = os.environ.get("CLASH_CONFIG_DIR", "/data/clash")
    relay_ip = os.environ.get("NINJA_RELAY_IP", "")

    if not sub_url and not (raw_sub_file and os.path.exists(raw_sub_file)):
        print("✗ 无订阅来源: CLASH_SUB_URL 未设置且本地文件不存在")
        print(f"  请设置 CLASH_SUB_URL 或上传订阅文件到 {raw_sub_file}")
        # 不退出，等待用户上传文件
        print(f"  每 {interval}s 重试一次...")

    print(f"Clash 订阅更新器启动")
    if sub_url:
        print(f"  订阅链接: {sub_url[:50]}...")
    print(f"  本地文件: {raw_sub_file}")
    print(f"  更新间隔: {interval}s")
    print(f"  输出文件: {provider_file}")
    print(f"  Clash API: {clash_api}")
    print(f"  配置目录: {config_dir}")
    if relay_ip:
        print(f"  Ninja Relay IP: {relay_ip}")
    else:
        print(f"  Ninja Relay IP: 未设置（不生成 hosts 映射）")

    # 启动时立即更新一次
    update_once(sub_url, raw_sub_file, provider_file, clash_api, config_dir, relay_ip)

    # 定期更新
    while True:
        time.sleep(interval)
        try:
            update_once(sub_url, raw_sub_file, provider_file, clash_api, config_dir, relay_ip)
        except Exception as e:
            print(f"  ✗ 更新异常: {e}")


if __name__ == "__main__":
    main()
