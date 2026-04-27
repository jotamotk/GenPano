"""Sentinel: this file deliberately violates a rule by design.

Used by scripts/ci_harness_selftest.py to verify the rule registry can detect
violations. Do NOT remove or "fix" this file; remove the corresponding rule
first (or accept that the harness will start silently passing on regressions).
"""


class AiResponse:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def _seed_one() -> AiResponse:
    return AiResponse(content="hello", engine="doubao")
