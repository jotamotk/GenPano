"""Phase K.5 — deterministic regex-based relation extractor.

Per PRD §4.3, relation candidates between brands / products are needed
to populate the KG. The plan calls for an LLM-driven extractor with
24h cache; this module provides a deterministic regex-based fallback
that ships first so the candidate review queue is non-empty pre-LLM.

Extraction strategy:
    For each (brand_a, brand_b) pair mentioned in the text, look for
    relationship cue phrases between them. Order matters: 'A vs B'
    triggers COMPETES_WITH, but 'A 收购 B' triggers SAME_GROUP with
    a directional hint (A is the parent).

Output: list of dicts each carrying
    {entity_kind, a_id, b_id, type, confidence, evidence}

The caller is expected to:
    1. Call `extract_relations(text, brand_index)` where `brand_index`
       maps brand names → brand_id.
    2. Stage each result into `kg_relation_candidates` with
       status='pending', `source='deterministic_v1'`.
    3. Admin reviews via `/api/admin/kg/candidates` (Phase K.3 admin
       sub-router; not yet shipped — this PR adds the producer).

LLM swap-in (Phase K.5 follow-up):
    Replace this module's body with a Doubao / DeepSeek call that
    returns the same dict shape. Keep `source='llm_v1'` to distinguish
    in evidence audits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Each pattern is a (regex, relation_type, confidence, directional)
# tuple. `directional=True` means a_id should refer to the LHS of the
# regex match (e.g., parent in SAME_GROUP); `False` means symmetric
# (COMPETES_WITH).
@dataclass(frozen=True)
class RelationPattern:
    pattern: re.Pattern[str]
    type: str
    confidence: float
    directional: bool


# Regex placeholders {a} and {b} are filled with brand-name fragments at
# match time. Patterns are evaluated in declared order; first match wins.
RELATION_PATTERNS: list[RelationPattern] = [
    # SAME_GROUP — directional (A 旗下 B = A parent of B)
    RelationPattern(
        re.compile(r"\b{a}\s*(?:旗下|收购|并购|是.*的子公司)\s*{b}\b"),
        type="SAME_GROUP",
        confidence=0.85,
        directional=True,
    ),
    RelationPattern(
        re.compile(r"\b{a}\s*owns\s*{b}\b", re.IGNORECASE),
        type="SAME_GROUP",
        confidence=0.85,
        directional=True,
    ),
    # COMPETES_WITH — symmetric
    RelationPattern(
        re.compile(r"\b{a}\s*(?:对比|vs\.?|对决|和|与)\s*{b}\b", re.IGNORECASE),
        type="COMPETES_WITH",
        confidence=0.75,
        directional=False,
    ),
    RelationPattern(
        re.compile(r"\b{a}\s+vs\s+{b}\b", re.IGNORECASE),
        type="COMPETES_WITH",
        confidence=0.85,
        directional=False,
    ),
    # SUBSTITUTES — directional (A is alternative for B)
    # "A 是 B 的平替" / "A 是 B 平替" (most common Chinese phrasing)
    RelationPattern(
        re.compile(r"\b{a}\s*是\s*{b}\s*(?:的)?\s*(?:平替|平价替代|替代品)\b"),
        type="SUBSTITUTES",
        confidence=0.85,
        directional=True,
    ),
    # "A 平替 B" (less common; LHS replaces RHS)
    RelationPattern(
        re.compile(r"\b{a}\s*(?:平替|平价替代)\s*{b}\b"),
        type="SUBSTITUTES",
        confidence=0.75,
        directional=True,
    ),
    # UPGRADES_TO — directional (A upgraded to B)
    RelationPattern(
        re.compile(r"\b{a}\s*(?:升级到|换成了|换到了|进化到了?)\s*{b}\b"),
        type="UPGRADES_TO",
        confidence=0.75,
        directional=True,
    ),
    # PAIRS_WITH — symmetric
    # Note: \b at the end can't match before Chinese chars (CJK isn't word
    # boundary), so use lookahead to allow either word-boundary or CJK.
    RelationPattern(
        re.compile(r"\b{a}\s*(?:搭配|配合|和)\s*{b}\s*(?:一起|搭|搭配使用)"),
        type="PAIRS_WITH",
        confidence=0.70,
        directional=False,
    ),
]


def _escape(name: str) -> str:
    """Return a regex-safe brand name fragment."""
    return re.escape(name)


def extract_relations(
    text: str,
    *,
    brand_index: dict[str, int],
    entity_kind: str = "brand",
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """Scan `text` for brand-pair relation cues.

    Args:
        text: free-form text to scan (e.g., LLM response body)
        brand_index: mapping brand name → brand_id (case-insensitive
            lookup keys recommended; we lowercase before lookup)
        entity_kind: 'brand' (default) or 'product'
        source_id: optional response_id / document_id passed through
            in the evidence dict for traceability

    Returns:
        List of candidate dicts. Each carries:
            entity_kind / a_id / b_id / type / confidence /
            evidence={text_snippet, pattern_type, source_id}

        Duplicates (same a_id, b_id, type) are deduplicated keeping
        the highest-confidence match.
    """
    if not text or not brand_index:
        return []

    # Normalize lookup keys
    name_to_id = {name.lower(): bid for name, bid in brand_index.items()}
    names = sorted(brand_index.keys(), key=len, reverse=True)

    # First, find every brand mention with offset
    mentions: list[tuple[int, str, int]] = []  # (offset, name, brand_id)
    for name in names:
        for m in re.finditer(_escape(name), text, re.IGNORECASE):
            mentions.append((m.start(), name, name_to_id[name.lower()]))

    if len(mentions) < 2:
        return []

    candidates: dict[tuple[int, int, str], dict[str, Any]] = {}

    for pat in RELATION_PATTERNS:
        # Replace {a} and {b} placeholders with brand alternation
        all_names_re = "|".join(_escape(n) for n in names)
        try:
            template = pat.pattern.pattern
            concrete = template.replace("{a}", f"(?P<a>{all_names_re})").replace(
                "{b}", f"(?P<b>{all_names_re})"
            )
            concrete_re = re.compile(concrete, pat.pattern.flags)
        except re.error:
            continue

        for m in concrete_re.finditer(text):
            a_name = m.group("a")
            b_name = m.group("b")
            a_id = name_to_id.get(a_name.lower())
            b_id = name_to_id.get(b_name.lower())
            if a_id is None or b_id is None or a_id == b_id:
                continue

            # Order pair: directional keeps (a, b); symmetric uses sorted ids
            if pat.directional:
                key = (a_id, b_id, pat.type)
            else:
                lo, hi = sorted([a_id, b_id])
                key = (lo, hi, pat.type)

            snippet = text[max(0, m.start() - 30) : min(len(text), m.end() + 30)]
            ev = {
                "text_snippet": snippet.strip(),
                "pattern_type": pat.type,
                "matched": m.group(0),
            }
            if source_id is not None:
                ev["source_id"] = source_id

            existing = candidates.get(key)
            if existing is None or pat.confidence > existing["confidence"]:
                candidates[key] = {
                    "entity_kind": entity_kind,
                    "a_id": key[0],
                    "b_id": key[1],
                    "type": pat.type,
                    "confidence": pat.confidence,
                    "evidence": ev,
                }

    return list(candidates.values())
