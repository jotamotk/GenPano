# ADR-013: Alerts `scope` 字段共表不同视图（user vs operator）

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
Phase N 用户产品端 alerts（diagnostic / competitor / monitoring）与 Phase O 运营端 alerts（engine_health / cost_overrun / kg_quality）行为重叠：都需要 list / mark read / acknowledge 等。可选 schema：① 两张独立表 `user_alerts` + `operator_alerts`；② 一张表 + `scope` 字段区分（'user' / 'operator'）。

**Decision**:
方案 ②：单 `alerts` 表 + `scope VARCHAR(16) NOT NULL DEFAULT 'user' CHECK (scope IN ('user', 'operator'))`。FE 路由分离：`/v1/alerts` 默认 `scope='user'`；`/api/admin/alerts` 默认 `scope='operator'`。

**Consequences**:
- ✅ 单一 `alerts` 表，service 层 / Celery 触发器 / 邮件模板 / 单测都不重复。
- ✅ 同一条 monitoring_outage 可同时影响用户 + 运营 → 写两条不同 scope 的 alert（关联同一 source_ref_id）。
- ✅ 索引按 `(scope, status, triggered_at DESC)` 复合，user / operator 视图查询同样高效。
- ⚠️ Service 层每次必须显式带 `scope` 过滤；漏写会跨视图泄露。CI 加 `test_alerts_scope_isolation.py` 验证。
- ⚠️ 用户表面想看到的"还有运营级问题影响我"信号不直接（需要在 user-facing 触发器里特意建一条 user scope alert）。

**Alternatives**:
- **方案 ① 双表**：避免 scope 错位风险，但 service / 邮件 / Celery 都要双份代码，否决。
- **多 scope 字段 `audience VARCHAR[]`**：复杂，过早抽象，否决。
