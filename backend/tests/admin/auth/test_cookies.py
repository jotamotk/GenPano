"""Cookie helpers — 11 cases.

Verifies attribute discipline (HttpOnly + SameSite=Strict + Path=/admin),
TTL routing per cookie, secure flag pass-through, clear-cookies behaviour,
and RFC 6265 string serialisation.
"""

from __future__ import annotations

from starlette.responses import Response

from app.admin.auth.constants import (
    ACCESS_TOKEN_COOKIE,
    ACCESS_TOKEN_TTL_SECONDS,
    COOKIE_PATH,
    REFRESH_TOKEN_COOKIE,
    REFRESH_TOKEN_TTL_SECONDS,
)
from app.admin.auth.cookies import (
    clear_auth_cookies,
    serialize_set_cookie,
    set_access_token_cookie,
    set_refresh_token_cookie,
)


def _set_cookie_strings(response: Response) -> list[str]:
    out: list[str] = []
    for k, v in response.raw_headers:
        if k == b"set-cookie":
            out.append(v.decode("latin-1") if isinstance(v, bytes) else v)
    return out


def test_access_cookie_has_httponly_strict_path() -> None:
    response = Response()
    set_access_token_cookie(response, "abc.def.ghi", secure=False)
    [header] = _set_cookie_strings(response)
    assert header.startswith(f"{ACCESS_TOKEN_COOKIE}=abc.def.ghi")
    assert "HttpOnly" in header
    assert "samesite=strict" in header.lower()
    assert f"Path={COOKIE_PATH}" in header


def test_access_cookie_max_age_matches_ttl() -> None:
    response = Response()
    set_access_token_cookie(response, "tok", secure=False)
    [header] = _set_cookie_strings(response)
    assert f"Max-Age={ACCESS_TOKEN_TTL_SECONDS}" in header


def test_access_cookie_secure_flag_off_in_dev() -> None:
    response = Response()
    set_access_token_cookie(response, "tok", secure=False)
    [header] = _set_cookie_strings(response)
    assert "Secure" not in header


def test_access_cookie_secure_flag_on_in_prod() -> None:
    response = Response()
    set_access_token_cookie(response, "tok", secure=True)
    [header] = _set_cookie_strings(response)
    assert "Secure" in header


def test_refresh_cookie_uses_refresh_ttl_not_access_ttl() -> None:
    response = Response()
    set_refresh_token_cookie(response, "rtok", secure=False)
    [header] = _set_cookie_strings(response)
    assert header.startswith(f"{REFRESH_TOKEN_COOKIE}=rtok")
    assert f"Max-Age={REFRESH_TOKEN_TTL_SECONDS}" in header
    assert f"Max-Age={ACCESS_TOKEN_TTL_SECONDS}" not in header


def test_refresh_cookie_has_strict_attributes() -> None:
    response = Response()
    set_refresh_token_cookie(response, "rtok", secure=True)
    [header] = _set_cookie_strings(response)
    assert "HttpOnly" in header
    assert "samesite=strict" in header.lower()
    assert f"Path={COOKIE_PATH}" in header
    assert "Secure" in header


def test_clear_auth_cookies_emits_two_max_age_zero_headers() -> None:
    response = Response()
    clear_auth_cookies(response)
    headers = _set_cookie_strings(response)
    assert len(headers) == 2
    names = {h.split("=", 1)[0] for h in headers}
    assert names == {ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE}
    for h in headers:
        assert "Max-Age=0" in h
        assert f"Path={COOKIE_PATH}" in h


def test_serialize_set_cookie_emits_expected_attributes() -> None:
    s = serialize_set_cookie("custom", "v1", max_age=60, secure=True)
    assert s.startswith("custom=v1;")
    assert f"Path={COOKIE_PATH}" in s
    assert "Max-Age=60" in s
    assert "HttpOnly" in s
    assert "SameSite=Strict" in s
    assert "Secure" in s


def test_serialize_set_cookie_omits_secure_when_false() -> None:
    s = serialize_set_cookie("custom", "v1", max_age=60, secure=False)
    assert "Secure" not in s
    assert "HttpOnly" in s
    assert "SameSite=Strict" in s


def test_set_both_cookies_in_one_response() -> None:
    response = Response()
    set_access_token_cookie(response, "atok", secure=True)
    set_refresh_token_cookie(response, "rtok", secure=True)
    headers = _set_cookie_strings(response)
    assert len(headers) == 2
    assert any(ACCESS_TOKEN_COOKIE in h for h in headers)
    assert any(REFRESH_TOKEN_COOKIE in h for h in headers)


def test_clear_path_matches_set_path_for_browser_eviction() -> None:
    """Browsers only evict cookies whose Path matches the original. The
    Path on a clear must equal the Path on the corresponding set."""

    set_resp = Response()
    set_access_token_cookie(set_resp, "tok", secure=True)
    [set_header] = _set_cookie_strings(set_resp)

    clear_resp = Response()
    clear_auth_cookies(clear_resp)
    headers = _set_cookie_strings(clear_resp)
    access_clear = next(h for h in headers if h.startswith(ACCESS_TOKEN_COOKIE))

    set_path = next(
        part for part in set_header.split("; ") if part.startswith("Path=")
    )
    clear_path = next(
        part for part in access_clear.split("; ") if part.startswith("Path=")
    )
    assert set_path == clear_path
