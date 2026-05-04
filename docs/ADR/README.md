# Architecture Decision Records (ADR)

> 日期：2026-05-04
> 范围：基于 `docs/APP_BACKEND_PLAN.md` Phase P 锁定的 15 条架构决策。
> 每条 ADR 一页内（Context / Decision / Consequences / Alternatives 各一段）。

## 索引

| ID | Title | Status | 决策日期 |
| --- | --- | --- | --- |
| [ADR-001](./001-admin-flask-to-fastapi.md) | Admin Flask → FastAPI 单进程 | Accepted | 2026-05-04 |
| [ADR-002](./002-schema-ssot-single-alembic.md) | Schema SSOT 单 Alembic head | Accepted | 2026-05-04 |
| [ADR-003](./003-frontend-typescript-only.md) | 前端全 TypeScript + 单入口 main.tsx | Accepted | 2026-05-04 |
| [ADR-004](./004-orm-shared-package.md) | ORM 共享包 `genpano_models/` | Accepted | 2026-05-04 |
| [ADR-005](./005-multitenancy-org-id.md) | 多租户 `org_id` 预留位 | Accepted | 2026-05-04 |
| [ADR-006](./006-mcp-bearer-api-key.md) | MCP 鉴权 Bearer API key（不上 OAuth） | Accepted | 2026-05-04 |
| [ADR-007](./007-analyzer-citation-source-columns.md) | Analyzer 三新维度落 citation_sources 列 | Accepted | 2026-05-04 |
| [ADR-008](./008-diagnostics-rule-engine-llm.md) | Diagnostics 规则引擎 + LLM causal chain | Accepted | 2026-05-04 |
| [ADR-009](./009-reports-section-matrix.md) | Reports SECTION_MATRIX 服务端实现 | Accepted | 2026-05-04 |
| [ADR-010](./010-alerts-diagnostics-coupling.md) | Alerts ↔ Diagnostics 联动 | Accepted | 2026-05-04 |
| [ADR-011](./011-kg-1to1-mapping.md) | KG 表 1:1 映射 brands/products | Accepted | 2026-05-04 |
| [ADR-012](./012-kg-relations-staging.md) | KG 关系边 staging → admin 审核流 | Accepted | 2026-05-04 |
| [ADR-013](./013-alerts-scope-shared.md) | Alerts scope 字段共表不同视图 | Accepted | 2026-05-04 |
| [ADR-014](./014-audit-decorator.md) | Audit Decorator 统一注入 | Accepted | 2026-05-04 |
| [ADR-015](./015-cost-events-budget-scope.md) | cost_events scope 4 分独立预算 | Accepted | 2026-05-04 |

## 写作约定

每条 ADR：

```markdown
# ADR-XXX: <短标题>

**Status**: Proposed | Accepted | Deprecated | Superseded by ADR-YYY
**Date**: YYYY-MM-DD
**Context**: 为什么需要做决策（一段）
**Decision**: 决定是什么（一段）
**Consequences**: 后果 / 影响 / 已知 trade-off（一段）
**Alternatives**: 还考虑过什么 + 为什么不选（一段）
```

变更：决策被推翻 → 不删，标 `Status: Superseded by ADR-XXX` + 添加 superseding ADR。
