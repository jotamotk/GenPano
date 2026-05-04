# PRD Addendum — Phase P 契约固化

> 日期：2026-05-04
> 范围：基于 `docs/APP_BACKEND_PLAN.md` Phase P，补全 `docs/PRD.md` §4.5.2、§4.7、§4.8 中已开题但缺**字段级 schema / 端点契约 / 状态机** 的部分。
> 本文是 PRD 的增量章节，最终应合入 `docs/PRD.md`。
> 配套：`docs/DATA_MODEL.md`（数据模型）、`docs/openapi.yaml`（端点契约）、`docs/ADR/`（决策记录）。

---

## §4.5.2 MCP Server 完整契约（重写）

### 4.5.2.1 鉴权

- **协议**：Bearer API Key（不上 OAuth）。
- **生成**：`POST /v1/users/me/api-keys` 由用户在 `/settings/api-keys` 自助生成。
- **格式**：`gp_sk_<32 字符 base62>` — 前缀 `gp_sk_` 用于识别，明文仅在创建响应中返回一次。
- **存储**：`user_api_keys.hash`（bcrypt cost 12）。
- **未带 token / 失效 / 已撤销**：返回 `401` + `application/problem+json` `{ "code": "MCP_AUTH_REQUIRED" }`。
- **越权**（key 持有者无目标 project 访问权）：`403` + `code=FORBIDDEN`。
- **限速**：60 req/min/key（默认），可在 `user_api_keys.rate_limit_per_minute` 调整；超限 `429` + `Retry-After` 头。

### 4.5.2.2 Tools 契约

| Tool | Input Schema | Output Schema |
| --- | --- | --- |
| `genpano_get_brand_visibility` | `{brand_id, project_id, engine?, period? ('7d'|'30d'|'90d', 默认 '30d')}` | `{mention_rate, sov, position_rank, geo_score, period: {from, to}, time_series: [{date, mention_rate, sov, rank}]}` |
| `genpano_compare_brands` | `{project_id, brand_ids: string[2..5], metrics: ('mention_rate'|'sov'|'sentiment'|'citation_share'|'geo_score')[], period?}` | `{brands: [{brand_id, name, metrics: {<key>: number}}], period: {from, to}}` |
| `genpano_get_industry_trends` | `{industry_id, period?}` | `{industry, total_brands, top_brands: [{brand_id, name, geo_score, rank}], avg_mention_rate, avg_sentiment, time_series}` |
| `genpano_get_product_ranking` | `{project_id, product_id?, category?}` | `{products: [{product_id, name, brand_id, category_rank, win_rate, top_features, top_scenarios}]}` |
| `genpano_generate_report` | `{project_id, report_type ('weekly'\|'monthly'\|'on_demand'), format ('markdown'\|'json'\|'pdf'), period?, locale? ('zh-CN'\|'en-US')}` | `{report_id, status: 'queued'\|'done', download_url?: string, sections: [...]}` （sync 等结果或返 job_id 异步）|
| `genpano_get_optimization_insights` | `{project_id, brand_id, severity? (P0\|P1\|P2\|P3)}` | `{diagnostics: [{id, category, severity, title, evidence, direction, anchor_questions}]}` |
| `genpano_get_citations` | `{brand_id, range? {start, end}, tier? number[], method? string[], page?, page_size? (≤500)}` | `{items: [{citation_id, url, domain, title, source_type, tier, attribution_method, page_type, occurred_at}], cursor?, total}` |
| `genpano_list_pr_targets` | `{brand_id, top? (≤200, 默认 50), exclude_covered? (默认 true)}` | `{targets: [{domain, tier, confidence, competitors_count, attributed_to_me_count, trending_30d_pct, site_type, same_group_shared, pr_score}]}` |
| `genpano_simulate_authority_boost` | `{brand_id, delta_by_tier: {1: int, 2: int, 3: int, 4: int}, confidence_override? (0.5..1.0)}` | `{current_pano_a, simulated_pano_a, delta, base_price_equivalent_cny}` |

### 4.5.2.3 Resources 契约

| URI | 内容 |
| --- | --- |
| `genpano://projects/{id}/dashboard` | Project 主品牌全景（KPI + Top diagnostics + 同集团共享 + 30d 趋势） |
| `genpano://brands/{id}/report` | 品牌完整 profile（基础 meta + 最近一份月度报告 markdown） |
| `genpano://industry/{name}/benchmark` | 行业基准（top 10 brands + 行业均值 + 30d 趋势） |

### 4.5.2.4 Scope 模型

`user_api_keys.scope` JSONB：

```json
{
  "tools": ["*"],                                    // 或具体 tool 名数组
  "resources": ["*"],
  "projects": ["*"],                                 // 或具体 project_id 数组
  "rate_limit_per_minute": 60,
  "expires_at": null                                  // ISO8601 或 null（不过期）
}
```

### 4.5.2.5 Usage Stats

`GET /v1/users/me/api-keys/:id/usage?from=&to=&group_by=tool|day` 返回：

```json
{
  "total_calls": 1234,
  "by_tool": [{"tool": "genpano_get_brand_visibility", "count": 800, "avg_latency_ms": 120, "error_rate": 0.01}],
  "by_day": [{"date": "2026-05-01", "count": 45, "cost_estimate_cny": 0.12}]
}
```

### 4.5.2.6 错误码

| HTTP | code | 触发 |
| --- | --- | --- |
| 401 | `MCP_AUTH_REQUIRED` | 无 / 失效 / 撤销 token |
| 403 | `FORBIDDEN` | key 无目标 project / brand 访问权 |
| 404 | `NOT_FOUND` | 资源不存在（不区分"不存在"vs"无权限"防泄露） |
| 422 | `PARAMS_INVALID` | 参数 schema 校验失败 |
| 429 | `RATE_LIMIT_EXCEEDED` | 超 `rate_limit_per_minute`，返 `Retry-After` |
| 500 | `INTERNAL_ERROR` | 服务端异常（不暴露细节） |
| 503 | `SERVICE_DEGRADED` | 上游 LLM 不可用，降级返部分数据 |

---

## §4.7.1 Diagnostic 数据结构（新）

完整字段表，与 `frontend/src/data/mock.js` 中 `DIAGNOSTICS` 常量 1:1 对齐。

```typescript
interface Diagnostic {
  id: string;                                  // diag-xxx
  project_id: string;                          // UUID
  brand_id: number | null;
  product_id: number | null;
  industry_id: number | null;
  category: DiagnosticCategory;                // 见 §4.7.1.1
  severity: 'P0' | 'P1' | 'P2' | 'P3';
  type: 'brand' | 'product' | 'industry';
  title: string;                               // 一句话总结
  description: string;                         // Layer 1 observation 主文本

  // Header meta
  engine: string | null;                       // 'ChatGPT' | 'DoubleBean' | 'DeepSeek' | null（跨引擎）
  detected_at: string;                         // ISO 8601
  focus_area: string;                          // "熬夜急救主题内容丢失"
  direction: string;                           // 方向性建议（不是 playbook 步骤）

  // Reader Layer
  reader_hints: ('operator' | 'manager' | 'branding')[];

  // Layer 1 — Observation
  evidence: {
    metric: string;                            // 'sov' | 'mention_rate' | 'sentiment_score' | 'citation_share' | …
    current_value: number;
    previous_value: number;
    change_percent: number;
    time_range: string;                        // "2026-03-23 → 2026-04-13"
    affected_queries: string[];
    affected_engines: string[];
    response_samples?: string[];               // response_id 列表
    citation_attribution_mismatch?: {          // 仅 category='citation_attribution_mismatch'
      window_start: string;
      window_end: string;
      by_method: {
        official_domain: { count: number; pct: number };
        co_occurrence: { count: number; pct: number };
        text_match: { count: number; pct: number };
      };
      possible_causes: string[];
      pano_a_shortfall: number;
    };
  };

  // Layer 2 — Explanation
  causal_chain: {
    trigger_metrics: string[];
    hypothesized_mechanism: string;
    supporting_evidence: string[];             // response_id 列表
    confidence_level: 'high' | 'medium' | 'low';
    alternative_hypotheses: string[];
  };
  industry_benchmark: {
    metric: string;
    my_value: number;
    industry_median: number;
    industry_top10_avg: number;
    top_competitor: {
      brand_id: number;
      brand_name: string;
      value: number;
    };
  };
  time_series: { date: string; value: number }[]; // 30d 趋势

  // Layer 3 — Direction
  anchor_questions: {
    operator: string[];
    manager: string[];
    branding: string[];
  };
  if_untreated: string;                        // "若不处理 4 周后预期..."
  decision_prompt: string;                     // "是否在下 4 周启动..."

  // State
  status: 'open' | 'acknowledged' | 'ignored' | 'resolved';
  acknowledged_at: string | null;
  acknowledged_by: number | null;
  resolved_at: string | null;
  resolved_by: number | null;

  // Linkage
  rule_id: string;                             // 'visibility_decline_v1'
  rule_version: string;                        // 'v1'
  alert_id: string | null;                     // P0/P1 自动创建的 alert
}
```

### 4.7.1.1 DiagnosticCategory 枚举

| category | 触发指标 | 默认 severity | reader_hints |
| --- | --- | --- | --- |
| `visibility_decline` | mention_rate / sov / position_rank | P1（≥30% 跌） / P2 | operator, manager |
| `sentiment_drop` | avg_sentiment / negative_rate | P1（≥20% 跌） / P2 | operator, branding |
| `citation_attribution_mismatch` | official_domain pct < 阈值 | P2 | operator, manager |
| `competitor_overtake` | competitor SoV/rank 反超 | P1 | manager, branding |
| `topic_loss` | 单 topic mention_rate 跌 | P1 / P2 | operator |
| `narrative_drift` | branding_narrative LLM diff | P2 | branding |
| `persona_keyword_change` | persona_keyword_frequency | P3 | branding |
| `negative_keyword_growth` | negative_keyword_frequency | P1 | operator, branding |
| `content_gap` | gap_ratio > 0.7 | P1 | operator |
| `pano_score_drop` | geo_score 30d 跌 ≥ 15% | P1 | manager |
| `citation_authority_low` | tier2 share < 10% | P2 | operator |
| `wiki_missing` | wiki page_type 缺 | P3 | branding |
| `product_feature_negative` | feature_negative_pct > 40% | P1 | operator |
| `product_remission` | 产品被竞品反超 | P1 | manager |
| `industry_lag_top10` | 行业 top10 距离 > 30% | P2 | manager |
| `same_group_share_low` | 共享域少于阈值 | P3 | branding |
| `monitoring_outage` | 24h 无新数据 | P0 | operator |
| `llm_engine_anomaly` | 单引擎数据归零 | P0 | operator |
| `geo_score_drop_severe` | geo_score 跌 ≥ 30% | P0 | manager |
| `competitor_radical_growth` | 竞品 30d +40%+ | P1 | branding |
| `share_of_voice_minor` | SoV < 5% 且新建 < 90d | P3 | manager |
| `attribution_anchor_low` | anchor_question 命中率 < 0.5 | P2 | branding |
| `citation_diversity_low` | distinct domain count < 5 | P3 | operator |
| `topic_emerging_missed` | 新兴 topic 未覆盖 | P2 | operator, manager |
| `category_rank_drop` | category_rank 30d 下滑 | P1 | manager |

**至少 25 条规则**。每条规则一个 `BaseRule` 子类，rule_id 形如 `visibility_decline_v1`。

### 4.7.1.2 严重度判定

```python
def severity_for(rule_id: str, evidence: dict) -> str:
    # 阈值梯度：每条规则自定义
    # 通用回退：
    change = abs(evidence.get('change_percent', 0))
    if change >= 30: return 'P1'
    if change >= 15: return 'P2'
    return 'P3'
```

### 4.7.1.3 Causal Chain LLM 缓存

- key: `(project_id, rule_id, brand_id, day)` → narrative
- TTL: 24h
- 缓存命中率目标 ≥ 70%
- 单 project 单日 LLM 调用上限 50 次

---

## §4.7.2 Reports SECTION_MATRIX 完整契约（新）

### 4.7.2.1 Report Type 枚举

| report_type | 触发 | 章节集 |
| --- | --- | --- |
| `weekly` | cron 每周一 / 用户手动 | 8 sections |
| `monthly` | cron 每月 1 号 / 用户手动 | 9 sections |
| `on_demand` | 用户即时生成 | 8 sections（含 product_competitiveness 可选） |
| `lead_diagnostic` | 用户提交 commercial_lead 后自动 | **不走 SECTION_MATRIX**，独立 4 layer view（Hero / Top 3 P0/P1 + 行业对比 / 一句方向 / Lead 顾问 CTA） |

### 4.7.2.2 SECTION_MATRIX

10 个 section_type × 3 variant × 3 reader × insight stack layer：

```python
SECTION_MATRIX = {
  'weekly': {
    'executive_summary':       {'variant': 'full',     'primary_reader': 'manager',  'layers': [1, 2]},
    'pano_score':              {'variant': 'simple',   'primary_reader': 'operator', 'layers': [1]},
    'industry_landscape':      {'variant': 'full',     'primary_reader': 'manager',  'layers': [1, 2]},
    'brand_performance':       {'variant': 'full',     'primary_reader': 'operator', 'layers': [1, 2]},
    'product_competitiveness': None,
    'competitor_comparison':   {'variant': 'simple',   'primary_reader': 'manager',  'layers': [1, 2]},
    'diagnostic_summary':      {'variant': 'p01_only', 'primary_reader': 'operator', 'layers': [1, 2, 3]},
    'anchor_actions':          {'variant': 'p01_only', 'primary_reader': 'operator', 'layers': [3]},
    'branding_narrative':      None,
    'cta':                     {'variant': 'full',     'primary_reader': 'manager',  'layers': [3]},
  },
  'monthly': { ... },     # 与 frontend SECTION_MATRIX 完全一致
  'on_demand': { ... },
  'lead_diagnostic': {'__use_lead_view': True},
}

SECTION_ORDER = [
  'executive_summary', 'pano_score', 'industry_landscape',
  'brand_performance', 'product_competitiveness', 'competitor_comparison',
  'diagnostic_summary', 'anchor_actions', 'branding_narrative', 'cta',
]
```

### 4.7.2.3 Section Output Schema

每个 section 输出固定结构：

```typescript
interface SectionData {
  type: SectionType;
  variant: 'full' | 'simple' | 'p01_only' | 'optional';
  primary_reader: 'operator' | 'manager' | 'branding';
  layers: (1 | 2 | 3)[];
  title_zh: string;
  title_en: string;
  narrative_zh: string;                         // LLM 生成的叙事段
  narrative_en: string;
  data: Record<string, any>;                    // section-specific 结构化数据
  charts?: Array<{
    type: 'line' | 'bar' | 'donut' | 'radar';
    title_zh: string; title_en: string;
    series: any[];
    annotations?: any[];
  }>;
  tables?: Array<{
    columns: string[];
    rows: any[][];
    caption_zh?: string; caption_en?: string;
  }>;
}
```

### 4.7.2.4 Narrative 生成

- 每段 80-200 字
- LLM 模型：豆包 / DeepSeek
- 缓存 key：`(report_type, section, period_id, brand_id, locale)`
- 失败 fallback：纯 i18n 模板（不带 LLM 润色）
- 单报告 LLM 调用上限：10 段 × 2 locale = 20 次

### 4.7.2.5 lead_diagnostic 独立 4 Layer View

```typescript
interface LeadDiagnosticReport {
  layer_1: {
    hero_one_liner: string;                    // "雅诗兰黛在 ChatGPT 美妆赛道排名 #4，距 Top 3 还差 8.2 PANO"
    kpi_cards: Array<{
      label_zh: string; label_en: string;
      value: number; unit?: string;
      delta_30d_pct: number;
    }>;
  };
  layer_2: {
    top_diagnostics: Diagnostic[];             // P0/P1 前 3 条
    industry_comparison: {
      my_rank: number; total_brands: number;
      top3_avg_geo_score: number;
      gap: number;
    };
  };
  layer_3: {
    direction_summary: string;                 // 一句话总结方向
  };
  layer_4: {
    consultant_cta: {
      title_zh: string; title_en: string;
      anchor_questions: string[];
      contact_form_url: string;                // 跳 LeadFormModal
    };
  };
}
```

### 4.7.2.6 Share Token

- `POST /v1/projects/:id/reports/:rid/share` → `{ token, expires_at, share_url }`
- 默认有效期 30 天
- `GET /reports/public/:token` 无 auth 公开访问；记 `view_count`；过期返 `410 Gone`
- `DELETE /v1/projects/:id/reports/:rid/share/:token` 撤销

### 4.7.2.7 调度

- `report_schedules.cron` 5 字段标准 cron（如 `0 8 * * 1` 周一 8AM）
- Celery beat 每 5 分钟扫 `next_run_at <= now() AND enabled = true`，enqueue + 更新 `next_run_at`
- 失败重试：3 次指数退避（1m / 5m / 15m），3 次后标 status='failed' + 触发 alert

---

## §4.7.3 Alerts + Notifications 完整契约（新）

### 4.7.3.1 Alert source 枚举

| source | 触发器 | 默认 severity | scope |
| --- | --- | --- | --- |
| `diagnostic` | Phase D evaluator 创建 P0/P1 时联动 | P0/P1 | user |
| `citation_attribution_mismatch` | A.3 attribution 写完后阈值检查 | P2 | user |
| `monitoring_outage` | 24h 无新 llm_responses 流入 | P1 | user + operator |
| `competitor_overtake` | A.7 competitor_aggregator 检测反超 | P1 | user (按 user.competitor_alert) |
| `engine_health` | O1.2 success_rate < 80% | P1 | operator |
| `cost_overrun` | O2.1 budget_scope 超阈值 | P0 | operator |
| `kg_quality` | KG quality 总分 < 80 | P2 | operator |
| `manual` | admin 手工触发 | 不限 | 任意 |
| `system` | 平台层（部署 / 升级通知） | 不限 | 任意 |

### 4.7.3.2 Notification Preference

```typescript
interface UserNotificationPreferences {
  user_id: number;
  p0p1_alerts: boolean;                        // 默认 true，对应 SettingsPage toggle 1
  weekly_report: boolean;                      // 默认 true，对应 toggle 2
  competitor_alert: boolean;                   // 默认 false，对应 toggle 3
  email_locale: 'zh-CN' | 'en-US';
  quiet_hours: {
    start: string;                             // 'HH:MM' 24h
    end: string;
    tz: string;                                // IANA tz, e.g. 'Asia/Shanghai'
  } | null;
  channels: ('email' | 'inapp')[];             // Phase 2 加 webhook
}
```

### 4.7.3.3 Alert 状态机

```
unread → read → resolved
unread → ignored (终态)
read → resolved (终态)
```

- Diagnostic resolve 时自动 resolve 其关联 alert
- `mark-all-read` 一键全部 unread → read（不进入 resolved）

### 4.7.3.4 Email 模板

```
backend/app/notifications/templates/
  alert_p0.{zh-CN,en-US}.html
  alert_p1.{zh-CN,en-US}.html
  weekly_digest.{zh-CN,en-US}.html
  competitor_overtake.{zh-CN,en-US}.html
  monitoring_outage.{zh-CN,en-US}.html
```

模板必须支持 quiet_hours 跳过、unsubscribe 链接、品牌一致样式。

---

## §4.7.4 Exports 完整契约（新）

### 4.7.4.1 ExportType 枚举

| export_type | 数据源 | 默认列 |
| --- | --- | --- |
| `mention_list` | brand_mentions JOIN llm_responses | response_id, brand, position_rank, sentiment, snippet, engine, occurred_at |
| `sentiment_list` | sentiment_drivers JOIN brand_mentions | mention_id, driver_text, polarity, category, strength, source_quote |
| `citation_list` | citation_sources | response_id, url, domain, title, source_type, tier, attribution_method, page_type |
| `competitor_matrix` | competitor_mention_daily | date, brand, competitor, co_mention_count, sentiment_diff, sov_diff |
| `topic_coverage` | topics JOIN prompts JOIN queries | topic, prompt, query, response_count, mention_rate |
| `industry_ranking` | industry_benchmark_daily | industry, date, brand, geo_score, mention_rate, rank |
| `products_list` | product_score_daily | brand, product, category, date, mention_rate, win_rate, geo_score |
| `report_data` | report_jobs.narrative_data | section, narrative_zh, narrative_en, data_json |

### 4.7.4.2 配额

- 每用户每天 ≤ 20 次 export（Free plan）
- 单次最大 100k 行（超过截断 + 提示）
- 超配额 `429` + `code=EXPORT_QUOTA_EXCEEDED` + 文案"今日已用 20/20，请明天再试"

### 4.7.4.3 文件名

`{project_slug}_{export_type}_{from}_{to}_{timestamp}.csv`

### 4.7.4.4 AuthPromptModal Hook

`auth.hook.export_csv` — 匿名用户点 CSV download icon → 弹 modal → 注册后 `?action=export_csv&exportType=mention_list&...` 自动触发。

---

## §4.7.5 Brand Submission 完整契约（新）

### 4.7.5.1 提交字段

```typescript
interface BrandSubmissionInput {
  proposed_name: string;                       // 必填
  proposed_industry_id: number | null;
  proposed_aliases: string[];                  // 别名列表
  proposed_official_domains: string[];
  notes: string;
  source_url?: string;                         // 用户提供的参考链接
}
```

### 4.7.5.2 状态机

```
pending → approved → ingested (写入 brands + kg_brands + 触发 K3 candidates)
pending → rejected (终态，记 rejection_reason)
pending → duplicate (合并到现有 brand_id)
```

### 4.7.5.3 admin 审核流

1. admin `/admin/kg/brand-submissions` 列表（默认 status=pending）
2. 点详情 → 与现有 brands 自动模糊匹配（编辑距离 ≤ 2 提示可能重复）
3. action：
   - approve → 入 brands + kg_brands + KG candidates 流程
   - reject → 记 rejection_reason
   - duplicate → 合并到 brand_id（更新提交人记录）
4. 触发 audit_decorator → admin_audit_log

### 4.7.5.4 提交 → 入库 端到端

- 用户 `/brands` 集市搜不到 → 点 "提交新品牌" CTA → modal 表单
- `POST /v1/brands/submissions` → `commercial_leads(source='brand_submission')` 也写一条
- 5 工作日内 admin 审核 → email 通知用户结果
- Approved → KG K3 candidates 流程 → 入 kg_brands + brand_id 反向更新提交记录

---

## §4.7.6 Simulator 完整契约（新）

### 4.7.6.1 公式

```
PANO_A = 0.4 × visibility + 0.2 × sov + 0.2 × sentiment + 0.2 × citation_authority

其中 citation_authority = Σ (tier_weight[t] × tier_count[t]) / total_citations
tier_weight = { 1: 1.0, 2: 0.7, 3: 0.4, 4: 0.1, 0: 0.0 }
```

模拟时仅改 `tier_count`，重算 `citation_authority` → 重算 `PANO_A`。

### 4.7.6.2 输入校验

```typescript
interface SimulatorInput {
  brand_id: number;
  delta_by_tier: { [tier: '1'|'2'|'3'|'4']: number };  // 不允许使 tier_count < 0
  confidence_override?: number;                          // [0.5, 1.0]
}
```

`delta` 上限：单 tier ≤ 现有 tier_count × 5（防止离谱模拟）。

### 4.7.6.3 行业参数表

新表 `industry_pricing_params`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| industry_id | INT PK | 行业 ID |
| tier1_unit_price_cny | NUMERIC | Tier 1 (官方域) 单条引用获取等价成本 |
| tier2_unit_price_cny | NUMERIC | Tier 2 (头部媒体) |
| tier3_unit_price_cny | NUMERIC | Tier 3 (KOL) |
| tier4_unit_price_cny | NUMERIC | Tier 4 (UGC) |
| updated_at | TIMESTAMPTZ | 最后维护时间 |

`base_price_equivalent_cny = Σ delta_by_tier[t] × industry_pricing_params.tier{t}_unit_price_cny`

admin `/admin/industry-pricing-params` 维护，初始 4 行业种子。

### 4.7.6.4 输出

```json
{
  "current_pano_a": 78.5,
  "simulated_pano_a": 84.2,
  "delta": 5.7,
  "delta_breakdown": {
    "visibility": 0,
    "sov": 0,
    "sentiment": 0,
    "citation_authority": 5.7
  },
  "base_price_equivalent_cny": 124000,
  "confidence": 0.82
}
```

### 4.7.6.5 与 MCP Tool 共享

`POST /v1/projects/:id/simulator/run`（REST）与 `genpano_simulate_authority_boost`（MCP）共享同一个 `backend/app/simulator/authority_boost.py` service 函数；输出**字节级**一致（除 metadata）。

---

## §4.8 Diagnostics 完整规则集（新）

详见 §4.7.1.1 25 条 category 列表。每条规则在 `backend/app/diagnostics/rules/<rule_name>.py` 实现，结构统一：

```python
class VisibilityDecline(BaseRule):
    rule_id = 'visibility_decline_v1'
    category = 'visibility_decline'
    triggers_on = ['mention_rate', 'sov']
    default_severity_table = {                          # change_percent 阈值
      30.0: 'P1',
      15.0: 'P2',
       5.0: 'P3',
    }
    cooldown_days = 7                                    # 同 (project, brand, category) 7 天内不重复触发

    def evaluate(self, context: RuleContext) -> list[DiagnosticPayload]:
        ...
```

### 4.8.1 规则注册流程

1. 新 rule 文件 → import 到 `backend/app/diagnostics/rules/__init__.py` REGISTRY
2. CI 跑 `test_rules_complete.py` 校验：每 category 至少 1 个 rule
3. 写 ≥ 3 个金标 case（happy / 不触发 / 边界）

### 4.8.2 evaluator 执行流

```
backend/app/diagnostics/evaluator.py
  ↓ 接收 project_id（每日 cron 或手动 refresh）
  ↓ 加载所有 enabled rule
  ↓ 构造 RuleContext（拉 30 天 geo_score_daily / response_analyses / citation_sources / sentiment_drivers）
  ↓ 对每条 rule 调 evaluate()
  ↓ 去重（cooldown_days）+ 升级（severity 升）+ UPSERT diagnostics
  ↓ 触发 P0/P1 → alerts_service.create_from_diagnostic(diag)
  ↓ LLM 异步生成 causal_chain（缓存命中跳过）
```

---

## 附录 — 与 plan 文档关系

- 本文档 §4.5.2 / §4.7.1 / §4.7.2 / §4.7.3 / §4.7.4 / §4.7.5 / §4.7.6 / §4.8 对应 `docs/APP_BACKEND_PLAN.md` 中 Phase M / D / RP / N / E。
- 数据模型详见 `docs/DATA_MODEL.md`。
- 端点详见 `docs/openapi.yaml`。
- 决策依据详见 `docs/ADR/`。

---

*本 addendum 在 Phase P 完成时合入 `docs/PRD.md`，按 §4.x 锚点替换 / 补充。*
