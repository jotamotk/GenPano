"""Numeric format helpers for analytics contract values.

Phase 2 of splitting `_analytics_contract.py` (Epic #885, design #888).
"""

from __future__ import annotations


def ratio_decimal(value: float | int | None) -> float | None:
    """Normalize ratio-like values to 0..1.

    Legacy aggregate rows may already store percent-like values such as 38.4.
    The project APIs expose ratio series as decimals, so those are converted to
    0.384 while existing decimal rows remain unchanged.
    """
    if value is None:
        return None
    raw = float(value)
    if abs(raw) > 1.0 and abs(raw) <= 100.0:
        raw = raw / 100.0
    return round(raw, 4)


def percent_display(value: float | int | None) -> float:
    if value is None:
        return 0.0
    raw = float(value)
    if abs(raw) > 100.0 and abs(raw) <= 10000.0:
        raw = raw / 100.0
    decimal = ratio_decimal(raw)
    if decimal is None:
        return 0.0
    return round(decimal * 100.0, 1)


def score_0_100(value: float | int | None) -> float | None:
    if value is None:
        return None
    raw = float(value)
    if 0.0 <= raw <= 1.0:
        raw *= 100.0
    return round(raw, 2)
