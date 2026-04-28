"""JWT module unit tests — 7 cases.

Covers boot-time secret discipline, sign/verify happy path, and the four
failure-reason branches of `AdminJwtInvalidError`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt as jose_jwt  # type: ignore[import-untyped]

from app.admin.auth import jwt as admin_jwt
from app.admin.auth.constants import (
    ACCESS_TOKEN_TTL_SECONDS,
    JWT_ALGORITHM,
    JWT_AUDIENCE_ACCESS,
    JWT_ISSUER,
)

_SECRET = "x" * 48  # 48 bytes ≥ 32-byte floor


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_JWT_SECRET", _SECRET)


def test_missing_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_JWT_SECRET", raising=False)
    with pytest.raises(admin_jwt.AdminJwtSecretMissingError):
        admin_jwt.sign_access_token(admin_user_id="u-1")


def test_short_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_JWT_SECRET", "x" * 31)  # one byte short
    with pytest.raises(admin_jwt.AdminJwtSecretMissingError):
        admin_jwt.sign_access_token(admin_user_id="u-1")


def test_sign_and_verify_round_trip() -> None:
    token, payload = admin_jwt.sign_access_token(admin_user_id="u-42")
    decoded = admin_jwt.verify_access_token(token)
    assert decoded.sub == "u-42"
    assert decoded.jti == payload.jti
    assert decoded.iss == JWT_ISSUER
    assert decoded.aud == JWT_AUDIENCE_ACCESS
    assert decoded.exp - decoded.iat == ACCESS_TOKEN_TTL_SECONDS


def test_expired_token_raises_expired() -> None:
    past = datetime.now(UTC) - timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS + 60)
    token, _ = admin_jwt.sign_access_token(admin_user_id="u-1", now=past)
    with pytest.raises(admin_jwt.AdminJwtInvalidError) as exc:
        admin_jwt.verify_access_token(token)
    assert exc.value.reason == "expired"


def test_bad_signature_raises_signature() -> None:
    token, _ = admin_jwt.sign_access_token(admin_user_id="u-1")
    # flip the last char of the signature segment (3rd dot-segment)
    head, _, sig = token.rpartition(".")
    flipped = head + "." + ("A" if sig[-1] != "A" else "B") + sig[:-1]
    with pytest.raises(admin_jwt.AdminJwtInvalidError) as exc:
        admin_jwt.verify_access_token(flipped)
    assert exc.value.reason == "signature"


def test_malformed_token_raises_malformed() -> None:
    with pytest.raises(admin_jwt.AdminJwtInvalidError) as exc:
        admin_jwt.verify_access_token("not-a-jwt")
    assert exc.value.reason == "malformed"


def test_wrong_audience_raises_claims() -> None:
    # Mint a token with a foreign audience using the same secret/algo,
    # so signature is valid but the audience claim mismatches.
    now = datetime.now(UTC)
    payload = {
        "sub": "u-1",
        "jti": "j-1",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=300)).timestamp()),
        "iss": JWT_ISSUER,
        "aud": "some-other-audience",
    }
    token = jose_jwt.encode(payload, _SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(admin_jwt.AdminJwtInvalidError) as exc:
        admin_jwt.verify_access_token(token)
    assert exc.value.reason == "claims"
