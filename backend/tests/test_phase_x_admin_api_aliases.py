import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/admin/api/admin/brands",
        "/admin/api/topics",
        "/admin/api/prompts",
        "/admin/api/profiles/lite",
        "/admin/api/scheduler/schedules",
    ],
)
async def test_admin_api_aliases_do_not_fall_through_to_spa_shell(client, path: str) -> None:
    resp = await client.get(path)

    assert resp.status_code == 401
    assert "text/html" not in resp.headers.get("content-type", "")
