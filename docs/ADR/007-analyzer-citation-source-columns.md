# ADR-007: Analyzer 三新维度落 citation_sources 列（而非新表）

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
Phase A 引入三新分析维度：`attribution_method`（归因方法 5 类）、`page_type`（页面类型 11 类）、`authority_tier`（域权威 0-4 级）。可选 schema：① 三列加到现有 `citation_sources` 表；② 新建一对一关联表 `citation_source_analysis(citation_id PK, attribution_method, page_type, ...)`。

**Decision**:
三个字段加到 `citation_sources` 表作为新列（`attribution_method VARCHAR(32)`、`page_type VARCHAR(32)`、`authority_tier SMALLINT`、`site_type VARCHAR(32)`）。不建一对一关联表。CI 跑 alembic 迁移幂等（IF NOT EXISTS 守卫）+ 历史回填脚本（`backfill_attribution.py`）。

**Consequences**:
- ✅ 查询无需 JOIN：`/v1/projects/:id/citations` 直接读 `citation_sources` 一张表。
- ✅ 索引高效：`(mention_id, attribution_method, created_at DESC)` 复合索引可服务 attribution 趋势 / aggregable chart。
- ✅ Phase RP / D / Phase O cost 计算都直接读这几个字段，性能可控。
- ⚠️ 30 天历史回填会触发表锁（Phase A.11），需在低峰期跑 + 分批 commit（每 10k 行）。
- ⚠️ 三列均允许 NULL（向后兼容旧数据）；但 CI 必须验证回填后旧数据 NULL 比例 < 5%。
- ⚠️ 表宽度增加（VARCHAR(32) × 3 + SMALLINT），单行约多 96 bytes；`citation_sources` 当前估 5M+ 行 → 多约 480MB。

**Alternatives**:
- **一对一关联表**：保持原表干净，但所有读端点要 JOIN；分析查询 N+1 风险；否决。
- **JSONB 字段**：`analysis JSONB` 装三个值。无法在 query 中直接索引（需要 GIN / 表达式 index 复杂），否决。
