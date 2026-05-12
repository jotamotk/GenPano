from __future__ import annotations

import sys
import types


def _install_fake_playwright(monkeypatch):
    playwright = types.ModuleType("playwright")
    playwright_async = types.ModuleType("playwright.async_api")
    playwright_async.async_playwright = object
    playwright_async.BrowserContext = object
    playwright_async.ElementHandle = object
    playwright_async.Page = object
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.async_api", playwright_async)


def test_successful_doubao_response_enqueues_analysis(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    calls: list[dict[str, object]] = []

    class FakeAnalyzeResponseTask:
        @staticmethod
        def apply_async(*, args, queue):
            calls.append({"args": args, "queue": queue})

    monkeypatch.setattr(celery_tasks, "analyze_response", FakeAnalyzeResponseTask)

    assert celery_tasks._enqueue_response_analysis(473) is True
    assert calls == [{"args": [473], "queue": "analysis"}]


def test_analysis_enqueue_failure_does_not_fail_saved_response(monkeypatch):
    _install_fake_playwright(monkeypatch)

    from geo_tracker.tasks import celery_tasks

    class FailingAnalyzeResponseTask:
        @staticmethod
        def apply_async(*, args, queue):
            raise RuntimeError("broker temporarily unavailable")

    monkeypatch.setattr(celery_tasks, "analyze_response", FailingAnalyzeResponseTask)

    assert celery_tasks._enqueue_response_analysis(473) is False
