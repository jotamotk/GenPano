import json

from geo_tracker.hotspots.browser import parse_cookie_payload


def test_parse_cookie_payload_accepts_plain_cookie_list():
    cookies, local_storage = parse_cookie_payload(json.dumps([{"name": "sid", "value": "1"}]))

    assert cookies == [{"name": "sid", "value": "1"}]
    assert local_storage == {}


def test_parse_cookie_payload_accepts_admin_resource_wrapper():
    cookies, local_storage = parse_cookie_payload(
        json.dumps({
            "cookies": [{"name": "web_session", "value": "ok"}],
            "localStorage": {"token": "abc"},
        })
    )

    assert cookies == [{"name": "web_session", "value": "ok"}]
    assert local_storage == {"token": "abc"}
