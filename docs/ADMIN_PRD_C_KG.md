# ADMIN PRD §C 深化 — 知识图谱运营

> **状态**: v1 · 2026-04-16 · 作为 `docs/ADMIN_PRD.md` §4.3 的深化。ADMIN_PRD.md §4.3 保留为一屏摘要；落地到 Claude Code 的实现细节 / 数据模型 / 实体运维 SOP 以本文为准。
>
> **配套**: 本文 §7 的 Entity Merge / KG Diff / Quality Monitor 实施阶段。

---

## 0. 本模块的运营价值

知识图谱（Industry → Category → Brand → Product + Relations）是 **GENPANO 的核心数据资产** — 它是 "监测谁" 和 "谁和谁比" 的来源。图谱错一处，所有下游的 SoV / 竞品对比 / 引用份额都错。

这一组页面承担三件事：

1. **冷启动补全** — 4 个 MVP 行业的品类树、核心品牌、基础关系，在 Week 1 内通过 LLM + 人工 ≤ 10 小时构建完成
2. **持续扩展** — 每日从用户提交 + Response 挖掘新增实体；运营 ≤ 30 分钟/天 完成审核
3. **持续清洁** — 别名冲突消解、关系置信度维护、孤立节点清理、幻觉实体下架；保证"图谱可信度 ≥ 95%"

**设计约束**:
- 所有图谱修改**必须可审计 + 可回滚**；KG 是 write-heavy 的平台资产
- LLM 发现的实体**永远先进 pending**，人工审核后才 active；MVP 绝不自动入图
- 用户共建（Brand Submission）建立 **trust score**，高信任用户的提交可以"快速路径"，恶意用户的提交自动降权

---

## 1. 运营场景驱动设计（KG workflows）

| # | 场景 | Primary Pages | 涉及实体 |
|---|---|---|---|
| K1 | 新行业"服装时尚"冷启动，批量初始化品类和品牌 | 行业 & 品类树 → 品牌批量导入 → 关系补全 | industry / category / brand |
| K2 | 用户提交 "花西子" 不在图谱 | Brand Submission → 自动核验 → 人工确认 → 入图 | brand_submission → brand |
| K3 | LLM 从 Response 挖出 "PRADA Cafè"，但归属可疑 | Discovery Log → 品牌审核抽屉 → 合并 or 拒绝 | discovery_log → brand |
| K4 | 别名 "小棕瓶" 被雅诗兰黛和 Kiehl's 同时认领 | Aliases & Conflicts → 仲裁 | alias_conflict → brand.aliases |
| K5 | 运营发现某关系边 "Chanel COMPETES_WITH Lancôme" 置信度长期 0.4，建议清理 | Relations 编辑器 → 手动调整或删除 | brand_relation |
| K6 | 用户投诉 "我的产品 A 下架了，图谱里还在" | 产品审核 → 标 deprecated | product |
| K7 | 检测到 "Guerlain" 和 "娇兰" 实际为同一品牌被入库两次 | Entity Merger → 二次确认 → 合并 | brand × 2 → 1 |
| K8 | 每日需要一份 "昨日图谱变化" 的摘要 | KG Diff Viewer | all entities |
| K9 | 某类别下 Product 数量异常（孤立或突涨） | KG Quality Monitor | category / product |
| K10 | Phase 2 想按 industry 授权给不同 support 成员审核 | Submissions + role assignment | submission |
| K11 | LLM 幻觉实体（现实中不存在的品牌）进入 discovery | Discovery Log → 拒绝 + 回流负例给 LLM | discovery_log |
| K12 | 用户批量恶意提交 spam brand | Submissions + Trust Score | submission_trust_score |

---

## 2. Module C 子页总览（深化后共 9 页）

ADMIN_PRD.md §4.3 里原列 6 个子页，此次深化新增 3 页（标 ★）。

| 编号 | 子页 | URL | 新增? | 场景覆盖 |
|---|---|---|---|---|
| C1 | 行业 & 品类树 | `/admin/kg/industries` | — | K1 |
| C2 | 品牌审核 | `/admin/kg/brands` | — | K2, K3 |
| C3 | 产品审核 | `/admin/kg/products` | — | K6 |
| C4 | 别名与关系 | `/admin/kg/aliases-relations` | — | K4, K5 |
| C5 | Brand Submission | `/admin/kg/brand-submissions` | — | K2, K10, K12 |
| C6 | Discovery Logs | `/admin/kg/discovery-logs` | — | K3, K11 |
| C7 ★ | Entity Merger & Splitter | `/admin/kg/entity-ops` | ✓ | K7 |
| C8 ★ | KG Diff Viewer | `/admin/kg/diff` | ✓ | K8 |
| C9 ★ | KG Quality Monitor | `/admin/kg/quality` | ✓ | K9, K11, K12 |

---

## 3. 子页详细设计

每个子页固定七段式：**目的 · IA · 交互 · UI 参考 · 边界 · 权限审计 · 验收**。

### C1. 行业 & 品类树 `/admin/kg/industries`

**目的**。冷启动 + 日常品类维护；直观展示每个 category 下的 brand/product 数量，快速发现失衡。

**IA**:
- 左侧：4 个行业 tab（美妆个护 / 奢侈品 / 食品饮料 / 服装时尚）+ 每行业一棵品类树（≤ 3 级）
- 右侧：选中节点的"详情"面板：
  - 品牌数 / 产品数 / 近 7d Topic 生成数 / 近 7d Response 命中数
  - 直属品牌 mini-list（≤ 5 个高提及，剩余给 "查看全部 →"）
  - "LLM 补全子品类" 按钮 → 预览 → 入库（人工 approve）
- 顶部工具条：筛选 `status=active|deprecated`、搜索 category 名

**关键实现点**:
- 品类树使用 **AntV G6 v5** 的 compact tree 布局，禁手写 SVG。
- 节点右键菜单（复用 Radix ContextMenu）：新建子品类 / 改名 / 移动到... / 标 deprecated

**边界**:
- 改名是 soft rename（保留 `previous_names[]` 历史），因为 category 被 Topic 生成器引用，立即改名会让历史 Topic 追溯时找不到源
- 移动品类要先检查"被引用的 active Topic 数"，> 0 需 confirm + 理由 + 批量迁移

**权限与审计**:
- 新建 / 改名 / 移动 / 标 deprecated → super_admin + 理由 + 审计
- "LLM 补全" 触发 LLM 花费 → 计入 Cost（D 模块）

**验收**: 构造一棵 3 级树并 bulk create / rename / move / deprecated；audit log 必须对应 4 条 entry。

---

### C2. 品牌审核 `/admin/kg/brands`

**目的**。所有 brand 实体的主入口 — 新建、审核、修改、下架。

**状态机** (扩展 ADMIN_PRD.md §4.3.2):

```
discovered (LLM 发现)
      ↓ 自动核验
submitted (用户提交, 或自动核验通过)
      ↓ 人工审核
     ┌───── approved ─────→ active (生产态)
     │
     └───── rejected / merged / inactive
```

**IA**:
- 顶部 KPI: 待审 / 24h 内新增 / active 总数 / 近 7d rejected 率
- 表格列: logo-mini / nameZh / nameEn / industry / category / status / submitter / auto_verify_score / submitted_at / reviewer / actions
- 筛选器: status / industry / source (`discovery|submission|manual`) / auto_verify_score / has_conflict
- 抽屉字段（点击行）:
  - **核验面板**: 评分构成（域名 MX / 行业归属 / 别名冲突 / LLM 幻觉检测）+ 总分
  - **多语言名**: nameZh / nameEn / nameJa / ...（MVP 只 zh/en）
  - **别名列表** + 语言标签 + 来源（user / discovery / manual）+ "删除" 按钮
  - **关系边**: COMPETES_WITH / SAME_GROUP，每条含 confidence 和时间序列 mini chart
  - **近 14 天 mention 样本**: 随机 10 条，点击展开看原始 Response
  - **Discovery source**: 如来自 LLM 发现，展示原始引用 (`discovery_logs.raw_llm_output` 的对应片段高亮)

**新增字段 / 细化数据模型**:

```sql
-- kg_brands 扩展
ALTER TABLE kg_brands
  ADD COLUMN name_zh TEXT,
  ADD COLUMN name_en TEXT,
  ADD COLUMN logo_url TEXT,
  ADD COLUMN status TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN source TEXT NOT NULL,             -- discovery | submission | manual | llm_bulk
  ADD COLUMN auto_verify_score NUMERIC,        -- 0-100
  ADD COLUMN auto_verify_breakdown JSONB,      -- {domain_mx:20, industry_fit:18, ...}
  ADD COLUMN approved_by UUID REFERENCES admin_users(id),
  ADD COLUMN approved_at TIMESTAMPTZ,
  ADD COLUMN rejected_reason TEXT,
  ADD COLUMN merged_into_id UUID REFERENCES kg_brands(id),
  ADD COLUMN deprecated_at TIMESTAMPTZ;

CREATE TABLE kg_brand_aliases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES kg_brands(id),
  alias_value TEXT NOT NULL,
  language TEXT NOT NULL,                       -- zh-CN|en-US|ja|...
  source TEXT NOT NULL,                         -- user|discovery|manual|merged_from
  added_by UUID REFERENCES admin_users(id),
  added_at TIMESTAMPTZ DEFAULT now(),
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE(brand_id, alias_value, language)
);
CREATE INDEX ON kg_brand_aliases (lower(alias_value));

-- kg_brand_relations 增加 confidence 时序
CREATE TABLE kg_brand_relation_history (
  id BIGSERIAL PRIMARY KEY,
  relation_id UUID NOT NULL REFERENCES kg_brand_relations(id),
  confidence NUMERIC NOT NULL,
  evidence_count INT NOT NULL,
  computed_at TIMESTAMPTZ NOT NULL,
  -- 让我们在抽屉里画 confidence 曲线
  UNIQUE(relation_id, computed_at)
);
```

**批量操作**:
- 多选 → 批量 approve / reject / merge
- 批量 merge 需要逐条确认 "合并到哪个已存在品牌"（不支持"批量合并到同一目标"防误操作）

**边界**:
- 同一时刻 pending 中的同行业品牌数 > 200 → 首页 P2 告警（可能 LLM 挖掘失控）
- auto_verify_score < 40 的不允许直接 approve，必须 "覆盖理由 + 二次确认"
- `merged_into_id` 写入后，该品牌的所有 aliases 自动迁移到 target 品牌的 aliases 表；原品牌 status 置 `merged`

**权限与审计**: 所有变更（approve / reject / merge / 别名增删 / 关系增删）super_admin + 理由 + 审计。

**验收**: 构造 5 条 pending → 批量 approve 3 条 + merge 1 条 + reject 1 条；audit log 必有 5 条 + aliases 迁移应正确。

---

### C3. 产品审核 `/admin/kg/products`

**结构同 C2，扩展字段**:

- `category_id` / `brand_id`（必填）
- `product_line` 可选（如 "小棕瓶" 属于 "雅诗兰黛·护肤" 产品线）
- `launch_date` / `retired_date` — 产品生命周期
- `key_features` JSONB — 成分 / 价位段 / 规格 / 定位关键词
- `status` enum: `pending | active | deprecated | retired | limited_edition_expired`

**产品审核的独特约束**:

- **必须挂 brand**: `brand_id` 非空 + brand 必须已是 active 状态（MVP 不允许同时创建 brand + product）
- **LLM 结构化抽取结果的字段对齐**: 用户提交 / Discovery 的产品描述，要通过 LLM 抽取关键字段（价位 / 规格 / 品类）→ 人工审核时作为预填
- **价位段归一化**: `price_tier` enum ('entry', 'mid', 'premium', 'luxury')，UI 下拉框，不让手输数字

**新增表**:

```sql
CREATE TABLE kg_product_lines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES kg_brands(id),
  name_zh TEXT,
  name_en TEXT,
  description TEXT,
  created_by UUID REFERENCES admin_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE kg_products
  ADD COLUMN product_line_id UUID REFERENCES kg_product_lines(id),
  ADD COLUMN launch_date DATE,
  ADD COLUMN retired_date DATE,
  ADD COLUMN price_tier TEXT,
  ADD COLUMN key_features JSONB,
  ADD COLUMN llm_extracted_raw JSONB;           -- LLM 原始输出，审核参考
```

**边界**:
- Product status `retired` 后仍保留数据但不参与 Topic 生成；如果 30 天内被 Response 挖出说明"可能复活"，自动触发重审提醒

**验收**: 同 C2 + 验证 retired product 不出现在 Topic generation 输入里。

---

### C4. 别名与关系 `/admin/kg/aliases-relations`

**ADMIN_PRD.md §4.3.4 基础 + 新增**:

**两个独立 tab**:

#### 4.1 别名冲突（alias_conflicts）

**IA**:
- 表格列: `alias_value / language / 候选实体列表 / evidence_counts / 首次发现 / 状态`
- 点击行 → 抽屉 "仲裁视图"：
  - 左：该 alias 最近 20 条 mention 上下文（句子级），每条标明识别出的品牌
  - 右：候选实体卡片（多张），每张显示 "支持此归属的证据数 / 关键上下文 / 当前 active 别名数"
  - 底部：单选 "归属到 X" / "拆分为新品牌" / "标记为同义（跨品牌共用）" / "忽略"

**决策类型枚举**:
- `resolved_to_brand(id)` — 归属给 brand id
- `split_new` — 创建新 brand 并归属（罕见）
- `shared` — 允许多品牌共用（极罕见，慎用）
- `ignore` — 标为歧义无关

**边界**:
- `shared` 决策必须写 detailed reason，后端触发 F4 场景下"该 alias 的提及需要二次消歧"（在 parser 做 context 判断）

#### 4.2 关系清理（brand_relations / product_relations）

**IA**:
- 筛选预设：
  - `confidence < 0.3` — 弱关系，建议删除
  - `confidence > 0.9 且 类型潜在冲突` — 如同时 COMPETES_WITH 和 SAME_GROUP，系统性矛盾
  - `orphan` — 关系一端实体 status != active
- 表格显示: from / to / relation_type / confidence / evidence_count / last_updated / confidence sparkline (时序)
- 点击行 → 抽屉，展示 `kg_brand_relation_history` 的曲线 + 关联证据（从哪些 Response 抽出）
- 批量操作：调整 confidence（设为 0 → 逻辑删除 / 设为指定值）、修改 relation_type、永久删除

**边界**:
- 永久删除关系**非幂等**；删除后如果 Response 挖掘再次发现同关系，会以新 id 重建（保留历史）

**权限与审计**: 冲突仲裁 / 关系增删 / confidence 调整 → super_admin + 理由 + 审计。

**验收**: 构造 5 条 conflict + 20 条弱关系 → 依次仲裁 + 批量置 0 → `alias_conflicts` 状态流转 + `brand_relations` 软删除记录。

---

### C5. Brand Submission `/admin/kg/brand-submissions`

**ADMIN_PRD.md §4.3.5 基础 + 新增**:

**SLA 看板**（页面顶部）:
- 待审总数 / 24h 内新增 / 超 24h SLA 未处理 / 平均处理时长 / rejected 率（本周）
- 超 SLA 的提交逐条显示于 Inbox 顶部 + 首页 P1 告警

**Trust Score 系统**（新增）:

用户提交品牌的历史数据用于计算 `submission_trust_score`:

```sql
CREATE TABLE submission_trust_score (
  user_id UUID PRIMARY KEY REFERENCES users(id),
  total_submissions INT NOT NULL DEFAULT 0,
  approved_count INT NOT NULL DEFAULT 0,
  rejected_count INT NOT NULL DEFAULT 0,
  spam_flagged_count INT NOT NULL DEFAULT 0,
  trust_score NUMERIC NOT NULL DEFAULT 50,       -- 0-100
  -- 计算: approved/total * 100 - spam_flagged * 30 (下限 0)
  last_computed_at TIMESTAMPTZ,
  auto_tier TEXT NOT NULL DEFAULT 'normal'       -- fast_track | normal | review_required | blocked
);
```

**tier 规则**:
- `trust_score ≥ 80` 且 approved ≥ 5 → `fast_track`（自动核验 ≥ 85 即直通审核完成）
- `trust_score ≤ 30` → `review_required`（需双审 / 在 solo 模式下需要强制输入详细理由）
- `spam_flagged ≥ 3` → `blocked`（所有后续提交直接进 rejected_pending 状态）

**交互新增**:
- 审核卡片上显示提交者的 trust tier badge
- "标记为 spam" 按钮：触发 +1 到 spam_flagged_count，并自动通知用户

**LLM 预验证接入**（对齐 §4.3.5 原文）:
- 用户提交后立即调用 LLM: `是否存在该品牌？主要官网？行业归属？`
- LLM 结果填充 "auto_verify_breakdown"
- 如果 LLM 返回"找不到该品牌"→ `auto_verify_score` 直接减 30

**权限与审计**: 处理 submission（approve/reject/merge）+ trust score 手动调整 → super_admin + 理由 + 审计。

**验收**: 构造 3 个 user × 不同 trust tier，提交同一批 brand，验证 fast_track 自动通过、review_required 需 extra confirm、blocked tier 提交应 409。

---

### C6. Discovery Logs `/admin/kg/discovery-logs`

**ADMIN_PRD.md §4.3.6 基础 + 新增**:

**LLM 幻觉检测**（页面新增视图）:
- 定期抽样 discovery 出来的 brand / product，调用第二模型（用独立 prompt）复核 "该实体是否真实存在？"
- 不通过的自动标 `hallucination_suspected = true`，在 Discovery Logs 顶部醒目列出
- 累积统计: 近 30 天 discovery 幻觉率，显示在 KG Quality Monitor (C9)

**质量评估 KPI**（页面顶部）:
- 近 7d discovery 总数 / 其中 approved 率 / hallucination_suspected 率 / avg time-to-review
- 按来源引擎分（ChatGPT 的 discovery 幻觉率 vs 豆包 等）

**回流负例**:
- Reject 的 discovery 带原因（"品牌不存在 / 重复 / 不相关"）写入 `discovery_feedback_negatives`，离线用于 LLM 下次 prompt 的 few-shot

**新增字段**:

```sql
ALTER TABLE discovery_logs
  ADD COLUMN hallucination_suspected BOOLEAN DEFAULT FALSE,
  ADD COLUMN hallucination_verified_at TIMESTAMPTZ,
  ADD COLUMN rejected_category TEXT;      -- not_real|duplicate|irrelevant|wrong_industry

CREATE TABLE discovery_feedback_negatives (
  id BIGSERIAL PRIMARY KEY,
  discovery_id UUID NOT NULL REFERENCES discovery_logs(id),
  rejected_category TEXT NOT NULL,
  raw_llm_output JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

**权限与审计**: 触发幻觉复核（消耗 LLM 成本）→ super_admin；其他只读 + 拒绝动作走 C2/C3 统一流。

**验收**: 构造 50 discovery → 其中 5 条触发幻觉复核 → 3 条进 suspected 列表 → 人工 reject 后进 negatives 表。

---

### C7. ★ Entity Merger & Splitter `/admin/kg/entity-ops`

**目的**。K7 / K11 两类实体级操作（合并 / 拆分）不适合放在审核列表里做，需要独立的、低频但高风险的页面。

**IA**:

两个 Tab：

#### 7.1 Merge (合并重复实体)

- 选择源实体 + 目标实体（通过搜索）
- 系统显示 "影响预览"：
  - 源品牌的 aliases 将迁移到目标（列出）
  - 源品牌的 relations 将合并到目标（冲突处理：取 max confidence）
  - 源品牌对应的 Response mention 历史将指向目标（`mention_log.brand_id` 批量 update）
  - 源品牌对应的 Projects 将自动跟随目标（user-facing 通知）
- "模拟执行"（dry run）→ 返回预估修改行数
- "执行合并" → 写 `entity_merge_log` + 批量更新；支持 30 天内回滚

#### 7.2 Split (拆分混淆实体)

- 选择一个实体 → 进入 "拆分向导"：
  - 选择 aliases 划归新实体（checkbox）
  - 选择 relations 划归新实体
  - 选择 mention 历史如何划分（按 evidence_context 关键词规则 / 按时间段 / 手工标注）
- 拆分预览 + 执行；比 merge 更谨慎，强制 30 min 冷却期（防误操作）

**新增数据模型**:

```sql
CREATE TABLE entity_merge_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  op_type TEXT NOT NULL,              -- merge | split
  source_entity_id UUID NOT NULL,
  target_entity_id UUID,              -- merge: target; split: 新实体 id
  entity_type TEXT NOT NULL,          -- brand | product
  diff_summary JSONB NOT NULL,        -- {aliases_moved:12, relations_merged:8, mentions_rewritten:4200}
  dry_run BOOLEAN DEFAULT FALSE,
  operator_id UUID NOT NULL REFERENCES admin_users(id),
  reason TEXT NOT NULL,
  executed_at TIMESTAMPTZ,
  rolled_back_at TIMESTAMPTZ,
  rollback_reason TEXT,
  snapshot JSONB NOT NULL              -- 回滚所需的完整原状快照
);
```

**边界**:
- merge / split 影响 ≥ 10k mention 记录时，强制分批（每批 1k），页面显示进度条；不允许阻塞 UI 线程
- split 必须在 merge 冷却期外才能执行（同一品牌 30 天内 merge 后不能立即 split，否则 confirm 强警告）

**权限与审计**: super_admin + 理由 + 审计；**merge/split 操作是 §B10 变更审批中心的强制走流操作**（即使 solo 模式也要 dry-run 通过）。

**验收**: 构造 brand A (12 aliases) + brand B (8 aliases) → dry-run 返回预估 → apply → 验证 aliases 迁移 + mention_log 重写 + 历史 snapshot 保留 → rollback → 还原。

---

### C8. ★ KG Diff Viewer `/admin/kg/diff`

**目的**。"今天图谱比昨天多/少了什么" — 运营日常的审计与理解工具；也用于周报的数据源。

**IA**:
- 日期选择器（默认 today）
- 对比基准：`昨日同时刻 | 本周一 | 上周同期 | 自定义`
- 主视图 tab：
  - **实体增减**: brand / product / category 的新增 / 下架 / 修改列表
  - **关系增减**: 新增的 relations / 删除的 relations / confidence 大幅变动的 relations (> ±0.3)
  - **别名增减**: 按品牌聚合
- 每条变动都有指向对应 audit_log 的 "查看操作" 链接
- 顶部 KPI: "净新增" 数 / 最活跃 reviewer / 最多变动的行业

**关键实现点**:
- 这不是新数据 — 依赖 `kg_daily_snapshot` 离线 job（每日凌晨 3:00 对所有 kg_* 表做 checksum + 快照），Diff Viewer 按 snapshot 对比生成
- 快照只保留最近 90 天（> 90 自动归档到 S3）

**新增表**:

```sql
CREATE TABLE kg_daily_snapshot (
  snapshot_date DATE PRIMARY KEY,
  brand_count INT NOT NULL,
  brand_active_count INT,
  product_count INT NOT NULL,
  category_count INT NOT NULL,
  alias_count INT NOT NULL,
  relation_count INT NOT NULL,
  -- hash 用来快速 diff
  brands_checksum TEXT,
  products_checksum TEXT,
  relations_checksum TEXT,
  full_dump_s3_key TEXT,              -- 完整快照落 S3
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE kg_daily_diff_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_date DATE NOT NULL,
  to_date DATE NOT NULL,
  diff_summary JSONB NOT NULL,
  computed_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(from_date, to_date)
);
```

**权限与审计**: 只读页面；每次生成 diff 不写审计；导出 diff 报告（CSV / MD）需 super_admin。

**验收**: 跑两天快照差 → 构造 5 条增 + 3 条删 + 2 条改 → diff viewer 应正确列出 10 条 + 每条 link 能打开 audit log。

---

### C9. ★ KG Quality Monitor `/admin/kg/quality`

**目的**。持续回答："图谱可信度现在如何？哪儿是薄弱点？"

**IA**（整页由 ≤ 6 个质量 KPI 卡片 + 明细表组成）:

1. **整体可信度**（以 0-100 打分，加权合成）
   - discovery 幻觉率（负向）
   - alias 冲突数（负向）
   - 关系 confidence 中位数（正向）
   - 孤立节点率（负向）
   - review SLA 达成率（正向）

2. **孤立节点**（orphan detection）
   - 无任何 mention_log 的 active 品牌（30 天）
   - 无任何关系边的 active 品牌
   - 品类下 product = 0 的活跃 category
   - 表格列出 + 可操作 "标 deprecated / 触发 LLM 补全"

3. **三角不封闭**（relation triangle closure）
   - A COMPETES_WITH B, B COMPETES_WITH C, 但 A 没有 C 的关系 — 可能缺失边
   - 表格列出候选 + "加入关系挖掘队列" 批量操作

4. **别名碰撞率**
   - alias_value 被 ≥ 2 品牌认领的比例
   - 按行业分层显示

5. **提交质量**（来自 §C5 trust_score）
   - 近 7d reject 率 / spam 率 / 来自 blocked 用户的尝试数

6. **Discovery 源头质量**（按 LLM model / engine 分）
   - 每源头的 discovery approved 率 / hallucination 率

**关键实现点**:
- 所有指标通过 **离线 daily job** 计算，写入 `kg_quality_metrics` 表，Monitor 页面只读
- 重跑按钮（super_admin）可手动触发刷新（审计 + 花费 LLM 成本）

**新增表**:

```sql
CREATE TABLE kg_quality_metrics (
  snapshot_date DATE PRIMARY KEY,
  overall_score NUMERIC NOT NULL,      -- 0-100
  hallucination_rate NUMERIC,
  alias_conflict_count INT,
  orphan_brand_count INT,
  triangle_closure_gap INT,
  relation_confidence_median NUMERIC,
  submission_reject_rate_7d NUMERIC,
  computed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE kg_orphan_list (
  id BIGSERIAL PRIMARY KEY,
  snapshot_date DATE NOT NULL,
  entity_type TEXT NOT NULL,            -- brand | category | product_line
  entity_id UUID NOT NULL,
  orphan_reason TEXT NOT NULL,          -- no_mention | no_relation | no_product
  first_detected_at DATE NOT NULL,
  resolved_at DATE,
  UNIQUE(snapshot_date, entity_type, entity_id, orphan_reason)
);
```

**权限与审计**: 只读页面；手动触发刷新 → super_admin + 审计；针对 orphan 的批量操作 → 走 C2/C3 审核流。

**验收**: 造 3 个 orphan 品牌 + 2 个 alias 冲突 → job 跑一次 → overall_score < 80 + KPI 卡片正确显示；手动 resolve 后应从 orphan_list 移除。

---

## 4. 模块级横切

### 4.1 LLM 使用约束

- 所有 KG 相关 LLM 调用（discovery / 幻觉复核 / 子品类补全 / brand submission 预验证）统一走 `services/kg/llm_gateway.ts`
- 所有调用带 `llm_cost_attribution` 字段，计入 Cost 面板（D 模块）的 "KG 运营" 类别
- 预算上限硬约束 `daily_kg_llm_budget`，超限自动停用 discovery；Quality Monitor 页面显示 "今日 LLM 预算剩余"

**预算上报**: KG LLM 调用的成本记入 `cost_events` 表，`budget_scope = 'kg'`（与 Pipeline 的 `budget_scope = 'pipeline'` 区分）。两者各自硬约束，独立告警。详见 DATA_MODEL.md `cost_events` 表定义。

### 4.2 KG 修改的事务性保证

所有**跨表操作**（merge / split / 别名迁移 / 关系级联）必须在 DB 事务内；任何一步失败整体回滚。使用 Prisma `$transaction` + 配合 `entity_merge_log.snapshot` 兜底。

### 4.3 与 App 数据层的关系

Admin 可**全写**所有 `kg_*` 表；但**不可**直接修改:

- `mention_log` 的 brand_id / product_id（只有 merge/split 工具在事务内修改）
- `user_projects.primary_brand_id`（完全由用户控制）
- `ai_responses.raw_text`（事实性数据不可篡改）

### 4.4 UI / Prompt 边界

C2/C3/C4 页面 **不**写 "本页不做...详情请进入..." 这类内部约束文字。改为：

- 在品牌审核抽屉底部放 "如需拆分此品牌 → Entity Ops" 的 **链接按钮**（带图标），不是文字说明
- 在 Quality Monitor orphan 列表点击 orphan 直接跳对应审核页

---

## 5. API 契约

全部位于 `/admin/api/v1/kg/*`：

```
GET    /admin/api/v1/kg/industries                           ?status=
POST   /admin/api/v1/kg/categories                           { parent_id, name_zh, name_en }
POST   /admin/api/v1/kg/categories/:id/actions               { action: 'rename'|'move'|'deprecate'|'llm_expand', reason, params }

GET    /admin/api/v1/kg/brands                               ?status=&industry=&cursor=
GET    /admin/api/v1/kg/brands/:id
POST   /admin/api/v1/kg/brands                               { ... } // 手动创建
POST   /admin/api/v1/kg/brands/:id/actions                   { action:'approve'|'reject'|'merge'|'inactive', reason, merge_target_id? }
POST   /admin/api/v1/kg/brands/:id/aliases                   { alias_value, language, source }
DELETE /admin/api/v1/kg/brand-aliases/:alias_id              { reason }

GET    /admin/api/v1/kg/products                             ?brand_id=&status=
POST   /admin/api/v1/kg/products/:id/actions                 { action, reason }

GET    /admin/api/v1/kg/aliases/conflicts                    ?status=
POST   /admin/api/v1/kg/aliases/conflicts/:id/resolve        { decision: 'resolved_to_brand'|'split_new'|'shared'|'ignore', target_id?, reason }

GET    /admin/api/v1/kg/relations                            ?confidence_lt=&confidence_gt=&type=
POST   /admin/api/v1/kg/relations/:id/actions                { action:'set_confidence'|'change_type'|'delete', params, reason }

GET    /admin/api/v1/kg/brand-submissions                    ?status=&tier=&sla_breach=
POST   /admin/api/v1/kg/brand-submissions/:id/actions        { action:'approve'|'reject'|'merge', reason, merge_target_id? }
POST   /admin/api/v1/kg/brand-submissions/:id/spam           { reason }

GET    /admin/api/v1/kg/discovery                            ?engine=&from=&hallucination_suspected=
POST   /admin/api/v1/kg/discovery/:id/verify-hallucination

GET    /admin/api/v1/kg/entity-ops/preview                   ?op=merge|split&source_id=&target_id=
POST   /admin/api/v1/kg/entity-ops/merge                     { source_id, target_id, reason, dry_run }
POST   /admin/api/v1/kg/entity-ops/split                     { source_id, split_plan, reason, dry_run }
POST   /admin/api/v1/kg/entity-ops/:id/rollback              { reason }

GET    /admin/api/v1/kg/diff                                 ?from=&to=
POST   /admin/api/v1/kg/diff/export                          ?format=csv|md

GET    /admin/api/v1/kg/quality/metrics                      ?date=
POST   /admin/api/v1/kg/quality/refresh
GET    /admin/api/v1/kg/quality/orphans                      ?type=
```

---

## 6. 观测与告警

| Rule ID | 条件 | 等级 | 路由 |
|---|---|---|---|
| KG-01 | Brand submission 超 24h SLA | P1 | Inbox |
| KG-02 | Pending brand > 200 | P2 | Inbox |
| KG-03 | Discovery 幻觉率 7d > 15% | P1 | Inbox |
| KG-04 | Alias 冲突未处理 > 7d | P2 | Inbox |
| KG-05 | Orphan brand 数 > 50 | P2 | Inbox |
| KG-06 | 单个用户 spam 提交 ≥ 5 次/天 | P2 | Inbox |
| KG-07 | KG quality overall_score < 80 | P2 | Inbox |
| KG-08 | entity merge/split 执行耗时 > 5min | P1 | Inbox |
| KG-09 | KG daily snapshot job 失败 | P1 | Pager |
| KG-10 | LLM KG 预算触顶 | P2 | Inbox |

---

## 7. Session 延伸

| Session | 交付 | 工时估算 (AI / human) |
|---|---|---|
| **A3**（不变） | C1-C6（原 6 页）+ kg_review_queue / alias_conflicts 数据表 | 10h / 3h |
| **A3.1**（新增） | C7 Entity Merger/Splitter + entity_merge_log + 事务保证 | 6h / 2h |
| **A3.2**（新增） | C8 KG Diff Viewer + kg_daily_snapshot job + diff cache | 4h / 1.5h |
| **A3.3**（新增） | C9 KG Quality Monitor + kg_quality_metrics job + orphan detection | 5h / 2h |

Phase Gate：A-Gate 3 在 A3 跑完后触发；A-Gate 3a 在 A3.1-A3.3 都完成后触发（验 KG 模块一体化）。

---

## 8. Open Questions

| # | 问题 | 影响 | 默认取舍 |
|---|---|---|---|
| Q1 | 用户共建品牌通过后是否立即加入 Topic 生成？ | 数据质量 vs 立即可见性 | 默认加入但标 new，7 天后才参与 SoV 计算 |
| Q2 | Trust score 是否允许用户看到？ | 激励 vs 隐形 | MVP 不展示给用户；Phase 2 可选开放 |
| Q3 | Entity merge 是否允许跨行业？ | 灵活性 vs 误操作 | 允许但 warning 强确认 |
| Q4 | 关系 confidence 的衰减策略？ | 旧证据是否过期 | 默认线性衰减 90 天窗口；可由 Quality Monitor 触发 recalc |
| Q5 | KG 导出给数据报告业务（商业盈利）是否放在 Admin？ | 业务 vs 运营分离 | MVP 放 Admin（solo 操作），Phase 2 拆到独立商务后台 |
| Q6 | 用户可以 "认领" 自己品牌的修改权限吗？ | UGC 质量 vs 自主 | MVP 不开放（管控风险），Phase 2 做有限制的认领 |

---

## 附录 — 与 ADMIN_PRD.md §4.3 的差分

| §4.3 原文 | 本文深化后 |
|---|---|
| 6 个子页 | 9 个（新增 C7-C9） |
| 数据模型仅 2 张表 | + kg_brand_aliases / kg_brand_relation_history / kg_product_lines / submission_trust_score / discovery_feedback_negatives / entity_merge_log / kg_daily_snapshot / kg_daily_diff_cache / kg_quality_metrics / kg_orphan_list |
| 无实体合并/拆分 | C7 + entity_merge_log + 事务保证 |
| 无 KG 版本对比 | C8 Diff Viewer + daily snapshot job |
| 无整体质量监测 | C9 Quality Monitor + 6 质量维度 |
| LLM 调用无预算 | §4.1 `daily_kg_llm_budget` + 超限停用 |
| Trust score 缺失 | §C5 submission_trust_score + 4 tier 分级 |

更新 ADMIN_PRD.md §4.3 opener，加一行指向本文：

> **⚠️ §4.3 为摘要。详细实现（包含 Entity Merger/Splitter、KG Diff Viewer、KG Quality Monitor 3 个延伸子页，以及 Trust Score、Hallucination Detection、Daily Snapshot 三个横切机制）见 [`ADMIN_PRD_C_KG.md`](./ADMIN_PRD_C_KG.md)。**
