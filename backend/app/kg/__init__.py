"""Phase K — Knowledge graph subsystem.

Public API:

    from app.kg import extract_relations
"""

from app.kg.relation_extractor import RELATION_PATTERNS, extract_relations

__all__ = ["RELATION_PATTERNS", "extract_relations"]
