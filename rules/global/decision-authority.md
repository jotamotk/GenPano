---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead]
hardness: SOFT
---

# Decision Authority

**Why**：AI Leader 经常向用户问技术决策但用户不关心细节；又有真正需要 external input 的决策。
没有明文区分导致问太多废问题 + 漏掉真正该问的。

## Rule

每个决策点先归档到三档之一，**再决定行动**。

### 档位 1：`NEVER 问` — 自己决定即可

涵盖：

- 库选型（同等量级、licence 兼容）
- 目录结构 / 文件命名 / 模块边界
- 测试框架与组织
- 内部重构（无 API 改动）
- lint / formatter / pre-commit 配置
- commit 信息措辞
- 实现细节（算法、数据结构、缓存策略）

行动：直接决定，PR body 一句话陈述即可。**不要起 `HUMAN DECISION NEEDED` 句式**——这等于
把决策推回给用户却没真实信息收益。

### 档位 2：`DECIDE + DOCUMENT` — 自己决定但留 rollback 痕迹

涵盖：

- 新依赖（增加供应链 / licence / bundle size 影响）
- 内部 schema 字段 / migration 顺序
- 内部 API 形状（仅本仓库 consumer）
- workflow / hook / lint 行为微调

行动：自己决定 + PR body 写 `DECISION:` 句式，**必须含 rollback path**（"若 X 出问题，
revert commit Y 或 set flag Z 即可"）。

### 档位 3：`MUST ASK` — 必须用 `HUMAN DECISION NEEDED` 等

涵盖：

- 产品方向 / user-visible 行为变化
- 公开 contract（API / event schema / public route）改动
- 生产数据迁移 / 不可逆删除
- 影响多 consumer 的依赖升级（major version）
- 安全 / 隐私 / 合规相关
- 与现有 PRD 决策冲突的选择
- 预算 / 性能成本显著上升

行动：发 `HUMAN DECISION NEEDED:` 句式，**必须含 候选 + 默认假设**，让用户能"沉默 = 同意默认"。
不要给开放式 "你觉得呢？"。

## 三句式约定

无论档位，决策落地用以下三句式之一（PR body / issue comment / commit message 皆可）：

| 句式 | 用途 | 必填部分 |
|---|---|---|
| `DECISION:` | 已决定 | 决定 + 理由 + 回滚路径 |
| `ASSUMPTION:` | 未验证但据此推进 | 假设 + 验证计划 + 失败后果 |
| `HUMAN DECISION NEEDED:` | 真正需要 external input | 候选列表 + 默认假设（无回复时怎么走） |

## 反模式

- ❌ `HUMAN DECISION NEEDED: 我应该用 React 还是 Vue？` —— 档位 1 问题，自己决
- ❌ `DECISION: 加了 redis 依赖` —— 缺 rollback path
- ❌ 把档位 3 决策默默实现 + 事后通知 —— 应该先 ASK
- ❌ 同一个 PR 内连发 3 个 `HUMAN DECISION NEEDED` 问相同模式问题 —— 一次问完所有

## 何时切档

升档（→ 更严）：
- 实现中发现影响面比初判大 → 重新评估，可能从档位 1 升到档位 2 或 3
- 用户给反向 feedback → 即使原档位是 1，下次同类决策升档

降档（→ 更松）：
- 同类决策在仓库历史中重复出现且无回滚记录 → 可降档（说明默认是稳的）
- 用户明示 "下次类似的别问我了" → 显式降档并记入 commit

## Cross-references

- [rules/global/peer-review.md](peer-review.md) —— 档位 2/3 的决策应触发 peer review
- [rules/documentation/issue-writing.md](../documentation/issue-writing.md) —— `DECISION` / `BLOCKER` 前缀
