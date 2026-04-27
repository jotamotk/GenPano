"""
添加测试账号到数据库
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from geo_tracker.config import get_async_session
from geo_tracker.db.models import LLMAccount, AccountStatus, Profile


async def add_test_accounts():
    async with get_async_session() as db:
        # 检查现有账号
        result = await db.execute(select(LLMAccount))
        accounts = result.scalars().all()
        print(f"现有账号数: {len(accounts)}")
        for a in accounts:
            print(f"  - {a.llm_name}: {a.email} (status: {a.status})")

        # 检查现有 profiles
        result = await db.execute(select(Profile))
        profiles = result.scalars().all()
        print(f"\n现有 Profiles: {len(profiles)}")
        profile_id = profiles[0].id if profiles else None

        if not profile_id:
            print("没有 profile，创建一个测试 profile...")
            profile = Profile(
                name="测试用户",
                age_range="25-34",
                location="Shanghai, CN",
                country_code="CN",
                profession="软件工程师",
                language="zh",
                device_type="desktop",
                persona_traits={"tone": "casual", "verbosity": "medium"},
            )
            db.add(profile)
            await db.commit()
            await db.refresh(profile)
            profile_id = profile.id
            print(f"创建 profile id={profile_id}")

        # 添加测试账号（实际使用时需要填写真实的 cookies）
        test_accounts = [
            # {
            #     "llm_name": "chatgpt",
            #     "email": "test-chatgpt@example.com",
            #     "password_encrypted": "",
            #     "cookies_json": None,  # 需要填入真实 cookies
            # },
            # {
            #     "llm_name": "gemini",
            #     "email": "test-gemini@example.com",
            #     "password_encrypted": "",
            #     "cookies_json": None,
            # },
            # {
            #     "llm_name": "kimi",
            #     "email": "test-kimi@example.com",
            #     "password_encrypted": "",
            #     "cookies_json": None,
            # },
        ]

        if test_accounts:
            for acc_data in test_accounts:
                # 检查是否已存在
                result = await db.execute(
                    select(LLMAccount).where(
                        LLMAccount.llm_name == acc_data["llm_name"],
                        LLMAccount.email == acc_data["email"],
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    print(f"账号已存在: {acc_data['llm_name']} - {acc_data['email']}")
                    continue

                acc = LLMAccount(
                    llm_name=acc_data["llm_name"],
                    email=acc_data["email"],
                    password_encrypted=acc_data["password_encrypted"],
                    cookies_json=acc_data.get("cookies_json"),
                    status=AccountStatus.ACTIVE.value,
                    profile_id=profile_id,
                    daily_limit=20,
                )
                db.add(acc)
                print(f"添加账号: {acc.llm_name} - {acc.email}")

            await db.commit()
            print("\n账号添加完成！")
        else:
            print("\n未配置测试账号数据，请编辑脚本添加真实账号/cookies")


if __name__ == "__main__":
    asyncio.run(add_test_accounts())
