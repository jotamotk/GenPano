#!/usr/bin/env python3
"""
LubanSMS 本地命令行工具

三个核心命令:
  get-phone    获取手机号（随机或指定复用）
  get-sms      轮询等待验证码
  release      释放手机号

使用流程:
  1. python scripts/luban_tool.py get-phone
     → 拿到手机号，手动填入 DeepSeek 登录页面

  2. 在 DeepSeek 页面点击"获取验证码"后:
     python scripts/luban_tool.py get-sms --phone 13800138000 --keyword 深度求索

  3. 拿到验证码，手动填入页面完成登录

  4. 登录成功后导出 cookies，然后释放号码:
     python scripts/luban_tool.py release --phone 13800138000

环境变量:
  LUBANSMS_TOKEN  接码平台 API Key（必须）

快捷用法（交互式全流程）:
  python scripts/luban_tool.py interactive --keyword 深度求索
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

try:
    import httpx
except ImportError:
    print("需要安装 httpx: pip install httpx")
    sys.exit(1)

LUBANSMS_BASE = "https://lubansms.com/v2/api"
TOKEN = os.getenv("LUBANSMS_TOKEN", "YOUR_LUBANSMS_TOKEN_HERE")

# ─── 同步 API 封装 ──────────────────────────────────────────────────────────


def _get(endpoint: str, params: dict) -> dict:
    params["apikey"] = TOKEN
    resp = httpx.get(f"{LUBANSMS_BASE}/{endpoint}", params=params, timeout=30)
    data = resp.json()
    return data


def get_phone(phone: str | None = None) -> str:
    """获取手机号"""
    params = {}
    if phone:
        params["phone"] = phone
    data = _get("getKeywordNumber", params)
    if data.get("code") != 0:
        print(f"❌ 获取手机号失败: {data}")
        sys.exit(1)
    result = data["phone"]
    print(f"✅ 手机号: {result}")
    return result


def get_sms(phone: str, keyword: str, timeout: int = 120) -> str:
    """轮询等待验证码"""
    print(f"⏳ 等待验证码 (手机号={phone}, 关键词={keyword}, 超时={timeout}s)...")
    waited = 0
    interval = 3
    while waited < timeout:
        data = _get("getKeywordSms", {"phone": phone, "keyword": keyword})
        if data.get("code") == 0 and data.get("msg"):
            msg = data["msg"]
            print(f"📩 收到短信: {msg}")
            match = re.search(r"(\d{4,8})", msg)
            if match:
                code = match.group(1)
                print(f"✅ 验证码: {code}")
                return code
            print(f"⚠️  无法从短信中提取验证码: {msg}")
            return ""

        if data.get("code") == 400 and "apikey" in data.get("msg", "").lower():
            print(f"❌ API 认证失败: {data}")
            sys.exit(1)

        time.sleep(interval)
        waited += interval
        if waited % 15 == 0:
            print(f"   ... 已等待 {waited}s/{timeout}s")

    print(f"❌ 等待超时 ({timeout}s)")
    return ""


def release_phone(phone: str) -> None:
    """释放手机号"""
    data = _get("delKeywordNumber", {"phone": phone})
    print(f"✅ 释放号码 {phone}: {data}")


def get_balance() -> None:
    """查询余额"""
    data = _get("getBalance", {})
    if data.get("code") != 0:
        print(f"❌ 查询失败: {data}")
        return
    print(f"💰 余额: {data['balance']}")


def interactive(keyword: str, timeout: int = 120) -> None:
    """交互式全流程"""
    print("=" * 50)
    print("  LubanSMS 手动登录辅助工具")
    print("=" * 50)

    get_balance()
    print()

    # Step 1: 获取手机号
    reuse = input("复用已有手机号? (直接输入号码，或按回车随机获取): ").strip()
    phone = get_phone(reuse if reuse else None)
    print()

    # Step 2: 提示用户操作
    print("📋 操作步骤:")
    print(f"   1. 在浏览器打开 DeepSeek 登录页面")
    print(f"   2. 输入手机号: {phone}")
    print(f"   3. 点击「获取验证码」")
    print()
    input("完成上述操作后按回车继续...")
    print()

    # Step 3: 等待验证码
    code = get_sms(phone, keyword, timeout)
    if not code:
        print("未获取到验证码，流程终止")
        release_phone(phone)
        return
    print()

    # Step 4: 提示输入验证码
    print(f"📋 请在浏览器中输入验证码: {code}")
    print(f"   然后完成登录")
    print()
    input("登录成功后按回车继续...")
    print()

    # Step 5: 导出 cookies 提示
    print("📋 导出 Cookies:")
    print("   方式1 - 浏览器 Console 执行:")
    print("   copy(JSON.stringify(document.cookie.split('; ').map(c => {")
    print("     const [name, ...v] = c.split('=');")
    print("     return {name, value: v.join('='), domain: '.deepseek.com', path: '/'};")
    print("   })))")
    print()
    print("   方式2 - 使用 EditThisCookie 扩展导出")
    print()
    print(f"   保存为 JSON 文件后运行:")
    print(f"   python scripts/import_cookies.py cookies.json --platform deepseek")
    print()

    # Step 6: 释放号码
    do_release = input("是否释放号码? (y/N): ").strip().lower()
    if do_release == "y":
        release_phone(phone)
    else:
        print(f"保留号码 {phone}，后续可手动释放:")
        print(f"  python scripts/luban_tool.py release --phone {phone}")

    print()
    print("✅ 完成!")


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main():
    if not TOKEN:
        print("❌ 请设置环境变量 LUBANSMS_TOKEN")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="LubanSMS 本地命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s get-phone                          # 随机获取手机号
  %(prog)s get-phone --phone 13800138000      # 复用指定号码
  %(prog)s get-sms --phone 13800138000 --keyword 深度求索
  %(prog)s release --phone 13800138000
  %(prog)s balance                            # 查询余额
  %(prog)s interactive --keyword 深度求索      # 交互式全流程
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # get-phone
    p_phone = sub.add_parser("get-phone", help="获取手机号")
    p_phone.add_argument("--phone", help="复用指定手机号")

    # get-sms
    p_sms = sub.add_parser("get-sms", help="轮询等待验证码")
    p_sms.add_argument("--phone", required=True, help="手机号")
    p_sms.add_argument("--keyword", required=True, help="短信关键词 (如: 深度求索)")
    p_sms.add_argument("--timeout", type=int, default=120, help="超时秒数 (默认120)")

    # release
    p_rel = sub.add_parser("release", help="释放手机号")
    p_rel.add_argument("--phone", required=True, help="手机号")

    # balance
    sub.add_parser("balance", help="查询余额")

    # interactive
    p_inter = sub.add_parser("interactive", help="交互式全流程")
    p_inter.add_argument("--keyword", default="深度求索", help="短信关键词 (默认: 深度求索)")
    p_inter.add_argument("--timeout", type=int, default=120, help="超时秒数 (默认120)")

    args = parser.parse_args()

    if args.command == "get-phone":
        get_phone(args.phone)
    elif args.command == "get-sms":
        get_sms(args.phone, args.keyword, args.timeout)
    elif args.command == "release":
        release_phone(args.phone)
    elif args.command == "balance":
        get_balance()
    elif args.command == "interactive":
        interactive(args.keyword, args.timeout)


if __name__ == "__main__":
    main()
