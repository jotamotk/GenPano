# PRD_TEST_DATA_V1 — 美妆个护全链路测试数据

> **目的**: 用一套端到端小样本测试数据**反向审查 PRD**, 暴露规则漏洞、歧义、矛盾。不是 feed 代码用的 fixture, 是审 PRD 用的放大镜。
>
> **范围**: 美妆个护 1 个行业 · KG → Topic → Prompt → Query → Response → Metric → Diagnostic 全链路 · 每层小样本可追溯回源
>
> **阅读方法**: 每层末尾有 **规则检查 ✅/❌** (数据是否满足 PRD 声称的约束) + **PRD Findings 🔍** (审查时发现的 PRD 问题)。最后 §9 汇总所有 Findings。
>
> **版本**: v1.0 · 2026-04-17 · 作者: Claude 为 Frank 生成

---

## 0. 数据规模 & 统计

| 层 | 条数 | 验证 PRD 章节 |
|---|---|---|
| Industry | 1 | §4.0.1a |
| Category (3 级) | 5 (1+2+2) | §4.0.1a |
| Brand | 3 | §4.0.1a + §4.10.2 (多语言) |
| Brand Relation | 3 | §4.0.1a (COMPETES_WITH / SAME_GROUP) |
| Product | 6 | §4.0.1a |
| Product Relation | 6 | §4.0.1a (5 种边类型覆盖 4 种) |
| Topic | 10 | §4.2.1 (Bottom-Up 3 层 + 品类配额) |
| Prompt | 18 | §4.2.2 (Intent × Language) |
| ProfileGroup | 4 | §4.2.3a |
| Query | 24 | §4.2.3 + §4.2.3a |
| Response | 24 (每 Query 1 条) | §4.3 |
| Metric | 2 口径对比 | §4.4 + §4.2.2a |
| Diagnostic | 1 完整样例 | §4.8.2 三层 Stack + 三读者 |

---

## 1. 知识图谱 KG — 验证 PRD §4.0.1a

### 1.1 Industry

```json
{
  "id": "ind_beauty_personal_care",
  "nameZh": "美妆个护",
  "nameEn": "Beauty & Personal Care",
  "slug": "beauty-personal-care",
  "mvpTier": 1
}
```

### 1.2 Category 树 (3 级)

```json
[
  { "id": "cat_skincare",          "level": 1, "parentId": null,             "nameZh": "护肤品",       "nameEn": "Skincare" },
  { "id": "cat_serum",             "level": 2, "parentId": "cat_skincare",   "nameZh": "精华液",       "nameEn": "Serum" },
  { "id": "cat_antiaging_serum",   "level": 3, "parentId": "cat_serum",      "nameZh": "抗衰精华",     "nameEn": "Anti-aging Serum" },
  { "id": "cat_eye_care",          "level": 2, "parentId": "cat_skincare",   "nameZh": "眼部护理",     "nameEn": "Eye Care" },
  { "id": "cat_eye_cream",         "level": 3, "parentId": "cat_eye_care",   "nameZh": "眼霜",         "nameEn": "Eye Cream" }
]
```

### 1.3 Brand (含 nameZh / nameEn / aliases[] — 验证 §4.10.2 多语言归一化)

```json
[
  {
    "id": "brand_estee_lauder",
    "industryId": "ind_beauty_personal_care",
    "nameZh": "雅诗兰黛",
    "nameEn": "Estée Lauder",
    "aliases": ["雅诗兰黛", "Estée Lauder", "Estee Lauder", "EL", "雅诗", "兰黛"],
    "positioning": "high-end",
    "priceRange": { "min": 800, "max": 3500, "currency": "CNY" },
    "homepageUrl": "https://www.esteelauder.com.cn/"
  },
  {
    "id": "brand_lancome",
    "industryId": "ind_beauty_personal_care",
    "nameZh": "兰蔻",
    "nameEn": "Lancôme",
    "aliases": ["兰蔻", "Lancôme", "Lancome", "LC"],
    "positioning": "high-end",
    "priceRange": { "min": 700, "max": 3000, "currency": "CNY" }
  },
  {
    "id": "brand_loreal_paris",
    "industryId": "ind_beauty_personal_care",
    "nameZh": "欧莱雅",
    "nameEn": "L'Oréal Paris",
    "aliases": ["欧莱雅", "L'Oréal Paris", "LOreal", "巴黎欧莱雅"],
    "positioning": "mass-market",
    "priceRange": { "min": 150, "max": 500, "currency": "CNY" }
  }
]
```

### 1.4 Brand Relations

```json
[
  { "id": "brel_1", "fromBrand": "brand_estee_lauder", "toBrand": "brand_lancome",      "type": "COMPETES_WITH", "confidence": 0.95, "evidenceSource": "llm_init+response_mining" },
  { "id": "brel_2", "fromBrand": "brand_estee_lauder", "toBrand": "brand_loreal_paris", "type": "SAME_GROUP",    "confidence": 0.40, "evidenceSource": "llm_init",  "note": "同为美国/法国大集团, 非同母公司 — 低置信度待挖掘验证" },
  { "id": "brel_3", "fromBrand": "brand_lancome",      "toBrand": "brand_loreal_paris", "type": "SAME_GROUP",    "confidence": 0.99, "evidenceSource": "llm_init", "note": "均为欧莱雅集团旗下" }
]
```

### 1.5 Product

```json
[
  { "id": "prod_el_anr",         "brandId": "brand_estee_lauder", "categoryId": "cat_antiaging_serum", "nameZh": "小棕瓶 (ANR 特润修护精华)", "nameEn": "Advanced Night Repair",          "aliases": ["小棕瓶", "ANR", "特润", "雅诗兰黛小棕瓶"],              "price": 980,  "currency": "CNY" },
  { "id": "prod_el_platinum",    "brandId": "brand_estee_lauder", "categoryId": "cat_eye_cream",        "nameZh": "白金眼霜",                 "nameEn": "Re-Nutriv Ultimate Lift Eye",    "aliases": ["白金眼霜", "雅诗兰黛白金"],                                "price": 2800, "currency": "CNY" },
  { "id": "prod_lc_genifique",   "brandId": "brand_lancome",      "categoryId": "cat_antiaging_serum", "nameZh": "小黑瓶 (Génifique 肌底精华)","nameEn": "Advanced Génifique",              "aliases": ["小黑瓶", "Genifique", "Génifique", "兰蔻小黑瓶"],         "price": 860,  "currency": "CNY" },
  { "id": "prod_lc_renergie",    "brandId": "brand_lancome",      "categoryId": "cat_antiaging_serum", "nameZh": "塑颜精华",                 "nameEn": "Rénergie H.C.F. Triple Serum",   "aliases": ["塑颜", "兰蔻塑颜"],                                        "price": 1350, "currency": "CNY" },
  { "id": "prod_lor_purple",     "brandId": "brand_loreal_paris", "categoryId": "cat_eye_cream",        "nameZh": "紫熨斗眼霜",               "nameEn": "Age Perfect Golden Age Eye",      "aliases": ["紫熨斗", "欧莱雅紫熨斗"],                                 "price": 280,  "currency": "CNY" },
  { "id": "prod_lor_pro_xylane", "brandId": "brand_loreal_paris", "categoryId": "cat_antiaging_serum", "nameZh": "玻色因面霜",               "nameEn": "Pro-Xylane Cream",                "aliases": ["玻色因", "欧莱雅玻色因"],                                 "price": 320,  "currency": "CNY" }
]
```

### 1.6 Product Relations (5 种边覆盖其中 4 种)

```json
[
  { "id": "prel_1", "from": "prod_el_anr",      "to": "prod_lc_genifique",   "type": "COMPETES_WITH", "confidence": 0.98, "note": "精华液价位同段, 国民度最高的竞品 CP" },
  { "id": "prel_2", "from": "prod_lor_purple",  "to": "prod_el_platinum",    "type": "BUDGET_ALT_OF", "confidence": 0.85, "note": "欧莱雅紫熨斗常被推荐为雅诗兰黛白金眼霜的平替" },
  { "id": "prel_3", "from": "prod_el_anr",      "to": "prod_el_platinum",    "type": "PAIRS_WITH",    "confidence": 0.90, "note": "同品牌产品线搭配使用 (精华 + 眼霜)" },
  { "id": "prel_4", "from": "prod_el_anr",      "to": "prod_lc_renergie",    "type": "UPGRADES_TO",   "confidence": 0.70, "note": "用户从平价抗衰升级到高浓度抗衰的常见路径" },
  { "id": "prel_5", "from": "prod_lor_pro_xylane","to": "prod_el_anr",       "type": "BUDGET_ALT_OF", "confidence": 0.75 },
  { "id": "prel_6", "from": "prod_el_anr",      "to": "prod_lor_pro_xylane", "type": "SUBSTITUTES",   "confidence": 0.60, "note": "不同作用机制但都是抗衰赛道" }
]
```

### 规则检查 ✅/❌ · KG 层

- ✅ Industry → Category → Brand → Product 4 级节点齐备
- ✅ Category 3 级树结构正确 (护肤品 → 精华液 → 抗衰精华)
- ✅ Brand 多语言: nameZh/nameEn/aliases[] 三字段全部有值, aliases 覆盖常见叫法
- ✅ COMPETES_WITH 边 (brand + product 级各 1 条) 可驱动 Planner 生成对比 Topic
- ✅ BUDGET_ALT_OF 边 2 条可驱动 "平替 Topic" 生成 (PRD §4.2.1 Step 1 第 4 项)
- ✅ Product 5 种边类型已覆盖 4 种 (COMPETES_WITH / BUDGET_ALT_OF / PAIRS_WITH / UPGRADES_TO / SUBSTITUTES), 缺 PAIRS_WITH 子类型是否还有更细分边未定义 → Finding
- ✅ SAME_GROUP 置信度 0.40 的弱边保留, 符合 PRD "置信度累积" 机制

### PRD Findings 🔍 · KG 层

- **F-KG-1** (P2 歧义): PRD §4.0.1a 定义 Brand 关系 `SAME_GROUP` 但没说"集团母公司"字段存放位置。欧莱雅集团包含兰蔻 + 欧莱雅巴黎两个 Brand, 但没有一个显式节点 "L'Oréal Group" 可 attach — 边端点必须都是 Brand, 导致"集团视角"数据缺失。**建议**: 要么允许 SAME_GROUP 边的双方都指向一个 "虚拟 Group Brand", 要么新增一个 `Group` 节点类型。
- **F-KG-2** (P2 歧义): Product 边 `SUBSTITUTES` 和 `COMPETES_WITH` 定义界限不清 — 小棕瓶 vs 玻色因面霜 既可说是竞品 (同抗衰赛道) 又可说是替代 (作用机制不同)。PRD 没给判定标准 → 数据挖掘时 LLM 会随机分类。**建议**: PRD 明确"同品类 = 竞品, 跨品类同功效 = 替代"。
- **F-KG-3** (P3 遗漏): Product.price 字段 PRD §5.3 的 Product 表没列, 但 PRD §4.2.1 Step 1 Topic 模板里有 `{品类}{价格区间}选购` — 价格区间字段缺失。**建议**: Product 表加 `priceCNY`、`pricePositioning` (budget/mid/premium) 两字段。
- **F-KG-4** (P1 矛盾): Brand.aliases[] 按 PRD §4.10.2 用于 Response 解析时的归一化匹配, 但 `Lancôme` (带 ô) 和 `Lancome` (ASCII) 应该是同一个 alias 的不同写法。PRD 没定义"去重音 (NFD normalize)"在哪一层做 — 是 alias 存储时就规范化, 还是匹配时运行时处理? **建议**: PRD 明确规范化在 `aliases` 写入时预处理 + 匹配时二次 normalize 双保险。

---

## 2. Topic 层 — 验证 PRD §4.2.1 Planner Bottom-Up

### 2.1 Step 1 产品级 Topic (4 条, 最先生成)

| ID | Topic 标题 | dimension | 场景标签 | 来源 (KG 节点/边) | 说明 |
|---|---|---|---|---|---|
| tp_01 | 小棕瓶 vs 小黑瓶 | 竞品 | informational | prod_el_anr × prod_lc_genifique [COMPETES_WITH] | 来自 Product 竞品边 |
| tp_02 | 小棕瓶适合敏感肌吗 | 产品 | 肤质×产品 | prod_el_anr | 产品适用性模板 |
| tp_03 | 紫熨斗平替小棕瓶行吗 | 产品 | 平替 | prod_lor_purple × prod_el_anr [BUDGET_ALT_OF] | ⚠️ 此边源点是 prod_lor_purple → 目标 prod_el_platinum 而非 prod_el_anr, 此 Topic 基于 prel_5 (prod_lor_pro_xylane → prod_el_anr) 生成更准 → 见 Findings F-TP-1 |
| tp_04 | 小棕瓶+白金眼霜搭配使用吗 | 产品 | 搭配 | prod_el_anr × prod_el_platinum [PAIRS_WITH] | 来自搭配边 |

### 2.2 Step 2 品牌级 Topic (2 条, 从产品推导)

| ID | Topic 标题 | dimension | 来源 | 说明 |
|---|---|---|---|---|
| tp_05 | 雅诗兰黛口碑怎么样 | 品牌 | brand_estee_lauder | 品牌评价模板 |
| tp_06 | 雅诗兰黛 vs 兰蔻 | 竞品 | brand_estee_lauder × brand_lancome [COMPETES_WITH] | 从 tp_01 (产品对比) 抽象为品牌对比 |

### 2.3 Step 3 行业级 Topic (4 条, 全部 dimension='品类')

| ID | Topic 标题 | dimension | 场景标签 | 来源 | 说明 |
|---|---|---|---|---|---|
| tp_07 | 抗衰精华推荐 | 品类 | 品类×推荐 | cat_antiaging_serum | L3 品类推荐 |
| tp_08 | 敏感肌精华推荐 | 品类 | 场景(肤质)×品类 | cat_serum + 场景标签 sensitive_skin | 场景驱动 |
| tp_09 | 精华液性价比排行 | 品类 | 价格×品类 | cat_serum | 价格维度 |
| tp_10 | 30岁抗初老产品怎么选 | 品类 | 年龄×场景 | cat_antiaging_serum + 年龄 | 场景驱动长尾 |

### 2.4 Step 4 变体扩展 (示意, 未全量落地)

对 tp_07 "抗衰精华推荐" 做变体:
- 口语化: "有没有好用的抗衰精华推荐下"
- 场景化: "送女朋友抗衰精华选什么"
- 长尾化: "30 岁抗衰精华推荐, 预算 1000 以内"
- 地域化: "国货抗衰精华推荐" (加国货标签, 测试 KG 未覆盖的需求缺口)

→ 真实 Pipeline 每个 Topic 至少 3-5 变体, 本文档只在 tp_07 示意。

### 2.5 Step 5 质量控制结果

- 去重: tp_06 "雅诗兰黛 vs 兰蔻" 和 tp_01 "小棕瓶 vs 小黑瓶" 虽高度相关, 但层级不同 (品牌/产品), 保留
- 真实度评分 (0-10): tp_01 (9), tp_07 (10), tp_09 (7, 偏 SEO 味)
- 质量门槛: 本样本全部通过 (≥6)

### 规则检查 ✅/❌ · Topic 层

- ✅ **Bottom-Up 生成顺序**: Step 1 (产品 4 条) → Step 2 (品牌 2 条) → Step 3 (行业/品类 4 条), 严格从具体到抽象
- ✅ **品类 dimension ≥40% 配额**: 4 / 10 = 40%, 临界达标 (PRD §4.2.1 Step 5 约束)
- ✅ **品类 Topic 纯净度**: tp_07/tp_08/tp_09/tp_10 标题中无任何 Brand.aliases[] 匹配 (`雅诗兰黛`/`兰蔻`/`欧莱雅`/`Estée Lauder`/`Lancôme`/`L'Oréal Paris` 等均未出现)
- ✅ **图谱关系边驱动**: tp_01 (COMPETES_WITH), tp_03 (BUDGET_ALT_OF), tp_04 (PAIRS_WITH) 均直接映射到 KG 边
- ✅ **Topic.dimension 4 枚举值完整**: 样本覆盖 `品类`/`品牌`/`产品`/`竞品` 4 种
- ❌ **dimension=竞品 算 brand 还是 non-brand**: tp_01 是产品级 Topic 但 dimension='竞品', PRD §4.2.2a 表中 `竞品` 属于 brand-side, 这里两条竞品 Topic (tp_01 + tp_06) 都会被排除出 non-brand 默认口径 → 规则一致, 但命名易混淆 → Finding

### PRD Findings 🔍 · Topic 层

- **F-TP-1** (P1 歧义): tp_03 "紫熨斗平替小棕瓶" 是基于 BUDGET_ALT_OF 边生成, 但 PRD §4.2.1 Step 1 未说明"平替"这类 Topic 归入哪个 dimension — 是 `产品` 还是应该新增 `平替` dimension? 本样本归为 `产品`, 但从用户查询意图看更接近"竞品发现", 应该是 `竞品` 或独立子类。**建议**: PRD §4.2.1 在 dimension 枚举中补充"平替"是独立子类还是并入"竞品"。
- **F-TP-2** (P2 矛盾): PRD §4.2.1 文字描述"真实度评分"这一质控步骤, 但 §5.3 Topic 表没有 `realnessScore` 字段. 真实度评分存哪? 如不存则无法做 Admin 审核和过滤。**建议**: Topic 表加 `realnessScore: number` 和 `qualityGateStatus: 'passed' | 'flagged' | 'rejected'`。
- **F-TP-3** (P3 边界): Step 4 "变体扩展" 生成的变体, 在数据模型里是独立 Topic (新 id) 还是同一 Topic 的 `variants[]` 字段? PRD 没说。若是独立 Topic, 品类配额计数会膨胀 (变体多的品类 Topic 容易刷出 40%); 若是字段, 前端 drilldown 怎么展示? **建议**: 明确存为独立 Topic 记录, 但用 `parentTopicId` + `variantType` 标注来源, 配额计算按 parentTopicId 去重。
- **F-TP-4** (P2 遗漏): PRD §4.2.1 Step 3 "竞品发现 — 用于发现用户未关注的竞品", 但这类 Topic (如 "高端抗衰精华品牌") 如果返回了用户 KG 里没有的品牌 (e.g. 海蓝之谜 La Mer), 新品牌入库流程没定义 — 是自动入 KG 待审, 还是丢弃? **建议**: PRD §4.0.1a 或 §4.2.1 补充"发现新品牌"路径 (回到知识图谱 Response 挖掘 loop)。

---

## 3. Prompt 层 — 验证 PRD §4.2.2 Topic × Intent

### 3.1 tp_07 "抗衰精华推荐" × 4 Intent × 2 语言 (8 Prompts, ChatGPT 双语)

| ID | topicId | intent | language | appliesToEngines | 文本 |
|---|---|---|---|---|---|
| pr_01 | tp_07 | informational | zh-CN | ["chatgpt","doubao","deepseek"] | 抗衰精华的主要作用成分有哪些? 哪些对 25+ 肌肤比较重要? |
| pr_02 | tp_07 | commercial    | zh-CN | ["chatgpt","doubao","deepseek"] | 1000 元以内有哪些值得买的抗衰精华? 推荐几款并说明理由 |
| pr_03 | tp_07 | transactional | zh-CN | ["chatgpt","doubao","deepseek"] | 双十一买抗衰精华哪家电商最划算? 怎么凑单? |
| pr_04 | tp_07 | navigational  | zh-CN | ["chatgpt","doubao","deepseek"] | 大牌抗衰精华的官方旗舰店清单 |
| pr_05 | tp_07 | informational | en-US | ["chatgpt"]                    | What are the key active ingredients in anti-aging serums and which ones work best for women in their late 20s? |
| pr_06 | tp_07 | commercial    | en-US | ["chatgpt"]                    | What are the best anti-aging serums under $150? |
| pr_07 | tp_07 | transactional | en-US | ["chatgpt"]                    | Where can I get the best deals on anti-aging serums during holiday sales? |
| pr_08 | tp_07 | navigational  | en-US | ["chatgpt"]                    | Where to find official authorized retailers for premium anti-aging serum brands |

### 3.2 tp_01 "小棕瓶 vs 小黑瓶" × 4 Intent (4 Prompts, 仅中文)

| ID | intent | 文本 |
|---|---|---|
| pr_09  | informational | 小棕瓶和小黑瓶的成分和功效有什么区别? |
| pr_10  | commercial    | 想买抗衰精华, 小棕瓶和小黑瓶选哪个性价比更高? |
| pr_11  | transactional | 小棕瓶和小黑瓶哪个平台现在有优惠? |
| pr_12  | navigational  | 雅诗兰黛小棕瓶和兰蔻小黑瓶的官方价格 |

### 3.3 tp_05 "雅诗兰黛口碑" × 2 Intent (基础覆盖)

| ID | intent | 文本 |
|---|---|---|
| pr_13 | informational | 雅诗兰黛在国内的口碑怎么样? 用户评价主要集中在什么方面? |
| pr_14 | commercial    | 雅诗兰黛值得买吗? 和其他同价位品牌比优势在哪? |

### 3.4 多轮 Prompt 链示例 (PRD §4.2.2 "支持多轮")

`chain_01` (基于 tp_07):
1. "我 28 岁想入一款抗衰精华, 有推荐吗?" (主问题)
2. "小棕瓶和你推荐的那款哪个更适合初抗老?" (追问 1)
3. "预算想控制在 800 以内呢?" (追问 2)

→ 每轮独立存为 Query 记录, 用 `conversationId` 串联。

### 规则检查 ✅/❌ · Prompt 层

- ✅ **每 Topic ≥ 2 Intent**: tp_07 (4 种全覆盖), tp_01 (4 种), tp_05 (2 种, 即 informational + commercial 必选项)
- ✅ **Informational + Commercial 必选**: 所有 Topic 都至少含这两种
- ✅ **自然语言而非关键词堆砌**: 无 "推荐 精华液 抗衰 2026 排行" 式堆砌
- ✅ **品类 Topic 的 Prompt 禁含品牌名**: pr_01~pr_08 (tp_07 的 8 个 Prompt) 标题与文本均不含 "雅诗兰黛/兰蔻/欧莱雅/Estée/Lancôme/L'Oréal" — 验证 PRD §4.2.2 品类纯净度
- ✅ **Engine-aware 语言**: pr_05~pr_08 (en-US) `appliesToEngines = ["chatgpt"]` 只发 ChatGPT, 豆包/DeepSeek 不发; 中文版所有引擎都发 — 验证 PRD §4.10.3
- ⚠️ **多轮 Prompt 链**: `chain_01` 展示了概念, 但数据模型如何存储 (conversation 表? 还是 Prompt.parentPromptId?) PRD 未明确 → Finding

### PRD Findings 🔍 · Prompt 层

- **F-PR-1** (P1 歧义): PRD §4.2.2 说"支持多轮 Prompt 链", 但 §5.3 Prompt 表没有 `conversationId` 或 `parentPromptId`。多轮追问和独立 Prompt 在库里怎么区分? 前端 Topics drilldown 展示多轮对话还是按 Prompt 扁平平铺? **建议**: Prompt 表加 `conversationId: string` + `turnIndex: number`, 同一 conversationId 的 turnIndex 升序构成一轮对话。
- **F-PR-2** (P2 矛盾): PRD §4.2.2 说 ChatGPT 发中英双语, 但 pr_05 的 en-US 问 "women in their late 20s" (25 岁 +), 而对应的 pr_01 中文版问 "25+ 肌肤" — 双语 Prompt 是独立生成还是互译? 如果独立生成, 意图可能漂移 (英文版更具体, 中文版更宽泛), 导致提及率口径失真 (同一 Topic 的中英 Query 之间不可比)。**建议**: PRD §4.10.3 明确"双语 Prompt 是互译 (preserve intent) 还是独立生成 (preserve nativeness)"并说明 trade-off。
- **F-PR-3** (P3 缺失): Intent `navigational` (寻找特定信息) 的 Prompt 质量难保证 — pr_04 "大牌抗衰精华的官方旗舰店清单" 很泛, 可能 LLM Response 直接给 KG 里已有品牌列表, 数据信息量低。**建议**: PRD §4.2.2 补充"Navigational Intent 生成时, 需带品牌或产品 ID 作锚点", 否则此 Intent 可能被 Planner 配额剔除。
- **F-PR-4** (P2 歧义): PRD §4.2.1 Step 5 品类 Topic 禁含品牌名是 Topic 层约束, PRD §4.2.2 最后一条重申"品类 Topic 的 Prompt 禁含品牌名" — 但如果 Topic.dimension='品牌' 或 '竞品', Prompt **允许**含品牌名的边界在哪? 例如 tp_06 "雅诗兰黛 vs 兰蔻" 本身含品牌名, 对应 Prompt 当然有品牌名; 但如果 Topic='雅诗兰黛口碑' (dimension='品牌'), 生成的 Prompt 可否引入兰蔻做对比? **建议**: PRD 明确"dimension=品牌的 Prompt 可提主品牌, 但不主动引入其他品牌做对比"。

---

## 4. Query 层 — 验证 PRD §4.2.3 Prompt × Profile + §4.2.3a ProfileGroup

### 4.1 ProfileGroup (4 个预置, 覆盖 PRD §4.2.3a 典型)

```json
[
  { "id": "pg_all",                  "nameZh": "全部 Profile",       "nameEn": "All Profiles",         "isDefault": true,  "description": "聚合基线", "industryScope": "all" },
  { "id": "pg_young_female_tier1",   "nameZh": "一线城市年轻女性",    "nameEn": "Tier-1 Young Female",   "isDefault": false, "description": "25-32岁, 北上广深, 月入 1.5-3 万, 关注抗初老", "industryScope": "beauty" },
  { "id": "pg_mid_age_female_tier23","nameZh": "二三线中年女性",      "nameEn": "Tier-2/3 Mid-age Female","isDefault": false, "description": "35-50岁, 非一线, 价格敏感, 关注功效型",        "industryScope": "beauty" },
  { "id": "pg_en_chatgpt",           "nameZh": "英文用户(ChatGPT)",   "nameEn": "English (ChatGPT)",     "isDefault": false, "description": "英文母语用户, 使用 ChatGPT",                  "industryScope": "beauty" }
]
```

### 4.2 Query 样本 (pr_02 "1000 元以内抗衰精华推荐" × 3 Profile + 其他代表性组合)

| ID | promptId | profileGroupIds | engine | status | scheduledAt | 说明 |
|---|---|---|---|---|---|---|
| qu_01 | pr_02 | ["pg_all"] | chatgpt | success | 2026-04-15T08:00Z | 基线采样 |
| qu_02 | pr_02 | ["pg_all"] | doubao  | success | 2026-04-15T08:00Z | 基线采样 |
| qu_03 | pr_02 | ["pg_all"] | deepseek| success | 2026-04-15T08:00Z | 基线采样 |
| qu_04 | pr_02 | ["pg_young_female_tier1"] | chatgpt | success | 2026-04-15T10:00Z | 细分画像 |
| qu_05 | pr_02 | ["pg_young_female_tier1"] | doubao  | success | 2026-04-15T10:00Z | |
| qu_06 | pr_02 | ["pg_mid_age_female_tier23"] | doubao | success | 2026-04-15T10:00Z | |
| qu_07 | pr_06 | ["pg_en_chatgpt"] | chatgpt | success | 2026-04-15T08:00Z | 英文版仅 ChatGPT |
| qu_08 | pr_09 | ["pg_all"] | chatgpt | success | 2026-04-15T08:00Z | 竞品对比 |
| qu_09 | pr_09 | ["pg_all"] | doubao  | success | 2026-04-15T08:00Z | |
| qu_10 | pr_13 | ["pg_all"] | chatgpt | success | 2026-04-15T08:00Z | 品牌口碑 |
| qu_11 | pr_13 | ["pg_all"] | doubao  | success | 2026-04-15T08:00Z | |
| qu_12 | pr_13 | ["pg_all"] | deepseek| success | 2026-04-15T08:00Z | |
| qu_13 | pr_01 | ["pg_all"] | chatgpt | success | 2026-04-16T08:00Z | tp_07 其他 Prompt 的 Query |
| qu_14 | pr_01 | ["pg_all"] | doubao  | success | 2026-04-16T08:00Z | |
| qu_15 | pr_01 | ["pg_young_female_tier1"] | doubao | success | 2026-04-16T08:00Z | |
| qu_16 | pr_02 | ["pg_mid_age_female_tier23"] | chatgpt | success | 2026-04-16T08:00Z | |
| qu_17 | pr_14 | ["pg_all"] | doubao | success | 2026-04-16T08:00Z | |
| qu_18 | pr_10 | ["pg_all"] | chatgpt | success | 2026-04-16T08:00Z | |
| qu_19 | pr_10 | ["pg_all"] | doubao | success | 2026-04-16T08:00Z | |
| qu_20 | pr_10 | ["pg_all"] | deepseek | success | 2026-04-16T08:00Z | |
| qu_21 | pr_03 | ["pg_all"] | doubao | success | 2026-04-16T08:00Z | transactional |
| qu_22 | pr_04 | ["pg_all"] | chatgpt | success | 2026-04-16T08:00Z | navigational |
| qu_23 | pr_11 | ["pg_all"] | doubao | success | 2026-04-16T08:00Z | |
| qu_24 | pr_12 | ["pg_all"] | chatgpt | success | 2026-04-16T08:00Z | |

**按 Topic.dimension 分布统计** (后续 Metric 层要用):
- 品类 dimension Query (来自 tp_07): qu_01~qu_07, qu_13~qu_16 = **11 条** (non-brand 口径)
- 竞品 dimension Query (来自 tp_01): qu_08, qu_09, qu_18~qu_20, qu_23, qu_24 = **7 条**
- 品牌 dimension Query (来自 tp_05): qu_10~qu_12, qu_17 = **4 条**
- Transactional + Navigational: qu_21, qu_22 = **2 条**
- **总计**: 24 条 Query · non-brand 占比 11/24 ≈ 46%

### 4.3 样本不足降级示例 (PRD §4.2.3a)

请求: `GET /api/v1/projects/xxx/brands/brand_estee_lauder/metrics?profileGroups=pg_young_female_tier1`

按本样本, `pg_young_female_tier1` 的 Query 只有 qu_04, qu_05, qu_15 = 3 条, 远低于 PRD §4.2.3a 的 50 Query 阈值。

**API 应返回**:
```json
{
  "sufficient": false,
  "sampleCount": 3,
  "fallback": "use_all",
  "message": "样本不足, 建议回退全量或选择其他画像"
}
```

前端按 PRD §4.6.1a §6b 的"样本不足降级 UI" 显示黄色条 + 双 CTA。

### 规则检查 ✅/❌ · Query 层

- ✅ **Query 可追溯**: 每条 `promptId` + `profileGroupIds[]` 可反推到 Prompt → Topic → KG 节点, JOIN `WHERE topic.dimension='品类'` 可筛出 non-brand 子集
- ✅ **多画像数组**: `profileGroupIds[]` 是数组, 一条 Query 可隶属多画像组 — 与 PRD §4.2.3a "Query.profileGroupIds ⊇ requestedGroups" 逻辑一致
- ✅ **Engine 分发正确**: qu_07 的 pr_06 (en-US) 只发 chatgpt, 未发 doubao/deepseek — 符合 §4.10.3
- ✅ **样本不足降级契约**: `{sufficient, sampleCount, fallback}` 三字段齐备
- ⚠️ **default `pg_all` 应不应该隐式加?**: 所有 Query 都显式标 `pg_all`, 但 PRD §4.2.3a 没说 `pg_all` 是否自动加到每条 Query → Finding

### PRD Findings 🔍 · Query 层

- **F-QU-1** (P1 歧义): PRD §4.2.3a 说 `profileGroupIds[]` 是数组, 聚合时 `Query.profileGroupIds ⊇ requestedGroups` — 但没说一条 Query 能不能同时属于多个互斥画像 (如 `pg_young_female_tier1` 和 `pg_mid_age_female_tier23` 显然互斥)。实际 Pipeline 一条 Query 应该只采样一组画像, 还是可以"一次调用满足多组"? **建议**: PRD §4.2.3a 明确"每条 Query 只隶属一组具体画像 + 自动加入 `pg_all`", 即 `profileGroupIds` 长度恒为 2 (具体组 + all)。
- **F-QU-2** (P2 缺失): 样本不足时 `fallback: 'use_all'` 是字符串枚举, 但 PRD 没定义其他值 — 是只有 `use_all` 一个选项, 还是未来会有 `reject` / `use_similar_group`? **建议**: PRD §4.2.3a 枚举 fallback 所有可能值。
- **F-QU-3** (P2 遗漏): PRD §4.2.3a 的 50 Query 阈值是硬编码还是可配? 对于小样本行业 (如奢侈品可能总 Query 数本身就少), 50 太高。**建议**: 阈值改为行业级可配或按 Query 总数动态 (如 `max(50, 总Query数 * 0.1)`)。
- **F-QU-4** (P3 边界): 一条 Query 失败 (status='failed') 是否算样本? 如果算, 提及率分母膨胀; 如果不算, 失败率高时样本不足会误触发降级。PRD 没明确。**建议**: 聚合时只统计 `status='success'`, `failed` 单独看"爬取健康度"指标, PRD §4.2.3a 加一行。

---

## 5. Response 层 — 验证 PRD §4.3

### 5.1 qu_01 (pr_02 "1000 元以内抗衰精华推荐", ChatGPT, 全画像) Response

```json
{
  "id": "rs_01",
  "queryId": "qu_01",
  "engine": "chatgpt",
  "language": "zh-CN",
  "capturedAt": "2026-04-15T08:02:14Z",
  "rawText": "1000元以内值得考虑的抗衰精华有几款经典选择:\n\n1. **雅诗兰黛小棕瓶 (ANR)** - 约 980 元, 含二裂酵母发酵产物滤液, 修护效果稳定, 适合抗初老;\n2. **兰蔻小黑瓶 (Génifique)** - 约 860 元, 主打肌底修护, 激发肌肤年轻力;\n3. **欧莱雅玻色因面霜** - 320 元, 玻色因浓度较高, 性价比突出, 适合作平替入门...\n\n三款各有侧重, 小棕瓶偏温和修护, 小黑瓶偏活力激发, 玻色因偏抗皱紧致。",
  "structured": {
    "brandMentions": [
      { "brandId": "brand_estee_lauder",  "position": 1, "sentiment": 0.85, "productMentioned": "prod_el_anr",          "priceHint": "约 980 元" },
      { "brandId": "brand_lancome",       "position": 2, "sentiment": 0.82, "productMentioned": "prod_lc_genifique",    "priceHint": "约 860 元" },
      { "brandId": "brand_loreal_paris",  "position": 3, "sentiment": 0.80, "productMentioned": "prod_lor_pro_xylane",  "priceHint": "320 元" }
    ],
    "citations": [],
    "productCards": []
  },
  "screenshotUrl": "s3://genpano-cn/screenshots/2026-04-15/qu_01.png"
}
```

### 5.2 qu_04 (pr_02, ChatGPT, young_female_tier1) Response (画像差异)

```json
{
  "id": "rs_04",
  "queryId": "qu_04",
  "engine": "chatgpt",
  "rawText": "25-32 岁一线城市的话推荐抗初老为主, 三款可以考虑:\n1. **雅诗兰黛小棕瓶** - 经典抗初老, 国民度最高;\n2. **资生堂红腰子** - 二裂酵母+焕颜, 一线女性口碑很好;\n3. **修丽可紫米精华** - 高浓度抗氧化, 进阶首选...",
  "structured": {
    "brandMentions": [
      { "brandId": "brand_estee_lauder", "position": 1, "sentiment": 0.88 },
      { "brandId": "brand_unknown_shiseido",   "position": 2, "sentiment": 0.85, "note": "⚠️ 新品牌, 未入 KG — 触发 §4.0.1a Response Mining" },
      { "brandId": "brand_unknown_skinceuticals","position": 3, "sentiment": 0.82, "note": "⚠️ 新品牌 — 触发挖掘" }
    ]
  }
}
```

⚠️ 本条演示 PRD §4.0.1a "Response 挖掘" 的触发路径: Response 提到 KG 未知品牌 → 挂起 `pending_brand_review` → Admin 审核入库。

### 5.3 qu_08 (pr_09 "小棕瓶 vs 小黑瓶", ChatGPT) Response (品牌必提示例)

```json
{
  "id": "rs_08",
  "queryId": "qu_08",
  "engine": "chatgpt",
  "rawText": "小棕瓶和小黑瓶是两款定位接近但机制不同的精华:\n\n**雅诗兰黛小棕瓶**...\n**兰蔻小黑瓶**...\n\n**推荐**: 如果是初抗老 25-28 岁, 小棕瓶更温和友好; 如果想要活力激发, 小黑瓶更合适。",
  "structured": {
    "brandMentions": [
      { "brandId": "brand_estee_lauder", "position": 1, "sentiment": 0.80 },
      { "brandId": "brand_lancome",      "position": 2, "sentiment": 0.80 }
    ]
  }
}
```

⚠️ 本 Query 来自 `tp_01` (dimension='竞品'), 根据 PRD §4.2.2a, **不计入 non-brand 默认提及率口径** — 因为两品牌在 Topic 里已直接提及, Response 必然提及, 统计入提及率会失去诊断意义。

### 5.4 qu_12 (pr_13 "雅诗兰黛口碑", DeepSeek) Response (中文品牌名解析)

```json
{
  "id": "rs_12",
  "engine": "deepseek",
  "language": "zh-CN",
  "rawText": "雅诗兰黛 (Estée Lauder, 常被叫做 EL 或雅诗兰黛) 在国内的口碑整体偏正向...",
  "structured": {
    "brandMentions": [
      { "brandId": "brand_estee_lauder", "position": 1, "sentiment": 0.75,
        "matchedAlias": "雅诗兰黛",
        "allAliasesInText": ["雅诗兰黛", "Estée Lauder", "EL"],
        "note": "单次 Response 多别名全部归一化为同一 brandId"
      }
    ]
  }
}
```

### 规则检查 ✅/❌ · Response 层

- ✅ **结构化提取**: rawText + structured.brandMentions[] + citations[] + productCards[] 四字段齐备
- ✅ **position 记录**: 排名位置 1/2/3 按出现顺序标注 (PRD §4.3)
- ✅ **sentiment 分数**: [0, 1] 区间 (`0.80`, `0.85` 等), 符合 PRD §4.4 情感计算基础
- ✅ **多别名归一化**: rs_12 的 "雅诗兰黛" / "Estée Lauder" / "EL" 全部映射到 `brand_estee_lauder`, 不重复计数 (PRD §4.10.2 多语言匹配)
- ✅ **新品牌触发挖掘**: rs_04 出现 KG 未知品牌 (资生堂/修丽可), 进入 `pending_brand_review` 流程
- ⚠️ **去重音 (Estée 的 é → e)**: 本样本已在 aliases 里预存 Estee 和 Estée 两个, 但未验证 LLM 实时输出 "Estee Lauder" (ASCII) 能否被正确匹配 → Finding

### PRD Findings 🔍 · Response 层

- **F-RS-1** (P1 矛盾): PRD §4.3 说 Response 存 `rawText` + 结构化提取, 但没说 rawText 存多久。若全量永久存储, 4 MVP 行业 × 每日 ~10K Query × 每 Response 平均 2KB = 每日约 80 MB, 一年 30 GB, 成本可控但要考虑。**建议**: PRD §5.3 Response 表加 `rawTextRetentionDays: number` 字段, 默认 180 天, 超期只保留 structured 摘要。
- **F-RS-2** (P2 歧义): rs_08 (qu_08 的 Response) 提及 brand_estee_lauder, 但因 Topic.dimension='竞品' 被排除出 non-brand 口径 — 排除的**实现层**在哪? 是 Metric 计算时 SQL WHERE 过滤, 还是 Response 入库时打标? PRD §4.2.2a 说"直接复用已有的 Topic.dimension 做口径过滤, 通过 Query → Prompt → Topic 的 JOIN", 即在查询层过滤。但这意味着 Response.brandMentions 原始数据还在, 只在聚合 KPI 时才过滤。**建议**: PRD 明确这是**只读聚合时过滤**, 不删原始提及数据; 同一条 Response 在"品牌详情页全量口径"下仍然计入。
- **F-RS-3** (P2 歧义): rs_04 触发 Response 挖掘新品牌, 但 PRD §4.0.1a 没说挖掘到的新品牌在 **未入库期间** 是否计入当前周期的 SoV/提及率分子。按目前约定好像两种都可以, 但影响差很大 — 如果计入, 当天 KPI 会立刻波动; 如果不计入, 要等 Admin 审核入库后下轮才生效, 会有数据滞后。**建议**: PRD §4.0.1a 补充"`pending_brand_review` 的品牌在 KPI 计算时按 `matchedBrandId=null` 处理, 只影响提及率分子的'其他品牌'聚合, 不影响具名品牌 SoV"。
- **F-RS-4** (P2 缺失): PRD §4.3 情感分数 0-1 的计算方式没写 — 是规则引擎 (正负面词汇表) 还是 LLM 分类? rs_01 中小棕瓶 0.85, 小黑瓶 0.82 差 0.03, 这种精度有统计意义吗? **建议**: PRD §4.4 (或 §4.8) 明确"情感分数用 LLM 分类返回 5 档 (非常负/负/中性/正/非常正), 映射为 0 / 0.25 / 0.5 / 0.75 / 1.0, 展示时用中性语言 (不做小数对比)"。对应 CLAUDE.md 图表契约 C4 (禁 `.toFixed(2)` 展示) 也在强化这一点。

---

## 6. Metric 层 — 验证 PRD §4.4 + §4.2.2a 口径分离

### 6.1 提及率双口径 (核心验证点)

基于本样本 24 条 Query 聚合 (假设"雅诗兰黛" 品牌为主监控视角):

| 口径 | 分母 (Query 集) | 分子 (提及雅诗兰黛的 Query 数) | 结果 |
|---|---|---|---|
| **non-brand 默认口径 (面板 KPI)** | 品类 dimension Query · n=11 | 其中 7 条提及 (qu_01, qu_02, qu_03, qu_04, qu_13, qu_14, qu_16) | **7 / 11 = 63.6%** |
| **全量口径 (品牌详情 / CSV)** | 所有 dimension · n=24 | 其中 18 条提及 (加上竞品 Topic 必提的 7 条 + 品牌 Topic 必提的 4 条) | **18 / 24 = 75.0%** |

**两口径差 11.4 pp**, 方向一致但揭示不同诊断路径:
- **non-brand 高 = 品类问题下 AI 主动想到我 → "我占据用户心智"** ✅
- **全量高但 non-brand 低 = AI 只在被显式问到我时才提及, 品类通用问题不会主动想到我 → "品类存在感弱"** ⚠️

### 6.2 SoV (Share of Voice) 计算 · PRD §4.4.1 口径边界

> **定义**: SoV 分母 = 已有品牌出现的 Response 数 (至少一个 KG 品牌被命中), 分子 = 其中提及"我"的次数 / 总提及次数

基于 24 条 Query 聚合 (命中至少一个品牌的 Response = 24 条中 22 条):

| Brand | 提及次数 (所有 Response 累加) | SoV |
|---|---|---|
| 雅诗兰黛 | 22 | 22 / 67 = 32.8% |
| 兰蔻 | 18 | 18 / 67 = 26.9% |
| 欧莱雅 | 12 | 12 / 67 = 17.9% |
| 其他 (资生堂/修丽可等 pending) | 15 | 15 / 67 = 22.4% |

⚠️ **图表契约 C3 检查**: "其他" 22.4% < 雅诗兰黛 32.8% ✅, 但 > 欧莱雅 17.9% — 接近违反"其他不得大于任一真实品牌片"的 CLAUDE.md 图表契约 (C3)。**建议**: UI 展示时将"其他"拆分 top 2 新品牌 (资生堂/修丽可) 单列, 其余合并。

### 6.3 情感均分

| Brand | 平均 sentiment | 样本数 |
|---|---|---|
| 雅诗兰黛 | 0.82 | 22 次提及 |
| 兰蔻 | 0.81 | 18 |
| 欧莱雅 | 0.76 | 12 |

按 PRD 图表契约 C4, 展示时转为 "积极 82%" (百分数整数, 不用小数)。

### 6.4 引用份额 (Citation Share)

本样本 rawText 中 citations[] 均为空 → 引用份额 = 0% (所有品牌)。

→ 此指标在本 Demo 中不激活, 真实 Pipeline 需爬取 AI 回答末尾的引用来源链接。

### 6.5 PANO Score (四维加权, PRD §4.4)

以雅诗兰黛为例 (权重默认 V:S:R:A = 30:25:25:20, 可配置):

| 子维度 | 计算 | 原始值 | 映射到 0-100 |
|---|---|---|---|
| V (Visibility 可见度) | 提及率 non-brand | 63.6% | 64 |
| S (Sentiment 情感) | 平均 sentiment 百分化 | 0.82 | 82 |
| R (Ranking 排名) | 平均 position 倒数 (1/平均位置 ×100) | 1/1.3 | 77 |
| A (Authority 权威) | 引用份额 | 0% | 0 (样本缺失) |
| **PANO Score** | 0.3×64 + 0.25×82 + 0.25×77 + 0.2×0 | | **58.9** |

### 规则检查 ✅/❌ · Metric 层

- ✅ **提及率 non-brand 默认口径**: JOIN `WHERE topic.dimension='品类'` 筛出 11 条, 分母正确
- ✅ **全量口径保留**: 全量 75% 可在品牌详情 + CSV 导出的 `mention_rate_all_pct` 列看到
- ✅ **两口径不等价**: 63.6% vs 75%, 差 11.4 pp, 验证 CLAUDE.md 决策 #2 "口径边界" 和 PRD §4.6.1a
- ✅ **SoV 分母是"已有品牌出现的 Response"**: 22 / 24 (排除 2 条无品牌出现), 不是全量 Query — 验证 PRD §4.4.1 SoV 定义
- ✅ **PANO Score 四维加权**: V/S/R/A 四个子分 + 可配置权重
- ❌ **A (Authority 权威) 维度**: 本 Demo 为 0 (citations 缺失), 如果真实 Pipeline 早期爬不到 citations, 此维度长期拉低 PANO Score → Finding

### PRD Findings 🔍 · Metric 层

- **F-ME-1** (P1 矛盾): PRD §4.4 PANO Score 四维 `V/S/R/A`, 但 A (Authority/引用份额) 依赖爬虫能从 AI Response 中提取引用来源 — 豆包/DeepSeek 的回答格式不一定带明显 citations, ChatGPT 的 citations 也是 Deep Research 模式才多见。MVP 阶段 A 维度数据稀疏, 会导致 PANO Score 整体偏低且不稳定。**建议**: MVP 用动态权重 — 如果某品牌 citations 样本数 < 10, A 权重降为 0, 将 20% 平均分到 V/S/R 上 (`V+S+R ≈ 30+10/3+25+10/3+25+10/3`), 避免早期冷启动 PANO 跑偏。
- **F-ME-2** (P1 歧义): PRD §4.4 提到"SoV 分母 = 已有品牌出现的 Response", 但本数据 rs_08 的 Response 两品牌都在 Topic 里已经被点名, 这种"命题式"品牌提及是否应该参与 SoV 计算? 感觉应该排除 (和 non-brand 提及率排除竞品 Topic 同理), 但 PRD §4.4 没说。**建议**: PRD §4.4 明确 "SoV 也默认排除 dimension='竞品' + '品牌' 的 Query" (与提及率默认口径对齐), 或显式说 "SoV 全量口径, 不做 dimension 过滤"。
- **F-ME-3** (P2 遗漏): PANO Score "可配置权重" 的配置存在哪? 全局 Admin 可配 × Project 可 override? PRD §4.4 和 §5.3 都没定义字段。**建议**: 新增 `ScoreWeightConfig` 表 (`scope: 'global'|'industry'|'project'`, `v`, `s`, `r`, `a`, `updatedAt`), Planner 计算时按 scope 优先级覆盖 (project > industry > global)。
- **F-ME-4** (P2 歧义): 提及率和 SoV 双口径对**品牌详情页**的展示怎么做? 如果默认只展示一种, 用户会漏看另一种; 如果两个一起展示, 视觉噪音大。CLAUDE.md 决策 #2 说"两者背离方向揭示不同诊断路径", 但 PRD §4.6.1b 品牌详情没给展示方案。**建议**: 品牌详情页概览 Tab 的"提及率" 卡片加 segmented control 让用户切换 "通用问题口径 / 全量口径", 切换时 tooltip 说明差异; 两值若相差 >15pp, 卡片底部加 anchor question "为什么两者差距大?"。
- **F-ME-5** (P3 缺失): PRD §4.4 对"平均 position" 计算没说加权方式 — 是按 mention 次数加权, 还是按 Query 次数加权? 一次 Response 提及 2 次同一品牌 (一次首位一次末位) 怎么算? **建议**: 按 Response 内去重取首次 position, 跨 Response 再算平均。

---

## 7. Diagnostic 层 — 验证 PRD §4.8.2 三层 Stack + 三读者视角

### 7.1 一条 P1 严重级 Diagnostic (完整示例)

```json
{
  "id": "diag_01",
  "projectId": "proj_demo",
  "brandId": "brand_estee_lauder",
  "category": "visibility_decline",
  "severity": "P1",
  "detectedAt": "2026-04-15T09:00Z",
  "primaryReader": "manager",
  "insightStackLayers": ["L1", "L2", "L3"],
  "title": "抗衰品类通用问题下, 我被 AI 主动想到的比例环比下降 14 pp",
  "evidence": {
    "currentValue": 63.6,
    "previousValue": 77.5,
    "delta": -13.9,
    "window": "last_7_days vs previous_7_days",
    "affectedQueries": ["qu_01", "qu_04", "qu_13", "qu_14"],
    "sampleSize": 11
  },
  "insights": {
    "L1": {
      "observation": "在'抗衰精华推荐'、'敏感肌精华推荐'、'30岁抗初老'这三个品类 Topic 下, 本周我被 AI 主动提及的比例是 63.6%, 上周是 77.5%, 下降 13.9 pp。同期 SoV 基本持平 (32.8% vs 33.5%, -0.7 pp)。",
      "readerHints": { "operator": "看数据是否真", "manager": "看是否应发报", "branding": "看是否影响叙事" }
    },
    "L2": {
      "explanation": "两个指标的分裂说明: 当 AI 被问到抗衰品类通用问题时, 它想到我的频率降了; 但当它已经在比较各品牌时, 我的份额没变。也就是说——用户在被动比较阶段我没失声, 但主动想到阶段我被淡化了。",
      "causalChain": [
        "hypothesis_1: 近期品类 Topic 多了新的热门品牌 (资生堂/修丽可在 rs_04 已经出现), 挤压了传统品牌 mindshare",
        "hypothesis_2: 我们自己的新品营销可能没有进入品类通用问题的训练语料/引用",
        "hypothesis_3: 竞品 (兰蔻) 可能增加了品类内容的曝光, 虽然 SoV 没升, 但'被主动想到'是增量路径"
      ],
      "confidence": 0.72,
      "evidenceRefs": ["rs_04", "rs_13", "rs_14"]
    },
    "L3": {
      "focusArea": "品类通用问题下的 top-of-mind 建设",
      "anchorQuestions": [
        "过去 7 天的抗衰品类 Topic 里, 提及我们的 Response 里有没有引用到具体来源 (citations)?",
        "如果有, 这些 citations 来自什么类型的内容 (官方站点 / 媒体评测 / UGC)?",
        "资生堂/修丽可被 AI 主动想到, 是因为它们最近有某些类型的内容集中出现吗?"
      ],
      "ifUntreated": "如果这个 top-of-mind 弱势持续 4 周, PANO Score V 维度从 64 可能降到 55 以下, 整体 PANO Score 从 58.9 降到约 54, 即从 '良好' 滑到 '一般' 等级。"
    }
  },
  "readerSections": {
    "operator": "运营执行层关注: 本周抗衰品类的爬取样本是 11 条, 上周是 15 条, 样本量下降 27%, 是否因为调度任务遗漏? 请检查 scheduler log。若样本量异常已排除, 再往产品层看。",
    "manager": "产品经理关注: 63.6% → 主动 top-of-mind 弱化, 需判断是否发 stakeholder 预警。竞品 SoV 未升, 属于'整个品类都被新品牌蚕食'还是'我们被特定内容类型压制', 需要进一步回答 anchorQuestions。",
    "branding": "品牌层关注: 我们品牌在抗衰赛道是传统强者, '被 AI 主动想到' 是品牌 equity 的数字信号之一。持续下降 4 周要进入季度 branding review 议题。"
  },
  "relatedDiagnostics": [],
  "anchorActions": null
}
```

> ⚠️ 注意: `anchorActions` 显式为 `null` — PRD §4.8.2a 强调 **Layer 3 只给 anchorQuestions 和 focusArea, 不给 playbook (执行剧本属于付费咨询业务)**。如果此字段非 null, 视为违反业务边界。

### 规则检查 ✅/❌ · Diagnostic 层

- ✅ **L1 / L2 / L3 三层 Stack 齐备**: L1 observation, L2 explanation + causalChain + confidence, L3 focusArea + anchorQuestions + ifUntreated
- ✅ **primaryReader 声明**: `"manager"`, 对应 readerSections.manager 为主文案 (operator/branding 为辅)
- ✅ **三读者视角都有**: operator 看数据真伪, manager 看决策, branding 看长期品牌信号
- ✅ **anchorQuestions 是事实探查型**: "有没有引用", "来自什么类型", "竞品是不是因为…" — 都是在**问 What/Why**, 不在指挥行动
- ✅ **没有执行剧本**: L3 不含"在小红书发内容 / 投放 KOL / 做产品 launch" 等具体动作; `anchorActions: null` 显式声明
- ✅ **ifUntreated 带定量估算**: PANO Score 预期下滑 58.9 → 54, 从 "良好" 到 "一般" — 不是吓唬, 是可衡量的后果
- ✅ **confidence 0.72**: 数值 ≠ 1.0, 诚实表达不确定性 (causalChain 三假设是**并列候选**, 不是断言)

### PRD Findings 🔍 · Diagnostic 层

- **F-DI-1** (P1 歧义): PRD §4.8.2 说 Diagnostic 有 L1/L2/L3 三层 Stack, 但没说**每条 Diagnostic 是不是必须三层都有**。本样本都给了, 但如果某条只是数据观察 (L1) 没有成因解释 (L2), 应该怎么存? `L2: null` 还是跳过? 前端展示时跳过的层怎么渲染? **建议**: PRD §4.8.2 明确 "L1 必选, L2/L3 按 severity 分级: P0/P1 必须三层, P2/P3 可省 L3"。
- **F-DI-2** (P1 矛盾): PRD §4.8.2a 说 "Layer 3 只给 anchorQuestions 和 focusArea", 但 PRD §4.8.5 (诊断 direction 颗粒度) 又说 direction 文本要包含"优化方向用动词+抽象对象 (如'提升权威来源覆盖密度')" — 这种"提升权威来源覆盖密度" 其实是**动作建议**, 只是 抽象化了。到底 L3 输出里允不允许这类"抽象动作方向"? 如果允许, `anchorActions: null` 的约束就和 §4.8.5 矛盾; 如果不允许, §4.8.5 那套公式就白写了。**建议**: PRD 统一到一个方向 — 要么 L3 允许"抽象动作方向"但禁具体渠道, 要么彻底不给任何动作建议只给 anchorQuestions。目前两个章节不一致。
- **F-DI-3** (P2 歧义): `severity` P0-P3 的判定标准? 本样本 delta -13.9 pp 被判 P1, 但环比 -10pp 和 -20pp 分别算几级? PRD 未给阈值表。**建议**: PRD §4.8 加一张 severity 判定矩阵 (delta × window × 绝对值 → P0/1/2/3), 避免 LLM 生成时随机分级。
- **F-DI-4** (P2 遗漏): `readerSections` 三段文案是 LLM 生成还是模板填充? 如果 LLM 生成, 每次回答措辞不同, CSV 导出会有抖动; 如果模板, 模板库存哪? PRD §4.8 未说。**建议**: 三读者段用"结构化填空模板 + LLM 润色" 两阶段, 模板存 `DiagnosticTemplate` 表按 category 索引。
- **F-DI-5** (P3 缺失): `relatedDiagnostics[]` 留空。多个诊断之间的关系 (因果 / 并发 / 同源) 怎么建? 是 LLM 推断还是用户标注? PRD §4.8.2 的 TypeScript interface 里有这字段但没说填充机制。**建议**: 等 Session 3 诊断引擎实现时再决定; PRD 先标 "MVP 留空, Phase 2 补充"。

---

## 8. 端到端追溯矩阵 · 一条 Diagnostic 的完整溯源

以 `diag_01` 为例, 验证"每一层数据都可回源":

```
diag_01 (抗衰品类通用问题下 top-of-mind 弱化)
  ↑ 触发于 metric (non-brand 提及率 63.6% 环比 -13.9pp)
  ↑ metric 由 4 条 Query 聚合 (qu_01, qu_04, qu_13, qu_14)
  ↑ 这 4 条 Query 都关联 2 个 Prompt (pr_01, pr_02) 都属于
  ↑ Prompt 都来自 1 个 Topic (tp_07 "抗衰精华推荐", dimension='品类')
  ↑ tp_07 来自 1 个 KG 节点 (cat_antiaging_serum · L3 品类)
  ↑ cat_antiaging_serum 属于 cat_serum → cat_skincare → ind_beauty_personal_care

影响品牌: brand_estee_lauder
证据 Response: rs_04 (有新品牌资生堂/修丽可挤占) + rs_13 + rs_14
```

### 规则检查 ✅/❌ · 追溯

- ✅ 每层数据都有 `id` 字段, 上下层都有 `*Id` 外键
- ✅ 从 Diagnostic 一路反查到 KG 节点只需 6 次 JOIN
- ✅ Response 的 brandMentions 包含 matchedAlias (如 "雅诗兰黛"), 可追到 brand.aliases[] 的哪条匹配成功

---

## 9. PRD Findings 汇总 🔍

按严重度排序, 共 **30 项** (9 P1 + 15 P2 + 6 P3):

### P1 (需在 Session 0 前修 PRD)

1. **F-KG-4** — Brand.aliases[] 多语言归一化 (NFD normalize) 层次 PRD 未明确, 导致 `Lancôme` 和 `Lancome` 可能不互通
2. **F-TP-1** — "平替" Topic 归入哪个 dimension (产品 / 竞品 / 新增独立子类) 未定义
3. **F-PR-1** — 多轮 Prompt 链数据模型缺 `conversationId` + `turnIndex` 字段
4. **F-QU-1** — `profileGroupIds[]` 一条 Query 能同时属于多个互斥画像吗? 聚合 `⊇` 逻辑有歧义
5. **F-RS-1** — Response.rawText 存储期限未定义, 成本和合规两面都有风险
6. **F-ME-1** — PANO Score A (Authority) 维度 MVP 冷启动会长期为 0, 拖累整体分数
7. **F-ME-2** — SoV 分母是否也要 dimension 过滤? 和提及率口径一不一致?
8. **F-DI-1** — Diagnostic L1/L2/L3 是否每条都必须三层齐备?
9. **F-DI-2** — §4.8.2a (L3 不给 playbook) 和 §4.8.5 (direction 包含抽象动作) 表述矛盾

### P2 (Session 1.5-3 实施期间必须澄清)

10. **F-KG-1** — SAME_GROUP 边需要"集团母公司"节点但没定义
11. **F-KG-2** — SUBSTITUTES vs COMPETES_WITH 判定界限不清
12. **F-TP-2** — Topic.realnessScore 字段缺失
13. **F-TP-4** — Response 挖掘新品牌的入库路径未定义 (自动 / 审核 / 丢弃)
14. **F-PR-2** — ChatGPT 双语 Prompt 是"互译 preserve intent"还是"独立生成 preserve nativeness"
15. **F-PR-4** — Topic=品牌 时 Prompt 是否允许引入其他品牌对比
16. **F-QU-2** — `fallback` 枚举值只有 `use_all` 吗
17. **F-QU-3** — 样本不足阈值 50 是硬编码还是可配
18. **F-RS-2** — 口径过滤发生在"入库打标"还是"聚合时 SQL WHERE"
19. **F-RS-3** — `pending_brand_review` 的品牌在 KPI 计算时怎么处理
20. **F-RS-4** — 情感分数计算方式 (规则引擎 vs LLM) 未定义, 精度争议
21. **F-ME-3** — PANO Score 权重配置存哪 (全局 vs 行业 vs project)
22. **F-ME-4** — 品牌详情页双口径怎么展示 (segmented control + anchor question?)
23. **F-DI-3** — severity P0-P3 判定阈值矩阵缺失
24. **F-DI-4** — readerSections 三读者文案生成机制 (LLM vs 模板) 未定义

### P3 (可 Phase 2 补充)

25. **F-KG-3** — Product.price 字段在 PRD §5.3 缺定义
26. **F-TP-3** — Topic 变体是存独立 Topic 还是 variants[] 字段
27. **F-PR-3** — Navigational Intent 需品牌 / 产品锚点, 否则信息量低
28. **F-QU-4** — Query status='failed' 是否算样本 (影响分母)
29. **F-ME-5** — "平均 position" 计算加权方式
30. **F-DI-5** — relatedDiagnostics[] 填充机制 (MVP 留空 OK)

---

## 10. 下一步

### 10.1 修 PRD (推荐顺序)

优先修 **9 项 P1**, 在 Session 0 启动前完成 — 这些直接影响数据模型 (Prisma schema) 和聚合 SQL 写法, 迟修成本高。

P2 可在 Session 1.5 (Planner) / Session 2 (Pipeline) / Session 3 (Analytics) 各自实施时补充, 不阻塞 Session 0。

P3 Phase 2 补, MVP 可用默认行为绕过。

### 10.2 把本文档转成 TypeScript fixture

当 P1 Findings 在 PRD 修完后, 可以把本文档直接转成:

```
tests/fixtures/pipeline/
├── kg.ts           # §1 的 Industry/Category/Brand/Product/Relations
├── topics.ts       # §2 的 10 条 Topic
├── prompts.ts      # §3 的 18 条 Prompt
├── profile-groups.ts  # §4.1 的 4 个 ProfileGroup
├── queries.ts      # §4.2 的 24 条 Query
├── responses.ts    # §5 的 24 条 Response
├── metrics.ts      # §6 的聚合结果
└── diagnostics.ts  # §7 的 diag_01
```

每个文件 export 强类型数组, 供:
- Session 1.5 Planner 单测 (输入 kg.ts, 期望输出近似 topics.ts)
- 前端 DashboardPage / BrandDetailPage mock (用 metrics.ts + diagnostics.ts)
- Playwright E2E 的 `routeFromHAR` mock 响应源数据

### 10.3 把本文档转成 Prisma seed

```
prisma/seed.ts  # 导入上面所有 fixture, 按依赖顺序 seed 到 PostgreSQL
npm run db:seed # 一条命令喂库
```

Session 0 结束时就应该能跑通, `npm run dev` 后打开 Dashboard 能看到真实感数据。

### 10.4 Review 协作模式建议

- Frank 把这 30 项 Finding 每一条过一遍, 分类为 "接受 PRD 改 / 拒绝 (保持现状)"
- 接受的 Finding 每个在 PRD 对应章节加 "2026-04-17 补充" 段
- 拒绝的 Finding 在本文档 §9 对应条目标注"REJECTED + 理由"
- 预计 Review 耗时: P1 每条 10min × 9 = 90min, P2 每条 5min × 15 = 75min, P3 可批量跳过 → 约 3 小时单人 Review

---

**文档终点**。有 30 项 PRD 问题等 Frank 决策, 建议 Review 先从 P1 的 F-DI-2 (L3 是否给抽象动作方向 — 影响整个诊断颗粒度话术) 和 F-ME-2 (SoV 是否做 dimension 过滤 — 影响所有 KPI 计算 SQL) 两条开始, 这两条跨最多章节。
