"""
Camoufox browser fingerprint persistence for SMS-registered accounts.

Refs #963 production evidence (server-diagnostics run 25951168887,
account 39 lifecycle 03:01:46 → 03:03:15 → 03:04:25): every Camoufox
launch generates a fresh random Firefox fingerprint (user-agent, screen
resolution, fonts, WebGL/Canvas seed, ...). The auto_login flow uses
fingerprint A to register and pull cookies; the next query opens a new
Camoufox instance with fingerprint B and injects A's cookies. Doubao's
session validator sees a mismatch between the cookie-bound fingerprint
and the current request fingerprint and treats the session as logged
out — so accounts ricochet active → expired within seconds of auto-login
success.

Persisting the Fingerprint object alongside cookies eliminates the drift:
auto_login generates and saves the fingerprint, every subsequent query
reuses it via Camoufox's ``fingerprint=...`` launch option.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from browserforge.fingerprints import Fingerprint, FingerprintGenerator
    _BROWSERFORGE_AVAILABLE = True
except ImportError:
    Fingerprint = None  # type: ignore[assignment,misc]
    FingerprintGenerator = None  # type: ignore[assignment,misc]
    _BROWSERFORGE_AVAILABLE = False


FINGERPRINT_PAYLOAD_KEY = "camoufoxFingerprint"


def is_available() -> bool:
    return _BROWSERFORGE_AVAILABLE


def generate_doubao_fingerprint() -> Optional["Fingerprint"]:
    """Generate a fresh Firefox/Windows fingerprint suitable for Doubao."""
    if not _BROWSERFORGE_AVAILABLE:
        return None
    try:
        return FingerprintGenerator().generate(browser="firefox", os="windows")
    except Exception as exc:
        logger.warning("Fingerprint generation failed: %s", exc)
        return None


def serialize_fingerprint(fingerprint: Any) -> Optional[dict]:
    """Convert a Fingerprint dataclass into a JSON-safe dict, or None."""
    if fingerprint is None or not _BROWSERFORGE_AVAILABLE:
        return None
    try:
        return dataclasses.asdict(fingerprint)
    except Exception as exc:
        logger.warning("Fingerprint serialization failed: %s", exc)
        return None


def deserialize_fingerprint(payload: Any) -> Optional["Fingerprint"]:
    """Rebuild a Fingerprint dataclass from a dict payload, or None on any error.

    A failure here must not crash the caller — fingerprint persistence is a
    pure optimisation: if deserialization fails, the caller falls back to a
    freshly-generated random fingerprint, which is the pre-persistence
    behaviour. The account just loses its fingerprint stability for one
    cycle until the next auto_login refresh.
    """
    if not payload or not _BROWSERFORGE_AVAILABLE:
        return None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception as exc:
            logger.warning("Fingerprint JSON decode failed: %s", exc)
            return None
    if not isinstance(payload, dict):
        return None
    try:
        return _rebuild_dataclass(Fingerprint, payload)
    except Exception as exc:
        logger.warning("Fingerprint deserialization failed: %s", exc)
        return None


def _rebuild_dataclass(cls, data):
    """Recursively reconstruct nested dataclasses from a plain-dict payload."""
    if data is None:
        return None
    if not dataclasses.is_dataclass(cls):
        return data
    if not isinstance(data, dict):
        return data
    kwargs = {}
    for field in dataclasses.fields(cls):
        if field.name not in data:
            continue
        field_value = data[field.name]
        field_type = field.type
        if dataclasses.is_dataclass(field_type):
            kwargs[field.name] = _rebuild_dataclass(field_type, field_value)
        else:
            kwargs[field.name] = field_value
    return cls(**kwargs)


def extract_fingerprint_from_account_cookies(
    account_cookies_payload: Any,
) -> Optional["Fingerprint"]:
    """Extract a Camoufox Fingerprint from an account's ``cookies_json`` payload.

    Accepts either the parsed-dict form (new account format with
    ``cookies`` + ``localStorage`` + ``storageState`` + ``camoufoxFingerprint``
    keys) or a raw JSON string. Returns ``None`` for legacy list-only
    payloads, missing keys, or any deserialization error so the caller can
    safely fall back to a fresh random fingerprint.
    """
    if not account_cookies_payload:
        return None
    payload: Any = account_cookies_payload
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    return deserialize_fingerprint(payload.get(FINGERPRINT_PAYLOAD_KEY))


def attach_fingerprint_to_login_result(
    result: dict,
    fingerprint: Any,
) -> dict:
    """Add the serialized fingerprint to a login_or_register result dict.

    No-op when the fingerprint or result is missing. The result dict is
    mutated in place and also returned for chaining.
    """
    if not isinstance(result, dict):
        return result
    serialized = serialize_fingerprint(fingerprint)
    if serialized is not None:
        result[FINGERPRINT_PAYLOAD_KEY] = serialized
    return result
