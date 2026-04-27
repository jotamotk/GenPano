"""Sentinel: this file deliberately violates a rule by design.

Used by scripts/ci_harness_selftest.py to verify the rule registry can detect
violations. Do NOT remove or "fix" this file; remove the corresponding rule
first (or accept that the harness will start silently passing on regressions).
"""


class _SentinelAdapter:
    async def execute(self, query: str) -> dict[str, str]:
        return {"text": "stub", "engine": "doubao"}
