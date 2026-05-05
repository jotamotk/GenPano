"""CSV renderer for report payloads.

Emits one CSV per section, joined with section header lines. The
`tables[*].rows` of each section become CSV bodies; sections without
tables are skipped.
"""

from __future__ import annotations

import csv
import io
from typing import Any


def render_csv(payload: dict[str, Any]) -> str:
    """Render section tables to a single multi-section CSV string."""
    out = io.StringIO()

    sections = payload.get("sections", [])
    for sec in sections:
        tables = sec.get("tables") or []
        if not tables:
            continue
        section_label = sec.get("title", sec.get("section_type", "section"))
        out.write(f"# {section_label}\n")
        for table in tables:
            rows = table.get("rows") or []
            if not rows:
                continue
            name = table.get("name", "table")
            out.write(f"## {name}\n")
            columns = list(rows[0].keys())
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in columns})
            out.write("\n")

    return out.getvalue()
