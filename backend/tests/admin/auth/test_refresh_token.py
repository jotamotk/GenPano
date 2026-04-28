"""Refresh token primitives — 8 cases.

Covers token generation entropy + length, sha256 determinism, and every
short-circuit / safe-failure of `constant_time_equal_hex`.
"""

from __future__ import annotations

from hashlib import sha256

from app.admin.auth.refresh_token import (
    constant_time_equal_hex,
    generate_refresh_token,
    hash_refresh_token,
)


def test_generate_returns_token_and_hash() -> None:
    bundle = generate_refresh_token()
    assert isinstance(bundle.token, str)
    assert len(bundle.token) >= 40  # token_urlsafe(32) ≈ 43 chars
    assert len(bundle.hash_hex) == 64  # sha256 hex
    assert int(bundle.hash_hex, 16) >= 0  # well-formed hex


def test_generate_is_unique_across_calls() -> None:
    pairs = {generate_refresh_token().token for _ in range(20)}
    assert len(pairs) == 20


def test_hash_refresh_token_matches_sha256() -> None:
    token = "fixed-token-for-hashing"
    expected = sha256(token.encode("utf-8")).hexdigest()
    assert hash_refresh_token(token) == expected


def test_hash_round_trip_with_generate() -> None:
    bundle = generate_refresh_token()
    assert hash_refresh_token(bundle.token) == bundle.hash_hex


def test_equal_hex_true_when_match() -> None:
    h = sha256(b"abc").hexdigest()
    assert constant_time_equal_hex(h, h) is True


def test_equal_hex_false_on_length_mismatch() -> None:
    a = sha256(b"abc").hexdigest()
    b = a[:-1]  # 63 chars
    assert constant_time_equal_hex(a, b) is False


def test_equal_hex_false_on_value_mismatch_same_length() -> None:
    a = sha256(b"abc").hexdigest()
    b = sha256(b"def").hexdigest()
    assert constant_time_equal_hex(a, b) is False


def test_equal_hex_false_on_non_hex_chars() -> None:
    a = sha256(b"abc").hexdigest()
    b = "z" * 64  # same length, but not hex
    assert constant_time_equal_hex(a, b) is False
