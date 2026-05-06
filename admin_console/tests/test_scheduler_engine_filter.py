import admin_console.app as app_mod


class _RowsCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchall(self):
        return self.rows


def test_scheduler_capacity_ignores_hotspot_cookie_accounts():
    rows = [
        {
            "engine": "chatgpt",
            "account_total": 2,
            "account_active": 1,
            "daily_capacity": 50,
        },
        {
            "engine": "douyin_hots",
            "account_total": 1,
            "account_active": 1,
            "daily_capacity": 20,
        },
        {
            "engine": "xhs_hots",
            "account_total": 1,
            "account_active": 1,
            "daily_capacity": 20,
        },
        {
            "engine": "weibo_hots",
            "account_total": 1,
            "account_active": 1,
            "daily_capacity": 20,
        },
        {
            "engine": "doubao",
            "account_total": 3,
            "account_active": 3,
            "daily_capacity": 150,
        },
    ]

    capacity = app_mod._account_capacity_breakdown(_RowsCursor(rows))

    assert [item["engine"] for item in capacity] == ["chatgpt", "doubao"]
    assert sum(item["daily_capacity"] for item in capacity) == 200


def test_scheduler_config_normalizers_drop_hotspot_engines():
    paused = app_mod._normalize_scheduler_paused_engines(
        ["chatgpt", "douyin_hots", "xhs_hots", "chatgpt", "", None]
    )
    caps = app_mod._normalize_scheduler_engine_caps(
        {
            "chatgpt": "50",
            "douyin_hots": "20",
            "xhs_hots": None,
            "": 10,
        }
    )

    assert paused == ["chatgpt"]
    assert caps == {"chatgpt": 50}
