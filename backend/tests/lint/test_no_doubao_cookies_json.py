"""Phase 3 cleanup regression guard (Refs #1118 / Epic #1110).

After Phase 2 ramp #1117 lands at 100% and the 30-day observation window
posted on Epic #1110 elapses, the env-variable cookie injection path for
the two MVP engines (``doubao`` + ``deepseek``) is retired in favour of
the ``vm_session`` execution mode + ``vm_side`` runner (see ADR-016).
This test fails CI if any runtime code / workflow / config file
re-introduces a reference to ``DOUBAO_COOKIES_JSON`` or
``DEEPSEEK_COOKIES_JSON``.

Allowed surfaces (intentional carve-outs):

- ``docs/ADAPTER_CONTRACT.md`` keeps the original §5.3 / §5.4 text under a
  DEPRECATED banner per AGENTS.md ``## Admin Surface Rule`` (维护原则:
  禁止删除未替换的规则, 标 DEPRECATED + 原因).
- This test file itself, excluded via ``--exclude=*test_no_doubao*``.
- ``alembic`` migration files keep their docstrings so a downgrade path
  can describe what the cleanup removed.

If a real code path re-introduces the env variable, this test fails with
the offending lines listed verbatim.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_no_doubao_cookies_json_references_in_runtime_code() -> None:
    """After Phase 3 cleanup, DOUBAO_COOKIES_JSON / DEEPSEEK_COOKIES_JSON
    must NOT appear in runtime code paths. Allowed: ADAPTER_CONTRACT.md
    DEPRECATED markers, this test file, and migration files.
    """
    result = subprocess.run(
        [
            "grep",
            "-rn",
            "-E",
            "DOUBAO_COOKIES_JSON|DEEPSEEK_COOKIES_JSON",
            str(REPO_ROOT),
            "--include=*.py",
            "--include=*.yml",
            "--include=*.yaml",
            "--exclude-dir=.git",
            "--exclude-dir=__pycache__",
            "--exclude-dir=.claude",
            "--exclude-dir=.venv",
            "--exclude=*test_no_doubao*",
        ],
        capture_output=True,
        text=True,
    )
    # grep exits 1 if no match → expected after cleanup.
    matches = [line for line in result.stdout.splitlines() if line]
    # Allow only: this file itself (excluded above) + ADAPTER_CONTRACT.md
    # DEPRECATED note + alembic migration files (downgrade reference).
    allowed_patterns = [
        "docs/ADAPTER_CONTRACT.md",
        "backend/alembic/versions/",
    ]
    real_violations = [
        m for m in matches if not any(p in m for p in allowed_patterns)
    ]
    assert not real_violations, (
        "DOUBAO/DEEPSEEK_COOKIES_JSON found in runtime code after Phase 3 "
        "cleanup (Refs #1118 / Epic #1110). The env-variable cookie "
        "injection path is deprecated — doubao/deepseek must route through "
        "vm_session + vm_side runner (ADR-016). Offending lines:\n"
        + "\n".join(real_violations)
    )
