---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead, Implementation, QA, Review]
hardness: SOFT
---

# Acceptance And Verification Evidence

**Why**：测试输出仅在绑定 acceptance claim 时才算证据。详 [rules/INCIDENTS.md#1283](../INCIDENTS.md#1283)。

## Rule

"Tests passed" 本身不足。

### Acceptance Matrix（开工前）

- 实施前，Lead hat 把 PRD 需求、用户报告、accepted Human Input decision 翻译为
  `Acceptance Matrix`
- 实施前确认 Business Goal 与 Final Success Evidence；不清楚则发 `HUMAN DECISION NEEDED`，
  不要拆分工作
- 每行 acceptance 必须引用来源：PRD ID / 用户报告症状 / Human Input disposition /
  issue `DECISION` / approved `PRD-CHANGE`
- 无来源的 acceptance row 无效；PRD 要求但无 row 的，作为覆盖 gap 在开工前记录
- 翻译不明确时发一个 `QUESTION` 列齐所有候选并等待，除非 issue 中已有显式默认

### 每项 verification 必填

- command
- exit code
- key output
- scope covered
- artifact 或 link
- commit SHA

**无证据 = 未勾选**。

### 用户报告的 bug

需要 `User-Symptom Replay`：对照确切的 route / row / brand / query / request / action /
visible result（可得时）。

不能精确 replay 时标 `BLOCKER`，不要从相邻测试声称 acceptance。

### Live incident

需要 `Business Result Gate` row，明命名业务对象与所需最终状态。

CI 绿 / deploy 绿 / 错误码更明确 **不构成 acceptance**，除非此 row 也通过。
scraper 恢复场景下意味着确切的 query readback（如 `done + response evidence`）。

仅观测性改进有用但不能关闭业务 incident，除非 Business Result Gate 通过。
更好的诊断、更具体的错误码、干净的 deploy → `Diagnostic progress only`。

### Live 突变 Playwright

任何 mutate live object 的 Playwright 测试（如重试生产 query / 提交 analyzer 工作）
**必须 disable Playwright retries**。workflow 不允许因首个 assertion fail 而重复 live mutation。

### Live mutation gate 的轮询窗口

必须覆盖完整的预期 recovery loop，包括 account 重新认证 + 重新认证后的 query 尝试。

窗口过期但对象仍在运行 → 报告证据 inconclusive，不要把 workflow 状态当 acceptance。

### 不能为绿而绿

不准通过删 assertion / 跳 case / 弱化 expectation / 吞 exception / 把检查移离用户路径
来让测试变绿。

测试错了或过时 → stop with `BLOCKER` 或 `PRD-CHANGE`，先拿决定再放松。

### PR handoff 必须声明 test integrity

- 测试文件变更
- 移除或放松的 assertion
- 新增的 skip
- 未验证的 acceptance row

## Cross-references

- [rules/testing/tiered-e2e.md](tiered-e2e.md) —— E2E 分层
- [rules/documentation/issue-pr-prd-contract.md](../documentation/issue-pr-prd-contract.md)
