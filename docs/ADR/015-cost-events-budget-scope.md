# ADR-015: `cost_events.scope` 4 分（pipeline / kg / mcp / reports）独立预算告警

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
GenPano 涉及多 LLM 调用源：① Tracker analyzer 调豆包/DeepSeek（pipeline）；② KG relation_extractor 调 LLM（kg）；③ MCP user 调用估算成本（mcp）；④ Reports narrative LLM（reports）。这些成本如果合并算总账，无法定位"今天费用超 50% 是因为 KG 跑大批回填"还是"用户 MCP 调爆了"。

**Decision**:
`cost_events.scope` 4 个枚举：`pipeline | kg | mcp | reports`。每个 scope 在 `budget_thresholds` 表有独立 `daily_limit_cny` / `weekly_limit_cny` / `monthly_limit_cny`。任一 scope 单日 > `daily × alert_at_pct/100`（默认 80%）→ P1 alert（scope=operator）。> `daily × hard_stop_at_pct/100`（默认 100%）→ P0 alert + 自动暂停对应功能（如 mcp tool 限流到只读）。

**Consequences**:
- ✅ 成本归因清晰：admin 看 cost dashboard 一眼分清四类。
- ✅ 单一 scope 故障（如 KG 死循环写入）不影响其他 scope 服务（pipeline 继续跑 / 用户报告继续生）。
- ✅ Phase 2 加 scope 容易（如 'background_worker' / 'storage'）。
- ⚠️ `pipeline` 内部细分（diagnostics / reports causal LLM）通过 `source` 字段区分（如 `doubao_diagnostics` / `doubao_narrative`），不开 sub-scope 防止表过散。
- ⚠️ Hard stop 逻辑要谨慎：mcp scope hard stop 不能完全禁用 user 已有的 API key（影响生产），改为限速到 1 req/min。

**Alternatives**:
- **统一总账**：故障归因难，否决。
- **细分到 source 级别（每个 LLM 模型独立预算）**：维护负担太大，PA 决策粒度太细，否决。
- **不限预算**：纯 cost dashboard 观测，无 hard stop。风险：恶意 / bug LLM 调用爆账户，否决。
