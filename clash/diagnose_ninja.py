#!/usr/bin/env python3
"""Ninja 代理诊断工具

在服务器上运行，诊断 cnameip.xyz 域名解析和代理连通性问题。

用法:
  # 直接在服务器上运行（需要 raw_sub.yaml 存在）
  python3 diagnose_ninja.py

  # 指定订阅文件路径
  python3 diagnose_ninja.py /opt/genpano/clash/raw_sub.yaml

  # 在 Docker 容器内运行
  docker compose exec clash-sub-updater python /app/diagnose_ninja.py /data/clash/raw_sub.yaml
"""

import json
import os
import socket
import ssl
import struct
import sys
import time
import urllib.request


def resolve_python(domain):
    """系统 DNS 解析"""
    try:
        result = socket.getaddrinfo(domain, None, socket.AF_INET)
        return result[0][4][0] if result else None
    except Exception as e:
        return f"FAIL: {e}"


def resolve_doh(domain, doh_url):
    """DNS-over-HTTPS"""
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
            data = json.loads(resp.read())
            answers = data.get("Answer", [])
            for a in answers:
                if a.get("type") == 1:
                    return a["data"]
                if a.get("type") == 5:
                    return f"CNAME → {a['data']}"
            status = data.get("Status", "unknown")
            return f"NO_ANSWER (status={status})"
    except Exception as e:
        return f"FAIL: {e}"


def resolve_udp(domain, dns_server, port=53, timeout=3):
    """直接 UDP DNS 查询"""
    try:
        txn_id = os.urandom(2)
        flags = b'\x01\x00'
        counts = struct.pack('>HHHH', 1, 0, 0, 0)
        qname = b''
        for part in domain.split('.'):
            qname += bytes([len(part)]) + part.encode('ascii')
        qname += b'\x00'
        qtype = struct.pack('>H', 1)
        qclass = struct.pack('>H', 1)
        query = txn_id + flags + counts + qname + qtype + qclass

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(query, (dns_server, port))
        data, _ = sock.recvfrom(512)
        sock.close()

        if len(data) < 12:
            return "FAIL: short response"
        rcode = data[3] & 0x0F
        if rcode == 3:
            return "NXDOMAIN"
        if rcode != 0:
            return f"DNS_ERROR (rcode={rcode})"
        ancount = struct.unpack('>H', data[6:8])[0]
        if ancount == 0:
            return "NO_ANSWER"

        offset = 12
        while offset < len(data) and data[offset] != 0:
            offset += data[offset] + 1
        offset += 5

        for _ in range(ancount):
            if offset >= len(data):
                break
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
            if rtype == 1 and rdlen == 4:
                return '.'.join(str(b) for b in data[offset:offset+4])
            offset += rdlen
        return "NO_A_RECORD"
    except socket.timeout:
        return "TIMEOUT"
    except Exception as e:
        return f"FAIL: {e}"


def check_tcp_connect(host, port, timeout=5):
    """测试 TCP 连接"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return "OK"
    except socket.timeout:
        return "TIMEOUT"
    except Exception as e:
        return f"FAIL: {e}"


def check_clash_ninja_service():
    """检查 clash-ninja-service Unix socket"""
    sock_path = "/tmp/clash-ninja-service.sock"
    if not os.path.exists(sock_path):
        return "NOT_FOUND"
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect(sock_path)
        # 尝试发送空消息看看响应
        sock.send(b'{"cmd":"ping"}\n')
        time.sleep(0.5)
        try:
            resp = sock.recv(4096)
            sock.close()
            return f"CONNECTED, response: {resp[:200]}"
        except socket.timeout:
            sock.close()
            return "CONNECTED, no response to ping"
    except Exception as e:
        return f"FAIL: {e}"


def main():
    print("=" * 60)
    print("Ninja 代理诊断工具")
    print("=" * 60)

    # 读取订阅文件
    sub_file = sys.argv[1] if len(sys.argv) > 1 else "/opt/genpano/clash/raw_sub.yaml"
    if not os.path.exists(sub_file):
        sub_file = "/data/clash/raw_sub.yaml"  # Docker 内路径
    if not os.path.exists(sub_file):
        print(f"\n✗ 订阅文件不存在: {sub_file}")
        print("  用法: python3 diagnose_ninja.py <path_to_raw_sub.yaml>")
        # 仍然运行基础诊断
        domains = []
    else:
        print(f"\n📄 订阅文件: {sub_file}")
        try:
            import yaml
            with open(sub_file) as f:
                data = yaml.safe_load(f)
            proxies = data.get("proxies", []) if isinstance(data, dict) else []
        except ImportError:
            # Fallback without pyyaml
            with open(sub_file) as f:
                content = f.read()
            proxies = []
            print("  ⚠ pyyaml 不可用，尝试手动提取域名")
            import re
            domains = re.findall(r'server:\s*[\'"]?([^\s\'"]+\.cnameip\.xyz)[\'"]?', content)
            print(f"  找到 {len(domains)} 个 cnameip.xyz 域名")

        if proxies:
            domains = sorted(set(
                p["server"] for p in proxies
                if isinstance(p, dict) and "cnameip.xyz" in p.get("server", "")
            ))
            print(f"  总节点: {len(proxies)}")
            print(f"  cnameip.xyz 域名: {len(domains)}")

            # 显示节点类型统计
            types = {}
            for p in proxies:
                if isinstance(p, dict):
                    t = p.get("type", "unknown")
                    types[t] = types.get(t, 0) + 1
            print(f"  节点类型: {types}")

    # 1. 检查 clash-ninja-service
    print(f"\n{'─'*60}")
    print("1. clash-ninja-service 状态")
    result = check_clash_ninja_service()
    print(f"   {result}")

    # 2. DNS 解析测试
    print(f"\n{'─'*60}")
    print("2. DNS 解析测试")

    test_domains = domains[:3] if domains else []
    if not test_domains:
        print("   无 cnameip.xyz 域名可测试")
    else:
        dns_servers = {
            "系统 DNS": None,
            "AliDNS (223.5.5.5)": "223.5.5.5",
            "Google (8.8.8.8)": "8.8.8.8",
            "Cloudflare (1.1.1.1)": "1.1.1.1",
            "OpenDNS (208.67.222.222)": "208.67.222.222",
            "DOGESS (45.137.181.169)": "45.137.181.169",
        }

        doh_servers = {
            "DOH Cloudflare": "https://1.1.1.1/dns-query",
            "DOH Google": "https://dns.google/resolve",
            "DOH AliDNS": "https://dns.alidns.com/resolve",
            "DOH DNSPod": "https://doh.pub/dns-query",
        }

        for domain in test_domains:
            print(f"\n   域名: {domain}")

            # System DNS
            result = resolve_python(domain)
            print(f"     系统 DNS:    {result}")

            # UDP DNS
            for name, ip in dns_servers.items():
                if ip:
                    result = resolve_udp(domain, ip)
                    print(f"     {name:30s} {result}")

            # DOH
            for name, url in doh_servers.items():
                result = resolve_doh(domain, url)
                print(f"     {name:30s} {result}")

    # 3. 查找 cnameip.xyz 的 NS 记录
    print(f"\n{'─'*60}")
    print("3. cnameip.xyz NS 记录查询")
    for dns_ip in ["8.8.8.8", "1.1.1.1", "223.5.5.5"]:
        try:
            # Query NS record for cnameip.xyz
            txn_id = os.urandom(2)
            flags = b'\x01\x00'
            counts = struct.pack('>HHHH', 1, 0, 0, 0)
            qname = b'\x07cnameip\x03xyz\x00'
            qtype = struct.pack('>H', 2)   # NS record
            qclass = struct.pack('>H', 1)
            query = txn_id + flags + counts + qname + qtype + qclass
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            sock.sendto(query, (dns_ip, 53))
            data, _ = sock.recvfrom(512)
            sock.close()
            rcode = data[3] & 0x0F
            ancount = struct.unpack('>H', data[6:8])[0]
            nscount = struct.unpack('>H', data[8:10])[0]
            print(f"   @{dns_ip}: rcode={rcode}, answers={ancount}, authority={nscount}, raw={data[12:80].hex()}")
        except Exception as e:
            print(f"   @{dns_ip}: FAIL: {e}")

    # 4. TCP 连通性测试
    print(f"\n{'─'*60}")
    print("4. DOGESS 服务器连通性")
    for port in [53, 80, 443, 7890, 9090]:
        result = check_tcp_connect("45.137.181.169", port, timeout=3)
        print(f"   45.137.181.169:{port:5d}  →  {result}")

    # 5. 如果有可解析的 IP，测试代理端口连通性
    if domains:
        print(f"\n{'─'*60}")
        print("5. 尝试解析第一个域名并测试连通性")
        domain = domains[0]
        # 尝试所有方法
        ip = None
        for dns_ip in ["223.5.5.5", "8.8.8.8", "1.1.1.1", "45.137.181.169"]:
            result = resolve_udp(domain, dns_ip)
            if result and not result.startswith(("FAIL", "NX", "NO_", "TIME")):
                ip = result
                print(f"   解析成功: {domain} → {ip} (via {dns_ip})")
                break

        if not ip:
            ip = resolve_python(domain)
            if ip and not str(ip).startswith("FAIL"):
                print(f"   解析成功: {domain} → {ip} (system)")

        if ip and not str(ip).startswith("FAIL"):
            # 找到该域名对应的端口
            port = None
            if proxies:
                for p in proxies:
                    if isinstance(p, dict) and p.get("server") == domain:
                        port = p.get("port")
                        break
            if port:
                result = check_tcp_connect(ip, int(port), timeout=5)
                print(f"   TCP {ip}:{port} → {result}")
        else:
            print(f"   ✗ 无法解析 {domain}")

    print(f"\n{'='*60}")
    print("诊断完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
