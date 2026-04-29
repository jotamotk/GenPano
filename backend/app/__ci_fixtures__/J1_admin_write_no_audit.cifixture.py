"""Sentinel: this file deliberately violates J1 by design.

J1 — every admin write handler (POST/PATCH/PUT/DELETE) under
`backend/app/admin/api/**` must contain a `record_audit(` call. This
fixture defines a write handler that omits the audit call, which the
rule must surface as a violation.

Used by scripts/ci_harness_selftest.py to verify the rule registry can
detect violations. Do NOT remove or "fix" this file; remove the
corresponding rule first (or accept the harness silently passing on
regressions).
"""

from __future__ import annotations


class _Router:
    def post(self, _path: str, **_kwargs: object) -> object:
        def _decorator(fn: object) -> object:
            return fn

        return _decorator


router = _Router()


@router.post("/{user_id}/dangerous-action")
async def dangerous_action_without_audit(user_id: str) -> dict[str, str]:
    return {"user_id": user_id, "action": "ok"}
