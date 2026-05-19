---
status: canonical
last_verified: 2026-05-18
owner: docs-maintenance
---

# docs/archive — 历史文档归档

此目录存放**已脱离实际、但保留备查**的旧文档。Git 历史是足够的，但把它们放在主 `docs/` 树里会污染 agent 的阅读上下文，所以集中迁移到这里。

## Agents：阅读规则

- 默认**不要**读取 `docs/archive/` 下的任何文件。
- 仅当用户**显式要求**查阅历史背景，或主 `docs/` 里某文件用 `supersedes: archive/...` front-matter 明确指向时，才打开 archive 文件。
- 永远不要从 archive 文件复制结构 / 章节锚点 / API 契约到新代码或新 PR — 它们已经不代表事实。

## 命名

`<原文件名>-v<版本>-<最后修订日期>.md`，例如 `PRD-v1.3-2026-04-15.md`。

## 当前归档

| 文件 | 原位置 | 归档日期 | 替代来源 |
| --- | --- | --- | --- |
| `PRD-v1.3-2026-04-15.md` | `docs/PRD.md` | 2026-05-18 | 见 `docs/PRD.md` (stub) |

## 增删规则

- 归档时：`git mv` + 在本表追加一行 + 在原位置留 stub（指向 archive 路径 + 当前事实来源）。
- 删除时：不要从此目录删除文件 — Git 历史足够，但保留 archive 副本可以让搜索（grep / agent）能直接命中。
