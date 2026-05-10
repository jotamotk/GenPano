from __future__ import annotations

from app.core.config import get_settings
from app.user_auth.jwt import _load_secret


def test_user_jwt_secret_loads_from_dotenv_when_env_var_missing(tmp_path, monkeypatch):
    secret = "dotenv-user-secret-at-least-32-bytes-long"
    (tmp_path / ".env").write_text(f"USER_JWT_SECRET={secret}\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("USER_JWT_SECRET", raising=False)
    get_settings.cache_clear()

    try:
        assert _load_secret() == secret
    finally:
        get_settings.cache_clear()
