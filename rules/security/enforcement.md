---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [all]
hardness: HARD
---

# Enforcement — CI 三层强制模型

**Why**：CI 是唯一硬 gate，所有 agent 都过同一关卡。详 [rules/INCIDENTS.md#1067](../INCIDENTS.md#1067)。

## Rule

### Layer 1：`.github/workflows/pr-body-lint.yml`（gate）

- 触发：`pull_request: [opened, edited, synchronize, reopened]`
- Validator：`.github/scripts/lint_pr_body.py`（Python 3.12 stdlib，无依赖）
- PR body 必须含三个 `## ` 节：
  - `## Linked Work` 含 `Business Goal:` 与 `Final Success Evidence:`
  - `## Root Cause Gate` 含 `Direct trigger:`、`Underlying product/system root cause:`、
    `Evidence proving it:` —— **或** `Classification: not an incident - <reason>`
    （单值，不是模板的 `|`-separated stub）
  - `## Verification Evidence Ledger` 含至少一个 `- [x]` 项 + 一个 `https://` URL
- Placeholder 文本（TODO / TBD / PLACEHOLDER / xxx / ... / bare N/A / 模板的字面中文 stub
  如 ``` `用户在 `http://116.62.36.173/<route>` ``` ``` ）按字段为空拒绝
- 失败：workflow 在 PR 发评论列出每个缺失/空字段，并 fail check
- 分支保护：`main` 上的 branch protection（Settings → Branches）必须列 `Lint PR Body`
  为 required status check；否则 lint 跑但不阻 merge

### Layer 2：`.github/workflows/issue-body-lint.yml`（feedback）

- 触发：`issues: [opened, edited]`
- Validator：`.github/scripts/lint_issue_body.py`
- 从 label（`type:human` / `type:epic` / `type:task`）+ body marker 探测 issue 类型，
  按模板验证必填字段
- 在 issue 评论 gap，但**永不 fail workflow** —— 此层是 feedback only

### 添加新必填字段

1. 在相关 `.github/ISSUE_TEMPLATE/` 模板加字段，`validations.required: true`（web UI 强制）
2. 字段名加到 `.github/scripts/lint_issue_body.py` 的 `REQUIRED_FIELDS_BY_TYPE`
   （或 `lint_pr_body.py` 的 `REQUIRED_FIELDS` / `REQUIRED_SECTIONS` for PR fields）
3. 更新 `.github/PULL_REQUEST_TEMPLATE.md`（若为 PR field）
4. 本地 smoke：`python3 .github/scripts/lint_pr_body.py --help` + 对照
   `.github/PULL_REQUEST_TEMPLATE.md`（必 fail）和 known-good body（必 pass）

## Verification

```bash
verify: test -f .github/workflows/pr-body-lint.yml && test -f .github/scripts/lint_pr_body.py
```

## Cross-references

- [rules/documentation/issue-pr-prd-contract.md](../documentation/issue-pr-prd-contract.md)
- [rules/MAINTENANCE.md](../MAINTENANCE.md) Cross-agent Consistency Contract
