# ADMIN_PRD Addendum — Phase P 契约固化

> 日期：2026-05-04
> 范围：基于 `docs/APP_BACKEND_PLAN.md` Phase O，补全 `docs/ADMIN_PRD.md` §4.2 + §4.3 + §4.4 + §5 中已开题但缺**字段级 schema / 端点契约 / 状态机** 的部分。
> 本文是 ADMIN_PRD 的增量章节。

---

## §4.2.1 Pipeline 全景 `/admin/pipeline/overview`

### 数据来源

JOIN：`query_executions` × `attempts` × `llm_responses` × `response_analyses`。

### 端点契约

| Method | Path | Resp |
| --- | --- | --- |
| GET | `/api/admin/pipeline/overview?from=&to=&engine=` | `{ funnel: { queries: int, attempts: int, responses: int, analyses: int }, success_rate, avg_duration_min, anomaly_rate, engine_distribution: [{engine, count, pct}], top_failures: [{error_code, count}] }` |

### KPI 卡

- 今日总查询 / 完成率 / 平均延迟 / 失败堆积 4 张

---

## §4.2.2 引擎健康 `/admin/pipeline/engines`

### 新表

```sql
CREATE TABLE engine_health_daily (
  id SERIAL PRIMARY KEY,
  engine VARCHAR(64) NOT NULL,
  date DATE NOT NULL,
  total_attempts INT DEFAULT 0,
  success_count INT DEFAULT 0,
  failed_count INT DEFAULT 0,
  success_rate FLOAT DEFAULT 0,
  p50_latency_ms INT,
  p95_latency_ms INT,
  cookie_status VARCHAR(16),                 -- 'healthy' | 'expiring' | 'expired'
  captcha_count INT DEFAULT 0,
  ip_blocked_count INT DEFAULT 0,
  rate_limited_count INT DEFAULT 0,
  last_updated TIMESTAMPTZ DEFAULT now(),
  UNIQUE (engine, date)
);
CREATE INDEX ON engine_health_daily (engine, date DESC);
```

### Celery 聚合

`engine_health.aggregate()` 每小时跑一次，扫上一小时 `attempts` 表聚合到当日行（UPSERT）。

### 告警

`success_rate < 80%`（持续 1h）→ 触发 `engine_health` alert（P1, scope=operator）。

### 端点

| Method | Path | Resp |
| --- | --- | --- |
| GET | `/api/admin/pipeline/engines?engine=&from=&to=` | `{ engines: [{engine, latest: {success_rate, p50_latency_ms, cookie_status}, history_30d: [...]}] }` |
| POST | `/api/admin/pipeline/engines/:engine/recheck` | 手动触发健康检查 |

---

## §4.2.6 失败重试中心 `/admin/pipeline/retry-center`

### 数据视图

```sql
SELECT q.id, q.brand_id, q.target_llm, q.created_at,
       a.attempt_no, a.error_code, a.error_message,
       a.created_at AS last_attempted_at
FROM query_executions q
LEFT JOIN attempts a ON a.query_id = q.id
WHERE q.status = 'failed'
ORDER BY q.created_at DESC;
```

### 失败原因分类

枚举 `attempts.error_code`：

| code | 说明 | 默认重试策略 |
| --- | --- | --- |
| `timeout` | 请求超时 | 自动 3 次指数退避 |
| `captcha` | 触发验证码 | 切换 IP + 等待 30min 后重试 |
| `rate_limit` | 平台限速 | 切换 account + 退避 1h |
| `parse_error` | 响应解析失败 | manual review |
| `account_blocked` | 账号被封 | manual：disable + 切换 |
| `network_error` | 网络故障 | 自动 1 次重试 |
| `unknown` | 兜底 | manual review |

### 端点

| Method | Path | Action |
| --- | --- | --- |
| GET | `/api/admin/pipeline/retry-center?error_code=&adapter=&from=&to=&cursor=` | 列表 |
| GET | `/api/admin/pipeline/retry-center/:query_id` | 详情 + artifacts (HTML / screenshot 引用) |
| POST | `/api/admin/pipeline/retry-center/:query_id/retry` | 单条重试 |
| POST | `/api/admin/pipeline/retry-center/batch-retry` | 批量重试 `{query_ids: [...]}` |
| POST | `/api/admin/pipeline/retry-center/:query_id/mark-failed-permanent` | 终态标记 |

每次 mutation 经 audit_decorator → admin_audit_log。

---

## §4.3.6 KG Discovery Logs `/admin/kg/discovery-logs`

### 新表

```sql
CREATE TABLE discovery_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source VARCHAR(32),                         -- 'relation_extractor' | 'brand_detector' | 'category_classifier'
  candidate_id UUID,                          -- kg_relation_candidates.id 等
  llm_model VARCHAR(64),
  confidence FLOAT,
  hallucination_flag BOOLEAN DEFAULT FALSE,
  hallucination_evidence JSONB,
  occurred_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON discovery_log (source, occurred_at DESC);
CREATE INDEX ON discovery_log (hallucination_flag, occurred_at DESC);
```

### 幻觉率定义

```
hallucination_rate(period) = COUNT(hallucination_flag = true) / COUNT(*)
```

7d 幻觉率 > 15% → KG quality monitor (§C9) 标红 + 触发 P1 alert (scope=operator)。

### 端点

| Method | Path | Resp |
| --- | --- | --- |
| GET | `/api/admin/kg/discovery-logs?source=&hallucination=&from=&to=&cursor=` | 列表 |
| POST | `/api/admin/kg/discovery-logs/:id/mark-hallucination` | 标记幻觉 |
| GET | `/api/admin/kg/discovery-logs/stats?period=7d|30d` | `{total_count, hallucination_count, rate, by_source: [...]}` |

---

## §4.4.1 成本看板 `/admin/cost/daily`

### 新表

```sql
CREATE TABLE cost_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope VARCHAR(16) NOT NULL,                 -- 'pipeline' | 'kg' | 'mcp' | 'reports'
  amount NUMERIC(10,4) NOT NULL,              -- CNY
  source VARCHAR(64) NOT NULL,                -- 'doubao_analyzer' | 'deepseek_relation_extractor' | 'openai_narrative' | ...
  event_type VARCHAR(32) NOT NULL,            -- 'llm_call' | 'storage' | 'compute' | 'bandwidth'
  reference_id VARCHAR(64),                   -- response_id / report_id / etc.
  metadata JSONB,                              -- {tokens_in, tokens_out, model, ...}
  occurred_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON cost_events (scope, occurred_at DESC);
CREATE INDEX ON cost_events (source, occurred_at DESC);
```

### 写入点矩阵

| Scope | Source | 触发位置 | 估值方式 |
| --- | --- | --- | --- |
| pipeline | `doubao_analyzer` | `geo_tracker/analyzer/llm_analyzer.py` 每次调用 | tokens × 单价 |
| pipeline | `deepseek_analyzer` | 同上（其他 adapter） | tokens × 单价 |
| pipeline (sub: diagnostics) | `doubao_causal_chain` | `backend/app/diagnostics/causal_llm.py` | tokens × 单价 |
| pipeline (sub: reports) | `doubao_narrative` | `backend/app/reports/narratives.py` | tokens × 单价 |
| kg | `relation_extractor_llm` | `geo_tracker/analyzer/relation_extractor.py` | tokens × 单价 |
| mcp | `mcp_tool_call` | MCP middleware 每次调用 | 估算（基于 tool 平均 tokens） |
| reports | `weasyprint_render` | `backend/app/reports/renderers/pdf.py` | 计算时间秒数 × 单价 |

### Budget Scope 预算硬约束

```sql
CREATE TABLE budget_thresholds (
  scope VARCHAR(16) PRIMARY KEY,
  daily_limit_cny NUMERIC(10,2),
  weekly_limit_cny NUMERIC(10,2),
  monthly_limit_cny NUMERIC(10,2),
  alert_at_pct INT DEFAULT 80,               -- 80% 时 P1 alert
  hard_stop_at_pct INT DEFAULT 100,          -- 100% 时禁用对应功能
  updated_at TIMESTAMPTZ
);
```

### 端点

| Method | Path | Resp |
| --- | --- | --- |
| GET | `/api/admin/cost/daily?scope=&from=&to=` | `{daily: [...], by_scope: [...], total_cny, vs_budget_pct}` |
| GET | `/api/admin/cost/breakdown?scope=&group_by=source\|date` | 钻取明细 |
| GET | `/api/admin/cost/budget-thresholds` / PUT | 预算配置 |

### 告警

`amount_today > budget_thresholds.daily_limit_cny × alert_at_pct/100` → P1 alert。
`> hard_stop_at_pct/100` → P0 alert + 自动暂停 corresponding tool/feature（如 mcp tool 限流）。

---

## §4.4.2 告警中心 `/admin/alerts` (operator scope)

### Scope 区分

`alerts.scope` 列：

- `'user'` — Phase N 用户产品端可见
- `'operator'` — admin only（运营 alert）

### 运营 alert 来源

详见 §4.7.3.1（与 user-side 共享 source 枚举）。

### SLA

| severity | response time | 通知 |
| --- | --- | --- |
| P0 | 5 min | 邮件 + 短信 (Phase 2) + 站内 |
| P1 | 1 hour | 邮件 + 站内 |
| P2 | 24 hours | 站内 |
| P3 | 72 hours | 站内 |

### 端点

| Method | Path | Action |
| --- | --- | --- |
| GET | `/api/admin/alerts?scope=operator&severity=&status=&cursor=` | 列表 |
| GET | `/api/admin/alerts/unread-count` | 角标数字 |
| PATCH | `/api/admin/alerts/:id` | `{status, assigned_to?, runbook_url?}` |
| POST | `/api/admin/alerts/:id/escalate` | P2→P1 升级（手动） |
| POST | `/api/admin/alerts/mark-all-read` | — |

---

## §4.4.4 公告 & 邮件 `/admin/comms`

### 新表

```sql
CREATE TABLE comms_announcements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title_zh VARCHAR(256), title_en VARCHAR(256),
  body_zh TEXT, body_en TEXT,
  channel VARCHAR(16) NOT NULL,               -- 'inapp' | 'email' | 'both'
  audience VARCHAR(32) NOT NULL,              -- 'all' | 'paid' | 'free' | 'org_id:<uuid>' | 'user_ids:[...]'
  scheduled_at TIMESTAMPTZ,
  sent_at TIMESTAMPTZ,
  sent_count INT DEFAULT 0,
  status VARCHAR(16) DEFAULT 'draft',         -- 'draft' | 'scheduled' | 'sending' | 'sent' | 'cancelled'
  created_by INT FK→users(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ
);
```

### 端点

| Method | Path | Action |
| --- | --- | --- |
| GET | `/api/admin/comms?status=&cursor=` | 列表 |
| POST | `/api/admin/comms` | 创建草稿 |
| PUT | `/api/admin/comms/:id` | 更新草稿 |
| POST | `/api/admin/comms/:id/preview` | 预览渲染 |
| POST | `/api/admin/comms/:id/send` | 触发发送（schedule_at=null 即时） |
| POST | `/api/admin/comms/:id/cancel` | 已 scheduled 状态可取消 |
| GET | `/api/admin/comms/:id/recipients?cursor=` | 受众列表（分页） |

---

## §4.4.5 商务线索 `/admin/commercial/leads`

### 表扩列

```sql
ALTER TABLE commercial_leads
  ADD COLUMN assigned_to INT FK→users(id),
  ADD COLUMN closed_reason VARCHAR(64),
  ADD COLUMN consultation_notes TEXT,
  ADD COLUMN report_pdf_url TEXT;             -- lead_diagnostic 报告下载链接
```

### 状态机

```
new → contacted → closed (won|lost|deferred)
new → ignored (终态)
```

### 端点

| Method | Path | Action |
| --- | --- | --- |
| GET | `/api/admin/commercial/leads?status=&assigned_to=&cursor=` | 列表 |
| GET | `/api/admin/commercial/leads/:id` | 详情（含 lead_diagnostic 报告 PDF） |
| PATCH | `/api/admin/commercial/leads/:id` | `{status, assigned_to, consultation_notes, closed_reason}` |
| GET | `/api/admin/commercial/leads/export?from=&to=` | CSV 导出 |

---

## §4.4.6 MCP 运营 `/admin/mcp-ops`

### 新表

```sql
CREATE TABLE mcp_call_log (
  id BIGSERIAL PRIMARY KEY,
  api_key_id UUID FK→user_api_keys(id) ON DELETE CASCADE,
  user_id INT FK→users(id),
  tool VARCHAR(64) NOT NULL,
  resource_uri VARCHAR(512),
  status VARCHAR(16) NOT NULL,                -- 'success' | 'error'
  http_status INT,
  error_code VARCHAR(64),
  latency_ms INT,
  cost_estimate_cny NUMERIC(10,4),
  request_size_bytes INT,
  response_size_bytes INT,
  occurred_at TIMESTAMPTZ DEFAULT now()
) PARTITION BY RANGE (occurred_at);
-- 月度分区，每月新建一个 partition
```

### 端点

| Method | Path | Resp |
| --- | --- | --- |
| GET | `/api/admin/mcp-ops/overview?period=24h\|7d\|30d` | `{total_calls, top_tools: [...], top_users: [...], error_rate, avg_latency_ms}` |
| GET | `/api/admin/mcp-ops/users?cursor=` | 用户调用排行（按 7d total_calls） |
| GET | `/api/admin/mcp-ops/calls?api_key_id=&tool=&status=&from=&to=&cursor=` | 调用流水 |
| POST | `/api/admin/mcp-ops/api-keys/:id/suspend?duration_hours=24` | 配额异常时手动暂停 |
| POST | `/api/admin/mcp-ops/api-keys/:id/resume` | 恢复 |

### 自动暂停规则

`COUNT(occurred_at > now() - 1min) > rate_limit_per_minute × 1.5`（持续 5 min）→ 自动 suspend 24h + 通知用户邮箱。

---

## §4.4.7 审计日志 `/admin/audit-log`

### 新表

```sql
CREATE TABLE admin_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id INT NOT NULL REFERENCES users(id),
  action VARCHAR(64) NOT NULL,                -- 'freeze_user' | 'brand_merge' | 'batch_retry' | ...
  resource_type VARCHAR(32) NOT NULL,         -- 'user' | 'brand' | 'query' | 'segment' | ...
  resource_id VARCHAR(64),
  severity VARCHAR(8) NOT NULL,               -- 'low' | 'med' | 'high'
  before JSONB,
  after JSONB,
  ip INET,
  user_agent TEXT,
  reason TEXT,                                 -- operator 提供的备注
  occurred_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON admin_audit_log (operator_id, occurred_at DESC);
CREATE INDEX ON admin_audit_log (action, severity, occurred_at DESC);
CREATE INDEX ON admin_audit_log (resource_type, resource_id);
```

### 高风险 mutation 必审名单

`severity='high'` 的 action：

```
freeze_user / unfreeze_user / soft_delete_user / force_password_reset
brand_merge / brand_delete / brand_approve_with_low_confidence
batch_retry (>= 100 queries)
account_pool_purge / account_disable_all_for_engine
config_change (scheduler / budget_thresholds / domain_authorities seed import)
cookies_import / api_key_revoke (admin level)
```

### 端点

| Method | Path | Action |
| --- | --- | --- |
| GET | `/api/admin/audit-log?operator=&action=&resource_type=&severity=&from=&to=&cursor=` | 列表 |
| GET | `/api/admin/audit-log/:id` | 详情（含 before/after diff） |
| GET | `/api/admin/audit-log/export?from=&to=` | CSV 导出 |

---

## §5.7 Audit Decorator 规范（新）

所有 admin 写操作必经 `@audit(action, severity)` 装饰器：

```python
# backend/app/admin/audit.py
from functools import wraps

def audit(action: str, severity: str = 'med', capture_diff: bool = True):
    def deco(fn):
        @wraps(fn)
        async def wrapper(request, *args, **kwargs):
            operator = request.state.user
            before = await capture_resource_state(request) if capture_diff else None
            try:
                result = await fn(request, *args, **kwargs)
                after = await capture_resource_state(request) if capture_diff else None
                await admin_audit_log_service.write({
                    'operator_id': operator.id,
                    'action': action,
                    'resource_type': extract_resource_type(request),
                    'resource_id': extract_resource_id(request),
                    'severity': severity,
                    'before': before,
                    'after': after,
                    'ip': request.client.host,
                    'user_agent': request.headers.get('user-agent'),
                })
                return result
            except Exception:
                # 失败也写一条 attempt 记录
                ...
        return wrapper
    return deco
```

### 用法示例

```python
@router.post('/users/{user_id}/freeze')
@audit(action='freeze_user', severity='high')
async def freeze_user(request, user_id: int): ...
```

### CI 检查

新建 `backend/tests/test_audit_decorator_coverage.py`：扫所有 `backend/app/api/admin/` 下的 POST/PUT/PATCH/DELETE，断言每个路由函数有 `@audit` 装饰器；缺失即 fail。

---

## 与 plan 文档关系

- 本 addendum §4.2.1-§4.2.6 / §4.3.6 / §4.4.1-§4.4.7 / §5.7 对应 `docs/APP_BACKEND_PLAN.md` Phase O 9 模块。
- 数据模型详见 `docs/DATA_MODEL.md`。
- 端点详见 `docs/openapi.yaml`。

---

*本 addendum 在 Phase P 完成时合入 `docs/ADMIN_PRD.md`，按 §4.x / §5.x 锚点替换 / 补充。*
