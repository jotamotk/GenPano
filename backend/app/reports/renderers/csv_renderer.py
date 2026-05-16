"""CSV renderer for report payloads.

Emits one CSV block per section. Each section gets:
  - a `# {section_title}` header line
  - a `## metrics` block (key,value rows) when `metrics` is non-empty —
    audit #1044 B2-11: the previous renderer skipped sections with no
    `tables` entirely, which lost the executive_summary block (which is
    metrics-only) from every CSV export.
  - one `## {table_name}` block per row-bearing table.
"""

from __future__ import annotations

import csv
import io
from typing import Any


def render_csv(payload: dict[str, Any]) -> str:
    """Render section payload to a single multi-section CSV string."""
    out = io.StringIO()

    sections = payload.get("sections", [])
    for sec in sections:
        tables = sec.get("tables") or []
        metrics = sec.get("metrics") or {}
        # Audit #1044 B2-11: don't skip sections that only carry
        # metrics (e.g. executive_summary). Emit the section header +
        # a key/value CSV for the metrics regardless of tables.
        if not tables and not metrics:
            continue
        section_label = sec.get("title", sec.get("section_type", "section"))
        out.write(f"# {section_label}\n")

        if metrics:
            out.write("## metrics\n")
            writer = csv.writer(out)
            writer.writerow(["key", "value"])
            for k, v in metrics.items():
                writer.writerow([k, _stringify(v)])
            out.write("\n")

        for table in tables:
            rows = table.get("rows") or []
            if not rows:
                continue
            name = table.get("name", "table")
            out.write(f"## {name}\n")
            columns = list(rows[0].keys())
            dict_writer = csv.DictWriter(out, fieldnames=columns)
            dict_writer.writeheader()
            for r in rows:
                dict_writer.writerow({k: _stringify(r.get(k, "")) for k in columns})
            out.write("\n")

    return out.getvalue()


def _stringify(value: Any) -> str:
    """Flatten dict/list into compact JSON so CSV stays parseable; pass
    primitives through. Avoids `{'V': 85, 'S': ...}` showing up as raw
    Python repr in the exported file."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        import json

        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)
