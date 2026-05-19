---
last-reviewed: 2026-05-19
owner-hat: Lead
next-review-by: 2026-11-19
status: active
applies-to: [Lead, Review]
hardness: SOFT
---

# Peer Review Required

**Why**：同一 session 内戴多 hat 自审会陷入 confirmation bias。独立 subagent 看同份资料能挑出
主 session 漏的点。这是单 coordinator 多 hat 模型的解药。

## Rule

### 必须 spawn peer subagent 的场景

1. **架构 / 结构性改动**（如规则模块化、目录重组、依赖图改动）
2. **公开 contract / schema / API 改动**
3. **弃用规则或删除代码**（不可逆）
4. **同一 session 内 ≥2 次自我修改的决策**——容易 confirmation bias
5. **用户给反向 feedback 时**——push back 之前先 peer review

### 如何做

- 用 Agent 工具 spawn subagent，`subagent_type=Plan` 或 `general-purpose`
- subagent prompt **只给 artifact 本身**：plan 文件、PR diff、改动 patch
- **不给** hypothesis、不给推荐、不给"用户希望我这么做"
- subagent 输出：同意 / 反对 / 具体担忧，标记**哪些点是它独立想到的**
- 主 session 必须 explicit 处理子 agent 异议，**不能 silent ignore**
- 异议处理结果记入 PR body 或 issue comment

### 反例（伪 peer review）

- ❌ 主 session 写好 PR，自己 review 自己 → 不算 peer review
- ❌ 把推荐告诉 subagent，subagent 同意 → echo chamber
- ❌ 用相同 hypothesis 的 prompt → 同 bias 不 peer
- ❌ 跑 peer 但不记录异议 → 走过场

## Cross-references

- [rules/global/orchestrator-discipline.md](orchestrator-discipline.md) —— subagent 一般规则
- [rules/global/agent-topology.md](agent-topology.md) —— 多 hat 模型的诚实抽象
