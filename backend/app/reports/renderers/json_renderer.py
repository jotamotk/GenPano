"""JSON renderer (pretty-printed) for report payloads."""

from __future__ import annotations

import json
from typing import Any


def render_json(payload: dict[str, Any], *, pretty: bool = True) -> str:
    """Serialize the report payload to JSON.

    Default `pretty=True` produces a 2-space indented document — easier
    on humans hitting the download URL directly. Set `pretty=False` for
    machine consumers / FE clients that pipe through their own parser.
    """
    if pretty:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
