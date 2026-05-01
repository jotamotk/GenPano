import unittest

from query_tool.topic_plan import (
    LLMTopic,
    TopicPlanLLMError,
    dedupe_topic_candidates,
    parse_llm_topics,
    repair_single_brand_placeholders,
    transition_candidate_status,
)


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
        self.assertEqual([item["reason"] for item in skipped], ["duplicate", "duplicate"])

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


if __name__ == "__main__":
    unittest.main()
