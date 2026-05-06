from geo_tracker.tasks import scheduler


class _RowsCursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self.rows


def test_scheduler_quotas_ignore_hotspot_cookie_accounts():
    rows = [
        {
            "account_id": 1,
            "engine": "chatgpt",
            "account_cap": 50,
            "profile_id": "101",
            "quota": 2,
        },
        {
            "account_id": 2,
            "engine": "douyin_hots",
            "account_cap": 20,
            "profile_id": "102",
            "quota": 1,
        },
        {
            "account_id": 3,
            "engine": "xhs_hots",
            "account_cap": 20,
            "profile_id": "103",
            "quota": 1,
        },
        {
            "account_id": 4,
            "engine": "weibo_hots",
            "account_cap": 20,
            "profile_id": "104",
            "quota": 1,
        },
    ]

    quotas = scheduler._quotas(_RowsCursor(rows), paused_engines=[])

    assert [row["engine"] for row in quotas] == ["chatgpt"]
