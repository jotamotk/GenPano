# ADR-012: KG 关系边走 staging table → admin 审核流

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
Phase K K5 `relation_extractor.py` 用 LLM 从 `llm_responses` 文本推断品牌/产品关系边（COMPETES_WITH / SAME_GROUP / SUBSTITUTES / UPGRADES_TO / BUDGET_ALT_OF / PAIRS_WITH）。准确率金标 ≥ 90%，意味着每 100 条仍有 10 条幻觉。直接写入 `kg_brand_relations` / `kg_product_relations` 会污染图谱核心数据。

**Decision**:
LLM 推断结果先写到 `kg_relation_candidates(status='pending')` staging 表，包含 evidence / llm_model / confidence 字段。admin 在 `/admin/kg/candidates` 审核（approve / reject / merge），通过后才合并到 `kg_brand_relations` / `kg_product_relations`（source='analyzer'）。运营手工添加的关系边 source='admin' 直接进正式表（不走 staging）。

**Consequences**:
- ✅ 图谱核心数据质量可控（人审过的才进）。
- ✅ Discovery log 可观测（`discovery_log` 表记每次 LLM 调用 + 是否被人审标记为 hallucination）。
- ✅ ADMIN_PRD §C9 KG Quality Monitor 有数据支撑（7d 幻觉率 = `discovery_log.hallucination_flag` 占比）。
- ⚠️ 运营审核压力：30 天历史回填可能产出数千 candidates，需要批量审核 UI（`bulk-review`）。
- ⚠️ Approval 链路增加 1-3 天延迟；用户在该期间看不到新关系边。

**Alternatives**:
- **直接写正式表**：质量不可控，幻觉污染图谱永久存在，否决。
- **不做 LLM 推断，全靠运营手工**：运营成本太高（每月数百关系边），否决。
- **置信度阈值自动通过**（如 confidence > 0.95）：节省运营时间但仍然有质量风险，可作为 Phase 2 优化。
