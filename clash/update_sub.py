#!/usr/bin/env python3
"""Clash 订阅更新器

定期下载机场订阅链接，提取 proxies 段，转换为 proxy-provider 格式。
解决订阅返回完整 Clash 配置但 proxy-provider 期望纯代理列表的兼容性问题。

支持两种数据源：
  1. 从 CLASH_SUB_URL 下载订阅（自动模式）
  2. 从 RAW_SUB_FILE 读取本地文件（手动模式，下载失败时 fallback）

对于 Ninja 代理节点（使用 cnameip.xyz 域名），会尝试解析真实 IP 并替换：
  1. 尝试 Python DNS 解析
  2. 尝试 DNS-over-HTTPS（Google/Cloudflare）
  3. 尝试直连订阅服务器 DNS
  4. Fallback: 使用 NINJA_RELAY_IP 生成 hosts 映射

环境变量:
  CLASH_SUB_URL     - 订阅链接（可选，下载失败会 fallback 到本地文件）
  RAW_SUB_FILE      - 本地原始订阅文件路径（默认 /data/clash/raw_sub.yaml）
  UPDATE_INTERVAL   - 更新间隔秒数（默认 3600 = 1小时）
  PROVIDER_FILE     - 输出文件路径（默认 /data/proxies/ninja.yaml）
  CLASH_API         - Clash API 地址（默认 http://clash:9090）
  CLASH_CONFIG_DIR  - Clash 配置目录（默认 /data/clash）
  NINJA_RELAY_IP    - Ninja CNAME 域名的 relay IP（fallback，默认空）
"""

import json
import os
import re
import socket
import ssl
import struct
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


def resolve_domain_python(domain: str) -> str:
    """尝试用 Python socket 解析域名"""
    try:
        result = socket.getaddrinfo(domain, None, socket.AF_INET)
        if result:
            return result[0][4][0]
    except (socket.gaierror, OSError):
        pass
    return ""


def resolve_domain_doh(domain: str, doh_url: str = "https://1.1.1.1/dns-query") -> str:
    """通过 DNS-over-HTTPS 解析域名（Cloudflare/Google）"""
    try:
        url = f"{doh_url}?name={domain}&type=A"
        req = urllib.request.Request(url, headers={
            "Accept": "application/dns-json",
            "User-Agent": "curl/7.68"
        })
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            answers = data.get("Answer", [])
            for a in answers:
                if a.get("type") == 1:  # A record
                    return a["data"]
                if a.get("type") == 5:  # CNAME - follow it
                    cname_target = a["data"].rstrip(".")
                    # Try to resolve the CNAME target
                    for a2 in answers:
                        if a2.get("type") == 1 and a2.get("name", "").rstrip(".") == cname_target:
                            return a2["data"]
    except Exception:
        pass
    return ""


def resolve_domain_udp(domain: str, dns_server: str, port: int = 53, timeout: int = 5) -> str:
    """直接发送 UDP DNS 查询到指定 DNS 服务器"""
    try:
        # 构建 DNS A 记录查询包
        txn_id = os.urandom(2)
        flags = b'\x01\x00'  # standard query, recursion desired
        counts = struct.pack('>HHHH', 1, 0, 0, 0)  # 1 question
        # 编码域名
        qname = b''
        for part in domain.split('.'):
            qname += bytes([len(part)]) + part.encode('ascii')
        qname += b'\x00'
        qtype = struct.pack('>H', 1)   # A record
        qclass = struct.pack('>H', 1)  # IN class
        query = txn_id + flags + counts + qname + qtype + qclass

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(query, (dns_server, port))
        data, _ = sock.recvfrom(512)
        sock.close()

        # 解析响应
        if len(data) < 12:
            return ""
        ancount = struct.unpack('>H', data[6:8])[0]
        if ancount == 0:
            return ""

        # 跳过 header (12 bytes) + question section
        offset = 12
        while offset < len(data) and data[offset] != 0:
            offset += data[offset] + 1
        offset += 5  # null byte + qtype(2) + qclass(2)

        # 解析 answer records
        for _ in range(ancount):
            if offset >= len(data):
                break
            # 跳过 name (可能是指针)
            if data[offset] & 0xC0 == 0xC0:
                offset += 2
            else:
                while offset < len(data) and data[offset] != 0:
                    offset += data[offset] + 1
                offset += 1
            if offset + 10 > len(data):
                break
            rtype = struct.unpack('>H', data[offset:offset+2])[0]
            rdlen = struct.unpack('>H', data[offset+8:offset+10])[0]
            offset += 10
            if rtype == 1 and rdlen == 4:  # A record
                ip = '.'.join(str(b) for b in data[offset:offset+4])
                return ip
            offset += rdlen
    except Exception:
        pass
    return ""


def resolve_cname_domains(proxies: list, sub_url: str = "") -> dict:
    """尝试解析所有 cnameip.xyz 域名为真实 IP

    返回 {domain: ip} 字典。使用多种方法尝试：
    1. Python socket（系统 DNS）
    2. DOH（Google/Cloudflare）
    3. 直连订阅服务器的 DNS（如果从 URL 能提取 IP）
    """
    domains = set()
    for p in proxies:
        if isinstance(p, dict):
            server = p.get("server", "")
            if "cnameip.xyz" in server:
                domains.add(server)

    if not domains:
        return {}

    print(f"  发现 {len(domains)} 个 cnameip.xyz 域名，尝试解析...")
    resolved = {}

    # 从订阅 URL 提取服务器 IP（用于直连 DNS 查询）
    sub_server_ip = ""
    if sub_url:
        import re
        match = re.search(r'https?://([0-9.]+)', sub_url)
        if match:
            sub_server_ip = match.group(1)

    for domain in sorted(domains):
        ip = ""

        # 方法1: Python socket
        if not ip:
            ip = resolve_domain_python(domain)
            if ip:
                print(f"    ✓ {domain} → {ip} (system DNS)")

        # 方法2: DOH - Cloudflare
        if not ip:
            ip = resolve_domain_doh(domain, "https://1.1.1.1/dns-query")
            if ip:
                print(f"    ✓ {domain} → {ip} (DOH Cloudflare)")

        # 方法3: DOH - Google (用 IP 避免 hostname 解析问题)
        if not ip:
            ip = resolve_domain_doh(domain, "https://8.8.8.8/resolve")
            if ip:
                print(f"    ✓ {domain} → {ip} (DOH Google)")

        # 方法4: DOH - AliDNS (中国 DNS，可能无法解析 cnameip.xyz)
        if not ip:
            ip = resolve_domain_doh(domain, "https://dns.alidns.com/resolve")
            if ip:
                print(f"    ✓ {domain} → {ip} (DOH AliDNS)")

        # 方法5: 直连订阅服务器 DNS（DOGESS 可能自建 DNS）
        if not ip and sub_server_ip:
            ip = resolve_domain_udp(domain, sub_server_ip)
            if ip:
                print(f"    ✓ {domain} → {ip} (sub server DNS @ {sub_server_ip})")

        # 方法6: 尝试常见公共 DNS
        if not ip:
            for dns_ip in ["8.8.8.8", "1.1.1.1", "208.67.222.222"]:
                ip = resolve_domain_udp(domain, dns_ip)
                if ip:
                    print(f"    ✓ {domain} → {ip} (UDP DNS @ {dns_ip})")
                    break

        if ip:
            resolved[domain] = ip
        else:
            print(f"    ✗ {domain} → 无法解析")

    print(f"  DNS 解析结果: {len(resolved)}/{len(domains)} 成功")
    return resolved


def replace_proxy_servers(proxies: list, resolved: dict) -> int:
    """将代理节点中的 cnameip.xyz 域名替换为已解析的 IP

    返回替换数量。直接修改 proxies 列表中的 dict。
    """
    count = 0
    for p in proxies:
        if isinstance(p, dict):
            server = p.get("server", "")
            if server in resolved:
                p["server"] = resolved[server]
                count += 1
    return count


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

    # 尝试解析 cnameip.xyz 域名为真实 IP（模拟 V-Ninja GUI 行为）
    hosts_updated = False
    if isinstance(proxies[0], dict):
        resolved = resolve_cname_domains(proxies, sub_url)
        if resolved:
            replaced = replace_proxy_servers(proxies, resolved)
            print(f"  ✓ 已替换 {replaced} 个节点的域名为 IP")

        # 对于未解析的域名，使用 NINJA_RELAY_IP 作为 hosts 映射 fallback
        unresolved = extract_cname_hosts(proxies)  # 替换后仍含 cnameip.xyz 的
        if unresolved and relay_ip:
            print(f"  还有 {len(unresolved)} 个域名未解析，使用 NINJA_RELAY_IP={relay_ip} 作为 hosts 映射")
            patch_config_hosts(config_dir, unresolved, relay_ip)
            hosts_updated = True
        elif unresolved:
            print(f"  ⚠ 还有 {len(unresolved)} 个 cnameip.xyz 域名未解析且 NINJA_RELAY_IP 未设置")
            print(f"    请设置 NINJA_RELAY_IP 环境变量，或在服务器上手动配置 hosts")

    # 写入 provider 文件
    os.makedirs(os.path.dirname(provider_file), exist_ok=True)
    yaml_content = dump_proxies_yaml(proxies)
    with open(provider_file, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"  ✓ 已写入 {provider_file}")

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
