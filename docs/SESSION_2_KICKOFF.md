# Session 2 Kickoff — 智能监测 Pipeline (Topic → Prompt → Query)

> 日期: 2026-04-22
> 真相源: `docs/CLAUDE_CODE_SESSIONS.md` Session 2 (line 1376-1527) + `docs/PRD.md` §4.2 (line 1740-2290) + §4.10.3 / §4.10.3.A
> 前置满足: Session 0-rev ✅ · Session 1 ✅ (CLAUDE.md #22) · Session 1.5 ✅ (CLAUDE.md #23) · Session A0 ✅ (CLAUDE.md #24/#25)
> 当前只替换 `backend/src/platform/planner/topic-pool.ts` 的 stub — 全 codebase 没有其他调用者 (grep 命中仅此文件自身)
> 跨 Session 反向同步 (§0 规则 8): Session 2 完工时必须 grep `generatePlatformTopics` / `platform_topics` / `platform_prompts` / `profile_groups` 的所有文档引用, 清单报告给 Frank

---

## 决策背景

**为什么先上 Session 2 而不是 Session 1.2**:
1. Session 1.2 (Adapter Hardening: Camoufox + golden HAR) 当前**不阻塞任何下游** — Session 1 的 "纯逻辑 + HAR stub" 足够支撑 Session 2 Planner 的单测
2. Session 2 完成后, Session 3 (分析引擎 + API + MCP + Citation 全链路 §4.2.6/§4.2.7) 立即可开工, App Track 核心闭环向前推进
3. Session 1.2 可以在 Session 3 前的空档插入 (SESSION_PROGRESS.md 流程图已这样标注)
4. Session 2 的 **Topic → Prompt → Query 三层规划**是 GENPANO 的**核心差异化**落地 (PRD §4.2), 优先级高于 Playwright 加固

**当前 stub 状态**: `backend/src/platform/planner/topic-pool.ts` 只导出接口 + 抛 `TopicPoolNotImplementedError`。Session 1.5 的 `scripts/seed-platform-data.ts` 中步骤 4-5 (Topic / Prompt 生成) 被显式跳过, Session 2 需要让该脚本端到端跑通到入库 Topic + Prompt + Query。

---

## 给 CC 的 Prompt (复制下面整个代码块给 CC)

```
继续 GENPANO 项目开发。开始 App Session 2: 智能监测 Pipeline (Topic → Prompt → Query 三层 Planner)。

本 Session 依赖: Session 0-rev ✅ · Session 1 ✅ (CLAUDE.md #22) · Session 1.5 ✅ (CLAUDE.md #23) 都已完成。
下一 Session (Session 3) 依赖本 Session 产出的 platform_topics / platform_prompts / platform_queries 表数据 + profile_groups seed。

---

## 1. 真相源索引 (§0 规则 5, 实施前必读, 有歧义以下列为准)

- **四层 Pipeline 架构** → `docs/PRD.md` §4.2.0 (line 1744-1780, 2026-04-16 术语定义)
- **Topic 生成 (Planner Bottom-Up)** → `docs/PRD.md` §4.2.1 (line 1781-1852)
- **Prompt 生成 (Topic × Intent)** → `docs/PRD.md` §4.2.2 (line 1853-1916)
- **Query 组装 (Prompt × Profile)** → `docs/PRD.md` §4.2.3 (line 1917-1975)
- **ProfileGroup 定义 + 6-10 个 MVP 预置组** → `docs/PRD.md` §4.2.3a (line 1976-2046)
- **Intent × Engine × Locale 决策矩阵 (23 行, Planner 强制查表)** → `docs/PRD.md` §4.10.3.A (line 6918-6961, 2026-04-21 固化版)
- **Pipeline 多语言 (zh-CN / en-US, 品牌 nameZh/nameEn 不混用)** → `docs/PRD.md` §4.10.3 (line 6860-6917)
- **Topic 管理 & 下钻 (Admin / App 共享)** → `docs/PRD.md` §4.2.5 (line 2093-2290)
- **Session 2 完整任务 + 验收** → `docs/CLAUDE_CODE_SESSIONS.md` Session 2 (line 1376-1527)
- **Session 1 产出接口** → `docs/CLAUDE.md` #22 (Session 1 交付边界, 特别是 profile-sampler / FNV-1a hash / 8 个 browser profile preset)
- **Session 1.5 产出接口 + stub** → `docs/CLAUDE.md` #23 · `backend/src/platform/planner/topic-pool.ts` (当前抛 TopicPoolNotImplementedError) · `backend/src/platform/db/ports.ts` (KgRepositories 接口) · `backend/src/platform/scheduler/platform-scheduler.ts` (`assignTiers` + `buildEnqueuePlan` 纯函数)
- **2026-04-21 Review 修复闭环 (38 Harness + 7 数据契约 + 5 self-seeded fixture 必须保持绿)** → `docs/CLAUDE.md` #21 + `docs/REVIEW_2026_04_21.md` + `docs/TEST_STRATEGY.md` §9-§13
- **Session Prompt 编写公约 (8 条规则, 本 Session 必遵守)** → `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` §0 (line 55-177, 2026-04-21 规则 8 固化版)
- **CLAUDE.md 决策链** #1-#25 (#16 提及率 non-brand 口径 · #20 V2 分析页数据口径 · #21 测试地基 · #22 Session 1 · #23 Session 1.5)

---

## 2. Pre-Flight Grep 契约 (§0 规则 2, 动代码前必跑)

把下列 grep 的原始输出报告给 Frank, 任何非预期命中停下等 Frank 决策, 不允许自行合并绕过:

```bash
cd /c/Users/frank/GENPANO

# G1 · 检查 topic-pool stub 下游调用者 (应只剩自身文件)
grep -rn "generatePlatformTopics\|TopicPoolNotImplementedError\|topic-pool" backend/src backend/scripts backend/tests

# G2 · 检查 platform_topics / platform_prompts / platform_queries / profile_groups 表是否已在 Prisma schema 或迁移中存在
grep -n "platform_topics\|platform_prompts\|platform_queries\|profile_groups\|ProfileGroup" backend/prisma/schema.prisma
ls backend/prisma/migrations/ 2>/dev/null

# G3 · 检查 Intent × Engine × Locale 矩阵 (PRD §4.10.3.A) 是否在代码里已有 seed / 常量 (应为 0 命中, 本 Session 是首次落地)
grep -rn "navigational\|informational.*commercial.*transactional" backend/src backend/tests 2>/dev/null | grep -v node_modules | head -20

# G4 · 检查 seed-platform-data.ts 中 Topic/Prompt 步骤 4-5 当前是否确实是 skip / stub
grep -n "TopicPool\|topic\|Prompt" backend/scripts/seed-platform-data.ts

# G5 · 检查 docs 下所有引用 platform/topic-pool 的位置 (规则 8 下游反向同步清单)
grep -rn "platform/topic-pool\|platform_topics\|platform_prompts\|generatePlatformTopics" docs/

# G6 · 确认 Session 1 产出的 profile-sampler (FNV-1a + 8 preset) 可复用
ls backend/src/engines/profile-sampler.ts backend/config/browser-profiles.ts 2>/dev/null
grep -n "sampleProfileForSeed\|listSegmentGroups\|SEGMENT_GROUPS" backend/src/engines/profile-sampler.ts 2>/dev/null | head
```

Frank 看到 G1-G6 结果后决策:
- **G1 预期**: 仅 `backend/src/platform/planner/topic-pool.ts` 自身文件内部有命中, 其他文件 0 命中 → 安全重写 stub
- **G2 预期**: Prisma schema 与 migrations 目录里当前**无** `platform_topics` / `platform_prompts` / `platform_queries` / `profile_groups` 定义 (本 Session 首次新增) → 本 Session 要新增 Prisma migration
- **G3 预期**: 0 命中 (Intent 矩阵首次落地)
- **G4 预期**: `seed-platform-data.ts` 中 Topic/Prompt 入口存在但抛 `TopicPoolNotImplementedError` 或被注释跳过 → 本 Session 接通
- **G5 预期**: 仅 CLAUDE_CODE_SESSIONS.md 4 处描述性引用 + CLAUDE.md 决策段 + 本 SESSION_2_KICKOFF.md, 无未同步的 inline schema
- **G6 预期**: 文件存在且导出这些符号; 若不存在停下报告 Frank

---

## 3. 硬约束 (违反 = 本 Session 失败, 来自 CLAUDE.md #21)

下列 38 条 Harness + 7 条 Data Contract + 5 条 self-seeded fixture 必须保持全绿, 本 Session 新增代码**不得**让它们中任何一条变红:

```bash
cd backend

# L1 · Harness 全量 (38 rules Group A-F)
node scripts/ci-check.mjs

# L1 · Harness self-test (5 expected positives)
node scripts/ci-harness-selftest.mjs

# 数据契约 (7 rules, 关系型约束)
node scripts/check-data-contracts.mjs

# L2 · Vitest 全量 (80% 分支覆盖阈值)
npm run test:coverage
```

本 Session **新增** 4 条 Planner 专属 Harness 规则 (Group G, 详见任务 §4 末尾), 并为其中 2 条落 self-seeded 违规 fixture (selftest EXPECTED_POSITIVES 从 8 扩到 10)。

---

## 4. 任务清单 (按序执行, 每项结束前自检)

> 实施策略: 延续 Session 1 / 1.5 的**"端口/适配器 + 可注入 transport + 纯逻辑单测"** 范式。所有编排用 `KgRepositories` 接口 + `LlmTransport` 函数类型注入, 单测走 `InMemoryKgRepositories` + `vi.fn()` 桩化, 零网络零 DB 零 Playwright。

### 任务 1 · Prisma schema 扩展 (新增 4 张表)

**真相源**: PRD §4.2.1 / §4.2.2 / §4.2.3 / §4.2.3a + DATA_MODEL.md (若 DATA_MODEL.md 已有 `platform_topics` / `platform_prompts` / `platform_queries` / `profile_groups` 定义则完全按 DATA_MODEL.md 走; 否则按 PRD 语义新增)。

**禁止**在本 Session Prompt 内重写完整 Prisma model 字段清单 (§0 规则 1)。本 Prompt 仅**列增量**:

- `PlatformTopic` — 承载 §4.2.1 Topic (id / industryId / topicKey unique / dimension CHECK IN ('品类','品牌','产品') / sourceEntityType / sourceEntityId / titleZh / titleEn / score / createdAt)
- `PlatformPrompt` — 承载 §4.2.2 Prompt (id / topicId FK / intent CHECK IN ('informational','commercial','transactional','navigational') / language CHECK IN ('zh-CN','en-US') / appliesToEngines String[] / promptText / isFollowUp Bool / parentPromptId? / createdAt)
- `PlatformQuery` — 承载 §4.2.3 Query (id / promptId FK / profileHash String / profileGroupIds String[] / personaPrefix Text / browserLocale / promptLanguage / status CHECK IN ('pending','queued','running','success','failed') / createdAt)
- `ProfileGroup` — 承载 §4.2.3a (id / nameZh / nameEn / description / filterRulesJson Json / industryScope String[]? / isDefault Bool / createdAt)
- 索引: `(industryId, dimension)` on PlatformTopic · `(topicId, intent, language)` on PlatformPrompt · `(promptId, status)` on PlatformQuery · `GIN` on profileGroupIds for PlatformQuery

**PRD 语义对齐检查** — 若实施过程中发现 PRD §4.2.x 与 DATA_MODEL.md 对同一字段给出不一致定义, 立即停下报告 Frank (§0 规则 4 真相源双向同步)。

**交付**: `backend/prisma/schema.prisma` 追加 4 个 model + 必要 migration SQL (CHECK 约束走裸 SQL, Prisma DSL 不支持)。

### 任务 2 · Topic Planner (Bottom-Up) — `backend/src/platform/planner/topic-planner.ts`

**真相源**: PRD §4.2.1 (Step 1-5, 严格 Bottom-Up 顺序 + 品类纯净度约束)。

- **输入**: `{ industryId, kgRepos, llmTransport, brandIds?, productIds? }` (允许筛选子集, 默认全行业)
- **步骤 (顺序不可变)**:
  1. 产品级 Topic (最先, 从 KG product 出发)
  2. 品牌级 Topic (去产品名保留品牌)
  3. 行业级 Topic (去品牌名保留品类 + 竞品发现类) — 此处品类 dimension Topic 比例必须 ≥40% (PRD §4.2.1 Step 5 + CLAUDE.md #16)
  4. 变体扩展 (口语化/场景化/地域化/长尾化)
  5. 去重 + 质量评分 (`score: number` 0-1, 真实度评估过滤 SEO 堆砌)
- **品类 Topic 纯净度强约束** (PRD §4.2.1 Step 5 + CLAUDE.md #16):
  - `dimension='品类'` 的 Topic 标题和对应 Prompt 文本**禁止**包含任何 KG Brand 的 `nameZh` / `nameEn` / `aliases[]`
  - 实现一个纯函数 `validateCategoryTopicPurity(topic, brands)` 返回 `{ ok: boolean, violations: string[] }`, Planner 内调用后命中违规直接丢弃该 Topic
- **LLM 调用预算**: 每行业 ≤ 80 LLM calls 硬上限 (Session 1.5 是 50, Topic 生成需要更多 few-shot; 超过抛 `LlmCallBudgetExceededError` 复用 Session 1.5 的 `backend/src/platform/llm/client.ts`)
- **Prompt 模板**: `backend/src/platform/planner/prompts.ts` 中英双语, few-shot examples 至少每层级 2 例
- **输出**: `DiscoveredTopic[]` — 字段形状按 `topic-pool.ts` 现有 interface (不改), 删除 stub body 替换为真实实现

**交付**: `topic-planner.ts` + `prompts.ts`; 更新 `topic-pool.ts` 让 `generatePlatformTopics` 调用 `topic-planner` 并 `persistTopics(repos)` 落库。

### 任务 3 · Prompt Generator (Topic × Intent × Locale) — `backend/src/platform/planner/prompt-generator.ts`

**真相源**: PRD §4.2.2 + §4.10.3 + §4.10.3.A (Intent × Engine × Locale 决策矩阵 23 行)。

- **强制查表**: 每个 Topic × Intent × Locale × Engine 四元组必须查 §4.10.3.A 决策矩阵, ❌ 格的组合禁止生成
- **决策矩阵常量位置**: `backend/src/platform/planner/intent-engine-locale-matrix.ts` 导出 `INTENT_ENGINE_LOCALE_MATRIX: Array<{intent, engine, locale, promptLanguage, emit: 'full' | 'reduced' | 'skip', reducedFactor?: 0.3}>` (23 行对应表中 23 行)
  - `navigational` 全部 `emit='reduced'` reducedFactor 0.3 (配额打 3 折)
  - 所有其他 `emit='full'`
  - `emit='skip'` 的永不入库
- **多语言纯洁**: zh-CN Prompt 只用 brand.nameZh, en-US Prompt 只用 brand.nameEn; 品牌名纯文本内嵌, 禁止混语
- **Prompt 质量约束** (PRD §4.2.2):
  - 自然语言完整句子, 像真人问话
  - 避免关键词堆砌 (LLM prompt 模板中 few-shot 必须对比正反例)
  - 每 Topic 至少覆盖 `informational + commercial` 两种 Intent (必选)
  - 支持多轮 Prompt 链 (主问题 + 追问 1-2 条): 用 `parentPromptId` 自引用, `isFollowUp=true`
- **输出**: `PlatformPrompt[]` 落 `platform_prompts` 表 + 触发下一层 Query 组装

**交付**: `prompt-generator.ts` + `intent-engine-locale-matrix.ts`; 单测 `tests/unit/platform/planner/intent-engine-matrix.test.ts` 断言 23 行全覆盖 (PRD §4.10.3.A Harness 兜底)。

### 任务 4 · Query Assembler (Prompt × Profile) + ProfileGroup seed — `backend/src/platform/planner/query-assembler.ts` + `backend/src/platform/seed/profile-groups.ts`

**真相源**: PRD §4.2.3 + §4.2.3a + Session 1 产出的 `backend/src/engines/profile-sampler.ts` (FNV-1a + 8 preset)。

**Query Assembler**:
- 每 Prompt 随机 (确定性 seed) 采样 3-5 个 Profile — 复用 Session 1 的 `sampleProfileForSeed(profileGroupId, seed)` 而不是重造采样器
- Query 记录 `profileHash` (用于未来去重), `profileGroupIds[]` (冗余存储方便按 group 聚合), `personaPrefix` (system prompt 人设字符串), `browserLocale` (浏览器 locale), `promptLanguage` (继承自 Prompt.language)
- `browserLocale` 与 `promptLanguage` MVP 默认一致, 但字段独立保留 (PRD §4.2.3 注释, 为 Phase 2 跨市场监测留余地)

**ProfileGroup seed** (PRD §4.2.3a 验收标准):
- `backend/src/platform/seed/profile-groups.ts` 导出 `MVP_PROFILE_GROUPS` 至少 6 条:
  - `all` (默认, isDefault=true, 无 filterRules)
  - `young_female_tier1` (age 18-30 + gender female + city tier=1)
  - `mid_age_female_tier23` (age 30-50 + gender female + city tier ∈ {2,3})
  - `male_tier1` (gender male + city tier=1)
  - `price_sensitive` (purchasingPower ∈ ['budget','mid'])
  - `zh_chatgpt` (promptLanguageIn=['zh-CN'] + appliesToEngines 含 chatgpt)
  - `en_chatgpt` (promptLanguageIn=['en-US'] + appliesToEngines 含 chatgpt)
- `matchProfileGroups(profile: AgentProfile): string[]` 工具函数: 对任意 Profile 输入, 返回该 Profile 命中的所有 ProfileGroup id, 至少返回 `['all', <1 个特化组>]`
- 插入 Profile / Query 时同步调用, groupIds 冗余到 Query.profileGroupIds

**最小样本保护**:
- `hasEnoughSamplesInGroup(groupId, dateRange, engineFilter, repos): { ok: boolean, count: number }` — 阈值 50 Queries / 30 天
- Session 3 Dashboard API 会调用此函数; 本 Session 只交付函数 + 单测, 不接 API

**新增 4 条 Harness (Group G) + 2 条 self-seeded fixture** — 追加到 `scripts/ci-check.mjs`:

- **G1** `category-topic-brand-contamination` — 扫 `backend/src/platform/planner/**/*.ts` 的 Topic 生成代码路径, 确保任何生成品类 Topic 的函数后面必跟 `validateCategoryTopicPurity` 调用 (grep 调用点存在性, 缺失阻断)
- **G2** `intent-engine-matrix-full-coverage` — 扫 `backend/tests/unit/platform/planner/intent-engine-matrix.test.ts` 必须包含 `expect(matrix.length).toBe(23)` 断言 (首字面量校验)
- **G3** `navigational-reduced-factor` — 扫 `backend/src/platform/planner/intent-engine-locale-matrix.ts` 所有 `intent: 'navigational'` 行必须带 `reducedFactor: 0.3` 或 `emit: 'skip'`, 缺失视为漏降频
- **G4** `profile-group-seed-minimum` — 扫 `backend/src/platform/seed/profile-groups.ts` 的 `MVP_PROFILE_GROUPS` 数组必须 ≥6 条且包含 `all` / `young_female_tier1` / `zh_chatgpt` / `en_chatgpt` 四个关键 id (PRD §4.2.3a 最小保证)

self-seeded 违规 fixture (放 `backend/src/__ci_fixtures__/`):
- `G1_category_topic_leak.cifixture.ts` — 一个"生成品类 Topic 但不调用 validateCategoryTopicPurity"的函数
- `G3_navigational_no_downsample.cifixture.ts` — 一个 `{ intent: 'navigational', emit: 'full' }` 不带 reducedFactor 的行

`scripts/ci-harness-selftest.mjs` 的 EXPECTED_POSITIVES 从 8 扩到 10 (+G1 + G3)。G2 / G4 是全局契约型, 不写 self-fixture (因 fixture 会污染真实测试文件)。

### 任务 5 · Topic 管理 API (RESTful, Next.js App Router) — App Session 层

**真相源**: PRD §4.2.5 + CLAUDE_CODE_SESSIONS.md Session 2 §4。

**⚠️ 注意 scope**: 若 App Session 0-rev 已搭 API 路由骨架, 本 Session 只实现以下 6 端点的 handler + OpenAPI schema 声明 (不引入新路由前缀); 若 App Session 0-rev 未覆盖 `/api/v1/` 用户态路由 (只覆盖 `/admin/api/v1/`), 本 Session 在实施前先停下报告 Frank, 讨论是本 Session 承接还是延后到 Session 3 一起做。

6 个端点:
- `POST /api/v1/projects/:id/topics/generate` — 触发 Topic + Prompt 生成
- `GET /api/v1/projects/:id/topics` — 列表 (过滤 dimension / intent / language, 分页)
- `POST /api/v1/projects/:id/topics/custom` — 用户自定义 Topic (系统自动生成 Prompt)
- `PATCH /api/v1/projects/:id/topics/:tid` — 字段级 merge (与 PRD §4.5.1 对齐)
- `DELETE /api/v1/projects/:id/topics/:tid` — 级联删 Prompt
- `GET /api/v1/projects/:id/topics/:tid/prompts` — 某 Topic 下的 Prompt 列表

每端点必须: (a) 在 `docs/openapi.yaml` 中声明 request/response schema + example; (b) 至少 1 条 Vitest 契约测试 (happy path + 1 错误路径); (c) 经过 `src/app/api/v1/_middleware.ts` 的 API Key 鉴权 (复用 Session 0-rev 的骨架)。

### 任务 6 · 端到端: 接通 `seed-platform-data.ts` 步骤 4-5

**真相源**: `backend/scripts/seed-platform-data.ts` 当前在步骤 4-5 抛 stub 错误 (Session 1.5 留的接口)。

- 步骤 4: 对 4 行业的所有品牌/产品批量跑 `topic-planner.generatePlatformTopics()`
- 步骤 5: 对生成的 Topic 跑 `prompt-generator.generateAndPersistPrompts()` + `query-assembler.assembleQueries()` (MVP 先入 `status='pending'` 不入爬取队列)
- **Dry-run transport** 按 Session 1.5 模式扩展: 新增 Topic/Prompt/Profile 三类 canned JSON 响应, 脱网可跑
- 运行 `npm run seed:platform:dry` 必须全绿, 4 行业合计生成:
  - Topic ≥ 4 行业 × 20 = 80 条 (品类 dimension ≥40% = 32 条)
  - Prompt ≥ Topic × 平均 2.5 (Intent × Locale 组合) = 200 条
  - Query ≥ Prompt × 3-5 Profile = 600-1000 条

### 任务 7 · Vitest 覆盖率 (≥80% 分支, `src/platform/planner/**` + `src/platform/seed/**`)

最小测试文件清单:
- `tests/unit/platform/planner/topic-planner.test.ts` — Bottom-Up 顺序 / 品类纯净度 / LLM budget exceeded / 变体扩展
- `tests/unit/platform/planner/prompt-generator.test.ts` — Topic × Intent 必选 informational+commercial / 多轮链 parentPromptId / 中英品牌名不混用
- `tests/unit/platform/planner/intent-engine-matrix.test.ts` — **23 行全覆盖硬断言** (PRD §4.10.3.A Harness 兜底)
- `tests/unit/platform/planner/query-assembler.test.ts` — profileHash 确定性 / profileGroupIds 冗余 / 3-5 Profile 采样
- `tests/unit/platform/seed/profile-groups.test.ts` — MVP_PROFILE_GROUPS ≥6 条 + 必含 id / matchProfileGroups 至少返回 2 组 / hasEnoughSamplesInGroup 阈值 50

---

## 5. Phase Gate · 完成前必跑的 9 项验证 (§0 规则 7)

把下列 9 项的执行结果逐条贴给 Frank:

**D1-D3 Schema 对齐**:
- D1 · `cat backend/prisma/schema.prisma | grep -c "^model \(PlatformTopic\|PlatformPrompt\|PlatformQuery\|ProfileGroup\)"` = 4
- D2 · `ls backend/prisma/migrations/*platform*` 或 `*profile_groups*` 至少 1 条新迁移
- D3 · 新增模型的 CHECK 约束在 migration SQL 中出现 (dimension / intent / language / status)

**S1-S4 服务端行为**:
- S1 · `npx tsx scripts/seed-platform-data.ts --dry-run --industry=beauty-personal-care --product-brands=3` 命令**退出码 0** + stdout 包含 Topic/Prompt/Query 生成计数
- S2 · `npm run seed:platform:dry` (全 4 行业 dry-run) 退出码 0
- S3 · `npm run test:coverage -- --coverage.include='src/platform/planner/**' --coverage.include='src/platform/seed/**'` 4 项指标 ≥80%
- S4 · `npm run test -- tests/unit/platform/planner/intent-engine-matrix.test.ts` PASS, 测试输出里可见 "23 combinations asserted" 字样 (或等价)

**C1-C2 Harness**:
- C1 · `node scripts/ci-check.mjs` 全绿 (含新增 G1/G2/G3/G4 四条)
- C2 · `node scripts/ci-harness-selftest.mjs` 输出 `selftest: PASS (10 / 10 fixture expectations met)`

9 项全绿 = Phase Gate 过; 有任何一项红, 贴原始输出 + 诊断 + 修复建议后停下, 等 Frank 决策。

---

## 6. 偏离记录 (§0 规则 3, 本 Session 完工时交付)

Session 完成时在 CLAUDE.md 新增决策 #26 (App Session 2), 内含:

- **A. 交付清单** (文件 / 行数 / 新增 Harness / Vitest 统计)
- **B. 架构要点** (Topic Planner 5 步 / Intent×Engine×Locale 23 行决策表 / Query Assembler 复用 Session 1 profile-sampler)
- **C. 偏离说明**:
  - **C1 偏离原 Prompt (N 处)**: 每处写理由 + 源偏离方向
  - **C2 偏离真相源 (N 处)**: 每处写理由 + Phase 2 收敛计划
- **D. 未来工作承接**: Session 3 MCP / API 消费 platform_topics · Session 1.2 Camoufox 接入后 Query 进入真实爬取队列
- **E. 跨 Session 反向同步清单 (§0 规则 8, 必填)**:
  - 列出所有下游 Session Prompt 中对 `generatePlatformTopics` / `platform_topics` 等的引用位置
  - 每处说明: 已反向 patch / 无需 patch / 需 Frank 决策

---

## 7. 硬性禁令 (违反 = 停下等 Frank 决策)

- ❌ 禁止在本 Prompt 内完整重抄 PlatformTopic / PlatformPrompt / PlatformQuery / ProfileGroup 的 Prisma 字段清单 (§0 规则 1, 真相源是 PRD §4.2.x + DATA_MODEL.md)
- ❌ 禁止硬编码 Intent × Engine × Locale 23 行决策到业务代码; 必须独立常量文件 + 单测覆盖 (PRD §4.10.3.A 应用规则 4 + Harness G2)
- ❌ 禁止手写随机数生成 Profile sampling; 必须复用 Session 1 的 FNV-1a 确定性采样 (CLAUDE.md #22 · `backend/src/engines/profile-sampler.ts`)
- ❌ 禁止在 `navigational` 配额上走 100% (必须 reducedFactor 0.3, Harness G3 拦截)
- ❌ 禁止品类 Topic 标题 / Prompt 文本出现任何 KG Brand nameZh/nameEn/aliases (CLAUDE.md #16 + Harness G1)
- ❌ 禁止新引入第三方测试库 (视觉回归 / 契约生成 / fixture 库) 替代 Vitest + supertest + openapi-typescript (CLAUDE.md #18)
- ❌ 禁止跳过 Pre-Flight Grep 报告直接动代码 (§0 规则 2)
- ❌ 禁止 `npm run ci` 红着 merge (CLAUDE.md #18 目标: Frank 零介入)
- ❌ 禁止 Phase Gate 9/9 全绿后不 commit 就宣绿 (Session A0 64 文件 untracked 事件教训, 2026-04-22 固化; 详见 §8.F)

---

## 8. 完成后报告格式

把下列模板的每个字段填好, 一次性贴到聊天:

```
[Session 2 完工报告]

A · 交付文件清单
- backend/prisma/schema.prisma · +XXX 行 (PlatformTopic/PlatformPrompt/PlatformQuery/ProfileGroup)
- backend/prisma/migrations/<timestamp>_session2_pipeline/migration.sql
- backend/src/platform/planner/topic-pool.ts · 重写 (stub → 真实实现)
- backend/src/platform/planner/topic-planner.ts · 新增 (XXX 行)
- backend/src/platform/planner/prompt-generator.ts · 新增 (XXX 行)
- backend/src/platform/planner/query-assembler.ts · 新增 (XXX 行)
- backend/src/platform/planner/intent-engine-locale-matrix.ts · 新增 (23 行表 + 类型)
- backend/src/platform/planner/prompts.ts · 新增 (LLM prompt 模板)
- backend/src/platform/seed/profile-groups.ts · 新增 (MVP_PROFILE_GROUPS + matchProfileGroups)
- backend/src/app/api/v1/projects/[id]/topics/**/route.ts · 6 端点
- backend/scripts/seed-platform-data.ts · +XXX 行 (步骤 4-5 接通)
- backend/tests/unit/platform/planner/*.test.ts · 4 套, XXX 例
- backend/tests/unit/platform/seed/profile-groups.test.ts · 1 套, XXX 例
- scripts/ci-check.mjs · +G1/G2/G3/G4 四条规则
- scripts/ci-harness-selftest.mjs · EXPECTED_POSITIVES 8 → 10
- backend/src/__ci_fixtures__/G1_category_topic_leak.cifixture.ts · 新增
- backend/src/__ci_fixtures__/G3_navigational_no_downsample.cifixture.ts · 新增
- docs/openapi.yaml · +6 端点 schema

B · Phase Gate 9/9 结果
| 项 | 状态 | 输出摘要 |
|---|---|---|
| D1 schema model 计数 | ✅ | 4 |
| D2 migration 存在 | ✅ | <filename> |
| D3 CHECK 约束 | ✅ | 4 枚举列全含 |
| S1 单行业 dry-run | ✅ | Topic=XX Prompt=XX Query=XX |
| S2 全行业 dry-run | ✅ | 合计 Topic=XXX Prompt=XXX Query=XXX |
| S3 Vitest 覆盖率 | ✅ | 分支 XX.X% / 行 XX.X% |
| S4 Intent×Engine×Locale 23 行覆盖 | ✅ | "23 combinations asserted" |
| C1 Harness 全量 | ✅ | 42 rules green (38 原 + 4 新) |
| C2 Selftest | ✅ | 10 / 10 |

C · 偏离记录 (CLAUDE.md #26 将写入)
- C1 偏离原 Prompt: N 处
  1. ...
- C2 偏离真相源: N 处
  1. ...

D · 下游 Session 反向同步 (§0 规则 8)
grep 命中 M 处:
  - docs/CLAUDE_CODE_SESSIONS.md line XXXX · Session 3 引用 generatePlatformTopics → 已反向 patch / 无需 patch
  - docs/ADMIN_CLAUDE_CODE_SESSIONS.md line XXXX · Session A2.1 引用 ProfileGroup → 已反向 patch / 无需 patch
  - ...

E · 遗留问题 (如有)
- ...

F · git commit 步骤 (Phase Gate 9/9 全绿后**立即**执行, 不得跳过)

把本 Session 全部产出打包成一个 commit, commit message 用 PowerShell here-string (Frank 在 Windows, 避免 bash HEREDOC):

```powershell
cd C:\Users\frank\GENPANO
git status                            # 确认 working tree 期望内
git add backend/ scripts/ docs/       # 按需细化, 不建议 git add -A
git status --short                    # 复核 staged 列表

$msg = @"
Session 2: Pipeline Planner (Topic -> Prompt -> Query) - Phase Gate 9/9 PASS

本 Session 交付 (参见 CLAUDE.md #26):
- Prisma: PlatformTopic / PlatformPrompt / PlatformQuery / ProfileGroup 4 张表 + CHECK 约束
- Planner: topic-planner.ts (Bottom-Up 5 步) / prompt-generator.ts / query-assembler.ts
- Matrix: intent-engine-locale-matrix.ts (PRD 4.10.3.A 23 行决策表)
- Seed: profile-groups.ts (MVP_PROFILE_GROUPS 6 组) + seed-platform-data.ts 步骤 4-5 接通
- API: /api/v1/projects/:id/topics 6 端点 (若本 Session 覆盖)
- Harness: Group G 新增 G1/G2/G3/G4 四条规则 + G1/G3 self-seeded fixture
- Selftest: EXPECTED_POSITIVES 8 -> 10
- Vitest: src/platform/planner/** + src/platform/seed/** 分支覆盖 >=80%

Phase Gate 9/9 全绿: D1-D3 schema + S1-S4 server + C1-C2 harness.
下一步 Session 3 (分析引擎 + API + MCP + Citation) 可启动.

回引: CLAUDE.md 决策 #26 (Session 2); 测试地基 #21; Session 1 #22; Session 1.5 #23.
"@
$msg | Out-File -FilePath commit-msg.txt -Encoding utf8
git commit --file commit-msg.txt
Remove-Item commit-msg.txt
git log --oneline -3                  # 验证 commit 落地, 输出贴给 Frank
```

**注意事项**:
- commit message **禁止** 使用 § / ✅ / — 等特殊 Unicode (PowerShell UTF-8 可能乱码), 用 "第 X 节" / "PASS" / "-" 替代
- commit 标题格式固定: `Session {号}: {主题} - Phase Gate X/X PASS`
- commit body 必须回引 CLAUDE.md 决策号 + 按类别列交付清单
- commit 完成后**必跑** `git log --oneline -3` 把输出贴给 Frank 作为 closure 证据
- 不要 `git push`, push 由 Frank 决定时机

本步骤完成后才算本 Session 真正"关闭", 未 commit 即宣绿会导致下一 Session 的 diff 被 A0 / Session 2 未 commit 改动污染 (参见 §7 新增硬禁令)。

请 Frank 决策: 是否批准本 Session 宣绿并登记 CLAUDE.md #26?
```

---

开工前请先完成第 2 节 Pre-Flight Grep, 把 G1-G6 原始输出报告给我, 等我回复后再动代码。
```

---

## 给 Frank 的提示

- 本 Prompt 是**自包含**的 — CC 不需要额外上下文, 按 §1-§8 顺序执行即可
- 复制时包含上下 ```` ``` ```` 代码围栏, CC 的输入是整个代码块内容
- 若 CC 在 Pre-Flight Grep 阶段就命中非预期条目 (例如 G2 发现已有 `platform_topics` 表定义), 不要让它"修正"绕过, 停下告诉我, 我来决定是 patch 真相源还是调整 Prompt
- 期望 CC 给 Pre-Flight 报告的时间: 5-15 分钟; Session 2 整体预估 2-3 天 (含任务 5 API 端点, 若任务 5 延后到 Session 3 则 1.5-2 天)
- 完工后 CC 会主动产出 `[Session 2 完工报告]`, 你把它贴回给我, 我来起草 CLAUDE.md #26 的 A/B/C/D/E 段
