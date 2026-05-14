"""Issue #862 - Admin Tracker screenshot click contract."""

from __future__ import annotations

from pathlib import Path


def _admin_html() -> str:
    return (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )


def test_attempt_screenshot_controls_open_the_screenshot_tab() -> None:
    html = _admin_html()

    assert ":data-testid=\"'attempt-screenshot-' + att.queryDbId\"" in html
    assert '@click.stop="openScreenshotEvidence(att)"' in html
    assert 'data-testid="attempt-drawer-screenshot-action"' in html
    assert '@click="openScreenshotEvidence(attemptDrawer)"' in html
    assert "openDebugDrawer(att, { tab: 'screenshots' })" in html


def test_attempt_screenshot_state_is_not_silently_disabled() -> None:
    html = _admin_html()
    mapper_start = html.index("function mapQueryRowToAttempt")
    mapper_end = html.index("function accountStatusMeta", mapper_start)
    mapper_body = html[mapper_start:mapper_end]

    assert "deriveAttemptScreenshotState(r)" in html
    assert "hasScreenshot: false" not in mapper_body
    assert 'data-testid="debug-screenshot-empty-state"' in html
    assert "debugScreenshotsError" in html
    assert "debugScreenshotEmptyMessage" in html
