# rules/ — 明细规则

按关注点拆到子目录，每条规则单独成文件。**主入口在仓库根目录的 [AGENTS.md](../AGENTS.md)**。

## 关注点 → 子目录

| 关注点 | 入口 | 何时读 | 规则数 |
|---|---|---|---|
| 全局/工作流 | [global/README.md](global/README.md) | 所有任务起点 | 7 |
| 前端 | [frontend/README.md](frontend/README.md) | 改 frontend/ 或 Admin UI | 3 |
| 后端 | [backend/README.md](backend/README.md) | 改 backend/ 或 /admin/api/* | 1 |
| 测试与证据 | [testing/README.md](testing/README.md) | 改 bug / 写 PR 之前 | 5 |
| 安全与执行 | [security/README.md](security/README.md) | CI / 秘密 / 不可绕过 gate | 1 |
| 文档/issue/PR | [documentation/README.md](documentation/README.md) | 写 issue / PR / PRD | 4 |

## 补充文件

- [INCIDENTS.md](INCIDENTS.md) —— war story 与 PR timeline；规则正文不重复 PR 编号
- [MAINTENANCE.md](MAINTENANCE.md) —— 规则更新流程 / 反 context 中毒约束 / Cross-agent Consistency Contract

## 元 lint

`scripts/lint_rules.py` + `.github/workflows/rules-lint.yml` 自动检查：

- 每条 rule 文件必有 frontmatter（`last-reviewed` / `owner-hat` / `next-review-by` / `status` / `applies-to` / `hardness`）
- 单文件 ≤ 200 行
- 规则正文不含 `#<数字>` PR 编号格式（INCIDENTS.md 例外）
