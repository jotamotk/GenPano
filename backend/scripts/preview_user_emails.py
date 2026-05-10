"""Generate local HTML previews for product user transactional emails."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

from app.user_auth.email import (
    EmailContent,
    build_password_reset_email,
    build_verification_email,
    build_welcome_email,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "email_previews"


def _write_preview(filename: str, content: EmailContent) -> Path:
    path = OUT_DIR / filename
    path.write_text(
        f"<!-- Subject: {content.subject} -->\n{content.html}",
        encoding="utf-8",
    )
    return path


def _index(items: list[tuple[str, str, Path]]) -> str:
    links = "\n".join(
        (
            f'<li><a href="{escape(path.name)}">{escape(title)}</a>'
            f"<span>{escape(subject)}</span></li>"
        )
        for title, subject, path in items
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>GenPano Email Previews</title>
  <style>
    body {{
      margin: 0;
      padding: 48px;
      background: #fafafb;
      color: #030229;
      font: 14px/1.6 Arial, "Microsoft YaHei", sans-serif;
    }}
    main {{
      max-width: 760px;
      margin: 0 auto;
      background: #fff;
      border: 1px solid #e8e8f0;
      border-radius: 12px;
      padding: 28px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ margin: 0 0 22px; color: #6b7280; }}
    ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }}
    li {{ border: 1px solid #eef0f6; border-radius: 10px; padding: 14px 16px; }}
    a {{ display: block; color: #605bff; font-weight: 700; text-decoration: none; }}
    span {{ display: block; color: #818194; margin-top: 4px; }}
  </style>
</head>
<body>
  <main>
    <h1>GenPano Email Previews</h1>
    <p>本地静态预览, 不会发送真实邮件。</p>
    <ul>
      {links}
    </ul>
  </main>
</body>
</html>"""


def main() -> None:
    os.environ.setdefault("USER_BASE_URL", "http://127.0.0.1:5173")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    samples = [
        (
            "验证邮件 · 中文",
            "verify-email.zh-CN.html",
            build_verification_email(token="preview-token", locale="zh-CN"),
        ),
        (
            "验证邮件 · English",
            "verify-email.en-US.html",
            build_verification_email(token="preview-token", locale="en-US"),
        ),
        (
            "重置密码 · 中文",
            "reset-password.zh-CN.html",
            build_password_reset_email(token="preview-token", locale="zh-CN"),
        ),
        (
            "重置密码 · English",
            "reset-password.en-US.html",
            build_password_reset_email(token="preview-token", locale="en-US"),
        ),
        ("欢迎邮件 · 中文", "welcome.zh-CN.html", build_welcome_email(locale="zh-CN")),
        ("欢迎邮件 · English", "welcome.en-US.html", build_welcome_email(locale="en-US")),
    ]

    items: list[tuple[str, str, Path]] = []
    for title, filename, content in samples:
        path = _write_preview(filename, content)
        items.append((title, content.subject, path))

    index_path = OUT_DIR / "index.html"
    index_path.write_text(_index(items), encoding="utf-8")
    print(index_path)
    for _, _, path in items:
        print(path)


if __name__ == "__main__":
    main()
