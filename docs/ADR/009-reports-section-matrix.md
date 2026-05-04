# ADR-009: Reports SECTION_MATRIX 服务端实现（不抽通用模板引擎）

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
Phase RP 要支持 4 reportType × 10 section × 3 variant × 3 reader perspective × insight stack layer。可选实现：① 抽通用模板引擎（DSL 配置 section + reader + variant），运行时解释执行；② 把 SECTION_MATRIX 写在代码里（每 section 一个 Python class）。

**Decision**:
SECTION_MATRIX 直接写在 `backend/app/reports/builder.py`（Python dict 字面量，与 `frontend/src/pages/ReportsPage.jsx` 同结构），每个 section_type 对应 `backend/app/reports/sections/<name>.py` 一个文件 + 一个 `BaseSection` 子类。Builder 接收 `report_type` → 查 matrix → 调每 section.render(ctx, variant, reader, layers)。

**Consequences**:
- ✅ Section 实现是普通 Python class，IDE 跳转 / 类型检查 / 单测都直接可用。
- ✅ 加新 section 或 variant 只改一处（matrix + 一个文件）。
- ✅ FE 与 BE 共享 SECTION_MATRIX 形状（FE 也用同一份 schema 渲染 PDF preview）。
- ⚠️ Section 数量增长到 20+ 时单文件可能膨胀；当前 10 sections 可控。
- ⚠️ 不像 DSL 那样让运营自助配置；但运营无定制 section 需求（PRD §4.7.0-a 已固化）。

**Alternatives**:
- **DSL 模板引擎**（如 Jinja2 + 自定义 directive）：配置驱动；但 section 业务逻辑（比如 `competitor_comparison` 要算 sov_diff、查多个 brand）DSL 无法表达，最终还是要回 Python，否决。
- **react-pdf 做 FE 渲染 + BE 只回 JSON**：BE 简单，但失去服务端 fallback / 后台批量生成能力（cron 月报必须 BE 渲染），否决。
