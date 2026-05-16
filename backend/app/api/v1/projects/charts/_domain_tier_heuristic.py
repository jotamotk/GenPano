"""Heuristic classifier for citation-source domains lacking an explicit
`domain_authorities` tier row.

Issue #1020 root cause: `domain_authorities` is a manually-curated table.
Live test envs ship without per-project tier rows, so the charts service's
``outerjoin(DomainAuthority, ...)`` returns ``tier IS NULL`` for every
citation. The `/brand/citations` donut consequently displays 100% as the
``未分类`` (untiered) bucket.

This module provides a *project-agnostic* fallback: a deterministic
classifier that maps a `domain` to a Tier 1-4 bucket using a brand-alias
match plus a small set of well-known authority and KOL hosts. The result
is applied ephemerally in the chart helpers — we never write back to
`domain_authorities`, so the curated data path remains canonical.

Forbidden by issue #1020:
- Do NOT silently coerce all untiered → Tier 4 (loses real "untiered"
  signal). When the domain is empty / None, this returns ``None``.
- Do NOT hand-write rules per project. Stick to alias-driven Tier 1 +
  generic authority/KOL set.
"""

from __future__ import annotations

from collections.abc import Iterable

# Authoritative news / institutional hosts.
#
# The Tier 2 set is intentionally extracted as a module constant so it can
# grow without touching the classification logic. Entries are lower-cased
# bare hostnames (no scheme, no leading dot).
_TIER_2_AUTHORITY_HOSTS: frozenset[str] = frozenset(
    {
        # Tech / business press
        "ibm.com",
        "mediacenter.ibm.com",
        "reuters.com",
        "bloomberg.com",
        "wsj.com",
        "nytimes.com",
        "forbes.com",
        "wired.com",
        "theguardian.com",
        "bbc.com",
        "bbc.co.uk",
        # Chinese state / mainstream media
        "xinhuanet.com",
        "people.com.cn",
        "cctv.com",
        "chinadaily.com.cn",
    }
)

# Domain suffixes that indicate institutional/authority sources. Matched on
# `domain.endswith("." + suffix)` OR `domain == suffix`.
_TIER_2_AUTHORITY_SUFFIXES: tuple[str, ...] = (
    "gov",
    "gov.cn",
    "edu",
    "edu.cn",
)

# Known KOL / blog / social platforms.
_TIER_3_KOL_HOSTS: frozenset[str] = frozenset(
    {
        "zhihu.com",
        "xiaohongshu.com",
        "weibo.com",
        "medium.com",
        "linkedin.com",
        "youtube.com",
        "bilibili.com",
        "douyin.com",
        "tiktok.com",
    }
)


def _normalize_domain(domain: str | None) -> str | None:
    if domain is None:
        return None
    value = str(domain).strip().lower()
    if not value:
        return None
    # Strip a single leading ``www.`` so cosmetic prefixes don't break the
    # authority/KOL lookups. We do NOT strip arbitrary subdomain depths
    # because endswith-style matching already covers e.g.
    # ``mediacenter.ibm.com`` (listed explicitly) or ``foo.gov.cn``.
    if value.startswith("www."):
        value = value[4:]
    return value or None


def _normalize_alias(alias: str | None) -> str | None:
    if alias is None:
        return None
    value = str(alias).strip().lower()
    return value or None


def _matches_brand_alias(domain: str, aliases: Iterable[str]) -> bool:
    """Return True when ``domain`` belongs to a brand alias.

    A match occurs when:
    - the alias appears as a label in ``domain`` (e.g. alias ``bestcoffer``
      matches ``bestcoffer.com``, ``bestcoffer.cn``, ``www.bestcoffer.com``);
    - the alias *is* ``domain`` (covers cases where the alias itself is a
      full hostname).
    """
    for raw in aliases:
        alias = _normalize_alias(raw)
        if not alias:
            continue
        if alias == domain:
            return True
        # ``alias.`` prefix → alias is the first label of the domain
        if domain.startswith(f"{alias}."):
            return True
        # ``.alias.`` infix or ``.alias`` TLD-style suffix → embedded label
        if f".{alias}." in domain or domain.endswith(f".{alias}"):
            return True
    return False


def _matches_suffix(domain: str, suffixes: Iterable[str]) -> bool:
    for raw in suffixes:
        suffix = _normalize_alias(raw)
        if not suffix:
            continue
        if domain == suffix or domain.endswith(f".{suffix}"):
            return True
    return False


def _classify_untiered_domain(
    domain: str | None,
    brand_aliases: list[str] | None,
) -> int | None:
    """Classify an untiered citation domain into a tier bucket.

    Rules (first match wins):
    1. ``domain`` matches an entry in ``brand_aliases`` (label or full
       hostname) → **Tier 1** (official).
    2. ``domain`` is / ends with a ``_TIER_2_AUTHORITY_SUFFIXES`` entry
       (``.gov``/``.gov.cn``/``.edu``/``.edu.cn``) OR appears in
       ``_TIER_2_AUTHORITY_HOSTS`` (well-known news / institutional press)
       → **Tier 2**.
    3. ``domain`` appears in ``_TIER_3_KOL_HOSTS`` (KOL/blog platforms) →
       **Tier 3**.
    4. Otherwise → **Tier 4** (UGC / long-tail).

    When ``domain`` is genuinely unknown (None / empty after trim) the
    classifier returns ``None``. The caller is expected to keep the
    contribution in the ``未分类`` bucket so the original "untiered"
    signal is preserved (issue #1020 forbids silent coercion to Tier 4).
    """
    normalized = _normalize_domain(domain)
    if normalized is None:
        return None

    aliases = brand_aliases or []
    if _matches_brand_alias(normalized, aliases):
        return 1
    if _matches_suffix(normalized, _TIER_2_AUTHORITY_SUFFIXES):
        return 2
    if normalized in _TIER_2_AUTHORITY_HOSTS:
        return 2
    if normalized in _TIER_3_KOL_HOSTS:
        return 3
    return 4


__all__ = [
    "_TIER_2_AUTHORITY_HOSTS",
    "_TIER_2_AUTHORITY_SUFFIXES",
    "_TIER_3_KOL_HOSTS",
    "_classify_untiered_domain",
]
