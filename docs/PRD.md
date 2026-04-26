# GENPANO - Product Requirements Document (PRD)

> Version: 1.3 | Author: Frank Wang | Date: 2026-04-15
> Status: Draft → Ready for Claude Code Implementation
> **Change Log (v1.3)**: Stripe-only design system (removed Linear dark theme), Recharts integration (5 chart components), updated frontend tech stack documentation
> **Change Log (v1.2)**: Based on CEO Product Review 2026-04-14 — 3 engines MVP (ChatGPT/豆包/DeepSeek), 4 industries, free-only MVP, share features, diagnostic enhancements

---

## 1. Executive Summary

GENPANO 是一个 Agent-native 的免费 Generative Engine Optimization (GEO) 监测平台。它帮助 SEO 从业者和品牌市场团队追踪其品牌、产品在主流 AI 引擎回答中的可见度、排名和情感表现。

**核心架构特征: 平台主动数据采集**。区别于 Semrush (小样本 opt-in 数据) 和 Profound (用户手动填入 topic 后才采集)，GENPANO 在用户注册前即已完成行业全量数据的采集和分析。用户注册后立即看到所在行业的品牌/产品 GEO 数据，无需等待爬取周期——这是 "data-first, user-second" 的产品策略。

系统通过公开数据源 + LLM 自动发现行业→品牌→产品图谱，平台级每日全量采集，用户按需补充自定义品牌/产品。

GENPANO 从架构层面为 AI Agent 设计，提供 MCP Server 和结构化 API，使任何 AI Agent 都能像人类用户一样便捷地获取和消费 GEO 数据。

**MVP 引擎**: ChatGPT、豆包、DeepSeek 三个引擎。Gemini 推迟至 Phase 2。

## 2. Goals & Non-Goals

### Goals (MVP)
- **平台主动采集行业全量数据** — 覆盖联蔚集团核心客户行业，在用户注册前即完成行业/品牌/产品数据的采集
- 用户注册即可立即查看所在行业的 GEO 监测数据，无需等待首次爬取
- 用户可以在平台数据基础上补充自定义品牌/产品
- 系统自动生成监测 Topic 并通过 Topic→Prompt→Query 四层 Pipeline 每日全量采集 AI 引擎
- 用户可以在 Dashboard 上查看提及率、排名、情感等核心指标
- 外部 AI Agent 可以通过 MCP/API 获取监测数据和报告
- MVP 支持 ChatGPT、豆包、DeepSeek 三个引擎
- **GEO 优化诊断建议**: 基于监测数据生成诊断性洞察 (问题是什么、为什么出现、严重程度)，作为咨询服务入口钩子

### Non-Goals (MVP)
- **不做 GEO 优化动作的产品化** — 诊断告诉用户"你的品牌在XX场景下被负面描述"，但不自动执行优化、不提供具体执行方案 (这是咨询服务的价值)
- 不做付费功能 (MVP 阶段全免费，自定义数据采集为 Phase 2 付费功能)
- 不做 Gemini 引擎 (Phase 2) 和 Google AI Overview / Bing Copilot 等搜索 AI (Phase 2)
- 不做团队协作 (Phase 2)
- 不做白标/代理商功能
- 不做全行业覆盖 (MVP 只覆盖 4 个核心行业，Phase 2 扩展)

## 3. User Personas

### Persona 1: SEO 从业者 - 小李
- **背景**: SEO agency 的 GEO 专员，负责 5-10 个客户的 AI 可见度管理
- **痛点**: 现有工具太贵 (Semrush $99/月/域名)，数据样本小不够准
- **需求**: 免费监测多个品牌在 AI 回答中的表现，导出报告给客户
- **使用场景**: 每周查看 Dashboard，月度导出报告，偶尔通过 API 拉数据到自己的报告系统

### Persona 2: 品牌市场经理 - 张总
- **背景**: 消费品品牌市场部负责人，关注品牌在新渠道的声量
- **痛点**: 不知道品牌在 AI 回答中被如何描述，不了解竞品对比
- **需求**: 直观看到品牌在 AI 引擎中的健康度，了解竞品差距
- **使用场景**: 每月看一次报告，关注异常变化告警

### Persona 3: AI Agent 开发者 - DevWang
- **背景**: 正在构建营销自动化 Agent，需要 GEO 数据作为输入
- **痛点**: 没有方便的 GEO 数据 API 可用，手动爬取不可靠
- **需求**: 通过 MCP 或 API 获取结构化的 GEO 数据，喂给自己的 Agent
- **使用场景**: Agent 自动调用 GENPANO MCP 获取数据，生成优化策略

## 4. Detailed Requirements

### 4.0 平台数据基础设施 (Platform Data Infrastructure)

> 核心理念: Data-First, User-Second — 平台在用户注册前即已完成行业全量数据采集，用户看到的不是空壳，而是已经运转的数据。

#### 4.0.1 数据架构: 平台层 + 用户视角层

```
┌──────────────────────────────────────────────────────────┐
│  Platform Layer (唯一数据源，所有用户共享)                   │
│                                                          │
│  Knowledge Graph (知识图谱)    Monitoring Pipeline        │
│  ├── Industry → Category 树   ├── Topic (Planner 从图谱生成)│
│  ├── Brand 节点 + 关系边      ├── Prompt (Topic × Intent)  │
│  ├── Product 节点 + 关系边    ├── Query (Prompt × Profile) │
│  └── 关系: 竞品/平替/搭配/升级 └── Response (每日采集)      │
│                                                          │
│  数据来源:                    MetricSnapshot (平台级)       │
│  ├── LLM 初始化              ├── 每日更新的 PANO Score      │
│  ├── Response 挖掘迭代        ├── 趋势数据                  │
│  └── 用户品牌提交 (触发扩充)  └── 诊断数据                  │
├──────────────────────────────────────────────────────────┤
│  User View Layer (视角过滤器，不存储监测数据)               │
│                                                          │
│  Project (每用户可多个)                                    │
│  ├── primaryBrandId: "我的品牌" (指向图谱 Brand 节点)      │
│  ├── competitorBrandIds: 竞品列表 (私有配置)              │
│  ├── preferences: 报告/告警偏好                           │
│  └── Dashboard 展示 = 平台数据 × Project 过滤             │
│                                                          │
│  Brand Submission (品牌提交)                               │
│  ├── 用户输入未知品牌 → 自动验证 → 纳入知识图谱            │
│  └── 品牌一旦入库，所有同行业用户可见 (共建效应)           │
└──────────────────────────────────────────────────────────┘
```

**核心原则**:
- 所有监测数据由平台统一生产，存储在 Platform Layer
- User Layer 不存储监测数据——Project 只是一组 ID 引用 + 偏好配置
- 用户的唯一贡献是"品牌发现"：提交平台未覆盖的品牌，触发图谱扩充
- 品牌通过验证后即成为平台公共资产，后续由平台 Pipeline 统一采集

#### 4.0.1a 行业知识图谱 (Industry Knowledge Graph)

> 知识图谱是 GENPANO 数据基础设施的核心——它定义了"监测什么"和"怎么理解关系"。Pipeline 从图谱生成 Topic，诊断从图谱理解竞争格局，Project 从图谱获取竞品推荐。

**节点类型**:

```
┌─────────────────────────────────────────────────────────────────┐
│  Knowledge Graph Node Types                                      │
│  ════════════════════════════════════════════════════════════    │
│                                                                  │
│  Industry (行业)                                                 │
│    属性: name, nameEn, aliases[], description                    │
│    示例: 美妆个护, 奢侈品, 食品饮料, 服装时尚                     │
│                                                                  │
│  Category (品类)                                                 │
│    属性: name, nameEn, level (1/2/3), parentCategoryId           │
│    示例: 护肤 > 精华 > 抗衰精华                                   │
│    说明: 品类树支持多级嵌套，MVP 支持 3 级                        │
│                                                                  │
│  Brand (品牌)                                                    │
│    属性: primaryName, nameZh, nameEn, aliases[] (见下),          │
│           positioning, priceRange, parentCompany, origin,        │
│           status (active/inactive)                               │
│    示例: 雅诗兰黛 / Estée Lauder / EL (国际高端, 雅诗兰黛集团)    │
│                                                                  │
│  Product (产品)                                                  │
│    属性: primaryName, nameZh, nameEn, aliases[] (见下),          │
│           price, keyFeatures[], launchDate, status               │
│    示例: 小棕瓶 / Advanced Night Repair / ANR (精华, ¥590)       │
└─────────────────────────────────────────────────────────────────┘
```

**边类型 (Relationship Types)**:

```
行业-品类关系:
  Industry ──HAS_CATEGORY──→ Category        // 美妆个护 → 护肤
  Category ──HAS_SUBCATEGORY──→ Category     // 护肤 → 精华 → 抗衰精华

品牌-行业关系:
  Brand ──BELONGS_TO──→ Industry             // 雅诗兰黛 → 美妆个护

品牌-品牌关系:
  Brand ←──COMPETES_WITH──→ Brand            // 雅诗兰黛 ↔ 兰蔻 (双向)
  Brand ←──SAME_GROUP──→ Brand               // 雅诗兰黛 ↔ 海蓝之谜 (同集团)

品牌-产品关系:
  Brand ──OWNS──→ Product                    // 雅诗兰黛 → 小棕瓶

产品-品类关系:
  Product ──IN_CATEGORY──→ Category          // 小棕瓶 → 精华

产品-产品关系:
  Product ←──COMPETES_WITH──→ Product        // 直接竞品: 小棕瓶 ↔ 小黑瓶
  Product ←──SUBSTITUTES──→ Product          // 替代关系: 精华 ↔ 精华面霜 (跨品类可替代)
  Product ←──PAIRS_WITH──→ Product           // 搭配推荐: 精华 + 眼霜 (经常被AI一起推荐)
  Product ──UPGRADES_TO──→ Product           // 升级关系: 小棕瓶 → 海蓝之谜精华 (高端升级)
  Product ──BUDGET_ALT_OF──→ Product         // 平替关系: 国货精华 → 小棕瓶 (低价替代)
```

**图谱在各模块中的作用**:

| 消费模块 | 如何使用图谱 |
|---------|------------|
| Planner (Topic 生成) | 从品类树 + 品牌/产品关系生成多层次 Topic ("精华推荐"来自品类，"小棕瓶 vs 小黑瓶"来自竞品边) |
| 竞品推荐 | 用户输入品牌 → 沿 COMPETES_WITH 边推荐品牌竞品 → 沿产品竞品边推荐产品竞品 |
| 诊断引擎 | "竞品超越告警"基于 COMPETES_WITH 边的品牌/产品对，"产品被遗漏"基于 IN_CATEGORY 找同品类产品 |
| 报告 | 竞品对比 Section 基于图谱竞品关系，行业格局基于 BELONGS_TO 行业的所有品牌 |
| 分析引擎 | Share of Voice 基于同品类/同行业的品牌聚合，产品竞争力基于同品类产品比较 |

**图谱构建: LLM 初始化 + Response 挖掘**:

```
Phase 1: LLM 初始化 (冷启动)
  │
  ├── Step 1: 品类树生成
  │   Prompt: "列出{行业}的完整品类树，3级深度"
  │   输出: Industry → Category → SubCategory 结构
  │
  ├── Step 2: 品牌发现 + 关系推断
  │   Prompt: "列出{行业}{品类}的 Top 30 品牌，标注竞争关系和集团归属"
  │   输出: Brand 节点 + COMPETES_WITH / SAME_GROUP 边
  │   交叉验证: 公开数据源 (电商、行业报告) 确认品牌真实性
  │
  ├── Step 3: 产品发现 + 关系推断
  │   Prompt: "列出{品牌}的核心产品，标注品类、竞品关系、平替/升级关系"
  │   输出: Product 节点 + IN_CATEGORY / COMPETES_WITH / UPGRADES_TO 等边
  │
  └── Step 4: 质量控制
      ├── 去重 (别名合并)
      ├── 关系对称性校验 (A竞品B → B竞品A)
      └── 人工抽检 (MVP 首批数据)

Phase 2: Response 挖掘 (持续迭代)
  │
  ├── 每次 Response 解析时，提取产品关系信号:
  │   ├── AI 回答中 "A 的平替是 B" → BUDGET_ALT_OF 边
  │   ├── AI 回答中 "A 搭配 B 使用" → PAIRS_WITH 边
  │   ├── AI 回答中 "A 和 B 哪个好" → COMPETES_WITH 边 (如不存在)
  │   ├── AI 回答中 "升级可选 B" → UPGRADES_TO 边
  │   └── AI 回答中出现新品牌/产品 → 候选节点 (待验证)
  │
  ├── 关系置信度:
  │   ├── LLM 初始化的关系: confidence = 0.6
  │   ├── 被 1 条 Response 佐证: confidence += 0.1
  │   ├── 被 5+ 条 Response 佐证: confidence = 0.9+
  │   └── confidence < 0.3 的关系定期清理
  │
  └── 新节点发现:
      ├── Response 中频繁出现的未知品牌/产品 → 自动创建候选节点
      ├── 候选节点被 3+ 条 Response 提及 → 自动验证 + 入库
      └── 等效于 "AI 引擎帮我们做品牌发现"
```

**图谱存储方案 (MVP)**:

MVP 阶段使用 PostgreSQL 关系表 + JSON 字段实现图谱存储 (无需引入 Neo4j 等图数据库):

```
表: kg_categories      — 品类树 (id, name_zh, name_en, parent_id, level, industry_id)
表: kg_brands          — 品牌节点 (id, primary_name, name_zh, name_en, aliases JSONB,
                                   metadata, industry_id)
表: kg_products        — 产品节点 (id, primary_name, name_zh, name_en, aliases JSONB,
                                   metadata, brand_id, category_id)
表: kg_brand_relations — 品牌关系边 (brand_a_id, brand_b_id, type, confidence, source)
表: kg_product_relations — 产品关系边 (product_a_id, product_b_id, type, confidence, source)
```

`aliases` 为 JSONB 数组，元素结构详见 4.10.2 节 (每个 alias 记录 value / language / type)。Phase 2 可根据图谱复杂度考虑迁移至图数据库。

**多语言名称与匹配**: 品牌/产品名称的多语言设计、别名池来源、提及识别匹配规则、消歧策略详见 [4.10.2 品牌/产品名称多语言模型](#4102-品牌产品名称多语言模型)。LLM 初始化阶段 (Phase 1 Step 2/3) 的 Prompt 必须要求输出中英文名 + 常见缩写/变体。

#### 4.0.2 行业覆盖策略

**MVP 行业范围**: 从联蔚集团核心客户行业中选择 4 个核心行业

```
MVP 首批行业 (4 个核心行业，基于联蔚集团客户覆盖):
├── 美妆个护 (Beauty & Personal Care)
├── 奢侈品 (Luxury)
├── 食品饮料 (Food & Beverage)
└── 服装时尚 (Fashion & Apparel)

Phase 2 扩展 (4 个行业):
├── 汽车 (Automotive)
├── 母婴 (Maternity & Baby)
├── 消费电子 (Consumer Electronics)
└── 家居日用 (Home & Living)

Phase 3 进一步扩展:
├── 医疗健康 / 金融保险 / 教育培训
├── 旅游酒店 / 宠物 / 运动户外
└── 按需求和数据反馈动态扩展
```

**知识图谱构建 Pipeline** (详细图谱设计见 4.0.1a):

```
Step 1: 行业种子 + 品类树 (人工定义 + LLM)
  ├── 每个行业的中文名/英文名/别名
  ├── 品类树生成: LLM 生成 3 级品类树 → 人工审核调整
  │   示例: 美妆个护 → 护肤 → 精华/面霜/防晒 → 抗衰精华/保湿精华
  └── 3-5 个种子品牌 (作为 LLM 发现的锚点)

Step 2: 品牌发现 + 关系建立 (公开数据源 + LLM)
  ├── 数据源:
  │   ├── 行业报告/排行榜 (公开可获取)
  │   ├── 电商平台品类 Top 品牌 (天猫/京东/Amazon 品类页)
  │   ├── LLM 知识 (Claude/GPT 对行业品牌的知识)
  │   └── 搜索引擎 "{行业} top brands / 品牌排行"
  ├── 发现流程:
  │   ├── 1. LLM Prompt: "列出{行业}{品类}的 Top 30 品牌，含中英文名，标注竞争关系和集团归属"
  │   ├── 2. 公开数据交叉验证 (至少两个数据源确认)
  │   ├── 3. 品牌元数据补全 (定位/价格区间/母公司/品类标签)
  │   ├── 4. 创建品牌关系边: COMPETES_WITH / SAME_GROUP
  │   └── 5. 人工审核 (MVP 阶段，首批数据需人工抽检)
  └── 输出: 每行业 20-50 个品牌 + 品牌间竞争关系图

Step 3: 产品发现 + 关系建立 (公开数据源 + LLM)
  ├── 数据源:
  │   ├── 品牌官网产品线 (公开)
  │   ├── 电商平台品牌旗舰店热销产品
  │   ├── LLM 知识 (品牌代表产品/明星产品)
  │   └── 搜索引擎 "{品牌} 热门产品 / 明星产品"
  ├── 发现流程:
  │   ├── 1. LLM Prompt: "列出{品牌}最知名的 10 个产品，含别名、品类、竞品/平替/升级关系"
  │   ├── 2. 公开数据交叉验证
  │   ├── 3. 产品元数据补全 (品类/价格段/核心卖点/别名)
  │   ├── 4. 关联品类: Product → IN_CATEGORY → Category
  │   ├── 5. 创建产品关系边: COMPETES_WITH / SUBSTITUTES / UPGRADES_TO / BUDGET_ALT_OF
  │   └── 6. 人工抽检
  └── 输出: 每品牌 5-15 个核心产品 + 产品间关系网络

Step 4: 图谱持续迭代 (自动)
  ├── Response 挖掘: 从每日 AI 回答中提取新关系 (详见 4.0.1a Phase 2)
  ├── 用户品牌提交: 验证通过后自动纳入图谱 (详见 4.1.2 品牌提交流程)
  ├── 新品牌/新产品发现: Response 中频繁出现的未知实体自动候选
  ├── 已退市/改名产品标记
  └── 关系置信度维护: 低置信度关系定期清理
```

#### 4.0.3 平台级数据采集调度

**每日全量采集 Pipeline**:

```
每日 02:00 (低峰时段) 启动
  │
  ├── 1. Topic → Prompt → Query 池刷新
  │   ├── 对新增品牌/产品: Planner 生成 Topic (Bottom-Up)
  │   ├── 对新 Topic: 生成 Prompt (× Intent 矩阵)
  │   ├── 对已有 Topic/Prompt: 检查时效性 (淘汰过时项)
  │   └── 趋势 Topic 补充 (基于热点信号)
  │
  ├── 2. Query 组装 & 爬取任务编排
  │   ├── 对每个 Prompt × Profile 采样 → 组装 Query
  │   ├── 计算今日总 Query 量 (≈ Prompt数 × 采样Profile数)
  │   ├── 按引擎分配到 Worker 队列
  │   └── 优先级排序: 高活跃行业 > 低活跃行业
  │
  ├── 3. 并行爬取执行 (Browser 执行 Query → Response)
  │   ├── 海外 Worker: ChatGPT
  │   ├── 中国 Worker: 豆包, DeepSeek
  │   ├── 限速: 账号池容量 × 每账号日限额
  │   └── 失败重试 + 降级
  │
  ├── 4. Response 入库 & 分析
  │   ├── 品牌/产品提及提取
  │   ├── 指标计算 (提及率/排名/情感)
  │   ├── PANO Score 更新
  │   └── 诊断引擎运行
  │
  └── 5. 新入库品牌补采 (如有)
      ├── 对用户提交且当日验证通过的新品牌
      ├── Planner 生成 Topic → Pipeline 首次采集
      └── 采集完成后通知提交用户
```

**成本控制策略**:

```
MVP 规模估算:
  4 行业 × 30 品牌/行业 × 10 产品/品牌 = 1,200 个实体
  每实体 ≈ 5 Topic × 2 Prompt/Topic × 3 Profile采样/Prompt = 30 Query/实体
  每日总量 ≈ 1,200 × 30 = 36,000 次 Query 执行
  ÷ 3 引擎 = 12,000 次/引擎
  ÷ 20 账号/引擎 = 600 次/账号/日 ← 远超单账号日限 (30-50次)

  优化方案:
  ├── 降低采样率: 每 Prompt 1-2 个 Profile (非关键 Topic)
  ├── 分层采集频率:
  │   ├── 高活跃品牌 (Top 20%): 每日采集
  │   ├── 中等品牌 (60%): 每3日轮转
  │   └── 长尾品牌 (20%): 每周采集
  ├── 优化后每日实际爬取量: ~8,000-12,000 次
  ├── 每引擎 ~2,000-3,000 次, 每账号 ~100-150 次 ← 需增加账号池
  └── 账号池目标: 每引擎 30-50 个账号 (MVP)

  增量成本:
  ├── 账号池扩大: 额外 ¥100-200/月 (鲁班SMS + 邮箱)
  ├── 代理流量增加: 额外 $10-20/月
  ├── VPS 可能需升级: 4核8G ($20-30/月)
  └── MVP 总成本调整: $60-110/月 (原 $43-72)
```

#### 4.0.4 用户体验变化

**旧模式 (用户驱动)**:
```
注册 → 创建项目 → 选行业 → 手动添加品牌/产品 → 等待首次爬取 (数小时) → 看到数据
```

**新模式 (平台驱动)**:
```
注册 → 选行业 → 输入/选择"我的品牌" → 确认竞品 → Dashboard 即刻可用
  ├── 品牌在图谱中 → 零等待，立即看到历史数据
  ├── 品牌不在图谱中 → 提交 → 自动验证入库 → 首次采集 (2-6h) → 通知就绪
  └── 竞品由知识图谱自动推荐，用户可调整
```

**数据架构**:
- **Platform Layer (唯一数据源)**: 知识图谱 + Pipeline 全量采集，所有用户共享
- **User View Layer (视角过滤器)**: Project 引用平台数据，不存储监测数据
- **共建机制**: 用户品牌提交通过验证后纳入平台图谱，丰富行业覆盖
- **Phase 2 付费扩展**: 用户请求平台未覆盖的行业、更高采集频率等

### 4.1 用户系统

#### 4.1.1 注册 & 登录 (延迟注册墙)

> **设计原则 (2026-04-17 重订)**: 注册不是入口, 是一种"解锁". 未登录用户进入产品第一屏立刻看到真实行业/品牌/产品数据 (§4.4 / §4.6.1b 已支持公开只读), 只在**价值已被用户感知后**、当用户主动触发高价值动作 (导出 CSV / 创建 Project / 加入监控 / 订阅告警 / 保存筛选偏好) 时才弹注册. 此设计呼应 [关键设计决策 #9 单路径 Onboarding](#关键设计决策) 与 [#10 数据驱动转化](#关键设计决策).
>
> **北极星 KPI — TTV (Time to Value)**: 用户首次打开 GENPANO (landing / 品牌直链 `/brands/:id` / 公开体检报告分享链接任一入口) → 首次完成**任意一个 "绑定动作"** (定义见 §4.1.1c 触发点矩阵: T1 加入监控 / T2 导出 CSV / T4 创建 Project / T5 订阅告警) 的间隔中位数 (P50). 目标: **P50 ≤ 5 分钟** (锚定 GROWTH_PLAN.md 行 320 "5 分钟建立第一个监测" 的业务承诺). GROWTH_PLAN.md 原本无 TTV 字段, 本节为其补全定义.
>
> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"延迟注册墙""注册不是入口"等表述仅用于指导实施, 严禁以 i18n key / JSX 文本节点 / PDF 文案形式呈现给最终用户. 参见 §4.6.0a.
>
> **登出 & 会话终结一侧**: 本节仅覆盖"用户如何进入". 用户离开 (登出 / 会话过期 / 注销账户) 一侧见 §4.1.1e.

**支持方式**:
- 邮箱注册 + OAuth (Google, GitHub)
- **OAuth 首次登录**: 因第三方已验证邮箱, 跳过 §4.1.1a E1 邮箱验证邮件, 直接触发 E2 欢迎邮件
- **找回密码**: 邮箱验证 → 重置密码链接 (24h 有效) → 设置新密码
  - 仅邮箱注册用户需要, OAuth 用户无密码
  - 重置链接使用一次性 token, 点击后立即失效
  - 连续请求频率限制: 同一邮箱 60 秒内仅可发送 1 次

**注册表单字段 (精简为 2 个必填)**:

| 字段 | 必填 | 说明 |
|------|------|------|
| 邮箱 | ✅ | 作为登录凭据 + 事务性邮件地址 |
| 密码 | ✅ | ≥ 8 位, 含字母+数字. OAuth 用户跳过 |
| `locale` | 自动推断 | 根据浏览器 `Accept-Language` 预填, 用户可在设置页切换. 详见 [4.10.4 UI 国际化](#4104-ui-国际化-中文--英文) |
| `defaultIndustryId` | ❌ | **不在注册表单收集**. 若用户从行业页 / 品牌直链进入注册, 自动从 URL `return_to` 继承; 否则在登录后首屏轻量引导 (可跳过, 详见 §4.1.1b) |

> **表单交互模型**: 上表是字段清单, 实际填写流程走 **§4.1.1-form Email-first 2-step** — 用户第一步只看到邮箱字段, 点"用邮箱继续" → 系统 lookup → 再决定显示"设密码" (新) 还是"输密码" (老). 这避免了"邮箱 + 密码同屏对新用户的摩擦". 完整状态机 / API 契约 / 防枚举约束见 §4.1.1-form.

> **变更说明**: 2026-04-17 之前版本把行业选择作为 Onboarding 必选步骤 (即便在注册后). 现改为: 未登录浏览时 URL 已体现用户关心的行业, 无需二次询问; 若用户是无 referrer 直接注册, 登录后展示"你想先看哪个行业?" 引导卡, **但可跳过直接进面板**. 这把"注册后看到数据"的步骤数从 2 (选行业 → 看数据) 降到 0-1 步.

**其他规则**:
- 用户可创建多个"监测项目" (Project), 也可不创建 Project 直接探索行业数据
- **用户偏好**:
  - `defaultIndustryId`: 首次触发 `T*` 绑定动作时若未设置, 以该动作所属行业回填; 用户可在设置页修改
  - `locale`: UI 语言偏好 (`zh-CN` / `en-US`), 注册时根据浏览器 `Accept-Language` 自动推断, 用户可在设置页切换
- 免费账户限制: 3 个项目, 每项目可关注 5 个竞品品牌

**验收 KPI (本节新增漏斗目标, MVP 第 1 季度口径)**:

| KPI | 目标 | 基线/引用 | 测量方式 |
|-----|------|-----------|----------|
| **TTV P50** (首次打开 → 首次绑定动作) | ≤ **5 分钟** | GROWTH_PLAN.md 行 320 "5 分钟建立第一个监测" | 事件埋点: `session_first_event_at` vs `first_binding_action_at` |
| **未登录浏览 → 注册 CVR** | ≥ **10%** | GROWTH_PLAN.md 行 20 "PDF 下载 → 注册 5-8%" 的 ~2x (产品内用户意图更强) | GA + 后端 `user.source=guest_converted` |
| **登录页 → 注册完成 CVR** (进入注册表单后) | ≥ **40%** | 漏斗瘦身后基准 (字段 5+ → 2) | `/auth?mode=register` PV → `user.created` |
| **注册后激活率** (注册 D1 内完成首次绑定动作) | ≥ **30%** | GROWTH_PLAN.md 行 839 "30%+ 新用户转化为活跃" | `user.created_at` vs `first_binding_action_at` ≤ 24h |

这 4 个漏斗指标均为 §4.1.1c 延迟注册墙落地后才可稳定测量, 实施时需同时埋好事件 (见 S4a 任务 7).

#### 4.1.1-form 注册/登录表单: Email-first 2-step (2026-04-19 新增, 锚点 = design/prototype-auth-v4.html + v5.html)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节的状态机 / 契约 / "Step N" 等术语仅用于指导实施; UI 文案只显示用户层面的动作标签 ("用邮箱继续" / "登录" / "创建账号"), 严禁出现 "Step 1 / Step 2 / Next Action / lookup" 等开发语. 参见 §4.6.0a.

**背景**:

- 2026-04-17 之前 AuthPage 是 "email + password 同屏一把交" 的单步表单, 不对邮箱做存在性分流. 问题:
  1. 新用户看到密码字段前, 没有任何"我要创建账号"的心智确认, 摩擦大
  2. 老用户无法区分"自己用哪个邮箱注册过" — 错邮箱 + 错密码两个错交错报错无法归因
  3. `/login` 和 `/register` 两条 URL 挂的是同一个 UI, 用户很难感知"我现在在做什么", 跟 Landing v2.1 (Stripe Light) 的现代感也对不上
- Stripe / Linear / Vercel / Claude.ai 等成熟产品都是 email-first 2-step: Step 0 只输邮箱 → 后端 lookup → Step 1 分流到"设密码 (新)" 或 "输密码 (老)". 原型 `design/prototype-auth-v4.html` (2026-04-17) + `v5.html` 已完整绘制该流程, 本节把原型固化为 spec.

**状态机 (authoritative)**:

```
                 ┌───────────────────┐
                 │  Step 0: email    │   用户只填邮箱 (+ 可选 OAuth fallback)
                 └─────────┬─────────┘
                           │ POST /api/auth/lookup   (≥ 400ms 固定响应)
                           │ { email } → { next: 'register' | 'login', locale_hint }
                           ▼
        ┌──────────────────────────────────────────────────────┐
        │  Step 1: branch                                      │
        │                                                      │
        │  next=register (新邮箱)       │  next=login (老邮箱) │
        │  ─ "为你的账号设置密码"       │  ─ "欢迎回来"        │
        │  ─ password strength meter    │  ─ "忘记密码?" 入口  │
        │  ─ [创建账号]                  │  ─ [登录]            │
        │  ─ 密码 ≥ 8 位                │                       │
        │                   ───→ Step 2: post-auth redirect   │
        └──────────────────────────────────────────────────────┘

另一支线 · 忘记密码 (仅从 Step 1 · login 点"忘记密码?" 进入):
                 ┌───────────────────┐
                 │  Step 1.forgot    │  带入 Step 0 的邮箱
                 └─────────┬─────────┘
                           │ POST /api/auth/forgot  (≥ 400ms)
                           ▼
                 ┌────────────────────────────┐
                 │  Step 1.forgot.sent        │
                 │  "重置邮件已发送" success  │
                 │  → "返回登录" 回 Step 0    │
                 └────────────────────────────┘
```

**URL 路由契约**:

- `/register` 和 `/login` 都继续挂 `<AuthPage>` (保留现有 Landing / WatchBrandButton / AuthPromptModal 的 CTA URL 不变), 但 Step 0 UI **不区分两条 URL** — 两者都显示 "用邮箱继续". 区别只在头部副标题:
  - `type="register"` → "直接输邮箱即可" / "Just enter your email"
  - `type="login"`    → "欢迎回来" / "Welcome back"
- Step 0 / Step 1 切换**不改变 URL** (不用 `/register/step-2` 这种深链). 仅前端 state. 目的: 避免用户刷新页面时处于"设密码态但没 email"的不可恢复态 — 刷新后自动回到 Step 0.
- 所有 CTA 落地 `/register` 或 `/login` 均可, AuthPage 内部 lookup 会自动分流. Landing 的 "免费开始监测" 指 `/register`, "已有账号? 登录" 指 `/login`, 两者只差 header 副标题.
- Post-auth redirect 保留 §4.1.1c T9 快路径 + `return_to` 白名单 (详见 §4.1.1c Return-To 契约).

**API 契约**:

**`POST /api/auth/lookup`** (MVP 可用 mock handler / MSW 实现, 后端落地在 S4a):

请求:

| 字段 | 类型 | 说明 |
|------|------|------|
| email | string | 必填, 合法邮箱格式 |

响应:

| 字段 | 类型 | 说明 |
|------|------|------|
| next | `'register'` \| `'login'` | 下一步视图 |
| locale_hint | `'zh-CN'` \| `'en-US'` \| `null` | 已注册用户的 locale 偏好, 用于预填 Step 1 UI 语言 (新邮箱场景为 null) |

**⚠️ 防枚举硬约束 (security-critical, 不可妥协)**:

1. **响应时间固定 ≥ 400ms**, 无论 DB 命中 / miss / 报错, 用 `Promise.all([dbQuery, sleep(400)])` 或 middleware fixed-delay. 目标 `p99 - p50 < 50ms` (时间侧信道防护).
2. **响应结构完全一致** — 新邮箱 / 老邮箱 / DB 报错三种情况, JSON 字段集相同 (都有 `next` + `locale_hint`). DB 报错时降级为 `next='register'`, locale_hint=null (以"错误 = 邮箱存在"的错觉比"错误 = 邮箱不存在"危害小).
3. **限流**: 同 IP 1min ≤ 20 次, 同邮箱 1min ≤ 10 次; 超限返回 HTTP 429 + 响应体 `{ next: 'register', locale_hint: null }` (仍然保持结构一致, 只在 header/status 上限流, 前端收到 429 仍展示 Step 1 · register UI 以避免泄漏).

**i18n key 清单 (PRD §4.10.4a 覆盖矩阵补充)**:

每个 key 必须在 `frontend/src/i18n/messages.zh-CN.json` 和 `messages.en-US.json` 都提供. CI grep 扫描缺项即阻断.

```text
auth.step0.title                    一步开始 / Start in one step
auth.step0.subtitle.login           欢迎回来 / Welcome back
auth.step0.subtitle.register        直接输邮箱即可 / Just enter your email
auth.step0.email_label              邮箱 / Email
auth.step0.email_placeholder        你的工作邮箱 / your@work-email.com
auth.step0.continue_btn             用邮箱继续 / Continue with email
auth.step0.continue_btn_loading     识别中… / Verifying…
auth.step0.oauth_divider            或 / or
auth.step0.oauth_google             使用 Google 账号继续 / Continue with Google
auth.step0.oauth_github             使用 GitHub 账号继续 / Continue with GitHub
auth.step0.error.email_invalid      请输入有效的邮箱地址 / Please enter a valid email
auth.step0.error.rate_limited       请求过于频繁, 请稍后再试 / Too many attempts, please retry later
auth.step0.legal                    继续即表示同意 {terms} 与 {privacy} / By continuing you agree to {terms} and {privacy}

auth.step1.new.chip                 新邮箱 · 正在为你创建账号 / New email · creating your account
auth.step1.new.title                为你的账号设置密码 / Set a password for your account
auth.step1.new.password_label       密码 / Password
auth.step1.new.password_hint        至少 8 位, 建议混合大小写与数字 / At least 8 chars, mix upper/lower and digits
auth.step1.new.strength.weak        弱 / Weak
auth.step1.new.strength.medium      中 / Medium
auth.step1.new.strength.strong      强 / Strong
auth.step1.new.create_btn           创建账号 / Create account
auth.step1.new.error.password_short 密码至少需要 8 个字符 / Password must be at least 8 characters

auth.step1.existing.chip            欢迎回来 / Welcome back
auth.step1.existing.title           输入密码登录 / Enter your password
auth.step1.existing.password_label  密码 / Password
auth.step1.existing.forgot          忘记密码? / Forgot password?
auth.step1.existing.login_btn       登录 / Sign in
auth.step1.back_to_email            用其他邮箱 / Use a different email

auth.step1.forgot.title             重置密码 / Reset your password
auth.step1.forgot.subtitle          输入注册邮箱, 我们会发送 24h 有效的重置链接 / Enter your email, we'll send a reset link valid for 24h
auth.step1.forgot.send_btn          发送重置链接 / Send reset link
auth.step1.forgot.sent_title        重置邮件已发送 / Reset email sent
auth.step1.forgot.sent_body         请查收 {email} 的收件箱, 24h 内点击链接完成重置 / Check {email} inbox, click the link within 24h
auth.step1.forgot.back_to_login     返回登录 / Back to sign-in
```

**Harness 拦截 (pre-commit + CI)**:

```bash
# (H1) AuthPage 禁止回退到 "email + password 同屏" 单表单
grep -nzoE "name=['\"]email['\"][^>]*>[\\s\\S]{0,400}name=['\"]password['\"]" \
  frontend/src/pages/AuthPage.jsx

# (H2) lookup / forgot handler 必须带固定 delay ≥ 400ms (后端落地 + 前端 mock 同规)
grep -rnE "auth[/.](lookup|forgot)" frontend/src backend/handlers 2>/dev/null \
  | xargs grep -L "400" | grep -v node_modules

# (H3) /login 与 /register Step 0 形态必须一致 — 走 Playwright toHaveScreenshot
#      (详见 docs/TEST_STRATEGY.md § 视觉回归 — auth-step0-login.png / auth-step0-register.png)

# (H4) i18n 覆盖矩阵 — auth.step0 / step1.new / step1.existing / step1.forgot 四命名空间 zh-CN + en-US 齐全
node scripts/check-i18n-coverage.mjs --namespace 'auth.step*' --locales zh-CN,en-US

# (H5) 防开发约束泄漏 (§4.6.0a 同规)
grep -rnE '(Step ?[012]|lookup|next_action|state machine)' frontend/src/i18n --include='*.json'
```

任一条有输出即视为违规, PR 必须修复方可合并.

**事件埋点 (PRD §4.11 补充, 事件 #57-#61)**:

| # | 事件名 | 触发点 | Props (禁 PII) |
|---|--------|--------|----------------|
| #57 | `auth_step0_email_submitted` | Step 0 点"用邮箱继续" | email_domain (仅 `@` 后部分), outcome=new\|existing\|error, elapsed_ms (实际等待时间) |
| #58 | `auth_step1_new_account_created` | Step 1 · 新邮箱, "创建账号"成功 | locale, oauth_available |
| #59 | `auth_step1_existing_logged_in` | Step 1 · 老邮箱, "登录"成功 | locale |
| #60 | `auth_step1_forgot_sent` | 忘记密码 → 点击"发送重置链接"成功 | — |
| #61 | `auth_oauth_fallback_clicked` | Step 0 用户不输邮箱直接走 Google / GitHub | provider=google\|github |

**PII 红线**: #57 的 `email_domain` 只取 `@` 后部分 (如 `gmail.com`), 禁止上报 local part 或完整邮箱. 参见 §4.11.5.

**锚点引用**:

- 结构视觉锚点: `design/prototype-auth-v4.html` · `design/prototype-auth-v5.html`
- 代码实现: `frontend/src/pages/AuthPage.jsx` (重写自 2026-04-17 版本)
- Session: `docs/CLAUDE_CODE_SESSIONS.md` Session 2a "AuthPage Email-first 2-step 迁移"
- DESIGN_TOKENS 依赖: 全部走 `var(--color-*)` / `t-input` / `t-btn-primary` / `t-card`, 禁止内联 hex (§设计锚点 · 样式契约)

---

#### 4.1.1-gate Auth-Required Data Viewing Policy (2026-04-20 新增 ⭐ SUPERSEDES §4.1.1c)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节是 Page Scope 和 Route Guard 层面的约束, 不得作为 i18n key / JSX 文本呈现给用户。详见 §4.6.0a。

**A. 政策反转**

原政策 ([关键设计决策 #9 Data-Before-Auth Onboarding](#关键设计决策) + [#10 数据驱动转化](#关键设计决策) + §4.1.1c 延迟注册墙) 承诺"未登录用户也能浏览真实行业/品牌/产品数据, 仅在高价值动作触发时弹注册". **2026-04-20 经 Frank 确认反转为: 任何数据页 + 任何数据 API 必须登录后访问, 未登录用户唯一能访问的是 Landing 营销页 + /auth + /register + /forgot**。

**B. 反转理由 (Business Rationale)**

1. 数据是 GENPANO 的核心资产, 用"免费注册"作为最低门槛比"完全匿名"更能沉淀用户
2. 降低爬虫/bot 盗用数据的风险 (Response 样本, Citation 数据, Topic 数据均为采集成本昂贵的原始资产)
3. MCP API 从 Day 1 走单一鉴权链路 (Bearer Token), 无需维护 "公开端点 vs 授权端点" 双套
4. 转化漏斗简化: Landing → /register → 数据, 不再出现"先逛 → 弹窗 → 转化"的多岔路径
5. MVP 期流量小, SEO 未起量, gate 全站的流量损失有限; Landing + Blog (Phase 2) 承担 SEO 入口角色

**C. 访问矩阵 (取代原 §4.1.1c 触发点矩阵)**

| 路径 | 未登录 | 已登录 + 零 Project | 已登录 + 有 Project |
|---|---|---|---|
| `/` (Landing 营销页) | ✅ 公开 | ✅ 可访问 (顶栏 CTA 变"进入工作台") | ✅ 可访问 |
| `/auth` / `/login` / `/register` / `/forgot` | ✅ 公开 | 已登录则 redirect → `/` (Dashboard) | 同左 |
| `/dashboard` | ⛔ **永久 301 → `/brand/overview`**（§4.6-IA-v2；DECISIONS §1；不再作为独立可达路由） | ⛔ 301 | ⛔ 301 |
| `/brand/overview` (Brand Mode · 总览, §4.6-IA-v2.C.2.2) | 🚫 redirect `/register?redirect=/brand/overview` | ✅ Empty State E1 (§4.1.1d) | ✅ 正常视图 |
| `/industries/:id` (Industry 视角, 见 §4.6.1e) | 🚫 redirect `/register?redirect=/industries/:id` | ✅ 可看 (无 "我" ▲ 标记) | ✅ 可看 (带 ▲ 主品牌锚点) |
| `/brands` (品牌列表) | 🚫 redirect `/register?redirect=/brands` | ✅ 可看 (仅能读行业内品牌, 无 "我的" 子列) | ✅ 可看 |
| `/brands/:id` (品牌详情, 见 §4.6.1b) | 🚫 redirect `/register?redirect=/brands/:id&brandHint=<slug>` | ✅ 可看 (未监控降级 banner) | ✅ 可看 (监控/未监控 banner) |
| `/brands/:id/products/:productId` (产品详情, 见 §4.6.1d) | 🚫 redirect + brandHint | ✅ 可看 | ✅ 可看 |
| `/brands/:id/metrics/:kpi` (KPI 全页下钻, 见 §4.6.1a-drilldown) | 🚫 redirect | ✅ 可看 | ✅ 可看 |
| `/topics` (Topic Pipeline 下钻) | 🚫 redirect | ✅ 可看 | ✅ 可看 |
| `/reports` | 🚫 redirect | ✅ 空态 | ✅ 可看 |
| `/settings/*` | 🚫 redirect | ✅ 可看 | ✅ 可看 |
| `/projects/new` | 🚫 redirect | ✅ 主入口 | ✅ 新建第二项目 |
| 所有 `api/*` 数据接口 (含 `/api/brands`, `/api/industries`, `/api/topics`, `/api/responses`, `/api/metrics`, `/api/citations`) | 🚫 401 | ✅ 返回 (按 Project 范围过滤) | ✅ 返回 |
| MCP 工具调用 (`genpano_get_*`, `genpano_list_*`, `genpano_simulate_*`) | 🚫 401 `MCP_AUTH_REQUIRED` | ✅ 返回 | ✅ 返回 |
| CSV 导出端点 | 🚫 401 | ✅ 返回 (按 Project 范围过滤) | ✅ 返回 |

**D. Route Guard 实现契约**

- 前端: `frontend/src/lib/auth/RequireAuth.tsx` 高阶组件, 包裹所有 gated 路由 (于 `App.jsx` 或 Router 层集中应用); 未登录态: `navigate('/register?redirect=' + encodeURIComponent(location.pathname + location.search), { replace: true })` + Mixpanel 事件 `#63 auth_gate_redirect { redirect_path, has_brand_hint }`
- 后端: `middleware.ts` 统一拦 Next.js App Router, 未带 session cookie 的 `/api/*` 返回 `401 AUTH_REQUIRED`; MCP 传输层检查 Bearer Token, 未带/无效返回 `401 MCP_AUTH_REQUIRED`
- Brand 直链 (SEO 场景): 未登录访问 `/brands/:id` 时, 检查 URL path 提取 brandId, lookup brand name (仅公开字段: nameZh / nameEn / logo, 不含数据), 传递到 `/register?redirect=/brands/:id&brandHint=<slug>` 页面, register 表单顶部显示 "注册后即可查看 {brand_name} 的 AI 引擎表现" 作为 brandHint-aware 首屏, 转化成功后走 `redirect` 跳回目标页. 埋点 `#64 brand_hint_register_success { brand_id, hint_source='brand_direct' }`
- SEO: Brand / Industry / Product 页面不再 server-render 真实数据; `<head>` 只渲染 brand name + industry + "登录 GENPANO 查看 AI 引擎里的品牌监测数据" meta description. Sitemap 仅暴露 Landing + Blog (Phase 2), 不再把 /brands/:id 列入 sitemap.

**E. §4.1.1d Empty State 简化影响**

- **E1 Brand Overview Empty** (`/brand/overview` + zero-project): 保留, 文案按 §4.6-IA-v2 Brand Mode 总览新定位调整 (Daily Digest / Action Center 相关 Spike 已废除, 见 DECISIONS §1; `/dashboard` 永久 301 → `/brand/overview`)
- **E2 Sidebar Empty** (`ProjectSelector.jsx` 零态): 保留
- **E3 Landing Nav Quick Create**: 简化为普通"登录 / 注册" 按钮 (Landing 顶栏, 三态合并为两态); 不再需要"已登录零态显示创建项目" 的特殊分支 (该状态进了 `/brand/overview` 就是 E1)
- **E4 Gated Banner** (`ProjectRequiredBanner.jsx`): **删除**. 所有 gated 页面已由 Route Guard 在未登录时 redirect, 登录后只剩 E1; "已登录零态落在 gated 页" 这个状态不存在了.

**F. Mixpanel 埋点调整**

- **下线** (若已实现则标记 deprecated): `#44 landing_quick_create_click` (E3 三态合并后无该行为), `#46 gated_banner_cta_click` (E4 删除)
- **保留**: `#45 entry_source` — 枚举值收缩到 `{ 'landing_cta', 'organic', 'referral', 'email', 'mcp_docs', 'blog' }`; 删除 `'brand_direct_anonymous'` 因为未登录访问 Brand 直链统一走 auth gate redirect, entry_source 在 register 成功后上报并可追加 `brandHint` 属性
- **新增** (详见 §4.11.4): `#63 auth_gate_redirect`, `#64 brand_hint_register_success`, `#65 mcp_auth_failure`

**G. Harness 拦截 (pre-commit + CI)**

```bash
# (1) 所有数据路由必须包在 <RequireAuth> 内 — 检查 App.jsx / Router 文件
#     任何 <Route path="/dashboard|/brands|/industries|/topics|/reports|/settings"> 外层必须是 RequireAuth
grep -nE '<Route\s+path="/(dashboard|brands|industries|topics|reports|settings|projects)' frontend/src --include='*.jsx' -r \
  | grep -v RequireAuth
# 任何输出 = 有路由未被 guard, 拒绝合并

# (2) 禁止未登录状态读取 data 类 API
#     fetch/axios 调用 /api/{brands,industries,topics,metrics,responses,citations} 必须在 useAuth 后
grep -rnE "fetch\(|axios\.(get|post)" frontend/src/lib/api --include='*.ts' --include='*.tsx' \
  | grep -E "/api/(brands|industries|topics|metrics|responses|citations)"
# 每条匹配必须在 api client 层 (统一注入 Authorization); 不应出现 component 级裸 fetch — 走现有 Harness

# (3) MCP handler 必须首行校验 token
grep -rL 'MCP_AUTH_REQUIRED\|requireMcpAuth' backend/src/mcp --include='*.ts'
# 任何输出 (文件) = MCP 工具处理函数未校验 token, 拒绝合并

# (4) /register 必须接住 redirect + brandHint 两个 query 参数
grep -nE "searchParams\.(get|has).*\b(redirect|brandHint)\b" frontend/src/pages/AuthPage.jsx
# 应至少匹配 2 行; 0 = brand direct 转化路径缺失
```

**H. 迁移清单 (Session S4 执行)**

1. 加 `RequireAuth` 高阶组件 + 路由应用
2. Next.js `middleware.ts` 拦 /api/* + MCP transport token check
3. AuthPage 解析 `redirect` + `brandHint` query, brandHint 存在时顶部渲染 brand-aware 首屏
4. 埋点新增 #63-#65 + 下线 #44/#46
5. 删除 `ProjectRequiredBanner.jsx` + E3 / E4 相关死代码
6. 更新 Landing 顶栏 CTA (登录/注册) + 移除 brand_direct_anonymous 相关 query
7. Sitemap 调整: 排除 /brands, /industries; 保留 /, /blog/*
8. SEO meta: Brand / Industry / Product 页 `<head>` 只渲染登录 CTA 的 meta description
9. 跨所有现有文档 cross-ref 更新: §4.1.1c 开头加 `> 2026-04-20 SUPERSEDED by §4.1.1-gate`, §4.6.1b 状态 C (公开只读) 开头同标注

#### 4.1.1a 事务性邮件系统

注册登录流程涉及的全部事务性邮件，统一使用 GENPANO 品牌模板 (Logo + 品牌色 + footer)。

**邮件清单**:

| # | 邮件类型 | 触发时机 | 主要内容 | 有效期/频率限制 |
|---|---------|---------|---------|---------------|
| E1 | 邮箱验证 | 邮箱注册提交后 | 验证链接，点击后激活账户 | 链接 24h 有效，60s 内限发 1 次 |
| E2 | 欢迎邮件 | 邮箱验证通过 / OAuth 首次登录 | 欢迎语 + 快速开始引导 (选行业→看数据) | 仅发 1 次 |
| E3 | 找回密码 | 用户点击"忘记密码"并提交邮箱 | 重置密码链接 (一次性 token) | 链接 24h 有效，使用后失效，60s 限发 1 次 |
| E4 | 密码重置成功 | 用户成功设置新密码后 | 确认通知 + 安全提示 (非本人操作请联系) | 即时发送 |
| E5 | 异常登录提醒 | 检测到新设备/新 IP 登录 | 登录时间、设备、IP 信息 + 非本人操作入口 | 即时发送，同设备 24h 内不重复 |

**邮件模板规范**:
- 发件人: GENPANO <noreply@genpano.com>
- 品牌头部: Logo + 产品名
- 正文区: 简洁文案 + 明确 CTA 按钮 (如"验证邮箱"、"重置密码")
- 底部: 联系方式 + 退订链接 (E2 适用) + "如非本人操作请忽略" (E1/E3 适用)
- 响应式: 适配桌面和移动端邮件客户端
- **多语言**: 每封邮件提供 zh-CN / en-US 两个模板文件 (共 10 个)，按 `User.locale` 选择发送版本；未注册场景 (E1 发送时用户尚未完成注册) 按注册表单填写的 locale 或浏览器 Accept-Language 判断。详见 [4.10.4](#4104-ui-国际化-中文--英文)

**技术实现**:
- 邮件服务: Resend (开发者友好, 免费 tier 100 封/天 MVP 足够) 或 AWS SES
- 模板引擎: React Email (与 Next.js 生态一致) 生成 HTML 邮件
- 发送方式: 后端 API 触发，异步发送 (不阻塞用户操作)
- Token 存储: 数据库存 hashed token + 过期时间，验证后立即删除
- 频率限制: Redis / 内存计数器，按邮箱地址 + 邮件类型限流

#### 4.1.1c 延迟注册墙: 触发点矩阵 & TTV 实现约束

> **⚠️ 2026-04-20 SUPERSEDED by §4.1.1-gate**: 本节"延迟注册墙 (先看数据再弹注册)"政策已被反转, 现行政策为所有数据页 + 数据 API 未登录即 redirect. 本节保留作为历史记录, 但 Harness / 路由 / i18n / 埋点均以 §4.1.1-gate 为准. 新代码请参照 §4.1.1-gate, 不再按本节实现.

> **本节目的**: 把分散在 §4.1 (行 400) / §4.4 / §4.6.1b / §4.6.4 的"未登录可见 / 关键动作前弹注册"论述**系统化**为唯一真相源. 所有新增"需要注册"的 UI 动作必须登记在本节表格, 不得在其他章节或代码中自行发明触发点.
>
> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节表格是实施规范, 任何单元格文字都不得以 i18n key 的 value 形式或 JSX 文本节点形式直接呈现给用户. 用户侧文案走 auth.hook.* 命名空间, 由 §4.10.4a 约束. 参见 §4.6.0a.

**A. 触发点矩阵 (Authoritative Trigger Registry)**

| ID | 页面/组件 | 用户动作 | 未登录响应 | 已登录响应 | i18n hook key | return_to query |
|----|----------|---------|-----------|-----------|---------------|-----------------|
| **T1** | 品牌详情 `/brands/:id` | 点击 "+ 加入竞品监控" | `<AuthPromptModal>`, 注册成功后自动走 §4.1.2a 状态机 | 按 §4.1.2a 正常执行 | `auth.hook.watch_brand` | `return_to=/brands/:id&action=watch` |
| **T2** | 任意表格/图表 | 点击 CSV 导出 (Download icon) | `<AuthPromptModal>` (已有约定, 见 §4.6.4 行 2456) | 直接下载 | `auth.hook.export_csv` | `return_to=currentUrl&action=export_csv&exportType=...` |
| **T3** | 品牌详情 | 点击 "🔗 分享体检报告 PDF" | **不拦截** (分享页公开只读); 公开页页脚固定 CTA 条 "注册持续监控 {brand} →" | 生成 PDF + 持久链接 | N/A (不弹 modal) | N/A |
| **T4** | 品牌详情 / Industry | 点击 "创建监测项目" | `<AuthPromptModal>`, 注册后跳 Project 创建页并预填主品牌 | 直接进 Project 创建 (§4.1.2) | `auth.hook.create_project` | `return_to=/projects/new&primaryBrandId=...` |
| **T5** | 品牌详情诊断 Tab | 点击 "订阅此品牌告警邮件" | `<AuthPromptModal>` + 注册时勾选 "已同意接收" | 创建告警订阅 | `auth.hook.subscribe_alerts` | `return_to=/brands/:id?tab=diag&action=subscribe` |
| **T6** | 面板/品牌详情 Toolbar | 点击 "保存当前筛选为默认" | `<AuthPromptModal>` | 写入 User.preferences | `auth.hook.save_preferences` | `return_to=currentUrl&action=save_filter&...` |
| **T7** | 行业探索视图 / 品牌详情 | 切换行业/画像/时间筛选 | **不拦截**; 用 `localStorage.genpanoGuest.*` 记录, 注册后同步到服务端 | 直接存 User.preferences | N/A | N/A |
| **T8** | 品牌详情 | 点击 "在 MCP 中查询此品牌" (Agent 入口) | `<AuthPromptModal>` (MCP 需 API Key) | 跳转 API Key 生成页 | `auth.hook.mcp_apikey` | `return_to=/settings/api-keys&action=create` |
| **T9** | Landing nav / Dashboard Empty / Sidebar Empty / Gated Banner (§4.1.1d E1-E4) | 点击 "+ 创建监测项目" / "+ 创建第一个项目" (专家快路径 / 零 Project 态引导) | `<AuthPromptModal>` hookKey=`auth.hook.quick_create_project`, 注册后跳 `/projects/new` (无 primaryBrandId 预填, 在 §4.1.2 快路径 Step 1 让用户选品牌) | 直接进 §4.1.2 Project 创建 (无预填) | `auth.hook.quick_create_project` | `return_to=/projects/new&source=landing_nav\|dashboard_empty\|sidebar_empty\|gated_banner` |

**列解读**:
- **未登录响应**: 仅 T1/T2/T4/T5/T6/T8/T9 弹 `<AuthPromptModal>`; T3/T7 保持开放以最大化数据曝光 → 深化用户意图.
- **return_to 策略**: 所有 query 参数必须经 allowlist 校验 (见 §4.6.4 行 2565, 仅允许 `genpano.com` 内部路径), 防开放重定向攻击. 登录成功后后端 redirect 到 return_to, 前端监听 `action` query 自动重放动作 (不再让用户手动点一次).
- **i18n hook key**: 每个触发点在 `messages/{locale}/auth.json` 下新增一条 `auth.hook.*` — 文案须描述"注册后能做什么" (用户价值), 不说"你必须注册" (强制口吻). 文案示例见下方 B 段.

**B. `<AuthPromptModal>` 组件规范**

- **依赖**: 必须使用 Radix UI Dialog (见 CLAUDE.md "依赖规则"), 禁止手写 modal
- **Props**: `{ hookKey: 'auth.hook.watch_brand' | ..., returnTo: string, action: string, onClose: () => void }`
- **结构**:
  ```
  ┌──────────────────────────────────────┐
  │  [close ×]                           │
  │                                      │
  │  {t(hookKey + '.title')}             │
  │  {t(hookKey + '.body')}              │
  │                                      │
  │  [主按钮: 免费注册 →]                │
  │  [次按钮: 已有账号, 登录]            │
  │                                      │
  │  {t('auth.prompt.why_register')}     │ ← 3 条价值点, 固定文案
  └──────────────────────────────────────┘
  ```
- **主 CTA**: "免费注册 →" (中) / "Sign up free →" (en), **不写 "立即注册" / "必须注册"** — 强调"免费"降低心理阻力
- **次 CTA**: "已有账号, 登录" / "Already have an account? Log in"
- **价值点 3 条 (固定, 所有触发点共用)**:
  1. `t('auth.prompt.why.daily_update')`: "每日自动追踪, 数据即时更新" / "Daily auto-tracking, real-time updates"
  2. `t('auth.prompt.why.free_mvp')`: "MVP 阶段全功能免费" / "All features free during MVP"
  3. `t('auth.prompt.why.agent_ready')`: "支持 MCP, Agent 可直接消费你的数据" / "MCP-ready, agents can consume your data directly"

**C. 公开/私域边界 (页面级)**

| 页面 / 路由 | 未登录访问 | 降级说明 |
|------------|-----------|---------|
| `/auth` (login/register/forgot) | ✅ 公开 | — |
| `/industries/:id` (行业探索视图) | ✅ 公开 | 筛选/切换行业 T7 走 localStorage, 不拦截 |
| `/brands/:id` (品牌详情) | ✅ 公开只读 | 竞品对比降级为 "vs 行业 Top 5" (§4.6.1b 状态 C); 页脚固定注册 CTA 条 |
| `/brands/:id/products/:productId` (产品详情) | ✅ 公开只读 | 同品牌详情 C 态 |
| `/reports/public/:shareToken` (体检报告分享页) | ✅ 公开 | 不需 token 以外的 auth; 页脚注册 CTA |
| `/dashboard` (Project 视角面板) | ❌ 强制登录 | 零 Project 时渲染 §4.1.1d E1 "零 Project Empty State" (主 CTA 建项目, 次 CTA 先探索行业), 而非空白页或自动重定向 |
| `/projects/*` (Project 管理) | ❌ 强制登录 | 同上 |
| `/settings/*` (用户设置) | ❌ 强制登录 | — |
| `/topics` / `/topics/:id/...` (Topic drilldown) | ❌ 强制登录 | Topic 属于 Project 配置的一部分, 无 Project 场景无意义 |

**D. TTV 事件埋点契约 (S4a 任务 2a 实施)**

TTV 的 4 类事件已纳入 §4.11.4 MVP 事件全量清单 (S1 / S11), 统一走 **Mixpanel**, 不自建 events 表. 具体:

| 事件 | §4.11 清单编号 | 上报方 |
|------|---------------|--------|
| `session_first_event` | #1 | 前端 (封装 `analytics.ts`) |
| `auth_prompt_shown` | #2 | 前端 `<AuthPromptModal>` mount 时 |
| `user_created` | #4 | **后端** 注册成功 API 触发 |
| `first_binding_action` | #41 | 前端, 完成 T1/T2/T4/T5 (`brand_watch_succeeded` / `export_csv_succeeded` / `alert_subscribed` / `project_created`) 任一时, session 级去重 |

TTV P50 通过 Mixpanel Funnels 自带的"time to convert"直接得出 (不写 SQL): 建一条 Funnel `session_first_event → first_binding_action`, conversion window 设 24h, 在右侧 panel 看 P50 即可. 漏斗建板细节见 §4.11.6 漏斗 1.

**为什么不用 Prisma events 表**: Frank 2026-04-17 决策——MVP 阶段单一后端走 Mixpanel, 减少 Solo 维护负担; Phase 2 如需数据主权回收或对接 MCP, 再通过 Mixpanel 的 `/export` API 夜间批拉到 Postgres.

**E. Harness 拦截 (pre-commit + CI)**

```bash
# (1) 禁止在代码里硬编码触发点白名单, 必须引用 §4.1.1c 表格
grep -rnE 'AuthPromptModal.*hookKey\s*=\s*["\x27][a-z_.]+' frontend/src \
  --include='*.jsx' --include='*.tsx' | \
  awk -F'hookKey' '{print $2}' | grep -vE 'auth\.hook\.(watch_brand|export_csv|create_project|subscribe_alerts|save_preferences|mcp_apikey|quick_create_project)'
# 任何输出 = 有新触发点未登记到 §4.1.1c, 拒绝合并

# (2) return_to 必须经 allowlist 校验
grep -rnE 'window\.location\s*=\s*.*returnTo' frontend/src --include='*.jsx'
# 任何输出 = 直接跳转未过 allowlist, 拒绝合并

# (3) §4.1.1c 表格里的 i18n key 必须都存在于 auth.json
for key in watch_brand export_csv create_project subscribe_alerts save_preferences mcp_apikey quick_create_project; do
  for locale in zh-CN en-US; do
    grep -q "\"$key\"" frontend/src/i18n/messages/$locale/auth.json || echo "MISSING: $locale/$key"
  done
done
```

任何一条有输出视为"触发点矩阵与代码 drift", PR 必须修复方可合并.

---

#### 4.1.1b Onboarding (新用户引导)

> **设计原则 (2026-04-17 重订)**: Data-First 升级为 Data-Before-Auth——用户**无需注册**即可看到真实数据. Onboarding 从"注册 → 选行业"的 2 步前置流程, 降为"直接看数据 → 触发绑定动作时注册"的 0-1 步流程. §4.1.1c 触发点矩阵是本节的实现依据.

**Onboarding 路径 (3 种入口, 全部零强制前置步骤)**:

```
路径 A: Landing 首屏 (无 referrer)
    访问 / → 首屏展示"今日 AI 热度 Top 4 行业"卡片 (同原行业选择卡片, §4.1.1b 下方"行业选择卡片")
        │
        ▼ 用户点击行业 → /industries/:id (公开)
        │
        ▼ 浏览数据, 点击品牌 → /brands/:id (公开)
        │
        ▼ 触发 T1/T2/T4 绑定动作 → <AuthPromptModal>
        │
        ▼ 注册完成 → 按 return_to 恢复动作 → 完成 TTV 里程碑

路径 B: 品牌直链 (从 SEO / 分享链接 / PDF 二维码进入)
    访问 /brands/:id → 直接进品牌详情 (公开只读, §4.6.1b 状态 C)
        │
        ▼ 浏览数据, 触发任意 T* 绑定动作 → <AuthPromptModal>
        │
        ▼ 注册完成, return_to 带回原品牌 → 完成 TTV

路径 C: 直接访问 /auth (SEO / 老用户)
    访问 /auth → 注册完成 (仅邮箱+密码, 无行业选择)
        │
        ▼ 登录后首屏: "你想先看哪个行业?" 引导卡 (可跳过)
        │      ├─ 选中 → 写 User.defaultIndustryId, 进 /industries/:id
        │      └─ 跳过 → 进 /dashboard, 按 §4.1.1d 渲染零 Project 态 Empty State (主 CTA "创建第一个项目", 次 CTA "先探索行业数据"), 而非空白页或自动重定向
        │
        ▼ 后续路径同 A/B
```

**路径选择说明**:
- **A/B 为主力路径 (预期占 ≥ 80% 新用户)**: 未登录先看数据, 让数据本身承担 "这个产品值不值得注册" 的说服. 对应 §4.1.1 验收 KPI "未登录浏览 → 注册 CVR ≥ 10%".
- **C 为兜底路径**: 保留 `/auth` 直达能力供老用户 / SEO 抓取 / 邮件 magic link 场景. 登录后的行业引导卡是 A/B 路径自然记录的 `defaultIndustryId` 的 fallback.

**行业选择卡片 (带数据钩子)**:

每张卡片展示该行业的实时数据摘要，让用户在选择前就看到平台的数据价值：

```
┌─────────────────────┐  ┌─────────────────────┐
│  美妆个护             │  │  食品饮料             │
│  监测 152 个品牌       │  │  监测 98 个品牌        │
│  今日 AI 热度 Top 3:  │  │  今日 AI 热度 Top 3:  │
│  1. 香奈儿  85.0      │  │  1. 茅台  91.2        │
│  2. 雅诗兰黛 72.3     │  │  2. 元气森林 78.5     │
│  3. 迪奥    71.2      │  │  3. 瑞幸    74.1      │
│                       │  │                       │
│  [进入查看 →]         │  │  [进入查看 →]         │
└─────────────────────┘  └─────────────────────┘
```

- **展示字段**: 行业名、监测品牌数量、PanoScore Top 3 品牌及分数
- **设计要点**: 卡片中的品牌名是用户熟悉的，降低认知门槛，激发好奇心
- **选完即走**: 点击卡片后零延迟进入行业探索视图，不再询问任何其他问题

**行业探索视图 (所有用户的默认主界面)**:

展示所选行业的全量公域数据，提供两种浏览模式。这不是"过渡态"或"探索模式"——对无 Project 的用户而言，这就是产品主界面：

**① Graph View (知识图谱视图)**:

基于 D3 力导向图，可视化展示行业知识图谱的节点和关系：

```
┌─────────────────────────────────────────────────────────────┐
│  美妆个护 · 知识图谱                    [Graph] [List]  🔍  │
│                                                             │
│         ┌──护肤──┐                                          │
│        /    |     \                                         │
│     精华   面霜   防晒        ← Category 节点 (品类树)       │
│      |      |      |                                        │
│   ┌─雅诗兰黛─┐  ┌─兰蔻─┐     ← Brand 节点                  │
│   |  ╲       |  |      |                                    │
│   |   COMPETES_WITH ── ┘     ← 关系边 (虚线/实线区分类型)    │
│   |          |                                              │
│  小棕瓶   小黑瓶              ← Product 节点                 │
│   └──COMPETES_WITH──┘                                       │
│                                                             │
│  ● Category  ● Brand  ● Product  --- COMPETES  ─── SAME_GROUP │
│                                                             │
│  点击节点 → 侧边详情面板 (PanoScore / 提及率 / 情感趋势)      │
│  滚轮缩放 / 拖拽平移 / 双击下钻                               │
└─────────────────────────────────────────────────────────────┘
```

- **节点类型**: Category (品类, 按层级大小), Brand (品牌, 大小映射 PanoScore), Product (产品, 较小)
- **边类型**: COMPETES_WITH (红色虚线), SAME_GROUP (蓝色实线), SUBSTITUTES/PAIRS_WITH 等 (灰色)
- **交互**: 点击节点弹出侧边详情面板 (PanoScore、提及率、情感趋势迷你图)；双击 Brand 节点可下钻看该品牌的产品子图；滚轮缩放 + 拖拽平移
- **筛选**: 顶部搜索框 + 品类筛选器 + 关系类型筛选器
- **转化入口**: 详情面板底部显示价值驱动的 CTA (见下方"品牌详情面板与转化设计")

**② List View (列表视图)**:

传统的表格/卡片列表，适合目标明确的查找和对比：

```
┌─────────────────────────────────────────────────────────────┐
│  美妆个护 · 品牌列表                    [Graph] [List]  🔍  │
│                                                             │
│  品类筛选: [全部 ▾]  价位: [全部 ▾]  排序: [PanoScore ▾]    │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 香奈儿  Chanel     国际高端  护肤/彩妆  85.0  ↑2.3  │   │
│  │ 雅诗兰黛  Estée Lauder  国际高端  护肤   72.3  ↑1.1  │   │
│  │ 兰蔻  Lancôme     国际高端  护肤/彩妆  68.1  ↓0.5  │   │
│  │ SK-II            国际高端  护肤       65.4  ↑0.8  │   │
│  │ 迪奥  Dior        国际高端  彩妆/护肤  71.2  ↑1.5  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  点击行 → 展开品牌详情 (竞品关系、核心产品、近期趋势)         │
│  每行右侧: [创建监测项目] 按钮                               │
│                                                             │
│  [1] [2] [3] ... [12]  共 125 个品牌                        │
└─────────────────────────────────────────────────────────────┘
```

- **展示字段**: 品牌名、英文名、定位标签、主营品类、PanoScore、变化趋势
- **筛选**: 品类 (从知识图谱 Category 树)、价位段、搜索关键词
- **排序**: PanoScore、提及率、情感分、变化幅度
- **展开行**: 点击品牌行展开详情卡片，显示竞品关系 (来自图谱 COMPETES_WITH 边)、核心产品列表、近 7 天趋势迷你图
- **分页**: TanStack Table 驱动，支持分页 + 每页条数切换
- **转化入口**: 每行右侧"创建监测项目"按钮

**两种视图的切换**: 顶部 Tab 切换 `[Graph] [List]`，切换时保留当前的筛选条件和搜索关键词。

**③ 行业 PANO Score 排行榜 (Hero 变体, 2026-04-17 新增)**:

行业探索页底部的 Top 8 排行榜, 应用 DESIGN_TOKENS C6 "放大胜利者" 变体:

- **Top 1 (Hero 卡)**: 横向布局 `flex items-center gap-8`, `PanoRing size={150}`, `linear-gradient(135deg, var(--color-bg-card) 0%, var(--color-bg-badge) 100%)` 渐变背景, `border-left: 4px solid var(--color-accent)`, `shadow: 0 8px 24px rgba(99,91,255,0.12)`, 左上 Badge `#1` + change + "行业领军" 标签, 3-col 指标网格 (提及率/排名/情感)
- **#2 - #8**: 普通 `grid-cols-4` 小卡片, `PanoRing size={100}`, 位置编号 `#idx+2`
- **数据契约 (C7)**: 8 个品牌按 `panoScore` 降序排, `brand.ranking` 字段必须等于排序后索引 +1; 若排行榜"位置 #N"和品牌卡里"排名 #ranking"Badge 出现矛盾, mock 数据需修复
- **SoV 饼图配套 (C3)**: 同页 `SOV_DATA` 必须包含这 8 个品牌 + "其他" ≤ 10%

完整视觉规范见 `docs/DESIGN_TOKENS.md` C6 / C7。

**品牌点击行为与转化设计 (2026-04-16 修订)**:

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"直达 Brand Detail"是 Harness 实施约束, 禁止进入 messages.*.json 或 JSX 硬编码文本; 页面边界应通过信息架构 + 交互跳转表达 (PRD §4.6.0a)。

用户在 Graph View / List View 中点击品牌节点或行时, **不再弹出侧边详情面板**, 而是**直接跳转到 `/brands/:brandId?tab=overview`** (品牌详情页, §4.6.1b) — 理由:

1. 弹出式面板是"探索→深度"路径上的不必要中转, Stripe 风格 deep-link 更符合"选中即打开"直觉
2. `/brands/:id` 已经是 SSR 友好的独立 URL (同 §4.6.1d 产品详情), 直链可分享, 利于 SEO 长尾
3. 面板能展示的信息有限, Brand Detail 页的 4 子 Tab (概览/诊断/产品/引擎对比) 才是单品牌深度分析的完整容器
4. 面板 + 详情页双入口会造成"为什么这里显示得不一样"的信息架构混乱

**跳转后 URL**: `/brands/:brandId?tab=overview&from=industry&industryId={industryId}`
- `from=industry` 告知 Brand Detail 展示"← 返回行业探索视图"面包屑
- Brand Detail 在**未监控状态**下会自动进入只读模式 + 展示"加入竞品监控"一键按钮 (详见 §4.1.2a 和 §4.6.1b)

**旧"品牌详情面板"移除路径**:
- `IndustryPage.jsx` 中的侧边 Panel 组件改为: 点击节点 / 行时使用 React Router `navigate(/brands/:brandId?from=industry)`, 不再渲染本地 Panel
- Panel 内"创建监测项目" CTA 迁移到 Brand Detail 未监控状态的顶部 upsell banner, 语义从"新建 Project" 转为"加入当前 Project 竞品池" (详见 §4.1.2a — 主品牌是用户视角的锚点, 不应被行业探索流随意替换)

**侧边栏状态 (无 Project 时)**:

```
┌─────────────────────────────┐
│  美妆个护                     │  ← 当前行业名
│  品牌 152 · 每日监测中    ▾    │  ← 行业概况，非"模式标签"
├─────────────────────────────┤
│  (尚未创建监测项目)             │
│  ＋ 创建监测项目               │  ← 引导转化
└─────────────────────────────┘
```

- 不显示"探索模式"标签——避免暗示用户"还没完成什么"，制造焦虑
- 用行业概况数据 (品牌数 + 监测状态) 替代模式标签，传递价值感

#### 4.1.1d 零 Project 态引导 & 专家快路径 (2026-04-17 新增)

> **⚠️ 2026-04-20 SUPERSEDED by §4.6-IA-v2.F**: 本节 E1/E2/E3/E4 四面 Empty State 方案**全部废除**。2026-04-20 Brand/Industry Mode IA 将零 Project 态处理统一为**强制重定向 `/onboarding`** (独立 4 步引导页, 无 App shell)——用户不会再看到"空侧栏 + CTA"形态。本节保留作为历史记录, 新实施以 §4.6-IA-v2.F 为准, 不再按本节实现 DashboardEmptyState / LandingNavQuickCreateButton / ProjectRequiredBanner 组件。原 DashboardEmptyState.jsx / ProjectRequiredBanner.jsx / LandingNavQuickCreateButton.jsx 任务 (若未完成) 直接取消。

> **本节目的**: 统一规格"已登录但 `User.projects.length === 0` / 未登录想直接建项目"两类场景的 Empty State UX, 补齐 §4.1.1b Data-Before-Auth 路径在"登录后回到工作台"这一段的留白. 历史上该处只有一句"先逛逛" CTA, 实际 frontend (`DashboardLayout.jsx:112` / `BrandsPage.jsx:28` / `ProjectContext.jsx:48`) 硬编码取 `PROJECTS[0]`, 零项目路径未走通, 违背 §4.1.1 验收 KPI "注册后 D1 激活率 ≥ 30%" 的转化收口.
>
> **本节锁定的三类痛点 (Frank 2026-04-17 反馈)**:
> - **Pain A**: 新用户不知道能建项目, 浏览行业/品牌时看不到"创建监测项目"入口, 得误打误撞点到品牌详情才发现 → E1 + E2 解决
> - **Pain B**: 专家用户已知监测目标, 进来后没"快速建项目"捷径, 被迫走浏览→点品牌→CTA 的长路径 → E3 + T9 解决
> - **Pain C**: 注册/登录完成后落到行业页或空白 /dashboard, 没有"下一步: 设置第一个项目"引导 → E1 解决
>
> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节 ASCII 结构与实施措辞 ("零 Project 态" / "专家快路径" / "引导位" / "Empty Surface") 严禁以 i18n key value 或 JSX 文本节点形式直接呈现给用户. 用户侧文案走 `dashboard.empty.*` / `sidebar.empty.*` / `nav.quickCreate.*` / `project.gatedBanner.*` 命名空间, 由 §4.10.4a 约束. 参见 §4.6.0a.

**A. 四个引导位 (Authoritative Empty Surface Registry)**

| ID | 位置 | 触发条件 | 主 CTA | 次 CTA | i18n 命名空间 | 覆盖痛点 |
|----|------|---------|--------|--------|---------------|---------|
| **E1** | `/dashboard` 主体区域 | 已登录 + `projects.length === 0` | `+ 创建第一个项目` → `/projects/new` | `先探索行业数据 →` → `/industries` | `dashboard.empty.*` | A + C |
| **E2** | `DashboardLayout` 侧栏 ProjectSelector 位置 | 已登录 + `projects.length === 0` | `+ 创建第一个项目` (**替代整个 Selector 外观**) → `/projects/new` | — (无, 避免占据侧栏空间) | `sidebar.empty.*` | A + D |
| **E3** | Landing `/` 顶部 nav 右侧 | 常驻可见, 按三态切换文案 | 未登录: `+ 创建监测项目` (触发 T9 `<AuthPromptModal>`); 已登录零 Project: `创建第一个项目 →` → `/projects/new`; 已登录有 Project: `进入工作台 →` → `/dashboard` | — | `nav.quickCreate.*` | B |
| **E4** | 任意强制登录且依赖 Project 的子页顶部 (如 `/brands/:id?tab=diag` / `/topics`) | 已登录 + 零 Project | inline `+ 创建项目解锁` → `/projects/new?primaryBrandId={当前品牌}` (若当前页有品牌上下文) | `关闭横幅` (session 级记住关闭状态) | `project.gatedBanner.*` | 防 dead-end |

**B. 核心 UX 结构**

**E1 Dashboard Empty** (主力锚点):

```
┌────────────────────────────────────────────────────────────┐
│  {dashboard.empty.title}                                   │
│  (例: "你还没有监测项目")                                  │
│                                                            │
│  {dashboard.empty.subtitle}                                │
│  (例: "创建第一个项目, 追踪你的品牌在 ChatGPT /            │
│        豆包 / DeepSeek 中的表现")                          │
│                                                            │
│  [+ 创建第一个项目]  ← 主按钮 t-btn-primary                │
│  [先探索行业数据 →]  ← 次按钮 t-btn-secondary              │
│                                                            │
│  ─────────────────────────────────────────                 │
│                                                            │
│  {dashboard.empty.preview.title}                           │
│  (例: "建成后你将看到:")                                   │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ PANO     │  │ SoV      │  │ 竞品     │                  │
│  │ Score    │  │ 饼图     │  │ 四象限   │                  │
│  │ (灰色占位)│  │ (灰色占位)│  │ (灰色占位)│                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
│  (整个预览区 onClick 跳 /projects/new)                     │
└────────────────────────────────────────────────────────────┘
```

- **预览卡用灰色占位图**, 禁止调用 Recharts 渲染真实/mock 数据 (避免误导用户"以为已经有数据只是空")
- 避免"欢迎 Frank!" 寒暄式开场, 直奔价值锚点

**E2 Sidebar Empty**: 零 Project 时 ProjectSelector **整体变形**为 Empty Button, 不是在原 Selector 展开后的底部塞 "+ 新建项目":

```
零 Project 态 (替代 Selector 外观):
┌──────────────────────────┐
│  + 创建第一个项目         │ ← 主色强调, 大号按钮
│  {sidebar.empty.hint}    │ ← 小字, 例: "建项目解锁工作台"
└──────────────────────────┘

有 Project 态 (保留现状):
┌──────────────────────────┐
│  美妆个护          ▼     │
│  雅诗兰黛 · 主品牌       │
└──────────────────────────┘
    (展开后列表 + 底部 "+ 新建项目", 同现状)
```

- **⚠️ 严禁**: 零 Project 态沿用 "Select Industry" / "Select Brand" / "Select Project" 等误导 label (现状 `ProjectSelector.jsx:74/85`). 必须替换为 "+ 创建第一个项目" 或等价 CTA 文案
- 点击直接跳 `/projects/new`, 不打开 dropdown (零 Project dropdown 内容为空, 打开无意义)

**E3 Landing Quick Create** (Pain B 主解法):

- 位置: Landing `/` 顶部 nav 最右侧, 主色填充按钮, 圆角 8px, 高度 36px
- **不与 Data-Before-Auth 冲突的理由**: Landing 首屏主体仍是 §4.1.1b 的"今日 AI 热度 Top 4 行业"卡片 (主路径); nav 快捷按钮只给"已有明确目标品牌"的专家一条捷径, 捷径下一步 (`/projects/new` Step 1 选主品牌) 仍然要用知识图谱品牌搜索——数据曝光照旧, 专家和新手分流而非强制分叉
- 按钮态切换逻辑:
  - 未登录: "+ 创建监测项目" → 触发 T9 `<AuthPromptModal>` (hookKey=`auth.hook.quick_create_project`, returnTo=`/projects/new&source=landing_nav`)
  - 已登录 + 零 Project: "创建第一个项目 →" → 直接跳 `/projects/new?source=landing_nav` (不弹 modal)
  - 已登录 + 有 Project: "进入工作台 →" → 跳 `/dashboard` (退化为"快速返回"按钮)

**E4 Gated Page Banner**: 已登录但零 Project 用户尝试访问需 Project 的子页 (如 `/brands/:id?tab=diag`, `/topics`) 时的顶部横幅, 防止 dead-end:

```
┌──────────────────────────────────────────────────────────────┐
│ ⓘ  {project.gatedBanner.body}                                │
│    (例: "需要先创建项目才能看到{brand}的诊断分析")           │
│    [+ 创建项目解锁] [关闭]                                   │
└──────────────────────────────────────────────────────────────┘
```

- 与 §4.6.1b 状态 #5 (已有 Project 但当前品牌未在竞品池) 的 upsell banner 并存但语义有别: #5 是"扩竞品池", E4 是"从零建项目"
- 关闭后 session 级记住 (`sessionStorage`), 避免同一 session 反复出现

**C. 状态机 (已登录用户 5 种路径 × 零/有 Project)**

| 用户路径 | 落地页 | 应渲染 |
|---------|--------|--------|
| 完成 T1-T8 的 AuthPromptModal 注册, `return_to` 带 action (watch/export/subscribe) | `return_to` 原页 | Action replay (§4.1.1c.A), **不显示** Empty State — 新建的 Project 由 action 自动创建 |
| 完成 T4/T9 的 AuthPromptModal 注册, `return_to=/projects/new` | `/projects/new` | 直接进 §4.1.2 Project 创建流程, **不显示** Empty State |
| 路径 C 注册 + 选了行业 | `/industries/:id` | 行业探索视图 (零 Project 不影响该页, 公开只读也能看) |
| 路径 C 注册 + 跳过选行业 | `/dashboard` | **E1 Dashboard Empty** |
| 老用户删除最后一个 Project 后回 `/dashboard` | `/dashboard` | **E1 Dashboard Empty** |

**侧栏 E2 在所有已登录零 Project 场景下**都渲染 (与 E1 共存), 因为侧栏是持久化 UI chrome, 不关心路由.

**D. 埋点契约 (详见 §4.11.4 追加事件 #44-46)**

| 事件 | 触发位 | 关键属性 |
|------|--------|---------|
| `dashboard_empty_state_shown` | E1 / E2 进入视口 (Intersection Observer 或 mount) | `surface` (dashboard_empty / sidebar_empty), `has_explored_industry` (bool, 注册前是否浏览过任一 /industries), `default_industry_id` (nullable) |
| `dashboard_empty_state_cta_clicked` | E1 / E2 任一 CTA 点击 | `surface`, `cta` (primary / secondary) |
| `project_creation_entry_clicked` | E1-E4 + 既有的 Industry Row CTA / Brand Detail CTA / T4 / T9 任一触发时 | `entry_source` ∈ {`empty_state_dashboard`, `empty_state_sidebar`, `landing_nav_quick`, `industry_row_cta`, `brand_detail_cta`, `gated_banner`}, `is_authenticated` (bool) |

本事件组回答三个业务问题:
1. **引导位有效吗**: `dashboard_empty_state_shown → cta_clicked` 转化率, 按 `surface` 分群
2. **哪个入口最拿转化**: `project_creation_entry_clicked` 按 `entry_source` 占比 → 指导后续重点投入
3. **Pain C 兜底多少**: 路径 C 注册用户中, `dashboard_empty_state_shown` 触达率 × 从 E1 进 `project_created` 转化率

**E. Harness 拦截 (pre-commit + CI)**

```bash
# (1) 禁止零 Project 态渲染 "Select Industry / Select Brand / Select Project" 误导 label
# (ProjectSelector 必须用条件分支切换 Empty/Active 两态, 不能让 Empty 态沿用 Active 态文案)
grep -rnE '"Select (Industry|Brand|Project)"' frontend/src --include='*.jsx' --include='*.tsx' | \
  grep -vE '\.test\.|\.stories\.'
# 任何输出 = Empty 态复用了 Active 态 label, 拒绝合并

# (2) 禁止 DashboardPage 在 projects.length === 0 时渲染 KPI 卡 / 竞争视图 / 告警条
# (必须 early-return <DashboardEmptyState>)
grep -nE 'projects\.length\s*(===?\s*0|<\s*1)' frontend/src/pages/DashboardPage.jsx
# 应至少匹配 1 行 (早退判断); 0 匹配 = 零项目路径未实现, 拒绝合并

# (3) §4.1.1d 新增 i18n key 必须全部存在
for key in title subtitle cta.primary cta.secondary preview.title; do
  for locale in zh-CN en-US; do
    grep -q "\"$key\"" frontend/src/i18n/messages/$locale/dashboard.json || echo "MISSING: dashboard.empty.$locale.$key"
  done
done
for key in cta hint; do
  for locale in zh-CN en-US; do
    grep -q "\"$key\"" frontend/src/i18n/messages/$locale/project.json || echo "MISSING: sidebar.empty.$locale.$key"
  done
done
for key in label.unauth label.zero_project label.has_project; do
  for locale in zh-CN en-US; do
    grep -q "\"$key\"" frontend/src/i18n/messages/$locale/common.json || echo "MISSING: nav.quickCreate.$locale.$key"
  done
done

# (4) entry_source 6 个枚举值必须在源码里都有接入
for source in empty_state_dashboard empty_state_sidebar landing_nav_quick industry_row_cta brand_detail_cta gated_banner; do
  grep -rqE "entry_source[^,]*['\"]${source}['\"]" frontend/src --include='*.jsx' --include='*.tsx' || echo "MISSING entry_source: $source"
done

# (5) DashboardLayout / BrandsPage / ProjectContext 不得硬编码 PROJECTS[0]
grep -rnE 'PROJECTS\[0\]|projects\[0\]' frontend/src/layouts frontend/src/pages/BrandsPage.jsx frontend/src/contexts/ProjectContext.jsx | \
  grep -vE '//.*fallback|//.*empty'
# 任何输出 = 还在硬编码默认 project, 拒绝合并 (零项目路径必须走 Empty State)
```

任何一条有输出视为"PRD §4.1.1d 与代码 drift", PR 必须修复方可合并.

##### 4.1.1d.C Onboarding 草稿存储与续期 (2026-04-21 新增)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节 schema / TTL / state machine 仅用于后端/中间件实现, 不在 Onboarding 页面以文字向用户解释。

**问题背景**: 决策 #10 提到"草稿 Project (中途退出) 存 72h, 下次登录 Route Guard 检测到草稿再次重定向续上", 但**存在哪里 / 什么 schema / 怎么过期**此前未定义, Review 2026-04-21 §3 指出这是一个边界空洞 (用户 Onboarding 到第 3 步关闭浏览器, 再进来要么从头, 要么数据丢失不知道).

**存储后端**: Supabase `draft_projects` 表 (独立于 `projects`, 因 `primary_brand_id` 在草稿态未必已选, `NOT NULL` 约束无法套用).

**Schema** (`prisma/schema.prisma` 新增 model):

```prisma
model DraftProject {
  id                   String   @id @default(cuid())
  userId               String
  user                 User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  step                 Int      @default(1)              // 1..4, 最后完成步骤
  industryId           String?                            // Step 1 选的行业
  primaryBrandId       String?                            // Step 2 选的主品牌
  competitorBrandIds   String[] @default([])              // Step 3 选的 3-5 个竞品
  preferences          Json?                              // Step 4 偏好 (时间窗/Engine 默认)
  lastStepCompletedAt  DateTime @updatedAt
  expiresAt            DateTime                           // lastStepCompletedAt + 72h, 定时任务清理
  createdAt            DateTime @default(now())
  @@unique([userId])                                      // 一个用户同时只能有一个草稿
  @@index([expiresAt])                                    // 清理任务走此索引
}
```

**状态机**:

```
[无记录] --选行业(Step 1)--> [DraftProject step=1]
         --选主品牌(Step 2)--> [step=2]
         --选竞品(Step 3)--> [step=3]
         --偏好(Step 4)--> [step=4]
         --提交--> [Project 正式记录, DraftProject 删除]
         --expiresAt 到--> [定时任务删除]
         --用户手动放弃--> [DraftProject 删除]
```

**Route Guard 检查** (`middleware.ts`):

1. 登录 session 有效 且 `projects.length === 0`:
   - 读 `draftProject = await db.draftProjects.findUnique({ where: { userId } })`
   - 若 `draftProject && draftProject.expiresAt > now`: 302 `/onboarding?resumeStep={draftProject.step}`, client 端从 `DraftProject` hydrate form state
   - 若 `draftProject == null || expiresAt <= now`: 302 `/onboarding` (全新开始)
2. 登录 session 有效 且 `projects.length >= 1`: 放行到请求目标

**清理任务**:

- Supabase cron / pg_cron: `DELETE FROM draft_projects WHERE expires_at < NOW()` 每小时跑一次
- Admin Session A4 看板新增 "Onboarding 漏斗" 一栏: 72h 内放弃的草稿数 / 占新注册用户比例

**埋点扩展** (§4.11):

- `onboarding_draft_created` (草稿第一次写入 Step 1)
- `onboarding_draft_resumed` (用户回来从草稿续上)
- `onboarding_draft_expired` (清理任务删除时每批触发一次, 不按用户级别)

**Harness 兜底** (TEST_STRATEGY §2.1 D7):

- `middleware.ts` 中检测 `projects.length === 0` 分支必须查 `draft_projects` 表 (grep `draftProject|draft_project|DraftProject`), 缺失 → PR block.

**UI 文案 (用户视角)**: Onboarding 页面顶部显示 "继续上次 · 第 {step}/4 步" (i18n key `onboarding.resume.banner`, zh-CN + en-US 必须成对). 禁止解释"72h" / "expiresAt" / "如果不完成会怎样", 这些是产品内部机制不必暴露.

---

#### 4.1.1e 登出 & 会话管理 (2026-04-17 新增)

> **本节目的**: 补齐 §4.1.1 注册/登录流程的镜像一侧——"用户如何离开"与"会话如何自然终结". 此前 PRD 仅在 §4.11 埋点章节提了一句 `resetSession()` 假设登出存在, 但登出入口、动作契约、跨标签同步、会话过期处理、与"注销账户"的边界均未定义; frontend 对应 `grep -i 'logout|signOut|退出|注销'` 在 `frontend/src` 下 **0 匹配**——用户一旦登录就出不去. 本节填坑.
>
> **本节锁定的设计决策 (Frank 2026-04-17)**:
> - **登出后跳 `/` 而非 `/auth`**: 对齐 §4.1.1b Data-Before-Auth 原则, 登出状态依然能看公开行业/品牌数据, 不把用户推到"非登录即孤岛"的死角
> - **不发 E6 登出通知邮件**: 登出是日常动作, 发邮件噪音过高. 仅 E5 异常登录提醒已承担安全侧责任
> - **会话刷新采用 silent refresh**: access token 15min + refresh token 30d, access 过期时前端透明换新; refresh 失败才弹 reauth modal (保留 `return_to` 不白屏)
> - **"登出" 与 "注销账户" 严格分离**: 前者清本地 session, 账户数据完整保留, 随时可回; 后者走 PIPL 删除权 30 天删号 (§4.11 行 4871), 属于 Danger Zone 二次 typed-confirm 操作
>
> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节 "登出动作契约" / "会话终结" / "跨标签同步" 等实施措辞严禁以 i18n key value / JSX 文本节点形式呈现给用户. 用户侧文案走 `common.userMenu.*` / `auth.session.*` / `settings.dangerZone.*` 命名空间, 由 §4.10.4a 约束. 参见 §4.6.0a.

**A. 登出入口 (Authoritative Logout Surface Registry)**

| ID | 位置 | 触发条件 | 结构 | i18n 命名空间 |
|----|------|---------|------|---------------|
| **L1** | `DashboardLayout` 侧栏底部用户头像按钮 | 已登录, 常驻 | 点击展开 Radix UI Popover 菜单: `[个人设置]` / `[语言: EN/中文]` / `[---]` / `[登出]` (危险色) | `common.userMenu.*` |
| **L2** | `SettingsPage` → Account 卡片底部 | 已登录, 点击 "登出当前设备" 链接 | inline 确认 (无 Modal, 防误触) → 执行 logout | `settings.account.logout.*` |
| **L3** | 会话过期弹窗 (Radix Dialog) | 任意已登录页, refresh token 失败 (401 + silent refresh 未恢复) | 标题 + body + `[重新登录]` 主 CTA (跳 `/auth?return_to=currentUrl`) + `[继续浏览]` 次 CTA (清本地 auth 状态, 跳 `/` 但不强制, 用户若在公开路由可留原地) | `auth.session.expired.*` |

- **⚠️ 禁止位置**: 不在 Landing nav / Dashboard 主内容区 / 任何 Empty State 放登出按钮. 登出是低频动作, 入口不喧宾夺主
- **L1 vs L2 分工**: L1 是主要入口, 一步可达; L2 只在 Settings 深层保留, 面向"已在设置页调整账户"的用户连贯操作

**B. `<UserMenu>` 组件规范**

- **依赖**: 必须使用 Radix UI Popover (见 CLAUDE.md "依赖规则"), 禁止手写 dropdown
- **挂载点**: 替换 `frontend/src/layouts/DashboardLayout.jsx:285-300` 当前整块都跳 `/settings` 的用户头像按钮; 改为按钮触发 Popover, Popover 内 `[个人设置]` 再跳 `/settings`
- **结构 (L1 展开态)**:
  ```
  ┌─────────────────────────────┐
  │  F  Frank                   │ ← 头像 + 用户名 (只读行)
  │     frankwangfj@gmail.com   │ ← 小字邮箱
  ├─────────────────────────────┤
  │  ⚙  {t('userMenu.settings')} │ → /settings
  │  🌐 EN / 中文 切换           │ → setLocale()
  ├─────────────────────────────┤
  │  ↩  {t('userMenu.logout')}  │ ← 危险色 (var(--color-danger))
  └─────────────────────────────┘
  ```
- **交互**:
  - ESC / 点击 Popover 外部 → 关闭 Popover
  - 点击 [登出] → 不弹二次确认 (登出本身可逆, 数据无损失, 二次确认是过度防御)
  - 仅当用户在 `/projects/new` 或其他"未保存状态"页时, 才 inline 警告 "有未保存的修改, 确认登出?" — 由调用方通过 `onBeforeLogout` prop 注入判断逻辑
- **i18n key 契约** (zh-CN / en-US 双语必须对齐):
  - `common.userMenu.settings`: "个人设置" / "Settings"
  - `common.userMenu.logout`: "登出" / "Log out"
  - `common.userMenu.logout_confirm_unsaved`: "有未保存的修改, 确认登出?" / "You have unsaved changes. Log out anyway?"

**C. 登出动作契约 (前端 + 后端)**

**前端 `logout()` 方法 (`useAuth()` hook 暴露)**:

```typescript
async function logout(trigger: 'manual' | 'session_expired' | 'multi_device_kick'): Promise<void> {
  // 1. 埋点 (先于清状态, 否则 distinct_id 已被 reset)
  analytics.track('user_logged_out', {
    session_duration_sec: Math.floor((Date.now() - session.startedAt) / 1000),
    trigger,
  });

  // 2. 调后端 POST /api/auth/logout
  //    后端负责: 吊销 refresh token + 清 session cookie (HttpOnly, Secure, SameSite=Lax)
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });

  // 3. 清前端状态
  //    - ProjectContext.reset() — 清 activeProject / projects 列表
  //    - localStorage 清用户偏好 (保留 genpanoGuest.* 匿名偏好, 供下次未登录浏览继续)
  projectCtx.reset();
  localStorage.removeItem('genpanoUser');  // 保留 genpanoGuest.*

  // 4. Mixpanel reset (清 distinct_id, 防止下一个登录用户继承事件)
  mixpanel.reset();  // §4.11 resetSession() 的具体实现

  // 5. 跨标签广播 (见 D 段)
  logoutChannel.postMessage({ type: 'logout', at: Date.now() });

  // 6. 跳转
  if (trigger === 'session_expired') {
    // 会话过期 — 保留 return_to 让用户重登后自动回到原页
    navigate(`/auth?return_to=${encodeURIComponent(currentPath)}&reason=session_expired`);
  } else {
    // 手动登出 — 跳 Landing / (符合 Data-Before-Auth, 不把用户推到 /auth 孤岛)
    navigate('/');
  }
}
```

**后端 `POST /api/auth/logout` 契约**:

- **输入**: Cookie (session / refresh token)
- **动作**: 吊销当前 refresh token (写 `revoked_at` 到 DB), 清 Set-Cookie 三个 token cookie
- **输出**: `204 No Content` (不返回任何 body; 即使 token 已过期或无 session 也返回 204 幂等, 避免登出失败让用户卡住)
- **安全**: 使用 POST (非 GET) 防 CSRF 预取误触发; Origin 校验

**D. 跨标签同步 (Multi-Tab Consistency)**

用户可能开了多个标签 (`/dashboard` + `/brands/:id` + `/settings`). 任一标签登出, 其他标签不应继续显示"已登录"UI.

**实现**: `BroadcastChannel('genpano-auth')` (现代浏览器全支持, IE 不支持但 MVP 已明确目标浏览器 ≥ Chrome/Safari/Firefox 最近两版).

```typescript
// 在 App.tsx 顶层建 channel
const logoutChannel = new BroadcastChannel('genpano-auth');
logoutChannel.onmessage = (e) => {
  if (e.data.type === 'logout') {
    // 当前标签收到其他标签的登出广播
    // 不直接跳转 (避免用户正在输入被打断), 而是标记 session 失效
    // 下一次路由切换 / 30s 后心跳检测时自动跳 /
    setSessionStale(true);
  }
};
```

- **fallback**: 若 BroadcastChannel 不可用, 降级用 `window.addEventListener('storage', ...)` 监听 `localStorage.genpanoSessionRevokedAt` 变化 (logout 时写入, 其他标签收到 storage event)
- **强制登出 (从服务端推)**: Phase 2 可接 WebSocket / SSE; MVP 不做, 靠 401 自然触发 silent refresh 失败分支

**E. 会话过期处理**

**Token 策略**:
- Access token: JWT, 有效期 **15 分钟**, 存 HttpOnly cookie
- Refresh token: 不透明字符串, 有效期 **30 天**, 存 HttpOnly cookie, 每次刷新轮换 (rotation)
- 所有 `/api/*` 响应带 `WWW-Authenticate: Bearer error="invalid_token"` 时触发前端 silent refresh

**Silent refresh 流程**:
```
API 返回 401 token_expired
    ↓
前端拦截器 (Axios interceptor) 自动调 POST /api/auth/refresh
    ↓
    ├─ 成功 → 用新 access token 重试原请求 (用户无感知)
    └─ 失败 (refresh token 也过期 / 已被吊销)
           ↓
           弹 <SessionExpiredModal> (L3)
           触发 logout('session_expired')
```

**L3 `<SessionExpiredModal>` 文案 (Radix Dialog)**:
- 标题: `t('auth.session.expired.title')` = "会话已过期" / "Your session has expired"
- 正文: `t('auth.session.expired.body')` = "为了保护你的账户安全, 请重新登录后继续" / "For your security, please log in again to continue."
- 主 CTA: "重新登录 →" / "Log in again →" → `/auth?return_to=${currentPath}&reason=session_expired`
- 次 CTA: "继续浏览公开数据" / "Continue browsing" → 跳 `/` (若当前在公开路由, 留原地)

**F. "登出" vs "注销账户" 分离**

| 维度 | 登出 (§4.1.1e) | 注销账户 (PIPL 删除权) |
|------|---------------|----------------------|
| 入口 | `<UserMenu>` L1 / SettingsPage L2 | SettingsPage 底部 `Danger Zone` 卡片 |
| 确认强度 | 无二次确认 (除非有未保存修改) | typed-confirm: 用户输入自己邮箱才启用 `删除账户` 按钮 |
| 前端动作 | 清本地 session + 跳 `/` | 调 `DELETE /api/users/me` + 强制登出 + 跳 `/?account_deleted=1` 展示告别 toast |
| 后端动作 | 吊销当前 refresh token | 标记 `users.deletion_requested_at = now()`, 触发 30 天定时任务 (删用户行 + 外键级联 + Mixpanel `delete_user(distinct_id)`, §4.11 行 4871) |
| 数据保留 | 账户完整保留, 随时回来 | 30 天内可反悔 (用户登录后看到"账户已标记删除, 是否撤销?"); 30 天后不可逆 |
| 邮件通知 | ❌ 不发 | 即时发 E6 "账户注销确认", 并在 29 天时发 E7 "最后一次撤销机会" |
| 埋点 | `user_logged_out` (事件 #47) | `user_deletion_requested` (事件 #48) + `user_deleted` (事件 #49, 后端 30 天后触发) |
| i18n | `common.userMenu.*` / `auth.session.*` | `settings.dangerZone.*` |

- **⚠️ Danger Zone 必须隔离**: SettingsPage 内 "注销账户" 卡片用红色描边 + `var(--color-danger-subtle)` 背景 + 默认折叠 (点击展开), 防止用户误点
- **反悔机制**: 30 天窗口内用户再次登录时展示 Undo Banner: "你的账户已标记于 {date} 删除 (剩 {N} 天). [取消删除]" → 点击调 `POST /api/users/me/undo-deletion` 清 `deletion_requested_at`

**G. 事件埋点 (补充 §4.11.4)**

新增 1 个事件 (登出), 预留 2 个事件 (注销账户, 后端触发). MVP 事件总数 **46 → 47** (仅 logout 立即落实; 48/49 待 Settings Danger Zone 实施 Session 完工后再落, 本节先占号).

| # | 事件名 | 触发 | 属性 | 所属 Section |
|---|-------|------|------|-------------|
| 47 | `user_logged_out` | 用户点击 L1/L2 登出 或 silent refresh 失败自动登出 | `trigger` ∈ `manual` / `session_expired` / `multi_device_kick`, `session_duration_sec` (int), `had_project` (bool), `locale` (zh-CN / en-US) | S11 |
| (48) | `user_deletion_requested` | 用户在 Danger Zone typed-confirm 后点删除 | `self_reported_reason` (optional, nullable), `had_project` (bool), `account_age_days` (int) | S11, Phase 2 |
| (49) | `user_deleted` | 后端 30 天定时任务执行删除 | `account_age_at_deletion_days` (int), `undo_used` (bool, false 表示走完 30 天未撤销) | S11, Phase 2 后端侧 |

- **事件总数硬约束更新**: §4.11.0 原则 5 "MVP 阶段 ≤ 50 个事件", 当前 47 个 (含本节 #47), 留 3 个冗余
- **`user_logged_out` 上报时机**: 必须在 `mixpanel.reset()` **之前** 调, 否则 distinct_id 已清, 事件归属混乱
- **`had_project`**: Mixpanel Funnel 分析"有 Project 用户"vs"零 Project 用户"的留存差异, 映射 §4.1.1d D1 激活率 KPI

**H. i18n 命名空间 (新增 3 个)**

| 命名空间 | 键 | 承载 |
|---------|------|------|
| `common.userMenu.*` | `settings` / `logout` / `logout_confirm_unsaved` | UserMenu Popover 文案 |
| `auth.session.*` | `expired.title` / `expired.body` / `expired.cta_primary` / `expired.cta_secondary` | SessionExpiredModal |
| `settings.account.logout.*` | `link_text` / `description` | SettingsPage L2 inline 登出链接 |
| `settings.dangerZone.*` (Phase 2) | `title` / `delete_account.button` / `delete_account.typed_confirm_label` / `delete_account.warning` / `undo_banner.*` | Danger Zone 注销账户区 |

**I. Harness 拦截 (pre-commit + CI)**

```bash
# (1) 禁止在 /auth 之外的路由里硬编码 window.location.href = '/auth' (会话过期必须走 return_to 保留机制)
grep -rnE "(window\.location|location\.href|navigate)\s*=?\(?\s*['\"]/auth['\"]" frontend/src \
  --include='*.jsx' --include='*.tsx' | \
  grep -vE 'return_to|source=|reason=session_expired'
# 任何输出 = 没带 return_to 的硬跳 /auth, 会丢失用户上下文, 拒绝合并

# (2) logout() 前必须先埋点 user_logged_out
# 正则检查: mixpanel.reset() 前 N 行是否出现 track('user_logged_out')
awk '/mixpanel\.reset\(\)/{if(!found_track)print FILENAME":"NR" mixpanel.reset() without prior user_logged_out track";found_track=0} /track\(["\x27]user_logged_out/{found_track=1}' \
  frontend/src/**/*.jsx frontend/src/**/*.ts
# 任何输出 = reset 早于 track, 事件会失归属, 拒绝合并

# (3) BroadcastChannel 或 storage event 二选一必须存在 (跨标签同步不可缺)
grep -rnE "new BroadcastChannel\(['\"]genpano-auth['\"]\)|genpanoSessionRevokedAt" frontend/src \
  --include='*.jsx' --include='*.tsx' --include='*.ts' | wc -l
# 0 = 跨标签同步未实现, 拒绝合并

# (4) "登出" / "Log out" 文案必须走 i18n key, 不硬编码
grep -rnE '>[^<]*(登出|Log out|Logout|Sign out)[^<]*<' frontend/src \
  --include='*.jsx' --include='*.tsx' | \
  grep -vE "t\(['\"]common\.userMenu\.logout|t\(['\"]auth\.session"
# 任何输出 = JSX 硬编码登出文案, 拒绝合并

# (5) Danger Zone 删除账户按钮必须有 typed-confirm (Phase 2)
# 正则: 定位 delete_account.button 使用处, 检查相邻 50 行内是否出现 typed_confirm
grep -rnA50 "settings\.dangerZone\.delete_account\.button" frontend/src --include='*.jsx' | \
  grep -cE "typed_confirm|typedConfirm" || echo "MISSING typed-confirm near delete_account.button"
# Phase 2 实施时必须 exit 0 (≥1 匹配)
```

任何一条有输出视为"PRD §4.1.1e 与代码 drift", PR 必须修复方可合并.

**J. SESSIONS 任务清单 (Session 4a 追加)**

- **Task 2c** (紧跟 Task 2b 之后): `<UserMenu>` Popover (Radix) 挂到 `DashboardLayout.jsx:285-300`; `useAuth()` hook 新增 `logout(trigger)` 方法; `<SessionExpiredModal>` (L3); Axios interceptor 实现 silent refresh; BroadcastChannel 跨标签同步; `/api/auth/logout` 后端 endpoint; i18n 3 新命名空间; Harness 4 条 grep (#5 Phase 2 再开)
- **埋点**: `user_logged_out` (#47) 纳入 S4a Task 7 Mixpanel event catalog 落地批次 (与 Task 2b 的 #44-46 合并一批)
- **Settings Danger Zone (Phase 2, 不在 MVP Session 4a)**: 单独作为 Phase 2 Session, 覆盖 typed-confirm / DELETE endpoint / 30 天反悔机制 / E6/E7 邮件 / 事件 #48/#49

---

#### 4.1.2 Project (项目) 设计

> **核心定位**: Project 是用户消费平台数据的"视角过滤器"，不是数据容器。所有监测数据由平台统一生产，Project 决定"用户看哪些数据、怎么看"。

**Project 数据模型**:

```typescript
interface Project {
  id: string;
  userId: string;
  industryId: string;           // 所属行业 (从平台行业列表选)
  
  // ① 我是谁 — Project 的核心锚点
  primaryBrandId: string;       // "我的品牌" (关联到知识图谱中的 Brand 节点)
  
  // ② 我和谁比 — 竞争视角 (私有，其他用户不可见)
  competitorBrandIds: string[]; // 竞品列表 (平台基于图谱自动推荐 + 用户调整)
  
  // ③ 我怎么看 — 消费偏好
  preferences: {
    engineFilter: string[];     // 关注的引擎 (默认全部: ChatGPT/豆包/DeepSeek)
    reportSchedule: {           // 报告偏好
      weeklyEnabled: boolean;   // 默认 true
      monthlyEnabled: boolean;  // 默认 true
      emailRecipients: string[];
    };
    alertConfig: {              // 告警配置
      p0Notify: boolean;        // P0 即时通知 (默认 true)
      p1Notify: boolean;        // P1 即时通知 (默认 true)
      channel: 'email';        // MVP 仅邮件，Phase 2 支持微信/钉钉
    };
  };
  
  createdAt: string;
  updatedAt: string;
}
```

**Project 不存储任何监测数据** — 没有 UserMetricSnapshot、没有 UserCustomTopic。Dashboard 展示时，后端根据 `primaryBrandId` + `competitorBrandIds` + `industryId` 从平台数据中实时查询和过滤。

**Project 创建流程 (主路径 1 步 / 快路径 2 步, 2026-04-17 扩展)**:

Project 创建有两条入口, 对应 §4.1.1c 触发点矩阵的 T4 (从探索视图进入, 主路径) 和 T9 (从零 Project 引导位 / Landing nav 进入, 专家快路径):

**主路径 (T4)**: 行业 + 主品牌已从 URL 或上下文预填, 只需确认竞品 (1 步):

```
探索视图 → 点击品牌 → 品牌详情 → "+ 加入竞品监控" / "创建监测项目"
    │  (未登录先走 T4 AuthPromptModal, 注册后 return_to 带 primaryBrandId 预填)
    │  (行业 + 主品牌已确定)
    ▼
确认竞品 (唯一步骤，1 页搞定)
```

**快路径 (T9, §4.1.1d E1/E2/E3/E4)**: 无预填, 先选主品牌再确认竞品 (2 步):

```
§4.1.1d 引导位 → "+ 创建监测项目" / "+ 创建第一个项目" → /projects/new
    │  (未登录先走 T9 AuthPromptModal, 注册后跳 /projects/new, 无 primaryBrandId 预填)
    ▼
Step 1: 选主品牌
    ├── 默认滚到 User.defaultIndustryId 对应行业 (若路径 C 登录时选过行业)
    ├── 知识图谱品牌搜索 + List / Graph 视图切换 (复用 §4.1.1b 行业探索视图组件)
    └── primaryBrandId 确定
    ▼
Step 2: 确认竞品 (同主路径)
```

**两条路径共享 "确认竞品" 这一步** (结构 / UX 同下方):

```
确认竞品 (最后一步, 1 页搞定)
    ├── 平台基于知识图谱自动推荐 3-5 个竞品品牌:
    │   ├── 沿 COMPETES_WITH 边找直接竞品 → 标注"经常一起被提及"
    │   ├── 同品类 + 同价位段的品牌 → 标注"同价位竞品"
    │   └── 同行业热门品牌 → 标注"行业热门"
    ├── 每个推荐带推荐理由，降低用户选择负担
    ├── 用户可调整: 添加/移除竞品 (搜索该行业品牌列表)
    └── competitorBrandIds 保存
    │
    ▼
Project 就绪 → 进入 Dashboard (Project 视角)
    Dashboard 首屏呼应用户选择 (品牌 vs 竞品对比 + 数据快照)
```

**确认竞品页面设计**:

```
┌──────────────────────────────────────────────┐
│  雅诗兰黛的竞争对手                              │
│  基于 AI 引擎回答数据，这些品牌最常同时出现：      │
│                                                │
│  ✅ 兰蔻          Score 68.1    经常一起被提及    │
│  ✅ SK-II         Score 65.4    同价位竞品        │
│  ✅ 迪奥          Score 71.2    同品类竞品        │
│  ☐  资生堂        Score 58.7    同集团            │
│                                                │
│  + 搜索添加其他品牌                               │
│                                                │
│  [完成，开始监测]                                 │
└──────────────────────────────────────────────┘
```

- **推荐理由**: 每个竞品标注推荐来源 (图谱关系类型)，用户理解"为什么推荐这些"
- **默认选中**: 前 3 个直接竞品默认勾选，其余不勾选，用户可自由调整
- **搜索添加**: 支持搜索该行业所有品牌，不限于推荐列表

**报告 & 告警偏好 (不在创建流程中，移至项目设置)**:

Project 创建时自动使用默认值，用户可在项目设置中随时修改：
- 周报/月报: 默认均开启
- P0/P1 即时告警: 默认均开启
- 接收邮箱: 默认注册邮箱
- 用户此刻的诉求是"赶紧看 Dashboard"，不是配置邮件频率

**Dashboard 首屏 (Onboarding 闭环)**:

Project 创建完成后，Dashboard 首屏明确呼应用户的选择，形成"选择→结果"的闭环：

```
┌──────────────────────────────────────────────────┐
│  雅诗兰黛 vs 竞品                                  │
│  监测中: ChatGPT · 豆包 · DeepSeek                 │
│                                                    │
│  [PanoScore 对比图: 雅诗兰黛 vs 兰蔻 vs SK-II ...] │
│                                                    │
│  以下是现有数据的快照:                               │
│  · 你的品牌在 3 个引擎中被提及 847 次 (过去 7 天)    │
│  · 情感评分高于 68% 的竞品                          │
│  · 首份周报将于下周一发送到 frank@...                │
└──────────────────────────────────────────────────┘
```

**从侧边栏新建 Project (已有 Project 的用户)**:

已有 Project 的用户通过侧边栏"+ 新建项目"按钮创建新 Project，流程为：选择行业 → 搜索设定品牌 → 确认竞品 (共 3 步，因为没有从品牌详情面板进入的上下文)。搜索品牌时若图谱中无匹配，触发品牌提交流程 (见下方)。

**品牌提交流程 (Brand Submission)**:

当用户搜索的品牌不在平台知识图谱中时触发:

```
用户输入 "花西子" → 图谱无匹配
    │
    ▼
自动验证 (LLM + 公开数据):
    ├── 是否为真实品牌？(LLM 判断 + 搜索引擎验证)
    ├── 属于哪个行业/品类？
    ├── 品牌基本信息 (定位、价格区间、母公司)
    └── 核心产品列表 (LLM 推断)
    │
    ├── 验证通过 →
    │   ├── 创建 Brand 节点 → 加入知识图谱
    │   ├── 推断竞品关系 (LLM) → 创建 COMPETES_WITH 边
    │   ├── 创建产品节点 + 产品关系
    │   ├── Planner 为该品牌生成 Topic → 进入 Pipeline
    │   ├── 首次采集 (预计 2-6 小时，取决于队列)
    │   ├── 采集完成 → 通知用户 "你的品牌数据已就绪"
    │   └── 该品牌数据对所有选了同行业的用户可见
    │
    └── 验证不通过 →
        └── 提示用户 "未识别为已知品牌，请确认品牌名称"
            用户可补充信息重新提交
```

**Project 切换器 (Sidebar ProjectSelector)**:

Dashboard 侧边栏顶部提供 Project 切换组件，用户可在多个 Project 之间快速切换视角：

```
┌─────────────────────────────┐
│  美妆个护                     │  ← 当前行业名
│  雅诗兰黛 · 主品牌       ▾    │  ← 主品牌名 + 下拉箭头
├─────────────────────────────┤
│  ◯ 雅诗兰黛    Score 72.3  ✓ │  ← 当前选中 (active)
│  ◯ 兰蔻        Score 68.1    │
├─────────────────────────────┤
│  ＋ 新建项目                   │  ← 进入 Project 创建流程
└─────────────────────────────┘
```

- **收起态**: 显示当前 Project 的行业名 + 主品牌名 + 下拉箭头
- **展开态**: 列出用户所有 Project，每项显示品牌名 + PanoScore，当前 Project 带 ✓
- **切换**: 点击即切换，Dashboard 所有数据根据新 Project 的 `primaryBrandId` + `competitorBrandIds` 重新查询
- **新建**: 底部"+ 新建项目"按钮进入 Project 创建流程 (选行业→搜索品牌→确认竞品)

**项目设置页 (Project Settings)**:

路由 `/project-settings`，用户从 Dashboard 侧边栏或设置页进入，Stripe 风格双栏布局：

```
左栏 (主内容):                          右栏 (摘要):
┌───────────────────────────┐    ┌──────────────────┐
│ 项目信息                    │    │ 项目概览           │
│  行业: 美妆个护             │    │  创建: 2026-03-15  │
│  主品牌: 雅诗兰黛           │    │  行业: 美妆个护     │
│  项目名称: [可编辑]         │    │  主品牌: 雅诗兰黛   │
├───────────────────────────┤    │  竞品: 3 个         │
│ 竞品管理 (最多 5 个)        │    │  报告: 周报+月报    │
│  兰蔻 · 国际高端  68.1  ✕  │    ├──────────────────┤
│  SK-II · 国际高端  65.4  ✕ │    │ [删除项目]          │
│  迪奥 · 国际高端  71.2  ✕  │    └──────────────────┘
│  [+ 添加竞品]               │
├───────────────────────────┤
│ 报告偏好                    │
│  周报 [ON]  月报 [ON]       │
│  邮箱: frank@example.com   │
├───────────────────────────┤
│ 告警设置                    │
│  P0 即时通知 [ON]           │
│  P1 即时通知 [ON]           │
├───────────────────────────┤
│        [保存修改]            │
└───────────────────────────┘
```

- **项目信息**: 行业和主品牌为只读 (创建后不可变)，项目名称可编辑
- **竞品管理**: 列出当前竞品 (显示名称、定位标签、PanoScore)，可逐个移除 (✕)，可搜索添加新竞品 (从同行业品牌列表选择，上限 5 个)
- **报告偏好**: 周报/月报开关 + 邮箱收件人列表
- **告警设置**: P0/P1 告警开关
- **删除项目**: 右栏底部，需二次确认，仅删除 Project 记录 (不影响平台数据)

**关键设计决策**:

1. **一个用户可创建多个 Project** — 适配 SEO agency (小李) 管理多个客户品牌的场景，每个 Project 对应一个品牌视角
2. **竞品配置完全私有** — 用户不知道别人关注了哪些竞品，品牌之间的竞争分析视角是敏感信息
3. **品牌提交即入图谱** — 用户提交的品牌通过验证后成为平台公共资产，所有同行业用户受益 (共建效应)
4. **Project 是轻量的** — 本质是一组 ID 引用 + 偏好配置，不存储任何监测数据
5. **MVP 限制**: 每用户最多 3 个 Project (免费)，Phase 2 可扩展
6. **行业和主品牌创建后不可变** — 避免数据口径混乱，如需更换品牌应新建 Project
7. **不强制创建 Project** — 探索型用户选完行业即可看数据，降低注册流失；探索视图提供 Graph View + List View 两种模式浏览知识图谱
8. **探索到项目的自然转化** — 探索视图中每个品牌都有"创建监测项目"入口，跳过 Step 1-2 直接进入竞品确认，降低转化摩擦
9. **一键加入监控 = 加入当前 Project 竞品池 (2026-04-16 新增)** — 从行业探索或任何非 Project 视角点品牌进入 Brand Detail, 若未监控则顶部显示"+ 加入竞品监控"按钮, 默认行为是把该品牌加到当前 active Project 的 `competitorBrandIds` 中 (详见 §4.1.2a)。理由: 主品牌是用户视角的深度锚点, 不会因行业探索随意替换; Project 数量也不会爆炸

#### 4.1.2a 一键加入监控 (Watch Button) ⭐ 2026-04-16 新增

> **定位**: 从任何非 Project 视角 (行业探索 / 排行榜 / 直链) 进入 Brand Detail 时, 用户能以最低摩擦把该品牌加入监控。默认语义 = **加入当前 active Project 的竞品池**, 不改变主品牌。

**按钮位置**: Brand Detail 顶栏右侧 (与"分享体检报告 PDF"并列), 常驻 — 无论监控状态都渲染, 只是文案/样式不同。

**按钮状态机 (6 状态)**:

| # | 场景 (用户 × 品牌关系) | 按钮文案 | 点击行为 | 成功反馈 |
|---|------------------------|---------|----------|----------|
| 1 | 该品牌 = 当前 Project.primaryBrandId | `✓ 主品牌 · {Project名}` (只读 badge, 不可点) | — | — |
| 2 | 该品牌 ∈ 当前 Project.competitorBrandIds | `✓ 已在监控 · {Project名}` (可 hover, 下拉"移出竞品池") | 确认弹窗 → 移除 → 成功 Toast | Toast: "已从 {Project} 移除 {brand}" |
| 3 | 该品牌 ∉ 当前 Project, 且同行业 | `+ 加入竞品监控` (主 CTA 样式) | 直接加入 `competitorBrandIds` (乐观更新), 失败回滚 | Toast: "已加入 {Project} 竞品池, 下次采集后开始追踪" |
| 4 | 该品牌 ∉ 当前 Project, 跨行业 | `+ 加入竞品监控 ▼` | 下拉 2 选项: "加入当前项目 (跨行业)" + "创建新项目监控此品牌" | 加入: Toast + 警告"跨行业竞品数据对比可能不准确"; 新项目: 跳 §4.1.2 Project 创建 |
| 5 | 用户已登录但无 Project | `+ 创建项目监控此品牌` (主 CTA) | 跳转 §4.1.2 Project 创建, `primaryBrandId` 预填该品牌 (允许用户修改) | 创建成功 → 回到 Brand Detail (此时状态变为 #1) |
| 6 | 用户未登录 | `+ 免费注册监控此品牌` | 跳转 /auth?return_to=/brands/:id&monitor_brand=:id → 注册成功 → 自动走 #5 路径 | — |

**主 CTA 视觉**: 实心品牌色按钮 + Lucide `Plus` / `Check` icon, `var(--color-accent)` + 白字; 只读 badge 为描边式 + `var(--color-success)` 绿底。

**后端 API**:
- `POST /api/v1/projects/{projectId}/competitors` body `{ brandId }` (状态 #3 + #4a)
- `DELETE /api/v1/projects/{projectId}/competitors/{brandId}` (状态 #2 移出)
- 状态 #3 乐观更新: 前端先 append 到本地 Project 缓存, API 失败则 rollback + 错误 Toast
- 无 `POST /api/v1/projects/{projectId}/primary-brand` (主品牌不可通过此按钮替换, 防误操作; 如确需更换主品牌, 走 Project Settings 的"删除并新建"流程)

**跨行业竞品保护 (状态 #4)**:
- 对比分析需要同行业基准, 跨行业比较会让 SoV / 排名失真
- UI 明确警告: "{brand} 属于 '{targetIndustry}' 行业, 当前 Project 监控 '{projectIndustry}'. 加入后在 SoV / 排名卡片上会显示灰色 ⚠️ 图标, 提示数据口径不同"
- Project Settings 的竞品列表中, 跨行业竞品单独分组显示

**边界与风险控制**:
- **竞品数量上限**: 单个 Project 最多 10 个竞品, 超出时按钮变灰 + tooltip "已达上限 (10), 请先移除部分竞品或创建新项目"
- **免费用户 Project 上限**: 3 个 (§4.1.2 决策 5), 状态 #5 达到上限时按钮变灰 + 引导升级或重用
- **防抖**: 同一 `(userId, brandId, projectId)` 30 秒内只允许 1 次加入操作, 防连点重复
- **i18n**: 所有文案走 `t('brand_watch.*')` 命名空间, `{Project名}` / `{brand}` 经 `formatBrand()`

**兼容旧路径**: §4.1.1b 原"探索视图品牌详情面板 → 创建监测项目"入口语义变更为"加入竞品池" (状态 #3 / #5 / #6), 原"创建监测项目"完整流程保留在侧栏"+ 新建项目"和 Brand Detail 未监控 upsell banner 的次要 CTA 里。

### 4.2 智能监测 Pipeline: Topic → Prompt → Query → Response

这是 GENPANO 的核心差异化模块。

#### 4.2.0 术语定义 & 四层 Pipeline 总览

GENPANO 的数据采集采用四层递进 pipeline，每一层有明确的输入输出和职责边界：

| 层级 | 英文 | 定义 | 来源 | 扇出关系 |
|------|------|------|------|----------|
| **Topic** | 监测主题 | 需要监测的品牌/产品/品类维度的主题 | Planner 从知识图谱 (4.0.1a) 自动生成 | 1 Brand → N Topics |
| **Prompt** | 提示语 | 结合意图 (Intent) 生成的自然语言问句 | Topic × Intent 矩阵 | 1 Topic → M Prompts |
| **Query** | 可执行查询 | Prompt + Profile 组合后的最终执行单元 | Prompt × Profile 采样 | 1 Prompt → K Queries |
| **Response** | AI 回答 | 引擎返回的完整回答 (含引用、卡片等) | Browser/API 执行 Query | 1 Query → 1 Response |

**总扇出**: 1 Brand → N×M×K Responses

```
Knowledge Graph (知识图谱: Industry→Category→Brand→Product + 关系边)
        │
        ▼  Planner (规划器，Bottom-Up)
    ┌─────────┐
    │  Topics  │  监测主题: "小棕瓶评价"、"精华液对比"、"抗衰产品推荐"
    └────┬────┘
         │  × Intent (informational / commercial / transactional / navigational)
         ▼
    ┌─────────┐
    │ Prompts  │  自然语言问句: "小棕瓶和小黑瓶哪个更值得买？"
    └────┬────┘
         │  × Profile (用户画像采样)
         ▼
    ┌─────────┐
    │ Queries  │  可执行查询: Prompt + persona前缀 + locale + context
    └────┬────┘
         │  Browser / API
         ▼
    ┌──────────┐
    │ Responses │  AI 引擎的完整回答
    └──────────┘
```

#### 4.2.1 第一层: Topic 生成 (Planner)

**设计原则: Bottom-Up 生成** — Topic 从产品级（最具体、最接近真实用户）向上抽象到品牌级和行业级，而非 Top-Down 凭空生成行业泛主题。

```
                ┌────────────────────────┐
                │  行业级 Topic (抽象)     │ ← 从品牌/产品属性中提炼品类词+场景词
                │  "精华液推荐"           │   + 竞品发现类主题
                │  "抗衰精华选购"         │
                └───────────┬────────────┘
                            │ 抽象化: 去掉品牌名，保留品类+场景
                ┌───────────┴────────────┐
                │  品牌级 Topic (中间层)   │ ← 从产品列表推导品牌维度
                │  "雅诗兰黛 vs 兰蔻"     │
                │  "雅诗兰黛口碑"         │
                └───────────┬────────────┘
                            │ 抽象化: 去掉产品名，保留品牌
                ┌───────────┴────────────┐
                │  产品级 Topic (最具体)   │ ← 生成起点，最接近真实用户关注
                │  "小棕瓶 vs 小黑瓶"     │
                │  "小棕瓶适用肤质"       │
                └────────────────────────┘
```

**为什么不 Top-Down**: 直接让 LLM 生成"2026年美妆行业发展趋势"这类主题，太人造、太泛——真实用户很少这样问 AI。真实用户的行业级主题本质上是带品类词的产品/品牌泛化表达。

**输入**: 知识图谱 (行业 → 品类树 → 品牌节点 + 关系边 → 产品节点 + 关系边)
**输出**: 标注了层级 (产品/品牌/行业)、场景标签的 Topic 集合

**图谱驱动的 Topic 生成优势**:
- 品类树提供多级 Topic 粒度: "精华推荐" (L1) → "抗衰精华推荐" (L2)
- COMPETES_WITH 边直接生成对比 Topic: "小棕瓶 vs 小黑瓶"
- SUBSTITUTES 边生成替代场景 Topic: "精华和精华面霜怎么选"
- BUDGET_ALT_OF 边生成平替 Topic: "小棕瓶平替推荐"

**Planner 生成流程 (严格按此顺序)**:

**Step 1: 产品级 Topic 生成 (最先)**

从具体产品出发，生成最接近真实用户关注点的 Topic:
- 产品评价: "{产品}评价"
- 产品对比: "{产品A} vs {产品B}"
- 产品适用性: "{产品}适用{场景/肤质/需求}"
- 产品价格: "{品类}{价格区间}选购"

**Step 2: 品牌级 Topic 生成 (从产品推导)**

从产品列表中推导品牌维度 Topic:
- 品牌评价: "{品牌}口碑"
- 品牌对比: "{品牌A} vs {品牌B}" (从产品对比中抽象)
- 品牌定位: "{品牌}定位/档次"

**Step 3: 行业级 Topic 生成 (从品牌/产品抽象)**

从品牌和产品的属性标签中提炼品类词和场景词:
- 品类推荐: "{品类}推荐"
- 场景驱动: "{场景}×{品类}"
- **竞品发现**: "{品类定位}品牌" — 用于发现用户未关注的竞品

**Step 4: 变体扩展 (对所有层级)**
- 口语化变体: 将正式 Topic 转为口语表达
- 场景化变体: 添加具体使用场景 (送礼、自用、专业需求等)
- 地域化变体: 针对中国市场添加本地化表达
- 长尾化变体: 扩展为更具体的细分 Topic
- **实现手段 (2026-04-22 显式化 · Session 2.1)**: **本步骤由 LLM (火山引擎统一入口, 默认 `doubao-1-5-pro`) 完成**。Planner 先按 Step 1-3 模板产出 Topic 骨架 (`topicSkeleton`), 再调用 LlmTransport 对每条骨架生成 2-3 个自然化变体 (variants)。LLM 调用走 Session 1.5 落地的 `backend/src/platform/llm/client.ts` 单一入口, 每行业 ≤ 50 次调用 (LlmCallBudgetExceededError 硬约束), dry-run transport 用 canned fixture 覆盖 CI, live transport 要求 `VOLC_API_KEY`

**Step 5: 质量控制**
- 去重 & 相似度合并
- 基于搜索趋势数据验证 Topic 真实度
- 每个维度的 Topic 数量平衡
- **真实度评分 (2026-04-22 显式化 · Session 2.1)**: 由 LLM 对每条 Topic (含 Step 4 变体) 自评 `realismScore ∈ [0, 1]`, 判定"像不像真人会关注的 Topic"。**硬阈值 `realismScore < 0.5` 的 Topic 丢弃**, `[0.5, 0.7)` 写入 `PlatformTopic.realismScore` 列供 Admin 审核,  `≥ 0.7` 默认纳入 Planner 输出池。LLM 打分 prompt 模板由 `backend/src/platform/planner/prompts.ts` 统一管理, 规则 heuristic 不可替代此步骤 (因为"像真人" = 语义判别, 非字面正则)
- **品类 dimension 纯净度约束 (2026-04-16 新增)**: `dimension='品类'` 的 Topic 标题和描述**禁止包含任何品牌名** (KG 中 Brand.{nameZh, nameEn, aliases[]} 的任意匹配)。品类 Topic 必须是纯品类/场景表述 (如 "精华液推荐"、"抗衰产品对比"), 不得出现 "雅诗兰黛精华推荐" 这类混合表述 — 如含品牌名应归入品牌或竞品 dimension。此约束保证品类 = non-brand 的纯净度, 直接影响提及率默认口径的准确性 (见 §4.2.2a)

#### 4.2.2 第二层: Prompt 生成 (Topic × Intent)

**设计原则**: 同一个 Topic 在不同意图下应生成不同的自然语言问句。Intent 决定了用户"为什么问"，Prompt 是最终的问法。

**Intent 类型**:

| Intent | 含义 | 示例 (Topic: "小棕瓶 vs 小黑瓶") |
|--------|------|------|
| Informational | 了解信息 | "小棕瓶和小黑瓶的成分有什么区别？" |
| Commercial | 购买决策 | "小棕瓶和小黑瓶哪个更值得买？" |
| Transactional | 行动导向 | "哪里买小棕瓶最划算？" |
| Navigational | 寻找特定信息 | "雅诗兰黛小棕瓶官方价格" |

**Prompt 生成规则**:
- 每个 Topic 至少覆盖 2 种 Intent（informational + commercial 为必选）
- Prompt 必须是自然语言完整句子，像真人在对话框里打的问题
- 避免关键词堆砌 ("推荐 精华液 抗衰 2026 排行") ← 这是搜索引擎思维，不是 AI 对话思维
- **品类 Topic 的 Prompt 禁止引入品牌名** (2026-04-16 新增): 当 Topic.dimension='品类' 时, 生成的 Prompt 文本**不得包含任何已知品牌名** (KG 中 Brand.{nameZh, nameEn, aliases[]})。品类 Topic 下的所有 Prompt 必须保持 non-brand 纯净度, 如 "抗衰精华哪个好？" ✅ / "除了雅诗兰黛还有什么好的精华？" ❌。此约束直接影响提及率默认口径的准确性 (见 §4.2.2a)
- 支持多轮 Prompt 链: 一个 Topic 可生成 [主问题 → 追问1 → 追问2] 的对话链
- **多语言生成**: 每个 Prompt 记录 `language` 字段 (`zh-CN` / `en-US`) 和适用引擎 `appliesToEngines[]`。同一 Topic × Intent 为 ChatGPT 生成中英双版本，分别存为独立 Prompt 记录；豆包/DeepSeek 默认只生成中文版本。详见 [4.10.3 Pipeline 多语言](#4103-pipeline-多语言-prompt--engine-language)

**Prompt naturalization 实现手段 (2026-04-22 显式化 · Session 2.1)**:
- **本步骤由 LLM (火山引擎统一入口) 完成**, 不用规则模板字面拼接
- Planner 先按 Topic × Intent 产出骨架 Prompt (`promptSkeleton`, 形如 `"关于{topic}, 我想知道{intent_anchor}"`), 再调用 `naturalizePromptWithLlm(skeleton, {intent, language, topic, brandVocab})` 把骨架改写成自然句子
- **Intent 语义锚点必须保留**: informational 保留"了解/区别"类问法 / commercial 保留"值不值得买/选哪个"类问法 / transactional 保留"哪里买/怎么买"类问法 / navigational 保留"{品牌}官方/{产品}官网"类定位问法 — LLM naturalize 过程中不得把 intent 扭曲 (如把 informational 改成 commercial)
- **Topic 关键词不得被稀释**: 品类名 / 品牌名 / 产品名必须在最终 Prompt 中原样保留或用已知别名 (KG `aliases[]`) 替换, 禁止 LLM 自创新别名 (否则 Response 解析时 brand-matcher 抓不到)
- **language 遵守 §4.10.3 决策矩阵**: zh-CN prompt 用中文自然表达 (口语/书面依 Profile 决定) / en-US prompt 用英文自然表达 (仅 ChatGPT)
- CI 用 canned fixture transport 覆盖 (`backend/src/platform/planner/llm-canned-responses.ts`), live mode 走 VOLC_API_KEY


##### 4.2.2a 提及率口径与 Topic.dimension 的关系 (2026-04-16 新增)

> **设计动机**: 对于品牌/产品/竞品 dimension 的 Topic (如 "雅诗兰黛小棕瓶怎么样"), LLM 大概率会在 Response 中提及该品牌, 导致提及率虚高、失去诊断意义。提及率 KPI 默认只统计品类 dimension 的 Topic 下产生的 Query (non-brand), 保证指标真实反映 "AI 被问到品类通用问题时, 是否会主动想到我的品牌"。

**MVP 引擎宇宙锁定** (Decision #28.C1, 2026-04-22): 本节及下文所有"引擎"指代统一限定为 **3 家** — `chatgpt` / `doubao` / `deepseek-CN` (`-CN` 后缀为 Phase 2 `'deepseek-overseas'` 命名空间预留)。原 9 家草案 (含 Gemini / Perplexity / Kimi / Grok / 智谱 / Claude) 推到 Phase 2+。Planner / Adapter / DB CHECK / CSV 导出全链路对齐, 实施真相源见 ADAPTER_CONTRACT §1.1 + DATA_MODEL §2.3 + §4.10.3.A 决策矩阵。

**Topic.dimension 与 brand/non-brand 映射**:

| Topic.dimension | 品牌属性 | 纳入提及率默认口径 | 示例 Topic |
|----------------|----------|------------------|-----------|
| `品类` | **non-brand** | ✅ 是 | "精华液推荐"、"抗衰产品对比" |
| `品牌` | brand | ❌ 否 | "雅诗兰黛抗衰方案" |
| `产品` | brand | ❌ 否 | "小棕瓶评价" |
| `竞品` | brand | ❌ 否 | "兰蔻小黑瓶 vs 雅诗兰黛" |

**不新增字段**: 直接复用已有的 `Topic.dimension` 做口径过滤, 通过 Query → Prompt → Topic 的 JOIN 链路 `WHERE topic.dimension = '品类'` 筛出 non-brand Query 子集。零新字段、零冗余。

**Planner 生成约束**:
- 品类 dimension 的 Topic 应占总 Topic 数 ≥40%, 保证 non-brand Query 有足够样本量
- 品类 Topic 的 Prompt 生成模板**禁止引入品牌名**, 从源头保证品类 = non-brand 的纯净度

**对提及率 KPI 的影响** (详见 §4.4.1):
- **默认口径 (面板 KPI 卡)**: 仅统计 `topic.dimension = '品类'` 的 Query → "品类通用问题中, AI 主动想到我的概率"
- **完整口径 (品牌详情 / 导出)**: 统计全量 Query (所有 dimension) → 保留原始全口径数据, 供深度分析

**扇出示例**:
```
Topic: "小棕瓶 vs 小黑瓶"
  ├── [Informational · zh-CN] "小棕瓶和小黑瓶的主要成分和功效有什么区别？"
  ├── [Commercial    · zh-CN] "想买精华液，小棕瓶和小黑瓶选哪个性价比更高？"
  ├── [Commercial    · zh-CN] "25岁抗初老，小棕瓶和小黑瓶哪个更适合？"
  ├── [Transactional · zh-CN] "小棕瓶和小黑瓶现在哪个平台有优惠？"
  ├── [Informational · en-US] "What's the difference between Estée Lauder ANR
  │                            and Lancôme Génifique in ingredients and efficacy?"
  └── [Commercial    · en-US] "Estée Lauder ANR vs Lancôme Génifique:
                               which one is worth buying for anti-aging?"

Topic: "精华液推荐"
  ├── [Informational · zh-CN] "2026年口碑最好的精华液有哪些？"
  ├── [Commercial    · zh-CN] "预算500左右，有什么好用的精华液推荐？"
  └── [Commercial    · en-US] "Best anti-aging serums under $80 in 2026?"
```
> 英文 Prompt 仅发送给 ChatGPT；中文 Prompt 发送给全部 3 个引擎。

#### 4.2.3 第三层: Query 组装 (Prompt × Profile)

**设计原则**: 同一个 Prompt 在不同用户 Profile 下，AI 引擎的回答可能完全不同。如果只用单一"空白用户"爬取，数据有偏。Prompt × Profile 的组合才构成完整的采样空间。Query 是最终交给 Browser/API 执行的完整请求包。

**Query = Prompt + Profile 上下文**，具体包含:
- **Prompt 本体**: 自然语言问句 (来自第二层，自带 `language` 字段)
- **Persona 前缀**: Profile 中的人口统计信息注入 (如 system prompt 或对话开场白)，Persona 语言必须与 Prompt.language 一致
- **promptLanguage**: 继承自 Prompt，决定 LLM 回答的语言期望
- **browserLocale**: 浏览器 `Accept-Language` / UI locale (如 `zh-CN`, `en-US`)，影响引擎前端 UI 和个性化
- **Conversation Context**: 冷启动 vs 带上下文开场 vs 多轮追问链路
- **引擎配置**: 引擎特有设置 (如 ChatGPT custom instructions)

> `promptLanguage` 和 `browserLocale` 是独立字段。MVP 默认两者一致 (例如 zh-CN Prompt 配 zh-CN 浏览器 locale)，但保留独立性以支持 Phase 2 跨市场监测场景 (如英文 Prompt 配美国浏览器 locale)。详见 [4.10.3](#4103-pipeline-多语言-prompt--engine-language)

**Profile 池设计**:

```
Profile 维度:
├── 人口统计维度
│   ├── 性别 (男/女/未设置)
│   ├── 年龄段 (18-24 / 25-34 / 35-44 / 45+)
│   └── 地域 (一线城市/二三线/海外)
├── 行为维度
│   ├── 对话开场白 (冷启动 vs 带需求上下文)
│   │   - 冷启动: 直接发送 Prompt
│   │   - 带上下文: "我是25岁干性皮肤，" + Prompt
│   ├── 提问风格 (简短直接 vs 详细描述)
│   │   - 简短: Prompt 原文
│   │   - 详细: 在 Prompt 基础上追加个人情境描述
│   └── 追问模式 (单轮 vs 多轮对话)
│       - 单轮: 只发送一个 Prompt
│       - 多轮: 按 Prompt 链依次发送 [主问题 → 追问1 → 追问2]
└── 引擎设置维度
    ├── promptLanguage (继承自 Prompt.language: zh-CN / en-US)
    ├── browserLocale (浏览器 Accept-Language: zh-CN / en-US)
    └── 引擎内偏好设置 (如 ChatGPT 的 custom instructions)
```

**采样策略** (控制成本):
- 不是每个 Prompt 跑全部 Profile (成本爆炸)
- 每个 Prompt 从 Profile 池里随机采样 3-5 个 Profile 执行
- 采样确保统计上覆盖主要人口统计维度
- "关键" Topic 下的 Prompt 可配置更多 Profile 采样量

**扇出示例**:
```
Prompt: "想买精华液，小棕瓶和小黑瓶选哪个性价比更高？"
  ├── Query 1: [Profile: 25岁女/一线城市/冷启动]
  │     → 直接发送 Prompt 原文
  ├── Query 2: [Profile: 35岁女/二线城市/带上下文]
  │     → "我是35岁混油皮，在二线城市，" + Prompt
  └── Query 3: [Profile: 28岁男/一线城市/简短风格]
        → "小棕瓶和小黑瓶哪个性价比高？"
```

##### 4.2.3a Profile Group — 一等公民的分析维度 (2026-04-16 补)

> **设计动机**: Query 本身是基于 Profile 执行的, 所以"不同 Profile 下我的品牌表现"本就是核心分析问题。Profile 不应只沉在 Pipeline 底层, 要作为**跨面板 / 品牌详情 / Topics 全链路的一等筛选维度**出现。和"引擎筛选"并列。

**Profile Group (ProfileGroup)** = 对 Profile 池的语义化分组。单个 Profile 字段过细 (年龄 × 性别 × 地域 × 开场 × 追问 × 语言 = 数百组合), 直接做 UI filter 选项过多。MVP 预置 6-10 个命名 cohort, 后续可由 LLM 自动聚类扩展。

> **来源**: ProfileGroup 由 Admin 后台统一管理 (详见 `ADMIN_PRD_B_PIPELINE.md` B12), App 端只读消费、展示、下拉筛选。

**MVP 预置 Profile Group** (按行业可重定义):

```typescript
interface ProfileGroup {
  id: string;                        // 'pg_young_female_tier1'
  nameZh: string;                    // '一线年轻女性'
  nameEn: string;                    // 'Young Female · Tier 1 City'
  description: string;               // 用于 UI tooltip
  filterRules: {                     // Profile → Group 匹配规则
    gender?: 'F' | 'M' | 'any';
    ageBandIn?: ('18-24' | '25-34' | '35-44' | '45+')[];
    regionIn?: ('tier1' | 'tier2-3' | 'overseas')[];
    conversationModeIn?: ('single' | 'multi-turn')[];
    promptLanguageIn?: ('zh-CN' | 'en-US')[];
  };
  industryScope?: string[];          // 限定适用的行业 id (null = 全行业)
  isDefault: boolean;                // 是否为 "全部 Profile" 聚合组
}
```

**MVP 默认组** (所有行业通用):
- `all` — 全部 Profile (聚合基线, 默认选中)
- `young_female_tier1` — 一线年轻女性 (18-34, F, tier1)
- `mid_age_female_tier23` — 下沉市场中年女性 (35-44, F, tier2-3)
- `male_tier1` — 一线男性 (any age, M, tier1)
- `price_sensitive` — 价格敏感型 (含 "性价比/平替/便宜" 关键词上下文)
- `zh_chatgpt` — 中文 ChatGPT 用户 (promptLanguage=zh-CN, 适用 ChatGPT)
- `en_chatgpt` — 英文 ChatGPT 用户 (promptLanguage=en-US, 适用 ChatGPT)

**行业特化组** (在行业种子中扩展, 例: 美妆):
- `dry_skin_24_34` — 25-34 干皮女性 (contextPrefix 含"干皮")
- `anti_aging_35_44` — 35-44 抗老关注 (contextPrefix 含"抗老/细纹")

**数据模型**:

```typescript
interface AgentProfile {
  // ... 原有字段
  groupIds: string[];                // 该 Profile 命中的 ProfileGroup id 列表 (一个 Profile 可属多组)
}

interface Query {
  // ... 原有字段
  profileId: string;
  profileGroupIds: string[];         // 冗余存储, 便于后续按 group 聚合查询
}
```

**聚合语义**:
- 当 UI 选中 `profileGroup=young_female_tier1`, 后端聚合只统计 `Query.profileGroupIds ⊇ ['young_female_tier1']` 的 Response
- 聚合 SoV / 情感 / 引用份额等指标时, 分母/分子都在该 Group 的 Query 子集内计算, 避免与全量聚合混淆
- 每个 Group 需达到最小样本量 (MVP: ≥50 Queries / 30 天) 才能在 UI 显示指标, 否则显示"样本不足, 请扩大时间范围"

**生成/维护责任**:
- **Session 2**: 落地默认 ProfileGroup 清单 (seed script), 每个 Profile 在插入时计算 `groupIds`
- **Session 3**: 后端聚合 API 支持 `?profileGroups=` 参数, 指标计算纳入 cohort 视角
- **Session 4b**: 面板 / 品牌详情 / Topics 增加 Profile Group 筛选器 (见 §4.6.1a, §4.6.1b, §4.2.5)

**LLM 自动聚类 (Phase 2)**:
- 定期扫描近 30 天 Response, 按"品牌表现差异显著"自动聚类出新 Group, 人工审核入库
- 例: 发现"低价带 + 儿童用品"这个 cohort 在回答中常出现, 而现有 Group 不覆盖, 建议新增

**分析维度扩展**:
- 所有核心指标 (提及率、排名、情感) 可按 Profile 维度切分
- 例如: "你的品牌在年轻女性群体中的提及率 vs 中年男性群体"
- 这是竞品目前不提供的差异化分析能力

##### 4.2.3b Profile-Aware Prompt Rewrite (LLM) (2026-04-22 新增)

> **设计动机 (Frank 2026-04-22 澄清目标)**: "**最终 query 要和真实用户的 query 无限接近**, 他们有相似的 browser profile、user profile"。Session 2 以前的 Query 组装是**字面拼接** (`"我是35岁混油皮，" + promptBody`), 只是给 Prompt 前面贴一段 persona 描述, Prompt 本体完全不变。这样产出的 Query 像"Prompt 加 persona 前缀"的机器产物, 不像真人在对话框里打的东西。Session 2.1 起, Query Assembler 必须调用 LLM **按 Profile 改写整条 Prompt 的 style / tone / 口癖**, 而不是贴前缀。

**为什么必须 LLM rewrite 而不是 prefix 拼接**:
- 真人不会说 "我是35岁混油皮，在二线城市，想买精华液，小棕瓶和小黑瓶选哪个性价比更高？" (persona 句 + Prompt 句机器式拼起来) — 这是**机器风**
- 真人更会说 "**姐妹们我35岁混油皮在武汉, 想囤个精华, 小棕瓶和小黑瓶哪个更值得入手呀？预算500左右**" — persona 信息**嵌入**在问法里, 用口语节奏和地域口癖连起来
- gen-Z 会说 "yyds / 无限回购", 中产商务男会说 "**给我太太买精华**, 她35岁敏感肌" — 不同 Profile 的**口癖和情境切入点不同**, prefix 拼接无法表达这种差异

**Rewrite 契约 (严格边界)**:

| 维度 | 必须保留 (reward) | 禁止改变 (punish) |
|------|------------------|-------------------|
| **Intent 语义锚点** | informational/commercial/transactional/navigational 的核心诉求 | 把 informational rewrite 成 commercial |
| **Topic 关键词** | 品类名 / 品牌名 / 产品名 (或 KG `aliases[]` 内的已知别名) | 自创新别名 (会导致 brand-matcher miss) |
| **Profile 特征** | 年龄段口癖 / 地域词汇 / 性别倾向 / 价格敏感度 | 编造 Profile 里没有的信息 (如 Profile 不含 age → rewrite 不得插入年龄) |
| **Prompt language** | 遵守 §4.10.3 矩阵 (zh-CN / en-US) | 混语 (中英夹杂除非 Profile 明示 bilingual) |
| **Query 核心问句** | 问题的目标答案形态 (推荐清单 / 对比分析 / 价格查询) | 把"问问题"改成"陈述事实" (否则 LLM Response 无法对应) |

**Rewrite 流程 (Query Assembler 内嵌)**:

```
第 2 层输出: Prompt (自然化完成, 已过 §4.2.2 naturalize)
         │
第 3 层 Query 组装:
  For each (Prompt, Profile) pair sampled:
    1. 读 Profile: 性别 / 年龄段 / 地域 / 开场偏好 / 提问风格 / 语言
    2. 读 Prompt: language / intent / topic / brandVocab
    3. 调用 LLM: rewritePromptForProfile({prompt, profile})
       输出: rewrittenPromptText + rewriteConfidence ∈ [0, 1]
    4. 校验: brand-matcher 扫描 rewrittenPromptText, 确保 Topic 关键词无丢失
    5. 校验: intent-classifier 扫描, 确保 intent 不漂移
    6. 若任一校验失败 → 降级: 回退到 "persona_prefix + original_prompt" 字面拼接 (Session 2 行为),
                       并记 `rewriteFallbackReason` 写入 attempts[].rewrite_meta
    7. 校验通过 → Query.promptText = rewrittenPromptText
```

**降级路径 (必须保留)**: 当 LLM 不可用 / rewriteConfidence < 0.6 / 校验失败时, Query Assembler **降级回 Session 2 的字面拼接模式** (`personaPrefix + original_prompt`), 不阻塞 Pipeline — 保证 LLM 链路故障时系统仍能产出 Query, 只是质量从"真实用户级"退到"机器拼接级", 该 Query 标记 `rewriteFallbackReason` 供 Admin 观测。

**扇出示例 (Session 2.1 后的预期产出)**:

```
第 2 层 Prompt (Topic="小棕瓶 vs 小黑瓶", Intent=Commercial, lang=zh-CN):
  "想买精华液，小棕瓶和小黑瓶选哪个性价比更高？"

第 3 层 Query (Prompt × Profile rewrite):
  ├── Profile: {25F 一线 冷启动 简短}
  │     promptText: "小棕瓶和小黑瓶选哪个更值得入？"
  │     rewriteConfidence: 0.87
  │
  ├── Profile: {35F 二线 带上下文 详细}
  │     promptText: "**姐妹们, 我35岁混油皮在杭州, 想入精华**,
  │                  小棕瓶和小黑瓶哪个更值呀？预算500以内"
  │     rewriteConfidence: 0.91
  │
  ├── Profile: {28M 一线 冷启动 简短}
  │     promptText: "**想给我太太买精华**, 她30岁干皮,
  │                  小棕瓶和小黑瓶哪个更合适？"
  │     rewriteConfidence: 0.83
  │
  └── Profile: {40F 海外 en-US ChatGPT}
        promptText: "I'm 40, combination skin in California — which one
                     gives better value, Estée Lauder ANR or Lancôme Génifique?"
        rewriteConfidence: 0.88
```
> 关键对比: Session 2 的输出会是 "我是35岁混油皮，在二线城市，想买精华液，小棕瓶和小黑瓶选哪个性价比更高？" (拼接风), Session 2.1 后应该是"姐妹们..."版本 (真人风)。**bold 部分是 Profile 嵌入点**, 自然融入而非前缀贴皮。

**数据模型扩展** (Session 2.1 schema migration):

```typescript
interface Query {
  // ... 原有字段
  promptText: string;                     // rewrite 后的最终问句 (若降级则等于 persona_prefix + original)
  rewriteMode: 'llm' | 'fallback_prefix' | 'skeleton_only';
  rewriteConfidence?: number;             // LLM 自评, fallback 模式为 null
  rewriteFallbackReason?: string;         // 'llm_unavailable' | 'intent_drift' | 'brand_miss' | 'low_confidence'
}
```

所有字段写入 `query_executions.attempts[].rewrite_meta` JSONB 子字段 (**不建顶层列**, 遵守 CLAUDE.md 决策 #26.C1 persona_snapshot 注入 attempts 的既定路径, 避免列膨胀)。

**Session 2.1 交付后 Harness Group H 护栏**:
- H1 `planner-must-invoke-llm`: Topic/Prompt/Query 生成链路必须 import `LlmClient`, 禁止纯规则实现 (rule-based-only PR block)
- H2 `query-rewrite-must-preserve-intent`: Query Assembler 必须在 rewrite 后调 `intent-classifier` 校验, regex 扫 `rewritePromptForProfile` 调用点必须后接校验逻辑
- H3 `query-rewrite-must-preserve-brand-vocab`: 同上, rewrite 后必须调 `brand-matcher` 扫 topic 关键词, 不得丢失

#### 4.2.4 第四层: Response 采集 (Browser 执行 Query)

Browser/API 接收 Query，执行并返回 Response。详见 [4.3 AI 引擎爬取系统](#43-ai-引擎爬取系统)。

每个 Query 产生一条 Response，包含:
- 回答全文 (含格式)
- 引用来源 URL
- 产品卡片/推荐模块
- 联网搜索触发状态
- 可选: 页面截图

##### 4.2.4.A Sentiment 分类阈值与 0.5 tiebreak (2026-04-21 新增)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节阈值仅用于 Sentiment 分类算法实现, UI 面向用户仅显示 positive / negative / neutral 三类分布与百分比, 不暴露 0.45 / 0.55 的数字.

**问题背景**: Review 2026-04-21 §3 指出, LLM 情感打分输出 0-1 连续值, 当分数正好落在 0.5 时归入 positive 还是 neutral, 代码与 PRD 都没定义. 0.5 是 AI 输出的常见 tie 值, 不定规则就会产生随机漂移, SoV 时序图出现毛刺.

**强制规则**:

```
score ∈ [0.00, 0.45]  → negative
score ∈ (0.45, 0.55)  → neutral    // 闭开区间, 0.45 属 negative, 0.55 属 positive
score ∈ [0.55, 1.00]  → positive
```

**为什么是 0.45 / 0.55 而非 0.4 / 0.6 或 0.45 / 0.5**:
- 10% 的 dead zone 给 LLM 噪声留余地 (同一 Response 多次打分在 ±0.05 内浮动)
- 对称区间避免偏向, 与 MVP 行业 sentiment 分布 (正态中心 0.5 附近) 适配
- 0.5 属 neutral, 未来若 LLM 升级分数精度也不会因为"多了一个小数位"导致重分类

**实现约束** (Session 3 新增):

- `src/services/sentiment/classify.ts` 单一入口, 禁业务代码直接写 `if (score > 0.5)` 逻辑
- 函数签名 `classifySentiment(score: number): 'positive' | 'negative' | 'neutral'`
- 分布聚合必须走该函数, 不得在 SQL 里 `CASE WHEN score > 0.5 THEN 'positive'` (精度不一致)
- 单测 `sentiment-tiebreak.test.ts` (TEST_STRATEGY §9.3) 必须覆盖 [0.0, 0.45, 0.449, 0.45, 0.4501, 0.5, 0.549, 0.55, 0.5501, 0.6, 1.0] 11 个边界值

**Harness 兜底** (Session 3 追加):

```bash
grep -rnE "(sentiment|score)\s*>\s*0\.5|score\s*>=\s*0\.5[^5]" src/ --include='*.ts' --include='*.tsx'
# 任何输出 = 绕过 classifySentiment, PR block
```

**历史数据**: MVP 上线前 (Session 3 交付时) 统一回溯重算所有 `sentiment_results` 表, 更新 `label` 字段. 之后禁止修改阈值 (会造成时序断裂, 要求必须有单独回溯任务).

#### 4.2.5 Topic 管理 & Pipeline 下钻浏览

Topic 管理页 (`/topics`) 是用户理解"平台在监测什么"以及"AI 引擎具体回答了什么"的核心入口。采用四层递进下钻结构，对应 Pipeline 的四层：

**四层下钻结构**:

```
Topics 列表页
    │  点击某个 Topic
    ▼
Prompts 列表 (该 Topic 下的所有提示语)
    │  点击某个 Prompt
    ▼
Queries 列表 (该 Prompt 下的所有执行查询)
    │  点击某个 Query
    ▼
Response 详情 (AI 引擎的完整回答)
```

**第 1 层: Topics 列表**

```
┌─────────────────────────────────────────────────────────────────────┐
│  监测主题管理                                        🔍 搜索 Topic  │
│                                                                     │
│  维度筛选: [全部 ▾]  品牌: [全部 ▾]  状态: [全部 ▾]  意图: [全部 ▾] │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Topic                    维度    品牌      Prompts  最近采集    │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │ ★ 小棕瓶评价             产品    雅诗兰黛    8       2h ago    │ │
│  │   精华液对比推荐          品类    —          12       2h ago    │ │
│  │   雅诗兰黛抗衰方案        品牌    雅诗兰黛    6       2h ago    │ │
│  │   高端面霜性价比          品类    —          10       2h ago    │ │
│  │ ○ 兰蔻小黑瓶 vs 雅诗兰黛  竞品    兰蔻       4       2h ago    │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ★ = 关键 Topic (优先监测)   ○ = 普通   ◌ = 已忽略                  │
│                                                                     │
│  [+ 自定义 Topic]                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

- **展示字段**: Topic 名称、维度 (品类/品牌/产品/竞品)、关联品牌、下属 Prompt 数、最近采集时间
- **筛选**: 维度类型、品牌、状态 (关键/普通/已忽略)、**意图 (Intent)** (2026-04-16 新增, 按 Topic 下 Prompt 的 Intent 聚合筛选: 选中某 Intent 后只展示含该 Intent Prompt 的 Topic)
- **操作**: 标记关键 (★) / 忽略 (◌)、自定义 Topic (系统自动生成 Prompt)
- 系统每月自动更新 Topic 集合 (新增趋势 Topic，淘汰过时 Topic)

**第 1 层 补充: Topic × Intent 交叉矩阵 (2026-04-21 v3.2 新增, 共享 Industry Mode 组件)**

Brand Mode `/brand/topics` (`TopicsPage.jsx` 的 `TopicsView` 子视图) 在 Topics 列表上方额外挂载 `<TopicIntentMatrix>` 面板, 用作"内容策略 vs 电商策略优先级"的入口视觉:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Topic × Intent 交叉矩阵                       [● 信息] [● 商业]     │
│  同一 Topic 背后是查资料还是查购买 · 决定内容策略 vs 电商策略优先级   │
│                                                                       │
│  小棕瓶评价       ▓▓▓▓▓▓▓▓▓▓▒▒▒▒▒▒░░░░░░▓▓▓   [ 信息型 ]            │
│  精华液对比推荐   ▒▒▒▒▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░▓▓▓   [ 商业型 ]            │
│  抗衰方案         ▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒░░░░░░░░░   [ 信息型 ]            │
│  ...                                                                  │
└──────────────────────────────────────────────────────────────────────┘
```

- **数据源 (MVP mock)**: `INDUSTRY_TOPIC_HEATMAP` Top 8 (按 `mentionCount` desc), 调 `statistics.js` 的 `topicIntentBreakdown(topic)` 合成 4 Intent 百分比 (hash 稳定, 和 = 100%)
- **Phase 2 接真实数据**: 按当前主品牌 (`activeProject.primaryBrandId`) 筛 Topic 覆盖面, breakdown 改为真实 Prompt.intent 聚合计数
- **组件路径**: `frontend/src/components/topics/TopicIntentMatrix.jsx` (共享 Brand Mode `/brand/topics` 与 Industry Mode `/industry/topics`, 详见 §4.6.1g v3.2)
- **交互**: 点击任意行 → 后续可扩展为跳转第 2 层 Prompts 列表并预筛 dominant Intent (MVP 无 onClick)
- **业务价值**: 点出"小棕瓶评价"这种 Topic 信息型占比高 → 品牌决策应投内容; "精华液对比推荐"商业型占比高 → 应投电商 SoV / 推荐位。是**提及率 / SoV 裸数字无法回答**的策略分流问题
- **字段契约**: `topic.topicName` / `topic.mentionCount` (禁 `topic.title` / `topic.heat`)
- **样式 Harness (C9-1 exempt)**: 4 Intent 颜色用 `var(--color-chart-2/3/6/7)` — 非 heatmap 语境, 不触发 C9-1 热图色带专用限制
- **密度 Harness (C14)**: 面板根用 `<div className="t-card p-3 space-y-3">`, header `text-[13px]`, 行高 `py-1`, 符合 V2 分析页统一密度契约

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本小节关于组件路径 / 数据源 MVP vs Phase 2 差异的说明仅指导实施, 严禁以 i18n key / JSX 文本节点呈现给用户。面板副标题 "同一 Topic 背后是查资料还是查购买 · 决定内容策略 vs 电商策略优先级" 是用户层面的产品价值表达, 属允许。

**第 2 层: Prompts 列表 (Topic 下钻)**

点击某个 Topic 后展开或跳转到该 Topic 下的 Prompt 列表：

```
┌─────────────────────────────────────────────────────────────────────┐
│  ← 返回 Topics    小棕瓶评价                              8 Prompts │
│                                                                     │
│  Intent 筛选: [全部 ▾]                                              │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Prompt                                Intent    Queries  覆盖率 │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │ "小棕瓶精华怎么样？值得买吗"           informational   6   100%  │ │
│  │ "小棕瓶和小黑瓶哪个更值得买？"         commercial      6   100%  │ │
│  │ "雅诗兰黛小棕瓶在哪买最便宜"           transactional   3    50%  │ │
│  │ "小棕瓶精华的成分是什么"               informational   6   100%  │ │
│  │ "推荐一款抗衰精华，小棕瓶好用吗"       commercial      6   100%  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  [+ 自定义 Prompt]                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

- **展示字段**: 完整 Prompt 文本、Intent 类型、下属 Query 数、引擎覆盖率 (已采集引擎数 / 总引擎数)
- **筛选**: Intent 类型 (informational / commercial / transactional / navigational)
- **操作**: 自定义 Prompt (挂载到当前 Topic 下)

**第 3 层: Queries 列表 (Prompt 下钻)**

点击某个 Prompt 后展示该 Prompt 下所有 Query 的执行记录：

```
┌─────────────────────────────────────────────────────────────────────┐
│  ← 返回 Prompts   "小棕瓶和小黑瓶哪个更值得买？"          6 Queries │
│                                                                     │
│  引擎筛选: [全部 ▾]  Profile: [全部 ▾]                              │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ 引擎      Profile         执行时间          状态    品牌提及   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │ ChatGPT   25岁女性,一线   2026-04-15 02:30  ✓成功   3个品牌   │ │
│  │ ChatGPT   35岁女性,二线   2026-04-15 02:31  ✓成功   4个品牌   │ │
│  │ 豆包      25岁女性,一线   2026-04-15 02:35  ✓成功   2个品牌   │ │
│  │ 豆包      35岁女性,二线   2026-04-15 02:36  ✓成功   3个品牌   │ │
│  │ DeepSeek  25岁女性,一线   2026-04-15 02:40  ✓成功   5个品牌   │ │
│  │ DeepSeek  35岁女性,二线   2026-04-15 02:41  ✗失败   —         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ✓ = 成功采集  ✗ = 采集失败 (可点击查看错误原因)                     │
└─────────────────────────────────────────────────────────────────────┘
```

- **展示字段**: 引擎名、Profile (用户画像)、执行时间、状态 (成功/失败/超时)、品牌提及数 (快速预览)
- **筛选**: 引擎、Profile 画像、状态
- **失败项**: 点击可查看错误原因 (超时、反爬、解析失败等)

**第 4 层: Response 详情 (Query 下钻)**

点击某个 Query 后展示 AI 引擎返回的完整回答及结构化分析：

```
┌─────────────────────────────────────────────────────────────────────┐
│  ← 返回 Queries                                                     │
│                                                                     │
│  ChatGPT · 25岁女性,一线 · 2026-04-15 02:30                        │
│  Prompt: "小棕瓶和小黑瓶哪个更值得买？"                              │
│                                                                     │
│  ┌─ 原始回答 ──────────────────────────────────────────────────────┐ │
│  │                                                                  │ │
│  │  小棕瓶（雅诗兰黛特润修护精华）和小黑瓶（兰蔻精华肌底液）         │ │
│  │  都是非常经典的抗衰精华产品。以下从几个维度帮你对比：              │ │
│  │                                                                  │ │
│  │  **功效对比**                                                     │ │
│  │  - 小棕瓶：主打修护 + 抗氧化，适合熬夜后修复...                  │ │
│  │  - 小黑瓶：主打微生态平衡 + 肌底修护...                          │ │
│  │                                                                  │ │
│  │  **适合人群**                                                     │ │
│  │  - 小棕瓶更适合 25-35 岁、需要日常抗初老的用户                    │ │
│  │  - 小黑瓶更适合肌肤状态不稳定、需要肌底调理的用户                 │ │
│  │                                                                  │ │
│  │  **价格**                                                        │ │
│  │  - 小棕瓶 50ml 约 590 元                                        │ │
│  │  - 小黑瓶 50ml 约 560 元                                        │ │
│  │                                                                  │ │
│  │  综合来看，如果你更关注抗老修护，推荐小棕瓶；如果想改善             │ │
│  │  整体肤质，小黑瓶是更好的选择。                                   │ │
│  │                                                                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ 结构化分析 ────────────────────────────────────────────────────┐ │
│  │                                                                  │ │
│  │  品牌提及:                                                       │ │
│  │  · 雅诗兰黛  位置: #1 (首次出现)  情感: 正面 (0.78)  推荐: 是   │ │
│  │  · 兰蔻      位置: #2            情感: 正面 (0.72)  推荐: 是   │ │
│  │                                                                  │ │
│  │  产品提及:                                                       │ │
│  │  · 小棕瓶 (雅诗兰黛)  情感: 正面  关键词: 修护, 抗氧化, 抗初老  │ │
│  │  · 小黑瓶 (兰蔻)      情感: 正面  关键词: 微生态, 肌底修护      │ │
│  │                                                                  │ │
│  │  引用来源: 无外部引用                                             │ │
│  │  回答长度: 287 字                                                │ │
│  │  推荐倾向: 条件性推荐 (按需求分流，无明确偏向)                    │ │
│  │                                                                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

- **原始回答区**: 完整展示 AI 引擎的原始回答文本，保留原始格式 (Markdown 渲染)
- **结构化分析区**: 系统从回答中提取的结构化数据：
  - **品牌提及**: 提到了哪些品牌、出现位置 (顺序)、情感极性 (正面/中性/负面 + 分数)、是否被推荐
  - **产品提及**: 提到了哪些产品、所属品牌、情感、关联关键词
  - **引用来源**: 回答中引用的外部 URL 列表 (如有)
  - **元数据**: 回答长度、推荐倾向 (明确推荐某品牌 / 条件性推荐 / 无推荐)
- **跨引擎对比** (可选): 如果同一 Prompt + 同一 Profile 在多个引擎都有结果，提供"查看其他引擎的回答"快捷切换

**Topic 管理操作**:

- 用户可标记 Topic 为"关键" (★, 优先监测, 更多 Profile 采样) 或"忽略" (◌, 暂停采集)
- 用户可手动添加自定义 Topic (系统自动生成对应 Prompt)
- 用户也可直接添加自定义 Prompt (挂载到对应 Topic 下)
- 系统每月自动更新 Topic 集合 (新增趋势 Topic，淘汰过时 Topic)

#### 4.2.6 Citation 提取与归属 (2026-04-17 新增)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节列出的字段结构和算法仅用于指导实施, 严禁以 i18n key / JSX 文本节点 / PDF 文案形式呈现给最终用户。

**背景**: 在 2026-04-17 之前的版本, PRD 在 §4.3.3 `ParsedResult` 声明了 `sourceCitations: SourceCitation[]`, 但 `SourceCitation` interface 从未定义, 提取算法零描述, 数据表缺失, Brand → Citation 归属逻辑空白。这导致 **5 KPI 中的"引用份额" / PANO A 维度 / Alert `citation_source_loss` / 报告 Data Recipe `citation_source_diff`** 四处依赖全部悬空。本节补齐整条链。

##### A. 数据模型 (Prisma Schema)

```prisma
model AiCitation {
  id              String       @id @default(cuid())
  responseId      String                                    // FK → Response
  response        Response     @relation(fields: [responseId], references: [id])
  index           Int                                       // 回答内的脚注编号 (ChatGPT [1][2] / 豆包 "参考资料:" 顺序 / DeepSeek 卡片顺序)
  rawText         String?                                   // 原始文本 "[1] Allure 2024 Best Brow Pencils"
  sourceDomain    String                                    // 归一后 domain (allure.com, sephora.com)
  sourceTitle     String?                                   // 引用标题
  sourceUrl       String?                                   // 完整 URL (如可提取)
  authorityTier   Int                                       // 1-4, 见 B
  authorityConfidence Float                                 // domain 分级的置信度 0-1 (首次入库时 LLM 辅助打分)
  brandsAttributed String[]                                 // 支撑的 brandId 数组, 见 D
  productsAttributed String[]                               // 支撑的 productId 数组 (可选)
  extractedAt     DateTime     @default(now())
  engineRaw       String                                    // 哪个引擎提取的 (用于引擎差异诊断)
  @@index([responseId])
  @@index([sourceDomain])
  @@index([authorityTier])
  @@index([extractedAt])
}

model CitationDomainAuthority {                             // 域名权威等级缓存表
  domain          String       @id                          // 归一小写, 去除 www. / m. 前缀
  tier            Int                                       // 1-4
  tierSource      String                                    // 'manual' | 'llm' | 'heuristic'
  displayName     String?                                   // "Allure"
  category        String?                                   // 'beauty_media' | 'ecommerce' | 'ugc_platform' | ...
  reviewedAt      DateTime?
  confidence      Float
  @@index([tier])
}
```

**关键约束**:
- `AiCitation.sourceDomain` 必须先写入 `CitationDomainAuthority` 才能计算 Tier (降级策略: 未知 domain 默认 Tier=3, `confidence=0.3`, 标记 `tierSource='heuristic'` 待人工复核)
- `brandsAttributed` 可以为空数组 (该引用未支撑任何已知品牌, 仅作为 Tier/authority 分析保留)
- 删除 Response 级联删除 AiCitation (响应物化失效时, citation 也失效)

##### B. Authority 分级表 (配置, 非代码硬编码)

> **⚠️ 开发者约束**: 分级列表作为**数据库种子**或**管理后台可编辑配置**, 禁止硬编码到业务逻辑中。

| Tier | 说明 | 典型来源 | 默认权重 (用于 PANO A) |
|------|------|---------|---------------------|
| **Tier 1** | 品牌官方来源 | `brand.com` 官网 / 官方小红书账号 / 官方天猫旗舰店 | 1.0 |
| **Tier 2** | 权威媒体 / 专业评测 | `allure.com` / `vogue.com` / `界面美妆` / `三联生活周刊` | 0.7 |
| **Tier 3** | 垂直媒体 / KOL 内容 | `temptalia.com` / 小红书美妆博主 / B 站测评 UP | 0.4 |
| **Tier 4** | UGC / 普通用户内容 | `reddit.com/r/*` / 普通小红书笔记 / 电商评价区 | 0.15 |
| **Tier 0** | 未知 / 待审核 | 新 domain 入库时默认 | 0 (不计入 A 分) |

**Tier 1 特殊逻辑**: `brand.officialDomains[]` (见 §4.0.1a KG 模型扩展字段) 命中即自动归属该 brand 的 Tier 1, 不需要 LLM 判定; 同时 `brandsAttributed` 自动包含该 brandId。

##### C. 引擎格式差异 × 提取算法

每个引擎 Adapter (§4.3.3) 必须实现 `extractCitations(rawResponse, html): AiCitation[]` 方法。三种实现:

**ChatGPT (Web)**:
1. 正则扫描正文: `/\[(\d+)\]/g` 捕获脚注编号
2. 解析回答末尾 `"参考资料:"` / `"Sources:"` / `"References:"` 段落
3. 对每条 `[N] {title} [{url}]` 提取 `index`, `rawText`, `sourceTitle`, `sourceUrl`
4. 额外: DOM 扫 `<a class="citation-link">` 获取超链接 (ChatGPT Plus 版本有内嵌)

**豆包 (Web)**:
1. DOM 选择器: `.reference-card`, `.source-link`
2. 每卡片提取 `title` 属性 + `href` 属性 + 可见文本
3. 若段落末尾有 `"参考资料:" / "来源:"` 样式段, 做 fallback 正则提取

**DeepSeek (Web)**:
1. DOM: `.citation-tooltip` 悬浮卡片内容 (hover 时渲染, 需等 `networkIdle`)
2. `.markdown-body sup.footnote-ref` 脚注引用
3. 缺点: DeepSeek 引用格式不稳定, 适配器需带降级 (若 DOM 选择器失败, 退回 `sourceUrls` 纯 URL 列表, tier 全部标 0)

**通用后处理**:
- URL 归一化: 去除 `utm_*` / `fbclid` query params, 去除 `#` fragment, 统一 lowercase domain
- Domain 提取: 使用 `tldts` 库 (不要手写正则, 违反依赖规则)
- 去重: 同一 Response 内 (sourceDomain, sourceTitle) 重复的只保留第一条

##### D. Brand → Citation 归属算法

每条 AiCitation 执行以下三级归属, **任一命中即写入 `brandsAttributed`** (多级可累加):

```
For each citation c in response r:
  1. Official Domain Match (Tier 1 自动归属):
     IF c.sourceDomain ∈ brand.officialDomains[] for any brand b:
        brandsAttributed.add(b.id); authorityTier := 1

  2. Paragraph-Local Co-occurrence:
     FOR each brandMention m in r (from §4.2.5 parsed result):
        IF c.index 出现在 m 所在段落 (±2 行窗口) within r.rawResponse:
           brandsAttributed.add(m.brandId)

  3. Title/URL Text Match:
     IF c.sourceTitle OR c.sourceUrl contains brand.nameZh/nameEn/alias (normalized match per §4.10):
        brandsAttributed.add(b.id)
```

**冲突处理**:
- 同一 citation 被归属给 >3 个品牌 → 视为噪声 citation, 只保留 Tier 1 命中的品牌 (通常是官网引用跨品牌讨论), 其余剔除
- 所有归属关系写入时包含 `attributionReason: 'official_domain' | 'co_occurrence' | 'text_match'` (审计用, 不落 Prisma 主表, 落 Audit Log)

##### E. citation_share KPI 公式 (修正)

> **⚠️ 相对 §4.6.1a 现有版本的修正**: 2026-04-17 之前 "引用份额" 基于 "自有域名引用次数", 隐含每个品牌必须先配置 `officialDomains[]`, 但大部分新入库品牌不会立即配; 且无法解释 Tier 2/3 权威媒体引用的正面价值。

修正为基于 `brandsAttributed`:

```
citation_share(brand b, period p) =
    |{ c ∈ AiCitation : b.id ∈ c.brandsAttributed AND c.extractedAt ∈ p }|
  / |{ c ∈ AiCitation : r ∈ brand-relevant responses AND c.extractedAt ∈ p }|

其中 brand-relevant responses = 命中至少一个 b 相关 Topic (§4.2.1) 的 Response
```

**Dashboard 5 KPI 卡**: 显示 `citation_share_pct` + 环比箭头
**CSV 导出字段**: `citation_share_pct`, `citation_count`, `tier1_share_pct` (Tier 1 细分, 选填)
**PANO A 子项**: 见 F

##### F. PANO A (Authority) 分维子公式 + citation_source_loss Alert

**A 维度分解** (权重表见 B):

```
A_score(brand b) = Σ_c∈attributed_citations(b) tier_weight(c.authorityTier) × c.authorityConfidence
                 / Σ_c∈all_industry_citations tier_weight(c.authorityTier)

归一化到 [0, 100] 作为 PANO A 子分
```

**citation_source_loss Alert 检测** (§4.8.5 cross-ref):

```
对比窗口: W1 = [T-14d, T-7d], W2 = [T-7d, T-0]
对每个 brand b:
  highAuthoritySet_W1 = { c.sourceDomain : c ∈ attributedCitations(b, W1) AND c.authorityTier ∈ {1,2} }
  highAuthoritySet_W2 = { c.sourceDomain : c ∈ attributedCitations(b, W2) AND c.authorityTier ∈ {1,2} }
  lost = highAuthoritySet_W1 - highAuthoritySet_W2
  IF |lost| >= 3 AND |highAuthoritySet_W2| < |highAuthoritySet_W1| * 0.7:
    触发 P1 Alert type='citation_source_loss'
    evidence.lostDomains = lost
    evidence.window = [W1, W2]
```

**Alert payload schema** (扩展 §4.8.5):
```ts
interface CitationSourceLossEvidence {
  lostDomains: string[];           // 丢失的 Tier 1+2 domain
  retainedDomains: string[];       // 仍保留的
  windowStart: Date;
  windowEnd: Date;
  priorWindowCount: number;
  currentWindowCount: number;
  dropRatePct: number;
}
```

##### G. 与现有章节的 cross-reference

| 现有章节 | 修正说明 |
|---------|--------|
| §4.3.3 `ParsedResult.sourceCitations` | `SourceCitation` interface 改为 `AiCitation` DB 模型的 TypeScript 投影 (见本节 A) |
| §4.6.1a 5 KPI 引用份额 | 公式改用本节 E (brandsAttributed-based), 不再使用"自有域名"纯分子公式 |
| §4.7 PANO A 维度 | 权重使用本节 B Tier 表, 公式使用本节 F |
| §4.8.5 `citation_source_loss` Alert | 检测算法使用本节 F, evidence schema 使用 `CitationSourceLossEvidence` |
| §4.6.4 CSV 导出 | `citation_share_pct` 列来自本节 E; `citation_domains` 分号分隔来自 `AiCitation.sourceDomain` distinct |

##### H. Testing (L2 单测 + L3 契约, cross-ref docs/TEST_STRATEGY.md)

必测场景 (不可少):

- `extractCitations` ChatGPT 3 种格式 (纯 `[1]` / 带 URL / 引用卡片) 的 fixture 回放
- `extractCitations` 豆包 DOM 变体 (有 reference-card / 无 reference-card 只有文末段落) 的 fixture 回放
- `attributeCitation` 三级归属优先级测试 (official_domain > co_occurrence > text_match)
- URL 归一化: `utm_*` 剔除 + fragment 去除 + `www.`/`m.` 前缀去除
- `citation_share` 分母约束: 当 Response 数为 0 时返回 `null`, 不返回 0 (避免 KPI 误导)
- `citation_source_loss` Alert 不会对首次入库 (无历史窗口) 的品牌触发

---

#### 4.2.7 Citation 驱动的用户行动面 (2026-04-17 新增)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节列出的 "不做 / 只做" 类限制仅用于指导实施, 严禁以 i18n key / JSX 文本节点 / PDF 文案形式呈现给最终用户 (详见 §4.6.0a)。

**定位**: §4.2.6 解决了 "citation 从哪来 / 怎么抽 / 怎么归属"; 本节解决 "用户拿到 citation 以后能做什么"。
Frank 的核心诉求 (2026-04-17 原话): "citations 拿到以后用户可以做什么？我不期望他只能看这些 citation"。
单纯把 `TOP_CITED_DOMAINS` 堆在面板上看, 等同于把原始日志给用户——GENPANO 必须把 citation 转化为 **诊断 / 策略 / 外联 / 解构 / 模拟 / 出口** 六条行动面。

**6 条行动面总览**:

| 子节 | 行动面 | 产品形态 | 核心数据依赖 | MVP/v1.1/P2 |
|------|--------|---------|-------------|-------------|
| §4.2.7.A | **归因诊断** | 新增 Alert type + Brand Detail 概览 Authority 时序 | AiCitation.attributionMethod / authorityTier | MVP |
| §4.2.7.B | **内容策略** | Brand Detail 新增 "内容缺口" 子 Tab | 反向 query: mention-but-no-citation; page-type | MVP |
| §4.2.7.C | **外联 / PR** | "PR 候选" 列表 + CSV 导出 + KOL 评分卡 | brandsAttributed 聚合 + rising trend | MVP |
| §4.2.7.D | **竞品解构** | Brand Detail 概览 Authority Radar + 事件流 | 对手 authorityTier 分布 + SAME_GROUP 共享域 | v1.1 |
| §4.2.7.E | **模拟 / What-if** | 独立页 `/brands/:id/simulator` | Tier 表 + PANO A 公式 | v1.1 |
| §4.2.7.F | **Agent / API 出口** | 3 个 MCP 工具 + 2 个 CSV exportType 扩展 | §4.5 MCP + §4.6.4 CSV | Phase 2 |

**跨节契约一览** (本节规定, 其他节引用):

| 章节 | 本节约束 | 引用点 |
|------|---------|-------|
| §4.2.6 | 本节所有计算依赖 §4.2.6 Tier 表 + AiCitation schema, 不得在本节重新定义 | A / B / C / D / E 全部 |
| §4.6.1b 品牌详情 | 新增 "内容缺口" 子 Tab (§4.2.7.B) + 概览 Tab 插入 Authority 时序和 Radar (§4.2.7.A + D) | 见 §4.6.1b 改点 |
| §4.6.4 CSV | 新增 `pr_targets` / `content_gap` 两个 exportType (§4.2.7.C + B) | 见 §4.6.4 Tier 1 #9 / #10 |
| §4.8.5 诊断 | 新增 `citation_attribution_mismatch` Alert type (§4.2.7.A) | §4.8.5 诊断类型表 |
| §4.5.2 MCP | 新增 3 个 MCP 工具 `get_citations` / `list_pr_targets` / `simulate_authority_boost` (§4.2.7.F) | §4.5.2 工具清单 |
| §4.11 埋点 | 新增事件 #50-#56 覆盖 6 条行动面 (§4.2.7 全节) | §4.11 事件清单尾部 |

---

##### A. 归因诊断 (Attribution Diagnostics) — MVP

**产品问题**: 当品牌 PANO A 或 citation_share 低迷时, 用户无法区分 "我根本没被引用" vs "我被引用了, 但归因算法没识别出来"。

**触发条件**: 
- 某品牌在 T-14d 窗口内 `co_occurrence` 或 `text_match` 归因占比 ≥ 60% (三级归属中 official_domain 占比 < 40%)
- **AND** 该品牌 panoA 落在行业后 30%

**诊断输出**:
- **Alert type**: `citation_attribution_mismatch` (新增, 注入 §4.8.5 诊断类型枚举)
- **Severity**: P2 (非紧急, 但指向可控的结构性问题)
- **Evidence schema** (扩展 §4.2.6.F 同族):
```ts
interface CitationAttributionMismatchEvidence {
  brandId: string;
  windowStart: Date;
  windowEnd: Date;
  byMethod: {
    official_domain: { count: number; pct: number };
    co_occurrence:   { count: number; pct: number };
    text_match:      { count: number; pct: number };
  };
  possibleCauses: Array<
    | 'missing_official_domain_config'      // Brand.domains 没配全
    | 'domain_not_indexed_by_ai'            // 官域本身没有被 AI 引擎收录
    | 'alias_mismatch_in_text'              // aliases[] 覆盖不全导致 text_match 兜底
  >;
  panoAShortfall: number;                   // 与行业中位的 PANO A 差距
}
```
- **Layer 2 因果链**: "品牌官方 domain 在 `brand.domains` 已配置 {N} 个, 但 AI 回答中真正指向官方的 citation 仅占 {X}%. 要么官域内容未被 AI 索引 (假设 A), 要么 `co_occurrence` 距离判定漏掉了新子域 (假设 B). 两个假设的证据权重对比见 `evidence.byMethod`."
- **Layer 3 方向**: "补强官方 domain 在 AI 可索引渠道中的结构化可见度, 并核验 `brand.domains` 是否涵盖所有近 6 个月新增子域。" (不给执行剧本)
- **Anchor Questions**: 
  - "近 3 个月新上线的官方子域 (活动页 / 登录页 / 白皮书页) 是否已进入 `brand.domains`?"
  - "官方内容是否提供了 AI 引擎可识别的结构化元数据 (JSON-LD / OpenGraph / robots-friendly)?"
  - "Tier 2 权威媒体是否在提到本品牌时会附带官域链接?"

**品牌详情概览增量 — Authority Share 时序图**:
- 位置: §4.6.1b 概览 Tab, V/S/R/A 维度条形下方 (不新增 Tab)
- 组件: Recharts `<AreaChart>` 堆叠面积 (30/90 天), 3 层 = `official_domain` / `co_occurrence` / `text_match`, 颜色走 `var(--color-chart-series-{1,2,3})`
- X 轴日期, Y 轴百分比 0-100%
- 禁止手写 SVG (依赖规则)
- 空态: 30 天内该品牌被引用次数 < 20 → 显示 "样本不足, 数据将在累计到 20 次引用后展示", 不渲染骨架曲线
- 交互: 悬停点显示当日 `official_domain / co_occurrence / text_match` 三值 + Tooltip 提示 "归因方法定义见帮助中心 (§4.2.6.D)"

**拦截 Harness (进 pre-commit)**:
```bash
# citation_attribution_mismatch Alert 禁止出现在 citation_source_loss 同一 Response 上游 — 两者是互斥问题 (后者是"被引用丢失", 前者是"归因失败"), 合并触发会放大用户焦虑
grep -rnE "type:\s*'citation_attribution_mismatch'.*type:\s*'citation_source_loss'|type:\s*'citation_source_loss'.*type:\s*'citation_attribution_mismatch'" \
  packages/backend/src --include='*.ts'
```

---

##### B. 内容策略 (Content Gap) — MVP

**产品问题**: 用户看完 "被引用域名 Top N" 仍不知道 "我的内容在哪个主题上根本没被 AI 看见 / 看见了但被竞品抢了"。

**核心算法**: 反向查询 "mention-but-no-citation" + 页面类型聚类。

```
对每个 Topic t (scope = 当前 Project 品类):
  relevantResponses(t) = { r : r.query.topicId = t }
  attributedResponses(t, b) = { r ∈ relevantResponses(t) : ∃ c ∈ r.citations, b ∈ c.brandsAttributed }
  mentionedResponses(t, b)  = { r ∈ relevantResponses(t) : b ∈ r.mentionedBrands }

  gap_ratio(t, b) = (|mentionedResponses| - |attributedResponses|) / |mentionedResponses|

  IF gap_ratio >= 0.4 AND |mentionedResponses| >= 10:
    → 该 Topic 列入 "内容缺口" 候选
    → 获取 topCompetitorAttributionCount(t) = max_{b' ≠ b} |attributedResponses(t, b')|
    → 获取 topCitedPageTypes(t) = 对该 Topic 下所有 attributed citation 按 url path pattern 聚类
       (产品页 / 评测页 / 榜单页 / KOL 文 / 知识百科 6 种)
```

**品牌详情新子 Tab `?tab=content-gap`** (§4.6.1b 4 Tab 扩为 5 Tab):

| 区块 | 内容 |
|------|------|
| ① Topic 缺口表 | Top 20 Topic, 列: Topic 文本 / 品类 / 相关 Response 数 / 我被提及数 / 我被引用数 / Gap Ratio / Top 竞品归因数 / 主流页面类型 |
| ② 页面类型分布对比 | 水平堆叠柱状: 我 vs 行业中位 vs Top 竞品, 6 类页面占比 — 暴露"行业 Top 都引评测页, 你官网产品页一枝独秀" |
| ③ Top 可引用页面对比 | 并排双列: 左"竞品 Top 5 被引页面 (with URL + 引用次数)" vs 右"我的 Top 5 被引页面", 凸显内容质量差距 |

**UI 空态**: 若该品牌在当前 Project 品类下 mentioned_count < 100, 显示 "监控周期不足, 内容缺口数据需累计 ≥ 100 条提及" — 不渲染零值误导。

**筛选器继承**: 继承品牌详情页顶栏 time/engines/profileGroup/dimension 筛选。

**CSV 导出**: 扩展 §4.6.4 新增 CSV #9 (见本节与 §4.6.4 cross-ref)。

**交互下钻**: 点击表行 → Topics 页 `?topicId=...&filterMention=missingCitation&brandId=...`, 预填筛选。

**禁止**: 
- ❌ 本子 Tab 不生成 "建议写什么标题 / 联系哪家 KOL" 类具体剧本 (属于咨询业务, §4.8.6 边界)
- ❌ 不混入 §4.8 诊断卡片 UI 风格 (内容缺口是探索工具而非告警, UI 区分度必须保持)

---

##### C. 外联 / PR 候选 (Outreach & PR Targets) — MVP

**产品问题**: 用户需要可操作的 "对谁发稿 / 跟谁建联" 清单, 但 GENPANO 不能帮他联系——所以我们做的是 "为什么是他 + 他能带来多少权重收益" 的决策支持。

**核心算法**:

```
对行业 I 内所有 sourceDomain d:
  竞品归因集合 C(d) = { b ∈ I \ {self} : d 在 T-90d 内有 attributed citation 归给 b }
  自己归因次数 A(d) = |{ c : c.sourceDomain = d AND self ∈ c.brandsAttributed }|
  Tier(d), Confidence(d) = 查 CitationDomainAuthority (§4.2.6.B)
  trending_score(d) = (T-30d citation_count - T-60d_to_T-30d citation_count) / max(T-60d_to_T-30d citation_count, 1)

  pr_score(d) = tier_weight(d) × (|C(d)| / totalCompetitors)^0.7 
              × (1 + 0.4 × max(0, trending_score(d)))
              × (1 if A(d) = 0 else 0.3)    # 已覆盖的域降权

  按 pr_score 降序取 Top 50 → PR 候选
```

**品牌详情新子 Tab 补充区块 (§4.6.1b `?tab=content-gap` 内嵌)**:

| 区块 | 内容 |
|------|------|
| ④ PR 候选列表 | 50 行, 列: 域名 / Tier / Confidence / 覆盖我 / 覆盖竞品数 / 近 30 天引用趋势 (MiniSparkline C1/C5 合规) / 站点类型 (官方/权威媒体/KOL/UGC) / 备注 (是否是 SAME_GROUP 共享域) |
| ⑤ Tier 2 覆盖矩阵 | 行=Tier 2 域名, 列=我+竞品, 单元格=引用次数 (深色=高), 快速识别"行业 Top 被 Tier 2 全覆盖, 我缺 3 个关键域" |
| ⑥ KOL 评分卡 (仅 Tier 3) | 每张卡: KOL 账号名 + authorityConfidence + 3 个月归因品牌多样性 (Shannon entropy) + 近 30 天活跃度 (avg_citations_per_week) |

**KOL 评分卡的品牌多样性公式**:
```
diversity(kol) = -Σ_{b ∈ brandsAttributed(kol, 90d)} p_b × log(p_b),  
                 where p_b = 归因给 b 的 citation 次数 / 总 citation 次数
```
diversity 越高 = KOL 越"中立", 说服力权重越高; diversity 接近 0 = KOL 可能是某品牌的独家合作, 价值对我方有限。UI 用 0-3.0 的分数呈现。

**CSV 导出 — 新增 CSV #9 `pr_targets`** (详见 §4.6.4 改点):
字段: `domain / tier / confidence / competitors_count / competitors / attributed_to_me_count / trending_30d_pct / site_type / same_group_shared / pr_score`

**禁止**:
- ❌ 不提供 "联系方式" 字段 (违反 §4.8.6: 不给执行方案)
- ❌ 不按 "pr_score 分数高 = 必然建联成功" 口径包装——这是候选信号, 不是保证
- ❌ `pr_score` 公式里的 tier_weight / trending 基数必须从 DB / 参数服务读, 禁硬编码 (§4.2.6 同款 Tier 表契约)

---

##### D. 竞品解构 (Competitor Deconstruction) — v1.1

**产品问题**: 用户需要理解 "某竞品为什么 PANO A 比我高 20 分", 答案藏在 authority 分布和 SAME_GROUP 资源共享里。

**品牌详情概览增量 — Authority Radar**:
- 位置: §4.6.1b 概览 Tab, Authority 时序图 (§4.2.7.A) 旁边
- 形态: Recharts `<RadarChart>` 5 维度 (Tier 1 / Tier 2 / Tier 3 / Tier 4 / Tier 0), 指标=该品牌在该 Tier 的 citation 份额占其全部 citation 的比例
- 对比: 默认叠加 "行业中位" 虚线 + "主要竞品" 实线 (两种颜色)
- 空态: citation 累计 < 20 → 不渲染 radar, 显示 "数据不足"

**Same-Group 共享域比例**:
- 计算: 对每对 `Brand.groupId` 相同的品牌 (a, b), 计算 `sharedDomains(a,b) = officialDomains(a) ∩ attributedDomains(b) 或 vice versa`, 得到共享占比
- UI: Brand Detail 概览右下角小卡, 展示 "与 SAME_GROUP 兄弟品牌 {X}, 共享权威域 {N} 个, 占双方总引用 {Y}%"
- 业务含义: 揭示集团矩阵的 "共振放大" 效应 (例如欧莱雅集团下巴黎欧莱雅 / 兰蔻共享 3 个 Tier 2 评测媒体), 供用户评估 "我是单兵作战还是集团军"

**Acquisition Event Stream (新 citation 来源首次出现)**:
- 定义: 某 Tier 1 或 Tier 2 域名首次归因给品牌 b 的事件
- 展示: 品牌详情概览时间轴, 最近 30 天事件流, 每个节点 (日期 + 域名 + Tier + 来源 Response 链接)
- 用于解答 "这个月权威度上升了, 新来源是什么"

**Harness 拦截**:
```bash
# Authority Radar 禁止使用 5 维以外的 Tier 枚举 — 5 级 Tier 是 §4.2.6.B 固化, 扩展 Tier 必须先改 §4.2.6 Tier 表
grep -rnE "<RadarChart[^>]*>[\s\S]*?dataKey=.{1,30}tier[^\"']*['\"]" \
  frontend/src --include='*.jsx' | grep -vE "tier[0-4]|tier(Zero|One|Two|Three|Four)"
```

---

##### E. 模拟 / What-if (Simulator) — v1.1

**产品问题**: 用户想知道 "如果我多拿 3 个 Tier 2, PANO A 能涨多少?" —— 这是转化到咨询服务的核心心理驱动。

**独立页**: `/brands/:id/simulator?tab=authority` (tab 后续可扩 sentiment/share), MVP 仅 authority。

**输入面板**:
- 当前状态快照 (只读): 各 Tier citation 数 / PANO A 当前值 / 行业中位
- 滑杆: 
  - "假设 Tier 1 citation +{N}": 范围 [-currentTier1, +20], 默认 0
  - "假设 Tier 2 citation +{N}": 范围 [-currentTier2, +30], 默认 0
  - "假设 Tier 3 citation +{N}": 范围 [-currentTier3, +50], 默认 0
- 高级: authorityConfidence 假设值 (Tier 2 默认 0.85, 允许调 [0.5, 1.0])

**输出面板**:
- 大号 PANO A delta 数字 (当前值 → 模拟值, 带箭头)
- 等价换算: "≈ 追平行业中位需要再加 Tier 2 × {N} 个", "≈ 超越 Top 3 竞品需要再加 Tier 1 × {N} 个"
- ROI 卡: "假设一次 Tier 2 权威媒体投放 (行业基准价 ¥{basePrice}) 能换来 1 个 Tier 2 citation, 本次模拟等价投入 ≈ ¥{total}, PANO A 预计提升 {delta} 分" — `basePrice` 从行业参数表读, Admin 可编辑 (§ADMIN_PRD 参考)
- **Removal / Blocking Sim** (反向模拟): "若失去 Top 3 Tier 1 来源 (竞品撤稿 / 媒体改版), PANO A 会降至 {X}" — 揭示来源脆弱性

**核心公式复用 §4.2.6.F**:
```
simulatedPanoA = [ Σ (tier_weight × (currentTierCount + deltaTier) × authorityConfidence) ] 
                 / Σ_industry(tier_weight × baseTierCount) × 100
```

**禁止事项**:
- ❌ 不承诺 "投放后一定能拿到 citation" (这是概率分布, 非因果保证), 页面底部必须显示 "本页输出为基于 §4.2.6.B Tier 表和 §4.2.6.F PANO A 公式的机械推算, 不构成 ROI 承诺" 类提示 — 注意这是 **合规提示**, 不是开发者约束, 可写入 i18n
- ❌ 滑杆不得允许负的 currentTier+delta (即不得模拟"负 citation")
- ❌ basePrice 不得硬编码, 必须走 DB/配置表

**埋点**: `simulator_run` / `simulator_cta_click_consulting` (见 §4.11 事件 #54/#55)

---

##### F. Agent / API 出口 — Phase 2

**定位**: GENPANO 的 Agent-Native 属性要求 citation 数据必须直达 MCP / API 层, 不绑定 UI。

**MCP 工具 (新增, 注入 §4.5.2)**:

| 工具 | 签名 | 返回 |
|------|------|------|
| `get_citations` | `(brandId: string, range?: DateRange, tier?: number[], method?: AttributionMethod[])` | `AiCitation[]` (分页, max 500) |
| `list_pr_targets` | `(brandId: string, top?: number=50, excludeCovered?: boolean=true)` | 按 §4.2.7.C pr_score 排序的候选列表 |
| `simulate_authority_boost` | `(brandId: string, deltaByTier: { [tier: number]: number }, confidenceOverride?: number)` | `{ currentPanoA, simulatedPanoA, delta, basePriceEquivalent }` |

**CSV 扩展** (§4.6.4 Tier 1 新增):
- CSV #9 `pr_targets` (见 §4.2.7.C)
- CSV #10 `content_gap` (§4.2.7.B 表 ① 的导出)

**权限**:
- 所有 citation 数据仅限已登录 + Project 内主品牌 or 竞品; 未登录用户调 MCP 工具返回 401
- 跨 Project 越权 (请求不属于自己 Project 的 brandId) 返回 403

**契约**: `docs/openapi.yaml` 必须同步更新 (§4.10.4a / §4.10.4 测试策略); 严禁手写契约测试 (CLAUDE.md 决策 #18)。

---

##### G. Cross-Reference 汇总 (本节对其他章节的 reach)

| 目标章节 | 本节注入的改点 | 由谁维护 |
|---------|--------------|---------|
| §4.5.2 MCP Server | 工具清单新增 3 项 (§4.2.7.F) | Session 4b API 层 |
| §4.6.1b 品牌详情 | 概览 Tab 增 Authority 时序图 + Radar + Same-Group 共享卡 + Acquisition 时间轴; 新增 `?tab=content-gap` 子 Tab | Session 3 前端 |
| §4.6.4 CSV | Tier 1 新增 CSV #9 `pr_targets` / #10 `content_gap` | Session 3 + Session 4b |
| §4.8.5 诊断类型 | 新增 `citation_attribution_mismatch` P2 Alert type + Evidence schema | Session 3 |
| §4.11 埋点 | 新增事件 #50-#56 (attribution_mismatch_view / content_gap_view / pr_targets_view / pr_targets_export / simulator_open / simulator_run / simulator_cta_click_consulting) | Session 0 |
| §ADMIN_PRD | `basePriceByTier` 行业参数表 CRUD (simulator 用) | Session A4 Admin |

##### H. Testing (L2 单测 + L3 契约 + L4 E2E)

**必测场景**:
- §4.2.7.A: attribution mismatch 触发的 fixture (官方归因 30% / co_occurrence 50% / text_match 20% + PANO A 低) → 预期 P2 alert; 反例 (官方归因 70%) → 不触发
- §4.2.7.B: gap_ratio 计算 (|mentioned| = 30, |attributed| = 15 → 0.5, 进候选); 样本不足 (|mentioned| = 8) → 不进候选
- §4.2.7.C: `pr_score` 算出后 Top 50 列表稳定排序 (相同 score 用 domain 字典序兜底); `excludeCovered=true` 确认已归因给自己的 domain 不进列表
- §4.2.7.D: SAME_GROUP 对称性 (`sharedDomains(A,B) = sharedDomains(B,A)`)
- §4.2.7.E: simulator delta = 0 时 simulatedPanoA = currentPanoA (零假设不变性)
- §4.2.7.F: MCP `simulate_authority_boost` 跨 Project 越权 → 403; 鉴权缺失 → 401

**Visual Regression**:
- `content-gap.png` / `authority-radar.png` / `simulator.png` 加入 Playwright baseline

---

### 4.3 AI 引擎爬取系统

> **📌 实施层真相源**: 本节仅描述 **产品视角** 的爬取能力需求 (为什么 Web-First / 覆盖哪些引擎 / 账号池水位目标 / 成本边界)。
>
> **Adapter 接口形状、错误码、状态机、反检测技巧、CAPTCHA 处置、HAR 脱敏** 的实施细节全部固化在 [`docs/ADAPTER_CONTRACT.md`](./ADAPTER_CONTRACT.md)。
>
> 来源: 2025 Q1-Q2 在 `github.com/jotamotk/GenPano` 测试床跑通的 9 引擎对抗经验蒸馏而来, 每条规则都对应一次真实生产 Bug 或风控对抗。
>
> 任何 Adapter 代码 (`src/engines/adapters/**`)、Admin 采集健康看板 (ADMIN_PRD §4.2)、Session 实施 (SESSIONS §1 / §1.2, ADMIN SESSIONS A2 / A2.5) 的开发都 **必须先读 ADAPTER_CONTRACT.md 全文**。
>
> 本节保留的 §4.3.1 - §4.3.5 是产品层需求; 新增 §4.3.6 - §4.3.10 是本节向 ADAPTER_CONTRACT 的锚点索引 (不重复定义, 仅指路)。

#### 4.3.1 技术路线: Web-First (浏览器自动化)

**核心决策**: 采用 **Web 爬取** 作为主方案，API 仅作为降级备选。

**为什么必须 Web 爬取**:
- GEO 监测的核心价值是"用户在 AI 引擎中看到了什么"——Web 端才是真实用户体验
- Web 端有搜索增强 (ChatGPT browsing, Gemini Google grounding)，API 没有
- Web 端有个性化、memory、隐藏 system prompt，和 API 的 raw model 回答差异巨大
- 用户可以自己去引擎验证数据——API 数据做不到这一点
- 行业竞品 (Profound, Otterly, Geoptie) 全部使用 Web 爬取方案

**技术实现方案**:

| 引擎 | Web 爬取方案 | 账号策略 | 降级方案 (API) |
|------|-------------|---------|---------------|
| ChatGPT | 自研 Playwright | 免费账号池 (邮箱注册) | 火山引擎 API (GPT 模型) |
| DeepSeek | 自研 Playwright | 手机号注册账号池 | 火山引擎 API (DeepSeek 模型) |
| 豆包 | 自研 Playwright | 手机号注册账号池 | 火山引擎 API (豆包模型) |
| Gemini (Phase 2) | 自研 Playwright | Google 账号池 | 火山引擎 API (或 Google AI Studio) |

#### 4.3.2 自研爬取引擎架构

**为什么自研**: 爬取引擎是 GENPANO 的核心壁垒。AI 引擎爬取和普通网页爬取有本质区别——需要等待流式回答完成、处理 markdown 渲染、提取引用卡片和产品推荐模块。通用云浏览器服务做不好这些，且存在数据安全和依赖风险。

**技术栈**:
```
自研爬取引擎
├── Playwright (核心浏览器自动化)
├── playwright-extra + stealth plugin (反检测)
│   - 指纹伪装 (WebGL, Canvas, AudioContext)
│   - navigator 属性伪装
│   - WebDriver 标记隐藏
├── 代理服务 (IP 轮转，按区域分)
│   - 海外节点: 海外住宅代理 (如 Bright Data, Oxylabs 等)
│   - 中国节点: 国内住宅代理 (如 IPIDEA, 快代理等)
│   - MVP 阶段两边合计月费 <$30 即可覆盖
├── Docker 容器化部署 (双区域)
│   ├── 海外 VPS (US/JP, 2核4G, $10-20/月)
│   │   - 主节点: Backend API + DB + MCP Server
│   │   - 海外爬取 Worker: ChatGPT (Gemini Phase 2)
│   │   - 海外住宅代理 IP 轮转
│   ├── 中国 VPS (2核4G, $10-15/月)
│   │   - 纯爬取节点 (无状态 Worker)
│   │   - 中国爬取 Worker: 豆包, DeepSeek
│   │   - 国内住宅代理 IP 轮转
│   │   - 结果通过 HTTPS 推送回海外主库
│   └── Frontend: Cloudflare Pages (全球 CDN, 中国访问友好)
└── 引擎特化适配层
    - ChatGPT: 等待流式回答完成、提取 citation 链接 [海外节点]
    - DeepSeek: 处理思考过程折叠、联网搜索结果 [中国节点]
    - 豆包: 处理字节特有的 UI 组件 [中国节点]
    - Gemini (Phase 2): 处理 Google Search grounding 卡片 [海外节点]
```

**每个 AI 引擎的 Playwright 脚本核心流程**:
```
1. 从账号池获取一个可用账号
2. 启动 Playwright browser (带 stealth plugin + 代理)
3. 导航到引擎页面
4. 如需登录: 使用存储的 cookies/session 恢复登录态
   - 如果 session 过期: 执行登录流程 → 保存新 session
5. 注入 Profile 上下文 (如: 先发一条设定 persona 背景的消息)
6. 发送 Query 中的 Prompt (含 Profile 修饰后的自然语言问句)
7. 等待回答完成 (检测流式输出停止/完成标记)
8. 从 DOM 中提取:
   - 回答全文 (含格式)
   - 引用来源 URL
   - 产品卡片/推荐模块
   - 联网搜索触发状态
9. 可选: 截图保存
10. 清理: 删除对话历史 (避免污染下次查询)
11. 归还账号到账号池
```

**账号池管理**:
```
AccountPool (数据库表)
├── ChatGPT 账号 (邮箱注册，免费 tier 即可)
│   ├── 初始规模: 10-20 个
│   ├── 注册方式: 半自动 (临时邮箱 API + Playwright 注册脚本)
│   ├── 存储: 账号凭据 + cookies/session 数据
│   └── 轮转策略: 每个账号每日限 30-50 次查询
├── DeepSeek 账号 (手机号) [自动化注册]
│   ├── 初始规模: 10-20 个
│   ├── 注册方式: 全自动 (鲁班SMS接码平台 API + Playwright 注册脚本)
│   ├── 流程: 调用鲁班SMS获取虚拟号 → Playwright 填入注册 → 读取验证码 → 完成注册 → 保存 session
│   └── 成本: 约 ¥0.5-2/号
├── 豆包账号 (手机号/字节账号) [自动化注册]
│   ├── 初始规模: 10-20 个
│   ├── 注册方式: 全自动 (同 DeepSeek，鲁班SMS + Playwright)
│   └── 成本: 约 ¥0.5-2/号
└── Gemini 账号 (Phase 2)
    ├── 初始规模: 10-20 个
    └── 注册方式: 半自动 (Google 账号，同 ChatGPT)

账号状态机:
  idle → in_use → cooldown → idle
         ↘ banned → auto_replenish (触发自动注册补充)
         ↘ session_expired → re_login → idle

自动补充策略:
  - 账号池水位监控: 可用账号 < 阈值 (如 5 个) 时自动触发注册
  - CN 引擎 (豆包/DeepSeek): 全自动补充 (鲁班SMS)
  - ChatGPT: 半自动补充 (脚本注册 + 人工过 CAPTCHA 兜底)
  - 每日补充上限: 防止异常消耗
```

**账号生命周期自动化 (MVP 即实现)**:
- 登录态自动刷新: 定时 Playwright 脚本续期 cookies/session
- 健康检测: 每个账号每日一次轻量探测，自动标记异常
- 自动轮转: 基于状态机的智能调度 (冷却期、负载均衡)
- 被封自动降级: Web → API Adapter，同时触发自动补充流程
- CN 引擎自动注册补充: 账号池水位低 → 鲁班SMS接码 → Playwright 注册 → 入池
- ChatGPT 半自动补充: 脚本尝试注册，CAPTCHA 失败时告警人工介入

**接码平台集成**:
- 服务商: 鲁班SMS (lubansms.com)
- 集成方式: REST API 调用
- 支持引擎: 豆包、DeepSeek (中国手机号验证)
- 流程: 获取号码 → 触发注册 → 轮询验证码 → 释放号码
- 成本: 约 ¥0.5-2/号，月消耗预计 ¥20-50 (按每月补充 20-50 个账号计)

**MVP 基础设施成本估算** (含平台级全量采集):
- 海外 VPS (主节点 + 海外爬取, 4核8G): $20-30/月
- 中国 VPS (中国爬取节点, 2核4G): $10-15/月
- 住宅代理 (海外+国内，流量增加): $30-40/月
- 接码平台 (鲁班SMS, 扩大账号池): ¥100-200/月 (~$15-28)
- 火山引擎 LLM API (品牌/产品发现 + Topic/Prompt 生成): $10-20/月
- Frontend (Cloudflare Pages 免费 tier): $0
- 总计: $85-133/月 (含平台级全量采集成本)

#### 4.3.3 适配器架构

> **⚠️ 接口定义已迁移至** [`docs/ADAPTER_CONTRACT.md`](./ADAPTER_CONTRACT.md) **§2**。
>
> 本节只保留"为什么这样设计"的产品层叙事, 具体 TypeScript 签名不在 PRD 维护 (避免双源漂移)。

**接口全景 (产品视角)**:

- **AIEngineAdapter**: 每个 AI 引擎独立 Adapter, Web 主路径 / API 降级共享接口形状, 参数为 `ExecutableQuery + ExecutionContext`, 返回 `AIResponse` 或抛 `AdapterError`。
- **ExecutableQuery**: Pipeline 第三层产出 (Topic × Prompt × Profile), 传入 adapter 的唯一输入。
- **ExecutionContext**: Adapter 执行上下文, 绑定 BrowserProfile + AccountSnapshot + ProxySnapshot, **每次 attempt 重新构造**, 不跨 attempt 复用。
- **AIResponse**: 结构化回答, 含 `rawText` (textContent 强制) + `citations[]` (ParsedCitation, 见 §4.2.6 A) + HAR/截图/raw HTML 三件套路径 (持久化字段定义见 ADAPTER_CONTRACT §10.1)。
- **AdapterError**: 8 种离散错误码 (CF_BLOCKED / COOKIE_EXPIRED / CAPTCHA_REQUIRED / PAGE_CRASHED / PROXY_DEAD / NO_ACCOUNT_AVAILABLE / EXTRACT_EMPTY / TIMEOUT), 详见 ADAPTER_CONTRACT §6.1 错误码表。

**关键语义合同** (给产品/业务读者, 实现层约束见 ADAPTER_CONTRACT):

1. `requiresLogin=true` 且无可用账号 → **Query 置 PENDING 而非 FAILED**; 账号补充后由调度器重入 (不污染成功率看板)。
2. Adapter 只抛结构化 `AdapterError`, 调度器按错误码决定重试 / 冷却 / 告警 (见 ADAPTER_CONTRACT §6.1 表)。
3. partial Response (抽到正文但 Citation 失败) 不抛异常, `status='partial'`, 与 success 在看板分桶统计。
4. traceId 贯穿 execute → 解析 → 持久化, 所有日志 / HAR / 截图共享前缀, 便于 Admin 失败重试中心 (ADMIN_PRD §4.2.6) 定位。

#### 4.3.4 爬取执行策略

**浏览器会话管理**:
- 每次爬取创建新的浏览器 session (避免历史对话污染)
- 或者: 利用历史对话作为 profile 的一部分 (多轮对话模式)
- Session 结束后销毁，不保留浏览器状态

**反检测措施**:
- 随机化请求间隔 (5-30 秒)
- 账号轮转 (同一账号不连续使用)
- IP 轮转 (通过住宅代理服务，按区域分海外/国内)
- 浏览器指纹多样化 (playwright-extra stealth plugin)
- 模拟真实用户行为 (滚动、等待、鼠标移动)

**失败处理**:
- CAPTCHA → 跳过本次 + 切换账号/IP 重试
- 账号被限流 → 切换账号重试
- 页面结构变化 → 告警 + 降级到 API
- 引擎不可用 → 标记并跳过

**成本控制**:
- 相同 Prompt+Profile 组合 (即相同 Query) 24 小时内不重复爬取
- 非关键 Topic 下的 Prompt 降低 Profile 采样数 (1-2 个)
- 关键 Topic 下的 Prompt 增加 Profile 采样数 (3-5 个)
- 自研方案无 session 限制，成本仅为 VPS + 代理 ($40-65/月)
- 每日成本预算上限告警

#### 4.3.5 MVP 引擎实现优先级
1. **DeepSeek** (Web 爬取, 最高优先) - 反爬宽松，易于验证数据采集 pipeline
2. **豆包** (Web 爬取) - 反爬宽松，同中文引擎生态
3. **ChatGPT** (Web 爬取 + API 降级) - 全球使用量最大，反爬最难，最后实现
4. **Gemini (Phase 2)** - 推迟至 Phase 2

**开发顺序说明**: 优先实现 DeepSeek/豆包，完成数据采集 pipeline 验证，确保爬取、解析、指标计算全链路可用后，再投入资源攻克 ChatGPT 反爬难题。这样可早期验证产品价值，避免陷入最难的反爬问题中。

#### 4.3.6 错误分类 & 重试策略 (锚点 → ADAPTER_CONTRACT §6)

Adapter 层 8 种离散错误码, 每种的"账号处置 / 代理处置 / 重试策略 / 是否计入成功率 / 告警级别" 矩阵定义在 [`ADAPTER_CONTRACT.md §6.1`](./ADAPTER_CONTRACT.md#61-错误码表-权威)。本节只给读者路标, 不重复定义。

产品层关键约束 (跨文档强一致):

- **NO_ACCOUNT_AVAILABLE 不计入成功率**, Query 状态置 PENDING, 与 FAILED 分桶 (避免账号池水位波动污染引擎可用性看板)。
- **COOKIE_EXPIRED 不计入成功率** (这是账号维护问题, 非引擎本身故障)。
- **成功率分母**: `success / (success + 计入成功率的失败)`; 与 §4.6 "引擎可用性" 指标定义一致, 与 ADMIN_PRD §4.2.2 引擎健康 5 分钟物化视图口径一致。

Harness: `retry_count` 不落库 (并发写会 race), 只存 `attempts: Attempt[]` append-only 数组 (见 ADAPTER_CONTRACT §6.3, 来自原测试床真实 Bug)。

#### 4.3.7 Profile-Aware 执行 (锚点 → ADAPTER_CONTRACT §3)

Query × BrowserProfile × AccountCookies 三元组构造 ExecutionContext, 实现细节见 [`ADAPTER_CONTRACT.md §3`](./ADAPTER_CONTRACT.md#3-profile-aware-执行模型)。

产品层约束:

- **Account.segmentGroup 必须匹配 Profile.segmentGroup**, 否则调度器拒绝执行并返 `NO_ACCOUNT_AVAILABLE`。原因: 同一账号反复喂跨类目 Query 会污染引擎的个性化模型, 导致结果偏离真实用户画像。
- **BrowserProfile 必须来自 coherent preset** (`config/browser-profiles.json`), UserAgent/platform/viewport/locale 禁止随机组合 (混搭直接 CF_BLOCKED)。
- ProfileGroup 定义见 §4.2.3a, 采样时 HAR 回放测试必须传 seed 保证确定性。

#### 4.3.8 CAPTCHA 三级处置 (锚点 → ADAPTER_CONTRACT §9)

实施分级: CapSolver API (Level 1, 覆盖 Turnstile/hCaptcha/reCAPTCHA) → 视觉模型 (Level 2, 火山方舟 doubao-seed-2.0-pro 判图) → 人工轨迹模拟 (Level 3, 滑块贝塞尔曲线 + 微抖动) → P1 告警人工兜底。

完整算法与超时/配额定义见 [`ADAPTER_CONTRACT.md §9`](./ADAPTER_CONTRACT.md#9-captcha-三级解决策略)。

产品层约束:

- 三级全失败 → P1 告警到 Admin `CAPTCHA_UNSOLVED` 分组 (ADMIN_PRD §4.2.6), **不自动重试** (防止 CAPTCHA 反复触发放大代理/账号成本)。
- CapSolver 配额 20 次/账号/天, 超出 P2 告警 (成本控制)。

#### 4.3.9 观测 & 持久化 (锚点 → ADAPTER_CONTRACT §10)

每条 Response 强制持久化: rawText + rawHtmlUrl + harUrl + screenshotUrl + profileSnapshot + accountIdUsed + proxyIdUsed + attempts 数组 (每次 attempt 独立 HAR/截图)。字段定义见 [`ADAPTER_CONTRACT.md §10.1`](./ADAPTER_CONTRACT.md#101-持久化字段-response-表)。

产品层约束:

- **HAR 必须脱敏** (删除 Authorization/Cookie/Set-Cookie/refresh_token), 违规即 CI 失败 (Harness grep `tests/fixtures/scraping/`)。
- **CI 回放** 用 `page.routeFromHAR({ update: false, notFound: 'abort' })`, 整个 Adapter 层测试 < 30s, 不连真实网络 (见 SESSIONS §1 §4, TEST_STRATEGY Phase 1)。
- `engine_health_5min` 物化视图 (SQL 定义在 ADAPTER_CONTRACT §10.4) 是 ADMIN_PRD §4.2.2 引擎健康卡的唯一数据源。

#### 4.3.10 账号 Cookie 生命周期 & 自动注册 (锚点 → ADAPTER_CONTRACT §5)

账号状态机 (ACTIVE ↔ COOLDOWN 12h ↔ FROZEN ↔ BANNED) 、Cookie 保活 2h cron、EditThisCookie/HAR 两种粘贴格式、DeepSeek localStorage.userToken 特例、鲁班SMS 接码注册全流程 — 全部固化在 [`ADAPTER_CONTRACT.md §5`](./ADAPTER_CONTRACT.md#5-账号--cookie-生命周期)。

产品层约束:

- **Cookie 存储必须 KMS 加密** (`encryptedCookies: Bytes`), Admin UI 回显永远 `***`, 审计日志仅记录"粘贴"动作不记明文。
- **自动注册 MVP 仅豆包/DeepSeek**, ChatGPT/Gemini 走半自动 (脚本 + CAPTCHA 失败告警人工)。
- **账号池水位阈值** (active_count < 3 触发补充) 在 `config/account-pool.yaml`, Admin §4.2.4 只读展示, Phase 2 改为 DB 可配置。

### 4.4 分析引擎

#### 4.4.1 核心指标

**提及率 (Mention Rate)** — 穿透率口径, 默认 non-brand (2026-04-16 口径精化)
- **默认口径 (面板 KPI 卡)**: 仅统计 `topic.dimension = '品类'` 的 Query (non-brand) — 品牌被提及的 Response 数 / non-brand Query 执行总数。回答: "AI 被问到品类通用问题时, 有多大比例会**主动**想到我" — 真实认知穿透率
- **完整口径 (品牌详情 / 导出)**: 统计全量 Query (所有 dimension) — 保留原始全口径, 供深度分析和对比
- **为什么默认排除 brand Topic**: 对于品牌/产品/竞品 dimension 的 Topic, Prompt 显式含品牌名, LLM 几乎必然在 Response 中提及该品牌, 导致提及率接近 100%、失去诊断价值。只有品类 dimension (non-brand) 的 Topic 才能真实测量品牌在 AI 认知中的穿透度
- 维度: 按引擎、按时间、按 Intent 类型、按 Profile Group、按 Topic.dimension
- 面板 KPI 呈现: §4.6.1a 区块 ① 首位
- **与 SoV 的区分**: 见 §4.6.1a "口径边界"表, 两者口径不等价不可互换
- **口径过滤规则**: 见 §4.2.2a

**排名位置 (Position Score)**
- 计算方式: 品牌在推荐列表中的平均位置 (1=第一个被推荐)
- 未被提及记为 null (不纳入排名计算，但纳入提及率)

**情感分数 (Sentiment Score)**
- 范围: -1 (极负面) 到 +1 (极正面)
- **MVP 实现**: 采用规则 + 词典方案（中文 SnowNLP、英文 VADER），字段 `ai_responses.sentiment_source = 'rule'` 标记来源。LLM 增强的 Sentiment（context-aware）延至 Phase 2；届时新增 `sentiment_source = 'llm'` 分支。
- 维度: 总体情感、产品质量情感、服务情感、价格情感（Phase 2 多维度拆分）

**SoV (Share of Voice)** — 相对份额口径 (2026-04-16 口径明确化)
- 计算方式: Σ(含主品牌的 response 数) / Σ(项目内竞争集合中至少命中 1 个品牌的 response 数) **(分母为已命中任一品牌的 Response)**
- 回答: "有品牌出现的讨论里, 我占几份菜" — 竞争位置 / 相对声量
- 维度: 按引擎、按时间、按行业/品类聚合
- 面板 KPI 呈现: §4.6.1a 区块 ① 次位 (紧邻提及率)
- **与提及率的区分**: 见 §4.6.1a "口径边界"表, SoV 分母比提及率分母小, 所以 SoV 通常 > 提及率; 两者背离方向往往揭示不同的诊断路径

**推荐语境分析**
- AI 在什么条件下推荐该品牌 (价格导向、品质导向、场景导向)
- 推荐伴随的限定条件 ("如果预算充足"、"适合初学者")

**引用来源追踪**
- AI 回答引用了哪些网站/内容作为品牌信息来源
- 来源稳定性: 哪些来源被持续引用

#### 4.4.2 PANO Score 综合评分体系

PANO Score 是 GENPANO 的核心输出指标，将复杂的多维度监测数据浓缩为一个直观的 0-100 分数。用户无需理解每个子指标的含义，就能通过 PANO Score 快速判断品牌/产品在 AI 引擎中的整体表现。

**设计原则**:
- 0-100 分数，直觉化理解 (类似信用评分)
- 子维度透明可拆解，用户能理解分数来源
- 权重可配置 (不同行业/品类侧重点不同)
- 支持跨引擎综合 和 单引擎独立 两种视角
- 支持时间序列，Score 变化即 GEO 表现变化

**三级 PANO Score**:

```
┌──────────────────────────────────────────────────┐
│  Brand PANO Score (品牌级, 0-100)                  │
│  ═══════════════════════════════════════════      │
│  ┌────────────────────────────────────────┐      │
│  │ V - Visibility (可见度)     权重 30%    │      │
│  │   提及率归一化分数                      │      │
│  │   = 品牌在相关Topic中被提及比例           │      │
│  ├────────────────────────────────────────┤      │
│  │ R - Ranking (排名)         权重 25%    │      │
│  │   排名位置归一化分数                    │      │
│  │   = 被提及时在推荐列表中的位置优势       │      │
│  ├────────────────────────────────────────┤      │
│  │ S - Sentiment (情感)       权重 20%    │      │
│  │   情感正面度归一化分数                  │      │
│  │   = AI描述品牌时的正面/负面倾向          │      │
│  ├────────────────────────────────────────┤      │
│  │ C - Context (推荐语境)     权重 15%    │      │
│  │   推荐语境质量分数                      │      │
│  │   = 品牌被推荐时的场景丰富度和准确度     │      │
│  ├────────────────────────────────────────┤      │
│  │ A - Authority (引用权威)   权重 10%    │      │
│  │   引用来源质量分数 (公式: §4.2.6.F)     │      │
│  │   = Σ tier_weight × authorityConfidence │      │
│  │     (Tier 表: §4.2.6.B)                 │      │
│  └────────────────────────────────────────┘      │
│                                                  │
│  Brand PANO = V×0.30 + R×0.25 + S×0.20          │
│              + C×0.15 + A×0.10                    │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│  Product PANO Score (产品级, 0-100)                │
│  ═══════════════════════════════════════════      │
│  继承 Brand PANO 的 V/R/S/C/A 五维度             │
│  + 额外维度:                                      │
│  ├── Accuracy (信息准确度) — AI描述的产品特性/      │
│  │   价格与事实是否相符                            │
│  └── Competitiveness (竞争力) — 同品类Topic中       │
│      该产品相对竞品的推荐频率优势                   │
│                                                  │
│  Product PANO = V×0.25 + R×0.20 + S×0.15         │
│                + C×0.10 + A×0.05                  │
│                + Accuracy×0.10 + Competitiveness×0.15 │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│  Industry PANO Score (行业级, 0-100)               │
│  ═══════════════════════════════════════════      │
│  衡量品牌在行业中的AI可见度地位                     │
│  ├── Share of Voice Score — 行业内占有率排名       │
│  ├── Coverage Score — 被覆盖的行业Topic比例         │
│  └── Trend Score — 趋势方向 (上升/稳定/下降)       │
│                                                  │
│  Industry PANO = SoV×0.50 + Coverage×0.30         │
│                 + Trend×0.20                       │
└──────────────────────────────────────────────────┘
```

**子维度归一化方法**:

每个子维度原始值域不同，需归一化到 0-100:

| 子维度 | 原始值域 | 归一化逻辑 |
|--------|---------|-----------|
| Visibility | 0%-100% (提及率, **non-brand 口径**: `topic.dimension='品类'`, 见 §4.2.2a) | 直接映射: 提及率 × 100 |
| Ranking | 1-N (排名位置) | 反向映射: max(0, 100 - (avg_position - 1) × 15)，第1名=100，第7+名≈0 |
| Sentiment | -1 到 +1 | 线性映射: (sentiment + 1) / 2 × 100 |
| Context | 0-1 (语境质量评分) | LLM 评估推荐语境的丰富度和准确度，输出 0-1 |
| Authority | 0-1 (来源质量) | 官方来源占比 × 0.5 + 权威来源占比 × 0.3 + 来源多样性 × 0.2 |
| Accuracy | 0-1 (信息准确度) | LLM 对比产品配置信息与 AI 回答，评估匹配度 |
| Competitiveness | 0-1 (竞争力) | 在竞品对比 Topic 中胜出比例 |

**PANO Score 等级映射**:

| 分数范围 | 等级 | 含义 |
|---------|------|------|
| 90-100 | A+ (卓越) | 在 AI 引擎中具有强势主导地位 |
| 80-89 | A (优秀) | AI 引擎表现优秀，持续保持即可 |
| 70-79 | B (良好) | 表现不错，有明确可提升空间 |
| 60-69 | C (及格) | 基本及格，多个维度需要关注 |
| 40-59 | D (较差) | 表现落后，需要系统性优化 |
| 0-39 | F (危险) | 在 AI 引擎中几乎不可见，亟需干预 |

**跨引擎 vs 单引擎**:
- 默认展示所有引擎的综合 PANO Score
- 用户可切换查看单引擎的 PANO Score (如"只看 ChatGPT")
- 引擎间 Score 差异大时，诊断系统自动标记 (如"你在豆包上得分 85，但 ChatGPT 只有 42")

**权重配置**:
- 系统提供行业默认权重 (如消费品行业更重 Visibility, B2B 更重 Authority)
- 用户可自定义权重 (Phase 2，MVP 先用默认)

#### 4.4.3 时间序列分析
- 所有指标 (含 PANO Score) 支持按日/周/月粒度查看趋势
- 异常检测: 指标突变自动告警
- 同比/环比对比
- PANO Score 周环比变化作为报告 headline 指标

### 4.5 API & MCP Server

#### 4.5.1 RESTful API

**认证**: API Key (在用户设置中生成)

**核心端点**:

```
# 项目管理
GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/:id

# 品牌监测
GET    /api/v1/projects/:id/brands
GET    /api/v1/projects/:id/brands/:brandId/metrics
GET    /api/v1/projects/:id/brands/:brandId/mentions
GET    /api/v1/projects/:id/brands/:brandId/sentiment
GET    /api/v1/projects/:id/brands/:brandId/ranking

# 产品监测
GET    /api/v1/projects/:id/products
GET    /api/v1/projects/:id/products/:productId/metrics
GET    /api/v1/projects/:id/products/:productId/comparisons

# 行业概览
GET    /api/v1/projects/:id/industry/overview
GET    /api/v1/projects/:id/industry/share-of-voice
GET    /api/v1/projects/:id/industry/trends

# Topic & Prompt 管理 + Pipeline 下钻浏览 (详见 4.2.5)
GET    /api/v1/projects/:id/topics                          # Topic 列表 (筛选: dimension, brandId, status)
GET    /api/v1/projects/:id/topics/:topicId                 # Topic 详情
PATCH  /api/v1/projects/:id/topics/:topicId                 # 更新 Topic (标记关键/忽略, 仅传被修改字段)
POST   /api/v1/projects/:id/topics/custom                   # 自定义 Topic
GET    /api/v1/projects/:id/topics/:topicId/prompts          # Prompt 列表 (筛选: intent)
POST   /api/v1/projects/:id/topics/:topicId/prompts/custom   # 自定义 Prompt
GET    /api/v1/projects/:id/prompts/:promptId/queries        # Query 列表 (筛选: engine, profile, status)
GET    /api/v1/projects/:id/queries/:queryId/response        # Response 详情 (原始回答 + 结构化分析)

# 报告 (详见 4.7.7)
GET    /api/v1/projects/:id/reports
GET    /api/v1/projects/:id/reports/latest
GET    /api/v1/projects/:id/reports/:reportId
POST   /api/v1/projects/:id/reports/generate
GET    /api/v1/projects/:id/report-schedules
PUT    /api/v1/projects/:id/report-schedules
```

**响应格式**: JSON，支持分页，支持时间范围过滤

#### 4.5.2 MCP Server

GENPANO MCP Server 让 AI Agent (如 Claude, GPT) 可以直接查询 GEO 数据:

**MCP Tools**:

```
tools:
  - name: genpano_get_brand_visibility
    description: "获取品牌在AI引擎中的可见度指标"
    parameters:
      brand: string
      engine?: string  # 可选，指定引擎
      period?: string  # 可选，时间范围

  - name: genpano_compare_brands
    description: "对比多个品牌在AI引擎中的表现"
    parameters:
      brands: string[]
      metrics: string[]  # mention_rate, position, sentiment

  - name: genpano_get_industry_trends
    description: "获取行业GEO趋势数据"
    parameters:
      industry: string
      period?: string

  - name: genpano_get_product_ranking
    description: "获取产品在AI推荐中的排名"
    parameters:
      product: string
      category?: string

  - name: genpano_generate_report
    description: "生成品牌GEO监测报告"
    parameters:
      project_id: string
      format: "markdown" | "json"
      period?: string

  - name: genpano_get_optimization_insights
    description: "获取GEO优化建议 (Phase 2)"
    parameters:
      brand: string

  # ── Citation 行动面 MCP 工具 (§4.2.7.F, Phase 2) ────────────────────
  - name: genpano_get_citations
    description: "按品牌/时间/Tier/归因方式过滤 citation 明细 (§4.2.7.F)"
    parameters:
      brand_id: string
      range?: { start: string; end: string }  # ISO8601
      tier?: number[]                         # [0..4], 默认全量
      method?: string[]                       # ['official_domain','co_occurrence','text_match']
      page?: number                           # 分页, 单页最大 500

  - name: genpano_list_pr_targets
    description: "按 §4.2.7.C pr_score 排序的 PR 候选域名列表"
    parameters:
      brand_id: string
      top?: number                # 默认 50, 最大 200
      exclude_covered?: boolean   # 默认 true, 排除已归因给自己的域

  - name: genpano_simulate_authority_boost
    description: "模拟 Tier 增量对 PANO A 的影响 (§4.2.7.E)"
    parameters:
      brand_id: string
      delta_by_tier: object        # { "1": N, "2": N, "3": N } (支持负值但不超过现有 count)
      confidence_override?: number # [0.5, 1.0], 覆盖 authorityConfidence 假设
    returns:
      current_pano_a: number
      simulated_pano_a: number
      delta: number
      base_price_equivalent: number  # 行业参数表读出的投放等价成本
```

**MCP Resources**:

```
resources:
  - uri: genpano://projects/{id}/dashboard
    description: "项目监测概览数据"

  - uri: genpano://brands/{id}/report
    description: "品牌GEO报告"

  - uri: genpano://industry/{name}/benchmark
    description: "行业基准数据"
```

### 4.6 Dashboard (Web UI)

#### 4.6.0a Page Scope 边界约束 vs UI 可见文案 (2026-04-16 补)

> **背景**: 在 Dashboard 重构过程中出现过一类典型污染——PRD / Session Prompt 中用于约束 Claude Code "本页做什么 / 不做什么"的**开发者导向约束语句**被直接塞进 i18n 文案库, 进而以 `page_subtitle` / `hierarchy_note` / `no_dup_caption` 等字段渲染给最终用户。此类文案读起来像"产品约束说明", 不是"用户价值主张", 会严重伤害体验并暴露内部实现语言。

##### (A) 什么是 "Page Scope 边界约束" (禁 UI)

以下几类表述**只能存在于 PRD / SESSIONS / 代码注释 / Session Prompt 中**, 不得以任何形式被渲染进用户 UI (包括 `messages.*.json` 的 value、JSX 文本节点、chart tooltip、报告 PDF):

1. "本页只做 X / 只回答 X" — 开发期指引, 告诉实施者不要越界
2. "本页不做 Y / 不承担 Y / 严禁 Y" — 防止越界的禁令式表述
3. "详情请进入 XXX 页 / 请去 XXX 查看" — 架构边界说明 (应通过导航设计/空态 CTA/点击跳转自然引导, 而不是用一句话解释)
4. "🚫" / "⚠️" / "详见 PRD §X" / "详见 Session X" — 文档内引用符号/锚点
5. 任何开发者视角描述 ("Breakdown Tab 已废弃" / "4 KPI 结构替代原 xxx") — 面向读者错位

##### (B) 用户可见的 UI 文案应该写什么 (鼓励)

同一个"页面边界"的信息如果对用户有价值, 要用产品语言重写:

| 开发者约束 (仅 PRD) | 对应的用户 UI 文案 (可落库) |
|------|------|
| "面板只回答'我在行业里的位置'" | 空/不写 (默认副标题已是"市场宏观视角 · 我 vs 竞品 vs 行业", 充分) |
| "本页不做单品牌深度分析, 请进入「品牌详情」" | 在 SoV 饼图或 KPI 卡上设 "点击查看品牌详情 →" 这种**交互引导**, 而不是解释性文字 |
| "本页不做产品细节" | 不写; 在品牌详情页 "产品" Tab 中自然承载, 用户到那里自然看到 |
| "🚫 严禁渲染诊断详情" | 不写; 代码注释即可, 不呈现 |

**原则**: 页面边界靠**信息架构 + 交互跳转**表达, 不靠解释性文字。

##### (C) 必须修复的已知泄漏点 (Session 4b 执行)

以下文案是 2026-04-16 审计发现的泄漏, Session 4b 必须清理:

| 文件:行 | 字段 | 内容 | 处理 |
|------|------|------|------|
| `frontend/src/i18n/messages.js:266` | `dashboard.hierarchy_note` | "面板只回答'我在行业里的位置'. 单品牌深度分析请进入「品牌详情」, 产品细节在品牌下钻第三层." | **删除** key; 如需副标题, 用 `page_subtitle` 已有的"市场宏观视角 · 我 vs 竞品 vs 行业"即可 |
| `frontend/src/i18n/messages.js:323` | `dashboard.no_dup_caption` | "本页不做单品牌的诊断详情 / Topic 下钻 / 产品细节" | **删除** key; 面板的边界通过"区块 ④ 告警条 → 查看品牌详情"按钮自然传达 |
| 所有 JSX 注释里的 "🚫 本页不做" | — | — | 保留 (开发者注释, 不可见) |

##### (D) Harness 强制规则

1. **CI 正则拦截** (pre-commit + CI):
   ```bash
   # 扫描 messages.*.json / i18n/messages.{js,ts} 的 value 中是否出现约束表述
   grep -rnE '本页(只|不)做|只回答|不承担|详情请进入|请去.*查看|严禁|🚫|⚠️ ?(本页|本段)' \
     frontend/src/i18n --include='*.json' --include='*.js' --include='*.ts'
   # 期望: 无输出; 有输出即视为开发者约束泄漏到 UI, PR 必须修复
   ```

2. **JSX 文本节点拦截** (同一条规则):
   ```bash
   grep -rnE '>\s*(本页(只|不)做|详情请进入|请去.*查看|严禁|🚫)' \
     frontend/src --include='*.jsx' --include='*.tsx'
   # 期望: 无输出
   ```

3. **PRD / SESSIONS 写作规范**: 以后每次 PRD 新增"本页做/不做"类章节, 小节开头必须带 `> **⚠️ 开发者约束 (不作为 UI 文案)**` 脚注 (见 §4.6.1a 首行), 让 Claude Code 在读 PRD 时一眼识别"这段不搬进文案库"。

4. **PR checklist 增条** (与 §4.10.4a.D 合并):
   - [ ] 新增 i18n key 是否仅承载"用户价值/交互反馈/产品动作"? 是否避免"开发者约束式"措辞?

##### (E) 与其他章节的关系

- 与 §4.10.4a (i18n 覆盖矩阵) 协同: §4.10.4a 确保文案**完整覆盖**, 本节 §4.6.0a 确保文案**语气正确 (用户视角而非开发者视角)**
- 与 §4.7 (报告系统) 同样适用: Report Markdown / PDF 里不得出现 "本报告不做..." / "详见 Dashboard 面板" 这类导航指引文字
- 与 Session Prompt 协同: CLAUDE_CODE_SESSIONS.md 的 "🚫 本页不做" 段落是给 Claude Code 的实施指令, 实施时**必须转化**为空态 CTA / 导航按钮 / 空字段, 不是 copy-paste 到 messages.json

#### 4.6-IA-v2 Brand Mode / Industry Mode IA (2026-04-20 新增 ⭐ SUPERSEDES §4.6.1 / §4.6.1-0 / §4.6.1b 顶层结构)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"Brand Mode / Industry Mode"、"sub-view"、"topbar mode toggle"等术语仅用于指导实施; UI 文案只使用用户层面的标签 ("🎯 品牌 / 🌍 行业", 每个 sub-view 的中文名), 严禁 "本页属于 Brand Mode" / "Industry Mode 不做 X" 等开发语进入 messages.*.json 或 JSX. 参见 §4.6.0a.

**A. 背景 & 反转决策**

Plan S 抽出 `BrandPanoramaPanel` 后, `/dashboard` 与 `/brands/:id?tab=overview` 100% 视觉重合——侧栏"面板"和"品牌"变成同一菜单项; §4.6.1-0 的 Daily Digest / Action Center 双版 Spike 在用户研究后被判为"给 Dashboard 硬造内容", 不如直接废除 Dashboard 路由; 同时 `/diagnostics` (跨品牌聚合诊断), `/topics` (无品牌上下文的 Topic 树), `/knowledge-graph` (裸图谱) 都缺明确的入口逻辑, 用户实际路径是"从品牌出发深度分析" 或 "从行业出发横向比较"。

**2026-04-20 Frank 决策**: 整个 IA 收敛为**两个 Mode**:
- **🎯 Brand Mode** — 用户以**我的主品牌 / 竞品**为中心, 做深度单品牌分析与诊断
- **🌍 Industry Mode** — 用户以**行业**为中心, 做横向比较、排行、知识图谱

Mode 切换由顶栏 Stripe 风格 pill toggle 承载, 由 URL (`/brand/*` / `/industry/*`) 决定, **不落 localStorage**。所有旧的"面板 / 品牌列表 / 品牌详情 / 诊断 / 报告 / Topics / 行业全景 / 知识图谱 / 产品详情"页面按 Mode 重新归属, 不再并列于侧栏顶层。

**B. 被 SUPERSEDE 的章节与迁移去向**

| 旧 §           | 旧定位                       | 2026-04-20 后                                                      |
|-----------------|------------------------------|---------------------------------------------------------------------|
| §4.6.1          | 面板 / 品牌 / 产品 三视角    | ⛔ SUPERSEDED — 本节 §4.6-IA-v2 取代                              |
| §4.6.1-0        | Dashboard Daily Digest Spike | ⛔ SUPERSEDED — `/dashboard` 路由废除, 登录后直接进 `/brand/overview` |
| §4.6.1a         | `/dashboard` 市场宏观视角    | 内容保留, 渲染锚点迁到 `/brand/overview` (Brand Mode · 总览)        |
| §4.6.1a-drilldown | 5 KPI Drawer + Full-page  | 保留, 渲染锚点迁到 `/brand/visibility` (Brand Mode · 可见性 sub-view) |
| §4.6.1b         | `/brands/:id` 4 Tab          | Tab 展平为 Brand Mode 7 个 sub-view (总览/可见性/Topics/情感/引用/产品/竞品) |
| §4.6.1d         | `/brands/:id/products/:pid` 产品详情 | 路径改为 `/brand/products/:productId` (单 brandId 来自 BrandPicker context), 保留 SSR 独立 URL |
| §4.6.1e         | `/industries/:id` Plan S 行业视角 | 内容保留, 渲染锚点迁到 `/industry/overview` (Industry Mode · 总览) |
| `/topics` (顶层)| Topic → Prompt → Query 下钻 | 拆成两处: 单品牌 Topic 命中 → Brand Mode · Topics; 行业热度 → Industry Mode · Topics 热度 |
| `/diagnostics` (顶层, 跨品牌聚合) | 跨品牌 Alert 列表 | ⛔ 删除跨品牌聚合视图; Alert 全部进 Brand Mode · 诊断 (单品牌上下文) + 顶栏 🔔 告警铃 (跨品牌快速入口) |
| `/knowledge-graph` (顶层) | 裸知识图谱 | 迁到 Industry Mode · 知识图谱 sub-view |
| `/reports` (顶层) | 跨品牌报告列表 | 迁到 Brand Mode · 报告 sub-view (单品牌上下文; 行业级报告 Phase 2) |
| §4.1.1d E1/E2/E3/E4 | 零 Project 态四面 Empty State | ⛔ SUPERSEDED — 登录后零 Project 用户 Route Guard 强制重定向 `/onboarding` (见本节 §4.6-IA-v2.F) |

**C. 全局布局 (单 App shell)**

所有已登录页面共享同一 shell: 顶栏 + 左侧栏 + 主内容区。匿名可达仅剩 `/` Landing + `/auth` + `/register` + `/onboarding` + `/forgot`。

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Logo  [🎯 品牌 ⇌ 🌍 行业]  [时间|引擎|画像 主筛选]      🔍  🔔 [3]  👤  │  ← 顶栏
├──────────────┬──────────────────────────────────────────────────────────┤
│ [Picker]     │                                                          │
│              │                                                          │
│ ── 分析      │                                                          │
│   sub-view 1 │                主内容区 (sub-view 对应页面)              │
│   sub-view 2 │                                                          │
│   ...        │                                                          │
│              │                                                          │
│ ── 运营      │                                                          │
│   sub-view n │                                                          │
│              │                                                          │
│ [Project 行] │  ← Brand Mode 独有: 底部小灰字 "当前监测: xxx" + 齿轮     │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**C.1 顶栏 (Topbar, 全局常驻, 唯一)**

左起:
1. **Logo** — 点击跳 `/brand/overview` (已登录) / `/` (未登录)
2. **Mode Toggle** — Stripe 风格 pill: `🎯 品牌  |  🌍 行业`。点击改 URL prefix (`/brand/*` ↔ `/industry/*`), 保持当前 sub-view 等价路径 (如 `/brand/overview` ↔ `/industry/overview`)
3. **全局筛选条** — 时间范围 / 引擎多选 / 画像 (ProfileGroupFilter); Brand Mode 下额外含 "引擎对比" Segmented Control (值 = 全部 / ChatGPT / 豆包 / DeepSeek / 📊 对比模式, 后者把所有图表切到多引擎并列视图; 见 §4.6-IA-v2.E)
4. **flex 分隔**
5. **🔍 搜索** — ⌘K 打开 Command Palette (搜索品牌 / Topic / 报告 / sub-view, 导航快捷入口)
6. **🔔 告警** — 铃铛 + 未处理 count 角标。下拉展示 Top 5 未处理 Alert (跨所有监控品牌), 点击跳对应品牌的 `/brand/diagnostics?alertId=xxx`。行业级异动告警 Phase 2 加入
7. **👤 UserMenu** — 头像下拉: 账号信息 / Settings / 语言切换 / 登出 (§4.1.1e L1 入口)

**C.2 Brand Mode 侧栏 (`/brand/*` 路径生效)**

```
┌────────────────────────────┐
│ [BrandPicker ▾]            │  ← 顶部 Picker (当前 Project 的主品牌 + 竞品)
├────────────────────────────┤
│ 分析                       │
│   📊 总览                  │  /brand/overview
│   👁️ 可见性                │  /brand/visibility
│   📝 Topics                │  /brand/topics
│   💭 情感                  │  /brand/sentiment
│   🔗 引用                  │  /brand/citations
│   📦 产品                  │  /brand/products
│   ⚔️ 竞品                  │  /brand/competitors
│                            │
│ 运营                       │
│   🩺 诊断                  │  /brand/diagnostics
│   📄 报告                  │  /brand/reports
├────────────────────────────┤
│ 当前监测: 我的品牌监测  ⚙️  │  ← Project 小灰字行 (齿轮跳 Settings)
└────────────────────────────┘
```

**C.2.1 BrandPicker**

- 下拉内容: 当前 Project 的主品牌 (置顶, 徽标 ⭐) + 竞品池品牌 (3-5 个)
- 顶部搜索框, 输入即过滤
- 底部链接: **"查看所有品牌 →"** — 跳 `/brands` (品牌集市, 独立卡片 grid 页面, 保留作为广场式浏览入口; 不在 Brand Mode 侧栏路径内, 但同样位于 Brand Mode URL 空间)
- 切换 Picker 只改 URL query `?brandId=xxx`, 不改 sub-view 路径, 状态由 context 持久到 session (刷新不丢)
- 零 Project 用户进 `/brand/*` 应被 Route Guard 重定向到 `/onboarding` (见 §4.6-IA-v2.F), 不会看到 BrandPicker

**C.2.2 7 个分析 sub-view 职责**

| Sub-view       | 路径                  | 职责                                                                                     |
|----------------|-----------------------|------------------------------------------------------------------------------------------|
| 📊 总览        | `/brand/overview`     | 单品牌 5 KPI 汇总 + PanoRing + V/S/R/A 趋势 + 告警 Top 3 (对标原 §4.6.1a 内容)          |
| 👁️ 可见性      | `/brand/visibility`   | 提及率 + SoV 深度拆分 (原 §4.6.1a-drilldown Full-page 版, KPI 卡 drill 的终态)        |
| 📝 Topics      | `/brand/topics`       | 该品牌在哪些 Topic 下被命中, Topic → Prompt → Query → Response 4 层下钻                 |
| 💭 情感        | `/brand/sentiment`    | 情感分布 + 趋势 + 典型正/负面 Response 样本 + 情感归因 (什么话题让情感下跌)             |
| 🔗 引用        | `/brand/citations`    | Citation 归因 + Authority Share 时序 + 内容差距 + PR 目标 (§4.2.7 A-F 行动面集中地)    |
| 📦 产品        | `/brand/products`     | 产品 BCG 矩阵 + 列表 + 产品下钻 (点击跳 `/brand/products/:productId`, 独立 URL, SSR)    |
| ⚔️ 竞品        | `/brand/competitors`  | Authority Radar 5 维 / SoV 对比 / Same-Group 共享域 / 情感对比矩阵                       |

##### C.2.2a 👁️ 可见性 `/brand/visibility` 详细规格 (2026-04-20 深化)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"Full-page 版 KPI 下钻"等术语仅指导实施, 不得进入 i18n/JSX。

**定位**: 提及率 + SoV 这一对核心可见性 KPI 的 **Full-page 深度分析**, 对标 §4.6.1a-drilldown 的 Full-page 版但直接作为独立 sub-view 承载, 无需经 Drawer 中转。

**区块构成 (7 区)**:

| 区块 | 内容 | 图表/组件 |
|------|------|----------|
| ① Hero 双 KPI 卡 | 提及率(non-brand口径) + SoV, 每卡含: 大数字 + delta pill + MiniSparkline + 按引擎 3 柱子指标 | `KpiCard` (复用 DashboardPage 的), `MiniSparkline` |
| ② 筛选栏 | 时间(7d/30d/90d) + 引擎(多选) + 维度(品类/品牌/产品) + 意图(4 Intent) | 可伸缩筛选栏 (§4.6.1a 同规), URL 持久化 |
| ③ SoV 饼图 + 竞品象限 | 左: SoV Donut (主品牌+Top4竞品+"其他", C3 约束); 右: 竞品四象限气泡散点图 (X=SoV, Y=情感, Z=引用份额, §4.6.1c 完整规格) | Recharts `PieChart` + `ScatterChart`+`ZAxis` |
| ④ 按引擎/按 dimension 拆分 | 左: 按引擎 3 组柱图(每组含提及率+SoV双柱); 右: 按 dimension 3 组柱图 | Recharts `BarChart` grouped |
| ⑤ PANO 趋势折线 | 主品牌 + Top 3 竞品 30d PANO 趋势 (4 线), 可切时间范围 | `TrendChart` (复用) |
| ⑥ Top 10 未命中 Prompt | 近 7 天高频发出但该品牌 0 命中的 Prompt 列表 (§4.6.1a-drilldown 段 1a), 按频次 desc, 点击跳 `/brand/topics?promptId=` | TanStack Table 或简单列表 |
| ⑦ 提及位置分布 | 3 卡片 (首位/中位/末位) + 按引擎细分表 | 复用 V1 MENTION_POSITION_DATA 渲染 |

**与 BrandOverviewPage 的边界**: Overview 展示 5 KPI 宏观总览 (每个 KPI 一张卡片级别), Visibility 只聚焦提及率+SoV 两个 KPI 做深度拆分, 图表尺寸翻倍, 拆解维度更多。

**数据源**: `BRANDS`, `SOV_DATA`, `COMPETITOR_SENTIMENT_BUBBLE`, `TREND_DATA`, `MENTION_TREND_BY_ENGINE`, `MENTION_POSITION_DATA`, `ENGINES` (均为 mock.js 已有 export)。未命中 Prompt 列表从 `TOPICS` + `PROMPTS` 过滤 "该品牌 0 Response" 的 Prompt。

---

##### C.2.2b 💭 情感 `/brand/sentiment` 详细规格 (2026-04-20 深化)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节限制仅指导实施。

**定位**: 单品牌情感健康度的深度分析 — 不仅展示"情感是多少", 更回答"为什么情感这样"和"跟竞品比如何"。

**区块构成 (7 区)**:

| 区块 | 内容 | 图表/组件 |
|------|------|----------|
| ① Hero 情感大数字 + PanoRing | 左: 情感得分百分比整数(C4 约束) + delta pill + "行业中位数 {X}%"; 右: PanoRing size=120 (情感子维度可视化) | `PanoRing`, 大数字 |
| ② 情感分布饼图 + 按引擎堆叠柱 | 左: 正/中/负三色 Donut; 右: 3 引擎各自的正/中/负堆叠柱 (每柱 3 段) | `DonutChart`, Recharts `BarChart` stacked |
| ③ 情感趋势折线 | 按引擎 3 线 (各引擎情感趋势), 时间可切 7d/30d/90d | `TrendChart` |
| ④ 情感归因 — Topic 下跌驱动 | "哪些 Topic 拉低了你的情感?" — 按 Topic 的 negative response 占比 desc, 前 5 个 Topic 展示: Topic 名 + 负面 response 数 + 典型负面摘要 + "查看详情 →" 跳 `/brand/topics?topicId=` | 卡片列表, 交互跳转 |
| ⑤ 正面/负面关键词云 | 两列: 正面词 (绿色 Badge) + 负面词 (红色 Badge), 每列 Top 12, 词频越高 Badge 越大 | `Badge` tone="success/danger" |
| ⑥ 竞品情感对比矩阵 | 行=品牌(主+4竞品), 列=正面%/中性%/负面%/情感得分, 主品牌行高亮; 可按任一列排序 | TanStack Table 或 styled `<table>` |
| ⑦ 典型 Response 样本 | 按极性分组 (正面 Top 3 + 负面 Top 3), 每条含: 引擎 icon + 时间 + 摘要 + Topic 来源 + **点击跳 `/brand/topics?responseId=`** | 卡片列表, 可交互 |

**数据源**: `SENTIMENT_DISTRIBUTION`, `SENTIMENT_TREND_BY_ENGINE`, `SENTIMENT_KEYWORDS`, `SENTIMENT_DETAIL_LIST`, `COMPETITOR_SENTIMENT_BUBBLE`, `BRANDS`, `TOPICS` (均已有或可从 mock 过滤派生)。新增 mock: `SENTIMENT_ATTRIBUTION_TOPICS` (Top 5 负面归因 Topic, 含 topicId/topicName/negativeCount/totalCount/sampleSnippet)。

---

##### C.2.2c ⚔️ 竞品 `/brand/competitors` 详细规格 (2026-04-20 深化)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节限制仅指导实施。

**定位**: 以"我 vs 竞品"为轴心的多维对比分析, 回答"竞品在哪些维度领先/落后我"。

**区块构成 (7 区)**:

| 区块 | 内容 | 图表/组件 |
|------|------|----------|
| ① SoV×情感 四象限气泡图 | X=SoV%, Y=情感, Z(气泡大小)=引用份额; 主品牌 accent 色+黑描边, 竞品灰阶; 四象限标签 (领跑者/追赶者/高光品牌/警示品牌); Hover tooltip; 点击跳对应品牌 `/brand/overview?brandId=` | Recharts `ScatterChart` + `ZAxis` (§4.6.1c 完整规格) |
| ② Authority Radar 5 维雷达图 | 5 维: 官方引用/权威媒体/KOL/UGC/来源多样性; 主品牌 accent 线, 各竞品灰线; Legend 列出所有品牌 | Recharts `RadarChart` + `PolarGrid` + `PolarAngleAxis` |
| ③ 多维对比表 | 行=品牌(主+4竞品), 列=PANO/SoV/情感/引用份额/行业排名/提及率; 主品牌行高亮 bg-themed-accent-soft; 可按任一列排序; 各列数据色阶 (高=绿, 低=红) | TanStack Table 或 styled `<table>` |
| ④ 竞品 PANO 趋势对比 | 主品牌 + Top 4 竞品 30d PANO 折线, 5 条线同图 | `TrendChart` 5 series |
| ⑤ SoV 对比柱图 | 水平柱 (§4.6.1a 同规), 主品牌 accent 色, 竞品灰, 数值标签; monochrome + showLabels (C2 约束) | `HorizontalBar` |
| ⑥ Same-Group 共享域 | 同集团品牌共享的权威引用域名列表 (域名 + Tier badge + 覆盖品牌 pills) | 卡片列表 (保留 V2 现有结构, 已足够) |
| ⑦ Acquisition 事件时间轴 (v1.1) | 行业内品牌收购/合并事件时间轴 (事件名 + 品牌 + 日期 + 影响摘要); MVP 用 mock, v1.1 自动挖掘 | 垂直时间轴卡片 |

**数据源**: `BRANDS`, `SOV_DATA`, `COMPETITOR_SENTIMENT_BUBBLE`, `AUTHORITY_RADAR_DATA`, `SAME_GROUP_SHARED`, `ACQUISITION_EVENTS`, `TREND_DATA` (均已在 mock.js)。

---

##### C.2.2d 🔗 引用 `/brand/citations` 详细规格 (2026-04-20 深化)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节限制仅指导实施。§4.2.6 + §4.2.7 是 Citation 的权威规格, 本节为 UI 渲染层规格补充。

**定位**: Citation 全链路行动面的集中呈现 — 从"引用了什么"到"应该争取什么引用"。

**Sub-tab 结构 (4 个, 通过 `?sub=` 切换)**:

| Sub-tab | 内容 | 组件 |
|---------|------|------|
| **概览** (默认) | ① Authority Share 时序图 (主品牌+竞品均值, §4.2.7.A) ② 来源组成饼图 (Tier 0-4 分布, §4.2.6.B) ③ Top 8 引用域名 (域名+Tier badge+计数) ④ Top 6 引用页面 (标题+URL+计数+Tier) ⑤ **引用趋势按引擎** (3 线折线, 新增) | `TrendChart`, `DonutChart`, 列表 |
| **内容差距** | ① Topic 级"被提及但未被引用"缺口表 (Topic名 + mentioned次数 - attributed次数 = gap, 按 gap desc) ② 页面类型分布对比 (我 vs 竞品: 官方/媒体/KOL/UGC 占比堆叠柱) ③ Top 可引用页面对比 (竞品有引用但我没有的页面) | `ContentGapPanel` (复用 V1 组件), Recharts `BarChart` stacked |
| **PR 目标** | ① PR 候选列表 (域名+Tier+pr_score+竞品覆盖度+是否已覆盖, §4.2.7.C) ② Tier 2 覆盖矩阵 (行=域名, 列=品牌, 单元格=✓/—) ③ KOL 评分卡 (KOL 名+平台+粉丝+覆盖品牌+Shannon entropy 多样性分) ④ 导出 CSV 按钮 (CSV #9 pr_targets) | `PrTargetsPanel` (复用 V1 组件), TanStack Table |
| **模拟器** | ① Tier delta 滑杆 (用户拖动 Tier 1-4 各增减 N 个引用, 实时预览 PANO A 变化) ② 预设场景按钮 (如"获得 3 个 Tier 2 媒体引用"→ 滑杆自动设值) ③ 预估 PANO A 变化值 + 排名预估变化 ④ CTA "需要专业帮助实现这个目标? → 咨询服务" | Radix UI Slider × 4, 实时计算, `LeadFormModal` CTA |

**数据源**: `AUTHORITY_SHARE_SERIES`, `CITATION_SOURCE_COMPOSITION`, `TOP_CITED_DOMAINS`, `TOP_CITED_PAGES`, `CITATION_TREND_BY_ENGINE`, `PR_TARGETS`, `TIER2_COVERAGE_MATRIX`, `KOL_SCORECARDS`, `CONTENT_GAP_TOPICS`, `CONTENT_GAP_PAGE_TYPE_DISTRIBUTION`, `SIMULATOR_BASELINE`, `SIMULATOR_PRESETS` (§4.2.7 mock 清单已在 CLAUDE.md 定义的 13 个 export)。

---

##### C.2.2e 📦 产品 `/brand/products` 详细规格 (2026-04-20 深化)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节限制仅指导实施。

**定位**: 品牌旗下产品组合的视觉化分析, 回答"哪些产品在 AI 引擎里表现好/差"。

**区块构成 (4 区)**:

| 区块 | 内容 | 图表/组件 |
|------|------|----------|
| ① BCG 气泡矩阵 (真可视化) | X=产品 SoV, Y=近 30d SoV 环比增长率, Z(气泡大小)=产品提及绝对次数; 四象限背景色浅标: 明星(右上绿)/金牛(右下蓝)/问题(左上黄)/瘦狗(左下灰); 气泡标签=产品名; Hover tooltip; 点击跳 `/brand/products/:productId` | Recharts `ScatterChart` + `ZAxis` + 象限背景 `ReferenceArea` |
| ② 产品趋势 sparkline 区 | 全产品 grid, 每格: 产品名 + SoV 大数字 + MiniSparkline 近 30d + delta pill; 按 SoV desc 排列 | `MiniSparkline`, grid 布局 |
| ③ 产品列表表格 | 列: 产品名/品类/提及率/SoV/情感/引用次数/30d趋势/排名; 可按任一列排序; MiniSparkline 列内嵌; 行点击跳产品详情 | TanStack Table |
| ④ 产品关系快照 | 当前品牌产品间的关系边可视化 (COMPETES_WITH/SUBSTITUTES/PAIRS_WITH/UPGRADES_TO/BUDGET_ALT_OF), 简化力导向图 (≤15 节点) | D3 force simulation 或 AntV G6 mini (复用 KnowledgeGraphPage 技术) |

**数据源**: `PRODUCTS` (按 brandId 过滤), `BRANDS`; BCG 象限分类逻辑: `mentionRate >= 0.15 && trend >= 0` = 明星, 其余三象限类推 (保留 V2 现有逻辑, 用于气泡图的四象限定位); 产品关系从 mock 新增 `PRODUCT_RELATIONS` (product_a_id, product_b_id, type)。

---

**C.2.3 2 个运营 sub-view 职责**

| Sub-view     | 路径                | 职责                                                                                |
|--------------|---------------------|-------------------------------------------------------------------------------------|
| 🩺 诊断      | `/brand/diagnostics` | 当前 BrandPicker 品牌的 Alert 列表 + 洞察 Stack (L1/L2/L3) + 分享 PDF              |
| 📄 报告      | `/brand/reports`    | 体检 PDF / 线索报告 / CSV 导出中心 (单品牌上下文)                                   |

**C.3 Industry Mode 侧栏 (`/industry/*` 路径生效)**

```
┌────────────────────────────┐
│ [IndustryPicker ▾]         │  ← 顶部 Picker (用户已订阅行业)
├────────────────────────────┤
│ 分析                       │
│   🌍 总览                  │  /industry/overview
│   🏆 排行榜                │  /industry/ranking
│   🔥 Topics 热度           │  /industry/topics
│   🕸️ 知识图谱              │  /industry/knowledge-graph
├────────────────────────────┤
│ "想追踪行业里的某个品牌？" │
│ "切到品牌模式 →"           │  ← 引导回 Brand Mode 的小灰字 + 链接
└────────────────────────────┘
```

**C.3.1 IndustryPicker**

- 下拉内容: 用户已订阅的行业 (MVP 默认 4 个: 美妆个护 / 奢侈品 / 食品饮料 / 服装时尚); 若用户只订阅了 1 个则直接显示名称, 下拉仍可打开查看 "添加行业订阅" 入口
- 底部链接: **"添加行业订阅 →"** — 跳 Settings 的 Industry 订阅管理 Section (Phase 2 可能拆独立页)

**C.3.2 4 个 sub-view 职责**

| Sub-view          | 路径                        | 职责                                                                           |
|-------------------|-----------------------------|--------------------------------------------------------------------------------|
| 🌍 总览           | `/industry/overview`        | Plan S 面板 (IQR 箱线 + 行业分布 + 核心指标均值 + 异动告警条; 原 §4.6.1e 内容) |
| 🏆 排行榜         | `/industry/ranking`         | Top 10 by PANO / SoV / 引用 / 情感, 多 Tab 切换; 可点品牌名跳 Brand Mode      |
| 🔥 Topics 热度    | `/industry/topics`          | 行业级 Topic 热度图 + 新兴 Topic 雷达 (非单品牌, 是行业横向视角)              |
| 🕸️ 知识图谱       | `/industry/knowledge-graph` | AntV G6, 行业 → 品类 → 品牌 → 产品 4 层; 关系边过滤 (迁自原 `/knowledge-graph`) |

**D. URL 结构 (权威清单)**

```
# 匿名可达
/                                              Landing
/auth, /login, /register, /forgot              §4.1.1-form
/onboarding                                    零 Project 态强制重定向目的地 (§4.6-IA-v2.F)

# 已登录 (Route Guard 拦截未登录)
/brand/overview                                Brand Mode · 总览 (登录后默认着陆)
/brand/visibility
/brand/topics
/brand/sentiment
/brand/citations                               含 ?sub=content-gap / ?sub=pr-targets / ?sub=simulator 查询参数
/brand/products                                列表
/brand/products/:productId                     产品详情 (SSR, 独立 URL; 保留原 §4.6.1d 能力)
/brand/competitors
/brand/diagnostics                             含 ?alertId=xxx 定位
/brand/reports

/industry/overview
/industry/ranking
/industry/topics
/industry/knowledge-graph

/brands                                        品牌集市 grid (BrandPicker "查看所有品牌" 出口, 保留独立页)
/settings                                      账号 / 语言 / Project 偏好 / MCP Token / Industry 订阅管理

# 已废除 (pre-existing URL, 2026-04-20 后触发 301 redirect 或 404)
/dashboard                → 301 /brand/overview
/brands/:id               → 301 /brand/overview?brandId=:id  (若当前用户有此品牌监控; 否则 /brands?highlight=:id)
/brands/:id/products/:pid → 301 /brand/products/:pid?brandId=:id
/brands/:id/simulator     → 301 /brand/citations?sub=simulator&brandId=:id
/topics                   → 301 /brand/topics
/industry                 → 301 /industry/overview
/industries/:id           → 301 /industry/overview?industryId=:id
/knowledge-graph          → 301 /industry/knowledge-graph
/diagnostics              → 301 /brand/diagnostics (跨品牌聚合能力废除)
/reports                  → 301 /brand/reports
```

**当前品牌/行业选择的状态管理**:
- Brand Mode: 当前 brandId 由 URL `?brandId=xxx` 携带, 无参数时 fallback 到 Project.primaryBrandId; BrandPicker 切换品牌重写 URL, sub-view 路径不变
- Industry Mode: 当前 industryId 同理, fallback 到用户订阅列表首个

**E. Engine 对比作为 Filter (不是 Sub-view)**

§4.6.1b 原"引擎对比" Tab 被**删除**, 改为 Brand Mode 全局筛选条里的 Segmented Control:

```
引擎: [全部]  [ChatGPT]  [豆包]  [DeepSeek]  [📊 对比模式]
```

- 前 4 个为**单引擎过滤**, 所有图表按选中引擎重算
- "📊 对比模式" 是**视图变换 (view transform)**:
  - SoV 饼图 → 三饼图并排
  - 趋势折线 → 三条线同图 (颜色 = 各引擎 token)
  - KPI 数字卡 → 三列 (ChatGPT / 豆包 / DeepSeek, 每列一个值)
  - 未命中某引擎的指标显示 `—` 占位
- 对比模式是 UI 渲染模式, 不改数据获取逻辑 (始终拉全部引擎数据, 切换只影响渲染)
- 不新增 `?compareEngines=1` 持久化; 刷新丢失也可, 因为对比模式是轻量探索不是持续状态
- Industry Mode 无引擎对比 (行业级数据本来就按引擎聚合, 对比价值低)

**F. 零 Project 态处理 (取代 §4.1.1d E1/E2/E3/E4)**

登录后 Route Guard 检查 `User.projects.length`:
- `0` → 强制重定向 `/onboarding`, **不让用户看到空 App shell**
- `≥1` → 正常渲染 Brand Mode, 默认进 `/brand/overview?brandId=<primaryBrandId>`

`/onboarding` 是**独立页面** (与 Brand Mode shell 分离, 无侧栏, 无 Mode Toggle, 只有顶栏 Logo + UserMenu), 4 步:

1. **选行业** — 卡片选择 (MVP 4 个行业)
2. **选主品牌** — 从该行业品牌库搜索 + 自填 (未入库品牌走用户共建流程, 见 §4.1.2)
3. **选 3-5 个竞品** — 知识图谱智能推荐 + 用户自选
4. **偏好设置** — 首选引擎 / 语言 / 告警频率

完成后写入 Project → 重定向 `/brand/overview?brandId=<主品牌 id>`。中途退出存草稿 (`draftProject` 字段, 72h 过期), 下次登录 Route Guard 检查到草稿也重定向 `/onboarding` 续上。

**被废除的 Empty State**:
- E1 (Dashboard Empty) ⛔ — `/dashboard` 路由本身废除
- E2 (Sidebar Empty) ⛔ — Route Guard 重定向后用户看不到侧栏
- E3 (Landing Nav Quick Create) ⛔ — Landing 只面向匿名用户, 已登录进不到 Landing
- E4 (Gated Banner) ⛔ — 无 Gated 场景, 有 Project 才能进 Brand Mode

**保留的转化入口**:
- Landing 的 "注册" / "登录" 按钮 (匿名用户)
- Onboarding 页本身就是转化路径
- Settings 里 "+ 新建项目" (Phase 2 多 Project)

**G. Project 在 MVP UI 里的"隐身处理"**

MVP 阶段每个用户只有 1 个 Project (primaryBrand + competitors), **Project 概念在 UI 里不是一等公民**:

- **侧栏无 ProjectPicker** (取代原 §4.1.1d E2 底部 ProjectSelector 下拉)
- **顶栏无 Project 名** (Stripe Test/Live toggle 的位置让给 Mode Toggle)
- **Brand Mode 侧栏底部**一行小灰字: `当前监测: 我的品牌监测  ⚙️`, 齿轮跳 `/settings#project`
- **Settings 页**包含 "Project 设置" Section: 改主品牌 / 增删竞品 / 改偏好 (原 `/project-settings` 独立页并入 Settings, 页面路径保留为 `/settings?section=project` 或 hash `#project`)
- **Phase 2 扩展**: 当多 Project 功能上线 (如"我是 Agency, 同时监测雅诗兰黛 + 兰蔻两个客户"), 侧栏底部"单行 Project 信息"升级为 ProjectSwitcher 下拉, Settings 内从一个 Section 升级为独立 Projects 页; URL 增加 `/brand/overview?projectId=xxx&brandId=yyy` 语义

**为什么不在 MVP 暴露 ProjectPicker**:
- MVP solo-user 一个 Project 一个主品牌, ProjectPicker 和 BrandPicker 视觉嵌套会让用户混淆 (Frank 本人就在 2026-04-20 讨论里明确表达过困惑)
- 隐藏 Project 让用户心智模型简化为: "登录 → 切换要看的品牌 → 看数据", Project 在路径上完全透明
- Phase 2 多 Project 用户出现时再显式暴露, 不损失扩展性 (URL 空间和 Context 结构均已预留 projectId)

**H. Harness 拦截规则**

```bash
# (H1) 禁止新代码继续引用已废除路由 (301 重定向是 Route Guard 的事, 代码里不应再 navigate 过去)
grep -rnE "navigate\(['\"](\/dashboard|\/topics|\/industry|\/industries\/|\/knowledge-graph|\/diagnostics|\/reports)['\"]?\)" \
  frontend/src --include='*.jsx' --include='*.tsx' --include='*.js' --include='*.ts'
# 期望: 无输出 (所有 navigate 必须用新 /brand/* /industry/* 路径)

# (H2) 侧栏组件禁止再渲染 ProjectSelector 组件 (MVP 隐身)
grep -rnE "<ProjectSelector" frontend/src --include='*.jsx' | grep -v "SettingsPage"
# 期望: 无输出

# (H3) Mode Toggle 必须由 URL 决定, 禁止 localStorage 持久化
grep -rnE "localStorage.*mode|mode.*localStorage" frontend/src --include='*.jsx' --include='*.ts'
# 期望: 无输出

# (H4) 禁止 i18n / JSX 出现 "Brand Mode" / "Industry Mode" 开发语
grep -rnE "(Brand Mode|Industry Mode|sub-view|mode toggle)" \
  frontend/src/i18n frontend/src --include='*.json' --include='*.jsx' --include='*.tsx'
# 期望: 无输出 (用户侧文案只用 "品牌" / "行业" 标签, 不暴露实现术语)

# (H5) Engine 对比不得成为路由 (应是 filter)
grep -rnE "path=['\"].*engines?.*['\"]" frontend/src/App.jsx
# 期望: 无输出
```

**I. 实施 Session 映射**

本节的落地由新增 Session T1'-T5' 承载, 取代 `docs/CLAUDE_CODE_SESSIONS.md` 原 Triad T1-T4。实施顺序见 SESSIONS.md "Brand/Industry Mode IA Sessions" 章节。

**J. 与其他章节的 Cross-Ref 更新**

- §4.6.1 / §4.6.1-0 / §4.6.1b / §4.6.1d / §4.6.1e: 每节开头加 `> 2026-04-20 SUPERSEDED by §4.6-IA-v2 — 本节内容的渲染锚点已迁移, 新实施以 §4.6-IA-v2 为准`
- §4.1.1d: 开头加 `> 2026-04-20 SUPERSEDED by §4.6-IA-v2.F — 零 Project 态统一走 /onboarding 重定向, 本节 E1/E2/E3/E4 全部废除`
- §4.1.1b Onboarding: 更新"数据曝光" 描述, 标注 2026-04-20 Auth-Required 反转后 Onboarding 从 0-1 步恢复为 4 步前置流程
- §4.11 埋点: 新增事件 #67 mode_toggle_clicked / #68 brand_picker_switched / #69 industry_picker_switched / #70 onboarding_step_completed (见 §4.11.4 S14, 待补)
- CLAUDE.md 决策 #2 同步重写

---

**K. V2 分析页视觉统一 & 全局 Filter Bar (2026-04-20 下午追加)**

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节列出的限制仅用于指导实施, 严禁以 i18n key / JSX 文本节点形式呈现给最终用户。

**K.1 问题陈述 (Frank 反馈 2026-04-20)**

Brand Mode 7 个分析 sub-view (overview / visibility / topics / sentiment / citations / products / competitors) 在 Session T2' 落地后, 存在以下视觉和信息架构问题:

1. **视觉不统一**: 各页卡片 padding / 间距 / 标题层级各异, 只有 `/brand/overview` (沿用 DashboardPage + BrandPanoramaPanel) 形成视觉基准, 其他 6 页感觉"不是同一个产品"
2. **缺少全局筛选器**: 用户在 Overview 选定了时间段/引擎, 切到 Visibility / Sentiment 后筛选条件丢失, 每页分别重开
3. **卡片留白过大**: 图表区与卡片边缘垂直间距过大, 一屏信息密度低
4. **数据口径 Bug**: Visibility 页面出现 "1620%" 提及率 (mentionRate 已是百分比再 ×100)
5. **Sentiment 页"看上去像图表坏了"**: Distribution 用 3 个纯文字大号百分比, 无饼图
6. **Competitors 页缺少叙事**: 7 张图堆砌, 用户看不出"我到底输在哪"
7. **Products BCG 矩阵空旷**: 4 个点悬浮在大片空白上, 无聚类感

**K.2 全局 Filter Bar 规范**

所有 Brand Mode 分析 sub-view 顶部 (仅 Overview 下方紧跟 KPI 卡后, 其他页首屏顶部) 渲染统一的 `<BrandAnalysisFilterBar>` 组件:

- **筛选项 (URL-driven)**: `?from=YYYY-MM-DD&to=YYYY-MM-DD&engines=chatgpt,doubao,deepseek-CN&profileGroup=xxx&dimensions=品类,品牌&intents=informational,commercial` (engines 枚举锁 MVP 3 家, Decision #28.C1)
- **6 字段 semantics**:
  - `from` / `to`: 时间段, 默认近 7 天 (空值表示默认)
  - `engines`: 引擎多选, 空值表示全部 (ChatGPT + 豆包 + DeepSeek)
  - `profileGroup`: 用户画像组 ID (见 §4.2.3a ProfileGroup), 空值表示全部
  - `dimensions`: Topic 维度多选 (品类/品牌/产品/关系), 空值表示全部
  - `intents`: Intent 多选 (informational / commercial / transactional / navigational), 空值表示全部
- **持久化**: URL 参数为唯一真相源, **不**落 localStorage。用户在 Brand Mode 切 sub-view 时, router 保留 query string (保留 `brandId` + 6 个 filter 字段, 去除 sub-view 私有参数如 `sub=content-gap`)
- **主/扩展分层** (同 CLAUDE.md 决策 #17):
  - 主筛选 (始终可见): 时间 + 引擎 + profileGroup
  - 扩展筛选 (折叠): dimensions + intents, "更多筛选" 按钮 + 活跃角标
- **跨 sub-view 同步**: Hook `useBrandAnalysisFilters()` 封装读/写, 所有 7 个分析页在顶部 mount 同一 `<BrandAnalysisFilterBar />`, 数据 fetch 以 hook 返回的 filters 为输入

**K.3 视觉统一契约**

所有分析页必须遵守的布局约束 (超出即 PR block):

- **页面头**: `<h1 className="text-2xl font-brand font-semibold">` + 下一行 `<p className="text-sm text-themed-muted">` 副标题, 间距固定 `mt-1`
- **Filter Bar**: 页面头下方固定 `mt-4 mb-6`, sticky 可选 (`position: sticky; top: 0; z-index: 10;`)
- **Card padding**: 主图表卡 `p-5`, KPI 小卡 `p-4`, 所有 Card 内上下留白一致
- **图表高度**: 主趋势图 `height={280}`, 分布/占比图 `height={240}`, Sparkline 默认 `height="100%"` (见 C1)
- **标题字号**: Card header `text-base font-semibold` + 右上 badge/filter (若有) 右对齐
- **分节间距**: 两个 Section 之间 `gap-6` (网格) 或 `space-y-6` (垂直堆叠), 禁止 `gap-10+` 过大留白

**K.4 Harness 拦截 (补充 CLAUDE.md 3 条)**

```bash
# (K1) Brand Mode 分析页必须 import BrandAnalysisFilterBar (Overview 例外, 它内嵌于 Panel)
for f in frontend/src/pages/brand/Brand{Visibility,Topics,Sentiment,Citations,Products,Competitors}Page.jsx; do
  grep -q "BrandAnalysisFilterBar\|useBrandAnalysisFilters" "$f" || echo "MISSING FILTER BAR: $f"
done

# (K2) 禁止在 Brand Mode 分析页写死时间范围 (必须走 hook)
grep -rnE "const\s+(from|to|dateRange)\s*=\s*['\"\(]" frontend/src/pages/brand/ --include='*.jsx'
```

---

**L. Heatmap 组件规范 (BrandTopicHeatmap)**

**L.1 用途**

- **Visibility 页**: 替代原"竞品提及率矩阵表" + "竞品象限图", 用一张 Brand × Topic 热力图展示"我和 Top 竞品在各 Topic 上的提及率对比" (sequential color: 低→高, 淡→深)
- **Sentiment 页**: 替代原"竞品情感对比表", 用一张 Brand × Topic 热力图展示"我和 Top 竞品在各 Topic 上的情感分数" (diverging color: 负面红 / 中性灰 / 正面绿)

**L.2 组件 Props**

```jsx
<BrandTopicHeatmap
  rows={[{ brandId, brandName, values: [{ topicId, topicLabel, value, sample }] }]}
  scale="sequential" | "diverging"  // sequential: [0,max]; diverging: [-1, 1]
  metric="mentionRate" | "sentiment" | "sov"  // 用于 tooltip 文案 + 格式化
  highlightBrandId={string}  // 当前品牌高亮行 (加边框)
  onCellClick={(brandId, topicId) => void}  // 点击跳转 Topic 详情
  loading={boolean}
/>
```

**L.3 色带**

- Sequential (Visibility): `var(--color-heatmap-seq-0)` → `var(--color-heatmap-seq-5)` (6 档, 基于 Tailwind zinc/slate 浅灰到品牌主色)
- Diverging (Sentiment): `var(--color-heatmap-div-neg)` (红) → `var(--color-heatmap-div-zero)` (浅灰) → `var(--color-heatmap-div-pos)` (绿), 5 档
- 所有颜色从 DESIGN_TOKENS.md C11 段新增, 禁止内联 hex

**L.4 交互**

- 悬停: 显示 `{brandName} × {topicLabel}: {value}{metricUnit} (样本 N)` tooltip
- 点击单元格: 跳 `/brand/topics?topicId=xxx` (如当前不是该品牌, 先切 `brandId`)
- 空值单元: 显示 `·` 浅灰, tooltip 提示 "样本不足"

**L.5 适用范围**

- Visibility 页 section 4 (替代原象限图 + 矩阵表)
- Sentiment 页 section 4 (替代原竞品情感对比表)
- **禁止**在 Industry Mode / Overview 页 / Products 页 使用 (叙事不同)

---

**M. 竞品页重构: "我在哪些维度输给谁"**

**M.1 叙事主线**

原 BrandCompetitorsPage 7 张图无主次。重构后单一叙事: *"作为当前品牌, 我在哪些维度输给了谁?"* — 让用户 5 秒内识别最大威胁 + 具体劣势维度。

**M.2 新布局 (顶→底)**

1. **页面头**: `"{currentBrand} · 竞品对比"` + 副标题 "我在哪些维度输给谁"
2. **Filter Bar** (K.2)
3. **Top 3 威胁品牌卡片** (3 列网格): 按 `gap(竞品 - 我)` 在核心指标上的加权和降序排列
   - 每张卡: 品牌 logo/名称 + 3 个关键 delta 数字 (V/S/R 对我) + "点击查看详情 →"
   - 当前激活的竞品卡片加品牌色边框
4. **Tier 2 引用域覆盖矩阵** (M.5, 2026-04-20 追加): HTML 表格; 行=权威媒体域名 (8 个), 列=我 + Top 3 竞品 (4 列), 单元格=该域在 T-30d 引用该品牌的次数。色阶用 `color-mix(in srgb, var(--color-accent) N%, transparent)`, "我"列用 accent, 竞品列用中性灰; 底部图例链接到 §4.2.7 引用→内容缺口/PR 目标行动面
5. **选中竞品的 5 维雷达图**: Authority Radar (见 §4.2.7.D) 改造——我 vs 选中竞品 叠加两条折线, 填色半透明
6. **Topic 胜负矩阵**: 精简版 BrandTopicHeatmap (2 行: 我 + 选中竞品; 多列: 共同覆盖的 Top 10 Topic), diverging scale (我胜为绿, 败为红)
7. **30 天动态时间线**: 双线 PANO 趋势 (我 vs 选中竞品), 标注关键交叉点
8. **Same-Group 共享域 + Acquisition** (M.6 加强): 保留原 §4.2.7.D 底部两块, 但 Same-Group 卡必须:
   - Header 行: 隶属集团名 + 共享占总引用百分比 (`{Math.round(sharedRatio * 100)}%`)
   - 紧随 header 的**用户层面解释段** (`<p className="text-[11px] text-themed-muted leading-relaxed">`): 2-3 句, 讲清"同集团兄弟品牌会加强母集团叙事, 但在 Topic 层会稀释 SoV, 不算敌方竞品但需识别". ⚠️ 禁止使用开发者约束措辞 (§4.6.0a)
   - 子品牌列表前加 "子品牌:" 前缀 (不再是裸 badge list)
   - 共享域列表保留 (域名 + Tier badge + 覆盖品牌 pills)

**M.3 状态管理**

- 选中竞品存 URL: `?vs=competitor-brand-id`, 默认选第一张威胁卡 (gap 最大者)
- 切换竞品只改 `?vs=`, Filter Bar 其他参数保持

**M.4 废弃 section**

原 7 张图中, 以下 3 个**完全删除** (叙事噪音): 单独 SoV 水平条 / 单独 PANO 趋势 / 单独 Authority Radar 全量竞品重叠版。保留并改造: Same-Group (M.6), Acquisition, Tier 2 Coverage (M.5, 新增), 竞品对比表 (收紧为 5 列 + 默认 collapsed)

**M.5 Tier 2 引用域覆盖矩阵 (2026-04-20 新增)**

**为什么**: 原 Competitors 页 Top 3 威胁卡之后直接跳雷达图, 用户拿不到"我在哪些权威媒体上缺位"的可操作信号。Tier 2 覆盖矩阵填补这个 gap, 并链接到已存在的行动面 (§4.2.7.B 内容差距 / §4.2.7.C PR 目标)。

**数据源**: `mock.js` / 生产后 `/api/citations/tier2-coverage?brandId=&competitorIds=&from=&to=` (Phase 2); 现阶段用 `TIER2_COVERAGE_MATRIX` mock, 字段 `{ domains: string[], brands: [{brandId, label, counts: number[]}] }`

**渲染契约**:
- 表头: 域名一列 + 品牌 N 列 (我 + Top 3 竞品); "我"列表头加 primary 色标记
- 单元格: 数字 + 背景色 intensity (`color-mix` with `var(--color-accent)` 对"我"列, `var(--color-text-muted)` 对竞品列), 基于 `count / maxCount` 计算 0-45% alpha
- 空/零值: 显示 `—` (em dash), 不显示 0
- 禁止: 内联 hex (C9-2 harness); 不得借用 heatmap 色带 (那是 BrandTopicHeatmap 专属, C9-1)
- 最大行数: 8 个 Tier 2 域 (若数据超过 10 个, 按总 count 降序截断)

**底部引导**: 短句 "要攻克这些域名, 可以在 [引用→内容缺口] 查看 Top 缺口页面类型, 或在 [引用→PR 目标] 查看优先触达名单" (锚文本跳 `/brand/citations?sub=content-gap` 和 `/brand/citations?sub=pr-targets`)

**M.6 Same-Group 共享域必须带用户层面解释 (2026-04-20 新增)**

**为什么**: Frank 2026-04-20 反馈"同集团共享域是什么意思"——原页面直接列域名, 用户无法在 3 秒内理解"这是竞品还是自家兄弟"。属于**用户层面信息缺失**, 必须在 UI 文案层补上。

**UI 文案规范** (必须遵守 §4.6.0a UI vs Prompt 边界):

✅ **示例 (可以写)**:
> 你和以下子品牌属于同一母集团。当 AI 引擎引用这些官方/权威域名时, 母集团叙事会被加强, 但**同一母集团的兄弟品牌之间也会在同一 Topic 里互相稀释 SoV** — 这些不算"敌方竞品", 但在做 Topic 层策略时需要识别出来, 以免和自家人抢占位。

❌ **反例 (禁止, 属于开发者约束泄漏)**:
> "本页不展示同集团品牌的竞争对比, 详情请进入 Same-Group 页" — 这类措辞 PRD §4.6.0a 明确禁止

**Header 元信息**: `隶属集团: {group} · 共享占总引用 {sharedRatioPct}%`

**子品牌列表**: `子品牌:` 前缀 + `<Badge variant="neutral">` 列表

**数据契约**: `SAME_GROUP_SHARED = { group: string, siblingBrands: string[], sharedDomains: string[], sharedRatio: number ∈ [0, 1] }` (mock.js 已有)

---

**N. 数据口径统一: mentionRate 必须小数 + Sentiment Distribution 必须 Donut**

**N.1 mentionRate 唯一小数契约 (C11)**

- **存储层 (mock.js + 后续 DB)**: `mentionRate` 字段**只**存小数 `0.162` (表示 16.2%), 不得存百分比 `16.2`
- **UI 渲染层**: 统一 `{(value * 100).toFixed(1)}%` 或 `${Math.round(value * 1000) / 10}%`, 禁止 `Math.round(value * 100)%` (那是"把已经是百分比的数再乘 100")
- **Harness (DESIGN_TOKENS.md C11)**: scripts/check-data-contracts.mjs 断言所有 BRANDS / PRODUCTS / TOPICS 的 `mentionRate` ∈ [0, 1], 超过 1 一律 fail

**N.2 Sentiment Distribution 必须 Donut (C12)**

- Sentiment 页顶部 Distribution 区**禁止**仅用 3 个大号文字百分比 (当前 BrandSentimentPage lines 85-99)
- 必须用 `<DonutChart segments={[{ label:'正面', value, color:var(--color-sentiment-pos) }, ...]} size={180} />` 组件
- 右侧保留文字图例: 3 行 `<label>: <pct>% (N 条)`
- **Harness (DESIGN_TOKENS.md C12)**: grep BrandSentimentPage 必须 import DonutChart, 若未出现则 PR block

**N.3 Cross-Ref**

- CLAUDE.md 图表契约 Harness 新增 C11/C12 (见 §4.6.0a 扩展)
- DESIGN_TOKENS.md "图表数据 & 行为契约" 从 C1-C8 扩展为 C1-C12 (C9/C10 已占位于 Heatmap seq/div 色带命名)
- mock.js 同步: BRANDS.mentionRate 现值 `18.5, 16.2, ...` → 改为 `0.185, 0.162, ...`; PRODUCTS 已是 decimal 不改; COMPETITOR_SENTIMENT_BUBBLE.sov 同理 (22 → 0.22), 或保留百分比但字段改名 `sovPct` 并在 UI 直接渲染不做 ×100

---

**O. Products 详情页数据渲染契约 (Wave-4, 2026-04-20 傍晚 · 取代 Wave-4 初版"列表页扩区"方案)**

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节限制仅指导实施, 不以解释性文字呈现给用户。

**O.0 背景 (Frank 校正)**: Wave-4 初版 (2026-04-20 午后) 误读为"列表页扩为 7 区 portfolio aggregate"; Frank 看到列表页输出后校正意图: **列表页维持 M 节 4 区原状, 真正要补的是详情页 `/brand/products/:productId?brandId=:brandId` 当前渲染空白 ("暂无数据") 的 bug**。Frank 原文: "A, 目前点击某一个详细的产品后, 应该是基于这些产品的 GEO 数据, 但是目前是空的"。

**O.1 Bug 根因**: `BrandProductDetailPage.jsx` 组件入口 `const { brandId, productId } = useParams()`。但 IA v2.0 路由约定 `/brand/products/:productId` 只含 productId 路径参数, brandId 走查询字符串 (`?brandId=:id`)。于是 `useParams()` 返回的 `brandId === undefined`, 后续 `BRANDS.find(b => b.id === undefined)` 得 undefined, 触发守卫 `if (!brand || !product) return <EmptyState />` → 整页空白。

**O.2 Routing 契约 (固化 V2 双参数拆分)**

| 参数 | 位置 | 读取方式 | 必填? | 回退 |
|------|------|---------|------|------|
| `productId` | path param | `useParams().productId` | 是 | 无 (缺则 404) |
| `brandId` | query string | `useSearchParams()[0].get('brandId')` | 否 | 由 `PRODUCTS.find(p=>p.id===productId)` 反查 `product.brand` / `product.brandEn` 匹配 BRANDS |

**为什么 brandId 放 query 不放 path**: 
- 保持与 Brand Mode 其他 sub-view 一致 (`/brand/overview?brandId=`, `/brand/visibility?brandId=` 全部 query string)
- Sidebar BrandPicker 切换品牌只改 `?brandId`, 不跳页
- 产品 id 全局唯一 (mock.js 已保证), 即使不传 brandId 也能单链跳转

**O.3 空状态守卫最小化**

- 仅当 `product === undefined` (productId 不存在) 才渲染空状态, 不因 brandId 缺失而空白
- brand 为 null 时 UI 降级而不塌陷: 顶栏品牌链接 disabled, 品牌名 fallback 到 `product.brand`, industry/category 降级为 null 不崩

**O.4 Harness (CLAUDE.md §"V2 分析页统一契约" 新增 C15)**

```bash
# C15-1: BrandProductDetailPage 禁止从 useParams 解构 brandId (brandId 是 query string)
grep -nE "useParams\(\)[^{]*\{[^}]*\bbrandId\b" \
  frontend/src/pages/BrandProductDetailPage.jsx \
  frontend/src/pages/brand/BrandProductDetailPage.jsx 2>/dev/null

# C15-2: BrandProductDetailPage 必须 import useSearchParams
grep -q "useSearchParams" frontend/src/pages/BrandProductDetailPage.jsx || \
  echo "C15-2 violation: BrandProductDetailPage missing useSearchParams import"

# C15-3: product-first guard (productId 才是 required, brand 可为 null)
#        检测: 若 `if (!brand` 出现在早期 return 之中 → block
grep -nE "if\s*\(\s*!brand\b[^)]*\)\s*\{?\s*return\b.*EmptyState|Empty" \
  frontend/src/pages/BrandProductDetailPage.jsx
```

**O.5 为什么 Wave-4 最终形态是"修详情页"而不是"扩列表页"**

- 列表页已覆盖 portfolio aggregate 的 4 区能力 (BCG + sparkline grid + 表格 + 关系), Frank 校正前的 7 区扩张是过度设计
- 空白详情页是**真实 P0 bug** (用户点任一产品都看到"暂无数据"), 应当优先修
- 详情页的渲染栈 (Hero + 语境 BarChart + Sparkline + 关系图 + Prompt Hits 表) 已全部在组件里实现, 只差 brand 数据可用即可
- Wave-4 真正固化的是"Brand Mode sub-view brandId 统一走 query string"这条路由契约, 不是 UI 区块扩张

**O.6 Cross-Ref (本次取代原"列表页扩区"版本的旧 cross-ref)**

- CLAUDE.md 决策 #20 Wave-4 段 (取代原段) + V2 分析页 Harness §C15-1/2/3
- DESIGN_TOKENS.md §C15 路由契约 (取代原"列表页密度契约")
- CLAUDE_CODE_SESSIONS.md Session T6' Wave-4 块 (取代原 11.6-11.10, 新版 §12.1-12.4)
- mock.js 引用: `PRODUCTS` / `BRANDS` / `PRODUCT_RELATIONS` / `MENTION_DETAIL_LIST` 零新增字段

---

#### 4.6.1 页面结构

> **⚠️ 2026-04-20 SUPERSEDED by §4.6-IA-v2**: 本节"面板 / 品牌列表 / 产品 三视角"结构已被 Brand Mode / Industry Mode 二 Mode IA 取代, 所有顶层路由重新归属。本节保留作为历史记录, 新实施以 §4.6-IA-v2 为准, 不再按本节实现。

**设计原则**: 面板 / 品牌 / 产品 三个视角的分工必须清晰——面板是宏观市场视角，品牌是单一品牌的深度视角，产品是品牌下钻的第三层细节。任何指标只在一处成为"主视图"，避免跨 tab 重复展示同一张图表。

**顶层导航** (侧栏分组, 见 `DashboardLayout.jsx`):

```
├── Landing Page (公开)
├── Auth (登录/注册)
├── Dashboard (登录后主应用)
│   ├── 项目列表
│   └── 项目详情 (侧栏导航)
│       ├── 【分析】
│       │   ├── 面板       /dashboard          — 市场宏观总览 (我 vs 竞品 vs 行业)
│       │   ├── 品牌       /brands             — 品牌列表 (默认聚焦我)
│       │   │   └── 品牌详情 /brands/:id        — 单品牌深度 (4 子 Tab)
│       │   │       ├── 概览    ?tab=overview   — PANO / 子维度 / 趋势 / 提及位置
│       │   │       ├── 诊断    ?tab=diagnostics — Diagnostics 列表 + 评分卡
│       │   │       ├── 产品    ?tab=products   — 该品牌产品 BCG 矩阵 + 列表
│       │   │       │   └── 产品详情 /brands/:id/products/:productId  (独立 URL, SSR)
│       │   │       └── 引擎对比 ?tab=engines    — 3 引擎并排分解
│       │   └── Topics     /topics             — Topic → Prompt → Query → Response 下钻
│       ├── 【数据】
│       │   ├── 行业全景   /industry           — SoV / 行业趋势 / 热门 Topic / 公开视角
│       │   └── 知识图谱   /knowledge-graph    — 品牌 / 产品 / 关系可视化
│       └── 【运营】
│           ├── 诊断       /diagnostics        — 跨品牌诊断聚合视图
│           └── 报告       /reports            — 周报/月报/体检报告 PDF 列表
└── Settings
    ├── 项目设置 /project-settings             — 主品牌 / 竞品 / 偏好
    ├── 账号设置 /settings                      — Profile / 通知 / 语言
    └── API Keys                                — 个人 API Token
```

**三个"分析"视角的分工 (避免重复)**:

| 视角 | 回答什么问题 | 主力指标 | 典型图表 | 不做什么 |
|------|------|---------|---------|---------|
| **面板 (/dashboard)** | 我在整个行业里表现如何？谁是最大威胁？ | SoV / 情感 / 引用份额 / 行业排名 | SoV 饼图 + 竞品四象限 + PANO 趋势 + 告警条 | **不做**单品牌的诊断详情<br>**不做**单品牌的 Topic 下钻<br>**不做**产品层面的细节 |
| **品牌 (/brands/:id)** | 这个品牌健康度如何？哪里做得好/坏？ | PANO / V / S / R / A 四子维度 | 品牌评分卡 + 4 维度条形 + 引擎对比 + 诊断列表 + 产品 BCG | **不做**跨品牌的市场份额比较 (那是面板)<br>**不做**产品层的独立指标趋势 (在产品详情页) |
| **产品 (/brands/:id/products/:productId)** | 这个产品在 AI 回答中被如何描述？ | 产品提及率 / 推荐语境 / 平替 & 搭配关系 | 推荐语境分类 + 替代品/搭配品 + Prompt 命中列表 | **不做**品牌整体评分<br>**不做**跨品牌对比 |

**产品从顶层导航移除的理由**:
- 产品天然隶属于品牌 (知识图谱 `kg_products.brand_id`)
- "一个项目下的所有产品平铺展示" 视角信息密度低，用户决策路径不清
- 改为品牌详情页的子 Tab + 独立 URL，兼顾品牌视角收敛 + 产品级 SEO/分享

#### 4.6.1-0 Dashboard 新定位: Daily Digest vs Action Center 双版 Spike (2026-04-20 新增)

> **⚠️ 2026-04-20 同日 SUPERSEDED by §4.6-IA-v2**: 本 Spike 从未落地; `/dashboard` 路由被整个废除, 登录后直接进 `/brand/overview`。本节保留为设计过程记录, 不再执行。

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"本版做/不做"、"Layout A 负责..."等限制是实施级约束, 不得以 i18n / JSX 文本呈现。详见 §4.6.0a。

**A. 背景 & 问题**

Plan S 提取 `BrandPanoramaPanel` 后, `/dashboard` 与 `/brands/:id?tab=overview` 共用同一组件 → **信息架构 100% 重合** (侧栏"面板"和"品牌"等于一个菜单项)。Frank 要求替换 Dashboard 内容, 但两个候选定位 (时间流 vs 待办板) 需要各自的视觉 Spike 才能判断, 因此 MVP 期两版同时实现, 放在 `?layout=digest|center` toggle 背后。

**B. 定位迁移**

- **§4.6.1a (/dashboard 市场宏观视角)** 的"5 KPI + 竞争视图 + 趋势 + 告警" 内容 **保持存在**, 但**唯一挂载点从 /dashboard 迁移到 /brands/:id?tab=overview** (单品牌概览 Tab)。组件名沿用 `BrandPanoramaPanel`。§4.6.1a 文本不删, 但全节开头加 `> 2026-04-20: 本节内容的渲染锚点已迁移到 §4.6.1b 品牌详情 Overview Tab, /dashboard 路由改由本节 §4.6.1-0 定义.`
- **`/dashboard`** 在 §4.6.1-0 定义下获得新内容 (Daily Digest 或 Action Center 之一), 不再含 5 KPI 卡 / PanoRing / 竞品四象限等"体检仪表盘"元素

**C. Layout A · Daily Digest (时间流视角)**

回答的问题: "我的品牌昨天发生了什么? 今天我需要关注什么?"

五段结构 (从上到下):

| 区块 | 内容 | 视觉 |
|---|---|---|
| ① Hero 变化提要 | 单行:主品牌名 + PANO {value} {delta-pill} · 提及率 {delta} · SoV {delta} · {alertCount} 条 P0 告警 + 上次刷新时间戳 | 高 72px, 无卡片边框, 灰底浅分隔 |
| ② 今日异动 (Delta Cards) | 3–5 张卡, 每张卡 = 一个 KPI 的"昨日 vs 7d 均值"跳点 + 一句话驱动因子. 卡点击 → 打开对应 KPI Drill-down (Drawer 模式, 详见 §4.6.1a-drilldown) | 水平滑动条 / md+ 改 grid-cols-3; 每卡带方向色 (涨绿/跌红/持平灰) + mini sparkline |
| ③ 待办行动 (Action Queue) | 合并 3 类 P0/P1 告警: (a) Diagnostics 未处理诊断 (§4.8.1) (b) Citation Attribution Mismatch (§4.2.7.A) (c) 新 PR Target (§4.2.7.C, 按 pr_score desc) · 最多 Top 3, 每条带主动作按钮 | 列表, 每行 48–56px, 左色条 (red P0 / amber P1) + 标题 + 一键动作 |
| ④ 近期 Response 样本流 | 最近 5 条命中主品牌的 Response 片段, 每条: 引擎 icon + 时间 + Topic title + sentiment 色条 + 截断文本. 点击 → 跳 /topics 四层下钻 (§4.2.5) 定位到该 Response | 类 Gmail 邮件列表, 无卡片, 悬浮 hover 高亮 |
| ⑤ 快速跳转 | 4 个方块: 深度体检 → /brands/:id · 行业对标 → /industries/:id · 数据导出 → /reports · MCP API → /settings/api | grid-cols-4, 每方块 96px |

**关键差异 (与 §4.6.1a Brand Panorama)**:
- 没有 5 KPI 仪表盘 (留给品牌概览)
- 没有 PanoRing (留给品牌概览)
- 没有 SoV 饼图 (留给品牌概览)
- 时间性强 (所有内容都是"昨日 / 近期"), 不是"当前体检"
- 强转化: ② 每卡可跳 Drawer, ③ 每条有主动作按钮, ④ 每条可跳 Topics 下钻

**D. Layout B · Action Center (待办工作台视角)**

回答的问题: "现在我有哪些事要处理? 按紧急度排"

结构: 顶栏 + 三栏 Kanban (P0 / P1 / P2)

| 栏位 | 数据源 | 卡片格式 |
|---|---|---|
| **P0 紧急** | Diagnostics severity=P0 + Citation Attribution Mismatch confidence>0.8 + 品牌监控断流 alert | 标题 + 上下文 1 行 + 主动作 + "忽略" 按钮 + 创建时间 |
| **P1 重要** | Diagnostics severity=P1 + PR Targets pr_score>80 + Content Gap topics ≥3 | 同上 |
| **P2 可选** | PR Targets pr_score 40–80 + 低置信度 Mismatch + 其他改善建议 | 同上 |

顶栏: 主品牌名 + Project 切换器 + 未处理计数 "P0: 3 · P1: 8 · P2: 12"

**关键差异 (与 Daily Digest)**:
- 按 severity 排, 不按时间
- 每张卡有"主动作"+"忽略"双按钮 (Daily Digest 异动卡只有跳 Drawer)
- 强 OKR 感: 列底部显示"本栏已处理 X / Y" 进度条
- 无 Response 样本流 (Daily Digest 的 ④), 无快速跳转方块 (⑤)

**E. 双版 toggle 契约 (Spike-only)**

- URL: `/dashboard?layout=digest` 或 `?layout=center`; 无参数 → localStorage 记住上次选择 → 首次默认 `digest`
- 切换按钮位置: Dashboard 顶栏右侧一组小分段按钮 "时间流 / 待办", 2026-04-20 Spike 期 Frank 可见
- **临时性质**: 这是 **Spike 工件**, Frank 决定保留哪版后, 另一版代码 + toggle + localStorage 一起下线 (Session S2 final cleanup 任务)
- 埋点: `dashboard_layout_switched { from, to }` (§4.11.4 追加 #66), Frank 实际使用频率是判据之一

**F. 共同约束 (两版都要满足)**

- 零 Project 态 (projects.length===0): 两版都 early-return `<DashboardEmptyState>` (§4.1.1d E1), 不渲染正文
- Profile Group 筛选器 (§4.2.3a): 两版顶栏都含 `<ProfileGroupFilter>`
- 时间/引擎筛选器: 两版都有; Daily Digest 默认锁定"昨日 vs 7d", Action Center 默认不筛时间 (当前未处理全量)
- 数据来源: 不新增 mock 表, 复用 `BRANDS` / `DIAGNOSTICS` / `PR_TARGETS` / `CITATION_*` / `RESPONSES` (Mixpanel 埋点新增仅 2 条: dashboard_layout_switched + kpi_drilldown_opened)
- Empty State E1 文案: 若 Frank 选 Layout A, 文案改"开始接收每日变化提醒"; 若选 Layout B, 文案改"开始接收待办告警"
- 国际化: 所有新文案按 i18n 矩阵 (§4.10.4a) 补 zh-CN + en-US, 命名空间 `dashboard.digest.*` + `dashboard.center.*`

**G. 组件清单**

Layout A · Daily Digest:
- `frontend/src/pages/DailyDigestPage.jsx` (新)
- `frontend/src/components/dashboard/HeroStrip.jsx` (新 · ① Hero)
- `frontend/src/components/dashboard/DeltaCard.jsx` (新 · ② 异动卡, 支持 click → Drawer)
- `frontend/src/components/dashboard/ActionQueue.jsx` (新 · ③ 待办)
- `frontend/src/components/dashboard/ResponseSampleFeed.jsx` (新 · ④)
- `frontend/src/components/dashboard/QuickLinkGrid.jsx` (新 · ⑤)

Layout B · Action Center:
- `frontend/src/pages/ActionCenterPage.jsx` (新)
- `frontend/src/components/dashboard/ActionKanban.jsx` (新 · 三栏容器)
- `frontend/src/components/dashboard/ActionCard.jsx` (新 · 单条卡)

共享:
- `frontend/src/pages/DashboardPage.jsx` 改为 "按 query layout 路由到 DailyDigestPage 或 ActionCenterPage" 的调度器 (30 行内)
- `frontend/src/components/dashboard/DashboardLayoutToggle.jsx` (新 · 顶栏切换按钮, Spike 期存在)

**H. 决策点 (Frank 需做)**

S2 Session 交付后, Frank 在真实数据下两版切换使用 ≥3 天, 然后:
- 情况 1: 选 Daily Digest → S2 followup 清理 ActionCenter 代码
- 情况 2: 选 Action Center → 清理 DailyDigest 代码
- 情况 3: 都保留 (两个独立入口 /dashboard + /action-center) → 追加 PRD §4.6.1-0b 把 Spike toggle 升级为永久功能, 侧栏分析组 2 项变 3 项

默认预期是情况 1 或 2 (减少导航冗余); 情况 3 需要 Frank 显式请求, 本节不预设。

#### 4.6.1a 面板 (/dashboard) — 市场宏观视角

> **⚠️ 2026-04-20 SUPERSEDED by §4.6-IA-v2**: 本节"5 KPI + 竞争视图 + 趋势 + 告警"内容保留, 但**渲染锚点从 `/dashboard` 迁移到 `/brand/overview`** (Brand Mode · 总览 sub-view)。`/dashboard` 路由本身被废除, 301 重定向到 `/brand/overview`。组件沿用 `BrandPanoramaPanel`, 不再叫"面板页"。

> **⚠️ 2026-04-20 渲染锚点迁移**: 本节原以 `/dashboard` 为挂载点的"5 KPI + 竞争视图 + 趋势 + 告警" 内容现通过共享组件 `BrandPanoramaPanel` 渲染在 `/brands/:id?tab=overview` (§4.6.1b 品牌概览 Tab); `/dashboard` 路由的新定位见 §4.6.1-0 (Daily Digest / Action Center 双版 Spike). 本节图表规格 / KPI 口径 / Harness 等所有内容保持有效, 仅挂载页改变.

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节列出的"面板只回答..."/"不承担..."/"不做..."表述属于 **Claude Code Session Prompt 和 Page Scope** 层面的页面边界约束, **严禁**作为 i18n key 或 JSX 文本节点直接呈现给最终用户。详见 §4.6.0a (Page Scope 边界约束规则)。

**定位**: 面板是"项目总览"。它回答的问题是:
1. **我在行业里的位置** — 相对 SoV、情感、引用、排名
2. **竞争格局** — 谁是领先者、谁在追赶、四象限定位
3. **变化趋势** — PANO 与子维度近 30 天如何变化
4. **告警** — 最紧迫的 3 条异常, 一键进入品牌深度视图

面板**永远以"我"为主视角** (主品牌 from `Project.primaryBrandId`)。若用户需要切换到另一个品牌视角，必须进入"品牌"详情页。面板不承担单品牌的诊断展开、Topic 下钻或产品细节——那些分别在"品牌详情"和"产品详情"页。

**顶栏 (Toolbar)**:
```
┌───────────────────────────────────────────────────────────────────────────┐
│ 面板 · {主品牌名}                                                          │
│ 时间 [最近7天|30天|90天▾]  引擎 [全部✓][ChatGPT][豆包][DeepSeek]           │
│ 用户画像 [全部 Profile▾]   (单选下拉, 默认"全部 Profile")                  │
└───────────────────────────────────────────────────────────────────────────┘
```

- 时间范围、引擎、**用户画像 (Profile Group)** 三个是**面板主筛选** (始终可见), 所有下方组件受其联动
- 用户画像下拉内容: MVP 6-10 个预置 Profile Group (见 §4.2.3a), 含 "全部 Profile" (默认聚合基线) + 行业特化组
- **维度 (dimension)** 和 **意图 (Intent)** 是**面板扩展筛选** (2026-04-16 新增, 收纳在可伸缩区域):
  - 维度: 全部 (默认) / 品类 / 品牌 / 产品 / 竞品 — 对应 Topic.dimension, 单选, 选中后所有 KPI/图表只统计该 dimension 的 Topic 下的 Query
  - 意图: 全部 (默认) / informational / commercial / transactional / navigational — 对应 Prompt.intent, 单选, 选中后所有 KPI/图表只统计该 Intent 的 Prompt 下的 Query
  - **提及率口径联动**: 当维度筛选非"全部"时, 提及率分母跟随所选 dimension; 当维度=全部时, 默认口径仍为 `dimension='品类'` (non-brand)
- 状态通过 URL query 持久化: `?range=30d&engines=chatgpt,doubao&profileGroup=young_female_tier1&dimension=品类&intent=commercial`
- 默认: 最近 30 天 × 全部引擎 × 全部 Profile × 全部维度 × 全部意图
- **样本不足兜底**: 当所选筛选组合下样本 < 50 Queries, KPI 卡改显 "样本不足 (n={count}), 请扩大时间范围或换组", 趋势图显示淡化状态; 不得静默用全量数据替代

##### 4.6.1a-filter 可伸缩筛选栏交互设计 (2026-04-16 新增)

> **设计动机**: 面板筛选维度已达 5 个 (时间/引擎/画像/维度/意图), 全部平铺会导致 toolbar 过宽或折行影响数据区域视觉。采用**主筛选 + 扩展筛选**分层, 兼顾高频操作效率和低频操作可发现性。

**交互规则**:
- **主筛选 (始终可见)**: 时间范围 + 引擎 + 画像 — 这 3 个是最高频操作, 占据 toolbar 第一行
- **扩展筛选 (折叠/展开)**: 维度 + 意图 — 点击 "更多筛选" 按钮展开第二行; 已有非默认筛选时按钮显示角标数字 (如 "更多筛选 · 2"), 提示用户当前有活跃的扩展筛选
- **展开态**: 第二行平铺显示维度和意图两个下拉/Pill 组, 带 "收起" 按钮
- **折叠记忆**: 展开/折叠状态跟随 URL 持久化 (如 `&filters=expanded`), 下次进入保持上次状态
- **活跃筛选 tag**: 当维度或意图不是"全部"时, toolbar 右侧显示可点击清除的 tag (如 `维度: 品类 ×` / `意图: commercial ×`), 即使扩展筛选折叠也能看到当前非默认筛选状态
- **同一规范适用于品牌详情页和 Topics 页**: 品牌详情页的 toolbar 沿用同样的主筛选 + 扩展筛选分层; Topics 第 1 层已有维度筛选, 扩展筛选中只需加意图

**页面布局 (从上至下 5 个区块)**:

```
┌─ Toolbar ───────────────────────────────────────────────────────┐
│ (主筛选: 时间+引擎+画像)  [更多筛选 ▾]                            │
├─ ⓪ Hero (品牌名 + PANO Score + 行业均值) ────────────────────────┤
│ ┌───────────────────────────────────────────────────────────┐    │
│ │                                                           │    │
│ │  雅诗兰黛                      PANO Score                  │    │
│ │  Estée Lauder                 ┌──────────┐               │    │
│ │                               │          │               │    │
│ │  美妆个护 · #2                │    78    │               │    │
│ │                               │          │               │    │
│ │  ▲ +3.2 vs 上月              └──────────┘               │    │
│ │                                良好 (Good)                │    │
│ │                                                           │    │
│ │  行业均值: 61  ████████████████░░░░░░░░░░                 │    │
│ │  我的品牌: 78  ████████████████████████░░░░               │    │
│ │                                                           │    │
│ └───────────────────────────────────────────────────────────┘    │
├─ ① 五 KPI 核心指标卡 (桌面 5×1, 移动 2×3 / 3×2) ────────────────┤
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │
│ │ 提及率   │ │ SoV     │ │ 情感得分 │ │ 引用份额 │ │ 行业排名 │    │
│ │ 62.4%   │ │ 23.4%   │ │  0.78   │ │  18.2%  │ │   #2    │    │
│ │ ▲ +3.8 │ │ ▲ +2.1 │ │ ▼ -0.02│ │ ▲ +1.5 │ │ ↑ 1    │    │
│ │ sparkline│ │ sparkline│ │sparkline│ │sparkline│ │(进退箭头)│    │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘    │
├─ ② 竞争视图 (左右并列) ────────────────────────────────────────┤
│ ┌─ SoV 饼图 ─────────┐ ┌─ 竞品四象限 (气泡图) ───────────────┐ │
│ │  我: 23%           │ │ 高 ▲ 情感                            │ │
│ │  竞A: 28%          │ │   ● 领跑者 ● 高光品牌                 │ │
│ │  竞B: 15%          │ │  (我) ●                              │ │
│ │  竞C: 11%          │ │                                     │ │
│ │  其他: 23%         │ │   ● 追赶者 ● 警示品牌                 │ │
│ │                    │ │ 低 ▼────────────── SoV ──────────▶ 高│ │
│ └───────────────────┘ └─────────────────────────────────────┘ │
├─ ③ 趋势 (左右并列) ────────────────────────────────────────────┤
│ ┌─ PANO 趋势 (我 vs Top 3 竞品) ──┐ ┌─ 5 KPI sparkline 汇总 ┐│
│ │ 折线图 30 天                     │ │ 每行一个指标:          ││
│ │  我 (高亮紫)                     │ │  提及率    ▁▂▃▄▄▅      ││
│ │  竞A (灰) 竞B (灰) 竞C (灰)      │ │  SoV      ▁▂▃▅▃▂      ││
│ │                                  │ │  情感     ▂▃▄▄▃▂      ││
│ │                                  │ │  引用份额  ▁▁▂▃▄▅      ││
│ └─────────────────────────────────┘ │  行业排名  ▂▂▃▂▁       ││
│                                      └───────────────────────┘│
├─ ④ 告警条 (Top 3 P0/P1 异常) ───────────────────────────────────┤
│ ⚠ [P0] 豆包中 SoV 近 7 天下降 15%  →查看品牌详情                  │
│ ⚠ [P1] ChatGPT 负面情感回答占比升至 18% (行业均值 9%) →查看     │
│ ⚠ [P1] 引用份额在"功效解读"Topic 下跌至 #5 →查看                 │
└─────────────────────────────────────────────────────────────────┘
```

**区块 ⓪ — Hero (品牌名 + PANO Score + 行业均值)** (2026-04-16 新增):

面板第一视觉焦点, 用户打开 Dashboard 第一眼看到的就是品牌整体健康度。

**布局** (左右结构):
- **左侧**: 品牌名称 (大号, `formatBrand(primaryBrand, locale)`) + 品牌英文名 (副标题灰色) + 行业标签 (如 "美妆个护") + 行业排名 (如 "#2") + 环比变化 (如 "▲ +3.2 vs 上月")
- **右侧**: PANO Score 大号数字 (0-100, 圆环或方块强调) + 等级标签 (优秀/良好/中等/及格/需关注) + 行业均值对比条
  - **行业均值对比**: 两条水平进度条对齐显示 "行业均值: {industryAvg}" 和 "我的品牌: {myScore}", 直观展示差距

**数据来源**:
- `myScore`: 主品牌 Brand PANO Score (§4.4.2 公式: V×0.30 + R×0.25 + S×0.20 + C×0.15 + A×0.10)
- `industryAvg`: 同行业所有被追踪品牌 Brand PANO Score 的均值
- `rank`: 行业内按 PANO Score 降序排位 (同 KPI 卡 "行业排名")
- `delta`: 本期 PANO Score - 上一周期 PANO Score (周期跟随 Toolbar 时间范围选择)

**等级标签**:

| 分数区间 | 等级 | 标签色 |
|---------|------|--------|
| 90-100 | 优秀 (Excellent) | 绿色 |
| 80-89 | 良好 (Good) | 蓝绿 |
| 70-79 | 中等 (Fair) | 蓝色 |
| 60-69 | 及格 (Pass) | 橙色 |
| 0-59 | 需关注 (Needs Attention) | 红色 |

**交互**:
- 点击 PANO Score 数字 → 跳转品牌详情页 概览 Tab (`/brands/:primaryBrandId?tab=overview`), 展示 PanoRing 大环 + V/R/S/C/A 子维度拆解
- 点击行业排名 → 滚动到本页区块 ② 竞品四象限
- 受 Toolbar 筛选联动: 选中单引擎时显示该引擎的 PANO Score; 选中 Profile Group 时显示该画像下的 PANO Score

**响应式**:
- 桌面: 左右并列, Hero 高度 ~120px
- 移动: 上下堆叠 (品牌名在上, PANO Score 居中, 行业对比条在下)

---

**区块 ① — 五 KPI 核心指标卡** (2026-04-16 修订: 恢复提及率独立 KPI, 详见本节末"口径边界"):

| KPI | 定义 | 计算 | sparkline | 回答用户的问题 |
|-----|------|------|-----------|-------------|
| **提及率 (Mention Rate)** | **默认 non-brand 口径** (2026-04-16): 在 `topic.dimension='品类'` 的 Query 中, 至少被提及一次的占比 **(真实穿透率)** | Σ(含主品牌的 Response 数, 仅 dimension=品类 的 Query) / Σ(dimension=品类 的 Query 总数) | 30 天日度 | "AI 被问品类通用问题时, 有多大比例会主动想到我?" |
| **SoV (Share of Voice)** | 在已经提到品牌的 Response 池内, 主品牌占有的声量份额 **(相对份额)** | Σ(含主品牌的 response 数) / Σ(项目内竞争集合中至少命中 1 个品牌的 response 数) | 30 天日度 | "有品牌出现的讨论里, 我分到几份菜?" |
| **情感得分** | 主品牌相关回答的情感加权平均, 范围 [-1, 1] | Σ(sentimentScore × mentionCount) / Σ(mentionCount) | 30 天日度 | "AI 讲到我时, 语气是正面还是负面?" |
| **引用份额** | 品牌被支撑的 citation 数在品牌相关 Response 的 citation 总数中的占比 | 见 §4.2.6.E (brandsAttributed-based, 2026-04-17 修正) | 30 天日度 | "我的品牌被 AI 引用支撑了多少?" |
| **行业排名** | 主品牌在项目所属行业内按 PANO Score 排名 | 行业内所有品牌按 PANO 降序排位; 值 = 当前排名; 趋势箭头 = 排名进退 | 30 天排名曲线 (Y 反向) | "我在整个行业里第几?" |

**🔑 口径边界 (提及率 vs SoV, 为什么两者都是 KPI 不能互相替代)**:

提及率和 SoV **口径不等价**, 2026-04-16 Frank 的判断推翻了原 §4.6.1a Line 1996 "提及率与 SoV 强相关, 保留 SoV 一个足够"的误判:

| 维度 | 提及率 (Mention Rate) | SoV (Share of Voice) |
|------|---------------------|---------------------|
| **分母** | **默认**: `topic.dimension='品类'` 的 Query 总数 (non-brand 口径, 2026-04-16 精化); 完整口径: 全量相关 Query | 竞争集合中**至少命中 1 个品牌的 Response** 数 (已筛选后口径) |
| **测量属性** | 穿透率 / 覆盖率 — "品类通用问题下, AI 会主动想到我吗" | 相对份额 — "当别人都被想到时, 我占多少" |
| **对用户的含义** | AI 对我的**主动认知度**. 提及率低 = AI 在没有品牌暗示时想不到我 | 竞争中的**相对地位**. SoV 低 = 我方在 AI 中被竞品挤压 |
| **极端反例 1** | 所有竞品和我都出现在 80% Query 里 → **提及率 80%, SoV 20%** (5 家均分) | 同上 |
| **极端反例 2** | 只有我被提到 10% Query, 其他竞品都没被提到 → **提及率 10%, SoV ~100%** | 同上 |
| **典型诊断方向** | 提及率下降 → 内容索引 / 品牌识别 / KG 训练缺失 | SoV 下降 → 竞品发力 / 内容被稀释 / 主题被改写 |

**同时保留两者的业务理由**:
- 一个 SEO 从业者面对客户, 需要同时回答两个完全不同的问题 — "AI 知道我们吗" 与 "在 AI 提到的品牌里我们是老几"
- 只有提及率在涨但 SoV 在跌 = 市场整体在被 AI 更多讨论, 但我方跟不上竞品的加速 (应该关注竞品动作)
- 只有 SoV 在涨但提及率在跌 = 相关讨论整体变少, 只是竞品退得比我更快 (应该关注行业流量为什么萎缩)
- 两者都涨: 健康扩张. 两者都跌: 深度危机, 大概率是内容层面的根本问题

**🔑 提及率 non-brand 口径精化 (2026-04-16 Frank 决策)**:

面板 KPI 卡默认展示 non-brand 提及率 (`topic.dimension='品类'`), 理由: 品牌/产品/竞品 dimension 的 Topic 下, Prompt 显式含品牌名, LLM 几乎必然提到该品牌, 提及率接近 100%, 无诊断价值。只有品类 dimension (non-brand) 的 Topic 才能测量品牌在 AI 中的**主动认知穿透**。

- KPI 卡标题: "提及率" (不加 "non-brand" 后缀, 简洁优先)
- KPI 卡 help tooltip: 说明 "基于品类通用问题计算, 排除了直接询问品牌的问题" (具体文案走 i18n `dashboard.kpi.mention_rate_help`)
- 品牌详情页可展示按 Topic.dimension 分层的提及率明细 (品类 / 品牌 / 产品 / 竞品)
- CSV 导出保留 `mention_rate_pct` (默认 non-brand 口径) + `mention_rate_all_pct` (全量口径) 两列
- 口径过滤规则: 见 §4.2.2a

**交互规则**:
- KPI 卡不可点击进入"Breakdown 详情页" (该结构已废弃, 改为直接去 /brands/:id)
- 点击 KPI 卡 → 跳转到主品牌详情页 (`/brands/:primaryBrandId?tab=overview`) 并 anchor 到对应子维度

**🔗 图表行为契约 (详见 `docs/DESIGN_TOKENS.md` §"图表数据 & 行为契约 C1-C7")**:

面板所有 KPI 卡、sparkline、SoV 饼图、行业排行榜 Hero、品类分布柱图均受 DESIGN_TOKENS C1-C7 约束。Dashboard 实现要点索引:

- **C1 原子默认 100%** — KPI 卡 sparkline / 汇总区 sparkline 必须 wrap 在 `<div className="h-10 flex-1">` 里, `<MiniSparkline>` 不传 width (走默认 `'100%'`)
- **C3 "其他" ≤ 10%** — `SOV_DATA` mock 必须覆盖 Top 8+ 品牌, `其他` 片 ≤ 10%; 若 `其他` > 任一品牌片, 数据集视为不完整, 需扩充
- **C4 Sentiment 百分比整数** — KPI 卡"情感得分"显示为 `${Math.round(sentiment * 100)}%`, **禁止** `.toFixed(2)` 的 `"0.82"` 展示; 唯一例外是 `CompetitorQuadrant` scatter 的 tooltip (Y 轴原生 [0,1])
- **C5 Sparkline 平滑性** — 5 条 KPI sparkline 的合成函数必须是连续的 (线性 + sin/cos 振幅 <1), **禁止** `i % 3 === 0 ? +1 : 0` 这类离散台阶 — 会让用户读出不存在的周期振荡
- **C7 Ranking 字段内在一致** — 当区块 ① 显示 "行业排名 #2" 且区块右侧 `AlertBar` 或"排行榜"同时出现位置编号时, `primary.ranking` 必须与主品牌在 `BRANDS.sort((a,b) => b.panoScore - a.panoScore)` 中的索引 +1 一致 (mock 数据契约)

**区块 ② — 竞争视图** (面板独占, 品牌页不复制):
- **SoV 饼图**: 主品牌 + Top 4 竞品 + "其他". 主品牌切片高亮品牌色, 其他灰阶
- **竞品四象限 (气泡图)**: 详见 4.6.1c

**区块 ③ — 趋势视图**:
- **PANO 趋势**: 折线图, 只画 "我 + Top 3 竞品", 避免过度拥挤. 竞品线灰阶, 我高亮
- **5 KPI sparkline 汇总**: 紧凑的 mini 趋势面板, 用作 KPI 卡的 30 天回看 (KPI 卡内已含 sparkline, 这里是跨维度对比视角——同一时间轴看 5 条线相对走势, 尤其关注**提及率与 SoV 的背离**: 两者分叉时往往是诊断信号)

**区块 ④ — 告警条**:
- 数据源: `Diagnostics` 表, 过滤 `severity IN ('P0','P1')` 且 `brandId = primaryBrandId`
- 排序: 按 severity → 新鲜度 → `quantifiedImpact` 降序
- 最多显示 3 条, 点击 "→查看" 跳转到 `/brands/:primaryBrandId?tab=diagnostics&diagId=...`
- 无 P0/P1 告警时显示绿色 "✓ 当前无严重异常" 单行

**数据聚合规则** (受引擎 + Profile Group 筛选联动):
- 提及率 / SoV / 情感 / 引用份额: 各引擎结果按 response 数加权聚合; 选中 Profile Group 时, 分子分母都在该 group 的 Query 子集内计算. **提及率默认分母是 `topic.dimension='品类'` 的 Query 总数 (non-brand 口径, 2026-04-16 精化), SoV 分母是"至少命中 1 品牌的 Response 数" (Response 级), 计算时不得串用**. 完整口径 (全量 Query) 仅在品牌详情 / CSV 导出中提供
- 行业排名: 基于聚合后的 PANO 排序 (若选单引擎, 则用该引擎单独评分重算排名; 若选非默认 Profile Group, 标注 "在 {group_name} 画像下的排名"); 小样本禁止出排名
- 趋势图: 每条线为加权聚合值; 引擎多选时可切换 "聚合" / "分引擎叠加" 两种模式; 选中非默认 Profile Group 时趋势图标题追加 "· {group_name}"
- 所有卡片和图表, 当 Profile Group 不是 "全部 Profile" 时, 右上角加一个 "画像: {name}" 小 tag (走 `formatProfileGroup(group, locale)`) 提示当前视角

**⚠️ 已废弃的结构 (不再在面板出现)**:
- ~~Breakdown 4 Metric Tab (总览/提及/情感/引用)~~ — 与品牌页深度重复, 删除
- ~~PANO Score 作为顶级 KPI~~ — PANO 聚合值搬到区块 ③ 趋势图主角位置, KPI 卡改为 提及率/SoV/情感/引用份额/行业排名 五个"可对比的市场位置型"指标
- ~~~~提及率单独作为 KPI~~~~ — **2026-04-16 撤销**: 原判断"提及率与 SoV 强相关, 保留 SoV 一个足够"错误. 提及率 (穿透率, 分母全量 Query) 与 SoV (相对份额, 分母已命中品牌的 Response) 口径不等价, 两者反向分叉时恰恰是诊断信号, 必须同时作为 KPI. 详见本节"口径边界"表

#### 4.6.1a-drilldown 5 KPI 下钻: Drawer + Full-page 双模式 (2026-04-20 新增)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"Drawer 只做..."/"全页承担..."等限制属 Page Scope 约束, 不得泄漏给用户。详见 §4.6.0a。

**A. 背景**

§4.6.1a 定义了面板 5 KPI (提及率 / SoV / 情感 / 引用份额 / 行业排名), 但没规定点击每张卡后用户看什么。Plan S 后 `KpiCard.onClick` 只跳 `/brands/:id?tab=overview` (原地转圈或等价 no-op)。本节补齐**每个 KPI 的深度分析**, 双模式共存:

- **Mode A · Drawer (侧滑抽屉)**: 轻量扫读, 保持主视图 context
- **Mode B · Full-page (专用全页)**: 重深度分析, 可分享 / 截图 / 存书签

**B. 交互契约**

- **单击 KPI 卡** → 打开 Drawer (默认)
- **Drawer 内 "展开全页 ↗" 链接** → 跳 Full-page `/brands/:id/metrics/:kpi`
- **Cmd/Ctrl + 单击 KPI 卡** → 新标签打开 Full-page (跳过 Drawer)
- **URL 直链 / 分享进入 Full-page** → 无 Drawer, 直接 Full-page
- **Daily Digest 的 DeltaCard 点击 (§4.6.1-0.C.②)** → 也开 Drawer (共享组件)

**C. 5 KPI Drawer 内容 schema**

统一三段结构 (保证扫读一致):

| KPI | 段 1: 当前值拆解 | 段 2: 时间维度 | 段 3: 诊断入口 |
|---|---|---|---|
| **提及率** (mention_rate) | (a) 全量 vs non-brand 对比条 (2 值) (b) 按引擎 3 柱 (ChatGPT/豆包/DeepSeek) (c) 按 dimension 3 柱 (品类/品牌/产品 Topic) | Top 10 未命中 Prompt 列表 (近 7 天高频发出但该品牌 0 命中的 Prompt, 按频次 desc) | "在 Topics 里查看全部未命中 →" → `/topics?filter=missed&brand_id=<id>` |
| **SoV** (sov) | (a) 竞品 SoV stacked area (近 30 天时间序列, 主品牌 + Top 4 竞品 + 其他) (b) 按引擎 3 柱 | 近 7 天 Top 3 竞品 SoV 变化 (涨/跌, 带 pp 数字) | "在品牌详情查看竞品对比 →" → `/brands/:id?tab=overview#competition` |
| **情感** (sentiment) | (a) 正/中/负三色分布柱 (百分比) (b) 按引擎 3 组堆叠柱 | 负面 Response 样本 Top 5 (引擎 icon + 时间 + 截断文本, 点击跳 Topics) | "查看全部负面样本 →" → `/topics?sentiment=negative&brand_id=<id>` |
| **引用份额** (citation_share) | (a) Tier 0–4 分布饼 (§4.2.6.B) (b) Authority Share 时序 (§4.2.7.A, 近 30 天) | Top 5 已引用域名 | "处理 Attribution Mismatch →" → `/brands/:id?tab=diagnostics&filter=citation_attribution_mismatch` + "查看 PR 目标 →" → `/brands/:id?tab=content-gap#pr-targets` |
| **行业排名** (industry_rank) | (a) 近 30 天 rank 折线 (Y 轴反转, 低数字=高位) (b) ±1 邻居对比 (3 列: 上邻居 / 我 / 下邻居, 各含 PANO + SoV + 变化) | "距上一名领先 {X} 分" + "距下一名差 {Y} 分" 两行文案 | "查看行业全景 →" → `/industries/:id` + "查看竞品对比 →" → `/brands/:id?tab=overview` |

**D. Drawer 组件契约 (对应 DESIGN_TOKENS C8)**

- 实现: Radix UI Dialog (依赖规则强制) + 自定义 CSS 切换为 drawer slide-in
- 宽度: 560px (桌面), `w-full` (移动端, 全屏底部 sheet)
- 方向: 从右滑入
- Overlay: `bg-black/30 backdrop-blur-sm`
- 关闭: ESC / 遮罩 click / 顶部 X 按钮
- 焦点陷阱 + aria-labelledby: 交给 Radix UI 自动处理
- 动画: 220ms `ease-out` slide + fade
- 顶栏: KPI 名称 + 当前值 + delta pill + "展开全页 ↗" 链接 + "关闭" 按钮
- 底栏: `<KpiDrilldownFooter>` · 3 个次动作 (导出 CSV / 保存截图 / 分享链接) — 与品牌详情右上 action bar 规范一致

**E. Full-page `/brands/:id/metrics/:kpi` 契约**

- 可索引 kpi 值: `mention_rate` | `sov` | `sentiment` | `citation_share` | `industry_rank` (5 个), 任何其他 kpi 值 404
- SSR 友好: `<head>` meta 含 brand name + KPI name + delta (有 brandHint 未登录被 redirect; 登录后返回)
- 顶栏: 面包屑 `品牌 {brandName} / 指标 {kpiLabel}` + "返回品牌概览 ←" 链接 + 时间/引擎/Profile 筛选器 (同品牌详情)
- 主内容区: 把 Drawer 的三段**升级为全页版本**:
  - 段 1: 图表尺寸翻倍, 拆解变量增加 (如提及率 Full-page 额外加"按 Profile Group 拆", Drawer 因空间小不展示)
  - 段 2: 时间序列 Y 轴可切换 (绝对值 / 百分比 / 排名反转), 时间范围可 1d/7d/30d/90d
  - 段 3: 诊断入口按钮升级为内嵌卡片, 卡片即时渲染诊断文本 + 证据 (不跳页)
- 额外: 页脚有"同行业品牌 {kpi} Top 10" 迷你表 (不是 Drawer 的内容), 点击跳对应 `/brands/:id/metrics/:kpi`

**F. 共享组件**

- `frontend/src/components/drilldown/KpiDrilldownDrawer.jsx` — Radix Dialog wrapper, 接 `kpiName` prop 路由到对应内容组件
- `frontend/src/components/drilldown/MentionRateDrilldown.jsx` (Drawer + Full-page 两种 variant prop)
- `frontend/src/components/drilldown/SovDrilldown.jsx`
- `frontend/src/components/drilldown/SentimentDrilldown.jsx`
- `frontend/src/components/drilldown/CitationShareDrilldown.jsx`
- `frontend/src/components/drilldown/IndustryRankDrilldown.jsx`
- `frontend/src/pages/BrandMetricDrilldownPage.jsx` — Full-page 路由组件, 按 :kpi 参数渲染上面 5 个 Drilldown 组件的 `variant="fullpage"` 模式

**G. 数据**

不新增 mock 表。5 个 Drawer 数据来源:
- 提及率: `BRANDS[i].kpiByEngine` + `TOPICS.filter(dimension=品类)` 过滤, 未命中 Prompt 用 `PROMPTS` (mock 已有) 按"该品牌 0 Response" 过滤
- SoV: `SOV_TIME_SERIES` (已有, stacked area) + `BRANDS[i].kpiByEngine`
- 情感: `RESPONSES` (已有) 过滤 brand_mention=true + sentiment 字段, Top 5 按时间 desc
- 引用份额: `AUTHORITY_SHARE_SERIES` + `ATTRIBUTION_MISMATCH_DIAGNOSTIC` (均在 Citation 模块已有, §4.2.7 导入清单)
- 行业排名: `BRANDS` 按 industryId 过滤 + 按 panoScore desc 排序, 找主品牌索引 ± 1

**H. Mixpanel 埋点**

- `#62 kpi_drilldown_opened`: `{ kpi_name: 'mention_rate' | ..., source_page: 'dashboard_digest' | 'dashboard_center' | 'brand_overview', mode: 'drawer' | 'fullpage' }`
- Drawer 内"展开全页 ↗" 点击: 沿用 `kpi_drilldown_opened` 上报 `mode='fullpage'`
- Drawer 段 3 任意诊断入口 click: 沿用现有 `diagnostics_clicked` (§4.11.4 已有)

**I. Harness 拦截**

```bash
# (1) KpiDrilldownDrawer 必须用 Radix Dialog
grep -L 'from "@radix-ui/react-dialog"' frontend/src/components/drilldown/KpiDrilldownDrawer.jsx
# 无匹配 (grep -L 文件未包含该字符串) = 手写 Modal 违反 "生产级依赖" 规则, 拒绝合并

# (2) 5 个 Drilldown 组件必须以 variant prop 双形态复用, 不得 fork 为 XxxDrawer + XxxFullpage 两个文件
ls frontend/src/components/drilldown/ 2>&1 | grep -E '(Drawer|Fullpage)\.jsx$' | grep -v KpiDrilldownDrawer
# 任何输出 = 有人 fork 组件, 拒绝合并

# (3) Full-page 路由必须校验 :kpi 枚举
grep -nE "allowedKpi|VALID_KPI" frontend/src/pages/BrandMetricDrilldownPage.jsx
# 0 匹配 = 未做 404 fallback, 拒绝合并

# (4) Drawer 内必须含 "展开全页" 链接 (跳 Full-page)
grep -nE "metrics/\{?(kpi|kpiName)" frontend/src/components/drilldown --include='*.jsx' -r
# 0 匹配 = Drawer 没有升级到 Full-page 的出口, 拒绝合并
```

**J. i18n 命名空间**

- `dashboard.drilldown.mention_rate.*`
- `dashboard.drilldown.sov.*`
- `dashboard.drilldown.sentiment.*`
- `dashboard.drilldown.citation_share.*`
- `dashboard.drilldown.industry_rank.*`
- 共享 key: `dashboard.drilldown.common.expand_fullpage` / `close` / `export_csv` / `save_screenshot` / `share_link`

zh-CN + en-US 齐全 (按 §4.10.4a i18n 覆盖矩阵)。

#### 4.6.1b 品牌详情页 (/brands/:id) — 单品牌深度视角

> **⚠️ 2026-04-20 SUPERSEDED by §4.6-IA-v2**: 本节 4 子 Tab (概览/诊断/产品/引擎对比) 结构被**展平**为 Brand Mode 9 个 sub-view: 分析组 7 项 (总览/可见性/Topics/情感/引用/产品/竞品) + 运营组 2 项 (诊断/报告)。引擎对比从 Tab 改为全局筛选条的 Segmented Control (§4.6-IA-v2.E)。路由 `/brands/:id` 301 重定向到 `/brand/overview?brandId=:id`。本节单 Tab 的功能规格 (Overview 区块 / Diagnostics 列表 / Products BCG) 仍适用, 只是挂载的 sub-view 改名并拆分。

**定位**: 回答"这一个品牌健康度如何、哪里好、哪里坏、为什么"。所有**单品牌**的深度分析集中在此, 面板与此不重复。

**入口路径**:
1. 面板 SoV 饼图 / 竞品四象限点击气泡 (§4.6.1a) → 该品牌 Brand Detail
2. 面板 KPI 卡点击"→ 查看品牌详情" → 主品牌 Brand Detail
3. `/brands` 列表页点击行 → 对应品牌 Brand Detail
4. **行业探索视图点击品牌节点 / 行 (§4.1.1b) → 目标品牌 Brand Detail** (`?from=industry&industryId=...`, 可能是未监控品牌)
5. 产品详情页面包屑 / 排行榜 / 公开体检报告链接等 → 目标品牌 Brand Detail
6. 未登录用户直链 `/brands/:id` (公开只读, SEO 友好)

**三种访问状态 (2026-04-16 新增, 基于 §4.1.2a 按钮状态机)**:

| 状态 | 识别条件 | 顶部 Banner | 数据展示 | 一键按钮 |
|------|---------|------------|---------|---------|
| **A. 监控中** | 品牌 ∈ 当前 Project (primary 或 competitor) | 无 Banner | 完整 (含基于 Project 竞品的相对指标 / 历史诊断) | §4.1.2a 状态 #1 (主品牌) or #2 (竞品) |
| **B. 未监控 (已登录)** | 品牌 ∉ 当前 Project, 或用户无 Project | 浅灰信息 Banner: "{brand} 暂未加入你的监控 · 数据来自 GENPANO 平台全量采集 (每日更新). 加入监控后系统会持续追踪变化并生成针对你的诊断 / Branding Narrative / 周报" + 次要 CTA 链接 "什么是监控?" | 完整展示 (平台数据全量), 竞品对比降级为 "vs 行业 Top 5" | §4.1.2a 状态 #3 / #4 / #5 |
| **C. 未登录** | 无 session | 顶部浅蓝公共 Banner: "你正在浏览 GENPANO 的公开数据 · 免费注册后可持续追踪此品牌、接收诊断告警、生成体检报告" + 右侧 CTA "免费注册监控" | 完整只读; 页脚固定 CTA 条 "免费注册持续监控 {brand} →" | §4.1.2a 状态 #6 |

**数据降级规则 (状态 B / C)**:
- **概览 Tab**: PANO 环 + V/S/R/A + 30 天趋势 + 提及位置分布 — 全部可显示 (平台数据)
- **诊断 Tab**: 完整展示该品牌所有 P0/P1/P2 诊断 (Frank 2026-04-16 确认: "完全展示 + upsell 条"), 列表顶部黄色 upsell 条 "加入监控后系统会持续追踪这些诊断的演变趋势 + 周报中重点提醒 + Branding Narrative 深度叙事"
- **产品 Tab**: BCG 矩阵 + 产品列表正常 (产品数据也是平台全量)
- **引擎对比 Tab**: 3 引擎卡片正常, 差异洞察 LLM 文案正常
- **竞品对比降级**: 当前页面所有"竞品"相关的 tooltip / 副标题 / 对比基线从 "vs 我的 Project 竞品" 降级为 "vs 行业 Top 5" (平台可算), 并在 tooltip 加注 "(行业基线, 因尚未监控)"

**顶栏 (所有状态共用)**:
```
┌────────────────────────────────────────────────────────────────────┐
│ ← 返回 {上一页} │ 品牌: {name ▾} (仅监控中状态展示下拉切换竞品)     │
│ 时间 [30天▾]  引擎 [全部✓]  画像 [全部▾]                           │
│                         [🔗 分享体检报告 PDF] [+ 加入竞品监控]       │
└────────────────────────────────────────────────────────────────────┘
```

- 品牌切换器: 仅监控中 (状态 A) 展示 dropdown (列出当前 Project 主品牌 + 竞品); 未监控 / 未登录时折叠为静态品牌名 (避免假装用户有 Project 的误导)
- 时间/引擎/画像筛选与面板相同契约 (§4.6.1a), 通过 URL 持久化 (`?range=...&engines=...&profileGroup=...`)
- **返回面包屑**: 按 URL query `?from=industry|dashboard|brands|product` 决定返回目标; 未提供 `from` 时默认 "← 返回面板"
- **"+ 加入竞品监控"按钮**: 按 §4.1.2a 状态机渲染 (6 个状态, 包含只读 badge / 可点 CTA / 下拉跨行业 / 创建 Project / 免费注册)

**子 Tab (5 个, 2026-04-17 扩为 5 Tab 含 content-gap)**:

| Tab | URL | 内容 |
|-----|-----|------|
| **概览** (默认) | `?tab=overview` | PANO Score 大环 + V/S/R/A 4 维度条形 + PANO 30 天趋势 + 提及位置分布 + 提及明细摘要 (Top 20) + **Authority Share 时序图 (§4.2.7.A)** + **Authority Radar + Same-Group 共享卡 + Acquisition 时间轴 (§4.2.7.D, v1.1)** |
| **诊断** | `?tab=diagnostics` | 该品牌 Diagnostics 列表 (P0/P1/P2 分组, 可过滤, **含 `citation_attribution_mismatch` 新 Alert type §4.2.7.A**) + 评分卡下载 (体检报告 PDF 入口) |
| **内容缺口** ⭐ 新增 | `?tab=content-gap` | Topic 级 mention-but-no-citation 缺口表 + 页面类型分布对比 + Top 可引用页面对比 + **PR 候选列表 (§4.2.7.C) + Tier 2 覆盖矩阵 + KOL 评分卡** (实施细节与反向算法见 §4.2.7.B / §4.2.7.C) |
| **产品** | `?tab=products` | BCG 矩阵 (详见 4.6.1d) + 产品列表 (可排序/分页, 列出 name/nameEn/SoV/情感/Top Prompt 命中数) |
| **引擎对比** | `?tab=engines` | 3 引擎并排卡片, 每张卡展示 提及率/情感/引用次数/提及位置分布; 引擎对比表 + 差异洞察文案 |

**🚫 品牌详情页不做**:
- 跨品牌市场份额饼图 (那是面板区块 ②)
- 竞品四象限 (那是面板区块 ②)
- 跨品牌 PANO 趋势对比 (那是面板区块 ③)
- Simulator / What-if 模拟 — 独立页 `/brands/:id/simulator` 承载 (§4.2.7.E), 避免 Tab 切换+滑杆操作相互污染; 从概览右上角按钮 "模拟 Authority 提升" 跳入

**与体检报告 PDF 的关系**: 概览 + 引擎对比 + 诊断 三个 Tab 的数据正是体检报告 PDF (4.6.3) 的 P2/P3/P5 内容源; UI 上点击顶栏"分享体检报告 PDF" 直接触发 PDF 生成, 保证两者数据一致。**内容缺口 Tab (§4.2.7.B) 不纳入体检 PDF** — 它是操作工具, 不是定论陈述, 纳入会稀释 PDF 的 "诊断 → 方向 → 不干预后果" 叙事链。

#### 4.6.1c 竞品四象限 (气泡图) 规范

**位置**: 面板 区块 ② 右侧 (与 SoV 饼图并列), 面板独占组件, 不在品牌页出现

**设计参考**: Semrush Brand Performance, BCG Matrix (经典 2×2)

**坐标系**:
- **X 轴** = **Share of Voice (SoV)**, 范围 `0 ~ max(行业 Top 5 SoV) × 1.1` (留 10% 边距)
- **Y 轴** = **情感得分 (Sentiment)**, 范围 `[-1, 1]`, 0 为中位参考线
- **气泡大小** = **引用份额** (引用次数占比), 半径 ∈ [8px, 32px], 线性映射
- **气泡颜色**:
  - 主品牌: 品牌主色 (`var(--color-accent)`) + 黑色描边 + 标签加粗
  - 竞品: 灰阶, 仅在 hover 时高亮

**象限命名** (四角文字标注, 取自典型战略定位):
```
              情感 ↑
              |
              |
  追赶者      |     领跑者
  (SoV低      |    (SoV高
   但情感好)  |    情感好)
              |
  ─────────── + ───────────→ SoV
              |
  警示品牌    |     高光但存风险
  (SoV低      |    (SoV高
   情感差)    |    情感差)
              |
              |
              情感 ↓
```

- **领跑者** (右上): 行业优势者, 目标象限
- **高光品牌** (右下): 曝光大但情感差, 存在负面舆情风险
- **追赶者** (左上): 小而美, 有成长机会
- **警示品牌** (左下): 冷门 + 差评, 最差象限

**数据范围**: 项目内主品牌 + 所有竞品 (来自 `Project.competitorBrandIds`), 最多显示 8 个气泡 (超过则保留 SoV Top 8)

**交互**:
- Hover 气泡 → tooltip 显示 `{品牌名} | SoV X% | 情感 Y | 引用 Z 次`
- 点击气泡 → 进入对应品牌详情页 `/brands/:id`
- 右上角开关: `圆形气泡 / 品牌 logo` 切换 (品牌 logo 模式: 气泡内嵌 logo, 需 `Brand.logoUrl` 字段, 可 Phase 2 做, MVP 先做圆形)

**实现库**: Recharts `<ScatterChart>` + `<ZAxis>` 支持气泡大小映射, 参考已有 `EngineTrendChart` 的色板规范 (`var(--color-chart-*)`). 禁止手写 SVG。

**空态**:
- 竞品不足 2 个: 显示 "至少配置 2 个竞品才能展示竞争格局 → [项目设置]"
- 所有品牌 SoV 均为 0: 显示 "当前时间/引擎筛选下无提及数据, 尝试扩大时间范围"

#### 4.6.1d 产品详情 (/brands/:id/products/:productId)

> **⚠️ 2026-04-20 SUPERSEDED by §4.6-IA-v2**: 路径改为 `/brand/products/:productId` (当前 brandId 由 BrandPicker context 经 `?brandId=` query 携带); SSR 友好 + 独立 URL + OG 图能力保留。旧路径 301 重定向到新路径。产品列表入口从"品牌详情 ?tab=products"改为"Brand Mode · 产品 sub-view" (`/brand/products`)。

**定位**: 独立 URL, SSR 渲染, SEO 友好 (产品名 × 品牌名可作为长尾关键词落地页). 从品牌详情页 "产品" Tab 的 BCG 矩阵或列表进入。

**URL 规范**:
- 权威路径: `/brands/:brandId/products/:productId`
- 别名 (Phase 2): `/p/:productSlug` → 301 重定向到权威路径

**页面内容**:
- 产品名 + 品牌名 + 品类面包屑 (Industry → Category → Product)
- 产品 PANO 子指标 (如适用: SoV / 情感 / 引用)
- **推荐语境分类** (该产品被 AI 回答提及时的典型场景): 饼图或水平柱状, 分类来自 Response 挖掘 (例: "干皮推荐", "送礼首选", "性价比")
- **关系视图**: 从 `kg_product_relations` 取出:
  - SUBSTITUTES (替代品) — 灰色关系线
  - PAIRS_WITH (搭配品) — 蓝色关系线
  - UPGRADES_TO (升级款) — 绿色关系线
  - BUDGET_ALT_OF (平替) — 紫色关系线
  - 用 D3 force simulation 或 AntV G6 渲染简化的局部关系图 (≤ 15 节点)
- **Prompt 命中列表**: 提到该产品的 Top 20 Prompt, 按命中次数降序, 点击下钻到 Topics 页的 Query 详情

**BCG 矩阵 (在品牌详情的 "产品" Tab 内)**:
- 2×2 矩阵, X 轴 = 产品 SoV (市场份额维度), Y 轴 = 增长率 (近 30 天 SoV 环比)
- 四象限: 明星 / 金牛 / 问题 / 瘦狗 (经典 BCG 命名)
- 气泡大小 = 产品提及绝对次数
- 点击气泡进入产品详情

**交互规则**:
- 所有组件受"时间 / 引擎"筛选联动
- 产品页有"返回品牌"面包屑
- 产品页 URL 直链分享可被搜索引擎索引 (meta tags + OG image 走 @vercel/og)

#### 4.6.1e 行业视角 (/industry/overview) — 行业全景 Plan S v3 (2026-04-20 傍晚晚间: 从 8 段瘦身至 6 段)

> **⚠️ 2026-04-20 演化记录**:
> - **v1 (上午)**: Plan S 5 段式, 路径 `/industries/:id`
> - **v2 (傍晚)**: Frank 反馈"行业页内容敷衍, 从用户角度补内容", 在 5 段式基础上追加 **⑥ 品牌集团版图 / ⑦ Topic 热度 Heatmap / ⑧ Top 10 引用源**, 共 8 段
> - **v3 (傍晚晚间, 本节生效版)**: Frank 反馈"你可以考虑把第一页拆分一下" — Overview 不应堆八段, 应让 Ranking/Topics 页真正承载其相应叙事。**段 ⑦ Topic 热度 Scatter 移到 §4.6.1g Topics 页 (作新段 ③)**, **段 ⑧ Top 10 引用源 移到 §4.6.1f Ranking 页 (作新段 ⑧)**。本页保留 6 段核心: ①-⑤ Plan S 原版 + ⑥ 集团版图 (最适合 Overview 的行业级横截面, 与 Topic 叙事 / 引用源叙事互不重复)。

> **⚠️ 同日 SUPERSEDED by §4.6-IA-v2**: 本节内容保留, 渲染锚点从 `/industries/:id` 迁移到 `/industry/overview?industryId=:id` (Industry Mode · 总览 sub-view)。Industry Mode 侧栏结构见 §4.6-IA-v2.C.3。旧路径 301 重定向到新路径。

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"行业视角只回答..."等限制属 Page Scope 约束, 不得泄漏给用户。详见 §4.6.0a。

**A. 定位**

回答: "整个行业长什么样? 品牌位置分布如何? 谁领跑谁跟跑? 集团版图如何切? 行业现在在聊什么? 我该打哪些媒体?"

**与 /brand/overview (品牌概览) 的边界**:
- 品牌概览回答"我品牌在行业的位置 (vs 竞品 Top 3)"
- 行业视角回答"行业整体格局" (全行业品牌分布, P25/P50/P75 箱线, Top 10 leaderboard, 集团版图, Topic 热度, Top 引用源)

**与 /brand/overview (Brand Mode 日常工作视角) 的边界**:
- Brand Mode 总览回答"我的品牌最近发生了什么"
- 行业视角回答"行业静态格局与长期趋势" (季度复盘视角, 不是日常工作视角)

**B. 六段结构** (v3, 锚点: `design/prototype-plan-s.html` "Dashboard View" 段 + 集团版图一段)

| 区块 | 内容 | 图表 / 交互 |
|---|---|---|
| ① 筛选栏 | 行业 (单选, URL `industryId` 绑定) + 时间 (1d/7d/30d/90d) + 引擎 (多选) + Profile Group (§4.2.3a) | Sticky top, 与 Brand Mode FilterBar 同规; 复用 `<BrandAnalysisFilterBar>` |
| ② Hero 行业格局 | 3 个 count KPI: 覆盖品牌数 / 活跃 Topic 数 / 品类数 (3 级) + 行业名 + 近 30 天全行业 Response 总数 | 无卡片边框, 大数字 + 小下标, 灰底浅分隔 |
| ③ **5 KPI 行业均值 + IQR 箱线分布 (本页独有)** | 5 张箱线卡 (提及率 / SoV / 情感 / 引用份额 / 行业排名), 每卡含: 箱线图 (P25 / P50 / P75 / 异常点) + 主品牌 ▲ marker (登录 + 有主品牌时) + "距行业中位数 {+/-pp}" 文案 | Horizontal box plot, Recharts 自定义 `<BoxPlot>` 或 `<ScatterChart>` 模拟 |
| ④ Top 10 Leaderboard + SoV Pie | 左表右饼: 表按任一 KPI 排序 (默认 PANO desc), 饼 = 全行业 SoV 分布 (Top 6 真实品牌 + "其他" 合并). 表行 click → `/brand/overview?brandId=:id` | TanStack Table + Recharts PieChart; ▲ 标记"我的品牌" 行; 饼的"其他"片禁大于任一真实品牌 (§DESIGN_TOKENS C3) |
| ⑤ 行业趋势 + 异动 Top 3 | 上: 行业 PANO 均值近 30 天折线 + 主品牌 PANO 折线叠加 (区分色). 下: 近 7 天 PANO 跳点最大的 Top 3 品牌卡 (涨幅 / 跌幅各 3, 共 6 张; 或合并 Top 3 按 abs desc) | Recharts LineChart (双线); 异动卡水平滑条 |
| ⑥ **品牌集团版图** | 按 `BRANDS.parentCompany` 聚合, 每个集团卡: 集团名 + 旗下品牌数 + 合计 SoV + 合计提及率均值 + 迷你气泡图 (旗下品牌按 panoScore 排) + 最大品牌名. 默认按合计 SoV 降序展示 Top 5 集团 + "其他集团"合并 | Tailwind Card grid, 3 列; 气泡色沿用 Brand Mode sentiment palette; 点击集团卡 → 展开 modal 显示全部旗下品牌 |

> **⚠️ v3 迁移**: 原 v2 段 ⑦ Topic 热度 Scatter 迁至 §4.6.1g Topics 页 (新段 ③), 原 v2 段 ⑧ Top 10 引用源 迁至 §4.6.1f Ranking 页 (新段 ⑧). 迁移后组件 `IndustryTopicHeatScatter` / `IndustryTopCitationDomains` 保留并被新宿主页引用, 不删。

**C. IQR 计算 (段 ③ 核心)**

**C. IQR 计算 (段 ③ 核心)**

禁止新增 mock exports。实时从 `BRANDS` 过滤 `industryId === currentIndustryId` 后按每个 KPI 计算:

```ts
function computeIQR(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;
  const p = (k: number) => sorted[Math.floor((k / 100) * (n - 1))];
  const p25 = p(25), p50 = p(50), p75 = p(75);
  const iqr = p75 - p25;
  const lowerFence = p25 - 1.5 * iqr;
  const upperFence = p75 + 1.5 * iqr;
  const outliers = sorted.filter(v => v < lowerFence || v > upperFence);
  return { p25, p50, p75, min: sorted[0], max: sorted[n - 1], outliers };
}
```

样本量约束:
- `n < 5`: 不画箱线, 改为横向点阵 (每个品牌一个点) + "样本量小" tag
- `n < 3`: 只显示均值, 不显示分布

**D. 主品牌 ▲ 标记**

- 未登录: **不会到达本页** (Auth-Required §4.1.1-gate, 已重定向 /register)
- 登录 + 零 Project: 段 ③ 的 ▲ 不渲染 (用户还没告诉我们"我是谁"), 但页面其他部分完整呈现; 段 ③ 卡片顶部显示"创建项目并选择主品牌后, 这里会标记你的位置 →" + 次 CTA 跳 `/projects/new`
- 登录 + 有 Project: ▲ 在箱线上对应位置绘制, hover 显示主品牌名 + 具体 KPI 值

**E. 数据来源 (零新增 Industry 专用 mock)**

- 段 ② count: `BRANDS.filter(b => b.industryId === id).length` + `TOPICS.filter(t => t.industryId === id).length` + `KG_CATEGORIES.filter(c => c.industryId === id).length` (或 CATEGORIES 对应三级)
- 段 ③ 箱线: 上述 `computeIQR` 实时, 对 BRANDS 过滤后的 5 KPI 数组分别计算
- 段 ④ Top 10: 同一过滤后 sort by kpi desc slice(0, 10); SoV Pie: 同过滤后 + mock 现有 `sov` 字段, Top 6 + 其他
- 段 ⑤ 趋势: `INDUSTRY_TREND_SERIES` (已有) + 主品牌 `panoTrend`; 异动: 按 `Math.abs(panoDelta7d)` desc; 若缺 `panoDelta7d` 字段, 用 `parseFloat(change)` 绝对值
- **段 ⑥ 集团版图**: `aggregateByGroup(BRANDS)` (见 `lib/industry/statistics.js`), 每组聚合 `{ brandCount, totalSov, avgMention, maxBrand, brands }`. `parentCompany` 字段在 BRANDS 已存在 (每条 Brand 一个). Top 5 集团 + 其他合并
- (原 v2 段 ⑦ Topic 热度 / 段 ⑧ Top 10 引用源数据源章节见 §4.6.1g / §4.6.1f)

**E.1 遗留 Dead Exports 清理 (v2 随改)**

以下两个 mock 导出在 mock.js 存在但无任何 import, 与本节 §G.1 harness 冲突, **v2 实施时一并删除**:
- `INDUSTRY_KPI_DISTRIBUTION` (line 2082)
- `INDUSTRY_TRENDING_EVENTS` (line 2090)

删除动作不影响任何现有渲染; 本页 v2 的 IQR 改从 BRANDS 实时计算, 异动改从 BRANDS.change 排序, 与旧派生 mock 无依赖。

**F. i18n 命名空间**

- `industry.header.*` (段 ①)
- `industry.hero.*` (段 ②)
- `industry.distribution.*` (段 ③ 箱线 + ▲ 文案 + "样本量小" tag)
- `industry.leaderboard.*` (段 ④ 表头 + 饼图 legend)
- `industry.trend.*` + `industry.movers.*` (段 ⑤)
- **`industry.group.*` (段 ⑥)**: v2 新增. `card.brand_count` / `card.total_sov` / `card.max_brand` / `others_label` / `modal.title`
- **`industry.topics_heat.*` (段 ⑦)**: v2 新增. `axis.mention_count` / `axis.sentiment` / `legend.emerging` / `legend.normal` / `tooltip.emerging_tag`
- **`industry.citations.*` (段 ⑧)**: v2 新增. `header.domain` / `header.citations` / `header.tier` / `header.brands_count` / `header.i_attributed` / `tier_label.1/2/3/4` / `you_not_attributed`

共享: `industry.anchor.no_project_cta` (段 ③ 空 ▲ 态下 CTA), zh-CN + en-US 齐全。

**G. Harness 拦截**

```bash
# (1) 禁止 Industry 页专用派生 mock — IQR / 排行 / 异动 三类必须从 BRANDS 实时派生
#     (v2 允许复用的共享 mock: INDUSTRY_TOPIC_HEATMAP, TOP_CITED_DOMAINS — 它们不是 Industry 专用派生, 是跨页共享数据)
grep -nE "^export const INDUSTRY_(KPI_DISTRIBUTION|TRENDING_EVENTS|LEADERBOARD|IQR)" frontend/src/data/mock.js
# 任何输出 = 有人为 Industry 页新建派生 mock, 拒绝合并 (会与 BRANDS 真相源分叉)

# (2) ▲ marker 仅在有主品牌时渲染
grep -nE "BoxPlotPrimaryMarker|IndustryPositionMarker" frontend/src/pages/industry/IndustryOverviewPage.jsx
# 检查该组件在使用处必须被 `{primaryBrand && (<...>)}` 守卫; 走现有 §4.6.0a JSX grep

# (3) IQR 公式统一走 computeIQR 工具函数, 不允许每张卡重算
grep -rnE "sort\(.*a\s*-\s*b\).*Math\.floor\(0\.(25|5|75)" frontend/src/pages frontend/src/components --include='*.jsx'
# 任何输出 = 有人 inline 计算 percentile, 必须改走 computeIQR

# (4) SoV Pie "其他" 片不得大于 Top 6 的最小真实片 (DESIGN_TOKENS C3, 运行时 assertion 已覆盖 scripts/check-data-contracts.mjs)

# (5) v2 集团聚合必须走 BRANDS.parentCompany, 禁新增 `BRAND_GROUPS` 派生 mock
grep -nE "^export const BRAND_GROUPS\b|^export const INDUSTRY_GROUPS\b" frontend/src/data/mock.js
# 任何输出 = 有人绕开 parentCompany 新建集团 mock, 拒绝合并

# (6) v2 段 ⑦ 必须复用 INDUSTRY_TOPIC_HEATMAP, 禁拷贝副本
grep -nE "^export const INDUSTRY_(HEATMAP|TOPIC_HEAT)_V2\b|^export const TOPIC_HEATMAP_INDUSTRY\b" frontend/src/data/mock.js
# 任何输出 = 拷贝 heatmap 副本, 拒绝合并
```

**H. 组件清单 (v3 Overview 7 组件)**

- `frontend/src/pages/industry/IndustryOverviewPage.jsx` (重写, 取代旧 `IndustryPage.jsx`; 旧文件如存在则删或 301 重定向)
- `frontend/src/components/industry/IndustryHero.jsx` (段 ②)
- `frontend/src/components/industry/IndustryDistributionCard.jsx` (段 ③ 单张箱线卡, 5 张 map 实例)
- `frontend/src/components/industry/IndustryLeaderboardTable.jsx` (段 ④ 表, 用 TanStack Table)
- `frontend/src/components/industry/IndustrySovPie.jsx` (段 ④ 饼)
- `frontend/src/components/industry/IndustryTrendChart.jsx` (段 ⑤ 折线)
- `frontend/src/components/industry/IndustryMoversRow.jsx` (段 ⑤ 异动水平滑条)
- `frontend/src/components/industry/IndustryGroupMap.jsx` (段 ⑥)
- `frontend/src/lib/industry/statistics.js` (`computeIQR` / `groupBy` / `topByField` / `topByAbsField` / `aggregateByGroup`)

**v3 迁移说明**: `IndustryTopicHeatScatter.jsx` 和 `IndustryTopCitationDomains.jsx` 保留在 `components/industry/`, 新宿主页是:
- `IndustryTopicHeatScatter` → 被 `IndustryTopicsPage.jsx` 引用 (段 ③, §4.6.1g)
- `IndustryTopCitationDomains` → 被 `IndustryRankingPage.jsx` 引用 (段 ⑧, §4.6.1f)

**I. Mixpanel 埋点**

- 沿用 `#7 industry_view_loaded { industry_id, view_mode: 'panorama' }` (已有事件 #7, view_mode 新增 `panorama` 值; 原 `graph/list` 保留)
- 段 ③ ▲ 空态 CTA click: `#12 project_create_click { source: 'industry_anchor_cta' }` (已有 #12, source 追加该值)
- 段 ④ Leaderboard 行 click: 沿用 `brand_detail_open { source: 'industry_leaderboard' }` (已有)

**J. MVP 边界**

- 品类树 drill-down (点击"美妆"下钻到"彩妆") — Phase 2, 本节只做行业级
- 跨行业对比 — 不做; 用户选单行业即可
- 时间线回放 (看行业格局如何演变) — Phase 2
- 导出整行业 CSV — 已在 §4.6.4 exportType `industry_panorama` 覆盖
- 段 ⑥ 集团版图的"集团 Logo / 集团介绍" — MVP 只展示集团名 + 聚合指标, Logo/介绍需独立 assets pipeline, Phase 2
- 段 ⑦ Topic heat 时序演变 (同一 Topic 近 30 天热度曲线) — Phase 2, MVP 静态快照
- 段 ⑧ 引用源反查 (点击域名展开被引用的具体页面列表) — 走 §4.6.1b Brand Detail Citations Tab, 本页不承载

#### 4.6.1f 行业排行榜 (/industry/ranking) — 深度扩展 (2026-04-20)

> **⚠️ 2026-04-20 扩展记录**: Frank 反馈 "Industry Mode 除 Overview 以外三 tab 内容敷衍 + 有 broken field reference"。本节以"行业视角下单品牌找不到的多口径排名叙事"为锚点设计 7 段结构, 严格区别于 §4.6.1e 段 ④ 的 "Top 10 静态快照"。

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"本页不做...请去 /industry/overview 查看"等限制仅用于指导实施, 严禁以 i18n key / JSX 文本节点形式呈现给最终用户。

**A. 定位**

回答: "谁在榜单里动 / 同一个品牌换个口径排第几 / 我弱在哪个维度 / 不同引擎上谁赢 / 国际高端 vs 大众高端分赛道怎么排?"

**与 §4.6.1e 段 ④ (Overview Top 10) 的边界**:
- Overview 段 ④: 单一 KPI 排序 + SoV 饼图 (静态快照, 一眼看谁领跑)
- Ranking: 多口径交叉 / 动态趋势 / 引擎分位 / 赛道分层 (结构化深挖, 支持"为什么 / 谁在变")

**B. 七段结构**

| 区块 | 内容 | 图表 / 交互 |
|---|---|---|
| ① 筛选栏 | 复用 `<BrandAnalysisFilterBar>` (时间 + 引擎 + Profile Group) | Sticky top, URL state via `useBrandAnalysisFilters` |
| ② Ranking Hero + "我的位置" Panel | 行业名 + 覆盖品牌数 / 集团数 / 平均 PANO 三 count; 主品牌存在时并列展示 "我综合 #N / SoV #N / 引用 #N / 情感 #N + 近 30d ±N 位 + 最弱维度 XXX" | 无卡片边框, 灰底浅分隔; "我的位置" 卡右侧跳 `/brand/overview?brandId=:primary` |
| ③ **Tier 分层 Breakdown (本页独有)** | 4 档: Top 3 (S 级头部) / 4-10 (腰部 A-B 级) / 11-25 (挑战者) / 26+ (尾部). 每档: 卡片高度体现档量级, 内含品牌数 / PANO 均值 / 合计 SoV / Top 2 品牌名 | 4 张并排 Tier 卡, 高度按档内 SoV 总和等比; Tier 1 大字高亮, Tier 4 浅灰底. 点击档展开"查看该档所有品牌"抽屉 |
| ④ **多指标交叉排名矩阵 (本页独有)** | Top 15 品牌 × (PANO / SoV / 引用 / 情感) 4 列排名 + "排名离散度 σ" 列 (4 列 rank 的标准差, 高 = 综合排但单项弱). 点击任何列排序; 主品牌行高亮 | TanStack Table; 每 cell 渲染 `#N` + 彩色 pill (top-3 绿 / mid 灰 / bottom 红); hover 该行: Radar mini chart 4 维可视化 |
| ⑤ **30d 排名异动 Top 5 涨/跌 (本页独有)** | 上涨 Top 5 / 下跌 Top 5 两列并排卡. 每卡: 品牌名 + Δ (from #M → #N) + 迷你 sparkline (30 点 rankTrend, 倒置 Y 轴) + 环比 PANO change | Framer Motion 进场; 涨卡绿 / 跌卡红; hover 卡: 底部显露"主要驱动"一行 (绝对值最大的 KPI 变动) |
| ⑥ **引擎分位矩阵 (本页独有)** | Top 10 品牌 × 3 引擎 (ChatGPT / 豆包 / DeepSeek). 格子 = 该引擎上的排名 `#N`, 色深表达位置 (排名越靠前色越深). 每行尾列 "最大分位差 ΔMax" (3 引擎最大 - 最小) | 自定义 heatmap grid; 色带: sequential `--color-heatmap-seq-0..5`; 行 click: 跳 `/brand/overview?brandId=:id&engines=:engine` 直接带引擎筛选 |
| ⑦ **赛道分层 Ranking** | 按 `positioning` 字段分三列: 国际高端 Top 5 / 大众高端 Top 5 / 小众/新锐 Top 5. 每列独立排名 #1-5, 每行: 品牌名 + PANO + change Δ + "→" 链接 | 三列等宽 grid; 列标题用 Badge 表达定位; 行 click 跳 Brand Mode |
| ⑧ **Top 10 引用源** (v3 从 §4.6.1e Overview 迁入) | 行业最权威的 10 个引用域: 域名 / 引用数 / 份额 / 权威 Tier badge / 覆盖品牌数 / "我是否被此源引用" Y/N. 按引用数降序 | 复用组件 `<IndustryTopCitationDomains>`; 复用 `TOP_CITED_DOMAINS` mock |

**C. 数据派生 (零新增 mock)**

- 段 ②③④⑦: 直接 `BRANDS.filter(b => b.industryId === id)` + `sort`, 无派生 mock
- 段 ④ 离散度 σ: `statistics.rankDispersion(brand, allBrands, ['panoScore','sov','citationShare','sentiment'])` — 对 4 个 KPI 分别排名, 计算 rank 数组标准差
- 段 ⑤ 30d 异动: `statistics.rankingDelta30d(brand)` — 用 `b.id` hash 作 seed 合成 `{ rankFrom, rankTo, trend[30], primaryDriver }`, 确保同一品牌结果稳定; `rankFrom`/`rankTo` 围绕 `b.ranking` ± 5 位, 有符号变化
- 段 ⑥ 引擎分位: `statistics.rankingByEngine(brand)` — hash seed 合成 `{ chatgpt, doubao, deepseek }` 3 值, 都围绕 `b.ranking` ±3 位; `rankingByEngine` helper 对外
- 段 ⑦ 赛道: 直接 filter `b.positioning`, 映射到 3 组 (国际高端 / 大众高端 / 小众|新锐|设计师|未标记)
- **段 ⑧ Top 10 引用源 (v3 迁入)**: 直接使用 `TOP_CITED_DOMAINS` (已存在 mock.js line 1807), 前端按 `citations` 降序取 Top 10; "我是否被此源引用" 由 `brandsAttributed.includes(primaryBrandId)` 实时计算

**D. Harness 拦截**

```bash
# (1) 禁止新增 Ranking 专用派生 mock
grep -nE "^export const (INDUSTRY_RANKING|RANKING_DELTA_30D|RANKING_BY_ENGINE|TIER_BREAKDOWN|SEGMENT_RANKING)" \
  frontend/src/data/mock.js
# 任何输出 = 派生数据泄漏到 mock, 必须改走 statistics.js helpers

# (2) Ranking 页 h1 必须 text-xl (C14-1 密度)
grep -nE "<h1[^>]*text-(2xl|3xl|4xl)" frontend/src/pages/industry/IndustryRankingPage.jsx \
  | grep -v "// C14-exempt"

# (3) Ranking 页必须 import FilterBar (C10-1 对齐 Industry Mode)
grep -q "BrandAnalysisFilterBar" frontend/src/pages/industry/IndustryRankingPage.jsx \
  || echo "missing FilterBar: IndustryRankingPage"

# (4) 禁止 BRANDS 字段 typo (primaryName / isPrimary / categoryName 都不存在, 是历史敷衍)
grep -nE "b\.(primaryName|isPrimary|categoryName)" \
  frontend/src/pages/industry/IndustryRankingPage.jsx

# (5) 禁止 `Math.round(v * 100)` 应用到 sov / citationShare (这两个字段已是 0-100)
grep -nE "Math\.round\([^)]*(sov|citationShare)[^)]*\*\s*100\)" \
  frontend/src/pages/industry/IndustryRankingPage.jsx
```

**E. i18n 命名空间**: `industry_ranking.*`
- `.hero.*` (段 ②): `brand_count` / `group_count` / `avg_pano` / `my_position_card_*`
- `.tier.*` (段 ③): `top3_label` / `mid_label` / `challenger_label` / `tail_label` / `card_brand_count` / `card_avg_pano` / `card_total_sov` / `card_leaders`
- `.matrix.*` (段 ④): `col_rank_pano` / `col_rank_sov` / `col_rank_citation` / `col_rank_sentiment` / `col_dispersion` / `tooltip_radar_title`
- `.movers.*` (段 ⑤): `gainers_title` / `losers_title` / `delta_format` / `primary_driver_label`
- `.engine_matrix.*` (段 ⑥): `col_chatgpt` / `col_doubao` / `col_deepseek` / `col_max_delta`
- `.segments.*` (段 ⑦): `segment_global_premium` / `segment_mass_premium` / `segment_niche` / `empty`

**F. 组件清单 (6 新 + 1 复用)**

- `frontend/src/components/industry/IndustryRankingHero.jsx` (段 ②)
- `frontend/src/components/industry/IndustryTierBreakdown.jsx` (段 ③)
- `frontend/src/components/industry/IndustryMultiMetricMatrix.jsx` (段 ④, 含 rank pill + hover radar)
- `frontend/src/components/industry/IndustryRankingMoversGrid.jsx` (段 ⑤)
- `frontend/src/components/industry/IndustryEngineRankingMatrix.jsx` (段 ⑥)
- `frontend/src/components/industry/IndustrySegmentRanking.jsx` (段 ⑦)
- `frontend/src/components/industry/IndustryTopCitationDomains.jsx` (段 ⑧, **复用** 自 §4.6.1e v2 实现, v3 迁入本页)
- `frontend/src/lib/industry/statistics.js` 扩展 3 helper: `rankingDelta30d` / `rankingByEngine` / `rankDispersion`

**G. MVP 边界**

- Tier 4 "查看该档所有品牌" 抽屉 — Phase 2 (MVP 点击仅跳 Brand Mode)
- 段 ⑥ 引擎分位的"引擎差异归因" (为什么 DeepSeek 比 ChatGPT 低 5 位) — Phase 2, 接真实引擎采集后做
- 段 ⑦ 赛道定义由 Admin 后台维护 — MVP 硬读 BRANDS.positioning

---

#### 4.6.1g 行业 Topic 格局 (/industry/topics) — 深度扩展 (2026-04-21, v3.2 终态)

> **⚠️ 演化记录**: v1 (原 /industry/topics 引用不存在字段 title/heat/industryId/categoryName 渲染空白) → v2 (2026-04-20 下午 7 段: Scatter + Coverage Heatmap + 新兴衰退 Radar + Intent Matrix + Detail Drawer + 2 Hero) → **v3.1 (2026-04-20 傍晚 6 段)** Frank 反 "数据都是模拟的, 所以热度上并不科学" + "把热度的相关信息全部删除, 把这个 topic 热度 tab 改成别的标题" → 删 Scatter, Hero 4→3 cards, Drawer 4→3 cards, 侧栏/i18n 去"热度" → **v3.2 (2026-04-21, 本节生效版)** Frank 问 "Brand × Topic 覆盖矩阵和 Visibility 里面的矩阵有什么区别" → 认定两张图回答同一问题 (Visibility BrandTopicHeatmap 用 mentionRate 0-1 真实比值, 本页 Coverage Heatmap 用 brandTopicHits 0-100 hash 合成 ordinal), MVP mock 期留 Visibility 更贴"我在哪些 Topic 上强/弱"叙事; 同日追加 "Topic × Intent 交叉矩阵 这个挺好, 是不是也可以放到品牌这个地方" → 组件从 `components/industry/IndustryTopicIntentMatrix` 重命名为 `components/topics/TopicIntentMatrix` 供两个 Mode 并行消费.

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节"本页不做..."等限制仅用于指导实施, 严禁泄漏给用户。

**A. 定位**

回答: "哪些话题在变热变冷 / 同一个话题背后是查购买还是查科普 / 单个话题点开看什么?"

与 Brand Mode 的关系: Brand Mode `/brand/visibility` 用 `<BrandTopicHeatmap>` 回答"我在每个 Topic 的提及率 (mentionRate 真实 0-1 比值)", Industry Mode 本页回答"行业级话题格局 + 动态 + 意图分布". 两张 heatmap 功能不再并存 (v3.2 删除行业 Coverage Heatmap).

**B. 五段结构** (v3.2 终态)

| 区块 | 内容 | 图表 / 交互 |
|---|---|---|
| ① 筛选栏 | 复用 `<BrandAnalysisFilterBar>` | Sticky top |
| ② Topics Hero | 活跃 Topic 数 / 新兴 Topic 数 (`isEmerging === true`) / 行业平均情感 3 count (v3.1 删"总提及量" 因 mock 数据绝对量级不科学) | 3 卡 |
| ③ **新兴 / 衰退 Topic 雷达 (本页独有)** | 左列: 新兴 Top 5 (按 `emergingScore` desc, `isEmerging === true`). 右列: 衰退 Top 5 (按 `emergingScore` asc 合成). 每卡: Topic 名 + avgSentiment Badge + "首次出现 Nd 前" (emerging) 或 "最近 N% 降幅" (declining) + 关联 Top 3 品牌头像带 (v3.1 删"N 次提及"前缀) | 两列 grid; 新兴卡金边, 衰退卡灰边; 点击卡: 展开段 ⑤ 详情抽屉 |
| ④ **Topic × Intent 交叉矩阵 (共享组件)** | Top 8 Topic × 4 Intent (informational / commercial / transactional / navigational). 格子 = 该 Intent 在该 Topic 下的占比 (hash 合成百分比, 和 = 100%). 每行尾列"主导 Intent" badge. 组件路径 `components/topics/TopicIntentMatrix` 共享给 Brand Mode `/brand/topics` (§4.2.5) | 百分比条堆叠 (stacked horizontal bar 100%), 4 色分别用 `--color-chart-2/3/6/7`; hover tooltip 4 Intent 具体百分比 |
| ⑤ **Topic 详情抽屉** | 点击段 ③/④ 任意 Topic 弹出右侧抽屉: Topic 名 + dimension tag + 3 大指标 (avgSentiment / brandCoverage / primaryIntent, v3.1 删"提及量") + "前 3 引用域" + "关联 Top 3 品牌" (按 `brandTopicHits` desc) + "去 Brand Mode 看主品牌在此 Topic 表现 →" CTA | 右侧抽屉 (600px), Framer Motion 滑入; Esc 关闭 |

**C. 数据派生 (零新增 mock)**

- 段 ②③④: 从 `INDUSTRY_TOPIC_HEATMAP` (已存在) + `BRANDS` + `TOPICS` 派生
- 段 ③ `emergingScore`: `statistics.emergingScore(topic)` — hash `topic.topicId` 合成符号值, `isEmerging === true` 时正值 (10-80), 否则负值 (-60 - 0); 确定性
- 段 ④ Intent 占比: `statistics.topicIntentBreakdown(topic)` — hash 合成 4 个占比, sum = 100
- 段 ⑤ 抽屉关联品牌: `statistics.brandTopicHits(brand, topic)` 对所有行业品牌 desc 取 Top 3 (helper 保留, 仅抽屉使用, UI 不展示 0-100 数值, 只用排序)
- 段 ⑤ 抽屉引用域: `TOP_CITED_DOMAINS` slice

**D. Harness 拦截**

```bash
# (1) 禁止新增 Topics 专用派生 mock
grep -nE "^export const (BRAND_TOPIC_COVERAGE|TOPIC_EMERGING|TOPIC_INTENT_BREAKDOWN|TOPIC_DETAIL_EXPORT)" \
  frontend/src/data/mock.js

# (2) 禁止使用 TOPICS 不存在的字段 (历史 bug)
grep -nE "topic\.(title|heat|industryId|categoryName)" \
  frontend/src/pages/industry/IndustryTopicsPage.jsx

# (3) Topics 页 h1 必须 text-xl (C14-1)
grep -nE "<h1[^>]*text-(2xl|3xl|4xl)" frontend/src/pages/industry/IndustryTopicsPage.jsx \
  | grep -v "// C14-exempt"

# (4) Topics 页必须 import FilterBar (Industry Mode 统一契约)
grep -q "BrandAnalysisFilterBar" frontend/src/pages/industry/IndustryTopicsPage.jsx \
  || echo "missing FilterBar: IndustryTopicsPage"

# (5) v3.2 新增: 禁止在 Industry 页复活 Coverage Heatmap (文件已物理删除, import 会构建失败)
grep -nE "IndustryTopicCoverageHeatmap" \
  frontend/src/pages/industry/IndustryTopicsPage.jsx \
  frontend/src/components/industry/

# (6) v3.2 新增: TopicIntentMatrix 必须在 components/topics/ 共享路径, 禁止在 industry/ 下复活
grep -nE "components/industry/IndustryTopicIntentMatrix" frontend/src/
```

**E. i18n 命名空间**: `industry_topics.*`
- `.hero.*` (段 ②): `active_count` / `emerging_count` / `avg_sentiment` (v3.1 删 `total_mentions`)
- `.emerging.*` (段 ③): `emerging_title` / `declining_title` / `first_seen_days_ago` / `decline_percent` / `related_brands_label`
- `.intent_cross.*` (段 ④): `col_informational` / `col_commercial` / `col_transactional` / `col_navigational` / `dominant_label`
- `.drawer.*` (段 ⑤): `avg_sentiment_label` / `brand_coverage_label` / `primary_intent_label` / `top_domains_label` / `related_brands_label` / `goto_brand_topic_cta` (v3.1 删 `mention_count_label`)

**F. 组件清单 (3 Industry 专属 + 1 共享 + 1 statistics)**

- `frontend/src/components/industry/IndustryTopicsHero.jsx` (段 ②)
- `frontend/src/components/industry/IndustryTopicEmergingRadar.jsx` (段 ③)
- `frontend/src/components/topics/TopicIntentMatrix.jsx` (段 ④, **共享** 给 Brand Mode `/brand/topics`)
- `frontend/src/components/industry/IndustryTopicDetailDrawer.jsx` (段 ⑤)
- `frontend/src/lib/industry/statistics.js` 暴露: `brandTopicHits` (仅抽屉排序, 不再驱动 heatmap) + `emergingScore` + `topicIntentBreakdown`

v3.2 已删除文件: ~~`IndustryTopicHeatScatter.jsx`~~ (v3.1) + ~~`IndustryTopicCoverageHeatmap.jsx`~~ (v3.2) + ~~`IndustryTopicIntentMatrix.jsx`~~ (v3.2, 重命名上移到 `components/topics/TopicIntentMatrix.jsx`)

**G. MVP 边界**

- 段 ③ 衰退雷达的真实衰退识别 (需 T-14d Topic mentionCount diff) — MVP 用 hash 合成, 接真实后端后替换
- 段 ④ Intent 占比的真实 Intent 归属 — MVP 合成, 需真实 Response → Intent NLU 管道 (Phase 2)
- 段 ⑤ 抽屉里的"典型 Prompt 样本" — Frank 2026-04-20 否决 (mock 数据会穿帮), 永久不做, 仅展示聚合指标
- v3.2 删除的 Brand × Topic Coverage Heatmap 不恢复: 真实数据接入后 Industry 若需"跨品牌话题格局 cross-scan"视图, 应以 mentionRate 0-1 真实比值为值域, 复用 `<BrandTopicHeatmap>` + 行级数据改为"Top 8 品牌", 而非重新造 brandTopicHits ordinal

---

#### 4.6.2 UI/UX 原则
- **数据密度高**: 营销人员需要在一屏看到关键数据，不做过度留白
- **对比为王**: 所有数据支持竞品对比视图
- **趋势优先**: 单一数字无意义，必须展示时间变化
- **一键导出**: 每个图表/表格都支持导出 (CSV, PNG, PDF)
- **移动端友好**: 响应式设计，支持手机查看关键指标

#### 4.6.2a 设计系统 (Stripe-inspired)

**设计参考**: 基于 Stripe Dashboard 风格，采用专业、清洁、数据导向的视觉语言。

**前端技术栈**:
- React 18 + Vite 5 + React Router DOM 6
- Tailwind CSS 3 (utility classes)
- Recharts (图表库: AreaChart, PieChart, BarChart, LineChart)
- CSS Custom Properties 实现主题系统

**色彩体系**:
- 品牌主色: `#635bff` (Stripe Purple)
- 页面背景: `#f6f9fc` (冷灰白)
- 侧边栏: `#0a1929` (深海军蓝)
- 标题文字: `#0a2540` (深色海军)
- 阴影: blue-tinted `rgba(50,50,93,0.25)` 风格

**组件体系**:
- `.t-card` / `.t-btn-primary` / `.t-badge-*` / `.t-tabs` / `.t-table` 等主题类
- 5 个 Recharts 图表组件: PanoRing (环形评分), MiniSparkline (迷你走势), DonutChart (饼图), TrendChart (趋势面积图), HorizontalBar (水平柱状图)
- 圆角: 6-8px (保守风格)
- 字体: Inter (衬线体)

**设计文件**: `frontend/DESIGN-STRIPE.md` (完整设计 token 参考)

#### 4.6.3 分享功能 (M4 范围)

**功能 1: 品牌 GEO 体检报告 PDF (Brand GEO Health Report)**

> 定位: 不是"一张社交截图"，而是一份可直接发给客户/老板/同事的**专业 PDF 体检报告**。对标 Semrush Domain Overview PDF，7 页 (2026-04-16 升级含上级导读封面 + Branding Narrative + 诊断 Stack 扩展)，有品牌感、有洞察、有 CTA。
> 与"线索诊断报告"(4.7.0 类型 4) 的区别: 本报告**公开、无需登录**即可生成下载，聚焦展示 GEO 健康度 + 引导注册；线索诊断报告是用户**提交咨询表单后**触发，聚焦品牌诊断 + BD 跟进。

**入口**:
- Dashboard 品牌 PANO Score 卡片右上角"分享报告"按钮 → 打开公开页
- 公开页 URL: `/brand-report/:brandId?locale=zh-CN|en-US` (无需登录可访问，SEO 索引)
- 公开页顶部: "下载 PDF" 按钮 → 调用 `GET /api/v1/brands/:id/share-report.pdf?locale=...` 实时生成

**格式**:
- PDF, A4 纵向, 7 页 (2026-04-16 升级)
- 生成: `@react-pdf/renderer` (遵循依赖规则 — 禁止 HTML 转 PDF)
- 双语: zh-CN / en-US 两套模板
- 报告周期: 默认最近 30 天 (显式标注)
- 数据来源: 复用 `MetricSnapshot` / `Diagnostics` / `KnowledgeGraph`，**不新增数据模型**

**报告结构 (7 页, 2026-04-16 升级)**:

> **升级说明**: 从 6 页扩为 7 页, 原 P1 封面升级为"上级导读封面" (Manager 5 秒扫读导向), P5 诊断按 Insight Stack Layer 1+2+3 扩展, 新增 P6 Branding Narrative 页服务品牌策略读者。所有页的主读者和 Insight Stack 层级在页眉右上角以小标签标注 (`[上级 · L1+L2]` / `[执行者 · L1+L2+L3]` / `[Branding · L1+L2]`)。

**P1 上级导读封面 (Executive Cover, primaryReader: manager)**
- GENPANO logo + 报告生成日期 + 周期文字
- 品牌名 (按 locale 显示 `nameZh` / `nameEn`，回退 `primaryName`) + 行业标签
- **5 秒扫读区 (页面上半部)**:
  - 大号 PANO Score (颜色: ≥80 绿 / 60-79 黄 / <60 红) + 等级 (S/A/B/C/D)
  - 5 KPI 条: 提及率 | SoV | 情感 | 引用份额 | 行业排名 (各含环比箭头)
  - 一句话结论 (LLM 生成, ~40 字, 上级导向): 例 "香奈儿在 AI 搜索中整体健康, 但豆包引擎的份额在近 30 天被竞品反超, 需战略关注"
- **1 分钟精读区 (页面下半部)**:
  - 成果 · 1 行: "本期亮点: [最突出的 1 个胜利]"
  - 风险 · 1 行: "本期风险: [最严重的 1 个问题] + P0/P1 诊断计数"
  - 决策点 · 1-2 行: "建议上级关注的决策问题 (来自 diagnostics.decisionPrompt 聚合)"
- 右下角二维码 → `https://genpano.com/brand/:id`

**P2 总览与子维度 (primaryReader: operator, secondary: manager)**
- 四维雷达图: 可见度 V / 情感 S / 引用 R / 权威 A
- 四个子维度条形 + 本期分数 + 环比变化 (例: +5 / -2)
- PANO Score 30 天趋势折线图
- "关键发现" 3 条 bullet (LLM 生成, 每条 1 句):
  - 最显著的亮点 (例: "情感得分在 DeepSeek 上领先竞品 8 分")
  - 最突出的风险 (例: "豆包中提及率下降 15%")
  - 最大的改善机会 (例: "ChatGPT 的引用权威度仍在行业平均之下")

**P3 引擎分解 (primaryReader: operator)**
- 三引擎卡片: ChatGPT / 豆包 / DeepSeek (并列)
- 每张卡片展示: 提及率 / 情感 / 引用次数 / 提及位置分布 (首位/前3/中段/末段 堆叠柱)
- 引擎对比表: 横轴 引擎 × 纵轴 指标
- "引擎差异洞察" 1 句话 (LLM): 例 "ChatGPT 中表现最强，豆包存在负面情感风险，建议优先改善豆包上的内容语境"

**P4 竞品对标 (primaryReader: manager + operator)**
- 本品牌 + Top 4 竞品 (从知识图谱 `COMPETES_WITH` 边取)
- 横向柱状图: 5 个品牌的 PANO Score 对比 (本品牌高亮)
- 竞品表: 5 品牌 × (PANO Score / 提及率 / 情感 / 行业排名)
- 领先 / 落后文字标注 (例: "领先雅诗兰黛 8 分 / 落后迪奥 3 分")
- **🆕 竞品四象限缩略图** (X=SoV / Y=情感 / size=引用份额), 本品牌象限高亮
- **🆕 一句话战略解读**: "兰蔻领跑 / 雅诗兰黛追赶 / 本品牌稳居领跑象限" (LLM 生成, 上级导向)

**P5 诊断摘要 (primaryReader: operator, 按 Insight Stack L1+L2+L3 扩展)**
- Top 3 P0/P1 诊断卡 (从 `Diagnostics` 表取 `priorityScore.composite` 最高的 3 条)
- 每条按三层 Stack 呈现:
  - **[L1 · 观察]** 触发指标 + 数字 + 对标差距 (来自 `evidence` + `industryBenchmark`)
    例: "熬夜急救主题 SoV 12% (行业中位 18%, Top1 兰蔻 30%, 差距 -18pt)"
  - **[L2 · 解释]** 因果链 + confidence (来自 `causalChain`)
    例: "触发: 引用份额 -8pt + 主题提及率 -15pt → 假设: ChatGPT 改用科普体, 品牌引用稀释 (med confidence, 3 条响应证据)"
  - **[L3 · 方向]** focus area + 3 个 anchor questions + ifUntreated (来自 `focusArea` + `anchorQuestions` + `ifUntreated`)
    例: 
    ```
    Focus: 熬夜急救主题内容丢失
    ① 该主题 Top5 引文来源是谁?
    ② 我方内容是否已被 AI 索引?
    ③ 4 周内能否产出补位内容?
    ⚠️ 不干预: 4 周后 SoV 预计跌至 8%, 行业排名 #5 → #8
    ```
- 底部小字 CTA: "想要具体的优化方案？→ 联系 GENPANO 咨询团队 [邮箱/链接]"

**P6 🆕 Branding Narrative (primaryReader: branding)**
- **不使用数字表头, 用引语和叙事**
- 6.1 AI 眼中的品牌人设: 本期 AI 描述品牌的 Top 5 高频词 + 一句话人设 label
  例: "'高端 · 抗老 · 经典 · 适合熟龄 · 稳定' → 高端抗老经典品牌"
- 6.2 漂移预警 (若存在): 对比上季度, 哪些词下降, 新出现哪些词
  例: "相比上季度, '创新''科技'下降 40%, '经典''稳定'上升——AI 正在重新定位本品牌为'传统稳定'"
- 6.3 典型引语 3 条 (1 positive / 1 neutral / 1 risk-leaning, 取自 `evidence.responseSamples`)
- 6.4 竞品人设对比 迷你矩阵 (3-4 个竞品的 Top3 词 + 叙事紧张度)
- 6.5 情感风险时间线 (若有风险事件, 过去 12 周的叙事走向折线描述)

**P7 关于 & 行动 (CTA 页, primaryReader: manager)**
- GENPANO 是什么 (3 行介绍)
- 数据方法说明: 监测引擎 (ChatGPT/豆包/DeepSeek) / 采集频次 (每日) / 样本规模 (X 个 Prompt × Y 次查询)
- 三个 CTA 区块:
  1. **监测你自己的品牌** → 免费注册 (含 QR + `genpano.com/register`)
  2. **查看行业完整排行榜** → `/rankings/:industry`
  3. **预约 GEO 诊断咨询** → 邮箱 / 咨询表单链接
- 页脚: 官网 / 版权声明 / 报告唯一 ID (例 `RPT-CHN-20260416-a3f2`) — 用于追踪分享来源和防伪

**品牌化与视觉**:
- 严格遵守 `docs/DESIGN_TOKENS.md` 色板 (PANO Score 色带走 `--color-pano-*`)
- 封面 + 页眉页脚使用 GENPANO 品牌主色
- 图表在 PDF 中以 SVG 形式嵌入 (基于 Recharts 渲染导出)
- 页眉: 品牌名 · 报告周期 · 第 X / 6 页
- 页脚: "Generated by GENPANO · {URL}"

**公开 HTML 预览页** (`/brand-report/:brandId`):
- 内容与 PDF 完全一致 (共用数据源 + 文案库)
- 适合 SEO 索引和微信/LinkedIn URL 贴卡预览
- 顶部"下载 PDF"主按钮 + "分享链接"次按钮 (复制当前 URL)
- Open Graph: 首页大号 PANO Score 自动渲染为 OG 图 (1200×630), 用于社交平台链接预览

**API**:
- `GET /api/v1/brands/:id/share-report` — 返回 HTML 预览数据 (JSON, agent 可读)
- `GET /api/v1/brands/:id/share-report.pdf?locale=zh-CN|en-US` — 返回 PDF 二进制流
- `GET /brand-report/:id?locale=...` — SSR 渲染的公开预览页

**限流 & 风险控制**:
- 同一 IP 60 秒内最多生成 3 份 PDF (防刷)
- 报告 PDF 内嵌 ID，可追溯分享源头 (Phase 2 可加 UTM)
- 含 LLM 生成文案的字段 (一句话结论 / 关键发现 / 引擎差异) 有降级: LLM 失败时展示纯数据模板文案

**功能 2: 行业排行榜嵌入代码**
- 在 Industry 页面添加"嵌入"按钮，生成 iframe 代码
- 内容: 该行业品牌 PANO Score Top 10 排行榜 (可选：含竞品)
- 供营销人员在博客文章、邮件营销、客户报告中嵌入
- iframe 可定制颜色主题，确保与外部页面风格一致
- 示例: 
  ```html
  <iframe src="https://genpano.com/embed/industry/beauty/leaderboard?theme=light" width="100%" height="400"></iframe>
  ```

#### 4.6.4 数据导出 (CSV) 规范 ⭐ 2026-04-16 新增

> **定位**: 每个图表/表格都应该"可带走"。CSV 是 GENPANO 面向两类用户 (SEO agency 做客户报告 + 数据分析师接入 BI) 的通用数据交付格式。未登录用户点导出 → 弹登录 modal → 登录后自动继续 (把 CSV 按钮当转化钩子, 2026-04-16 Frank 决策)。

**通用共同规则 (所有 CSV 必须遵守)**:

| 维度 | 规则 |
|------|------|
| **编码** | UTF-8 with BOM (Excel 中文友好, 直接双击可读) |
| **分隔符** | 逗号 `,` (默认); 字段内含逗号/引号时用 `"` 包裹 + 双引号转义 (`""`) |
| **换行** | 行间分隔 `\r\n` (Excel 兼容); 字段内部 (如 Response 原文) 保留 `\n` 不转义 |
| **列头语言** | 按 `User.locale` 单语 — `zh-CN` 用中文列头 (`品牌`, `PANO`), `en-US` 用英文 (`brand`, `pano`); 品牌/产品名同样按 locale 取 `nameZh`/`nameEn` (经 `formatBrand()` / `formatProduct()`) |
| **日期** | ISO 8601 — `YYYY-MM-DD` (仅日期) 或 `YYYY-MM-DDTHH:mm:ssZ` (时间戳), 不本地化格式 |
| **百分数** | 数值 0~100, 保留 2 位小数, **不带** `%` 符号 (列头注明"SoV (%)"); 比率型 0~1 保留 4 位小数 |
| **枚举值** | 导出时经 i18n 翻译 (如 `severity='P0'` → 中文 "P0 严重"); 机器字段 (engine 代号、brand_id) 保持原值 |
| **空值** | 空字符串 ``, **不用** `null` / `N/A` / `-` |
| **筛选继承** | CSV 数据严格受当前页面 filter 约束: `range` / `engines` / `profileGroup` / `brandId` (页面级); UI 右上角 tooltip 明示 "当前筛选: 30 天, 全部引擎, 全部画像" |
| **行数上限** | Tier 1 同步导出上限 **10,000 行**; 超出弹 modal "数据量 {n} 超过同步导出上限. Phase 2 将支持异步邮件发送." MVP 直接拒绝 + 引导用户收窄 filter |
| **文件名** | `genpano_{type}_{subject}_{filterSlug}_{YYYYMMDD-HHmmss}.csv`. 例 `genpano_brand-diagnostics_chanel_30d-all-engines_20260416-143022.csv` |
| **速率限制** | 单用户 60 秒内 ≤ 5 次 CSV 导出, 超出返回 429 + Toast "请稍后再导出" |
| **审计日志** | 后端 `export_log` 表记录 `(userId, exportType, filters, rowCount, fileName, createdAt, ip)` — 追溯用户行为 + 异常保护 |

**权限矩阵 (所有 CSV 类型统一)**:

| 用户状态 | 按钮渲染 | 点击行为 |
|---------|---------|---------|
| 未登录 | 按钮常驻 (不灰) | 弹 `<AuthPromptModal>` ("免费注册即可导出 CSV") → 成功 → 自动恢复导出 + URL 保留 `return_to=currentUrl&action=export_csv&exportType=...` |
| 已登录, 品牌未监控 | 按钮常驻 | 直接导出, 不因"未监控"限制; 与 §4.6.1b B 态数据降级一致 (竞品对比降级为"vs 行业 Top 5") |
| 已登录, 品牌监控中 | 按钮常驻 | 直接导出, 完整数据 |

**交互设计**:
- 每个可导出的表格 / 图表右上角: Lucide `Download` icon (20px) + tooltip `t('common.export.csv')` = "导出 CSV" / "Export CSV"
- 导出前确认: 若 rowCount > 1000, 先弹 "即将导出 {n} 行, 确认?" 防误触
- 导出成功: Sonner Toast "已导出 {fileName} ({rowCount} 行)"
- 按钮位置统一在组件标题栏右侧, 紧贴"分享 PDF"按钮 (若同时存在)

---

**Tier 1 (MVP) — 8 个 CSV 数据字典**:

**CSV #1: 面板 PANO 趋势 (`/dashboard` 区块 ③)**
- 类型: `dashboard-pano-trend`
- Subject: `{projectName}`
- 字段 (中文 / en):
  | 日期 / date | 品牌 / brand | PANO Score / pano_score | 提及率 (%) / mention_rate_pct | 提及率-全量 (%) / mention_rate_all_pct | SoV (%) / sov_pct | 排名 / rank | 是否主品牌 / is_primary |
- 行数: `range.days × (1 primary + up to 3 competitors)` ≈ 30-120 行
- 备注: 仅导出 UI 可见的 Top 3 竞品; 全竞品视图走 CSV #2
- **提及率双口径导出 (2026-04-16 口径精化)**: `mention_rate_pct` = 默认 non-brand 口径 (分母 = `topic.dimension='品类'` 的 Query); `mention_rate_all_pct` = 全量口径 (分母 = 全量相关 Query, 含 brand Topic); `sov_pct` 分母 = 命中任一品牌的 Response (相对份额); 三字段分别计算, 禁止任何一个字段 fallback 到另一个

**CSV #2: 面板竞品四象限 (`/dashboard` 区块 ②)**
- 类型: `dashboard-competitor-quadrant`
- Subject: `{projectName}`
- 字段:
  | 品牌 / brand | 提及率 (%) / mention_rate_pct | SoV (%) / sov_pct | 情感得分 / sentiment | 引用份额 (%) / citation_share_pct | 提及次数 / mention_count | 象限 / quadrant |
- `象限` 枚举: `领跑者/高光但存风险/追赶者/警示品牌` (en: `leader/spotlight-risk/challenger/warning`)
- 行数: 主品牌 + 所有竞品 ≤ 8 行
- **提及率 + SoV 并列导出 (2026-04-16 Frank 纠偏)**: 2026-04-16 前版本仅有 `sov_pct`, 基于"提及率 ≈ SoV"错误前提; 现两列并存, BI 侧可做 (a) "提及率高 + SoV 高" 的绝对领先者 vs (b) "提及率高 + SoV 低" 的行业普涨跟随者 vs (c) "提及率低 + SoV 高" 的窄赛道赢家 三路径分析; 列顺序固定 `提及率 → SoV` 不得反转 (BI 下游列位置敏感)

**CSV #3: 品牌详情 概览 - 提及明细 (`/brands/:id?tab=overview` Top 20)**
- 类型: `brand-mentions`
- Subject: `{brandSlug}`
- 字段:
  | Query ID / query_id | 提示语 / prompt_text | 引擎 / engine | 用户画像 / profile_group | 提及位置 / mention_position | 情感 / sentiment | 片段 / snippet | 采集时间 / collected_at | 查看原文 / response_url |
- `提及位置`: `首位/前3/中段/末段` (en: `first/top3/middle/last`)
- `查看原文`: 深链 `https://genpano.com/topics?responseId=xxx`
- 行数: Top 20 (按"我的提及次数"排序)

**CSV #4: 品牌详情 诊断 (`/brands/:id?tab=diagnostics`)**
- 类型: `brand-diagnostics`
- Subject: `{brandSlug}`
- 字段:
  | 诊断 ID / diag_id | 严重度 / severity | 维度 / dimension | 观察指标 / metric_name | 我的值 / my_value | 行业中位 / industry_median | 行业 Top10 均值 / top10_avg | 差距 (%) / gap_pct | 因果链摘要 / causal_chain_summary | 假设置信度 / hypothesis_confidence | 优先级综合分 / priority_composite | 影响 / impact | 易度 / ease | 紧迫度 / urgency | 首次出现 / first_observed_at | 趋势状态 / trend_status | 读者 / reader_hints | 聚焦区域 / focus_area | 不干预后果 / if_untreated |
- `trend_status` 枚举: `新出现/增长中/持续/改善/已解决` (en: `new/growing/persisting/improving/resolved`)
- `reader_hints`: 分号分隔多值 (`执行者;上级`)
- 行数: 该品牌所有 active diagnostics (通常 10-40)
- **不含** `anchorQuestions` 数组 — 结构太复杂, 属于体检 PDF 专属 (PRD §4.7)

**CSV #5: 品牌详情 产品 (`/brands/:id?tab=products`)**
- 类型: `brand-products`
- Subject: `{brandSlug}`
- 字段:
  | 产品 ID / product_id | 产品名 / product_name | 英文名 / product_name_en | 子品类 / sub_category | SoV (%) / sov_pct | 情感 / sentiment | 30 天增长率 (%) / growth_30d_pct | 提及次数 / mention_count | Top 命中 Prompt / top_prompt_text | BCG 象限 / bcg_quadrant | 产品关系 / relations |
- `bcg_quadrant` 枚举: `明星/现金牛/问题/瘦狗` (en: `star/cash-cow/question-mark/dog`)
- `relations`: `SUBSTITUTES:产品A;PAIRS_WITH:产品B;UPGRADES_TO:产品C` 分号分隔
- 行数: 该品牌所有产品 (通常 5-30)

**CSV #6: 品牌详情 引擎对比 (`/brands/:id?tab=engines`)**
- 类型: `brand-engines`
- Subject: `{brandSlug}`
- 字段:
  | 引擎 / engine | 提及率 (%) / mention_rate_pct | 情感得分 / sentiment | 引用次数 / citation_count | 首位占比 (%) / position_first_pct | 前 3 占比 (%) / position_top3_pct | 中段占比 (%) / position_middle_pct | 末段占比 (%) / position_last_pct |
- 行数: 3 (ChatGPT / 豆包 / DeepSeek), Phase 2 新增引擎按需增行

**CSV #7: Topics Pipeline 全量明细 (`/topics` 4 层 Join)**
- 类型: `pipeline-full`
- Subject: `{projectName}`
- 字段 (宽表, 4 层 JOIN):
  | Topic ID / topic_id | Topic 文本 / topic_text | Intent / intent | Prompt ID / prompt_id | Prompt 文本 / prompt_text | Prompt 语言 / prompt_language | 适用引擎 / applies_to_engines | Query ID / query_id | Profile ID / profile_id | 画像分组 / profile_group_ids | 引擎 / engine | Response ID / response_id | 采集时间 / collected_at | Response 情感 / response_sentiment | 提及品牌 / mentioned_brands | 我的品牌提及位置 / my_brand_position | 引用域名 / citation_domains | Response 原文 / response_text |
- `profile_group_ids` / `mentioned_brands` / `citation_domains`: 分号分隔多值
- `response_text`: 全文保留 `\n`, 用 `"..."` 包裹转义
- 行数: 大 — **通常超过 10,000 行**, MVP 必须要求用户先收窄 filter (time range ≤ 7d + 单引擎) 才能同步导出; Phase 2 异步邮件发送 (PRD §4.7.9 同款异步方案)
- **权限**: 需登录 + 对应 Project 内 Response (若品牌未监控, 仅能拉该品牌作为"主体"的 Response 不含竞品池扩展)

**CSV #8: 行业 / 品牌列表 (`/industry` List View)**
- 类型: `industry-brands`
- Subject: `{industrySlug}`
- 字段:
  | 品牌 ID / brand_id | 品牌名 / brand_name | 英文名 / brand_name_en | 别名 / aliases | 定位 / positioning | 价位段 / price_range | 主营品类 / primary_categories | PANO Score / pano_score | 7 天变化 / pano_delta_7d | SoV (%) / sov_pct | 情感 / sentiment | 行业排名 / industry_rank | 在我的监控中 / is_in_my_monitoring |
- `aliases` / `primary_categories`: 分号分隔多值
- `is_in_my_monitoring` 枚举: `主品牌/竞品/未监控` (en: `primary/competitor/none`); 未登录时此列统一显示"未登录/not-logged-in"
- 行数: 该行业所有 brands (通常 50-200)

**CSV #9: PR 候选列表 (`/brands/:id?tab=content-gap` 区块 ④)** — 2026-04-17 新增 (§4.2.7.C)
- 类型: `pr_targets`
- Subject: `{brandSlug}`
- 字段:
  | 域名 / domain | 权威 Tier / authority_tier | 置信度 / authority_confidence | 覆盖我 / attributed_to_me_count | 覆盖竞品数 / competitors_count | 覆盖竞品 / competitors | 近 30 天引用次数 / citations_30d | 近 30 天趋势 (%) / trending_30d_pct | 站点类型 / site_type | SAME_GROUP 共享 / same_group_shared | PR Score / pr_score |
- `site_type` 枚举: `官方/权威媒体/KOL/UGC/未知` (en: `official/authority_media/kol/ugc/unknown`)
- `same_group_shared` 布尔: `是/否` (en: `true/false`)
- `competitors`: 分号分隔多值 (最多 5 个, 超出 → `;… +N`)
- 行数: Top 50 (按 `pr_score` 降序)
- **不含** "联系方式" 字段 (§4.2.7.C 禁止事项)
- **权限**: 与 CSV #3/#4 同; 未登录 → AuthPromptModal 转化钩子
- i18n key: `export.csv.column.pr_score` / `authority_tier` / `site_type` 等全部双语
- 排序稳定性: 相同 `pr_score` 用 `domain` 字典序兜底 (避免重排引起 BI 下游 diff 噪音)

**CSV #10: 内容缺口表 (`/brands/:id?tab=content-gap` 区块 ①)** — 2026-04-17 新增 (§4.2.7.B)
- 类型: `content_gap`
- Subject: `{brandSlug}`
- 字段:
  | Topic ID / topic_id | Topic 文本 / topic_text | 品类 / category_path | 相关 Response 数 / relevant_responses | 我被提及数 / my_mentions | 我被引用数 / my_attributions | Gap Ratio / gap_ratio | Top 竞品归因数 / top_competitor_attributions | Top 竞品 / top_competitor_brand | 主流页面类型 / top_page_type |
- `top_page_type` 枚举: `产品页/评测页/榜单页/KOL文/知识百科/其他` (en: `product/review/ranking/kol/knowledge/other`)
- `gap_ratio`: 4 位小数, 范围 [0, 1]
- 行数: Top 20 (按 gap_ratio 降序, 次序依 relevant_responses 降序兜底)
- **权限**: 与 CSV #3/#4 同

---

**后端实现要点**:
- 路由: `GET /api/v1/export/csv/:exportType?filters=...`
- Streaming Response (`Transfer-Encoding: chunked`), 避免内存峰值 (针对 CSV #7 大文件)
- Content-Type: `text/csv; charset=utf-8`
- Content-Disposition: `attachment; filename="..."` + 同文件名的 `filename*=UTF-8''...` (RFC 5987, 兼容中文文件名)
- CSV Library: `csv-stringify` (Node) 或 `encoding/csv` (Go); **禁止**手写 CSV 拼接 (引号转义容易踩坑)
- BOM 写入: 流首字节 `\uFEFF`
- 前端触发: `window.location.href = '/api/v1/export/csv/...'` 或 `<a download>` — 让浏览器原生下载, 不用 Blob + URL.createObjectURL (大文件内存问题)

**i18n 命名空间** (`messages/{locale}/export.json`):
- `export.csv.button` = "导出 CSV" / "Export CSV"
- `export.csv.confirm.title` / `confirm.body` (行数确认)
- `export.csv.auth_modal.title` / `auth_modal.body` / `auth_modal.cta` (未登录弹窗)
- `export.csv.toast.success` / `toast.rate_limit` / `toast.too_large`
- `export.csv.column.{key}` (所有列头双语对齐, 由 Tier 1 的 8 个 CSV 的列名翻译到这里)
  - 必须含 `export.csv.column.mention_rate_pct` (zh-CN "提及率 (%)" / en-US "Mention Rate (%)") + `export.csv.column.mention_rate_all_pct` (zh-CN "提及率-全量 (%)" / en-US "Mention Rate All (%)") + `export.csv.column.sov_pct` (zh-CN "SoV (%)" / en-US "SoV (%)") 三键, **不得共用** — 三列口径各不相同
- `export.csv.enum.severity.{P0,P1,P2,P3}` / `enum.trend_status.*` / `enum.bcg_quadrant.*` / `enum.quadrant.*`

**边界与风险**:
- **数据敏感性**: 竞品池是私有信息, CSV 只能导出当前用户自己 Project 的 `competitorBrandIds` 对应数据; 后端必须二次校验 userId, 防止 URL 参数篡改
- **PII**: CSV 不含任何用户个人信息 (邮箱/手机), 只含品牌 / Response 公开数据
- **未登录 return_to 安全**: `return_to` 必须做 allowlist (仅 `genpano.com` 内部路径), 防开放重定向攻击
- **审计数据留存**: `export_log` 保留 90 天, 超过自动清理

### 4.7 报告系统

> 报告是 GENPANO 的核心输出之一：对用户而言是定期的 GEO 健康度汇报，对商业模式而言是咨询服务转化的关键载体。
> 设计原则: Agent-First (Markdown/JSON 机器可读) + Human-Friendly (PDF 可视化导出) + **Insight-Dense (指标→解释→方向三层闭环)** + **Multi-Audience (执行者/上级/Branding 三读者分发)**。

#### 4.7.0-a 报告设计框架：洞察 Stack × 三读者视角

> ⚠️ **所有报告 Section 在设计、撰写、验收时必须同时符合这两个框架。** 违反任何一条视为"指标堆砌"，需要重写。

**框架 1 · 洞察 Stack (Insight Stack)**

每一块内容都必须走完从"数据→含义→行动"的三层路径。平台负责全部 Layer 1/2，以及 Layer 3 的锚点化表达；**Layer 3 只给 focus area + 锚点问题 (anchor questions) + 优先级，不给执行剧本 (playbook)**——剧本属于付费咨询的价值边界（详见 4.8.6）。

| 层级 | 英文 | 回答什么 | 产出形式 | 示例 |
|------|------|---------|---------|------|
| Layer 1 **观察** | Observation (What) | 发生了什么？指标值是多少？环比/对标差距？ | 数字 + sparkline + 标签（上升/下降/新增）| 雅诗兰黛在 ChatGPT 的 SoV 从 18% 降至 12% (WoW -6pt)，行业 Top10 中位数 21% |
| Layer 2 **解释** | Explanation (Why) | 为什么会这样？哪条因果链 / 触发指标？信心度？ | 因果链 1–3 条 + confidence(low/med/high) + 证据引用 | 触发指标: 引用份额同步 -8pt, "熬夜急救"主题提及率 -15pt; 假说: ChatGPT 在该主题改用科普内容, 品牌引用被稀释; 信心: med (3 条响应证据) |
| Layer 3 **方向** | Direction (What next) | 接下来该关注什么？优先级？我该问什么？ | focus area + 3–5 个 anchor questions + priority(P0/P1/P2) + 不干预后果 | Focus: "熬夜急救"主题的内容来源丢失. 锚点: ① 该主题 Top5 引文是谁？② 我方内容是否被 GPT 索引？③ 竞品兰蔻在同主题 SoV 升至多少？优先级 P1. 不干预 4 周后 SoV 预计跌至 8%. |

**为什么 Layer 3 不给完整剧本**:
- "写 X 篇 SEO 文章"这种执行步骤依赖企业侧内容策略、法务、预算、代理商——平台没有这些输入
- 给错剧本比不给更糟：客户会照做然后把失败归因到平台
- 锚点问题比剧本更通用：无论客户有内部团队还是外包代理，都能把问题接下去
- 想要剧本的客户，正是咨询服务的 ICP：Layer 3 的每个 focus area 都可以带一个"需要执行方案？预约 30 分钟诊断"CTA

**框架 2 · 三读者视角 (Three-Audience View)**

GENPANO 的报告同时服务 3 类读者，他们关心的问题、愿意阅读的深度、可以接受的抽象度完全不同。Section 设计时必须**显式标记主读者 (primary) 和次读者 (secondary)**。

| 读者 | Persona | 关心什么 | 5 秒扫读要看到 | 愿意的深度 | 典型疑问 |
|------|---------|---------|---------------|-----------|---------|
| **执行者** Operator | SEO/GEO 小李 | 本周/本月做什么？哪个问题先啃？ | 优先级 + 锚点问题 + 我负责的指标颜色 | 指标-诊断因果链 + 对标 + 引文证据 | "为什么这个问题 P1 不是 P2？" |
| **上级** Manager | 品牌市场经理张总、CMO | 团队整体表现？竞品打赢了吗？要不要追投资源？ | 行业排名 + 环比箭头 + Top3 风险/机会 + 一句总结 | Exec Summary、趋势叙事、竞品矩阵；不关心单条诊断细节 | "我们在行业里第几？环比好还是坏？值不值得继续投？" |
| **Branding** Strategist | 品牌策略/PR/社交 | AI 在把我的品牌塑造成什么样？竞品的叙事是什么？有没有负面故事发酵？ | 品牌人设标签 + 典型引语 + 情感风险 Top3 | 定性多于定量：引文、叙事分类、竞品人设对比、风险时间线 | "AI 说我们是什么风格的品牌？有没有说错？竞品被 AI 说成什么样？" |

**Section 角色规则**:
1. 每个 Section 必须在 schema 里声明 `primaryReader` 和 `insightStackLayer`（详见 4.7.1 数据模型扩展）
2. 每份报告至少包含 **3 种主读者各自的 1 个 Section**，且顺序遵循"上级导读 → 执行者 → Branding"的阅读动线
3. 上级向 Section 限制在报告前 20% 篇幅内（PDF 前 1–2 页），必须支持 5 秒扫读
4. Branding 向 Section 不用数字表头，用引语 / 词云 / 时间线叙事
5. 执行者向 Section 必须走完 Layer 1→2→3 完整 Stack；其他读者向 Section 可以只覆盖 Layer 1–2

**示例：同一个"SoV 下降"事件在三视角下的呈现**

```
[上级 · 行业格局] 
  SoV 12% (行业第 5, 环比 -2 位), 竞品兰蔻 +3 位抢到第 2. 
  💡 一句话: 我们在 ChatGPT 丢了 6pt, 主要被兰蔻和 Olay 瓜分. 

[执行者 · 诊断因果] 
  触发: ChatGPT SoV -6pt
  因果: 引用份额 -8pt ← "熬夜急救"主题提及 -15pt
  方向: Focus "熬夜急救"主题内容丢失, P1, 4 周不干预 SoV 跌至 8%
  锚点问: ① 我方在该主题发过几篇内容？② 哪些竞品 URL 被 ChatGPT 引用？③ 内容是否被搜索引擎索引？

[Branding · 叙事分析]
  AI 人设: 从"高端抗老专家"漂移为"经典品牌"(3 月前高频词"精华/夜间修护", 本周高频词"经典/大牌/稳定")
  典型竞品引语: 兰蔻被 GPT 描述为"科技抗老新锐", 提及 3 项"最新配方"
  情感风险: 出现 2 条 neutral-leaning 提及暗示"老牌但创新不足"
```

**Section 分发矩阵** (各报告类型必含的 Section × 主读者):

| Section Type | 周报 | 月报 | 即时 | 线索 | 主读者 | Insight Stack |
|--------------|:---:|:---:|:---:|:---:|--------|---------------|
| `executive_summary` (上级导读) | ✓ | ✓ | ✓ | ✓ | 上级 | L1+L2 精炼 |
| `industry_landscape` | ✓ | ✓ | ✓ | ✓ | 上级 | L1+L2 |
| `brand_performance` | ✓ | ✓ | ✓ | ✓ | 执行者 | L1+L2 |
| `diagnostic_summary` | ✓ | ✓ | ✓ | ✓ | 执行者 | L1+L2+L3 |
| `branding_narrative` (新增) | – | ✓ | 可选 | ✓ | Branding | L1+L2 |
| `competitor_comparison` | ✓ | ✓ | ✓ | ✓ | 执行者/上级 | L1+L2 |
| `product_competitiveness` | – | ✓ | 可选 | ✓ | 执行者 | L1+L2 |
| `anchor_actions` (新增) | ✓ | ✓ | ✓ | – | 执行者 | L3 |
| `cta` | – | ✓ | – | ✓ | 上级 | — |

> **注**: `branding_narrative` 和 `anchor_actions` 是本次升级新增 Section Type，详见 4.7.3。

#### 4.7.0 报告类型总览

```
┌─────────────────────────────────────────────────────────────────┐
│  Report Types                                                    │
│  ═══════════════════════════════════════════════════════════     │
│                                                                  │
│  1. 周报 (Weekly Report)                                         │
│     ├── 触发: 每周一 08:00 自动生成 (上周一~周日数据)               │
│     ├── 粒度: 日级趋势、周环比                                    │
│     ├── 受众: SEO 从业者 (小李)、品牌经理日常跟踪                  │
│     └── 篇幅: ~2000 字                                           │
│                                                                  │
│  2. 月报 (Monthly Report)                                        │
│     ├── 触发: 每月 1 号 08:00 自动生成 (上月数据)                  │
│     ├── 粒度: 周级趋势、月环比、月同比 (有历史时)                  │
│     ├── 受众: 品牌市场经理 (张总)、管理层                         │
│     └── 篇幅: ~4000 字                                           │
│                                                                  │
│  3. 即时报告 (On-Demand Report)                                   │
│     ├── 触发: 用户手动点击"生成报告"或 API/MCP 调用               │
│     ├── 粒度: 用户指定时间范围                                    │
│     ├── 受众: 按需使用，常见于客户汇报前                          │
│     └── 篇幅: 根据时间跨度自动调整                                │
│                                                                  │
│  4. 线索诊断报告 (Lead Diagnostic Report)                         │
│     ├── 触发: 用户提交咨询线索表单时自动生成                      │
│     ├── 粒度: 聚焦该品牌的诊断数据，含行业对标                    │
│     ├── 受众: BD 团队 + 潜在客户                                  │
│     └── 篇幅: ~1500 字，PDF 格式，附带 GENPANO 品牌               │
│                                                                  │
│  ※ Phase 2: 咨询客户复盘报告 (优化前后对比)                       │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.7.1 报告数据模型

```typescript
interface Report {
  id: string;
  projectId: string;
  type: 'weekly' | 'monthly' | 'on_demand' | 'lead_diagnostic';
  status: 'generating' | 'completed' | 'failed';
  
  // 时间范围
  periodStart: string;           // ISO date
  periodEnd: string;
  generatedAt: string;
  
  // 内容
  title: string;                 // LLM 生成的报告标题 (如 "雅诗兰黛 GEO 周报 · 2026-W16")
  executiveSummary: string;      // LLM 生成的一段话摘要 (~200 字)
  sections: ReportSection[];     // 结构化的章节列表
  
  // 输出
  markdownContent: string;       // 完整 Markdown 文本 (MVP 主格式)
  pdfUrl?: string;               // PDF 文件 URL (生成后填充)
  jsonData: ReportJSON;          // 结构化 JSON (Agent 消费用)
  
  // 关联
  brandId?: string;              // 品牌聚焦报告时
  diagnosticIds: string[];       // 本报告包含的诊断 ID 列表
  
  // 配送
  deliveredVia: ('dashboard' | 'email' | 'api')[];
  emailSentAt?: string;
  
  // 元信息
  wordCount: number;
  sectionCount: number;
  createdBy: 'system' | 'user' | 'lead_form';
}

interface ReportSection {
  id: string;
  order: number;
  type: ReportSectionType;
  title: string;
  content: string;              // Markdown 格式的章节正文
  dataPoints: ReportDataPoint[]; // 该章节引用的数据点 (用于 JSON 输出)
  charts?: ReportChart[];       // 图表定义 (PDF 渲染用)
  
  // ⬇️ 4.7.0-a 三读者 × Insight Stack 框架扩展字段
  primaryReader: 'operator' | 'manager' | 'branding'; // 主读者 (必填)
  secondaryReaders?: ('operator' | 'manager' | 'branding')[];
  insightStackLayers: ('observation' | 'explanation' | 'direction')[];  // 本 section 覆盖的 Stack 层 (至少 1 个)
  
  // 结构化洞察 (Layer 2 / Layer 3 产出, 供 Agent 消费)
  insights?: SectionInsight[];
  anchorQuestions?: string[];   // Layer 3 专用 (operator section 必填, 3-5 条)
  
  // 叙事证据 (branding section 专用)
  narrativeEvidence?: NarrativeEvidence[];
}

interface SectionInsight {
  layer: 'observation' | 'explanation' | 'direction';
  statement: string;                   // 洞察句子 (<= 120 字)
  evidence: {                          // 支撑证据
    metricIds?: string[];              // 引用哪些指标
    diagnosticIds?: string[];          // 关联诊断
    responseQuotes?: string[];         // 引用原文片段 (Branding 用)
  };
  confidence: 'low' | 'medium' | 'high';
}

interface NarrativeEvidence {
  type: 'persona_label' | 'quote' | 'competitor_contrast' | 'risk_timeline';
  content: string;                     // 人设标签 / 原文引语 / 对比描述 / 时间点
  sentiment?: 'positive' | 'neutral' | 'negative';
  engine?: string;                     // 来自哪个引擎
  firstSeenAt?: string;                // 首次出现时间 (风险时间线用)
  sourceResponseIds?: string[];
}

type ReportSectionType = 
  | 'executive_summary'       // 总览摘要 [主读者: 上级]
  | 'pano_score'              // PANO Score 详情 [主读者: 执行者]
  | 'industry_landscape'      // 行业格局 [主读者: 上级]
  | 'brand_performance'       // 品牌表现 [主读者: 执行者]
  | 'branding_narrative'      // 🆕 品牌叙事分析 [主读者: Branding]
  | 'product_competitiveness' // 产品竞争力 [主读者: 执行者]
  | 'competitor_comparison'   // 竞品对比 [主读者: 执行者/上级]
  | 'diagnostic_summary'      // 诊断摘要 [主读者: 执行者, 含 Stack L1+L2+L3]
  | 'anchor_actions'          // 🆕 锚点行动清单 [主读者: 执行者, 纯 Stack L3]
  | 'cta';                    // 咨询服务 CTA [主读者: 上级]

interface ReportDataPoint {
  metric: string;              // 如 'brand_pano_score', 'mention_rate'
  engine?: string;             // 引擎维度
  currentValue: number;
  previousValue?: number;
  changePercent?: number;
  rank?: number;               // 行业排名
  industryAvg?: number;        // 行业平均值
}

interface ReportChart {
  type: 'line' | 'bar' | 'radar' | 'table';
  title: string;
  data: Record<string, any>[];  // 图表数据
  config: Record<string, any>;  // 渲染配置 (颜色、轴标签等)
}

interface ReportJSON {
  metadata: {
    reportId: string;
    type: string;
    period: { start: string; end: string };
    generatedAt: string;
    brandName: string;
    industryName: string;
  };
  scores: {
    brandPano: { current: number; previous: number; grade: string };
    productPano: { productName: string; current: number; previous: number }[];
    industryPano: { current: number; sovRank: number };
  };
  highlights: string[];         // 本期关键变化列表 (LLM 生成)
  diagnostics: {
    p0Count: number;
    p1Count: number;
    items: { id: string; severity: string; title: string }[];
  };
  sections: ReportSection[];
}
```

#### 4.7.2 报告内容模板 (深度版)

> 每个 Section 都遵守同一套 5 元组：**Primary Reader → Insight Stack Layers → Data Recipe → Narrative Formula → Human-Readable Output**。Section 之间通过 `insightStackLayers` 声明不重叠——Layer 1 的展示在多处出现是允许的（各视角复用事实），但 Layer 2 解释和 Layer 3 方向必须有唯一主场。

**Section 1: Executive Summary · 上级导读** 
- `primaryReader`: manager; `secondaryReaders`: [operator, branding]
- `insightStackLayers`: ['observation', 'explanation']  (不含 direction, 避免上级决策越过执行者)
- 必含所有报告类型；位于报告开头；目标：**上级 5 秒扫读 + 1 分钟精读**

```
[P0 Hero Strip · 5 秒扫读区]
  ↑ 行业排名 #5 (↓2)  SoV 12% (-6pt)  情感 4.2 (±0)  引用份额 18% (-8pt)
  📢 Top3 变化: ① 被兰蔻反超到第 4  ② "熬夜急救"主题丢失  ③ 产品 A 引用份额登顶

[1 分钟精读区 · 3 段叙事]
  段 1 (成果): 新开拓 [主题X] 登顶, 产品 A SoV +5pt 至行业第 2
  段 2 (风险): [主题Y] 引用链条断裂, P1 诊断 2 条, 4 周不干预预计掉至第 7
  段 3 (决策点):
    • 资源决策: 要不要加内容投入到 [主题Y]? (锚点问题见诊断 Section)
    • 竞品决策: 兰蔻在本周上新 3 条科技叙事, 要不要应对?
    • 指标决策: 本期 SoV -6pt 是否触发复盘机制?
```

**Data Recipe**:
```sql
-- 5 秒扫读区
SELECT metric_id, current, prev_period, change_pct, industry_rank
FROM metric_snapshot
WHERE brand_id = $brand AND metric_id IN (
  'sov', 'sentiment_score', 'citation_share', 'industry_rank_v2'
) AND period = $period;

-- Top3 变化 (按 impact_score 排序, 取绝对值最大的 3 条)
SELECT event_type, headline, magnitude, direction
FROM brand_events
WHERE brand_id = $brand AND period_overlap($period)
ORDER BY abs(impact_score) DESC LIMIT 3;

-- 决策点 (从 diagnostics 筛 severity=P0/P1 + readerHint='manager')
SELECT title, decisionPrompt
FROM diagnostics
WHERE brand_id = $brand AND period_overlap($period) 
  AND severity IN ('P0','P1') AND reader_hints @> '["manager"]';
```

**Narrative Formula** (段 1/2/3 强制结构):
- 段 1: `{成果数量}项关键胜利。最突出的是 {hero_event}，{直接量化影响}。`
- 段 2: `同时需要关注 {风险数量} 个风险点。最严重的是 {top_risk}，{触发指标+因果链一句话}。如果 {预测窗口} 内不干预，预计 {predictedImpact}。`
- 段 3: 每个决策点一行，格式 `• {决策类别}: {是否 Y/N 的问题} ({数据支撑})`

**Acceptance**: 任意上级在不点开其他 Section 的情况下，必须能回答"我们赢了吗？输在哪？我要不要介入？"三个问题。

---

**Section 2: PANO Score 详情 · 执行者内部诊断**
- `primaryReader`: operator; `insightStackLayers`: ['observation', 'explanation']
- **注意**: PANO Score 面向执行者是"内部指标"——不是面板主 KPI（面板 KPI 是 SoV/情感/引用份额/排名）。PANO 在报告中解释"复合得分为何变化"，走 V/S/R/A 四子维度。

```
[PANO Score 构成瀑布图]
  Brand PANO 72 ← V 85 × 0.3 + S 68 × 0.2 + R 75 × 0.25 + A 60 × 0.25
  本期变化: -4 (V -8 + S ±0 + R ±0 + A -2)
  
[子维度因果链]
  V 下降主因: ChatGPT 提及率 ↓
    → ChatGPT 对 "熬夜急救" 主题改用科普体内容, 品牌词被挤出
    → confidence: medium (3 条响应证据, Prompt ID: P-17832/P-18203/P-18541)
  A 下降次因: 高权威引用来源 (官方/权威媒体) 份额下降
    → 新出现 3 条 KOL/UGC 来源稀释了 A 分子
    → confidence: high (来源列表可追溯)

[产品 PANO 表现 Top 10] 
  排名 | 产品 | PANO | 环比 | 主推 Topic 命中率
  1    | Prod A | 78 | +5 | "精华 Top Pick" 85%
  ...
```

**Data Recipe**: `metric_snapshot` + `pano_component_breakdown` + `diagnostic.causalChain` join。

**Narrative Formula**: `本期 PANO {current} ({trend})，主要由 {dominantComponent} 驱动。进一步拆解，{dominantComponent} 的变化来自 {causalChainHead} → {causalChainTail}，信心 {confidence}。`

---

**Section 3: 行业格局 · 上级战略视角**
- `primaryReader`: manager; `secondaryReaders`: [operator]
- `insightStackLayers`: ['observation', 'explanation']

```
[SoV 分布 · 本期 vs 上期]
  双层环图: 外环本期 / 内环上期
  本品牌 12% → 我方 | 兰蔻 18% → 领跑 | Olay 15% → 追赶 | ...
  
[竞品四象限 (关键图, 从面板复用)]
  X = SoV, Y = 情感 (0 中线), bubble size = 引用份额
  四象限打标: 领跑者 / 高光但存风险 / 追赶者 / 警示品牌
  🔴 本品牌落入 "追赶者", 上期在 "领跑者"
  
[行业主题迁移 · 本期 vs 上期]
  新增主导主题: "熬夜急救" 提及量 +180%, 兰蔻拿下 35% 份额
  消失主题: "补水面膜" 提及量 -45% (用户搜索行为迁移至护肤步骤)
  我方主题覆盖率: 5/8 → 3/8 (丢失 熬夜急救 + 维稳精华 2 个主题)

[新竞争者动态]
  异军突起: 品牌 X (国货新锐) 首次进入 Top 10, SoV 从 0.5% 跳至 4%
  → 触发来源: 与某美妆博主联动内容被 GPT 索引
```

**Data Recipe**: `industry_sov_distribution` + `topic_share_delta` + `new_entrants_detection`。

**Narrative Formula**: `行业在本期发生 {major_shift}。我方从 {prev_position} 移动至 {current_position}，主因 {cause}。值得关注的竞争者变化是 {notable_mover}。`

---

**Section 4: 品牌表现 · 执行者深度**
- `primaryReader`: operator; `insightStackLayers`: ['observation', 'explanation']

```
[引擎表现矩阵 · 3 × 4]
  引擎     | SoV    | 情感  | 引用份额 | 排名
  ChatGPT  | 10%↓6  | 4.1± | 15%↓8   | #6↓2
  豆包     | 14%↑2  | 4.3↑ | 20%±    | #4↑1
  DeepSeek | 12%±   | 4.2± | 19%±    | #5±
  
  → 引擎表现分化显著: ChatGPT 下滑, 豆包改善
  
[关键 Topic 排名变动 Top 10]
  Topic | 本期排名 | 环比 | 触发原因(诊断 ID)
  熬夜急救 | #8 | ↓5 | DIAG-2041 引用链条断裂
  抗老精华 | #3 | ↑1 | —
  ...
  
[情感下钻 · 负面关键词扫描]
  neutral-leaning 关键词: "老牌" +15 次, "经典" +10 次 (可能暗示创新性不足)
  negative 关键词: 0 (未出现明显负面)
  → Branding Section 3 详细叙事分析

[引用来源变化]
  新增高权威引用: +2 (某美妆媒体权威测评)
  消失高权威引用: -4 (某博客停更) ← 直接影响 A 分
  新增低权威引用: +8 (UGC 类) ← 稀释 A 分
```

**Data Recipe**: `engine_breakdown_matrix` + `topic_rank_delta` + `sentiment_keyword_scan` + `citation_source_diff`。

**Narrative Formula**: `本期品牌在 {strongest_engine} 表现最佳 ({evidence})，在 {weakest_engine} 面临压力 ({evidence})。关键驱动因素是 {top_causal_factor}。`

---

**Section 5: 🆕 Branding Narrative · 品牌叙事分析** (月报/线索报告必含)
- `primaryReader`: branding; `insightStackLayers`: ['observation', 'explanation']
- **原则**: 用引语和叙事，不用数字表头。内容 ~400 字 + 2–3 张可视化。

```
[5.1 AI 眼中的品牌人设 (Persona)]
  本期 AI 描述本品牌最高频的 5 个词/短语 (来自 200+ 响应挖掘):
    "高端" (提及 45 次) · "抗老" (38) · "经典" (30) · "适合熟龄" (22) · "稳定" (18)
  
  📌 人设标签: "高端抗老经典品牌 · 偏向熟龄客群"
  
  ⚠️ 漂移预警: 相比上季度, "创新""科技""前沿"等词提及率下降 40%
  可能的叙事风险: AI 正在将本品牌从"前沿抗老"重新定位为"传统稳定"

[5.2 竞品叙事对比矩阵]
  品牌   | AI 人设 (Top3 词)           | 叙事紧张度
  本品牌 | 高端 · 抗老 · 经典           | 中性偏稳
  兰蔻   | 科技 · 新锐 · 前沿           | 上升动能
  雅诗兰黛| 专业 · 修护 · 可靠          | 稳定
  Olay   | 平价 · 有效 · 日常          | 快速上升
  
  → 兰蔻正在抢占"科技新锐"心智, 我方若不应对, 2 个季度内品牌人设可能被固化

[5.3 典型引语 · AI 如何描述品牌]
  🟢 Positive (3 条典型引语):
    "XX 是高端美妆中最稳定的抗老品牌之一, 适合追求经典品质的用户..."
    (来源: ChatGPT 响应, Prompt: "推荐经典抗老精华", 2026-04-10)
    ...
  🟡 Neutral (2 条):
    "XX 的产品更适合 35 岁以上熟龄肌..."
    "如果追求性价比, XX 可能不是首选..."
  🔴 Risk-leaning (1 条):
    "XX 近年在新品创新速度上稍慢于兰蔻..."
    (来源: 豆包, Prompt: "抗老精华品牌对比", 2026-04-12)

[5.4 情感风险时间线]
  风险事件 (过去 12 周):
    2026-W13: 首次出现 "创新不足" 关键词 (1 次)
    2026-W14: "创新不足" 出现 3 次, 扩散至 2 个引擎
    2026-W15: 出现 "被兰蔻超越" 叙事 (2 次)
    2026-W16: 本期, "经典""稳定"高频化, "新品"关键词降至历史低点
  
  → 叙事走向: 从"无风险"→"竞品比较"→"品牌定位固化"
```

**Data Recipe**: `brand_persona_extraction` + `competitor_narrative_matrix` + `quote_selection` + `sentiment_risk_timeline`。

**Narrative Formula (每小节一句 summary)**:
- 5.1: `AI 将 {brand} 描述为 {persona}, 相比上期 {drift_direction}.`
- 5.2: `在 {competitor} 叙事上 {advantage/lag}.`
- 5.3: (不使用公式, 选取真实引语)
- 5.4: `品牌叙事在过去 {N} 周经历 {trajectory}.`

**Acceptance**: Branding 读者能在 3 分钟内回答"AI 说我们是什么品牌？有没有漂移？竞品的叙事是什么？要不要干预？"

---

**Section 6: 产品竞争力 · 执行者产品线视角** (月报/线索必含, 周报可选)
- `primaryReader`: operator; `insightStackLayers`: ['observation', 'explanation']

```
[产品表现 BCG 矩阵 (从品牌详情页复用)]
  X = 推荐频次, Y = 推荐份额 → 明星/现金牛/问号/瘦狗
  Top 5 明星: Prod A, B... (值得加码)
  🔴 跌落到瘦狗象限: Prod X (原现金牛, 本期推荐频次 -60%)

[推荐语境变化]
  Prod A 本期高频语境: "抗老精华 Top Pick" (85%) / "孕期敏感可用" (15%)
  Prod A 上期高频语境: "抗老精华 Top Pick" (60%) / "礼盒送礼" (40%)
  → 语境迁移: 从"送礼"转向"专业抗老"(可能因竞品礼盒主题争夺)

[产品信息准确度诊断]
  Prod A 配方描述准确性: 
    ChatGPT 95% | 豆包 100% | DeepSeek 88%
    🔴 DeepSeek 出现"含酒精"错误描述 (实际不含), 推荐 12% 响应受影响
```

**Data Recipe**: `product_bcg_position` + `recommendation_context_diff` + `product_accuracy_breakdown`。

---

**Section 7: 竞品对比 · 上级+执行者双用途**
- `primaryReader`: operator; `secondaryReaders`: [manager]
- `insightStackLayers`: ['observation', 'explanation']

```
[竞品四维度打分表] (上级用: 一眼看胜负)
  维度           | 本品牌 | 兰蔻 | 雅诗兰黛 | Olay | 🏆
  SoV           | 12%    | 18%  | 10%     | 15%  | 兰蔻
  情感           | 4.2    | 4.1  | 4.3     | 4.0  | 雅诗兰黛
  引用份额       | 18%    | 22%  | 15%     | 16%  | 兰蔻
  行业排名       | #5     | #2   | #6      | #3   | 兰蔻
  PANO Score     | 72     | 78   | 70      | 74   | 兰蔻
  
  → 兰蔻领先 4/5 维度, 但情感分数被雅诗兰黛反超, 值得深究

[竞品叙事对比 · 本期新动向] (执行者用: 竞品在做什么)
  兰蔻: 新上线 3 篇"实验室科技"主题内容被 ChatGPT 索引, SoV +3pt
  Olay: 在 DeepSeek 强势崛起, 推测其社群内容被大量采样
  雅诗兰黛: 无显著变化

[竞品 SoV 5 周趋势对比折线图]
  我方: 平缓下降 → 兰蔻: 持续上升 → Olay: 快速上升
  → 兰蔻曲线在 W14 后斜率陡增, 关联其内容投放高峰

[差距与机会点]
  落后维度: SoV (-6pt vs 兰蔻), 引用份额 (-4pt vs 兰蔻)
  领先维度: 情感稳定 (无波动, 竞品均有波动)
  机会点: 本品牌在"敏感肌"细分主题仍是第 1 (竞品未覆盖)
```

**Data Recipe**: `competitor_matrix` + `competitor_recent_events` + `competitor_trend_series` + `gap_opportunity_analysis`。

---

**Section 8: 诊断摘要 · 执行者 Layer 3 主场**
- `primaryReader`: operator; `insightStackLayers`: ['observation', 'explanation', 'direction']
- **本 Section 是整份报告 Layer 3 的主要承载处**

```
[诊断计数 · 趋势状态分组]
  P0: 0 新增, 1 持续 (DIAG-2011 熬夜急救引用丢失)
  P1: 2 新增 (DIAG-2041, DIAG-2042), 1 持续, 1 已改善
  P2: 3 新增, 2 改善, 8 持续
  P3: 5 个小问题 (折叠不展开)

[P0/P1 诊断详情卡 · 每条含 5 段]
  ── DIAG-2011 · P0 · 持续 3 周 ────
  【触发】 "熬夜急救"主题 SoV -6pt, ChatGPT 引用份额 -8pt
  【因果链】 ChatGPT 在该主题改用科普体 → 品牌名被挤出 → 需更多权威引用回补
           confidence: medium (3 条响应证据)
  【对标】  我方 12% | 行业中位 18% | Top1(兰蔻) 30% | 差距 -18pt
  【优先级】 P0, impact=9, ease=5, urgency=9 (comp_score=7.7)
  【方向 · 锚点问题】
    ① 该主题 Top5 引文来源是谁? 我方官网/权威媒体是否被 ChatGPT 索引?
    ② 过去 3 周竞品兰蔻在该主题发过多少条内容? URL 清单?
    ③ 我方内部是否有该主题的 Q&A/科普素材, 是否被结构化发布?
    ④ 若启动内容补位, 预计产出周期多长? 4 周内能否追回?
    ⑤ 是否存在与 KOL/权威媒体的合作机会加速引用?
  【不干预后果】 4 周内 SoV 预计跌至 8%, 行业排名预计 #5 → #8
  【CTA】 需要执行方案? [预约 30 分钟诊断咨询 →]

[诊断追溯与关联]
  DIAG-2011 ←→ DIAG-2042 (同一主题派生的产品级诊断)
  DIAG-2011 ←→ DIAG-1987 (已改善, 上季度同类诊断的教训)

[P2/P3 折叠列表]
  DIAG-2053 · P2 · [标题] ...
  ...
```

**Data Recipe**: `diagnostics` 表 (含本次 4.8 升级的 schema 字段: causalChain, industryBenchmark, priorityScore, timeSeries, anchorQuestions, relatedDiagnostics)。

**Narrative Formula**: 由 4.8 诊断撰写公式直接复用。

---

**Section 9: 🆕 Anchor Actions · 本期锚点行动清单** (周报/月报必含)
- `primaryReader`: operator; `insightStackLayers`: ['direction']
- **纯 Layer 3**: 本周/本月应当 focus 的 3–5 个问题, 以锚点问题形式呈现, 不给执行剧本

```
本期 Focus (本周 3 个问题, 按优先级排序):

1. P0 · 熬夜急救主题引用丢失 (DIAG-2011 衍生)
   锚点问题:
   □ 主题 Top5 引文来源是谁?
   □ 我方相关内容是否被 AI 引擎索引?
   □ 4 周内能否产出补位内容?
   
2. P1 · 产品 A 在 DeepSeek 配方描述错误 (DIAG-2041)
   锚点问题:
   □ 错误描述的来源是哪份第三方文章?
   □ 官网产品页结构化数据是否正确?
   □ 是否需要提交 DeepSeek feedback?

3. P1 · 兰蔻 "实验室科技"叙事抢占 (DIAG-2042)
   锚点问题:
   □ 我方在 "科技感" 维度的现有内容盘点?
   □ 是否有实验室合作/专利可用作内容素材?
   □ 与 Branding 团队的叙事策略是否一致?

[复盘表] 上期锚点行动关闭情况 (月报必含)
  上期 Focus 3 个, 本期:
    关闭 1 (指标改善)
    仍在 1 (需要继续)
    失效 1 (指标已自然回正, 无需干预)
```

---

**Section 10: CTA · 咨询服务引导**
- `primaryReader`: manager; `insightStackLayers`: []

(与原有设计一致, 保留)

---

**报告类型 × Section 分发矩阵** (升级版):

| Section | 周报 | 月报 | 即时报告 | 线索诊断 | 主读者 | Stack |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 Executive Summary | ✓ | ✓ | ✓ | ✓ | 上级 | L1+L2 |
| 2 PANO Score 详情 | 简版 | 完整 | ✓ | ✓ | 执行者 | L1+L2 |
| 3 行业格局 | ✓ | ✓ | ✓ | — | 上级 | L1+L2 |
| 4 品牌表现 | ✓ | ✓ | ✓ | ✓ | 执行者 | L1+L2 |
| 5 🆕 Branding Narrative | — | ✓ | 可选 | ✓ | Branding | L1+L2 |
| 6 产品竞争力 | — | ✓ | 可选 | ✓ | 执行者 | L1+L2 |
| 7 竞品对比 | 简版 | ✓ | ✓ | Top3 | 执行者/上级 | L1+L2 |
| 8 诊断摘要 | P0+P1 | 全 | ✓ | 全+突出 | 执行者 | L1+L2+L3 |
| 9 🆕 Anchor Actions | ✓ | ✓ | ✓ | — | 执行者 | L3 |
| 10 CTA | ✓ | ✓ | ✓ | 强化 | 上级 | — |

**篇幅控制 (更新)**:
- 周报: ~2500 字 (原 2000, 新增 anchor actions 扩展)
- 月报: ~5500 字 (原 4000, 新增 Branding Narrative + anchor actions)
- 即时: 弹性
- 线索: ~2500 字 PDF (原 1500, 新增 Branding 风险页)

#### 4.7.3 报告生成逻辑

```
┌─────────────────────────────────────────────────────────────┐
│  Report Generation Pipeline                                  │
│  ════════════════════════════════════════════════════════    │
│                                                              │
│  Step 1: 数据聚合 (Data Aggregation)                         │
│  ├── 输入: periodStart, periodEnd, projectId, brandId        │
│  ├── 从 MetricSnapshot 查询 (平台统一数据)                    │
│  ├── 聚合各 Section 所需指标 (环比、排名、趋势)              │
│  └── 输出: ReportDataContext (结构化数据包)                   │
│       约 20-30 个 SQL 查询，耗时 <5s                         │
│                                                              │
│  Step 2: 诊断关联 (Diagnostic Linking)                       │
│  ├── 查询本 period 内产生的 GEODiagnostic                    │
│  ├── 按 severity 排序，P0/P1 优先                            │
│  ├── 标记已改善 / 新增 / 持续未解决                          │
│  └── 输出: DiagnosticContext                                 │
│                                                              │
│  Step 3: LLM 叙述生成 (Narrative Generation)                 │
│  ├── 每个 Section 独立调用 LLM 生成叙述段落                  │
│  ├── 输入: Section 类型 + 对应数据点 + 上期报告摘要 (如有)   │
│  ├── Prompt 约束:                                            │
│  │   - 使用客观数据驱动的叙述，不做主观评价                  │
│  │   - 突出变化和异常，忽略平稳无变化的维度                  │
│  │   - 字数控制: 按 Section 定义的篇幅上限                   │
│  │   - 中文输出，专业但不晦涩                                │
│  │   - Executive Summary 和 CTA 可适度使用引导性语言         │
│  ├── LLM: 火山引擎 API (DeepSeek/豆包模型)                   │
│  ├── 并发: 各 Section 可并行生成                             │
│  └── 输出: 每个 Section 的 narrative string                  │
│       约 6-8 次 LLM 调用，耗时 <15s (并发)                   │
│                                                              │
│  Step 4: 模板渲染 (Template Rendering)                       │
│  ├── 将 Section 数据 + LLM 叙述 + 图表定义合并               │
│  ├── 渲染 Markdown 版本 (MVP 主格式)                         │
│  ├── 渲染 JSON 版本 (Agent 消费)                             │
│  ├── 异步生成 PDF 版本 (图表渲染 + 样式排版)                 │
│  └── 输出: markdownContent + jsonData + pdfUrl               │
│                                                              │
│  Step 5: 存储 & 配送 (Storage & Delivery)                    │
│  ├── 存入 Report 表，status → 'completed'                    │
│  ├── Dashboard 可查看/下载                                   │
│  ├── 邮件发送 (含 Markdown 正文 + PDF 附件)                  │
│  └── MCP/API 可拉取                                         │
│                                                              │
│  总耗时预估: <30s (数据聚合 5s + LLM 15s + 渲染 5s + 存储 5s) │
└─────────────────────────────────────────────────────────────┘
```

**LLM Prompt 模板 (Executive Summary 示例)**:

```
你是 GENPANO GEO 监测平台的报告分析师。请根据以下数据为品牌"{brandName}"生成本期监测报告的 Executive Summary。

## 数据输入
- 报告周期: {periodStart} ~ {periodEnd}
- 品牌 PANO Score: 当前 {currentScore} ({grade})，上期 {previousScore}，变化 {changePercent}%
- 子维度变化: V={vChange}, R={rChange}, S={sChange}, C={cChange}, A={aChange}
- P0 诊断数: {p0Count}，P1 诊断数: {p1Count}
- 最紧急诊断: {topDiagnosticTitle}
- 行业 SoV 排名: 当前 #{sovRank}，上期 #{prevSovRank}
- 提及率变化最大的引擎: {topChangeEngine} ({topChangePercent}%)

## 输出要求
- 200 字以内的中文段落
- 开头用一句话概括本期整体趋势 (上升/下降/稳定)
- 必须提及 PANO Score 变化和等级
- 如有 P0/P1 诊断，必须一句话提及最紧急的问题
- 客观数据驱动，不使用"建议""应该"等指令词
- 语气专业、简洁，适合品牌负责人快速阅读
```

#### 4.7.4 报告调度与配置

**自动报告调度**:

```typescript
interface ReportSchedule {
  projectId: string;
  type: 'weekly' | 'monthly';
  enabled: boolean;              // 用户可开关
  cronExpression: string;        // 默认: 周报 "0 8 * * 1", 月报 "0 8 1 * *"
  timezone: string;              // 用户时区，默认 Asia/Shanghai
  emailRecipients: string[];     // 发送邮箱列表 (默认为注册邮箱)
  includePdf: boolean;           // 是否附带 PDF (默认 true)
}
```

**MVP 默认行为**:
- 用户创建 Project 后，自动启用周报和月报
- 默认发送至注册邮箱
- 用户可在"设置 → 报告"中关闭自动报告或修改收件人
- 即时报告无需配置，点击即生成

**线索诊断报告触发**:
- 用户在诊断详情页点击 CTA → 填写线索表单 → 提交后自动触发
- 报告内容聚焦该品牌，诊断部分完整展示，CTA 区域强化
- 同时发送给: (1) BD 团队邮箱 (管理员配置), (2) 用户邮箱 (可选)

#### 4.7.4a 线索诊断报告四层 Section 结构 (2026-04-16 升级)

> **升级动机**: 原线索诊断报告结构与即时报告高度重合，CTA 只是尾部加强，缺少"让 BD 接单容易 + 让客户感到问题严重 + 让咨询价值自然呈现"的专业感。升级后采用 **Quick Wins / Strategic Bets / Branding Risks / Consulting Accelerators** 四层 section 架构，每层目标读者/洞察层级不同。

```
┌─────────────────────────────────────────────────────────────┐
│  Lead Diagnostic Report — 4-Layer Architecture              │
├─────────────────────────────────────────────────────────────┤
│  P1  Executive Cover (上级导读)                            │
│      → 复用 4.6.3 P1, 加线索表单信息                        │
│                                                             │
│  L1  Quick Wins (执行者, Stack L1+L2+L3)                   │
│      4 周内可自解决的问题 · 2-3 条                          │
│      目的: 让客户体验到"平台给我价值了", 建立信任           │
│                                                             │
│  L2  Strategic Bets (上级, Stack L1+L2)                    │
│      需要资源投入的核心风险 · 2-3 条                        │
│      目的: 让上级看到"这是战略级问题, 不是小修小补"         │
│                                                             │
│  L3  Branding Risks (Branding, Stack L1+L2)               │
│      品牌叙事层面的风险 · 1-2 条                            │
│      目的: 让 Branding 参与决策, 扩展决策圈                 │
│                                                             │
│  L4  Consulting Accelerators (上级, 关联咨询价值)          │
│      "以下问题建议咨询介入" · 1-2 条 + 咨询价值点           │
│      目的: 为 BD 跟进提供结构化切入点                       │
│                                                             │
│  Pn  Appendix: 数据来源 / 监测方法 / 联系方式              │
└─────────────────────────────────────────────────────────────┘
```

**L1 · Quick Wins · 执行者速解型**
- **选取规则**: `priorityScore.ease >= 7 AND priorityScore.composite >= 5.5` (容易解 + 有一定影响)
- **典型类型**: `product_misinformation` / `citation_source_loss` / 部分 `visibility_decline`
- **每条包含**: L1 观察 + L2 解释 + L3 anchor questions (3 条) + "4 周内可自行修复" 标签
- **示例**:
  ```
  📌 Quick Win #1: DeepSeek 中"小棕瓶精华"成分描述错误
  [L1] AI 错误描述: 含酒精 (实际不含), 影响 DeepSeek 中 12% 响应
  [L2] 触发: 第三方文章 X 被 AI 采样 → 错误信息扩散
       confidence: high (可追溯到 3 个引用源)
  [L3] Focus: 结构化数据 + feedback
       锚点: ① 官网产品页 schema 是否完整? ② 是否已向 DeepSeek 提交纠错?
       ③ 关联的第三方文章能否联系修正?
       ⚠️ 不干预: 错误描述可能被更多 AI 引擎采样固化
  💡 "4 周内可自行修复" — 不需要专业咨询
  ```

**L2 · Strategic Bets · 上级决策型**
- **选取规则**: `priorityScore.impact >= 8 AND priorityScore.ease <= 6` (高影响 + 难解决)
- **典型类型**: `competitor_overtake` / `new_entrant` / 高影响的 `visibility_decline`
- **每条包含**: L1 观察 + L2 解释 + `decisionPrompt` (给上级一句决策提问) + `predictedImpact` (干预收益) + `ifUntreated` (不干预损失)
- **示例**:
  ```
  📌 Strategic Bet #1: 兰蔻在"科技抗老"心智中快速抢占
  [L1] 兰蔻 SoV 上升 6pt, 反超本品牌至第 2 位
       过去 4 周上线 "实验室科技" 主题内容 8 篇, 被 ChatGPT 索引
  [L2] 触发: 我方在"科技感"维度内容库存断档
       confidence: high
  [决策问题] "是否在下季度加投预算追赶'科技抗老'内容战线? 
              预估投入约 X 万, 窗口期 8 周内"
  [干预收益] 预计 SoV 回升 3-5pt, PANO Score +4~6 (medium confidence)
  [不干预] 8 周后本品牌可能被进一步推到第 4 位, 心智固化 6-12 个月难逆
  ```

**L3 · Branding Risks · 品牌叙事型**
- **选取规则**: `readerHints` 包含 'branding' 的所有诊断, 按 `priorityScore.composite` 取 Top 1-2
- **典型类型**: `narrative_drift` / `sentiment_shift`
- **每条包含**: 叙事层面的 L1 观察 + L2 解释 + 2-3 条 AI 原文引语 + 竞品叙事对比一句话
- **示例**:
  ```
  📌 Branding Risk #1: AI 人设正在从"前沿抗老"漂移至"传统稳定"
  [L1 · 叙事观察] "创新""科技""前沿" 在本品牌的 AI 描述中下降 40%, 
                  "经典""稳定""老牌" 上升
  [L2 · 叙事解释] 假设: 竞品抢占"科技"心智 + 我方近期无科技叙事内容
                   confidence: med
  [典型引语]
    🔴 "XX 近年在新品创新速度上稍慢于兰蔻..." (豆包, 2026-04-12)
    🟡 "XX 是高端美妆中最稳定的抗老品牌..." (ChatGPT, 2026-04-10)
  [竞品叙事对比] 兰蔻被描述为 "科技 · 新锐 · 前沿", 我方为 "经典 · 稳定"
  ```

**L4 · Consulting Accelerators · 咨询价值切入点**
- **选取规则**: 需要跨职能协作 / 长期投入 / 不适合客户自查的问题 (典型: `ease <= 4`)
- **每条包含**: 问题概括 + "为什么需要专业咨询介入" + 对应的 GEO 咨询服务层级 (L1/L2/L3)
- **示例**:
  ```
  📌 建议咨询介入 #1: 品牌叙事漂移 + 竞品心智抢占
  为什么需要咨询: 
    - 涉及跨职能 (Branding + Content + PR), 单一团队难驱动
    - 窗口期 8 周, 错过后心智固化难逆
    - 需要竞品情报 + 内容策略 + 执行监测的完整方案
  对应服务层级: L2 GEO 优化方案 (预估 5-8 万)
  下一步: [预约 30 分钟咨询] — 我们会基于本报告深入拆解
  ```

**报告尾部强化 CTA**:
- 不再是简单的"预约咨询", 而是按问题归类的切入点
- 每个 Consulting Accelerator 后直接跟"预约咨询"按钮, BD 端可看到"客户点击了哪个问题的咨询入口"
- 附 GENPANO 咨询团队简介 (1 段) + 咨询流程说明 (诊断 → 提案 → 签约 → 交付)

**篇幅**: ~2500 字 PDF, 6-8 页 (比周报长, 有更多叙事深度)

#### 4.7.5 输出格式

**Markdown (MVP 主格式)**:
- 所有报告首先生成 Markdown 版本
- Markdown 内嵌数据表格 (使用 GFM 表格语法)
- 图表以文字数据表格 + 趋势描述代替 (Markdown 不支持原生图表)
- Agent 通过 API/MCP 拉取时直接返回 Markdown 或 JSON

**PDF (导出格式)**:
- 基于 Markdown 内容 + ReportChart 定义渲染
- 使用 Node.js PDF 库 (如 puppeteer 或 @react-pdf/renderer)
- 包含 GENPANO 品牌 header/footer、页码
- 图表渲染为 SVG/PNG 嵌入 PDF
- 线索诊断报告的 PDF 带 GENPANO 水印和联系方式

**JSON (Agent 格式)**:
- ReportJSON 结构化数据，无叙述文本
- 适用于 Agent 消费和二次加工
- 通过 API `Accept: application/json` 或 MCP 获取

#### 4.7.6 报告与商业化的衔接

报告在咨询转化漏斗 (4.9) 中扮演三个角色:

```
角色 1: 日常价值交付 (留存驱动)
  周报/月报 → 用户持续获得价值 → 平台粘性 → 持续暴露诊断问题 → 转化机会

角色 2: 线索转化催化剂
  用户点击 CTA → 线索诊断报告自动生成 → BD 拿到带数据的线索 → 首次沟通更高效

角色 3: 内容获客工具 (Phase 2)
  行业 GEO 趋势公开报告 → SEO/社交传播 → 吸引新用户注册
```

**报告中的 CTA 设计**:
- 周报/月报: 尾部固定 CTA 区域 + 基于最严重诊断的动态 CTA 文案
- 线索诊断报告: 每个诊断条目后紧跟迷你 CTA，报告尾部为强化版 CTA (含咨询师介绍、预约链接)
- 即时报告: 与周报相同的 CTA 策略

#### 4.7.7 API & MCP 报告接口

**RESTful API** (扩展 4.5.1):

```
# 报告管理
GET    /api/v1/projects/:id/reports              # 报告列表 (分页, 支持 type 过滤)
GET    /api/v1/projects/:id/reports/latest        # 最新报告
GET    /api/v1/projects/:id/reports/:reportId     # 报告详情 (Accept: text/markdown | application/json | application/pdf)
POST   /api/v1/projects/:id/reports/generate      # 生成即时报告

# 报告调度
GET    /api/v1/projects/:id/report-schedules      # 获取调度配置
PUT    /api/v1/projects/:id/report-schedules      # 更新调度配置
```

**MCP Tool** (扩展 4.5.2):

```yaml
- name: genpano_generate_report
  description: "生成品牌 GEO 监测报告"
  parameters:
    project_id: string
    type: "weekly" | "monthly" | "on_demand"     # 报告类型
    format: "markdown" | "json"                   # 输出格式
    period_start?: string                         # 自定义起始日期 (on_demand 时使用)
    period_end?: string
  returns:
    report_id: string
    status: string
    content: string            # Markdown 或 JSON 字符串
    pdf_url?: string

- name: genpano_get_report
  description: "获取已生成的报告内容"
  parameters:
    report_id: string
    format: "markdown" | "json"
  returns:
    content: string
    metadata: object
```

#### 4.7.8 报告存储与清理

- 报告存储在对象存储 (如 Supabase Storage / Cloudflare R2)
- Markdown/JSON 内容同时存入数据库 Report 表 (方便查询)
- PDF 文件存入对象存储，Report 表存 URL
- 保留策略: 最近 52 周的周报 + 最近 24 个月的月报 + 所有线索诊断报告永久保留
- 即时报告保留 90 天

#### 4.7.9 MVP 边界

**MVP 必须实现**:
- 周报和月报自动生成 (Markdown 格式)
- LLM 生成 Executive Summary 和各 Section 叙述
- Dashboard 报告列表页 + 报告详情页 (渲染 Markdown)
- 邮件发送报告 (Markdown 正文)
- API/MCP 拉取报告
- 诊断摘要 Section (含 P0/P1 突出显示)
- 报告尾部 CTA

**MVP 可简化**:
- PDF 导出: MVP 可使用浏览器端 window.print() 作为临时方案，Phase 2 实现服务端 PDF 渲染
- 图表: MVP 的 Markdown 报告用数据表格代替图表，PDF 图表推迟
- 线索诊断报告: MVP 可复用即时报告逻辑，仅额外添加强化 CTA
- 报告调度配置 UI: MVP 使用默认配置，Phase 2 开放用户自定义

**Phase 2 增强**:
- 服务端 PDF 渲染 (带图表、品牌样式)
- 咨询客户复盘报告 (优化前后 PANO Score 对比)
- 行业 GEO 趋势公开报告 (获客用)
- 报告模板自定义 (选择包含哪些 Section)
- 多语言报告 (英文版)

### 4.8 GEO 优化诊断建议 (服务钩子)

#### 4.8.0 设计定位

**核心原则**: 免费工具展示"病情诊断" (What & Why)，付费咨询服务提供"治疗方案" (How)。

优化诊断建议是 GENPANO 从纯监测工具转化为咨询服务入口的关键模块。它不是独立的优化产品，而是基于已有监测数据的智能解读层——让用户意识到问题的存在和严重性，从而产生咨询需求。

```
监测数据 (4.4 分析引擎)
     │
     ▼
┌──────────────────────────────────┐
│  优化诊断引擎                      │
│  ├── 问题检测: 识别异常和劣势       │
│  ├── 归因分析: 为什么出现这个问题   │
│  ├── 严重度评分: P0/P1/P2/P3       │
│  └── 方向指引: 大致优化方向         │
│       (不含具体执行步骤)            │
└────────────┬─────────────────────┘
             │
             ▼
┌──────────────────────────────────┐
│  Dashboard 展示                    │
│  ├── 诊断卡片 (问题 + 严重度)      │
│  ├── 趋势对比 (恶化/改善)          │
│  └── CTA: "需要专业优化方案？      │
│           联系我们的 GEO 顾问"     │
└──────────────────────────────────┘
```

#### 4.8.1 诊断类型

**品牌维度诊断**:
- **可见度下降**: 品牌提及率在某引擎/某类 Topic 中持续下降
- **负面情感异常**: 情感分数出现显著负面偏移
- **竞品超越告警**: 竞品在关键 Topic 中排名反超
- **引用来源缺失**: AI 引擎未引用品牌官方权威来源
- **引用来源丢失** (`citation_source_loss`, P1): T-14d Tier 1+2 权威来源集 vs T-0 出现显著 set diff — 检测算法 + evidence schema 固化于 §4.2.6.F
- **引用归因失配** ⭐ 2026-04-17 新增 (`citation_attribution_mismatch`, P2): 品牌在 AI 回答中 **有被引用** 但 `official_domain` 归因占比 < 40% 且 PANO A 落后 — 指向官域未收录 / 别名缺失 / 子域漏配 三类假设。完整触发条件 + Evidence schema + Anchor Questions 固化于 §4.2.7.A
- **推荐语境偏差**: 品牌被推荐的场景与定位不符

**产品维度诊断**:
- **产品信息失真**: AI 回答中的产品特性/价格与事实不符
- **产品被遗漏**: 在高相关度 Topic 中产品未被提及
- **竞品替代风险**: 竞品在同类 Topic 中被优先推荐

**行业维度诊断**:
- **市场份额变化**: 行业 Share of Voice 格局发生显著变动
- **新竞争者入场**: 新品牌/产品在行业 Topic 中频繁出现

#### 4.8.2 诊断输出格式 (深度升级版)

> **升级说明**: 2026-04-16 在原有 `possibleCauses / direction / predictedImpact / benchmarkReference` 基础上，根据 "洞察 Stack + 三读者视角" 框架 (4.7.0-a) 扩展了 **causalChain / industryBenchmark (结构化) / priorityScore / timeSeries / relatedDiagnostics / anchorQuestions / readerHints** 七组字段，让诊断从"指标堆砌"进化为"可追溯、可复盘、可分发的洞察 unit"。

每条诊断建议包含:

```typescript
interface GEODiagnostic {
  id: string;
  type: 'brand' | 'product' | 'industry';
  category: string;                   // 如 'visibility_decline', 'sentiment_shift'
  severity: 'P0' | 'P1' | 'P2' | 'P3';
  title: string;                      // "小棕瓶在ChatGPT的抗衰精华推荐中排名从#2降至#5"
  description: string;                // 问题描述 (What)
  
  // ── Layer 1 · Observation ────────────────────────────────
  evidence: {                         // 数据支撑
    metric: string;
    currentValue: number;
    previousValue: number;
    changePercent: number;
    timeRange: string;
    affectedQueries: string[];
    affectedEngines: string[];
    responseSamples?: {               // 🆕 原文证据 (供 Branding/审计)
      engine: string;
      promptId: string;
      responseId: string;
      snippet: string;                // 原文片段 <=200 字
      capturedAt: string;
    }[];
  };
  
  // ── Layer 2 · Explanation ────────────────────────────────
  possibleCauses: string[];           // 可能原因 (Why, 保留, 用于向 LLM 输入假说)
  causalChain: {                      // 🆕 结构化因果链 (替代单纯 possibleCauses 的扁平列表)
    triggerMetrics: string[];         // 触发本诊断的指标 ID 列表
    hypothesizedMechanism: string;    // 机制假设 (一段话)
    supportingEvidence: string[];     // 支撑证据 ID (responseSamples / 引用来源 diff / 竞品动作)
    contradictingEvidence?: string[]; // 反证 (若存在)
    confidenceLevel: 'low' | 'medium' | 'high';
    alternativeHypotheses?: string[]; // 备选假设 (供咨询深挖)
  };
  
  industryBenchmark: {                // 🆕 结构化的行业对标 (替代自由文本 benchmarkReference)
    metric: string;                   // 对标维度
    myValue: number;
    industryMedian: number;
    industryTop10Avg: number;
    topCompetitor: {                  // 该指标下的标杆
      brandId: string;
      brandName: string;
      value: number;
      keyCharacteristics: string[];   // 标杆品牌在该维度的数据特征 (不含 How-to)
    };
    gapAnalysis: {
      gapToMedian: number;            // 正/负
      gapToTop: number;
      percentileRank: number;         // 1-100
    };
  };
  
  // ── Layer 3 · Direction ──────────────────────────────────
  direction: string;                  // 大致优化方向 (如 "需要加强品牌在权威评测媒体的内容布局")
  focusArea: string;                  // 🆕 锚点焦点区域 (简短 label, 如 "熬夜急救主题内容丢失")
  anchorQuestions: string[];          // 🆕 3-5 个 self-diagnostic questions (替代剧本式 action list)
                                      // 示例: "① 该主题 Top5 引文来源是谁?" 
                                      //       "② 我方内容是否已被 AI 引擎索引?"
                                      //       "③ 4 周内能否产出补位内容?"
  ifUntreated: {                      // 🆕 不干预后果 (原 predictedImpact 的反向投射)
    metric: string;
    projectedValue: number;           // 预计恶化到什么值
    timeframe: string;                // "4 weeks"
    confidence: 'high' | 'medium' | 'low';
    scenarioDescription: string;      // 一句话描述惨态
  };
  predictedImpact?: {                 // 量化预期影响 (若干预, 保留)
    metric: string;
    projectedChange: number;
    timeframe: string;
    confidence: 'high' | 'medium' | 'low';
  };
  
  // ── 优先级 & 时间维度 ──────────────────────────────────────
  priorityScore: {                    // 🆕 结构化优先级 (替代单一 severity)
    impact: number;                   // 1-10, 对 PANO/SoV 的影响量级
    ease: number;                     // 1-10, 解决的容易度 (高=容易)
    urgency: number;                  // 1-10, 时间敏感度
    composite: number;                // (impact * 0.5 + ease * 0.2 + urgency * 0.3)
    rankWithinPeriod: number;         // 本期所有诊断中的排名
  };
  
  timeSeries: {                       // 🆕 诊断生命周期
    firstObservedAt: string;          // 首次被检测到
    lastUpdatedAt: string;
    trendStatus: 'new' | 'growing' | 'persisting' | 'improving' | 'resolved';
    ageInDays: number;
    severityHistory: {                // 严重度随时间的变化
      date: string;
      severity: 'P0' | 'P1' | 'P2' | 'P3';
    }[];
  };
  
  relatedDiagnostics: {               // 🆕 关联诊断 (用于追溯 + 复盘)
    derivedFrom?: string[];           // 由哪些更大的诊断派生
    childDiagnostics?: string[];      // 派生出的子诊断 (产品级 / 引擎级)
    historicalSimilar?: string[];     // 历史上同类诊断 (供学习教训)
  };
  
  // ── 读者分发 ────────────────────────────────────────────
  readerHints: ('operator' | 'manager' | 'branding')[];  // 🆕 本诊断适合哪几类读者看
                                                         // operator (default, 全部) / 
                                                         // manager (涉及资源/决策) / 
                                                         // branding (涉及叙事/情感)
  decisionPrompt?: string;            // 🆕 给上级看的决策一句话 (如: "是否加投 2 周内容预算补位?")
  
  // ── 元信息 & CTA ──────────────────────────────────────
  ctaType: 'consulting' | 'report';  // 关联的服务类型
  createdAt: string;
  resolvedAt?: string;                // 如果后续监测显示问题已改善
}
```

**严重度定义** (与 priorityScore 并存, severity 是粗分类, priorityScore 是细打分):
- **P0 (紧急)**: 品牌在核心 Topic 中完全消失、严重负面描述 (composite >= 8.5)
- **P1 (重要)**: 排名大幅下降 (>3位)、情感从正转负 (composite 6.5-8.4)
- **P2 (关注)**: 轻微排名波动、竞品缩小差距 (composite 4.5-6.4)
- **P3 (信息)**: 可优化空间提示、行业趋势变化 (composite < 4.5)

#### 4.8.2a Anchor Questions 框架 (Layer 3 专用)

> **为什么用锚点问题替代执行步骤**: 4.7.0-a 洞察 Stack 的 Layer 3 原则明确：平台不给 playbook (那是咨询业务)。锚点问题 = 让客户**自己问对问题**。问得到的客户可以自己解；问不到的客户，正是咨询服务 ICP。

**锚点问题撰写规则** (用于 4.8.3 诊断生成):

```
锚点问题 = 事实探查型问题 (非决策型, 非执行型)

✅ 合格锚点问题:
  "该主题 Top5 引文的来源是谁？"          (事实探查)
  "我方内容是否已被 AI 引擎索引？"        (事实核查)
  "4 周内能否产出补位内容？"              (能力评估)
  "该错误描述的来源是哪份第三方文章？"    (溯源)
  "官网产品页结构化数据是否正确？"        (自审)

❌ 不合格锚点问题:
  "要不要去小红书发文？"                  (具体渠道, 变 playbook)
  "你们打算怎么解决？"                    (空泛, 无帮助)
  "需要加预算吗？"                        (决策, 非锚点)

锚点问题数量: 3-5 个
锚点问题顺序: 从易到难 / 从事实到行动能力 / 从内审到外探
```

**锚点问题 × 诊断类型模板**:

| 诊断 Category | 典型锚点问题骨架 |
|--------------|------------------|
| `visibility_decline` | ① 失去份额的主题是什么？ ② Top5 引文是谁？ ③ 我方相关内容是否被索引？ ④ 补位窗口多长？ ⑤ 是否存在合作加速路径？ |
| `sentiment_shift` | ① 负面关键词的原始来源是哪些内容？ ② 该来源的权重能否下降？ ③ 是否有 UGC 能覆盖？ ④ 品牌官方是否有澄清通道？ |
| `competitor_overtake` | ① 竞品近期发了什么？ ② 我方在同主题的内容库存？ ③ 引文来源差异在哪？ ④ 是否需要 Branding 配合？ |
| `citation_source_loss` | ① 丢失的 Top 引用来源是谁？ ② 该来源停发或改写原因？ ③ 是否存在替代来源？ ④ 官方结构化数据能否补位？ · **检测算法 + evidence schema 见 §4.2.6.F** |
| `citation_attribution_mismatch` | ① 近 3 个月新增的官方子域是否已在 `brand.domains`？ ② 官方内容是否提供 AI 可识别的结构化元数据 (JSON-LD / OG)？ ③ Tier 2 媒体提到本品牌时是否附带官域链接？ · **检测条件 + Evidence schema + 禁止互斥触发规则见 §4.2.7.A** |
| `product_misinformation` | ① 错误信息来源是哪份内容？ ② 是否能通过 feedback / 官方声明纠正？ ③ 结构化数据是否完整？ |
| `product_missing` | ① 该主题的 Top 产品是什么？ ② 我方产品是否在同主题有内容？ ③ 是否是命名/别名识别失败？ |
| `new_entrant` | ① 新竞品的起势内容是什么？ ② 它抢占了我方哪些主题份额？ ③ 是否威胁到核心品类？ ④ 观察窗口多长再决策？ |
| `narrative_drift` (Branding) | ① 漂移前后的人设词是什么？ ② 漂移对应的内容事件？ ③ 竞品是否主动塑造？ ④ 是否需要 PR 介入？ |

#### 4.8.3 诊断生成逻辑

诊断基于 4.4 分析引擎的指标数据，通过规则引擎 + LLM 组合生成:

**规则引擎 (确定性检测)**:
- 提及率环比下降 > 20% → 触发可见度下降诊断
- 情感分数跌破阈值 → 触发负面情感异常
- 竞品排名反超 → 触发竞品超越告警
- 产品信息与配置数据不匹配 → 触发产品信息失真

**LLM 辅助 (归因、方向、预期影响)**:
- 将检测到的异常 + 上下文数据 (Topic/Prompt 内容、AI 回答原文、时间趋势) 送入 LLM
- LLM 生成 possibleCauses、direction、predictedImpact 字段
- Prompt 明确约束: 
  - 只输出方向性建议，不输出具体执行步骤
  - predictedImpact: 基于历史数据和行业样本，预估修复该问题可带来的 PANO Score 改变和时间周期
  - benchmarkReference: 从该行业 PANO Score Top 品牌中提取参考特征 (如提及率、排名、情感等数值)，不含优化方案

#### 4.8.4 Dashboard 展示

**诊断总览卡片** (Dashboard 首页):
- 按严重度排列的诊断列表
- 每张卡片: 标题 + 严重度标签 + 影响范围 (哪些引擎/Topic)
- 趋势箭头: 问题在恶化还是改善

**诊断详情页**:
- 完整的 evidence 数据可视化
- possibleCauses 列表
- direction 提示
- **量化预期影响** (新增): 
  - 显示修复该诊断问题预计可改善的 PANO Score 变化 (如 "+8 points")
  - 预期达成周期 (如 "4-6 weeks")
  - 置信度标签 (High/Medium/Low)
- **同行业 Top 品牌参考** (新增):
  - 展示该行业 PANO Score 最高的 3 个品牌
  - 这些品牌的关键指标对标 (提及率、排名、情感分数等)
  - 用户可看到"标杆品牌的表现是什么样的"，而非"应该怎么做"
- **CTA 区域**: "想知道具体怎么优化？联系 GEO 顾问获取定制方案"

**报告中的诊断**:
- 周报/月报自动包含诊断摘要
- P0/P1 诊断在报告中突出显示

#### 4.8.5 诊断建议颗粒度规范 (Diagnostic Direction Spec)

> 核心挑战: 方向性建议太模糊 → 用户觉得没价值、不转化。太具体 → 用户自己能做、不需要咨询。
> 目标: 让用户**看到问题的全貌和紧迫性**，意识到"我需要专业帮助"，而不是"我自己就能搞定"。

**颗粒度标尺 (1-5)**:

```
Level 1 (太模糊 ❌): "建议关注 PR"
Level 2 (略模糊 ❌): "需要加强品牌内容建设"
Level 3 (目标颗粒度 ✅): "品牌在权威评测媒体的引用覆盖不足——
                          行业 Top 品牌平均被 12 个权威来源引用，你仅有 3 个。
                          优化方向：增加品牌在第三方权威评测中的曝光密度。"
Level 4 (偏具体 ⚠️): "需要在什么值得买、知乎等平台增加专业评测内容"
Level 5 (太具体 ❌): "在什么值得买发布3篇横评文章，联系KOL张三做视频评测"
```

**GENPANO 目标: Level 3** — 给出问题诊断 + 数据对标 + 优化方向，但不给出具体执行渠道和动作。

**诊断建议撰写公式**:

```
[问题陈述] + [数据证据] + [标杆对比] + [优化方向] + [不干预后果]

= 完整的诊断建议
```

**各诊断类型的具体示例**:

**品牌可见度下降**:
```
❌ Level 1: "品牌可见度下降，建议优化"
❌ Level 2: "品牌在 ChatGPT 中可见度下降，需要加强内容建设"
✅ Level 3: "你的品牌在 ChatGPT「抗衰精华推荐」类 Topic 中提及率从 78% 降至 45%，
            环比下降 42%。同行业 Top 3 品牌（雅诗兰黛/兰蔻/SK-II）平均提及率保持
            在 85% 以上。下降主要发生在近 2 周，与竞品新品发布周期吻合。
            优化方向：提升品牌在「抗衰」语义场景中的内容权威性和覆盖密度。
            若不干预，预计 PANO Score 将在 30 天内从 B(72) 降至 C(61)。"
❌ Level 5: "在小红书发布5篇抗衰成分科普文，联系美丽修行APP做成分评测"
```

**负面情感异常**:
```
❌ Level 1: "情感偏负面，注意品牌形象"
✅ Level 3: "品牌在 DeepSeek 中的情感得分从 0.72(正面) 骤降至 0.31(负面)，
            降幅 57%。AI 回答中出现的负面关键词集中在「过敏」「刺激」「不适合敏感肌」。
            追溯发现，近期 3 条高权重负面内容被 AI 频繁引用。
            同行业正面情感均值为 0.68，你目前处于行业末位 (排名 18/20)。
            优化方向：稀释负面内容源的权重，增强正面用户体验内容的可引用性。
            若不干预，负面情感可能随时间固化在 AI 模型的品牌认知中。"
```

**竞品超越告警**:
```
❌ Level 1: "竞品排名超过你了"
✅ Level 3: "兰蔻在「精华液推荐」类 Topic 中排名从 #4 上升到 #1，你的品牌从 #2 降到 #4。
            排名反转发生在过去 14 天内。分析显示兰蔻同期新增了 8 个被 AI 引用的权威来源，
            而你的引用来源数量未变化 (维持 5 个)。
            行业 Top 品牌平均被引用来源数为 11 个。
            优化方向：补强品牌在高权威第三方来源中的内容存在感。"
```

**引用来源缺失**:
```
❌ Level 1: "AI 没有引用你的官方来源"
✅ Level 3: "在涉及你品牌的 47 条 AI 回答中，仅 12% 引用了品牌官方来源（官网/官方社媒），
            68% 引用了第三方评测，20% 引用了用户 UGC。而行业 Top 品牌的官方来源引用率
            平均为 35%。你的品牌叙事主要由第三方定义，品牌对 AI 回答的控制力弱。
            优化方向：提升品牌官方内容的结构化程度和可被 AI 抓取/引用的能力。"
```

**产品信息失真**:
```
❌ Level 1: "产品信息不准确"
✅ Level 3: "「小棕瓶精华」在 ChatGPT 中被描述的价格为 ¥520，实际零售价 ¥590，
            偏差 12%。产品核心成分被遗漏了「二裂酵母」，而这是品牌主推卖点。
            在 3 个引擎中，信息准确度得分: ChatGPT 0.61 / 豆包 0.78 / DeepSeek 0.72。
            行业 Top 品牌产品信息准确度平均为 0.85。
            优化方向：增强产品核心信息在 AI 可索引内容中的一致性和准确性。"
```

**产品被遗漏**:
```
❌ Level 1: "你的产品没被提到"
✅ Level 3: "在「500元以内精华液推荐」等 12 条高相关 Topic 中，你的旗舰产品「小棕瓶」
            提及率为 0%，而直接竞品兰蔻「小黑瓶」提及率为 83%。
            该 Topic 群的月搜索量预估较高，是核心转化场景。
            你的产品在「品牌名 + 产品」直接 Topic 中表现正常 (提及率 95%)，
            说明问题出在通用品类场景中 AI 未将你的产品纳入推荐池。
            优化方向：增强产品在品类通用场景中的内容关联性和可发现性。"
```

**行业新竞争者入场**:
```
❌ Level 1: "有新品牌出现"
✅ Level 3: "过去 30 天，品牌「观夏」在奢侈品香水类 Topic 中从未出现到提及率 34%，
            增速为行业最快。其 PANO Score 从 F(0) 升至 C(58)。
            「观夏」目前被 AI 推荐的语境集中在「国产高端香水」「中国风香水」。
            这可能分流你在「高端香水推荐」类 Topic 中 8%-15% 的 Share of Voice。
            建议关注：监测该品牌未来 2-4 周的增长趋势，评估是否构成直接竞争威胁。"
```

**LLM Prompt 约束规则** (用于 4.8.3 诊断生成):

```
生成诊断建议时，必须遵循以下规则:

1. 必须包含 Layer 1 + Layer 2 + Layer 3 三层内容 (详见 4.7.0-a 洞察 Stack 框架):
   Layer 1: 具体数据指标 + 环比变化 + 行业对标数据
   Layer 2: 因果链 (triggerMetrics → hypothesizedMechanism) + confidence level
   Layer 3: focus area + 3-5 个 anchor questions + ifUntreated 后果

2. 优化方向 (direction 字段) 使用「动词 + 抽象对象」格式:
   ✅ "提升品牌在权威来源中的内容覆盖密度"
   ✅ "增强产品核心信息在 AI 可索引内容中的一致性"
   ✅ "稀释负面内容源的权重，增强正面内容可引用性"
   ❌ "在小红书发布内容" (具体渠道)
   ❌ "联系 KOL 做评测" (具体动作)
   ❌ "优化官网 SEO" (具体手段)

3. 锚点问题 (anchorQuestions) 是事实探查型问题, 不是决策型/执行型 (详见 4.8.2a):
   ✅ "该主题 Top5 引文来源是谁?" (事实探查)
   ✅ "我方内容是否已被 AI 引擎索引?" (事实核查)
   ✅ "4 周内能否产出补位内容?" (能力评估)
   ❌ "要不要去小红书发文?" (具体渠道)
   ❌ "你们打算怎么解决?" (空泛)

4. industryBenchmark 必须结构化, 含 myValue / industryMedian / industryTop10Avg / topCompetitor / gapAnalysis
   不再允许自由文本形式的"标杆品牌特征"

5. causalChain 必须声明 confidenceLevel, 且支撑证据 ID 必须可追溯到 responseSamples 或指标 diff
   confidence=low 时, 必须在 alternativeHypotheses 列出 1-2 个备选

6. 必须给出 ifUntreated.scenarioDescription (若不干预预估后果)
   + predictedImpact (若干预预期收益)
   两者结合让用户看到"干预 vs 不干预"的 delta

7. readerHints 必须至少包含 'operator'; 涉及资源/预算/竞品策略级别添加 'manager'; 
   涉及品牌叙事/情感漂移/PR 风险添加 'branding'
   decisionPrompt 仅在 readerHints 含 'manager' 时必填

8. 严禁事项:
   - 不使用"建议""应该"等指令性词汇引出具体执行步骤
   - 不给出"应该去哪个平台/找谁/发什么类型内容"(给出执行方案)
   - 不做竞品攻击性建议 (如"打压竞品 X")
```

#### 4.8.6 边界 — 明确不做什么

- **不提供自动化优化动作**: 没有"一键优化"按钮
- **不保证优化效果**: 诊断是洞察，不是承诺
- **不做竞品攻击建议**: 只做自身优化方向，不建议打压竞品
- **不给具体执行渠道/动作**: 详见 4.8.5 颗粒度规范
- **不给 Layer 4 "Playbook"**: 锚点问题 (anchorQuestions) 是探查型问题, 不是 "先做 X 再做 Y" 的执行清单——那属于付费咨询的价值边界 (详见 4.7.0-a Layer 3 的"为什么 Layer 3 不给完整剧本")
- **不做跨品牌的内容策略建议**: 每条诊断聚焦单品牌/单产品自身数据, 不越界给"你们行业都应该..."之类的泛化建议
- **不做未来市场预测**: `ifUntreated.projectedValue` 是基于历史回归的保守外推, 不是"我们预测市场会如何", 要用保留余地的措辞

### 4.9 商业化: GEO 咨询服务转化漏斗

> 与产品功能平行的商业化设计——平台免费获客，诊断创造需求，咨询变现

#### 4.9.0 商业模型

```
免费平台 (获客引擎)          →  GEO 咨询服务 (收入来源)
┌─────────────────────┐    ┌──────────────────────────┐
│  全行业 GEO 数据     │    │  诊断驱动的咨询转化        │
│  零等待 Dashboard    │    │                          │
│  PANO Score          │ →  │  P0/P1 诊断 → CTA        │
│  优化诊断 (免费)     │    │  → 咨询线索 → 签约        │
│  API / MCP          │    │  → 交付 GEO 优化方案       │
└─────────────────────┘    └──────────────────────────┘
   MAU 5,000 目标             35 签约 / 300万 目标
```

#### 4.9.1 转化漏斗设计

```
Stage 1: 获客 (Acquisition)
  ├── SEO/内容: GEO 行业趋势报告、品牌 GEO 健康度公开排名
  ├── 联蔚集团客户直推: 现有客户关系 → 免费开通 GENPANO
  ├── 社交/专业传播: 品牌 GEO 体检报告 PDF 下载分享 (公开页 `/brand-report/:id`, 对标 Semrush Domain Overview PDF)
  ├── Agent 生态: MCP Server 被 Agent 集成 → 反向引流
  └── 目标: 注册用户
  
Stage 2: 激活 (Activation)
  ├── 选行业 → 立即看到品牌 GEO 数据 (Data-First 体验)
  ├── 设置"我的品牌" → 个性化 Dashboard
  ├── 首次看到 P0/P1 诊断 → "原来我的品牌有这些问题"
  └── 目标: MAU (月内登录 + 触发查询)

Stage 3: 转化线索 (Lead Generation)
  ├── 触发点: P0/P1 诊断详情页的 CTA
  │   └── "需要专业 GEO 优化方案？预约 30 分钟免费诊断咨询"
  ├── 线索表单: 品牌名 + 联系人 + 最关心的诊断问题
  ├── 自动附带: 该品牌的 PANO Score 报告 + 诊断摘要 (PDF)
  └── 目标: 合格线索 (MQL)

Stage 4: 销售转化 (Sales Conversion)
  ├── 30 分钟免费诊断咨询 (展示平台数据 + 问题严重性)
  ├── 输出: 定制 GEO 优化提案 (问题→方案→预期效果→报价)
  ├── 联蔚集团 BD 团队跟进
  └── 目标: 签约客户

Stage 5: 交付 & 续约
  ├── 按合同交付 GEO 优化方案
  ├── 客户在 GENPANO 平台持续监测优化效果
  ├── 定期复盘报告 (自动生成 + 人工解读)
  └── 续约/增购驱动
```

**漏斗预估** (2026 年底目标):
```
注册用户: ~15,000     (7.5个月累计)
MAU: 5,000           (KPI)
诊断查看/月: ~2,500   (MAU 的 50%)
CTA 点击/月: ~250     (诊断查看的 10%)
MQL/月: ~50           (CTA 的 20%)
签约/月: ~5           (MQL 的 10%)
7.5个月累计签约: ~37  → ≥35 (KPI)
平均客单价: ~8.6万    → 300万 (KPI)
```

#### 4.9.2 GEO 咨询服务包定义

**服务层级**:

| 层级 | 名称 | 内容 | 参考定价 | 目标客户 |
|------|------|------|---------|---------|
| L1 | GEO 诊断报告 | 深度诊断 + 优化方向 + 竞品分析报告 (一次性) | 2-3 万 | 中小品牌，试水需求 |
| L2 | GEO 优化方案 | L1 + 具体执行方案 + 3 个月跟踪 | 5-8 万 | 中型品牌，明确需求 |
| L3 | GEO 全案服务 | L2 + 执行落地 + 持续监测 + 月度复盘 | 10-20 万 | 大品牌，长期合作 |

**客单价分布预估** (达成 300 万):
```
L1 × 10 单 × 2.5万 = 25万
L2 × 15 单 × 6.5万 = 97.5万
L3 × 10 单 × 18万 = 180万
合计: ~302.5万 ≈ 300万目标
```

**交付流程** (非产品开发范围，但影响产品设计):
1. 诊断咨询 (免费30min): 基于 GENPANO 数据展示问题
2. 提案 (1周): 定制优化方案 + 报价
3. 签约: 双章合同
4. 执行 (持续): 团队执行优化动作
5. 效果追踪: 客户在 GENPANO 平台实时看优化效果 → **这是续约驱动力**

#### 4.9.3 产品侧支撑咨询转化的功能

**MVP 必须支撑** (已在当前计划中):
- PANO Score + 诊断卡片 + CTA (4.8 节)
- 平台数据 + 零等待体验 (4.0 节)
- 报告自动生成 (4.7 节)

**MVP 需新增的转化功能**:
- **线索收集表单**: 诊断详情页的 CTA → 嵌入线索表单 (品牌名+联系人+关心问题)
- **自动线索报告**: 用户提交线索后，自动生成该品牌的 PDF 诊断报告，发送给 BD 团队
- **线索管理 Admin**: 简单的线索列表 (新线索/已联系/已转化)，供 BD 团队使用

**Phase 2 增强**:
- 咨询客户专属 Dashboard (查看优化前后对比)
- 自动化月度复盘报告 (对比优化前后 PANO Score)
- 客户 ROI 计算器

#### 4.9.4 成本保护与异常消费告警 (2026-04-21 新增)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节告警阈值与暂停策略仅用于后端实现和 Admin 面板, 不向终端用户展示"火山引擎 API 花了多少钱"这类经营数据.

**问题背景**: Review 2026-04-21 §1 指出, GENPANO 成本 3 大来源 (火山引擎 LLM API / Ninja Clash 代理订阅 / Supabase 存储) 都有突增风险, 此前 PRD 未定义"什么情况暂停爬取避免烧钱", 也未定义阈值和告警链路. 对 Solo founder 财务安全是红线.

**4.9.4.1 成本来源与监控**

| 成本项 | 监控字段 | 采集频率 | 告警阈值 |
|---|---|---|---|
| LLM API (火山引擎) | `ai_responses.cost_usd` + `cost_cny` | 每条 Response 实时 | 单日 > 前 7 日中位数的 200% |
| 代理订阅 (Ninja Clash) | `proxy_subscription_usage` (Admin 每日 pull) | 每日 | 月配额用 > 80% |
| Supabase 存储 | Supabase dashboard API | 每小时 | 用量 > Plan 70% |
| Playwright 运行时长 | `query_executions.duration_ms` 聚合 | 每小时 | 日总耗时 > 48 核·时 |

**4.9.4.2 告警规则** (PagerDuty / Admin Slack):

- `cost_spike_daily` P1: 单日 LLM 成本 > 前 7 日中位数 × 2 → **暂停 Topic 扩容** (Planner 跳过 new Topic), 只跑存量 Topic, 发送告警
- `cost_spike_hourly` P2: 最近 1h 成本 > 前 24h 同时段 × 3 → 仅告警不暂停
- `proxy_quota_warning` P2: 代理节点月配额 > 80% → 切到备用订阅 + 告警
- `proxy_quota_critical` P1: > 95% → 暂停海外爬取, 仅保留国内引擎
- `storage_near_limit` P1: Supabase 用量 > 80% Plan → 触发旧数据归档任务 (Response 超过 90d 迁冷存储)
- `response_token_overflow` P3: 单 Response > 16K token → 截断 + 标记 `raw_truncated=true`, 不告警, 仅日志

**4.9.4.3 数据模型扩展** (对应 DATA_MODEL §2.5 ai_responses 新增字段):

```prisma
// 对 ai_responses 表扩展, 详见 docs/DATA_MODEL.md §2.5 的 2026-04-21 patch
cost_usd           Float?         // 本次 Response 的 LLM API 成本 (美元)
cost_cny           Float?         // 同上, 人民币 (火山引擎计价)
token_count        Json?          // { input: n, output: n, total: n }
latency_breakdown  Json?          // { queue_ms, adapter_ms, llm_ms, parse_ms }
trigger_source     String         // 'scheduled' | 'manual' | 'retry' | 'user_refresh'
```

`trigger_source` 必须非空, 用于成本归因 (定时任务产生的成本 vs 用户主动刷新产生的成本分开计量).

**4.9.4.4 暂停策略实现约束**:

- 暂停不是"杀 Worker 进程", 而是 Planner 停止 enqueue 新 Query, 已入队的 Query 继续跑完 (避免半截数据)
- 暂停状态写入 `admin_runtime_flags.cost_paused=true`, Admin 面板一键手动恢复
- Worker 每 60s 读一次 flag, 命中则进入 idle, 不关进程
- 告警只发 1 次 (1h 冷却), 避免轰炸

**4.9.4.5 Harness & 测试兜底** (TEST_STRATEGY §9.5):

- `ai-response-cost-field-required` harness: `ai_responses` 写入路径 (adapter AFTER hook) 必须设 `cost_usd`, 缺失 → PR block
- 单测 `cost-spike-alert.test.ts` 覆盖 "前 7 日中位数" 滑窗算法 + 告警去重冷却
- 集成测试 `proxy-quota-fallback.test.ts` 覆盖 80% / 95% 两档切换

### 4.10 国际化 (Internationalization)

> GENPANO 监测的是"AI 引擎中的品牌可见度"，但品牌天然是跨语言的——雅诗兰黛 = Estée Lauder = EL 是同一个实体，ChatGPT 用户用英文问、豆包用户用中文问。国际化不是"Phase 2 再说"的锦上添花，它是保证数据正确性的基础设施。

#### 4.10.0 设计原则

1. **China-first, global-ready**: MVP 以中文市场为主，但底层数据模型 (品牌名称、Prompt) 从 Day 1 就支持多语言，避免 Phase 2 推倒重来。
2. **数据层优先于表现层**: 品牌名称多语言匹配 (影响数据正确性) 优先级高于 UI 多语言 (影响可用性覆盖)。
3. **Engine-aware 语言策略**: 不同 AI 引擎的典型用户使用不同语言，Prompt 生成要贴近真实用户场景——中文引擎发中文 Prompt，海外引擎发英文 Prompt。
4. **用户语言 ≠ 监测语言**: 用户看 UI 的语言 (zh-CN / en-US) 和 Pipeline 发送给引擎的 Prompt 语言是两件独立的事，不要耦合。

#### 4.10.1 MVP 国际化范围

```
┌─────────────────────────────────────────────────────────────┐
│ 维度                    │ MVP   │ Phase 2+              │
├─────────────────────────────────────────────────────────────┤
│ 品牌名称多语言匹配         │ ✅    │ 扩展至更多语言 (日/韩) │
│ Prompt 多语言生成 (中/英)  │ ✅    │ 小语种 (日/韩/法/德)   │
│ UI 多语言 (中文/英文)     │ ✅    │ 更多语言              │
│ 邮件/报告多语言           │ ✅    │ 更多语言              │
│ 跨市场/地域监测            │ ❌    │ ✅ (Locale × Region)   │
│ 货币/时区格式化            │ ❌    │ ✅                    │
└─────────────────────────────────────────────────────────────┘
```

#### 4.10.2 品牌/产品名称多语言模型

**问题**: AI 引擎回答可能出现"雅诗兰黛"、"Estée Lauder"、"EL"、"estee lauder"（不带重音）、"雅诗兰黛公司"等多种形式，指同一个实体。如果只匹配 `Brand.name`，提及率会被严重低估，数据基础就错了。

**数据模型扩展** (对应 4.0.1a 节知识图谱):

```typescript
interface Brand {
  id: string;
  primaryName: string;         // 主名称，按品牌官方标注（如 "Estée Lauder"）
  nameZh: string;              // 中文名 ("雅诗兰黛")
  nameEn: string;              // 英文名 ("Estée Lauder")
  aliases: BrandAlias[];       // 多语言别名与变体
  // ... 其他字段同原定义
}

interface BrandAlias {
  value: string;               // 别名文本 ("EL", "estee lauder", "雅诗兰黛公司")
  language: 'zh' | 'en' | 'ja' | 'ko' | 'other';
  type: 'abbr' | 'variant' | 'legal' | 'informal';
  // abbr:缩写, variant:变体(如无重音), legal:法律实体名, informal:俗称
}
```

Product 同样扩展 (`nameZh` / `nameEn` / `aliases[]`)。

**别名来源**:
1. **LLM 初始化**: 冷启动阶段 Prompt 明确要求 "列出品牌的中英文名、常见缩写、无重音/符号变体"
2. **Response 挖掘**: 对比 Response 中的品牌指称与图谱已知名称，新变体自动入候选池，达到置信度阈值后入库
3. **用户共建**: 用户提交品牌时可补充别名字段

**匹配规则 (用于 Response 解析时的品牌提及识别)**:

```
对每条 Response，执行多语言名称匹配:
  1. 精确匹配: primaryName / nameZh / nameEn / aliases[].value 全集
  2. 归一化匹配: 去重音 (Estée → Estee)、去标点、小写化后匹配
  3. 歧义处理: 短别名 (如 "EL") 需配合上下文消歧，避免误判
  4. 命中后统一归一到 Brand.id，指标计算使用 id 维度
```

**消歧规则**:
- 短别名 (≤ 3 字符或 ≤ 2 个中文字) 必须配合上下文关键词才能判定为品牌提及。示例: "EL" 单独出现不算品牌提及，"EL 小棕瓶" / "Estée Lauder (EL)" 才算。
- 跨品牌冲突名 (如多个品牌都用 "Pure") 标注为 `ambiguous = true`，匹配时需要上下文加权。
- 消歧规则在 Brand 数据中独立配置，不硬编码。

#### 4.10.3 Pipeline 多语言: Prompt × Engine Language

**核心思路**: Topic 是语言中性的抽象监测点，Prompt 是面向特定引擎/语言的自然表达。一个 Topic 在不同引擎下可以有不同语言的 Prompt 实例。

```
Topic (语言中性)
  "小棕瓶 vs 小黑瓶 产品对比"
    │
    ├─→ Prompt (zh-CN, for 豆包 / DeepSeek / ChatGPT-zh)
    │     "小棕瓶和小黑瓶哪个更值得买？"
    │
    └─→ Prompt (en-US, for ChatGPT-en)
          "Estée Lauder ANR vs Lancôme Génifique: which is better?"
```

**引擎 → 语言默认策略** (MVP):

| 引擎 | 默认 Prompt 语言 | 可选语言 | 备注 |
|------|---------------|---------|------|
| 豆包 | zh-CN | - | 中文场景为主 |
| DeepSeek | zh-CN | en-US (可选) | 中文为主，用户可配置 |
| ChatGPT | en-US + zh-CN 双采 | - | 同一 Topic 生成两版 Prompt 各跑一次 |

**Prompt 生成逻辑变更** (对应 4.2.2 节):

```typescript
interface Prompt {
  id: string;
  topicId: string;
  intent: Intent;
  language: 'zh-CN' | 'en-US';        // 新增: Prompt 本体语言
  text: string;                        // 自然语言问句 (该 language 的表述)
  appliesToEngines: EngineId[];       // 该 Prompt 适用哪些引擎
}
```

LLM 生成 Prompt 时，同一 Topic × Intent 可能被调用两次（一次生成中文、一次生成英文），分别存储为独立的 Prompt 记录，拥有独立的 `appliesToEngines`。生成时必须使用正确的品牌名称对应语言（中文 Prompt 用 `nameZh`，英文 Prompt 用 `nameEn`）。

**Query Locale 语义** (对应 4.2.3 节):

原 Query 模型中 `locale` 字段表达不清。明确为两个字段：

```typescript
interface Query {
  // ...
  promptLanguage: 'zh-CN' | 'en-US';     // 来自 Prompt.language
  browserLocale: string;                 // 浏览器 Accept-Language / UI locale
  // (MVP 暂不区分 region，如 en-US vs en-GB。Phase 2 跨市场监测时扩展)
}
```

**Response 归属**: 每条 Response 记录自己的 `promptLanguage`，指标可按语言切分（例如"雅诗兰黛在英文 AI 回答中的提及率 vs 中文 AI 回答中的提及率"）。

##### 4.10.3.A Intent × Engine × Locale 决策矩阵 (2026-04-21 新增)

> **⚠️ 开发者约束 (不作为 UI 文案)**: 本节列出的矩阵仅用于 Planner 代码实现, 严禁以 i18n key / JSX 文本节点呈现给最终用户。

**问题背景**: Review 2026-04-21 §1 指出, Planner 在 Topic × Intent 生成 Prompt 时, 与 Engine Language 的交叉矩阵只有散落描述, 没有**一张决策表**让实施者一眼看到"在什么引擎、什么地区、什么意图下, 我该发中文还是英文"。

**实施 EngineId 标识符** (Decision #28.C1, 2026-04-22): 表中 "豆包" 对应 `'doubao'`, "ChatGPT" 对应 `'chatgpt'`, "DeepSeek-CN" 对应 `'deepseek-CN'` — `-CN` 后缀为 Phase 2 `'deepseek-overseas'` 命名空间预留, 实施代码 / Prisma CHECK / `intent-engine-locale-matrix.ts` 必须用全名。MVP 引擎宇宙锁 3 家, 其它 (Gemini / Perplexity / Kimi / Grok / 智谱 / Claude) 推到 Phase 2+ (规则 4)。

**决策矩阵** (Planner 生成 Prompt 时的强制查表):

| Intent | Engine | 目标市场 locale | promptLanguage | 该组合是否生成 | 备注 |
|---|---|---|---|---|---|
| informational | 豆包 | zh-CN | zh-CN | ✅ | 国内信息型问答主力 |
| informational | 豆包 | en-US | — | ❌ | 豆包不发英文 (引擎能力约束) |
| informational | DeepSeek-CN | zh-CN | zh-CN | ✅ | 同豆包 |
| informational | DeepSeek-CN | en-US | — | ❌ | 同豆包 |
| informational | ChatGPT | zh-CN | zh-CN | ✅ | 海外 ChatGPT 对中文 Prompt 有合理回答, 覆盖中文市场但从海外引擎视角 |
| informational | ChatGPT | en-US | en-US | ✅ | 海外 ChatGPT 英文信息型主力 |
| commercial | 豆包 | zh-CN | zh-CN | ✅ | |
| commercial | 豆包 | en-US | — | ❌ | |
| commercial | DeepSeek-CN | zh-CN | zh-CN | ✅ | |
| commercial | DeepSeek-CN | en-US | — | ❌ | |
| commercial | ChatGPT | zh-CN | zh-CN | ✅ | |
| commercial | ChatGPT | en-US | en-US | ✅ | |
| transactional | 豆包 | zh-CN | zh-CN | ✅ (含"购买/对比/值不值"型) | |
| transactional | 豆包 | en-US | — | ❌ | |
| transactional | DeepSeek-CN | zh-CN | zh-CN | ✅ | |
| transactional | DeepSeek-CN | en-US | — | ❌ | |
| transactional | ChatGPT | zh-CN | zh-CN | ✅ | |
| transactional | ChatGPT | en-US | en-US | ✅ | |
| navigational | 豆包 | zh-CN | zh-CN | ⚠️ 降频 30% | 导航型 prompt AI 回答信息量低, 仅补全 coverage, 不是主力 |
| navigational | 豆包 | en-US | — | ❌ | |
| navigational | DeepSeek-CN | zh-CN | zh-CN | ⚠️ 降频 30% | 同上 |
| navigational | ChatGPT | zh-CN | zh-CN | ⚠️ 降频 30% | |
| navigational | ChatGPT | en-US | en-US | ⚠️ 降频 30% | |

**应用规则** (Planner 代码必须实现):

1. 每个 Topic 生成 Prompt 前, **查表**决定 `(intent, engine, locale)` 三元组是否生成. ❌ 格的组合禁写入 platform_prompts
2. `navigational` ⚠️ 降频: 生成配额打 0.3 折, 节省爬取成本但不丢失覆盖
3. `Prompt.language = promptLanguage` (本表), `Prompt.appliesToEngines = [engines where 该组合为 ✅]`
4. 若未来新增引擎 (Gemini / Claude / Perplexity), 必须在本表 append 一行并同步 Planner 单测 (见 TEST_STRATEGY §9.2)
5. 成本分析 (§4.9): 本表共 12 个 ✅ 组合 + 4 个 ⚠️, 以 MVP 4 行业 × 100 Topic × 3-4 Intent ≈ 每日 Prompt 数 1200-2000 条, 分摊到 Profile 采样后 Query 数 3000-6000

**Harness 兜底**: Planner 单测 (`tests/unit/planner/intent-engine-matrix.test.ts`, Session 2) 必须把本表 23 行全覆盖, 任一行算法修改必须同步本 PRD 表格 + 单测断言.

#### 4.10.4 UI 国际化 (中文 / 英文)

**技术方案**:
- **框架**: `next-intl` (与 Next.js App Router 原生集成，SSR 友好)。不用 `react-i18next` 因其对 App Router 支持弱。
- **文案库结构**: `locales/{zh-CN,en-US}/{common,dashboard,onboarding,report,email}.json`
- **命名空间**: 按页面/域划分，避免单文件膨胀
- **默认语言**: zh-CN，英文用户从导航栏或设置页切换

**用户语言偏好**:
- `User.locale` 字段 (`zh-CN` / `en-US`)，注册时根据浏览器 `Accept-Language` 自动推断
- 用户可在设置页手动切换，立即生效（切换后整站重新渲染对应语言）
- 未登录访问 (Landing Page 等公开页) 根据浏览器 locale 自动选择

**文案编写规范**:
- 文案中不拼接字符串，使用 ICU MessageFormat 语法处理复数、占位符
- 数字/日期格式化通过 `date-fns/locale` + `Intl.NumberFormat` 处理
- 品牌名称在 UI 中按用户 locale 显示 (`locale === 'zh-CN'` 显示 `nameZh`，否则 `nameEn`)
- 专有名词（PANO Score、GEO、Topic 等）在两种语言中保持原文不翻译

**Phase 1 覆盖范围** (MVP):
- Landing Page / 注册登录流程 / Onboarding / Dashboard 主视图 / Project 设置 / 报告页面
- **不覆盖**: Admin 后台（团队内部使用，仅中文）、诊断建议正文（见下方"生成内容的语言"）

**生成内容的语言** (报告 / 诊断 / 邮件):

这类内容由 LLM 生成，不是静态文案。按以下规则处理:
- **周报/月报 PDF 内容**: 跟随 Project 所有者的 `User.locale` 语言生成
- **诊断建议正文**: 同上
- **事务性邮件** (E1-E5): 按用户 locale 选择邮件模板（`verify-email.zh-CN.tsx` / `verify-email.en-US.tsx`）
- **LLM 生成时**: Prompt 注入目标语言指令，例如 `"请用{{locale}}输出报告正文，保持专业术语的原文形式"`

#### 4.10.4a i18n 覆盖矩阵与强制规则 (2026-04-16 补)

> **背景**: Phase 1 覆盖范围 (§4.10.4) 只点到了"Dashboard 主视图 / Project 设置 / 报告页面"等域名，但在实施中出现三个反复被遗漏的盲区：**Alerts (告警标题/描述)**、**Settings (账号 + 项目设置页的字段级文案)**、**品牌名称显示 (BCG/Quadrant/列表等处直接读 brand.name)**。本节明确这三块的"必须覆盖清单 + 数据模型要求 + CI 强制规则"。

##### (A) Alerts / 诊断标题与描述 — 数据层双语

**问题**: 告警卡片和诊断结果的 `title` / `description` 长期以中文硬编码直接写进 mock / 种子数据 (例如"提及率周环比下降 8%"、"竞品 B 引用份额反超"). UI `t()` 只能翻译外壳文字 (筛选按钮、栏标题)，内容本体是数据，`locale=en-US` 的用户会看到中文数据。

**必须满足的数据模型变更**:

```typescript
interface Diagnostic {
  id: string;
  severity: 'P0' | 'P1' | 'P2' | 'P3';
  category: 'visibility' | 'sentiment' | 'competitor' | 'coverage' | ...;

  // 方案 A (首选, 适用于规则/模板化告警):
  titleKey: string;        // i18n key, e.g. 'alerts.titles.mention_drop_wow'
  titleParams: Record<string, string | number>;  // ICU 占位符
  descriptionKey: string;
  descriptionParams: Record<string, string | number>;

  // 方案 B (备选, 适用于 LLM 自由生成的叙述型告警):
  titleZh?: string;
  titleEn?: string;
  descriptionZh?: string;
  descriptionEn?: string;

  // 两种方案二选一, 同一条记录只允许一种
  renderMode: 'key' | 'bilingual';
}
```

**UI 层约束**:
- AlertBar / AlertList / AlertDrawer 在渲染时根据 `renderMode` 分支; `renderMode='key'` 走 `t(titleKey, titleParams)`, `renderMode='bilingual'` 按 `User.locale` 取 `titleZh` / `titleEn`
- 兜底: 如缺失目标 locale 字段, fallback 到 zh-CN 并记录数据完整度告警, 不得直接穿透显示原值
- **禁止**: 在 DIAGNOSTICS / ALERTS / mock.js 中写出单语中文硬编码 `title: '...'` / `description: '...'` 字段, 上述三类生产告警源数据必须满足方案 A 或 B

**LLM 生成告警的规则**:
- Planner / Analyzer 生成告警时, 如果是模板型 (如 "X 环比下降 Y%"), 生成 `titleKey` + `titleParams`
- 如果是叙述型 (如"本周 ChatGPT 首次出现品牌 A 被误归类为竞品"), 一次调用生成 `titleZh + titleEn + descriptionZh + descriptionEn` 四字段并存库, 不走"先存中文再翻译"
- MVP 接受个别 LLM 翻译不自然的情况 (与 §4.10.6 对齐)

##### (B) Settings / Project Settings — 字段级枚举清单

**问题**: SettingsPage (账号) 与 ProjectSettingsPage (项目配置) 中有大量字段标签、toggle 描述、确认弹窗文案、按钮文字, 直接写成中文字符串, UI i18n 漏覆盖的重灾区。

**必须在 messages.{zh-CN,en-US}.json 中存在的命名空间 (MVP 强制)**:

```
settings.*                              // 账号设置页
  ├── account.title / username / email / registered_date
  ├── api_keys.title / generate_new / copy / created_at / usage / delete / confirm_revoke
  ├── mcp.title / description
  └── notifications.title
       └── p0p1_alerts_{title,hint}
       └── weekly_report_{title,hint}
       └── competitor_alert_{title,hint}

project_settings.*                      // 项目设置页
  ├── page_title
  ├── section.{project_info,competitor_management,report_preferences,alert_settings,summary,danger_zone}
  ├── field.{industry,primary_brand,created_at,project_id,positioning,price_range,country_origin}
  ├── competitor.{current_label,add_button,picker_header,max_reached,remove_title}
  ├── report.{frequency_label,format_label,day_of_week,recipients}
  ├── alert.{p0p1_toggle,weekly_toggle,threshold_hint}
  ├── actions.{save,saved,cancel,reset}
  ├── summary.{last_updated,total_queries_today,mentions_this_week}
  └── delete.{button,confirm_title,confirm_hint,confirm_input_hint}

project_selector.*                      // 侧栏底部项目选择器
  ├── fallback_industry / fallback_brand / fallback_brand_row
  ├── primary_suffix / score_label
  └── create_new

user.*                                  // 用户 profile 兜底文案 (在接入真实 auth 前使用)
  ├── profile_default_name
  └── profile_default_email

brand_meta.*                            // 品牌元信息枚举值的展示名
  ├── positioning.{luxury,premium,mid_range,mass,value}
  ├── price_range.{ultra_high,high,mid,low}
  ├── primary_badge
  └── competitor_badge
```

**UI 层约束**:
- SettingsPage / ProjectSettingsPage / ProjectSelector 组件中所有文案必须通过 `t(...)` 读取, 不得出现裸中文字符串
- 日期 (注册时间, 项目创建时间, API key created_at) 必须走 `formatDate()`, 禁止 `toLocaleDateString('zh-CN', ...)` 硬编码 locale
- 品牌元信息 (positioning / priceRange) 的显示值要经过 `brand_meta.positioning.{value}` / `brand_meta.price_range.{value}` 查找, 查不到才 fallback 到原值

##### (C) 品牌名称显示 — formatBrand() 是唯一入口

**问题**: BrandDetailPage / BCG / CompetitorQuadrant / 面板 KPI 竞争视图 / 报告 PDF 等处, 有时直接读 `brand.name` / `brand.nameZh` / `payload.brand` 字符串, 绕过 `formatBrand()`, 导致 en-US 用户看到中文品牌名。mock 数据里也出现过 `brand: '雅诗兰黛', brandEn: 'Estée Lauder'` 这种拆分字段写法, 与 §4.10.2 的结构化 Brand 模型不一致。

**必须满足的规则**:
- **唯一显示入口**: 所有 UI 中展示品牌名称必须调用 `formatBrand(brand)`, 返回值按 `User.locale`:
  - `locale === 'zh-CN'` → `brand.nameZh ?? brand.primaryName ?? brand.nameEn`
  - `locale === 'en-US'` → `brand.nameEn ?? brand.primaryName ?? brand.nameZh`
- **禁止**: 组件中直接读 `brand.name` / `brand.nameZh` / `brand.nameEn` / `payload.brand` 字符串
- **mock / 种子 / 图表 payload**: 必须传结构化 `brand` 对象而不是拆字段, Chart 的 tooltip / legend formatter 里也调用 `formatBrand`
- **Product 同理**: 所有产品名走 `formatProduct(product)` (同构规则)
- **报告 PDF / 邮件模板**: 渲染品牌名时传 User.locale 到 `formatBrand`, 不硬编码

##### (D) CI / Code Review 强制规则

为防止上述三类盲区反复复发, 加入机械检测:

1. **CI grep 规则** (进 pre-commit 与 CI pipeline):
   - 扫描 `frontend/src/**/*.{jsx,js}` 匹配 CJK Unicode 范围 `\u4e00-\u9fff`
   - Allowlist: `frontend/src/i18n/messages.js`, `frontend/src/data/mock.js` 中明确标注 `nameZh` / `descriptionZh` 结构化字段的行
   - 命中任何不在 allowlist 的中文字符 → CI 失败, 要求修复或扩展 allowlist
2. **ESLint 规则 (自定义)**:
   - 禁止 JSX 中出现 `>(.*[\u4e00-\u9fff].*)<` 形式的文本节点
   - 禁止 `brand\.name(?!Zh|En)` 直接读取, 必须走 `formatBrand`
3. **Code review checklist** (新建 PR 时自动插入):
   - [ ] 新增 UI 文案全部经由 `t()` / `messages.json`
   - [ ] 新增数据模型字段含 `Zh`/`En` 或 `titleKey`/`descriptionKey` 分枝
   - [ ] 新增品牌名称展示点经由 `formatBrand()`
   - [ ] 日期格式化经由 `formatDate()`, 未使用 `toLocaleDateString` 硬编码 locale

##### (E) MVP 阶段例外与兜底

- **兜底原则**: 任何 i18n key 查找失败, fallback 到 zh-CN key, 再 fallback 到英文短语提示 "[i18n missing: {key}]" (而不是崩溃)
- **允许的中文硬编码**: 开发日志 / 注释 / commit message / CLAUDE.md 内部文档 / PRD 本身
- **MVP 明确不做**: 复杂复数规则 (超过"1 / >1 两档")、性别词变位 (MVP 两个语言都不需要), Phase 2 按需扩展

#### 4.10.5 国际化在各模块的影响清单

| 模块 | 国际化影响 |
|-----|----------|
| 4.0.1a 知识图谱 | Brand/Product 扩展 `nameZh`/`nameEn`/`aliases[]`，LLM 初始化 Prompt 调整 |
| 4.1.1 用户系统 | User 模型新增 `locale` 字段 (zh-CN / en-US) |
| 4.1.1a 事务性邮件 | 5 封邮件模板按 locale 分版本 (10 个模板文件) |
| 4.1.1b Onboarding | 按 User.locale 渲染，行业卡片 Top 3 品牌名按 locale 显示 |
| 4.2.2 Prompt 生成 | Prompt 带 `language` 字段，ChatGPT 中英双采 |
| 4.2.3 Query 组装 | 拆分 `promptLanguage` 和 `browserLocale` 两字段 |
| 4.4 分析引擎 | 品牌提及识别使用多语言匹配规则 (4.10.2)，指标可按语言维度切分 |
| 4.6 Dashboard | 使用 `next-intl`，品牌名按 `formatBrand()` 显示 (§4.10.4a.C)，竞品四象限/KPI 传结构化 brand 对象 |
| 4.6.1 面板告警条 / Alerts | AlertBar 使用 `t()`; DIAGNOSTIC 数据模型按 §4.10.4a.A 采用 `titleKey/params` 或 `titleZh/En` 双语 |
| 4.6.3 账号设置页 / Settings | `settings.{account,api_keys,mcp,notifications}.*` 全量落库; 日期走 `formatDate()` (§4.10.4a.B) |
| 4.6.4 项目设置页 / Project Settings | `project_settings.*` 全量落库; 品牌显示走 `formatBrand()`, positioning/priceRange 走 `brand_meta.*` (§4.10.4a.B) |
| 4.6.x 侧栏项目选择器 | `project_selector.*` 与 `user.*` 兜底命名空间; 切换语言即时生效 |
| 4.7 报告系统 | LLM 按 Project 所有者 locale 生成报告正文; PDF 模板中品牌名走 `formatBrand()` 并传入 locale |
| 4.8 诊断建议 | LLM 按 locale 生成诊断正文; 标题/描述按 §4.10.4a.A 存双语 (`titleKey` 或 `titleZh/En`) |
| CI / Lint | §4.10.4a.D 强制规则: CJK grep + `brand.name` 直读拦截 + PR checklist |

#### 4.10.6 边界与风险

**MVP 明确不做**:
- 跨市场/跨地域监测（同一品牌在不同国家 AI 答案差异）——Phase 2
- 日韩法德等小语种 Prompt / UI——Phase 2
- 货币/时区本地化——MVP 默认 CNY + Asia/Shanghai，Phase 2 扩展
- 用户自定义翻译/术语库——Phase 2

**已知风险**:
- **LLM 生成多语言 Prompt 的质量**: 英文 Prompt 由国内团队通过 LLM 生成，可能"中式英文"风格不自然。MVP 接受，Phase 2 引入 Native Review。
- **别名池膨胀**: Response 挖掘可能产出大量噪声别名，需要置信度阈值 + 定期清理机制。
- **短别名误匹配**: "EL" / "YSL" 等缩写在非品牌语境中误命中，消歧规则的覆盖率是关键监控项。

---

### 4.11 埋点 & 分析 (Analytics Instrumentation)

> **本章节地位**: PRD 里关于"用户行为观测"的**唯一真相源**. 所有章节 (§4.1-4.9) 提到的验收 KPI / 漏斗 / 转化率都以本章定义的事件为口径. 新增 feature 时, 必须先把新事件登记到 §4.11.4 清单再下代码, 不得在业务代码里随手调 `track()`.
>
> **⚠️ 开发者约束 (不作为 UI 文案)**: 本章所有事件名 / 属性名仅出现在前端 SDK 调用代码、后端日志、Mixpanel 控制台和本 PRD 中, **严禁**以 i18n key / JSX 文本节点 / PDF 文案形式呈现给最终用户. 参见 §4.6.0a.

#### 4.11.0 设计原则

1. **Mixpanel 为唯一后端**: MVP 阶段不自建 `events` 表, 不引第二家分析 SDK (PostHog / Amplitude 不用). Mixpanel 足以覆盖漏斗 / 留存 / 分群 / 公式化 KPI, Solo founder 够用.
2. **事件对齐业务里程碑, 不镜像 UI 鼠标动作**: 每一个事件都应能回答"这个行为发生了多少次?这个漏斗转化几成?", 而不是"用户在第 3 秒 hover 了按钮". UI 级热图 (hover / scroll) 由 Mixpanel autocapture 兜底, 不在本清单.
3. **区分"意图"和"结果"**: 凡是可能失败的动作 (导出 / 注册 / 提交表单), 拆成 `*_clicked` + `*_succeeded` + `*_failed` 三事件用于漏斗. 不会失败的纯查看类事件只保留单事件.
4. **未登录可追踪**: `anonymous_id` (等价于 §4.1.1c 的 `gpSessionId` cookie) 在 Mixpanel 里贯穿未登录期; 注册成功后调 `mixpanel.alias(user_id)`, 历史事件自动归并到用户档案. 这是 TTV 能测的前提.
5. **事件总数硬约束**: MVP 阶段 ≤ **50 个**事件 (当前 47 个, 留 3 个冗余). 超过阈值前必须先合并粒度相近的事件 (如不同筛选器合并为 `*_filter_changed` 带 `filter_type`). Phase 2 预留 #48/#49 给账户注销 (§4.1.1e F).

#### 4.11.1 分析基础设施

**SDK & 项目**:
- 前端: `mixpanel-browser`, 通过 `frontend/src/lib/analytics.ts` 统一封装 (不直接 import Mixpanel 到页面/组件; 封装内部负责 session / device / locale 公共属性注入)
- 后端: `mixpanel` (Node SDK) 仅用于 3 个服务端触发的事件 (`user_created` / `report_generated_succeeded` / `alert_email_sent`), 避免前端伪造
- Mixpanel 项目隔离: 3 个项目 — `genpano-dev`, `genpano-staging`, `genpano-prod`; 各自独立 token, 通过 `VITE_MIXPANEL_TOKEN` / `MIXPANEL_TOKEN_SERVER` 环境变量注入

**统一封装 API (`frontend/src/lib/analytics.ts`)**:
```ts
export function track(eventName: EventName, properties?: EventProps): void
export function identify(userId: string): void  // 登录后调用
export function alias(userId: string): void     // 注册成功后调用
export function resetSession(): void             // 登出后调用, 清 distinct_id
```

- `EventName` 是联合类型, 由本章 §4.11.4 清单生成的 enum (位于 `frontend/src/lib/analytics-events.ts`), 传非清单内字符串 TypeScript 直接拒编
- `EventProps` 按事件类型做 `Record<EventName, PropSchema>` 映射, 属性字段校验同样走类型 (漏传 / 拼错字段编译失败)
- 封装内部自动拼入公共属性 (§4.11.3), 业务方不手动传

**环境隔离 & 去重**:
- `track()` 在 `NODE_ENV=test` 下 no-op, 防污染线上数据
- 每个事件带 `$insert_id = {event_name}|{session_id}|{fingerprint}`, Mixpanel 侧基于 insert_id 去重 (防重试 / 双击导致双上报)

#### 4.11.2 事件命名规范

- 格式: `{domain}_{object}_{verb_past}` snake_case
- `domain` ∈ `auth / onboarding / industry / brand / product / topic / dashboard / report / diagnostic / alert / project / export / consult / system`
- `verb_past` ∈ `viewed / clicked / submitted / succeeded / failed / shown / dismissed / changed / expanded`
- 禁止缩写 (`btn` / `usr` / `idx` 全展开)
- 禁止 UI 元素名做 object (`nav_item_clicked` ❌); 用业务对象 (`industry_card_clicked` ✅)
- 事件名一经发布**永远** append-only: 要改语义, 只能新建事件 + 在旧事件上标 `deprecated_at`. 删除 = breaking change, 会让 Mixpanel 历史看板全部断档.
- **例外条款 — system 域事件**: `session_first_event` / `first_binding_action` / `error_shown` 这类元事件不强制 verb_past 后缀; 但 object 部分仍必须是业务名词, 不得用 UI 元素名. 新增 system 域事件需在本 §4.11 清单里明确登记.

#### 4.11.3 公共属性字典 (SDK 自动注入, 业务不手动传)

| 分组 | 字段 | 类型 | 说明 |
|------|------|------|------|
| **User** | `user_id` | string \| null | 登录后为 `User.id`, 未登录为 null |
| | `is_authenticated` | boolean | 同 `user_id != null` |
| | `locale` | string | `zh-CN` / `en-US` |
| | `user_role` | string | `free` / `paid` / `admin` (MVP 只有 free) |
| **Session** | `session_id` | string | `gpSessionId` cookie (24h 滑窗) |
| | `anonymous_id` | string | 首次访问生成, 注册时 alias 到 `user_id` |
| | `utm_source` | string | 首次触达时 capture, 写入 cookie (30 天) |
| | `referrer` | string | document.referrer |
| **Device** | `device_type` | string | `mobile` / `desktop` / `tablet` |
| | `os` | string | `mac` / `windows` / `ios` / `android` / `linux` |
| | `browser` | string | `chrome` / `safari` / `firefox` / ... |
| **Page** | `page_path` | string | `window.location.pathname` (不含 query) |
| | `page_title` | string | `<title>` 当前值 |
| | `from_page` | string | 上一页 page_path (SPA 路由变化时更新) |

**不入公共属性的字段**: IP (Mixpanel 自动推断, 不冗余) / 精确地理位置 (隐私考量, 仅国家级由 Mixpanel 内部推断) / 邮箱 / 手机号 (PII 红线, 见 §4.11.5).

#### 4.11.4 MVP 事件全量清单 (47 个)

**S1 Auth (§4.1)** — 5 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 1 | `session_first_event` | 浏览器首次挂 gpSessionId cookie 时 | (仅公共属性) |
| 2 | `auth_prompt_shown` | `<AuthPromptModal>` mount 时 | `hook_key`, `return_to`, `action` |
| 3 | `auth_login_clicked` | 用户点击登录/注册主 CTA | `auth_mode` (login/register/forgot) |
| 4 | `user_created` | **后端**注册成功 API 内部触发 | `auth_method` (email/google/github), `signup_source` (modal/auth_page/oauth_callback) |
| 5 | `password_reset_requested` | 用户提交找回密码表单 | (仅公共属性, **不含邮箱值**) |

**S2 Onboarding / Industry (§4.1.1b, §4.4)** — 3 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 6 | `industry_card_clicked` | Landing 首屏 / 注册后引导卡点击行业卡 | `industry_id`, `card_position` (0..3), `card_source` (landing/onboarding_fallback) |
| 7 | `industry_view_loaded` | `/industries/:id` 首屏可用 | `industry_id`, `view_mode` (graph/list) |
| 8 | `industry_filter_changed` | 用户修改品类/排序/搜索 | `filter_type` (category/sort/search), `filter_value`, `result_count` |

**S3 Brand Detail (§4.6.1b)** — 4 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 9 | `brand_detail_viewed` | `/brands/:id` 首屏可用 | `brand_id`, `is_monitored` (true/false), `user_status` (authenticated/guest), `industry_id` |
| 10 | `brand_tab_clicked` | 切换子 Tab (概览/诊断/产品/引擎对比) | `brand_id`, `tab_name` |
| 11 | `brand_watch_clicked` | 点击 "+ 加入竞品监控" | `brand_id`, `direction` (add/remove), `project_id` (null 表未登录) |
| 12 | `brand_watch_succeeded` | 加入/移出成功 (**T1 first_binding_action**) | `brand_id`, `direction`, `project_id`, `is_cross_industry` |

**S4 Product Detail (§4.6.1d)** — 2 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 13 | `product_detail_viewed` | `/brands/:brandId/products/:productId` 首屏 | `product_id`, `brand_id`, `from_page` |
| 14 | `product_relation_viewed` | 关系视图加载完毕 | `product_id`, `relation_count_by_type` (JSON) |

**S5 Topics Drilldown (§4.2.5)** — 3 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 15 | `topics_page_loaded` | `/topics` 首屏可用 | `project_id`, `filter_dimension` (brand/product/category) |
| 16 | `topic_query_expanded` | 用户在 Pipeline 下钻展开 Query | `topic_id`, `prompt_id`, `query_id`, `engine_code` |
| 17 | `response_viewed` | 用户查看 Response 原文 | `response_id`, `engine_code`, `snippet_length` |

**S6 Dashboard 面板 (§4.6.1a)** — 6 个 (含 #44, #45 零 Project Empty State 追加, 见 §4.1.1d)

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 18 | `dashboard_loaded` | `/dashboard` 首屏可用 (有 Project) | `project_id`, `range_days`, `engines` (数组), `profile_group_id` |
| 19 | `dashboard_filter_changed` | 顶栏主筛/扩展筛任意变更 | `filter_type` (time/engine/profile/dimension/intent), `old_value`, `new_value` |
| 20 | `dashboard_kpi_card_clicked` | 点击 5 KPI 卡中任一 | `kpi_name` (mention/sov/sentiment/citation/rank), `target_brand_id` |
| 21 | `dashboard_competitor_clicked` | 竞品四象限气泡 / SoV 饼扇区点击 | `source_block` (quadrant/sov_pie), `target_brand_id` |
| 44 | `dashboard_empty_state_shown` | 已登录零 Project 用户落 `/dashboard` / 侧栏 ProjectSelector 渲染 Empty 态 (§4.1.1d E1/E2) | `surface` (dashboard_empty / sidebar_empty), `has_explored_industry` (bool), `default_industry_id` (nullable) |
| 45 | `dashboard_empty_state_cta_clicked` | E1 / E2 主/次 CTA 点击 | `surface` (dashboard_empty / sidebar_empty), `cta` (primary / secondary) |

**S7 CSV 导出 (§4.6.4)** — 4 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 22 | `export_csv_clicked` | 用户点击任意 CSV 导出按钮 | `export_type` (8 种), `page_path`, `estimated_rows` |
| 23 | `export_csv_confirmed` | `row_count > 1000` 二次确认 | `export_type`, `row_count` |
| 24 | `export_csv_succeeded` | CSV 下载完成 (**T2 first_binding_action**) | `export_type`, `row_count`, `file_size_kb`, `duration_ms` |
| 25 | `export_csv_failed` | 导出失败 (服务端 5xx / 超 10k 行拒绝) | `export_type`, `error_code`, `row_count` |

**S8 报告 PDF (§4.7)** — 5 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 26 | `report_generation_requested` | 用户点"生成" / Cron 触发周报月报 | `report_type` (weekly/monthly/on_demand/lead_diagnostic), `triggered_by` (user/cron), `project_id` |
| 27 | `report_generation_succeeded` | **后端**生成完毕 | `report_id`, `report_type`, `duration_ms`, `section_count` |
| 28 | `report_pdf_viewed` | 用户打开报告在线预览 | `report_id`, `viewer_type` (owner/guest), `locale` |
| 29 | `report_pdf_downloaded` | PDF 文件下载 | `report_id`, `locale` |
| 30 | `report_shared` | 复制/分享报告链接 | `report_id`, `share_method` (copy_link/email/qr) |

**S9 诊断 & 告警 (§4.8)** — 5 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 31 | `diagnostic_card_shown` | 诊断卡片进入视口 (Intersection Observer) | `diagnostic_id`, `severity` (P0/P1/P2/P3), `category`, `page_path` |
| 32 | `diagnostic_detail_clicked` | 用户点诊断卡进详情 | `diagnostic_id`, `severity`, `from_page` |
| 33 | `diagnostic_layer_expanded` | 用户展开 L1/L2/L3 洞察层 | `diagnostic_id`, `layer` (l1/l2/l3) |
| 34 | `alert_subscribed` | 用户订阅告警 (**T5 first_binding_action**) | `brand_id`, `project_id`, `alert_type` (p0p1/weekly) |
| 35 | `alert_email_sent` | **后端**告警邮件发出 | `alert_type`, `project_id`, `severity`, `brand_id` |

**S10 咨询转化 (§4.9)** — 5 个

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 36 | `consult_cta_shown` | 咨询 CTA 区块进入视口 | `source_diagnostic_id`, `severity`, `cta_version` |
| 37 | `consult_cta_clicked` | 用户点"预约诊断咨询" | `source_diagnostic_id`, `severity`, `from_page` |
| 38 | `consult_form_opened` | 咨询线索表单弹起 | `source_diagnostic_id` |
| 39 | `consult_form_submitted` | 用户提交表单 | `source_diagnostic_id`, `field_count`, `has_company_field` (bool, **不含公司名值**) |
| 40 | `consult_form_failed` | 表单提交失败 | `error_code` |

**S11 系统/元事件 & Project 生命周期** — 5 个 (含 #46 项目入口分布追加, 见 §4.1.1d; #47 登出追加, 见 §4.1.1e)

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 41 | `first_binding_action` | 用户首次完成 #12 / #24 / #34 / #42 任一 (session 内只发一次) | `binding_action` (watch/export_csv/subscribe_alerts/create_project), `minutes_since_first_event` |
| 42 | `project_created` | **后端** Project 创建成功 API 返回 (**T4 / T9 first_binding_action**) | `project_id`, `primary_brand_id`, `competitor_count`, `industry_id`, `entry_source` (同 #46 枚举, 便于归因) |
| 43 | `error_shown` | 用户可见的错误 toast/页面 | `error_code`, `error_message_key`, `page_path` |
| 46 | `project_creation_entry_clicked` | 任一"创建监测项目" / "+ 创建第一个项目" 入口被点击 (入口分布诊断事件, §4.1.1d D 段) | `entry_source` ∈ `empty_state_dashboard` / `empty_state_sidebar` / `landing_nav_quick` / `industry_row_cta` / `brand_detail_cta` / `gated_banner`, `is_authenticated` (bool) |
| 47 | `user_logged_out` | 用户点击 UserMenu L1 / SettingsPage L2 登出, 或 silent refresh 失败后自动登出 (§4.1.1e C/E) | `trigger` ∈ `manual` / `session_expired` / `multi_device_kick`, `session_duration_sec` (int), `had_project` (bool), `locale` (`zh-CN` / `en-US`). **⚠️ 必须在 `mixpanel.reset()` 之前上报**, 否则 distinct_id 已清导致事件失归属 |

**S12 Citation 行动面 (§4.2.7)** — 7 个 (2026-04-17 新增)

| # | event_name | 触发时机 | 关键属性 |
|---|-----------|---------|---------|
| 50 | `attribution_mismatch_viewed` | 用户展开 `citation_attribution_mismatch` 诊断卡详情 (§4.2.7.A) | `diagnostic_id`, `brand_id`, `possible_causes` (数组, 三选一) |
| 51 | `content_gap_tab_viewed` | `/brands/:id?tab=content-gap` 首屏可用 (§4.2.7.B) | `brand_id`, `gap_topic_count`, `user_status` (authenticated/guest) |
| 52 | `pr_targets_viewed` | PR 候选列表进入视口 (§4.2.7.C 区块 ④) | `brand_id`, `visible_row_count` (≤50) |
| 53 | `pr_targets_csv_exported` | 用户导出 `pr_targets` CSV (§4.6.4 CSV #9) 成功 | `brand_id`, `row_count`, `tier_filter` (JSON, 可空) |
| 54 | `simulator_opened` | `/brands/:id/simulator` 首屏可用 (§4.2.7.E) | `brand_id`, `from_page` (brand_detail_overview / brand_detail_diagnostics / deeplink) |
| 55 | `simulator_run` | 用户滑动任一 Tier delta 或点"计算" (debounced 500ms) | `brand_id`, `delta_tier1`, `delta_tier2`, `delta_tier3`, `base_pano_a`, `simulated_pano_a`, `delta_pano_a` |
| 56 | `simulator_cta_click_consulting` | 从 simulator 输出面板点"预约咨询" (连上 §4.9 漏斗) | `brand_id`, `simulated_pano_a`, `delta_pano_a` (作为线索富化) |

**事件总数更新**: MVP 事件清单从 47 扩为 **54** (47 + #50-#56 = 54, #48/#49 仍为 Phase 2 预留, 未计入 MVP 总数). §4.11.4 小节标题的 "(47 个)" 口径含义为 "MVP 启动时 Phase 1 已上线事件计数", 新增 7 个 Citation 行动面事件随 §4.2.7 MVP/v1.1/Phase 2 分批实施一同上线.

**不纳入 MVP 的事件 (Phase 2)**:
- `mcp_api_call_made` / `api_key_created` — MCP 消费面, Phase 2 开放 API Key 时再埋
- `project_settings_changed` — 项目偏好修改, MVP 只关注创建 / 删除
- 各类 hover / scroll / copy 等 UI 级行为 — Mixpanel autocapture 兜底, 不在清单
- `onboarding_skipped` — 路径 C 行业引导卡跳过率, Phase 2 优化引导时再加
- **#48 `user_deletion_requested` / #49 `user_deleted`** — 账户注销 (PIPL 删除权), 事件号已预留, 待 Phase 2 Settings Danger Zone 实施 Session 完工后落地 (§4.1.1e F)
- **#54/#55/#56 Simulator 相关** 随 §4.2.7.E v1.1 版本上线; MVP 仅 #50-#53 (归因诊断/内容缺口/PR 候选)

##### S13 Dashboard / Drill-down / Auth Gate 事件 