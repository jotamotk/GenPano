"""Shared fixtures for vm_side tests.

The vm_side package imports ``playwright.async_api`` at module load. To keep
the test environment lightweight (no real browser binaries needed) we shim
the relevant Playwright surface with ``AsyncMock`` objects.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make repo root importable so ``import vm_side`` resolves under pytest
# regardless of where the test is run from.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Default env so tests do not accidentally hit a real orchestrator."""
    monkeypatch.setenv("VM_ID", "test-vm")
    monkeypatch.delenv("ORCHESTRATOR_URL", raising=False)
    yield
