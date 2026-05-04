# ADR-010: Alerts ↔ Diagnostics 联动（severity ≥ P1 自动建 alert）

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
Phase D 输出 diagnostics（含 P0-P3 严重度）；Phase N 输出 alerts（顶栏铃铛 + 邮件）。两者关系若不规范，会有：① alert 与 diagnostic 各自独立，运营要查两遍；② P0 diagnostic 没触发邮件 alert 用户不知；③ alert 处理后 diagnostic 状态不同步。

**Decision**:
- Phase D evaluator 创建 P0/P1 diagnostic 时**自动**通过 `alerts_service.create_from_diagnostic(diag)` 写一条 alert（source='diagnostic', source_ref_id=diag.id）。
- Diagnostic resolved → alert 自动 resolved（trigger / DB constraint 或 service 层）。
- Alert 跳转默认到对应 diagnostic（`/brand/diagnostics?diagnosticId=...`）。
- alert.scope='user'（用户产品端可见）；运营场景下 P1+ engine_health / monitoring_outage 等系统类 alert 走 `scope='operator'`，UI 分离。

**Consequences**:
- ✅ 用户一处看 alerts → 进 diagnostic 详情 → 处理 → 自动 alert 关闭，闭环。
- ✅ 邮件 / 站内通知统一走 alerts 表，不需要 diagnostic 单独触发。
- ⚠️ Diagnostic 升级（P2 → P1）逻辑：原 P2 diagnostic 不会有 alert，升 P1 时需触发新 alert。
- ⚠️ Alert 表会比 diagnostic 表大（含 system / operator 类）；按 scope 分区可优化。

**Alternatives**:
- **Alerts 与 Diagnostics 独立**：用户处理 diagnostic 后 alert 不自动消，体验差，否决。
- **Diagnostics 直接发邮件不经 alerts 表**：失去 alerts 列表 / 顶栏铃铛 / 标记已读功能，否决。
