from pathlib import Path

import admin_console.app as app_mod


def test_database_url_env_configures_admin_db(monkeypatch):
    original_url = app_mod.DATABASE_URL
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.local:6543/admin_db")
    try:
        app_mod._configure_database_url_from_env()
        assert app_mod.DB_USER == "user"
        assert app_mod.DB_PASS == "pass"
        assert app_mod.DB_HOST == "db.local"
        assert app_mod.DB_PORT == "6543"
        assert app_mod.DB_NAME == "admin_db"
    finally:
        app_mod._configure_database_url(original_url)


def test_database_url_env_is_applied_before_startup_migrations():
    source = Path(app_mod.__file__).read_text(encoding="utf-8")
    env_call = source.index("_configure_database_url_from_env()")
    migration_guard = source.index('if os.getenv("ADMIN_CONSOLE_SKIP_STARTUP_MIGRATIONS")')
    assert env_call < migration_guard
