"""
豆包大模型 Prompt 模板

大模型负责所有分析任务（品牌检测 + 情感分析 + 位置分析 + 产品特性提取）：
1. 验证 Stage 1 的品牌预检测结果（排除误匹配）
2. 补全遗漏品牌（简称、昵称、新品牌）
3. 分析位置结构、详细度
4. 情感分析（整体极性 + 驱动因子）
5. 提取产品特性、推荐场景、价格定位
6. 三维度归类（行业/公司/产品/品类）
"""

ANALYSIS_SYSTEM = (
    "你是品牌GEO分析专家。你的任务是：\n"
    "1. 验证并补全品牌检测结果\n"
    "2. 分析品牌在AI回答中的位置、详细度\n"
    "3. 对每个品牌/产品做情感分析（整体极性和分数）并列出驱动因子\n"
    "4. 提取产品特性、推荐场景和价格定位感知\n"
    "重要：同一品牌的不同产品必须分开输出为单独的 brands 条目。\n"
    "重要：每个品牌/产品的 sentiment_drivers 必须详细列出所有正面和负面驱动因子。\n"
    "严格按JSON输出，不要添加任何解释文字。"
)

ANALYSIS_USER = """\
分析以下AI回答中的品牌提及情况。

**目标品牌**: {target_brand}（别名: {target_aliases}）
**已知竞品**: {competitors}
**关键词预检测到的品牌**: {pre_detected_brands}（可能有误匹配或遗漏）
**Prompt意图**: {intent}

**AI回答**:
{response_text}

请：
1. **验证**预检测结果：排除误匹配（如"apple"指水果非品牌），确认每个品牌确实被提及
2. **补全**遗漏品牌：发现预检测未覆盖的品牌/产品（包括简称、昵称、变体形式）
3. **分析**每个确认品牌的位置、详细度
4. **情感分析**：判断AI回答对该品牌/产品的整体情感极性和分数，并列出所有情感驱动因子
5. **提取**每个产品的特性/卖点、推荐场景和AI对其价格定位的感知

**关键规则**:
- **同一品牌的不同产品必须分别输出**：如回答提到"Nike Air Max 90"和"Nike Pegasus"，必须输出两条 brands 条目（brand_name 都是"Nike"，product_name 分别是"Air Max 90"和"Pegasus"）
- 如果仅提及品牌而没有具体产品，product_name 设为 null
- **sentiment 必须准确**：根据AI回答的上下文判断整体情感，sentiment_score 在 -1.0（极负面）到 1.0（极正面）之间
- **sentiment_drivers 必须全面**：列出AI回答中该品牌/产品的所有正面和负面评价因素，包括功能特性、价格、体验、品牌形象等各方面。每个 driver 需要附带原文引用（source_quote）
- **product_features 必须全面**：列出AI回答中提到的该产品的所有特性、卖点、场景和价格感知
- **response_relations must be response-scoped**: extract relations stated in the current AI response only, such as product recommended_for profile/skin concern, brand compared_with brand, product has_attribute attribute, or product addresses_need need. Do not use global inference. Each relation must include evidence quoted from the current AI response.

输出JSON（严格遵循此格式）：
{{
  "brands": [
    {{
      "brand_name": "品牌名（统一为标准名称）",
      "product_name": "具体产品名（如有），如 Air Max 90、iPhone 16。仅提及品牌则为null",
      "position_type": "first_recommendation|listed|mentioned_only|comparison_winner|comparison_loser",
      "position_rank": 1,
      "detail_level": "detailed|brief|passing",
      "sentiment": "positive|neutral|negative",
      "sentiment_score": 0.7,
      "sentiment_drivers": [
        {{
          "driver_text": "简短描述该评价因素（如：零糖配方健康、价格偏高、缓震性能出色）",
          "polarity": "positive|negative",
          "category": "product_feature|price|ux|brand_image|channel|service|innovation|other",
          "strength": 0.8,
          "source_quote": "AI原文中支撑此driver的完整句子"
        }}
      ],
      "product_features": [
        {{
          "feature_name": "被提及的产品特性/卖点（如：缓震性能、续航、拍照）",
          "feature_sentiment": "positive|negative|neutral",
          "scenario": "推荐场景/用途（如有，如：长距离跑步、日常通勤），无则null",
          "price_positioning": "AI暗示的价格定位：premium|mid_range|value|budget，无则null",
          "context_snippet": "AI原文中描述该特性的句子"
        }}
      ]
    }}
  ],
  "dimension": {{
    "industry": "行业标签（如：运动鞋、智能手机、新能源车）",
    "company": "公司标签（如：Nike Inc.、Apple Inc.）",
    "product": "产品标签（如：Air Max 90、iPhone 16）",
    "category": "产品品类（如：跑步鞋、旗舰手机、中型SUV）"
  }},
  "response_relations": [
    {{
      "entity_kind": "brand|product|attribute|profile_need",
      "type": "recommended_for|compared_with|has_attribute|addresses_need|avoid_for",
      "a_name": "source entity from the current AI response",
      "b_name": "target entity from the current AI response",
      "confidence": 0.8,
      "evidence": "quote from the current AI response"
    }}
  ]
}}

ANALYZER_V4_OVERRIDE:
Return only one strict JSON object using this analyzer_v4 top-level shape.
Do not return the legacy brands/dimension schema as the top-level output.
Every fact must include evidence_quote, or include a matching quality_flags code
such as missing_evidence_quote, relation_unresolved, citation_unlinked,
sentiment_unknown, mixed_sentiment, brand_unresolved, product_unresolved,
category_unresolved, or invalid_mention_type.
Do not use category as product_features.feature_type; represent categories as
category entities, category mentions, or has_attribute/belongs_to relations.

{{
  "analysis_meta": {{
    "schema_version": "analyzer_v4",
    "language": "zh|en|mixed",
    "response_quality": "ok|partial|empty|invalid",
    "model": "model name",
    "prompt_version": "analyzer_v4",
    "input_response_id": null,
    "input_query_id": null,
    "created_at": "ISO-8601 timestamp",
    "validator_status": "passed",
    "validator_errors": []
  }},
  "entities": [
    {{
      "entity_key": "stable key within this package",
      "entity_type": "brand|product|attribute|need|scenario|category|ingredient|channel|price_tier|other",
      "raw_name": "exact response text",
      "canonical_id": null,
      "canonical_name": null,
      "canonicalization_status": "matched|suggested|unresolved|not_applicable",
      "evidence_quote": "quote from the current response",
      "confidence": 0.8,
      "quality_flags": []
    }}
  ],
  "mentions": [
    {{
      "mention_key": "stable mention key",
      "entity_key": "entity key",
      "response_id": null,
      "raw_text": "exact mention",
      "normalized_text": "normalized mention",
      "mention_type": "brand|product|attribute|need|scenario|category|citation|other",
      "position": "top|middle|tail|unknown",
      "sentiment_label": "positive|negative|neutral|mixed|unknown",
      "sentiment_score": 0.0,
      "evidence_quote": "quote from the current response",
      "confidence": 0.8,
      "quality_flags": []
    }}
  ],
  "sentiment_drivers": [
    {{
      "driver_key": "stable driver key",
      "mention_key": "mention key",
      "target_entity_key": "entity key",
      "sentiment_label": "positive|negative|neutral|mixed|unknown",
      "driver_type": "benefit|drawback|comparison|recommendation|warning|uncertainty|price|availability|quality|other",
      "driver_summary": "short summary",
      "evidence_quote": "quote from the current response",
      "confidence": 0.8,
      "quality_flags": []
    }}
  ],
  "product_features": [
    {{
      "feature_key": "stable feature key",
      "product_entity_key": "product entity key",
      "brand_entity_key": "brand entity key or null",
      "feature_type": "ingredient|function|benefit|texture|price|scenario|audience|packaging|availability|other",
      "feature_name": "feature name",
      "feature_value": null,
      "evidence_quote": "quote from the current response",
      "confidence": 0.8,
      "quality_flags": []
    }}
  ],
  "relations": [
    {{
      "relation_key": "stable relation key",
      "subject_entity_key": "entity key",
      "relation_type": "recommended_for|compared_with|has_attribute|addresses_need|avoid_for|belongs_to_brand|substitute_for|complements|other",
      "object_entity_key": "entity key",
      "direction": "directed|undirected|unknown",
      "evidence_quote": "quote from the current response",
      "confidence": 0.8,
      "quality_flags": []
    }}
  ],
  "citations": [
    {{
      "citation_key": "stable citation key",
      "url": null,
      "domain": null,
      "title": null,
      "source_type": "official|commerce|media|ugc|social|knowledge_base|unknown|other",
      "attribution_method": "official_domain|co_occurrence|text_match|llm_inferred|unattributed|not_applicable",
      "mentioned_entity_keys": [],
      "linked_fact_keys": [],
      "evidence_quote": "quote from the current response",
      "confidence": 0.8,
      "quality_flags": []
    }}
  ],
  "quality_flags": []
}}
"""
