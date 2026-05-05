"""MCP tool input schemas (JSON Schema draft-07 compatible).

Each entry maps a tool name in `MCP_TOOLS` to its `inputSchema` and
human-readable `description`. Returned by `tools/list` so MCP-compliant
AI clients (Claude / GPT) discover the tool surface correctly.

Without these schemas, `tools/list` returned `{type: "object"}` for
every tool — the client thought every tool took any object and would
guess argument names, often passing wrong shapes.
"""

from __future__ import annotations

from typing import Any

# JSON Schema fragments reused across multiple tools
_PROJECT_ID_REQUIRED = {
    "project_id": {
        "type": "string",
        "description": "ID of the user's GenPano project. Multi-tenant scope check.",
    },
}

_BRAND_ID_INT = {
    "type": "integer",
    "description": "Internal brand ID. Look up via tools/list of brand catalog.",
}

_PERIOD = {
    "type": "string",
    "description": "Time window suffix. e.g. '7d', '30d', '90d'. Default '30d'.",
    "pattern": r"^\d+d$",
    "default": "30d",
}

_ENGINE = {
    "type": "string",
    "description": "Filter to one LLM engine. e.g. 'chatgpt', 'doubao', 'deepseek'.",
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "genpano_get_brand_visibility": {
        "description": (
            "Brand visibility metrics over the last N days: mention rate, share "
            "of voice, average rank, sentiment summary."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["brand_id", "project_id"],
            "properties": {
                "brand_id": _BRAND_ID_INT,
                **_PROJECT_ID_REQUIRED,
                "engine": _ENGINE,
                "period": _PERIOD,
            },
            "additionalProperties": False,
        },
    },
    "genpano_compare_brands": {
        "description": (
            "Compare 2-10 brands' KPIs side-by-side over the same window. Returns "
            "matrix of metrics per brand."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["brand_ids", "project_id"],
            "properties": {
                "brand_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 10,
                    "description": "List of internal brand IDs to compare.",
                },
                **_PROJECT_ID_REQUIRED,
                "period": _PERIOD,
            },
            "additionalProperties": False,
        },
    },
    "genpano_get_industry_trends": {
        "description": ("Industry-level KPI snapshot + 30d trend + top brand list."),
        "inputSchema": {
            "type": "object",
            "required": ["industry_id"],
            "properties": {
                "industry_id": {"type": "integer", "description": "Internal industry ID."},
                "industry_name": {"type": "string", "description": "Optional human industry name."},
                "period": _PERIOD,
            },
            "additionalProperties": False,
        },
    },
    "genpano_get_industry_kg": {
        "description": (
            "Industry knowledge graph: brands + categories + relations. Returns "
            "{nodes, edges} compatible with antv/g6 / d3-force."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["industry_id"],
            "properties": {
                "industry_id": {"type": "integer", "description": "Internal industry ID."},
                "industry_name": {"type": "string", "description": "Optional human industry name."},
                "focus": {
                    "type": "string",
                    "description": "Optional node id to BFS-cluster around.",
                },
                "depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 2,
                    "description": "Graph traversal depth. depth=1 omits products.",
                },
            },
            "additionalProperties": False,
        },
    },
    "genpano_get_product_ranking": {
        "description": (
            "Product ranking inside a project: per-product mention rate, "
            "first-place count, avg rank."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                **_PROJECT_ID_REQUIRED,
                "product_id": {
                    "type": "integer",
                    "description": "Optional single-product filter.",
                },
                "category": {"type": "string", "description": "Optional category filter."},
                "period": _PERIOD,
            },
            "additionalProperties": False,
        },
    },
    "genpano_generate_report": {
        "description": (
            "Trigger an async report generation job. Returns the queued job_id "
            "to poll with /v1/projects/:id/reports/:rid."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                **_PROJECT_ID_REQUIRED,
                "report_type": {
                    "type": "string",
                    "enum": ["weekly", "monthly", "on_demand", "lead_diagnostic"],
                    "default": "weekly",
                },
                "locale": {
                    "type": "string",
                    "enum": ["zh-CN", "en"],
                    "default": "zh-CN",
                },
                "reader_perspective": {
                    "type": "string",
                    "enum": ["operator", "manager", "branding"],
                    "default": "manager",
                },
            },
            "additionalProperties": False,
        },
    },
    "genpano_get_optimization_insights": {
        "description": (
            "Top diagnostic insights for the project — Phase D rule output. "
            "Filter by severity / category."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["project_id"],
            "properties": {
                **_PROJECT_ID_REQUIRED,
                "severity": {
                    "type": "string",
                    "enum": ["P0", "P1", "P2", "P3"],
                    "description": "Optional minimum severity filter.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter (e.g. 'visibility_decline').",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 10,
                },
            },
            "additionalProperties": False,
        },
    },
    "genpano_get_citations": {
        "description": ("Brand citation list with source domain, type, and authority tier."),
        "inputSchema": {
            "type": "object",
            "required": ["brand_id", "project_id"],
            "properties": {
                "brand_id": _BRAND_ID_INT,
                **_PROJECT_ID_REQUIRED,
                "domain": {"type": "string", "description": "Optional domain filter."},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 50,
                },
            },
            "additionalProperties": False,
        },
    },
    "genpano_list_pr_targets": {
        "description": (
            "Recommended Tier-1/2 PR target domains for this brand based on "
            "current authority tier coverage gaps."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["brand_id", "project_id"],
            "properties": {
                "brand_id": _BRAND_ID_INT,
                **_PROJECT_ID_REQUIRED,
                "tier": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4,
                    "description": "Optional authority tier filter (1=official, 2=tier-2, etc.).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                },
            },
            "additionalProperties": False,
        },
    },
    "genpano_simulate_authority_boost": {
        "description": (
            "Simulate the PANO_A score impact of adding citations at specific "
            "authority tiers. Returns simulated_pano_a + delta + estimated CNY cost."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["brand_id", "delta_by_tier"],
            "properties": {
                "brand_id": _BRAND_ID_INT,
                "delta_by_tier": {
                    "type": "object",
                    "description": (
                        "Mapping of tier number (as string) to citation delta. e.g. "
                        '{"1": 5, "2": 10} adds 5 tier-1 + 10 tier-2 citations.'
                    ),
                    "additionalProperties": {"type": "integer"},
                },
                "confidence_override": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 1.0,
                    "description": "Optional override for the confidence score (default 0.85).",
                },
                "project_id": {
                    "type": "string",
                    "description": (
                        "Optional project context — used to derive industry_id "
                        "for base_price_equivalent_cny."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
}


def get_tool_descriptors() -> list[dict[str, Any]]:
    """Return tools/list descriptors for every tool in MCP_TOOLS.

    Tools without an entry in TOOL_SCHEMAS fall back to a permissive
    `{type: "object"}` schema so adding a new tool to the registry
    doesn't break MCP responses while the schema is being authored.
    """
    from app.api.v1.api_keys.service import MCP_TOOLS

    out: list[dict[str, Any]] = []
    for name in MCP_TOOLS:
        entry = TOOL_SCHEMAS.get(name)
        if entry is None:
            out.append(
                {
                    "name": name,
                    "description": f"GenPano tool: {name}",
                    "inputSchema": {"type": "object"},
                }
            )
        else:
            out.append(
                {
                    "name": name,
                    "description": entry["description"],
                    "inputSchema": entry["inputSchema"],
                }
            )
    return out
