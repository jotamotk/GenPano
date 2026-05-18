# Documentation Index

This index groups every document under `docs/` so contributors and agents can
navigate the ~1.4 MB knowledge base without grepping. New documents should be
added to the appropriate section below.

For the project-level entry point see the repository root `README.md`. For
agent collaboration rules see `AGENTS.md` at the repository root.

> Note: 旧的 `docs/PRD.md` (v1.3, ~500 KB) 已 archive 到
> [`docs/archive/PRD-v1.3-2026-04-15.md`](archive/PRD-v1.3-2026-04-15.md)。
> 当前 `docs/PRD.md` 是 stub，指向代码 + `frontend/src/data/mock.js` 作为事实来源。
> Addendum 文档（`PRD_ADDENDUM_PHASE_P.md` 等）尚未处理，下一轮维护再清理。

---

## Product Requirements

Cross-cutting product spec, addenda, and per-area PRDs.

- [`PRD.md`](PRD.md) — **stub**：旧 PRD 已 archive，指向代码 + mock.js 作事实来源
- [`PRD_ADDENDUM_PHASE_P.md`](PRD_ADDENDUM_PHASE_P.md) — Phase P additions
- [`PRD_CODEX_READY.md`](PRD_CODEX_READY.md) — Codex-implementable PRD snapshot
- [`PRD_APP_ANALYTICS_CORRECTION.md`](PRD_APP_ANALYTICS_CORRECTION.md) — App analytics no-fallback corrections
- [`PRD_ADMIN_ANALYZER_V4.md`](PRD_ADMIN_ANALYZER_V4.md) — Admin analyzer v4
- [`PRD_ADMIN_IMPLEMENTATION_PLAN.md`](PRD_ADMIN_IMPLEMENTATION_PLAN.md) — Admin implementation plan
- [`PRD_PIPELINE_ACCOUNT_LIFECYCLE.md`](PRD_PIPELINE_ACCOUNT_LIFECYCLE.md) — Pipeline account lifecycle
- [`PRD_PAGE_MAP.md`](PRD_PAGE_MAP.md) — page-to-PRD map
- [`ADMIN_PRD.md`](ADMIN_PRD.md) — Admin PRD
- [`ADMIN_PRD_B_PIPELINE.md`](ADMIN_PRD_B_PIPELINE.md) — Admin Pipeline slice
- [`ADMIN_PRD_C_KG.md`](ADMIN_PRD_C_KG.md) — Admin Knowledge Graph slice
- [`ADMIN_PRD_ADDENDUM_PHASE_P.md`](ADMIN_PRD_ADDENDUM_PHASE_P.md) — Admin Phase P addendum
- [`GROWTH_PLAN.md`](GROWTH_PLAN.md) — growth plan
- [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md) — development plan
- [`DASHBOARD_REDESIGN_PROPOSAL.md`](DASHBOARD_REDESIGN_PROPOSAL.md) — dashboard redesign proposal

## Architecture & Contracts

System architecture, adapter contracts, page surfaces, and OpenAPI schemas.

- [`ACTIVE_SURFACES.md`](ACTIVE_SURFACES.md) — active product/admin surfaces
- [`ADAPTER_CONTRACT.md`](ADAPTER_CONTRACT.md) — adapter contract (large)
- [`APP_BACKEND_PLAN.md`](APP_BACKEND_PLAN.md) — backend plan (large)
- [`openapi.yaml`](openapi.yaml) — OpenAPI schema
- [`openapi_addendum_phase_p.yaml`](openapi_addendum_phase_p.yaml) — OpenAPI Phase P additions
- [`plan-profile-aware-execution.md`](plan-profile-aware-execution.md) — profile-aware execution plan

## Data Model

ORM + database schema docs.

- [`DATA_MODEL.md`](DATA_MODEL.md) — canonical data model
- [`DATA_MODEL_ADDENDUM_PHASE_P.md`](DATA_MODEL_ADDENDUM_PHASE_P.md) — Phase P data-model additions

## Design System

Visual tokens and component design rules.

- [`DESIGN_TOKENS.md`](DESIGN_TOKENS.md) — design tokens
- [`design-system.md`](design-system.md) — design system overview

## Operations & Runbooks

Production runbooks, CI/CD reference, evidence collection.

- [`CI-CD.md`](CI-CD.md) — CI/CD reference
- [`APP_ANALYTICS_EXTRACTION_PROVENANCE_RUNBOOK.md`](APP_ANALYTICS_EXTRACTION_PROVENANCE_RUNBOOK.md) — app analytics extraction provenance
- [`APP_ANALYTICS_READONLY_EVIDENCE.md`](APP_ANALYTICS_READONLY_EVIDENCE.md) — readonly evidence runbook
- [`HOTSPOTS_OPS_HANDOFF.md`](HOTSPOTS_OPS_HANDOFF.md) — hotspots ops handoff

## Pipeline & Scraping

LLM scraping, debugging notes, and provider-specific guides.

- [`doubao-scraping-guide.md`](doubao-scraping-guide.md) — Doubao scraping guide
- [`gemini-debug-notes.md`](gemini-debug-notes.md) — Gemini debug notes
- [`llm-token-upload-guide.md`](llm-token-upload-guide.md) — LLM token upload guide
- [`scraping-experience-report.md`](scraping-experience-report.md) — scraping experience report

## Agent Collaboration

Codex / AI Lead workflow and handoff rules. See also `AGENTS.md` at repo root.

- [`AI_LEAD_WORKFLOW.md`](AI_LEAD_WORKFLOW.md) — AI Lead workflow
- [`AI_LEAD_CLAUDE_COLLABORATION.md`](AI_LEAD_CLAUDE_COLLABORATION.md) — Claude collaboration rules
- [`CODEX_ACCOUNT_HANDOFF.md`](CODEX_ACCOUNT_HANDOFF.md) — Codex account handoff
- [`CODEX_PROMPT_SEGMENT_PROFILE.md`](CODEX_PROMPT_SEGMENT_PROFILE.md) — Codex prompt segment profile

## Test Plans

- [`test-plan-auth.md`](test-plan-auth.md) — auth test plan

## Archive

Historical documents kept for grep / context only. See
[`archive/README.md`](archive/README.md) for the agent reading rule.

- [`archive/README.md`](archive/README.md) — archive policy + index
- [`archive/PRD-v1.3-2026-04-15.md`](archive/PRD-v1.3-2026-04-15.md) — old monolithic PRD (superseded 2026-05-18)

## Architecture Decision Records (ADRs)

Numbered architectural decisions, append-only.

- [`ADR/README.md`](ADR/README.md) — ADR index
- [`ADR/001-admin-flask-to-fastapi.md`](ADR/001-admin-flask-to-fastapi.md)
- [`ADR/002-schema-ssot-single-alembic.md`](ADR/002-schema-ssot-single-alembic.md)
- [`ADR/003-frontend-typescript-only.md`](ADR/003-frontend-typescript-only.md)
- [`ADR/004-orm-shared-package.md`](ADR/004-orm-shared-package.md)
- [`ADR/005-multitenancy-org-id.md`](ADR/005-multitenancy-org-id.md)
- [`ADR/006-mcp-bearer-api-key.md`](ADR/006-mcp-bearer-api-key.md)
- [`ADR/007-analyzer-citation-source-columns.md`](ADR/007-analyzer-citation-source-columns.md)
- [`ADR/008-diagnostics-rule-engine-llm.md`](ADR/008-diagnostics-rule-engine-llm.md)
- [`ADR/009-reports-section-matrix.md`](ADR/009-reports-section-matrix.md)
- [`ADR/010-alerts-diagnostics-coupling.md`](ADR/010-alerts-diagnostics-coupling.md)
- [`ADR/011-kg-1to1-mapping.md`](ADR/011-kg-1to1-mapping.md)
- [`ADR/012-kg-relations-staging.md`](ADR/012-kg-relations-staging.md)
- [`ADR/013-alerts-scope-shared.md`](ADR/013-alerts-scope-shared.md)
- [`ADR/014-audit-decorator.md`](ADR/014-audit-decorator.md)
- [`ADR/015-cost-events-budget-scope.md`](ADR/015-cost-events-budget-scope.md)

## Superpowers (dated plans & specs)

Internal time-stamped working documents.

- [`superpowers/plans/2026-05-06-generation-quality-feedback.md`](superpowers/plans/2026-05-06-generation-quality-feedback.md)
- [`superpowers/plans/2026-05-09-prompt-scope-generation-implementation.md`](superpowers/plans/2026-05-09-prompt-scope-generation-implementation.md)
- [`superpowers/specs/2026-05-06-generation-quality-feedback-design.md`](superpowers/specs/2026-05-06-generation-quality-feedback-design.md)
- [`superpowers/specs/2026-05-09-prompt-scope-generation-design.md`](superpowers/specs/2026-05-09-prompt-scope-generation-design.md)

## Folder-level READMEs

- [`README.md`](README.md) — short canonical-reference list (predates this INDEX)
