"""
Stage 3 豆包大模型 Prompt 模板

大模型负责：
1. 验证 Stage 1 的品牌预检测结果（排除误匹配）
2. 补全遗漏品牌（简称、昵称、新品牌）
3. 分析位置结构、详细度、情感驱动因子
4. 提取产品特性、推荐场景、价格定位
5. 三维度归类（行业/公司/产品/品类）
"""

ANALYSIS_SYSTEM = (
    "你是品牌GEO分析专家。你的任务是：\n"
    "1. 验证并补全品牌检测结果\n"
    "2. 分析品牌在AI回答中的位置、详细度和情感驱动因子\n"
    "3. 提取产品特性、推荐场景和价格定位感知\n"
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
3. **分析**每个确认品牌的位置、详细度和情感驱动因子
4. **提取**每个产品的特性/卖点、推荐场景和AI对其价格定位的感知

输出JSON（严格遵循此格式）：
{{
  "brands": [
    {{
      "brand_name": "品牌名",
      "product_name": "具体产品名（如有），如 Air Max 90、iPhone 16。仅提及品牌则为null",
      "position_type": "first_recommendation|listed|mentioned_only|comparison_winner|comparison_loser",
      "position_rank": 1,
      "detail_level": "detailed|brief|passing",
      "sentiment_drivers": [
        {{
          "driver_text": "简短描述（如：零糖配方健康）",
          "polarity": "positive|negative",
          "category": "product_feature|price|ux|brand_image|channel|service|innovation|other",
          "strength": 0.8,
          "source_quote": "AI原文中支撑此driver的句子"
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
  }}
}}
"""
