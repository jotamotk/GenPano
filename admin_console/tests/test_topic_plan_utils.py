import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

from admin_console.topic_plan import (
    DoubaoConfig,
    DoubaoTopicPlanClient,
    LLMTopic,
    TopicPlanLLMError,
    build_topic_plan_messages,
    consumer_aliases_for_brand,
    dedupe_topic_candidates,
    is_natural_consumer_topic,
    parse_llm_topics,
    repair_single_brand_placeholders,
    transition_candidate_status,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_CONSOLE_DIR = REPO_ROOT / "admin_console"


def _run_script_mode_python(code: str):
    env = os.environ.copy()
    env["ADMIN_CONSOLE_SKIP_STARTUP_MIGRATIONS"] = "1"
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_topic_plan_helpers_work_when_imported_as_docker_script_modules():
    result = _run_script_mode_python(
        f"""
        import sys
        sys.path.insert(0, {str(ADMIN_CONSOLE_DIR)!r})
        import topic_plan

        messages = topic_plan.build_topic_plan_messages(
            industry="运动户外",
            category="All categories",
            brands=[{{"id": 18, "name": "NIKE", "topic_count": 2}}],
            coverage_gaps=[{{"brand_id": 18, "brand": "NIKE", "type": "brand", "count": 1}}],
            max_topics=1,
            existing_topics=[],
        )
        candidates, skipped = topic_plan.dedupe_topic_candidates(
            [
                topic_plan.LLMTopic(
                    title="NIKE beginner road running shoes",
                    brand="NIKE",
                    dimension="product",
                    reason="覆盖新手跑步购买意图",
                    confidence=0.9,
                    coverage_gap="NIKE:product",
                )
            ],
            [],
            1,
        )
        assert len(messages) == 2
        assert len(candidates) == 1
        assert skipped == []
        """
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_topic_plan_generation_helpers_work_when_app_imported_as_docker_script_module():
    result = _run_script_mode_python(
        f"""
        import sys
        import types
        sys.path.insert(0, {str(ADMIN_CONSOLE_DIR)!r})
        import app

        class FakeCursor:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def execute(self, *args, **kwargs):
                return None

        class FakeConn:
            def cursor(self, *args, **kwargs):
                return FakeCursor()
            def commit(self):
                return None

        class FakeClient:
            def __init__(self, config):
                self.config = config
            def generate_topics(self, **kwargs):
                return [], {{"model": "fake-model", "usage": {{}}}}

        app.load_doubao_config = lambda: types.SimpleNamespace(model="fake-model")
        app.DoubaoTopicPlanClient = FakeClient
        app._topic_plan_brand_batches = lambda *args, **kwargs: iter([
            ([{{"id": 18, "name": "NIKE"}}], [{{"brand_id": 18, "count": 1}}], 1)
        ])
        app._is_generation_run_cancelled = lambda *args, **kwargs: False
        app._insert_topic_plan_candidate_batch = lambda *args, **kwargs: []
        app._insert_admin_audit_log = lambda *args, **kwargs: None

        app._execute_topic_plan_generation(
            run_id="run-1",
            admin_id=1,
            industry_id="运动户外",
            category_id=None,
            brands=[{{"id": 18, "name": "NIKE"}}],
            llm_gaps=[{{"brand_id": 18, "count": 1}}],
            max_per_brand=40,
            max_topics=1,
            existing_titles=[],
            request_config={{"max_topics": 1}},
            coverage_summary={{}},
            conn=FakeConn(),
        )
        """
    )

    assert result.returncode == 0, result.stderr + result.stdout


class TopicPlanUtilsTest(unittest.TestCase):
    def test_parse_llm_topics_success(self):
        parsed = parse_llm_topics(
            """
            ```json
            {
              "topics": [
                {
                  "title": "Sensitive skin barrier repair routine",
                  "brand": "Winona",
                  "dimension": "scenario",
                  "reason": "Covers a scenario gap",
                  "confidence": 0.82,
                  "coverage_gap": "Winona:scenario"
                }
              ]
            }
            ```
            """
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].dimension, "scenario")
        self.assertAlmostEqual(parsed[0].confidence, 0.82)

    def test_parse_llm_topics_rejects_non_json(self):
        with self.assertRaises(TopicPlanLLMError) as ctx:
            parse_llm_topics("not-json: nope")
        self.assertEqual(ctx.exception.code, "llm_json_invalid")

    def test_parse_llm_topics_rejects_schema_errors(self):
        with self.assertRaises(TopicPlanLLMError) as ctx:
            parse_llm_topics({"topics": [{"title": "Missing fields"}]})
        self.assertEqual(ctx.exception.code, "llm_schema_invalid")

    def test_dedupe_topic_candidates_against_existing_and_batch(self):
        candidates = [
            LLMTopic(
                title="Sensitive Skin Barrier Repair Serum",
                brand="Winona",
                dimension="brand",
                reason="duplicate",
                confidence=0.8,
                coverage_gap="Winona:brand",
            ),
            LLMTopic(
                title="How to use barrier repair serum after sun exposure",
                brand="Winona",
                dimension="question",
                reason="new question gap",
                confidence=0.86,
                coverage_gap="Winona:question",
            ),
            LLMTopic(
                title="How to use barrier-repair serum after sun exposure?",
                brand="Winona",
                dimension="question",
                reason="batch duplicate",
                confidence=0.84,
                coverage_gap="Winona:question",
            ),
        ]

        accepted, skipped = dedupe_topic_candidates(
            candidates,
            existing_titles=["Sensitive skin barrier repair serum"],
        )

        self.assertEqual([item.title for item in accepted], [candidates[1].title])
        self.assertEqual([item["reason"] for item in skipped], ["duplicate_db", "looks_like_prompt"])

    def test_review_candidate_status_transition(self):
        self.assertEqual(transition_candidate_status("pending", "approved"), "approved")
        self.assertEqual(transition_candidate_status("pending", "rejected"), "rejected")
        with self.assertRaises(TopicPlanLLMError) as ctx:
            transition_candidate_status("approved", "rejected")
        self.assertEqual(ctx.exception.code, "candidate_already_reviewed")

    def test_repair_single_brand_placeholders(self):
        repaired = repair_single_brand_placeholders(
            [
                LLMTopic(
                    title="???敏感肌护理场景",
                    brand="???",
                    dimension="scenario",
                    reason="???场景缺口",
                    confidence=0.8,
                    coverage_gap="???:scenario",
                )
            ],
            [{"name": "薇诺娜"}],
        )

        self.assertEqual(repaired[0].brand, "薇诺娜")
        self.assertEqual(repaired[0].title, "薇诺娜敏感肌护理场景")

    def test_build_topic_plan_messages_uses_consumer_perspective(self):
        messages = build_topic_plan_messages(
            industry="\u65f6\u5c1a\u5962\u54c1",
            category="All categories",
            brands=[{"name": "CHANEL", "industry": "\u65f6\u5c1a\u5962\u54c1", "topic_count": 2}],
            coverage_gaps=[{"brand": "CHANEL", "type": "product", "count": 3, "priority": "P1"}],
            max_topics=3,
            existing_topics=[],
        )
        combined = "\n".join(message["content"] for message in messages)

        self.assertIn("consumer-facing", combined)
        self.assertIn("real consumer search", combined)
        self.assertIn("consumer search subject", combined)
        self.assertIn("not every Topic needs to be a question", combined)
        self.assertIn("quality gate", combined)
        self.assertIn("consumer_search_and_shopping_intent", combined)
        self.assertIn("\u79c1\u57df", combined)
        self.assertIn("\u9999\u5948\u513f\u53e3\u7ea2\u70ed\u95e8\u8272\u53f7\u600e\u4e48\u9009", combined)
        self.assertNotIn("for operations users", combined)

    def test_consumer_aliases_for_group_brand(self):
        aliases = consumer_aliases_for_brand({"name": "LVMH", "aliases": ["路威酩轩"]})
        self.assertIn("LV", aliases)
        self.assertIn("大牌香水", aliases)

    def test_natural_topic_rules_reject_corporate_group_wording(self):
        self.assertFalse(is_natural_consumer_topic("LVMH旗下的香水线哪些性价比更高"))
        self.assertFalse(is_natural_consumer_topic("LVMH集团旗下的奢品品牌档次是怎么划分的"))
        self.assertFalse(is_natural_consumer_topic("LVMH珠宝腕表品类线上消费人群画像与转化路径分析"))
        self.assertTrue(is_natural_consumer_topic("想买大牌香水送人哪种味道不容易踩雷"))
        self.assertTrue(is_natural_consumer_topic("hiking有什么鞋子推荐"))

    def test_natural_topic_rules_accept_consumer_topic_subjects(self):
        self.assertTrue(is_natural_consumer_topic("NIKE品牌真伪辨别方法"))
        self.assertTrue(is_natural_consumer_topic("NIKE篮球鞋抓地力性能测评"))
        self.assertTrue(is_natural_consumer_topic("NIKE跑鞋日常慢跑适配性分析"))
        self.assertTrue(is_natural_consumer_topic("NIKE品牌退换货政策整理"))
        self.assertTrue(is_natural_consumer_topic("NIKE儿童运动鞋尺码选择指南"))
        self.assertFalse(is_natural_consumer_topic("NIKE私域会员运营策略分析"))
        self.assertFalse(is_natural_consumer_topic("NIKE用户画像与转化路径分析"))


    def test_topic_plan_client_applies_configurable_timeout(self):
        captured = {}

        class FakeCompletions:
            def create(self, **kwargs):
                captured["request_timeout"] = kwargs.get("timeout")
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=(
                                    '{"topics":[{"title":"Which NIKE running shoes fit beginners?",'
                                    '"brand":"NIKE","dimension":"question","reason":"Covers a gap",'
                                    '"confidence":0.82,"coverage_gap":"NIKE:question"}]}'
                                )
                            )
                        )
                    ],
                    usage={"total_tokens": 12},
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured["client_timeout"] = kwargs.get("timeout")
                self.chat = SimpleNamespace(completions=FakeCompletions())

        original_openai = sys.modules.get("openai")
        original_timeout = os.environ.get("TOPIC_PLAN_LLM_TIMEOUT_SECONDS")
        sys.modules["openai"] = SimpleNamespace(OpenAI=FakeOpenAI)
        os.environ["TOPIC_PLAN_LLM_TIMEOUT_SECONDS"] = "120"
        try:
            client = DoubaoTopicPlanClient(
                DoubaoConfig(api_key="key", base_url="https://example.test", model="model")
            )
            topics, _ = client.generate_topics(
                industry="Sports",
                category="All categories",
                brands=[{"name": "NIKE"}],
                coverage_gaps=[{"brand_id": 18, "brand": "NIKE", "type": "question", "count": 1}],
                max_topics=1,
                existing_topics=[],
            )
        finally:
            if original_openai is None:
                sys.modules.pop("openai", None)
            else:
                sys.modules["openai"] = original_openai
            if original_timeout is None:
                os.environ.pop("TOPIC_PLAN_LLM_TIMEOUT_SECONDS", None)
            else:
                os.environ["TOPIC_PLAN_LLM_TIMEOUT_SECONDS"] = original_timeout

        self.assertEqual(captured["client_timeout"], 120)
        self.assertEqual(captured["request_timeout"], 120)
        self.assertEqual(topics[0].brand, "NIKE")


if __name__ == "__main__":
    unittest.main()
