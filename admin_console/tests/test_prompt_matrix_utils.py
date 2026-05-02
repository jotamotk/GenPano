import unittest

from admin_console.prompt_matrix import (
    LLMPromptCandidate,
    PromptMatrixError,
    consumer_aliases_for_brand_name,
    dedupe_prompt_candidates,
    detect_brand_leaks,
    estimate_generation_count,
    has_prompt_language_mismatch,
    intent_language_combinations,
    is_natural_user_prompt,
    is_prompt_relevant_to_topic,
    is_valid_prompt_for_language,
    parse_llm_prompt_candidates,
    transition_candidate_status,
)


class PromptMatrixUtilsTest(unittest.TestCase):
    def test_estimate_generation_count_caps_per_topic_and_total(self):
        self.assertEqual(
            estimate_generation_count(
                selected_topics=10,
                intent_count=4,
                language_count=2,
                max_per_topic=4,
                max_prompts=1000,
            ),
            40,
        )
        self.assertEqual(
            estimate_generation_count(
                selected_topics=10,
                intent_count=4,
                language_count=2,
                max_per_topic=8,
                max_prompts=50,
            ),
            50,
        )

    def test_intent_language_combinations_are_stable(self):
        combos = intent_language_combinations(4, 2, 5)
        self.assertEqual(
            combos,
            [
                {"intent": "informational", "language": "zh-CN"},
                {"intent": "informational", "language": "en-US"},
                {"intent": "commercial", "language": "zh-CN"},
                {"intent": "commercial", "language": "en-US"},
                {"intent": "transactional", "language": "zh-CN"},
            ],
        )

    def test_parse_llm_prompt_candidates_success(self):
        parsed = parse_llm_prompt_candidates(
            """
            ```json
            {
              "prompts": [
                {
                  "topic_id": "T-12",
                  "intent": "commercial",
                  "language": "zh-CN",
                  "text": "敏感肌换季时应该怎么挑选温和保湿面霜？",
                  "confidence": 0.86,
                  "reason": "covers purchase comparison"
                }
              ]
            }
            ```
            """,
            topics_by_id={12: {"id": 12, "title": "敏感肌保湿", "dimension": "scenario"}},
            known_brands=[],
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].intent, "commercial")
        self.assertNotIn("engines", parsed[0].tags)
        self.assertEqual(parsed[0].tags["routing"], "deferred_to_query_pool")

    def test_parse_llm_prompt_candidates_rejects_invalid_schema(self):
        with self.assertRaises(PromptMatrixError) as ctx:
            parse_llm_prompt_candidates(
                {"prompts": [{"topic_id": 1, "intent": "bad", "language": "zh-CN", "text": "这款产品好吗？"}]},
                topics_by_id={1: {"id": 1, "dimension": "brand"}},
                known_brands=[],
            )
        self.assertEqual(ctx.exception.code, "llm_schema_invalid")

    def test_parse_llm_prompt_candidates_rejects_language_mismatch(self):
        with self.assertRaises(PromptMatrixError) as ctx:
            parse_llm_prompt_candidates(
                {
                    "prompts": [
                        {
                            "topic_id": 1,
                            "intent": "informational",
                            "language": "en-US",
                            "text": "How should I choose Nike的徒步鞋？",
                            "confidence": 0.8,
                        }
                    ]
                },
                topics_by_id={1: {"id": 1, "dimension": "brand"}},
                known_brands=[],
            )
        self.assertEqual(ctx.exception.code, "prompt_language_mismatch")

    def test_language_rules_allow_english_terms_inside_chinese_questions(self):
        natural_code_switching = [
            "Nike的鞋子好不好？",
            "hiking有什么好的鞋子推荐？",
            "Gore-Tex徒步鞋值得买吗？",
            "city walk穿什么鞋比较舒服？",
            "trail running鞋和hiking鞋有什么区别？",
            "Air Max适合日常通勤穿吗？",
            "lululemon瑜伽裤怎么选尺码？",
        ]
        for text in natural_code_switching:
            with self.subTest(text=text):
                self.assertFalse(has_prompt_language_mismatch(text, "zh-CN"))
                self.assertTrue(is_valid_prompt_for_language(text, "zh-CN"))

    def test_topic_relevance_rejects_same_brand_wrong_product(self):
        topic = {
            "id": 67,
            "title": "CHANEL的防晒霜哪款适合混油皮夏天使用",
            "brand": "CHANEL",
            "dimension": "question",
        }
        brands = [{"name": "CHANEL", "aliases": ["香奈儿"]}]
        self.assertTrue(is_prompt_relevant_to_topic("混油皮夏天用CHANEL防晒会不会搓泥？", topic, brands, language="zh-CN"))
        self.assertFalse(is_prompt_relevant_to_topic("香奈儿五号香水的不同版本有什么区别？", topic, brands, language="zh-CN"))
        self.assertTrue(
            is_prompt_relevant_to_topic(
                "Which CHANEL sunscreen works better for oily skin in summer?",
                topic,
                brands,
                language="en-US",
            )
        )

    def test_english_topic_relevance_uses_ascii_anchors_when_available(self):
        topic = {
            "id": 12,
            "title": "Nike的徒步鞋适合长线hiking吗",
            "brand": "Nike",
            "dimension": "product",
        }
        self.assertTrue(
            is_prompt_relevant_to_topic(
                "Are Nike hiking shoes comfortable enough for long trails?",
                topic,
                [{"name": "Nike", "aliases": []}],
                language="en-US",
            )
        )
        self.assertFalse(
            is_prompt_relevant_to_topic(
                "Are Nike running shoes good for city commuting?",
                topic,
                [{"name": "Nike", "aliases": []}],
                language="en-US",
            )
        )

    def test_parse_llm_prompt_candidates_rejects_topic_mismatch(self):
        with self.assertRaises(PromptMatrixError) as ctx:
            parse_llm_prompt_candidates(
                {
                    "prompts": [
                        {
                            "topic_id": 67,
                            "intent": "informational",
                            "language": "zh-CN",
                            "text": "香奈儿五号香水的不同版本有什么区别？",
                            "confidence": 0.9,
                        }
                    ]
                },
                topics_by_id={
                    67: {
                        "id": 67,
                        "title": "CHANEL的防晒霜哪款适合混油皮夏天使用",
                        "brand": "CHANEL",
                        "dimension": "question",
                    }
                },
                known_brands=[{"name": "CHANEL", "aliases": ["香奈儿"]}],
            )
        self.assertEqual(ctx.exception.code, "prompt_topic_mismatch")

    def test_dedupe_prompt_candidates_against_existing_and_batch(self):
        candidates = [
            LLMPromptCandidate(
                topic_id=1,
                intent="informational",
                language="zh-CN",
                text="敏感肌换季时应该怎么挑选温和保湿面霜？",
                template_strategy="latest",
                template_version="v1",
                confidence=0.8,
                reason="duplicate",
                tags={},
            ),
            LLMPromptCandidate(
                topic_id=1,
                intent="commercial",
                language="zh-CN",
                text="敏感肌预算两百元以内可以买哪些修护面霜？",
                template_strategy="latest",
                template_version="v1",
                confidence=0.84,
                reason="new",
                tags={},
            ),
            LLMPromptCandidate(
                topic_id=1,
                intent="commercial",
                language="zh-CN",
                text="敏感肌预算两百元以内可以买哪些修护面霜吗？",
                template_strategy="latest",
                template_version="v1",
                confidence=0.83,
                reason="batch duplicate",
                tags={},
            ),
        ]
        accepted, skipped = dedupe_prompt_candidates(
            candidates,
            ["敏感肌换季时应该怎么挑选温和保湿面霜？"],
        )
        self.assertEqual([item.text for item in accepted], [candidates[1].text])
        self.assertEqual([item["reason"] for item in skipped], ["duplicate", "duplicate"])

    def test_category_prompt_brand_leak_is_rejected(self):
        with self.assertRaises(PromptMatrixError) as ctx:
            parse_llm_prompt_candidates(
                {
                    "prompts": [
                        {
                            "topic_id": 9,
                            "intent": "informational",
                            "language": "zh-CN",
                            "text": "薇诺娜面霜和普通修护面霜有什么区别？",
                            "confidence": 0.9,
                            "reason": "leaks brand",
                        }
                    ]
                },
                topics_by_id={9: {"id": 9, "dimension": "category"}},
                known_brands=[{"name": "薇诺娜", "aliases": ["Winona"]}],
            )
        self.assertEqual(ctx.exception.code, "category_brand_leak")
        self.assertEqual(detect_brand_leaks("Is Winona good?", [{"name": "薇诺娜", "aliases": ["Winona"]}]), ["Winona"])

    def test_review_candidate_status_transition(self):
        self.assertEqual(transition_candidate_status("pending", "approved"), "approved")
        self.assertEqual(transition_candidate_status("pending", "rejected"), "rejected")
        with self.assertRaises(PromptMatrixError) as ctx:
            transition_candidate_status("approved", "rejected")
        self.assertEqual(ctx.exception.code, "candidate_already_reviewed")

    def test_natural_prompt_rules_reject_keyword_stuffing_and_admin_view(self):
        self.assertTrue(is_natural_user_prompt("敏感肌换季应该怎么挑选温和保湿面霜？"))
        self.assertTrue(is_natural_user_prompt("Which sunscreen is better for oily skin under $25?"))
        self.assertFalse(is_natural_user_prompt("防晒 美白 成分 排名 榜单"))
        self.assertFalse(is_natural_user_prompt("给CRM私域会员运营设计复购转化触达任务"))

    def test_natural_prompt_rules_reject_stilted_generated_copy(self):
        self.assertFalse(is_natural_user_prompt("高端奢侈品集团旗下的香水线哪些性价比更高？"))
        self.assertFalse(is_natural_user_prompt("打算送礼物给职场女性，LVMH旗下的产品选哪个更合适性价比更高？"))
        self.assertFalse(is_natural_user_prompt("What suitable gift options under LVMH are there for working women?"))
        self.assertFalse(is_natural_user_prompt("Which product has higher cost performance and is worth buying?"))
        self.assertFalse(is_natural_user_prompt("送职场女生 LVMH 礼物，选香水还是小皮具更稳？"))
        self.assertFalse(is_natural_user_prompt("Is perfume or a small leather good a safer LVMH gift for someone at work?"))
        self.assertTrue(is_natural_user_prompt("送职场女生大牌礼物，选香水还是小皮具更稳？"))
        self.assertTrue(is_natural_user_prompt("Is perfume or a small leather good a safer luxury gift for someone at work?"))

    def test_consumer_aliases_for_group_brand(self):
        aliases = consumer_aliases_for_brand_name("LVMH", ["路威酩轩"])
        self.assertIn("LV", aliases)
        self.assertIn("大牌包", aliases)


if __name__ == "__main__":
    unittest.main()
