# MAINTENANCE — 规则维护 / 反 Context 中毒 / Cross-agent Consistency

本文件覆盖**如何改 rules/ 与 AGENTS.md 本身**。规则正文应只关心"做什么"；元规则在这里。

## 1. 谁能改

PR + ≥1 reviewer + `rules-change` label。

## 2. 改前检查清单

- 跑 `python3 .github/scripts/lint_pr_body.py --body-file <body>` 通过
- 跑 `python3 scripts/lint_rules.py rules/`（元 lint）通过
- 改路径 → 同步 [AGENTS.md](../AGENTS.md) §7 旧章节对照表 + 相关子目录 `README.md`
- 触碰 AGENTS.md `<!-- DIGEST-BEGIN -->...<!-- DIGEST-END -->` 块 → 跑 `bash .claude/hooks/session-start.sh` smoke 确认抽取

## 3. 改后联动

- 新增 hard rule → 评估是否入 DIGEST 块（**门槛高**；只有 6 条 hard rule 级别才进）
- 改 Enforcement → 确认 `.github/scripts/lint_pr_body.py` 仍匹配
- frontmatter 改 → 子目录 README.md 同步

## 4. 反 Context 中毒规则

这一节是本仓库的**自身防护层**。违反这些约束的 PR 应被 reject。

### 4.1 手写 digest 禁止

hook 输出的 hard rule **必须从 AGENTS.md DIGEST 块抽取**，不能 hook 脚本里硬写。
`.claude/hooks/session-start.sh` 顶部注释必须重申此约束。

### 4.2 War story 隔离

规则正文不准出现 `#<数字>` PR 编号格式。引用 PR / 轮次 / 历史 timeline 必须改用
`rules/INCIDENTS.md#<anchor>` 链接。`scripts/lint_rules.py` 自动检测。

### 4.3 过期约束

- 每个 rule 文件 frontmatter 必含 `last-reviewed` / `next-review-by`
- `next-review-by` 过期 → 子目录 README.md 把该行标 `[STALE]`（本次手工，P1 自动）
- **STALE 规则不能作为决策唯一依据**；引用前必须重新确认

### 4.4 具体物必带 verify

路径 / IP / workflow 引用必须配 `verify:` bash 命令（本次只对新增 / 触碰到的规则强制；
存量按需补）。verify 失败 → 规则视为 stale，开 issue。

### 4.5 单文件 200 行上限

单条 rule 文件超过 200 行**强制拆分**到子目录。`scripts/lint_rules.py` 自动检测。

### 4.6 弃用 ≥ 新增

rules-change PR body 必填一行 `可废弃旧规则候选: <列表 or 无>`。强迫每次新增顺手清扫一次。

### 4.7 skills 是 rules 的投影

`.claude/skills/*/SKILL.md` body **不允许持有 rule 内容副本**。SKILL.md 只允许：

- 必需的 skill frontmatter（`name` / `description` / `allowed-tools`）
- 一行 "Read rules/<path>"
- skill 调用专属的**工具序列模板**（rule 没有的内容）

下次触碰 SKILL.md 必须满足此约束。本次 PR 不动 SKILL.md。

### 4.8 规则正文与 CI lint 常量同步

`rules/security/enforcement.md` 描述了 `.github/scripts/lint_pr_body.py` 的必填 section（`Linked Work` / `Root Cause Gate` / `Verification Evidence Ledger`）。**CI lint 是 source of truth**，规则文档是它的人类可读说明。

`scripts/lint_rules.py` 自动检查：

- 解析 `lint_pr_body.py` 的 `SECTION_*` 常量
- 在 `rules/security/enforcement.md` 中 grep 每个 section 名
- 任一缺失 → fail

防的就是"开发者改了 lint_pr_body.py 的 REQUIRED_SECTIONS 但忘了同步 enforcement.md"。无该机制时，规则文档静默 stale，agent 读到错误信息——正是模块化重构本应阻止的中毒模式。

## 5. Cross-agent Consistency Contract

### 5.1 三层保证

- **L1（hard）**：`.github/workflows/pr-body-lint.yml` —— 所有 agent 的 PR 都过此 lint。
  规则不在 PR body → 合并被拒。**唯一硬保证**。
- **L2（mid）**：`.github/ISSUE_TEMPLATE/*` validations + `issue-body-lint.yml` —— web UI 强制必填，API 提醒
- **L3（soft）**：各 agent carrier 文件——尽力让 agent 在动手前就知道规则

### 5.2 Carrier 对应表

| Agent | Carrier 文件 | 加载方式 |
|---|---|---|
| Claude Code (CLI/Web) | `CLAUDE.md` → `AGENTS.md`；`.claude/hooks/session-start.sh` 注入 DIGEST | SessionStart hook |
| Codex (CLI/cloud) | `AGENTS.md`（约定名直接读） | 启动时读取 |
| Cursor | `.cursorrules` → `AGENTS.md` | 启动时读取 |
| Aider | `--read AGENTS.md` 或 config | 显式声明 |
| Devin | 仓库浏览 | 启动时浏览 |
| 人类 | `README.md` / issue 模板 / PR 模板 | 手动 |

### 5.3 新 agent 接入清单（3 步）

1. 在新 agent 约定的 carrier 文件中加 5 行指针，指向 `AGENTS.md`，**禁止复制内容**
2. 若该 agent 有 SessionStart 类机制，参考 `.claude/hooks/session-start.sh` 实现"从 AGENTS.md
   DIGEST 块抽取"
3. 该 agent 的 PR 一样过 `.github/workflows/pr-body-lint.yml`——**不需要新增 CI workflow**

### 5.4 不可逾越的约束

- 任何 agent-specific 文件**只能是指针**，不允许复制规则内容
- 任何 agent **不能修改 CI lint** 来宽容自己的输出
- 任何 agent 都遵守同一份 rules/，**没有**"我作为 X 不适用"的例外

## 6. 弃用流程

- 开 issue + `rules-change` label
- frontmatter 改 `status: deprecated`
- 30 天后由 Pruning Automation 真删
- 期间 [AGENTS.md](../AGENTS.md) §7 对照表标 `(deprecated)`

## 7. Stale 检测（机器化）

P1：`scripts/check_rules_freshness.py` + CI 周期 job 自动扫 frontmatter 找过期 + verify 失败。
本次靠人 + README 汇总表。

## 8. 版本与历史

- git history 是权威；不维护独立 changelog
- 重大结构变更（拆分 / 合并）在 PR ledger 写"迁移前后映射表"

## 9. 冲突解决

- rules/ 与 AGENTS.md 索引冲突 → 明细文件优先
- rules/ 与 CI lint script 冲突 → **CI script 优先**（CI 才是真正的 gate）
- 多个 rules/*.md 冲突 → 关注点更窄的优先（`rules/frontend/` > `rules/global/`）

## 10. docs/ 同病备案（P1 单独立项）

`docs/` 与 `rules/` 共享多种中毒模式：无时间戳 / 无 deprecation marker / 与代码漂移 / 无分层。
本次 PR **不动 `docs/` 本体**。

P1 独立 plan 应包含：

- 审计 + 分类（`current` / `stale` / `superseded` / `archived` / `derived`）
- 加 frontmatter（`last-reviewed` / `verified-against-commit` / `next-review-by`）
- 分层目录：`docs/current/` `docs/runbooks/` `docs/adrs/` `docs/archive/`
- 扩展 `scripts/lint_rules.py` 适配 docs/
- 与代码相关的 doc（API ref 等）改为自动生成

**约束**：本次 rules/ 引用 docs/ 时，鼓励但不强制带 commit SHA（避免 plan 范围扩大）。
