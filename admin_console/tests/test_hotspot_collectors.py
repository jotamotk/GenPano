"""Unit tests for ``admin_console.hotspot_collectors``.

The collectors hit external APIs in production; these tests stub urlopen and
the OpenAI client so they're hermetic. We focus on:

- The pipeline's source dispatch + dedupe + persistence loop.
- Per-source response parsing (Baidu PC, Zhihu desktop, Weibo sidebar,
  Toutiao hot-board) — using captured shapes from the live endpoints so we
  catch upstream schema drift if it ever returns later.
- The LLM-search collector's strict-JSON parse path (with markdown fences
  and bare arrays both handled).
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock


# Allow ``import admin_console.hotspot_collectors`` from a checked-out repo
# even if pytest is invoked from the repo root rather than admin_console/.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from admin_console import hotspot_collectors as hc  # noqa: E402


@contextmanager
def _patched_urlopen(payload):
    """Patch urllib.request.urlopen to return a single canned JSON payload."""

    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload

    def fake_urlopen(req, timeout=15):
        return _Resp(body)

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        yield


class BaiduCollectorTest(unittest.TestCase):
    def test_pc_shape(self):
        payload = {
            "data": {
                "cards": [
                    {
                        "content": [
                            {
                                "word": "示例热搜",
                                "query": "示例热搜",
                                "desc": "事件描述",
                                "hotScore": "1234",
                                "url": "https://www.baidu.com/s?wd=x",
                                "rawUrl": "https://www.baidu.com/s?wd=x",
                            },
                        ]
                    }
                ]
            }
        }
        with _patched_urlopen(payload):
            items = hc.collect_baidu(limit=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "示例热搜")
        self.assertEqual(items[0].source, "baidu")
        self.assertEqual(items[0].raw_rank, 1)
        self.assertIn("热度", items[0].raw_metric or "")

    def test_wise_double_nested_shape(self):
        payload = {
            "data": {
                "cards": [
                    {
                        "content": [
                            {"content": [{"word": "嵌套热搜", "url": "u"}]},
                        ]
                    }
                ]
            }
        }
        with _patched_urlopen(payload):
            items = hc.collect_baidu(limit=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "嵌套热搜")

    def test_empty_cards_returns_empty(self):
        with _patched_urlopen({"data": {"cards": []}}):
            self.assertEqual(hc.collect_baidu(), [])


class ZhihuCollectorTest(unittest.TestCase):
    def test_parses_target_and_rewrites_url(self):
        payload = {
            "data": [
                {
                    "target": {
                        "id": 12345,
                        "title": "知乎热问标题",
                        "excerpt": "摘要",
                        "url": "https://api.zhihu.com/questions/12345",
                    },
                    "detail_text": "599 万热度",
                }
            ]
        }
        with _patched_urlopen(payload):
            items = hc.collect_zhihu(limit=3)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "知乎热问标题")
        self.assertEqual(items[0].source_url, "https://www.zhihu.com/question/12345")
        self.assertEqual(items[0].raw_metric, "599 万热度")


class WeiboCollectorTest(unittest.TestCase):
    def test_strips_ads_and_keeps_top(self):
        payload = {
            "data": {
                "realtime": [
                    {"word": "推广热搜", "is_ad": 1, "rank": 0, "num": 100},
                    {"word": "真热搜", "rank": 0, "num": 8888,
                     "label_name": "热", "word_scheme": "#真热搜#"},
                ]
            }
        }
        with _patched_urlopen(payload):
            items = hc.collect_weibo(limit=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "真热搜")
        self.assertIn("热", items[0].raw_metric or "")
        self.assertTrue(items[0].source_url and "s.weibo.com" in items[0].source_url)


class ToutiaoCollectorTest(unittest.TestCase):
    def test_maps_interest_category_to_industry(self):
        payload = {
            "data": [
                {
                    "Title": "测试标题",
                    "QueryWord": "测试标题",
                    "HotValue": "9999",
                    "Url": "https://www.toutiao.com/trending/123",
                    "InterestCategory": ["beauty"],
                    "LabelDesc": "新事件上榜",
                }
            ]
        }
        with _patched_urlopen(payload):
            items = hc.collect_toutiao(limit=3)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].industry, "美妆个护")
        self.assertEqual(items[0].category, "新事件上榜")
        self.assertEqual(items[0].raw_rank, 1)
        self.assertIn("热度", items[0].raw_metric or "")


class LLMSearchTest(unittest.TestCase):
    def _stub_client(self, content: str):
        class FakeMessage:
            def __init__(self, content):
                self.content = content

        class FakeChoice:
            def __init__(self, content):
                self.message = FakeMessage(content)

        class FakeResponse:
            def __init__(self, content):
                self.choices = [FakeChoice(content)]

        class FakeChat:
            def __init__(self, content):
                self._content = content
                self.completions = self

            def create(self, **kwargs):
                return FakeResponse(self._content)

        class FakeClient:
            def __init__(self, content):
                self.chat = FakeChat(content)

        def factory(api_key, base_url):
            return FakeClient(content)

        return factory

    def test_parses_strict_json_with_fence(self):
        content = (
            "```json\n"
            '{"hotspots": [{"title": "化妆品控油到底是真控油还是物理吸油",'
            ' "summary": "夏天出油多，最近热议", "category": "舆论", "industry": "美妆个护"}]}'
            "\n```"
        )
        cfg_patch = mock.patch.object(
            hc, "load_doubao_config",
            return_value=mock.Mock(api_key="k", base_url="https://x", model="doubao"),
        )
        with cfg_patch:
            items = hc.collect_llm_search(
                industry="美妆个护", limit=5,
                client_factory=self._stub_client(content),
            )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "llm_search")
        self.assertEqual(items[0].industry, "美妆个护")

    def test_drops_placeholder_titles(self):
        content = json.dumps({
            "hotspots": [
                {"title": "[LLM-search placeholder] 美妆 trending #1"},
                {"title": "真实话题：A 品牌粉底新品上市"},
            ]
        })
        cfg_patch = mock.patch.object(
            hc, "load_doubao_config",
            return_value=mock.Mock(api_key="k", base_url="https://x", model="doubao"),
        )
        with cfg_patch:
            items = hc.collect_llm_search(
                industry="美妆个护", limit=5,
                client_factory=self._stub_client(content),
            )
        self.assertEqual(len(items), 1)
        self.assertNotIn("placeholder", items[0].title)

    def test_no_api_key_returns_empty(self):
        cfg_patch = mock.patch.object(
            hc, "load_doubao_config",
            return_value=mock.Mock(api_key="", base_url="x", model="m"),
        )
        with cfg_patch:
            items = hc.collect_llm_search(industry=None, limit=3, client_factory=lambda *a: None)
        self.assertEqual(items, [])


class PipelineTest(unittest.TestCase):
    def setUp(self):
        # Patch out network collectors with deterministic factories.
        self.calls: list[str] = []

        def fake_baidu(*, limit=30):
            self.calls.append("baidu")
            return [hc.HotspotCandidate(title="热点A", source="baidu", raw_rank=1)]

        def fake_zhihu(*, limit=30):
            self.calls.append("zhihu")
            return [
                hc.HotspotCandidate(title="热点A", source="zhihu", raw_rank=1),  # dup of baidu
                hc.HotspotCandidate(title="热点B", source="zhihu", raw_rank=2),
            ]

        def fake_llm(*, industry=None, limit=20):
            self.calls.append("llm_search")
            return [
                hc.HotspotCandidate(
                    title="热点C", source="llm_search", industry="美妆个护"
                ),
                hc.HotspotCandidate(
                    title="热点D", source="llm_search", industry="数码"  # filtered out
                ),
            ]

        self.patches = [
            mock.patch.dict(hc.COLLECTORS, {
                "baidu": fake_baidu,
                "zhihu": fake_zhihu,
                "weibo": lambda *, limit=30: [],
                "toutiao": lambda *, limit=30: [],
                "llm_search": fake_llm,
            }, clear=False),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_dedupe_and_industry_filter(self):
        captured: list[tuple] = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params=None):
                if "SELECT title" in sql:
                    self._rows = []
                else:
                    captured.append((sql.strip().split()[0], params))

            def fetchall(self):
                return getattr(self, "_rows", [])

        class FakeConn:
            def cursor(self):
                return FakeCursor()

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        result = hc.run_collection_cycle(
            sources=["baidu", "zhihu", "llm_search"],
            industry_filter="美妆个护",
            get_db=lambda: FakeConn(),
        )

        # dedupe: 热点A appears in baidu & zhihu => one row; 热点B kept;
        # 热点C kept (industry matches); 热点D filtered out (industry != 美妆个护).
        self.assertEqual(result["collected"], 3)
        self.assertEqual(result["inserted"], 3)
        # All three sources were consulted.
        self.assertEqual(set(self.calls), {"baidu", "zhihu", "llm_search"})
        self.assertEqual(result["by_source"], {"baidu": 1, "zhihu": 2, "llm_search": 2})

    def test_collector_failure_isolates(self):
        def boom(*, limit=30):
            raise RuntimeError("upstream-down")

        with mock.patch.dict(hc.COLLECTORS, {"baidu": boom}, clear=False):
            result = hc.run_collection_cycle(
                sources=["baidu", "zhihu"],
                get_db=lambda: (_ for _ in ()).throw(AssertionError("should not call db")),
            )

        self.assertIn("baidu", result["errors"])
        self.assertIn("upstream-down", result["errors"]["baidu"])
        # Zhihu still ran and produced its 2 items but DB persistence is a
        # separate path. We allow either persist path; the key is that the
        # collector loop didn't abort on the baidu failure.
        self.assertEqual(result["by_source"].get("baidu"), 0)


if __name__ == "__main__":
    unittest.main()
