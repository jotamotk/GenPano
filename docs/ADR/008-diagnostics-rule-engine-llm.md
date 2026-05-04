# ADR-008: Diagnostics 规则引擎 + LLM Causal Chain（缓存 24h，单 project 50 调用/天）

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
Phase D 要支持 25+ 条诊断规则 + 每条诊断含 `causal_chain.hypothesized_mechanism` + `alternative_hypotheses` 自然语言段。完全 hard-coded 文案不灵活；每次诊断都调 LLM 成本爆炸。

**Decision**:
规则引擎用 Python class（每 rule 一个 `BaseRule` 子类），评估输入聚合 dict 输出 `DiagnosticPayload`。Causal chain 文本由 LLM（豆包 / DeepSeek）异步生成，缓存 24h；缓存 key = `(project_id, rule_id, brand_id, day)`。单 project 单日 LLM 调用上限 50 次。LLM 失败 → fallback 用规则自带的静态文案（`rule.fallback_mechanism`）。

**Consequences**:
- ✅ 规则严肃可测（每 rule 写 happy + 不触发 + 边界 ≥ 3 case）；25 rule × 3 ≈ 75 单测。
- ✅ Causal chain 文案自然（LLM 优化），用户体验远高于纯模板。
- ✅ 成本可控：每 project 每日 ≤ 50 次 LLM × 平均 0.05 元 ≈ 2.5 元/project/天；500 project ≈ 1250 元/天；可承受。
- ⚠️ 缓存命中率目标 ≥ 70%；Phase O cost dashboard 持续监控。
- ⚠️ 同 (project, rule, brand) 在 24h 内只算一次 LLM，不能反映同日内剧烈波动；可接受（诊断粒度本就是日级）。
- ⚠️ LLM 输出需要 JSON 解析容错（用 `json_repair` 库，与 `geo_tracker/analyzer/llm_analyzer.py` 一致）。

**Alternatives**:
- **纯模板（无 LLM）**：causal chain 文案僵硬，违反 PRD §4.7.1 阅读体验要求。
- **每次诊断都调 LLM 不缓存**：成本爆炸（500 project × 25 rule × 0.05 元 = 625 元/天/project），否决。
- **离线批量 LLM 跑（每周一次）**：诊断时效性差，错过 P0/P1 实时性窗口，否决。
