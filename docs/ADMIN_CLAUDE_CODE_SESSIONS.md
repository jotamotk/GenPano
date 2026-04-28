# GENPANO Admin — Claude Code Session 规划

> 每个 Milestone 对应一个独立的 Claude Code Session
> 每个 Session 包含: 完整 Prompt、预期产出、验收标准、依赖说明、对抗性验证 + 规约对齐 prompt 模板
> 配套文档: [ADMIN_PRD.md](./ADMIN_PRD.md) (需求) · [HARNESS_ENGINEERING.md](./HARNESS_ENGINEERING.md) (方法论) · [CLAUDE_CODE_SESSIONS.md](./CLAUDE_CODE_SESSIONS.md) (App 侧 Session，务必在 **Admin Session A1 启动前** 完成 App Session 0-3)

---

## 使用指南

### Admin Session 在整体 Roadmap 中的位置

Admin 依赖 App 侧 **数据层 + Pipeline + 分析 API**，因此必须排在 App Session 3 之后：

```
┌────────── App 侧 ──────────┐  ┌──────────── Admin 侧 ────────────────┐
│                            │  │                                      │
│  Session 0  脚手架           │  │                                      │
│  Session 1  爬取引擎         │  │                                      │
│  Session 1.5 平台数据图谱    │  │                                      │
│  Session 2  Pipeline         │  │                                      │
│  Session 3  分析+API+MCP    │  │                                      │
│                            │─▶│  Session A0  Admin 认证脚手架          │
│                            │  │  Session A1  Admin 脚手架+账号+审计    │
│  Session 4a 用户+Onboarding │  │  Session A2  Pipeline Dashboard+Planner│
│                            │  │  Session A2.1 Planner (Prompt+Profile) │
│                            │  │  Session A2.2 Tracker (Attempt+引擎)   │
│                            │  │  Session A2.3 Tracker (Trace)+变更审批 │
│                            │  │  Session A2.4 Analyzer (质量+QA)       │
│                            │─▶│  Session A3  KG 运营中心               │
│  Session 4b Dashboard+报告  │  │                                      │
│                            │─▶│  Session A4  成本/告警/商务/MCP        │
│  Session 5  上线打磨         │  │                                      │
└────────────────────────────┘  └──────────────────────────────────────┘
```

### 每个 Admin Session 的 Pre-Flight

```
PRE-FLIGHT ✈️ (人类, 10-15min)
  □ App Session 3 已完成 (Analytics API + MCP 可用)
  □ 阅读本文件中对应 Session 的 Prompt
  □ 阅读 docs/ADMIN_PRD.md 对应模块
  □ 阅读 docs/DESIGN_TOKENS.md (若涉及 UI)
  □ 确认 frontend-admin/ 骨架可启动 (从 A1 起可用)
  □ Git 状态干净，复制 Prompt 给 Claude Code
```

### Admin 的 Phase Gate

见 `ADMIN_PRD.md §8.4`。人类 Review 在 A1+A2 / A3 / A4 后各有一次。

---

## §0. Session Prompt 编写公约 (2026-04-21 固化规则 1-8, 2026-04-22 追加规则 9, 2026-04-23 追加规则 10-12, 全 Admin + App + UI Prototype Session 必遵守)

> 🛡️ **为什么有这一段**: Session A0 实施时发现 `forcePasswordChangeAt` vs `mustChangePasswd` 的命名偏离, 根因是 A0 Prompt **独立重抄了** PRD §5.6 的 AdminUser schema, 两处维护必然 drift; A0 宣绿后 64 个文件 untracked 触发规则 9 追加。本公约固化 9 条规则, 防止 A1-A5 及后续 Session 重蹈覆辙。

### 规则 1: 真相源 (Source of Truth) 锚定

Session Prompt 内**禁止**完整重抄下列真相源中的定义:

| 真相源 | 管辖范围 | 禁止重抄的对象 |
|---|---|---|
| `ADMIN_PRD.md §5.6.8` | `admin_*` 表字段完整定义 | model AdminUser / AdminSession / AdminLoginAttempt / AdminPasswordReset 的 Prisma 字段清单 |
| `ADMIN_PRD.md §4.1.4 / §4.2.x / §4.3.x / ...` | 各 Module 业务表字段 | 业务表 Prisma 模型字段 |
| `ADAPTER_CONTRACT.md` | 引擎契约 (错误码 / 状态机 / 副作用边界) | 9 种 AdapterError / 账号 6 状态机 / 代理调度规则 |
| `DESIGN_TOKENS.md C1-C15` | UI 视觉/结构契约 | 色值 / 间距 / 图表规则 |
| `TEST_STRATEGY.md §9-§13` | 测试矩阵 | 异常覆盖矩阵 / Admin 测试矩阵 / P0-P2 优先级 |
| `schema.prisma` | Prisma 当前运行状态 | 现有模型和 FK 关系 |

**正确写法**:
```markdown
## 1. Prisma schema 扩展
字段形状按 **ADMIN_PRD.md §5.6.8 (admin_users 行)** 为准, 本 Session 仅追加以下字段:
- `foo String @default("bar")`  // 对应 PRD §X.Y.Z 新需求
**禁止**在本 Prompt 内重写完整 model AdminUser { ... } 字段清单。
```

**错误写法** (导致 A0 Q2 偏离的模式):
```markdown
## 1. Prisma schema 扩展
model AdminUser {
  id               String   @id @default(cuid())        // ← 独立指定, 与 PRD/schema 不同步就 drift
  forcePasswordChangeAt DateTime? ...                    // ← 独立命名, 可能与 PRD 相悖
  ...(20 字段)
}
```

### 规则 2: 前置 Grep 契约 (Pre-Flight Grep Contract)

所有涉及 schema / PRD 字段/ 端点定义的 Session, **第一步必跑**下列 3 条 grep, 报告给人类后再动代码:

```bash
# G1: 检查 seed / script / code 是否有旧值硬编码 (以本次变更字段为关键词)
grep -rn "<字段名>.*['\"]<旧值>['\"]" backend/prisma backend/scripts backend/src

# G2: 检查文档 (PRD 系列 / SESSIONS / DATA_MODEL / ADAPTER_CONTRACT) 是否已固化字段形状
grep -rn "<字段名>\|<表名>" docs/

# G3: 检查代码下游引用 (FK / relation 字段 / TS 类型)
grep -rn "<表名>\.<字段名>\|<表名>\\s*\\{[^}]*<字段名>" backend/
```

人类看到 grep 结果后, 任何命中都必须做决策 (同步改? 迁移? 撤回当前改动?), **不允许 Claude Code 自行合并绕过**。

### 规则 3: 偏离必记录 (Deviation-Record Contract)

Session 完成时, 若实际交付偏离了原 Prompt 或任一真相源, 必须在 CLAUDE.md 新增决策的 "C. 偏离说明" 段记录, 分两小段:

- **C1. 偏离原 Prompt (N 处)** — 每处写"理由"(为什么偏离) + "源偏离方向"(对齐 PRD / 对齐 schema / 对齐项目风格)
- **C2. 偏离真相源 (PRD / ADAPTER_CONTRACT / DESIGN_TOKENS) (N 处)** — 每处写"理由" + "Phase 2 收敛计划"(如何在未来消除此偏离)

A0 的决策 #24 "C1/C2" 结构是标准模板, 后续 Session 沿用。

### 规则 4: 真相源双向同步 (Bidirectional Sync)

若 Session 实施过程中**发现真相源本身**有遗漏 / 错误 / 内部矛盾 (例如 PRD §4.1.4 和 §5.6.8 对 admin_users 字段清单不一致), 必须:

1. 立即停止实施, 报告给人类
2. 由人类决定: (a) PRD 改 / (b) 实施按 PRD 现状走并在 C2 记录 / (c) 撤回本次改动
3. 若选 (a), Session 完成时同步提交 PRD 修正 + schema + Prompt 三处改动在同一 commit

### 规则 5: Session Prompt 的 §1 必须声明"真相源索引"

每个 Session 的 Prompt §1 开头**必须**列出本 Session 涉及的真相源锚点, 示例:

```markdown
## 1. <本 Session 主题>

**真相源索引** (实施前必读, 有歧义以下列为准):
- 字段 / 表定义 → ADMIN_PRD.md §5.6.8 + schema.prisma:656-720
- 契约 / 错误码 → ADAPTER_CONTRACT.md §5 (账号) + §6 (错误码)
- UI / 样式 → DESIGN_TOKENS.md C1-C15
- 测试 / 覆盖 → TEST_STRATEGY.md §10 (Admin 测试矩阵)
- 前置决策 → CLAUDE.md #9 / #21 / #22 / #23 / #24
```

### 规则 6: 引用 PRD 段号必须锚定到最小单元

禁止粗略引用 "见 PRD §5"。必须精确到 `§5.6.4-8` 或 `§5.6.8 表中 admin_users 行`, 以便 grep 验证 + diff 工具追踪。

### 规则 7: Session 完成时反查一致性

每个 Session 完成时, 最后一步**必须**运行:

```bash
# 1. schema.prisma 字段与 PRD 真相源段落逐字段对比 (人工或脚本)
# 2. Session Prompt 内 §1 真相源索引列出的段落编号, grep 在对应文件真实存在
# 3. CLAUDE.md 新增决策 "C. 偏离说明" 段已写, 条目数 = 实际偏离数
```

不一致 → 不能 merge, 补齐后重跑。

### 规则 8: Cross-Session Boundary 反向同步 (2026-04-21 固化)

**场景**: Session X 实施完成, 新增/改名/删除了真相源 (PRD / schema.prisma / CLAUDE.md 决策) 中的字段、表、端点、常量。下游**未开工**的 Session Y-Z 的 Prompt 里引用的字段清单 / 表结构 / 函数签名 **必须同步**, 否则 Y-Z 开工时 CC 按陈旧 Prompt 落地会产生:
1. **phantom 字段** — Y Prompt 列出的字段在 X 完工后已不在真相源 (Y 若直接照抄, 会引入不应存在的 DB 列)
2. **漏字段** — X 新增字段未同步到 Y Prompt, Y 开工会产生 schema diff 冲突
3. **函数签名 drift** — X 重构的函数签名 Y Prompt 仍引用旧形状, CC 实施时自行"修复"造成二次偏离

**规则**:

1. Session X 完工时 (CLAUDE.md 决策号登记 + `grep 反查` 通过后), **必须**在 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` / `docs/CLAUDE_CODE_SESSIONS.md` 里 grep 下游 Session 对 X 产出字段 / 表 / 函数的引用位置, 清单报告给 Frank
2. 若下游 Session Y/Z 的 Prompt inline 重抄了字段清单 (违反规则 1), 必须立即反向 patch 改为"按真相源 + 本 Session 增量"模式, 不得留给 Y/Z 开工时解决
3. 引用真相源段号时, **必须**附日期锚点: 格式 `§X.Y.Z (2026-MM-DD 固化版)` 或 `CLAUDE.md #N (2026-MM-DD)`, 让后来者一眼看出引用时的真相源状态, 过期或真相源变化时 grep 一次就能定位所有下游
4. 若 X 完工时发现 Y/Z 已在其他仓 / 其他文件也重抄了同一张表, 清单一次性更新所有 (见规则 4 · 双向同步的扩展)

**执行位置**: 每个 Session 的"完成后报告"段末尾, 新增一项: "下游 Session 同步清单 — grep 结果 N 处引用, 已全部反向 patch / 无命中 → 报告 Frank"。

**反例 (本规则触发源)**:
- Step 11.5 把 AdminUser phantom 扩 2 字段 (failedLoginCount / lockedUntil), 推入 A1 Prompt 前被 Step 11.6 拦截
- A0 实落 AdminUser 扩 3 字段 (forcePasswordChangeAt / lastPasswordAt / lastLoginAt), A1 §2 inline schema (line 452) 既未同步删除 phantom `totp_secret?` 也未同步补充 3 字段, Step 13 反向 patch

### 规则 9: Session 完工即 commit (Commit Closure Contract, 2026-04-22 固化)

**场景**: Session A0 连过 6 Step (11/11.5/11.6/12/13/14) Phase Gate 9/9 全绿后, Frank 执行 `git status` 发现 working tree 还有 64 个文件 (15 modified + 49 untracked) 一个 commit 都没打。后果:

1. CLAUDE.md #24/#25 决策登记没进 git history, 未来 `git blame` / `git log -S` 查不到
2. 下一 Session 改到 `schema.prisma` / `ci-check.mjs` 会和 A0 未 commit 改动混在 diff 里, 不可读
3. 若下一 Session 出问题要回滚, 会把 A0 成果一起滚掉
4. 等同于没有真正"关闭" Session — 工程断点不明确

**规则**: 每个 Session (App / Admin / UI Prototype) 宣绿 (Phase Gate 全过 + CLAUDE.md 决策号登记 + 规则 8 反向同步清单产出) 之后, **必须立即执行 git commit**, 把本 Session 全部产出打包成一个 (或语义分组的多个) commit。未 commit 即宣绿 = 本 Session 未真正关闭。

**commit 落地规范**:

1. **commit 命令** — Frank 在 Windows, 用 PowerShell here-string + `git commit --file`, 避免 bash HEREDOC:
   ```powershell
   $msg = @"
   Session {号}: {主题} - Phase Gate X/X PASS

   本 Session 交付 (参见 CLAUDE.md #{决策号}):
   - {类别 1}: ...
   - {类别 2}: ...
   - ...

   回引: CLAUDE.md 决策 #{N} ({主题}); 相关决策 #{M} / #{K}.
   "@
   $msg | Out-File -FilePath commit-msg.txt -Encoding utf8
   git commit --file commit-msg.txt
   Remove-Item commit-msg.txt
   ```

2. **commit 标题格式** — 固定 `Session {号}: {主题} - Phase Gate X/X PASS` (例如 `Session 2: Pipeline Planner - Phase Gate 9/9 PASS`)

3. **commit body 必含** — (a) 回引 CLAUDE.md 新增决策号 + 相关前置决策号; (b) 按类别列交付清单 (schema / planner / API / test / harness / docs 等分段)

4. **Unicode 安全** — commit message 禁用 `§` / `✅` / `—` / `🚫` 等特殊 Unicode (PowerShell UTF-8 可能乱码), 用 ASCII 替代: `第 X 节` / `PASS` / `-` / `禁止`

5. **staging 策略** — 按需 `git add backend/ scripts/ docs/` 细化, **不建议** `git add -A` (容易把本不该 commit 的临时产物 / 截图 / 草稿拉进来); staging 后 `git status --short` 复核清单

6. **验证 closure** — commit 完成后**必跑** `git log --oneline -3`, 把输出贴回"完成后报告"作为 closure 证据, 无此证据 = Session 未真正关闭

7. **push 时机** — `git push` 不是 Session 完工硬要求, Frank 决定时机 (若 repo 有 remote, 建议每个 Session commit 后推一次作为备份)

**执行位置**: 每个 Session 的"完成后报告"段末尾固定一项 "F · git commit 步骤", 列 staging 列表 / commit message 草稿 / commit 后 `git log --oneline -3` 输出。A1-A5 及后续 Session 均按此格式。

**与规则 8 的关系**: 规则 8 (反向同步清单) 产出后 → 规则 9 (commit closure)。顺序不可颠倒 — 未同步清单就 commit 会让反向 patch 散落在下一个 commit 里, 失去"一个 Session = 一个可回滚节点"的干净度。

### 规则 10: MVP Scope-Cut Declaration (2026-04-23 固化, Session 1.2 结构性缺陷触发)

**场景**: Session 1.2 原 Prompt §1-§8 覆盖 Camoufox + humanize + 3 引擎真实 execute + CAPTCHA + Account Pool Prisma + HAR + auto-register + L4 staging smoke, 正常是 2-3 个 Session 的量。原 Prompt 没有"本 Session 做 / 不做"剪裁段, CC 实施时只能"尽力往前推", 结果 §0.3 双修正预先登记 (MVP 3 引擎口径 + 6 枚举 fallback labeling, 2026-04-22 决策) 消耗完整个 atomic batch 预算, §1-§8 主体一步未动 (commit 5f05229 只交付了 schema + harness 对齐)。根因: 原 Prompt 没有强制 MVP 剪裁段。

**规则**: 每个 Session Prompt **必须**在 §2 (或等效紧跟真相源索引的位置) 显式声明"本 Session 做 / 不做" 二分段:

```markdown
## 2. MVP 范围剪裁 (严格遵守, 不自作主张扩)

**本 Session 做**:
- §X.Y <具体子项> → 预期产出 <1 行>
- ...

**本 Session 不做 (明确延后)**:
- §A.B <具体子项> → 延后理由 + 后继 Session 编号 (如 "Fix Session 1.2.1")
- ...
```

"做" 与 "不做" 必须各列具体子项 + Session 段号锚点 (§X.Y 形式), **禁止**写 "核心功能" / "爬取框架" / "主体流程" 这类粗略字眼。CC 开工时 §2 是第一道边界, **任何超出 §2 "做" 列表的工作必须触发规则 12 的 STOP 类型 C, 报告 Frank 后再决定**。

**反例 (本规则触发源)**: Session 1.2 原 Prompt 只有 §1-§8 任务清单, 无"本 Session 不做"段, CC 遇到 2026-04-22 落地的新决策冲突时, 只能自主决策要不要拖入本 Session, 导致范围不可控。续推 Prompt (2026-04-23) 的 §2 是规则 10 的标准样板。

### 规则 11: Pre-Send Decision-Freshness Check (2026-04-23 固化)

**场景**: Session 1.2 原 Prompt 写于 2026-04-21, 发送给 CC 前未回查 2026-04-22 新落地的决策 / 记忆 (MVP 3 引擎口径 + `feedback_genpano_no_api_scraping.md` 6 枚举 fallback labeling)。CC 开工按陈旧 Prompt 拿到旧引擎枚举, 与当前真相源矛盾, 只能停下做"双修正预先登记"消耗整 Session 预算。

**规则**: Session Prompt 发送给 CC **前 30 分钟内**, 发送人 (Frank / 协作者 / Cowork Claude) **必须**跑下列 freshness check 3 条, 任一命中都要在 Prompt §1 真相源索引补齐引用或直接撤回本次 Prompt 重写:

```bash
# F1: 近 3 条 CLAUDE.md 决策 (最近几天可能落地的新规则)
tail -400 CLAUDE.md | grep -nE "^[0-9]+\. \*\*" | tail -5

# F2: docs/auto-memory/ 近 7 天新增 feedback / project 记忆
git log --since='7 days ago' --diff-filter=A --name-only -- docs/auto-memory/

# F3: 本 Session 涉及表 / 字段的近期 migration (与 Prompt §0.3 声明对齐)
ls -lt backend/prisma/migrations/ | head -5
```

如有命中, 发送人必须回答 3 问后再决定是否发出:
1. 新决策 / 记忆 / migration 是否影响本 Prompt 任一章节的前提条件?
2. 若影响, 把新决策号登记进 Prompt §1 真相源索引, 明确是"引用"还是"修改"
3. 若冲突到 Prompt 任务清单本身, 重写相关段落再发送 (不能指望 CC 开工时自己发现)

**与规则 4 (Bidirectional Sync) 的关系**: 规则 4 是"真相源改动时反查所有下游引用" (Push 模式), 规则 11 是"Prompt 发送前反查真相源近期变化" (Pull 模式)。两条方向相反, 互补不可替代。规则 4 要求修改真相源的 PR 同时 patch 下游 Session Prompt, 规则 11 是兜底 — 即使规则 4 执行不彻底, 发送前这一轮 grep 也能拦住陈旧 Prompt。

### 规则 12: Explicit STOP-Trigger Template (2026-04-23 固化)

**场景**: Session 1.2 原 Prompt 没有列"什么情况下 CC 应该立即停下来问人类", CC 实施遇到 `prisma generate EPERM on Windows` 时自行绕过 (走 `prisma validate` 代替), 结果虽然良性, 但若是"Camoufox 装不上" / "真相源自相矛盾" / "范围溢出 §2" 这类更严重情况, CC 同样可能自作主张降级, 把决策熵悄悄推给未来 (例如降级到 chromium 会穿透 Session 1 锁定的"Camoufox 作为反检测真相源"决策, 后患无穷)。

**规则**: 每个 Session Prompt 必须固定一段 STOP 触发条件模板, 位置一般在"开工第一批动作"之前或紧跟 §3 硬约束之后, 三类必含:

```markdown
## 4. STOP 触发条件 (满足任一立即停下, 不自作主张降级)

**类型 A · 环境依赖失败**:
- <依赖 1> 装不上 / fetch 0 节点 / API key 401 → STOP 报告 3 条: (a) 失败 log; (b) 判断是环境问题还是代码问题; (c) 提议方案 (升版本 / 换后端 / 走降级 stub / 延后该子项)

**类型 B · 真相源与 Prompt 冲突**:
- Prompt §X.Y 引用的字段 / CHECK 约束 / 路径常量, grep 时发现真相源已是别的值 → STOP 报告当前真相源状态 + 建议: (a) 改 Prompt; (b) 改真相源; (c) 撤回本次改动

**类型 C · 范围溢出 §2 "做" 列表**:
- 实施到 §N 时发现必须动 §2 "不做" 里的某项才能继续 → STOP 报告: (a) 为什么必须动; (b) 是否可以 stub 兜底; (c) 拆新 Session 接手的提议

**禁止项**: 任何"类型 A/B/C 命中但 CC 自行降级 / 兜底 / 扩范围后继续" 的行为都属公约违反, 下次 Session 复盘时必须登记进"偏离说明 C 段"。
```

三类 STOP 条件是**下限**。Session 特异的 STOP 触发 (如 Session 1.2 续推 Prompt 的"Camoufox 失败禁切 chromium" / "recorder.ts 不抓 secret 禁改 HAR fixture 行") 必须在该模板下**增补**, 不得删减 A/B/C 三类底板。

**反例 (本规则触发源)**: Session 1.2 原 Prompt 没有 STOP 模板, CC 遇到 prisma generate EPERM 时自行 workaround 走 validate 替代, 结果良性; 但若是 Camoufox 装失败, 很可能被静默降级到 chromium, 穿透 Session 1 决策。续推 Prompt §4 是规则 12 的标准样板。

**与规则 3 (偏离必记录) 的关系**: 规则 12 是"STOP 时机"契约, 规则 3 是"事后偏离记录"契约。理想路径: 规则 12 触发 STOP → Frank 决策 → 执行按决策走 → 规则 3 登记 C 段。跳过 STOP 直接自行偏离, 规则 3 就只能补"为什么偷着改", 工程质量下降。

---

> 以下 Session (A0-A5) 从 2026-04-21 起逐步对齐本公约, 凡是仍内嵌完整 schema 的段落在对应 Session 实施时现场重构为"参考真相源 + 仅列增量"模式。

---

## Session A0 · Admin 认证脚手架 & 登录页

### 前置依赖

无 (第一个 Admin Session)

### 目标

搭起 Admin 平台的**认证层基础设施**：登录页、会话管理、密码重置、重新认证网关，以及后续 Sessions 依赖的关键数据表。

### 交付物

- `/admin/login` 登录页 (左环境色带+右表单, 与 App AuthPage 结构对齐但色调区分)
- Admin 认证中间件 (JWT HttpOnly cookie, access 15min + refresh 7d)
- `admin_users` / `admin_sessions` / `admin_login_attempts` / `admin_password_resets` 表
- Seed script: `npm run admin:bootstrap` 创建首个 super_admin (幂等)
- Silent refresh 机制 + SessionExpiredModal
- Re-auth gate: 距上次认证 > 30min 的特权操作需要密码确认
- Admin route guard: 未登录 → redirect `/admin/login`

### PRD 对应

ADMIN_PRD.md §5.6 (会话管理) + §6.1-6.2 (登录页设计)

### 三层 QA

**Executable Acceptance**:
- [ ] seed 脚本可重复执行, 第二次不报错
- [ ] 登录成功后 cookie 包含 HttpOnly + Secure + SameSite=Strict
- [ ] 错误密码 5 次 → 第 6 次 429, 15min 后恢复
- [ ] Access token 过期 → silent refresh 自动续期, 用户无感
- [ ] 新 tab 打开 admin 页 → 自动 silent refresh 而非弹登录框
- [ ] 首次登录强制改密码

**Adversarial**:
- [ ] 直接访问 /admin/pipeline/overview 未登录 → redirect /admin/login
- [ ] 伪造过期 JWT → 401 而非 500
- [ ] Refresh token 被 revoke 后 → 401 + SessionExpiredModal
- [ ] CSRF: 跨域 POST /admin/api/v1/auth/login → 被 SameSite 拦截

**Spec Compliance**:
- [ ] `admin_sessions` 表 schema 符合 §5.6 定义
- [ ] 所有登录/登出/失败写入 `admin_audit_log`
- [ ] 密码 bcrypt cost=12, 最少 12 字符含大小写+数字

### Prompt

````
你是 GENPANO Admin 的实施 Session A0。

本 Session 是 **Admin 模块的第一件事** — 搭建认证层基础设施。后续所有 Admin Session (A1-A5) 均依赖本 Session 产出的 4 张 admin 表 + JWT 中间件 + `/admin/login` 登录页。**未完成 A0, A1 无法启动**。

请先按顺序读入以下文件:
- CLAUDE.md (全局决策, 特别是 #9 Auth-Required / #21 Review 修复闭环 / #22 Session 1 / #23 Session 1.5)
- docs/ADMIN_PRD.md §5.6 (会话管理全文) + §6.1-6.2 (登录页 + 环境色带设计)
- docs/DESIGN_TOKENS.md (C1-C15 契约, 尤其 --color-env-* 环境色带)
- frontend/src/pages/AuthPage.jsx (App 侧 email-first 2-step 登录页, A0 不复用状态机但复用左色带 + 右表单骨架)
- backend/prisma/schema.prisma (**A0 就地扩写 Session 0-rev 已建的 `AdminUser` + 新增 3 张 admin 表**，AuditLog 不碰)
- backend/package.json + backend/tsconfig.json (Session 1.5 已建立 ts 基座, A0 扩展而非重建)

---

## 1. Prisma schema 扩展 (backend/prisma/schema.prisma)

**真相源索引** (依 §0 规则 5 声明, 实施前必读, 歧义以下列为准):
- `admin_*` 表字段定义 → **ADMIN_PRD.md §5.6.8** (唯一权威, 含 CHECK constraint + 字段语义补注)
- Session 0-rev 现状 → `schema.prisma:656-690` (AdminUser + AuditLog 已存在, 本 Session 就地扩写 AdminUser, AuditLog 不碰)
- 下游 FK → `schema.prisma:605` (AccountState.adminOperatorId) / `:675` (AuditLog.operatorId) / `:716` (BrandSubmission.adminOperatorId), 三者 `@db.Uuid` 锁死, 本 Session 不触动

**实施动作** (依 §0 规则 1, 禁止在本段重写完整 model 字段清单, 仅描述增量):

**A. `AdminUser` 就地扩写 (schema.prisma:656)** — 按 **PRD §5.6.8 admin_users 行** 当前字段清单比对现有 schema, 追加缺失字段:
- 追加 `forcePasswordChangeAt DateTime? @default(now())` (对齐 PRD §5.6.4, 语义"bootstrap 后首次登录强制改密", 改密成功置 null)
- 追加 `lastPasswordAt DateTime?` (对齐 PRD §5.6.8 补注, re-auth gate 判据)
- 追加 `updatedAt DateTime @updatedAt` (若 Session 0-rev schema 没有)
- 字段 `role` default 从 `"ops"` 改为 `"super_admin"` (对齐 PRD §5.1 MVP 约束)
- 其他字段保留 Session 0-rev 既有形态不动 (`id` 保持 `@db.Uuid @default(dbgenerated("gen_random_uuid()"))`, `role/status` 保持 `String`)

**B. 新增 3 张表** — 字段清单**严格按 PRD §5.6.8** 对应行 (admin_sessions / admin_login_attempts / admin_password_resets), Prisma model 名为驼峰 (`AdminSession` / `AdminLoginAttempt` / `AdminPasswordReset`), 字段名 snake_case 映射到 camelCase。所有 `id` 与 FK `userId` 用 `@db.Uuid @default(dbgenerated("gen_random_uuid()"))` 对齐项目基座。

**C. Migration raw SQL (在 `admin_auth_foundation` migration 内追加)** — CHECK constraint 按 **PRD §5.6.8 末段 "CHECK constraint (MVP 初始值)"** 逐字落地:

```sql
-- default 修正 + 现存 role='ops' 数据迁移 (若 grep G1 命中)
UPDATE admin_users SET role = 'super_admin' WHERE role = 'ops';

-- CHECK constraints, 语义对齐 PRD §5.1 "MVP: CHECK (role IN ('super_admin'))"
ALTER TABLE admin_users ADD CONSTRAINT admin_users_role_chk
  CHECK (role IN ('super_admin'));
ALTER TABLE admin_users ADD CONSTRAINT admin_users_status_chk
  CHECK (status IN ('active', 'suspended'));
```

**D. `AuditLog` (schema.prisma:673) 完全不碰** — A0 所有登录事件只写 `admin_login_attempts`; logout 事件保留 `console.info + TODO("A1 写入 audit_logs")` 占位。A1 按 ADMIN_PRD §5.2 再决定 `audit_logs` 的 consolidate/rename。

**E. 前置 Grep 契约** (依 §0 规则 2, 执行 A-C 前必跑, 结果报告给人类后再动代码):

```bash
# G1: seed / script / code 有无 role='ops' 硬编码
grep -rn "role.*['\"]ops['\"]\|role:\s*['\"]ops['\"]" backend/prisma backend/scripts backend/src

# G2: 文档是否固化了 admin_users 字段形状 (以便同步改)
grep -rn "admin_users\|AdminUser" docs/ADMIN_PRD.md docs/DATA_MODEL.md docs/ADMIN_PRD_*.md

# G3: 代码下游引用 FK
grep -rn "adminOperatorId\|admin_user_id" backend/
```

三条任一命中 → 贴报告给人类决策后再动 migration; 无命中 → 直接按本段 A-D 执行。

Prisma migration 命名: `admin_auth_foundation`.

## 2. JWT 中间件 (backend/src/admin/auth/)

- `jwt.ts` — 发 access/refresh, 用 jose 库, HS256, 读 ADMIN_JWT_SECRET (env, 不得硬编码)
- `cookies.ts` — HttpOnly + Secure + SameSite=Strict + Path=/admin
- `middleware.ts` — Next.js `middleware.ts` 注入: 访问 /admin/** (除 /admin/login + /admin/api/v1/auth/**) 校验 access cookie, 过期 → 触发 silent refresh, refresh 失败 → 302 /admin/login?reason=session_expired
- `reauth-gate.ts` — `requireRecentAuth(maxAgeMs = 30*60*1000)` 返回 middleware, 用于特权操作 (删除用户 / 撤销 API Token / 改 Tier 参数等)。判据: `lastPasswordAt` 距 now < 30min。

## 3. 登录页 `/admin/login` (frontend/src/admin/pages/AdminLoginPage.jsx)

- 左侧 480px 色带 (env-aware: dev=绿 `--color-env-dev` / staging=橙 `--color-env-staging` / prod=红 `--color-env-prod`, 读 `import.meta.env.VITE_ENV_NAME`)
- 右侧表单: email + password + Sign In, Inter font, p-8 card
- 错误态: 红色 toast, 不暴露 "Email 不存在" (统一返 "邮箱或密码错误", anti-enum)
- 首次登录 (`forcePasswordChangeAt && forcePasswordChangeAt <= now()`) → 登录成功后强制跳 `/admin/change-password` 再进 `/admin/dashboard`；改密成功后把字段置 null 清除强制
- 样式全部消费 DESIGN_TOKENS.md, 禁 inline hex
- **不复用 AuthPage 的 email-first 2-step 状态机** (Admin 面向已知账号, 不做 identifier-lookup 分岔)

## 4. `/admin/api/v1/auth/**` 端点

- POST `/auth/login` (body: email, password) → 200 set cookies + user; 401 统一 "邮箱或密码错误"; 429 + Retry-After
- POST `/auth/refresh` → 200 rotate access + refresh (refresh 一次性, 旧的立即 revoke, 防 replay)
- POST `/auth/logout` → 撤销 session + 清 cookie + broadcast
- POST `/auth/forgot-password` (body: email) → 总返 200 (anti-enum), 若 email 存在则发 Resend 邮件 (引用 App 的 Resend client, 新模板 admin-password-reset zh/en 双语)
- POST `/auth/reset-password` (body: token, newPassword) → 校验 token + 强度 + 写入 + 撤销用户所有 session
- POST `/auth/change-password` (需 access cookie, body: oldPassword, newPassword) → 首次登录 + 主动改密共用

密码策略: bcrypt cost=12, ≥12 字符 + 大写 + 小写 + 数字, zxcvbn score ≥ 3.

## 5. 防暴力破解 (rate limit)

- 同 email: 5 次失败 → 15min lock (LockKey `login_fail_email_${email}`, 本地 Map + TTL 即可, MVP 不引 Redis)
- 同 IP: 20 次失败 / 10min → 临时 block
- 锁定期间 POST /auth/login → 429 + `failureCode='RATE_LIMITED'` 写 `admin_login_attempts`
- 锁定计数器仅在同一进程内生效 (MVP 够用), Phase 2 抽到 Redis — 在本 Session 代码里加 TODO 注释。

## 6. Seed script `backend/scripts/admin-bootstrap.ts`

命令: `npm run admin:bootstrap`
- 读 env `ADMIN_BOOTSTRAP_EMAIL` + `ADMIN_BOOTSTRAP_PASSWORD` (若缺则 prompt 交互式输入)
- upsert AdminUser (role=super_admin, forcePasswordChangeAt=now(), status=active)
- **幂等**: 重复执行只更新 passwordHash + updatedAt, 不报错, 不覆盖 lastLoginAt
- 输出:
  `Admin bootstrap complete. Email: ${email}. First-login password must be changed at /admin/login.`
- 写入 DATABASE_URL 前先 echo 目标 URL (只印 host + db, 不印密码), 让 Frank 确认不是误连 prod

## 7. Silent refresh + SessionExpiredModal (frontend/src/admin/components/)

- `AdminAuthProvider.jsx` — fetch wrapper 拦截 401 → POST /auth/refresh 重试一次 → 仍 401 则开 SessionExpiredModal
- `SessionExpiredModal.jsx` — Radix Dialog, 标题 "会话已过期, 请重新登录", 单按钮跳 `/admin/login?redirect=<当前路径>`
- `BroadcastChannel('admin-session')` 跨 tab 同步: tab A logout → tab B 同步弹 modal
- Silent refresh 必须在 access 过期前 60s 主动触发 (setTimeout 轮), 避免请求突然 401 的"坏抖动"

## 8. Route guard (middleware.ts + AdminRouteGuard.jsx)

- Next.js middleware 层: 所有 /admin/** 非白名单路径 → 校验 access cookie → 无则 302 /admin/login?redirect=<path>
- 白名单: `/admin/login`, `/admin/change-password` (仅 `forcePasswordChangeAt && <= now()` 可访问), `/admin/forgot-password`, `/admin/reset-password/[token]`, `/admin/api/v1/auth/**`
- 前端 `<AdminRouteGuard>` HOC 二次校验, 避免 middleware 短路后仍渲染骨架
- 非 admin 域名访问 /admin/** 一律 404 (此约束 A1 会扩到 hostname 判定, A0 先做 cookie 校验)

## 9. 审计日志最小落地

A0 不建 `admin_audit_log` 全表 schema (留给 A1 按 PRD §5.2 建), 但**必须**写 `admin_login_attempts` 的 3 种事件:
- `login_success` (success=true, failureCode=null)
- `login_failed` (success=false, failureCode ∈ {WRONG_PASSWORD, USER_SUSPENDED, RATE_LIMITED, UNKNOWN_EMAIL})
- logout 事件 A0 先记 console.info + TODO 注释, 待 A1 admin_audit_log 表建好后回填

## 10. 测试

Vitest 单测 (覆盖率 ≥ 80%, 同 Session 1.5 阈值):
- bcrypt 校验 (cost=12 强制 + 弱密码拒绝 6 例)
- JWT 发 + 验 (access/refresh 生命周期 + 伪造拒绝 + 过期拒绝)
- rate limit 触发 (email 5 次 / IP 20 次 / 锁定期 429 + Retry-After)
- 密码强度 zxcvbn 分档 (score < 3 拒绝 + score ≥ 3 通过)

集成测试 (延到 Session 1.2 / A1, A0 写占位 describe.skip):
- POST /auth/login → set cookie → GET /admin/api/v1/users → 401 (因 A1 未实现)
- 锁定 5 次失败后 429

Harness 新增 3 条 (Group D 扩展, 落到 `scripts/ci/harness-D.sh` 或 `scripts/ci-check.mjs` Group D 段):
- **D8** `admin-jwt-secret-must-be-env` — grep `ADMIN_JWT_SECRET\s*=\s*['"][^'"$]` = block (硬编码字符串)
- **D9** `admin-password-hash-bcrypt-cost-12` — grep `bcrypt\.hash\s*\([^,]+,\s*(\d+)` 捕获 cost, 必须 ≥ 12 或引用常量 `BCRYPT_COST`
- **D10** `admin-session-cookie-samesite-strict` — grep cookie 配置必须 `sameSite:\s*['"]strict['"]` 或 `SameSite=Strict`

`__ci_fixtures__/` 各加 1 条 self-seeded 违规 fixture, 运行 `npm run ci:harness:selftest` 期望值从 8 扩到 **11**, 全绿才能 merge.

## 11. 文档收尾

**A. `CLAUDE.md` 新增决策 #24 "Session A0 · Admin 认证脚手架交付 (2026-04-21)"**, 沿用 #22/#23 的分段法, 但必须包含**六段** (比 #22/#23 多一段 C):

- **A. 目标** — 为后续 Admin Session A1-A5 搭认证层地基
- **B. 文件清单** — 新增/修改的所有路径
- **C. 偏离说明 (2026-04-21 对齐, 不可省略)** — 记录以下偏离原因, 方便 A1 接手时理解决策链。分两段:

  **C1. 偏离原 A0 Prompt (4 处，均为对齐项目/PRD 真相源)**:
  1. `AdminUser.id` 从原 Prompt 的 `cuid()` 改为 `@db.Uuid @default(gen_random_uuid())` — 与项目现有 15+ 张 uuid 表基座一致, 避免连锁改 3 个下游 FK (AccountState/AuditLog/BrandSubmission.adminOperatorId)
  2. `role` / `status` 从原 Prompt 的 `enum` 改为 `String + CHECK constraint` — 与项目 String-based 字段风格一致, migration 扩取值时更灵活 (Phase 2 不用跑 ALTER TYPE)
  3. `AdminUser` 就地扩写 Session 0-rev 既有模型 (schema.prisma:656), 不新建 — 保留所有下游 FK, 仅追加 `forcePasswordChangeAt` + `lastPasswordAt` 2 字段 + default 修正 + CHECK constraint
  4. 字段命名用 `forcePasswordChangeAt DateTime?` 非 `mustChangePasswd Boolean` — 对齐 PRD §5.6.4-8，修正原 A0 Prompt 的错译（DateTime 保留 Phase 2 "延时强制 / 特定日期后强制" 能力，MVP 代码路径仅增 `&& <= new Date()` 一处判断，零复杂度成本）

  **C2. 偏离 ADMIN_PRD (1 处，intentional MVP 安全收紧)**:
  5. `role` CHECK constraint 只允许 `'super_admin'` 单值，非 PRD §5.1 列举的 5 值 allow-list (`super_admin` / `ops` / `data_ops` / `support` / `bizdev`) — MVP 无创建非 super_admin 的 UI/API 路径，tight CHECK 防 SQL 直写绕过 (defense in depth)。Phase 2 RBAC 中间件落地时一起 `ALTER TABLE admin_users DROP CONSTRAINT admin_users_role_chk; ADD CONSTRAINT admin_users_role_chk CHECK (role IN (...5 值...));` 放宽
- **D. 契约** — JWT secret 必走 env / bcrypt cost=12 / SameSite=Strict / Path=/admin / access 15min + refresh 7d rotation
- **E. Harness 新规则** — D8 / D9 / D10 三条 + selftest 8→11
- **F. 下一步** — A1 按 PRD §5.2 决定 audit_logs 是扩字段/重命名/拆表

**B. 同步更新 "目录结构" 段**, 追加 `backend/src/admin/auth/**` + `backend/scripts/admin-bootstrap.ts` + `frontend/src/admin/pages/AdminLoginPage.jsx` + `frontend/src/admin/components/{AdminAuthProvider,SessionExpiredModal,AdminRouteGuard}.jsx`

**C. 新 env var 追加** — `ADMIN_JWT_SECRET / VITE_ENV_NAME / ADMIN_BOOTSTRAP_EMAIL / ADMIN_BOOTSTRAP_PASSWORD` 写入 `backend/.env.example` + `backend/README.md` "First-time setup" 段

**D. 依 §1 §E grep 结果条件性同步**:
- 若 `docs/DATA_MODEL.md` 命中 AdminUser 字段形状 → **必须同步**: 把 id/role/status 字段形状改为当前实现 (uuid + String + CHECK), 加"2026-04-21 Session A0 扩字段" changelog 条目
- 若 `docs/ADMIN_PRD.md §5.6` 固化了 AdminUser schema → **必须同步**: 字段形状对齐当前实现, §5.6 末尾补"2026-04-21 Session A0 对齐"脚注
- grep 全部无命中 → 跳过本段

## 12. Phase Gate 验收 (Frank 亲自跑)

1. `npm run admin:bootstrap` 创建 super_admin (幂等, 第二次不报错)
2. 打开 `/admin/login`, 输入 seed 账号 → 登录成功
3. 首次登录自动跳 `/admin/change-password`, 改密成功 → `/admin/dashboard` (A1 占位也行)
4. 浏览器 devtools 看 cookie: HttpOnly ✅ Secure ✅ SameSite=Strict ✅ Path=/admin ✅
5. 等 14-15min 后点任意 admin 页面 → silent refresh 无感续期 (看 Network 有一次 /auth/refresh)
6. 手动把 DB 里 session.revokedAt 置为 now() → 下次请求 → SessionExpiredModal 弹
7. 打开第二个 tab 登录同一账号 → tab A 点登出 → tab B 自动弹 SessionExpiredModal (BroadcastChannel 验证)
8. 错误密码连输 5 次 → 第 6 次 返 429 + Retry-After; 15min 后解锁
9. 调用受 `requireRecentAuth` 保护的假端点 (如 mock 的 `/admin/api/v1/privileged-test`) → 若距上次认证 > 30min 返 403 + `reauth_required=true`

---

**工程纪律**:
- 严格按 1-12 顺序执行, 每完成一步贴进度报告 + 贴新增/修改文件清单
- 所有 vitest 分支覆盖率保持 ≥ 80%, 新增 harness 规则必须 selftest 全绿
- 若遇任何冲突 (比如 schema 与 §23 已有表撞名) / 回滚 / 验证失败 → 立即停 + 详细报告, **不要自行修复绕过**, 先与 Frank 对齐再动

执行完成后回报: 新增文件清单 + vitest 覆盖率数字 + `npm run ci:harness:selftest` 输出 + CLAUDE.md 决策 #24 diff。
````

### Phase Gate

A-Gate 0 — Frank 能用 seed 账号成功登录 Admin, 执行一次特权操作触发 re-auth, 登出后页面正确跳转。

---

## Session A1 · Admin 脚手架 & 账号身份 & 审计

### 前置依赖

- Session A0 完成 (认证脚手架就绪)
- App Session 0-3 完成
- `admin.genpano.internal` 子域名 + IP 白名单（或 Cloudflare Access）就绪
- 已阅读 `docs/ADMIN_PRD.md` §3、§4.1、§5、§6

### 目标

搭起 Admin 的 **所有运营模块的共享基础设施**：路由组、布局、权限中间件、审计日志写入、命令面板。同时实现 Module A（账号 & 用户运营）。

### Prompt

```
你是 GENPANO Admin 的实施 Session A1。

请先阅读以下文件了解上下文:
- CLAUDE.md (项目全局)
- docs/ADMIN_PRD.md (Admin 需求，必读 §3, §4.1, §5, §6)
- docs/DESIGN_TOKENS.md (样式契约)
- frontend/src/layouts/DashboardLayout.jsx (App 侧侧栏结构参考)
- frontend/src/components/ui/Card.jsx + Badge.jsx (既有 UI 原子)

本 Session 覆盖 ADMIN_PRD §8.1 的 M1 + M7 + M8 三个 Milestone。

## 1. Admin 独立路由组 & 部署隔离

- Next.js App Router 下新建 `app/admin/**` 路由组
- 中间件: hostname === 'admin.genpano.internal' 时路由至 /admin/*，
  否则走 App 路由；非 admin 域名访问 /admin/* 全部 404
- 在 middleware.ts 中注入 Admin session cookie 校验，失败跳 /admin/login
- 环境变量: ADMIN_ALLOWED_IPS (逗号分隔), ADMIN_SESSION_SECRET

## 2. Admin 数据模型迁移 (Prisma)

**真相源**: 字段以 `ADMIN_PRD.md §5.6.8` (admin_* 表) + `CLAUDE.md #24 C1.3` (A0 已落 AdminUser 3 字段) + 后续 `ADMIN_PRD.md §4.1.4 / §5.2` (业务表) 为准。**禁止**在本 Prompt 内重抄任一模型的字段清单。

本 Session 新增/扩展的表 (仅列差异):
- `admin_users` · A0 已落基础字段 (`id / email / passwordHash / role / status / forcePasswordChangeAt / lastPasswordAt / lastLoginAt / createdAt / updatedAt`, 见 CLAUDE.md #24 A 段 + C1.3)。A1 本 Session **不扩字段** (totp_secret / 2FA 相关字段属 Phase 2 范围, A1 不引入)
- `admin_audit_log` · A1 **新建全表** (A0 未建, 见本文档 line 333 批注)。字段形状按 `ADMIN_PRD.md §5.2` admin_audit_log 行为准
- `user_moderation_actions` · A1 新建。字段形状按 `ADMIN_PRD.md §4.1.4` 对应行为准
- `user_activity_stats` · A1 新建 (定时 job 填充)。字段形状按 `ADMIN_PRD.md §4.1.4` 对应行为准

迁移额外执行 (Postgres SQL, Prisma DSL 不支持所以写原生 migration):
```sql
-- 只保留 INSERT + SELECT 权限 (审计日志不可改不可删)
-- ⚠️ 下列 role 名 `<app_role_placeholder>` 必须在 A1 实施前由 Frank 确认本地 Postgres 实际应用角色名
--    (候选: genpano_app / application_role / PUBLIC, 以 backend/.env 的 DATABASE_URL user 或 Supabase 角色为准)
REVOKE UPDATE, DELETE ON admin_audit_log FROM <app_role_placeholder>;
```

> 2026-04-21 · Session A0 Step 13 · 反向同步 A1 inline schema: 删除 phantom 字段 `totp_secret?` (A0 未落, PRD §5.6.8 无); 补充引用 A0 已落 3 字段 (force_password_change_at / last_password_at / last_login_at); REVOKE target role 标记为 `<app_role_placeholder>` 待 A1 开工前 Frank 确认。

## 3. RBAC 中间件

实现 `requireRole(allowed: AdminRole[])` 中间件:
- 解析 session -> admin_users -> role
- role 不在 allowed 列表 -> 403
- MVP: 所有 endpoint 默认只允许 ['super_admin']，但以列表形式调用，Phase 2 扩展

## 4. 审计日志自动接入

实现 `withAudit(action, target_type)` 高阶包装器:
- 包裹所有 POST/PUT/PATCH/DELETE 的 /admin/api/v1/** 路由
- 自动捕获: operator_id (from session), ip, ua, diff (before/after), reason (body.reason, 必填)
- 写入 admin_audit_log

⚠️ 单元测试必须覆盖: "任何对 kg_*, users (status), budget_config, engine_runtime_config 的写操作后，
    admin_audit_log 必有对应记录"。

## 5. AdminLayout 前端骨架

在 frontend-admin/ (如果没有就新建) 或同仓 frontend/src/admin/ 下实现:
- AdminLayout.jsx
  - 左侧 240px 侧栏 (4 大 Section + 动态 badge)
  - 顶部 4px 环境色带 (prod 红 / staging 橙 / dev 绿)，颜色消费 --color-* tokens
  - Header 左上角 "ADMIN" 色块徽标 + 当前页标题
  - Header 右侧: Cmd+K 快捷入口 + 环境下拉 + Admin 用户名
  - 底部: 当前环境 + 切换按钮
- 技术栈:
  - 样式必须全部消费 docs/DESIGN_TOKENS.md 的 CSS vars / t-* / text-themed-* 类
  - 侧栏 active 态复用 App 侧的 --gradient-sidebar-active
  - 严禁 inline hex

## 6. Cmd+K 命令面板

- 使用 cmdk 包
- 默认打开快捷键: Cmd/Ctrl + K
- 命令列表数据源: /admin/api/v1/nav-commands (返回所有可跳转页面 + 常用动作)
- 支持模糊搜索，回车跳转

## 7. 用户列表 + 详情 + 冻结 + 登录审计 (Module A 全部)

### 后端 API (/admin/api/v1)
- GET  /users (分页 + 筛选 + 搜索，见 PRD §4.1.1 表格字段)
- GET  /users/:id
- GET  /users/:id/projects (只读)
- GET  /users/:id/api-keys
- GET  /users/:id/moderation-history
- POST /users/:id/suspend  (body: reason, duration?)
- POST /users/:id/unsuspend (body: reason)
- POST /users/:id/force-password-reset (body: reason) -- 触发 email
- DELETE /users/:id (soft delete, body: reason)
- GET  /users/login-audit (分页 + 筛选)

全部走 requireRole(['super_admin']) + withAudit

### 前端页面
- /admin/users (表格 + 搜索 + 筛选)
  - 使用 @tanstack/react-table
  - 行 hover 显示 [...] 下拉菜单
  - 分页/排序/筛选同步到 URL query
- /admin/users/[id] (4 Tab: 概览 / Projects / API / 操作记录)
  - 使用 Radix Tabs
- /admin/users/login-audit (表格)

### 危险操作 二次确认
- 删除用户 + 冻结用户 + 导出 CSV 必须走统一的 ConfirmDestructiveDialog:
  - 标题: 明确动作
  - 输入: 要求用户输入用户 email 作为确认
  - reason 字段必填

## 8. 审计日志 UI (/admin/audit-log)

- 全局视图，表格 + 筛选 (时间 / 操作员 / 动作 / 对象类型 / 关键字搜索)
- 点击某行 -> 右侧抽屉展示 diff_json (react-json-view-lite 渲染)
- 导出 CSV (super_admin only) -- 导出动作本身也写入 audit_log

## 9. 测试

- 单测: RBAC middleware / withAudit / API endpoints
- 集成测试: 冻结用户 -> 用户无法登录 App -> 解冻 -> 恢复
- 集成测试: 任何写操作 -> admin_audit_log 有记录
- 端到端烟测脚本 scripts/verify-admin-session-A1.sh

## 10. 文档

完成后更新 CLAUDE.md:
- 增加 "Admin 模块" 一节
- 列出 Admin 的路由前缀 / 域名 / 登录方式
- 列出新增的 Admin 数据表
- 列出 Admin 的 5 个结构锚点 (ADMIN_PRD §6.5)

请按顺序执行，每完成一步报告进展。
```

### 预期产出

- `app/admin/**` 路由组 + middleware
- Prisma migration (新增 4 张表 + REVOKE 语句)
- `app/admin/api/v1/users/**` API
- `frontend/src/admin/layouts/AdminLayout.jsx` + 侧栏
- `frontend/src/admin/pages/{UsersList,UserDetail,LoginAudit,AuditLog}Page.jsx`
- Cmd+K 命令面板
- 测试 + `scripts/verify-admin-session-A1.sh`
- CLAUDE.md 更新

### Layer 1 验收脚本 (verify-admin-session-A1.sh)

```bash
#!/bin/bash
set -e
echo "=== Admin Session A1 验收 ==="

# 1. 结构
REQUIRED=(
  "app/admin/layout.tsx"
  "app/admin/api/v1/users/route.ts"
  "app/admin/api/v1/users/[id]/route.ts"
  "frontend/src/admin/layouts/AdminLayout.jsx"
  "frontend/src/admin/pages/UsersListPage.jsx"
  "prisma/migrations/*admin_core*"
  "scripts/verify-admin-session-A1.sh"
)
for f in "${REQUIRED[@]}"; do
  compgen -G "$f" > /dev/null || { echo "FAIL: $f missing"; exit 1; }
done

# 2. 数据库表
psql "$DATABASE_URL" -c "SELECT 1 FROM admin_users LIMIT 1;" > /dev/null
psql "$DATABASE_URL" -c "SELECT 1 FROM admin_audit_log LIMIT 1;" > /dev/null

# 3. 审计表 REVOKE 生效
! psql "$DATABASE_URL" -c "DELETE FROM admin_audit_log;" 2>&1 | grep -q "permission denied" \
  && { echo "FAIL: audit_log DELETE not revoked"; exit 1; }

# 4. 权限检查: 非登录访问 401
curl -s -o /dev/null -w "%{http_code}" https://admin.genpano.internal/admin/api/v1/users \
  | grep -q "401"

# 5. 审计完整性: 冻结测试用户后 audit_log +1
BEFORE=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM admin_audit_log;")
# ... trigger suspend via authenticated call ...
AFTER=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM admin_audit_log;")
[ "$AFTER" -gt "$BEFORE" ] || { echo "FAIL: audit not recorded"; exit 1; }

# 6. 无硬编码密钥
! grep -rn "sk-[a-zA-Z0-9]" app/admin/ frontend/src/admin/ \
  || { echo "FAIL: secrets found"; exit 1; }

echo "=== A1 PASS ✅ ==="
```

### Layer 2 对抗性验证 Prompt (adversarial-A1.md)

```
你是代码安全审计员。请审查 app/admin/ 和 frontend/src/admin/。

重点:
1. 权限绕过: 是否存在 /admin/** 在 middleware 中被遗漏? 特别是:
   - /admin/api 的 websocket / static / public 路径?
   - hostname 检查是否能通过 Host header 伪造绕过?
2. 审计缺口: 找出所有绕过 withAudit 的写操作路径
3. SQL 注入 / XSS: users 表格的搜索参数 / 详情抽屉的 JSON 渲染
4. 会话管理: admin session 有无过期? 可否被 fixation? HttpOnly/Secure 齐全?
5. CSRF: /admin/api/v1/** 的 POST/DELETE 有无 CSRF 保护?
6. 敏感数据: login audit 是否存了明文 password? email 是否在日志中脱敏?
7. RBAC 退化风险: 未来加角色时, 哪些 endpoint 会不小心对新角色开放?

每个发现给出: 文件:行号, 严重级别 P0-P3, 修复建议。
输出到 review/admin-session-A1-adversarial.md
```

### Layer 3 规约对齐 Prompt (compliance-A1.md)

```
你是产品经理助理。对比 ADMIN_PRD.md §3, §4.1, §5, §6, §8.1 的 M1+M7+M8 与当前实现。

逐条输出:
| PRD 条目 | 是否实现 | 文件/路径 | 偏差 |
|---|---|---|---|
| §4.1.1 用户列表 8 列 | ... | ... | ... |
| §4.1.2 用户详情 4 Tab | ... | ... | ... |
| §4.1.3 登录审计警戒规则 | ... | ... | ... |
| §5.1 RBAC 中间件形态 | ... | ... | ... |
| §5.2 审计不可变 | ... | ... | ... |
| §5.5 /admin/api/v1 前缀 | ... | ... | ... |
| §6.1 环境色带 | ... | ... | ... |
| §6.3 危险操作二次确认 | ... | ... | ... |

重点: M8 的 5 个结构锚点文件是否都存在?
重点: M7 的"审计日志不可更新/删除"是数据库层面生效的吗?

输出到 review/admin-session-A1-compliance.md

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### Phase Gate

A-Gate 1 (30min): 人类登录、冻结一个用户、导出一次 CSV，确认 audit 有记录，侧栏结构清晰。

---

## Session A2 · Pipeline Dashboard + Planner 核心 + 基础数据模型

> **v2 重构**: 本 Session 系列对应 [`ADMIN_PRD_B_PIPELINE.md`](./ADMIN_PRD_B_PIPELINE.md) v2 的 **Planner / Tracker / Analyzer** 三大模块。v1 的 13 个子页 (B1-B13) 已按 data pipeline 生命周期重组。

### 前置依赖

- Session A1 完成
- App Session 1 + 1.5 完成 (爬取引擎 + 知识图谱数据已有)
- **App Session 1.2 Platform Layer 已交付** (2026-04-23 追加, CLAUDE.md #28.A): `backend/src/accounts/**` 提供账号状态机 / 鲁班 SMS live client / auto-register orchestrator / cookie bundle 读写 / AccountPool DB-backed 选择器。Session A2 Tab 1 账号池页 (§5 Tab 1) 的 admin API handler 必须 `import { ... } from '@/accounts/**'`, **仅做 HTTP wrapper + UI 可视化**, 严禁重写 Luban / auto-register / crypto 业务逻辑, 否则双轨代码违反 CLAUDE.md 决策 #28.A 边界。
- **必读**: [`docs/ADAPTER_CONTRACT.md`](./ADAPTER_CONTRACT.md) — 所有字段、状态机、告警规则的语义真相源 (重点 §5.1 账号状态机 + §5.3a Pre-Warm 7 步 + §5.4 自动注册流程)
- **必读**: [`docs/ADMIN_PRD_B_PIPELINE.md`](./ADMIN_PRD_B_PIPELINE.md) §0 (重组动机 + v1→v2 映射) + §1 (Planner 全文) + §4.1 (Dashboard) + §5.1 (Planner API)
- **必读**: [`docs/ADMIN_PRD.md`](./ADMIN_PRD.md) §4.2.4 账号池页架构边界块 (Tab 1 cookie 明文存储契约, CLAUDE.md #28.C1)

### 目标

搭建 Pipeline 管理的 **数据模型基础** + **Planner 模块核心 3 页** + **跨模块 Dashboard**。

**契约原则**: 本 Session 展示的每一个指标 / 每一个按钮触发的动作, 其语义与副作用必须与 ADAPTER_CONTRACT 一致 — 若契约里没有某个字段或动作, 本 Session 不得发明。

### Prompt

```
**前置：测试数据 seeding**
执行 `npm run seed:admin`（使用 PRD_TEST_DATA_V1.md 的 fixtures 注入 SQLite dev DB：128K attempts / 1560 topics / 9 engines 基线）。该命令幂等，多次执行不会重复插入。

---

你是 GENPANO Admin 的实施 Session A2。

请先阅读 (顺序不能变, 契约先于视图):
- CLAUDE.md
- docs/ADAPTER_CONTRACT.md §5 (账号) + §6 (错误码) + §7 (代理调度)
- docs/ADMIN_PRD_B_PIPELINE.md §0 (v1→v2 映射) + §1 (Planner) + §4.1 (Dashboard) + §5.1 (Planner API)
- docs/ADMIN_PRD.md §4.4.7 (审计)
- 现有 src/engines/**, src/accounts/**, src/scraping/** (App Session 1 + 1.2 产出)
- Session A1 的 AdminLayout + withAudit + RBAC
- design/prototype-admin.html (Pipeline 页面原型, 查看 Planner/Tracker/Analyzer 导航结构)

## 1. 数据模型迁移 (Prisma)

### 1.1 Planner 基础表

pipeline_batches          — PRD §1.1 定义 (batch_date, status, total_queries, completed, failed, started_at, completed_at)
planner_runs              — PRD §1.1 定义 (triggered_by, scope, industry_id, brand_id, topics_generated, category_topic_pct, topics_from_extraction, status)
pipeline_global_pause     — PRD §1.1 定义 (is_paused, paused_by, paused_at, paused_reason, resumed_at)

### 1.2 生成管线表

prompt_generation_runs    — PRD §1.2 定义 (scope, industry_id, topic_id, intent_filter[], language_filter[], prompts_generated/failed, status)
query_generation_runs     — PRD §1.2 定义 (scope, from_date, to_date, profile_groups_selected[], queries_assembled, status)

### 1.3 采集资源表

engine_runtime_config     (engine PK, adapter_mode enum('web','api'), is_paused bool, updated_at, updated_by)
account_tags              — PRD §1.5 定义 (account_id, tag_name, tagged_at, tagged_by)
account_retirement_rules  — PRD §1.5 定义 (engine, consecutive_failures_threshold, cooldown_cascade_count, is_enabled)
account_execution_stats   — PRD §1.5 定义 (account_id, query_id, execution_at, status, error_type, response_time_ms)
proxy_subscriptions       — PRD §1.5 定义 (provider, subscription_url encrypted, status, max_concurrent_connections)
proxy_nodes               — PRD §1.5 定义 (subscription_id, ip_address, region, protocol, latency_ms, is_online, is_region_paused)

### 1.4 物化视图

account_health_score      — PRD §1.5 定义 (每账号近 50 次执行的成功率)

### 1.5 Tracker 核心表 (本 Session 只建表, UI 在 A2.2)

query_execution_attempts  — PRD §2.1 完整 schema (query_id, engine, attempt_number, account_id, proxy_node_id, proxy_region, profile_id, profile_group_id, prompt_version_id, adapter_mode, status, error_code, error_subcategory, response_text, response_tokens, response_time_ms, har_path, raw_html_path, screenshot_path, console_log_path, retry_of_attempt_id, retry_strategy, started_at, completed_at)
  — 含全部索引 (idx_attempts_query, idx_attempts_status, idx_attempts_error, idx_attempts_engine, idx_attempts_account)

engine_health_5min        — PRD §2.1 物化视图 (5 分钟聚合: success_rate, p50_ms, p95_ms, captcha_count, cf_blocked_count, timeout_count)

retry_strategy_rules      — PRD §2.2.1 定义 (failure_category, failure_subcategory, strategy, max_retries, backoff_base_sec, backoff_max_sec, cooldown_window_minutes, is_system_default, is_enabled)
  — 含 7 条系统预置规则 seed

⚠️ `query_execution_attempts` 是 Tracker 的唯一核心表, 替代 v1 的 `query_execution_failures`。

### 1.6 Analyzer 基础字段 (本 Session 只加字段, UI 在 A2.4)

ALTER TABLE ai_responses ADD parse_status, brands_detected, citations_detected, overall_sentiment, pano_score_breakdown, parse_errors
  — PRD §3.1.3 定义

response_quality_daily    — PRD §3.1.3 物化视图 (每日聚合: parse_success_rate, avg_sentiment, avg_brands_per_response, citation_coverage_pct)

### 1.7 变更审批表

pipeline_change_requests  — PRD §4.3 定义 (change_type, target_resource, diff, requested_by, status, approved_by, dry_run_result)

⚠️ 全部字段以 ADMIN_PRD_B_PIPELINE.md 对应章节的 CREATE TABLE 为准, 不得简化或增减列。
⚠️ engine_runtime_config 迁移加注释: "所有写入必须走 /admin/api/v1/pipeline/* endpoint, 禁止直连 DB 修改"

## 2. Pipeline Dashboard /admin/pipeline/dashboard

按 ADMIN_PRD_B_PIPELINE §4.1:
- 顶部告警条: 最多 3 条 P0/P1, 含"定位"跳转按钮
- 3 列摘要: Planner (批次进度+Planner 状态+品类 Topic %) / Tracker (24h 成功率+3 引擎迷你卡+DLQ 数量) / Analyzer (解析成功率+品牌 Precision+待标注 QA)
- 14 天趋势: 成功率 + 成本双轴折线 (Recharts ComposedChart)
- Reaper 状态 footer

## 3. Planner — 采集调度总控 /admin/pipeline/planner/scheduler

按 ADMIN_PRD_B_PIPELINE §1.1:
- 全局采集开关 (暂停/恢复 + confirm + reason → 审计)
- 今日批次进度条 + 四层漏斗 (Topic→Prompt→Query→Response + 流失率)
- Planner 状态: 最后运行 + Topics 品类/品牌/产品占比 + 来源分布
- "立即运行 Planner" 按钮 → Modal (Full/By Industry/By Brand) → enqueue → 进度条
- 历史批次列表 (30 天) → 行点击展开该批次四层 breakdown
- KPI: 总成本预估 / 剩余 ETA / 最后更新
- 边界: Planner 2h 无增量 → PIPE-04; failed > 30% → PIPE-05 + 自动暂停; 品类 < 40% → 橙色

## 4. Planner — 生成管线 /admin/pipeline/planner/generation

按 ADMIN_PRD_B_PIPELINE §1.2:
- **三层 Tab**:
  - Tab 1 Topic 生成: Planner 历史 + 品类/品牌/产品占比饼图 + 运行 Planner 按钮
  - Tab 2 Prompt 生成: 统计面板 + 失败列表 + 覆盖度检查(缺 Prompt 标红/缺 Intent 标黄) + "生成 Prompt" 按钮
  - Tab 3 Query 组装: 统计面板 + 队列堆栈图(3 日) + 组合逻辑展示 + "组装 Query" 按钮 + Per-engine 暂停开关

## 5. Planner — 采集资源 /admin/pipeline/planner/resources

按 ADMIN_PRD_B_PIPELINE §1.5 (合并原 B4 账号池 + B5 代理池):

### Tab 1: 账号池
- 引擎水位摘要 (3 卡: active/total + 健康均分 + 预计耗尽时间)
- 账号列表: TanStack Table (ID/引擎/状态/健康分/标签/上次使用/成功率/操作)
- 轮换策略配置 (走变更审批)
- 自动退役规则 (阈值 + 影响预览)
- "导入 JSON" 批量入库 (max 1000, 每行 /whoami 验证) — admin API 必须调用 Platform Layer `backend/src/accounts/db-repo.ts` 的 `bulkImport()`, 禁重写解析 + 校验逻辑
- **Cookie 存储 (2026-04-23 更新, CLAUDE.md #28.C1)**: `accounts.encryptedCookies Bytes?` 字段 **MVP 阶段存明文 UTF-8 JSON** (`JSON.stringify({cookies, localStorage, userToken?})` 的 UTF-8 bytes), 字段名与 Bytes 类型保留作为日后 AES-256-GCM + KMS 升级的预留点, 不改 schema。UI 仍遵守 "回显永远 `***` / 审计日志不记明文 cookie" 两条行为纪律 — 视图层 mask 与底层是否加密解耦。Platform Layer 提供 `crypto-noop.ts` (当前 identity) 作为未来换实现的唯一入口, admin API 禁直读 `encryptedCookies` 字段
- **自动注册触发**: "为引擎 X 新增账号" 按钮 → admin API 调 Platform Layer `registerAccount({engineId, luban, countryCode})` (App Session 1.2 交付的 live 实现, doubao + deepseek-CN 支持; ChatGPT 走人工导入). API handler 只做 RBAC + audit, 业务走 Platform Layer

### Tab 2: 代理池 (Ninja Clash)
- 订阅配置: URL/状态/最大并发/已用/"立即刷新"
- 节点按区域分组 (节点数/在线数/p95 延迟/暂停开关)
- 节点详情抽屉 (IP/延迟/黑名单)
- 订阅链接失效 → PIPE-11 P0; 区域节点 < 3 → PIPE-03 P1; 国内引擎禁分配代理

## 6. API 实现

全部走 requireRole + withAudit (写操作), 路径前缀 `/admin/api/v1/pipeline/`:

### 调度 API (§5.1)
GET    /scheduler/overview
GET    /scheduler/batches?range=7d&cursor=
POST   /scheduler/planner/trigger { scope, industry_id?, brand_id? }
GET    /scheduler/planner/status
POST   /scheduler/pause { action:'pause'|'resume', reason }

### 生成管线 API (§5.1)
GET    /generation/topics/runs
GET    /generation/prompts
POST   /generation/prompts/trigger { scope, industry_id?, intent_filter[] }
GET    /generation/prompts/failures?page=&limit=
POST   /generation/prompts/retry { failure_ids[], reason }
GET    /generation/prompts/coverage
GET    /generation/queries
POST   /generation/queries/trigger { scope, profile_groups[], date_range }
POST   /generation/queries/engine-pause { engine, action:'pause'|'resume', reason }

### 资源 API (§5.1)
GET    /resources/accounts?engine=
GET    /resources/accounts/:id
POST   /resources/accounts { engine, cookies, tags }
POST   /resources/accounts/:id/freeze { reason }
POST   /resources/accounts/:id/unfreeze { reason }
POST   /resources/accounts/batch-import { accounts[] }
GET    /resources/accounts/retirement-rules
PUT    /resources/accounts/retirement-rules/:engine { thresholds }
GET    /resources/proxies?region=
GET    /resources/proxies/subscription
POST   /resources/proxies/subscription/refresh
POST   /resources/proxies/:id/blacklist { reason }
POST   /resources/proxies/region-toggle { region, action, reason }

### Dashboard API (§5.3)
GET    /dashboard/summary
GET    /dashboard/trend?days=14

## 7. 实时性

- Dashboard + 调度: SWR + 30s revalidate
- 账号池/代理池: SWR + 30s revalidate
- 生成管线 (running 状态): SWR + 10s revalidate + 页面可见性检测
- 侧栏 badge: 独立 SWR hook, 30s

## 8. 测试

- 单测: adapter-mode 切换后新入队 Query 的 router 是否生效
- 单测: retry_strategy_rules 7 条 seed 完整性
- 集成: 停采 → 新任务不再进入队列 → 恢复
- 集成: 冻结账号 → 该账号不再被 scheduler 选中
- 集成: 手动触发 Planner → planner_runs 记录 + 品类 Topic ≥ 40%
- 集成: 全局暂停 → 新 Query 不入队, running 继续 → 恢复后续新
- verify-admin-session-A2.sh 覆盖: 全部数据模型 + Planner API 可达 + Dashboard 可达 + 审计记录

完成后更新 CLAUDE.md (新增: Admin Pipeline 模块 Planner/Tracker/Analyzer 三大模块说明)。

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### 预期产出

- Prisma migration: **全部** Pipeline 数据模型 (Planner + Tracker + Analyzer + 横切 = ~15 张表/视图)
- 3 个 Planner 页面 + 1 个 Dashboard 页面
- Planner + Dashboard 全部 API (~25 个 endpoint)
- 7 条 retry_strategy_rules seed
- 测试 + `scripts/verify-admin-session-A2.sh`
- CLAUDE.md 更新

### 对抗性验证 (adversarial-A2.md 要点)

- 账号池并发: 两个 scheduler worker 同时取账号是否会取到同一个 (SELECT FOR UPDATE SKIP LOCKED)
- 停采 race: "停采"写入与"新任务入队"的时序
- 代理拉黑: 被拉黑后已在 inflight 的请求会怎样
- Cookie 粘贴: XSS / 日志泄露 cookie 内容
- Planner 并发触发: 两次同时触发是否有乐观锁
- 批量导入 1000 账号 → 验证并发 /whoami 不打爆引擎限流

### 规约对齐 (compliance-A2.md 要点)

- §1.1 采集调度: 全局开关 + 批次进度 + Planner 状态 + 四层漏斗齐全?
- §1.2 生成管线: 三层 Tab + 覆盖度检查 + per-engine 暂停都实现了?
- §1.5 采集资源: 账号健康分 + 退役规则 + 代理订阅 + Ninja Clash 适配?
- §4.1 Dashboard: 三模块摘要 + 告警条 + 14 天趋势 + Reaper 状态?
- §2.1 Tracker 核心表: schema 与 PRD 完全一致 (不少列)?

### Phase Gate

A-Gate 2 (60min): 人类在 staging 环境执行完整 Planner 链路 — 触发 Planner → 查看 Topic 生成 → 确认 ProfileGroup → 触发 Prompt/Query 生成 → 暂停单引擎 → 恢复 → Dashboard 各摘要反映真实数据。

---

## Session A2.1 · Planner 深化: Prompt 模板 + ProfileGroup

### 前置依赖

- Session A2 完成
- **必读**: [`ADMIN_PRD_B_PIPELINE.md`](./ADMIN_PRD_B_PIPELINE.md) §1.3 (Prompt 模板) + §1.4 (ProfileGroup)

### 目标

补全 Planner 最后 2 个页面: Prompt 模板管理 (灰度 + A/B + 版本 diff) 和 ProfileGroup 管理 (CRUD + LLM 生成 Profile 池)。

### Prompt

```
你是 GENPANO Admin 的实施 Session A2.1。

请先阅读:
- CLAUDE.md
- docs/ADMIN_PRD_B_PIPELINE.md §1.3 (Prompt 模板) + §1.4 (ProfileGroup) + §5.1 (对应 API)
- Session A2 的 AdminLayout + 数据模型 + withAudit
- design/prototype-admin.html (planner-prompts + planner-profiles 原型页面)

## 1. Prompt 模板 /admin/pipeline/planner/prompts

按 ADMIN_PRD_B_PIPELINE §1.3:

### 数据模型 (A2 未建的 Prompt 模板表)
prompt_templates          — §1.3 定义 (name, intent, language, applies_to_engines[], active_version_id, status)
prompt_template_versions  — §1.3 定义 (template_id, version, body, variables JSONB, rollout_plan JSONB, activated_at, deactivated_at)
prompt_ab_experiments     — §1.3 定义 (template_id, control_version_id, treatment_version_id, traffic_split, started_at, ended_at, conclusion)

### UI
- 模板列表: template_id / name / intent / language / engines / active_version / status(draft|active|archived)
- 版本抽屉: 历史 version + Monaco diff viewer + 创建人 + 响应统计
- 新版本编辑器: Monaco + 变量 auto-complete ({{brand_name}} / {{industry}} / {{competitor_ids}})
- 灰度发布: 全量 / A/B 5% / 限行业 / 限引擎。发布后 24h 观察期 → 升全量 / 回滚
- A/B 面板: 覆盖率 / 解析成功率 / 平均 token / 成本 / precision@10 + z-test 显著性
- 回归 Prompt: 激活前强制跑固定 brand+industry 组合, diff > 30% 需 confirm
- 所有操作 → super_admin + 理由 + 审计 + 走变更审批

### API
GET    /pipeline/prompts/templates
GET    /pipeline/prompts/templates/:id
POST   /pipeline/prompts/templates
PUT    /pipeline/prompts/templates/:id
GET    /pipeline/prompts/templates/:id/versions
POST   /pipeline/prompts/templates/:id/versions
POST   /pipeline/prompts/templates/:id/activate { version_id, rollout_plan }  → 走 CR
POST   /pipeline/prompts/templates/:id/rollback { reason }                   → 走 CR
GET    /pipeline/prompts/ab-experiments
POST   /pipeline/prompts/ab-experiments
POST   /pipeline/prompts/ab-experiments/:id/conclude { winner }

## 2. ProfileGroup & Profile /admin/pipeline/planner/profiles

按 ADMIN_PRD_B_PIPELINE §1.4:

### 数据模型 (A2 若未建)
profile_groups            — §1.4 定义 (name_zh, name_en, description, industry_id, demographic_filters JSONB, sampling_weight, min_sample_threshold, is_active)
profiles                  — §1.4 定义 (profile_group_id, persona_json, is_active)
profile_generation_logs   — §1.4 定义 (profile_group_id, llm_model, prompt_used, profiles_generated, tokens_used, estimated_cost)

### UI
- ProfileGroup 列表: 名称(zh/en) / 行业 / 活跃 Profile 数 / 采样权重 / 状态
- 详情抽屉 4 Tab:
  - 基本信息 (名称 / 行业 / 权重 0-100 / 最小阈值 默认 50)
  - 人口属性 (age_range / gender[] / region_tier[] / income / device[] / interests)
  - Profile 池 (列表 + "重新生成" 按钮 → LLM 生成 N 个)
  - 采样策略 (权重 / 阈值 / 平均每日 Query 采样量只读)
- 新建/编辑 Modal: React Hook Form + Zod 校验
- 30 天采样 < threshold → PIPE-12 告警
- 删除 = 标 inactive, 不破坏已有 Query lineage

### API
GET    /pipeline/profiles/groups
GET    /pipeline/profiles/groups/:id
POST   /pipeline/profiles/groups
PUT    /pipeline/profiles/groups/:id
DELETE /pipeline/profiles/groups/:id    (soft: is_active=false)
GET    /pipeline/profiles/groups/:id/profiles
POST   /pipeline/profiles/groups/:id/generate { count, llm_model }
GET    /pipeline/profiles/generation-logs?group_id=

## 3. 测试

- 单测: Prompt 版本 diff 计算
- 单测: A/B 实验 z-test 显著性边界 (5% 差距)
- 集成: 新建 Prompt 模板 v2 → 挂 A/B → 24h 后 conclude winner
- 集成: 删除被 Query 引用的 ProfileGroup → 软禁用 + 历史数据完整
- 集成: Profile LLM 生成 → 每组 ≥ N 条 persona + token 消耗记入 log

完成后更新 CLAUDE.md (Planner 子模块完整清单)。

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### 三层 QA

**Executable Acceptance**:
- [ ] 模板创建 + 版本 diff Monaco 渲染正常
- [ ] A/B 实验 24h 后能出 winner，z-test 显著性展示
- [ ] 创建 ProfileGroup → App 端 `/api/v1/profile-groups` 能读到 (共享表)
- [ ] Profile 池 LLM 生成 → token 消耗记入 `profile_generation_logs`
- [ ] 回归 Prompt diff > 30% → 强制 confirm

**Adversarial**:
- [ ] 两个版本 response_quality_score 差 < 5% → winner 判定边界
- [ ] ProfileGroup 采样权重全为 0 → 阻断提示
- [ ] 并发创建同名模板 → UNIQUE 约束 + 友好错误
- [ ] Prompt 正文不可导出 (防模板外泄)

**Spec Compliance**:
- [ ] §1.3 版本 diff 用 Monaco
- [ ] §1.3 A/B 流量分配真落到 queries.prompt_version_id
- [ ] §1.3 回滚走变更审批 + 有 audit
- [ ] §1.4 ProfileGroup 字段 (name_zh/name_en/demographic_filters JSONB) 符合定义

### Phase Gate

A-Gate 2.1 (30min): 人类新建一个 Prompt 模板 v2，挂到 3 个 Topic 上跑 A/B，评估 winner 判定逻辑; 创建一个 ProfileGroup 并生成 Profile 池。

---

## Session A2.2 · Tracker 核心: Attempt 列表 + 引擎健康

### 前置依赖

- Session A2 完成 (query_execution_attempts 表已建)
- **必读**: [`ADMIN_PRD_B_PIPELINE.md`](./ADMIN_PRD_B_PIPELINE.md) §2 (Tracker 全文) + §5.2 (Tracker API)

### 目标

实现 Tracker 模块的核心 2 页: **执行追踪 (Attempt 列表 + 详情 + 重试)** 和 **引擎健康 (per-engine 卡片 + 错误分布)**。这是 Pipeline 运营最高频使用的页面。

### Prompt

```
你是 GENPANO Admin 的实施 Session A2.2。

请先阅读:
- CLAUDE.md
- docs/ADMIN_PRD_B_PIPELINE.md §2 (Tracker 全文) + §5.2 (Tracker API)
- docs/ADAPTER_CONTRACT.md §6 (错误码) + §10 (观测)
- Session A2 建好的 query_execution_attempts + engine_health_5min + retry_strategy_rules
- design/prototype-admin.html (tracker-attempts + tracker-engines 原型页面)

## 1. 执行追踪 /admin/pipeline/tracker/attempts

按 ADMIN_PRD_B_PIPELINE §2.2 — **Tracker 的核心页面**:

### Attempt 列表
- 汇总条: 总 Attempt / 成功 (%) / 失败 / 重试中 / 待人工 / DLQ
- 筛选栏: 引擎 / 状态 / 错误码 / 时间范围 / Query ID 搜索
- 错误码快筛 chip: 全部 | CAPTCHA | CF_BLOCKED | PARSER_FAIL | PROXY_DEAD | TIMEOUT | COOKIE_EXPIRED | EXTRACT_EMPTY | PAGE_CRASHED (含 count)
- TanStack Table (虚拟滚动): Attempt ID / Query ID / 引擎 / # / Prompt 摘要 / 账号 / 代理区域 / 状态 / 错误码 / 耗时 / Debug 凭据图标 (HAR/HTML/截图/日志) / 开始时间
- 批量操作: 多选 → 批量重试 / 批量送 DLQ / 批量忽略 (≥200 自动拆分 50/批 + 进度条)
- 手动重试: failed/waiting_manual → 选策略 (same/rotate_proxy/rotate_account) → 执行

### Attempt 详情抽屉 (540px 右滑)
按 PRD §2.2 关键交互 #1:
- **概要 Tab**: Query 全文 / Prompt 版本 / Profile 画像 / 引擎 / 账号 / 代理 / adapter mode
- **Response Tab**: AI 回答全文 (成功) / 错误详情 (失败)
- **HAR Tab**: HTTP Archive 查看器 (请求 / 响应头 / 时间线瀑布图)
- **HTML Tab**: 原始 HTML 渲染 (iframe sandbox) + DOM 高亮
- **截图 Tab**: 页面截图 (可放大) + 时间戳水印
- **日志 Tab**: 浏览器 console log (按 warn/error 过滤)
- **重试链 Tab**: 该 Query×Engine 的所有 Attempt 时间线 (#1→#2→#3), 每次策略标注

### 自动重试规则设置面板 (齿轮图标展开)
- 规则列表: 错误码 / 策略 / 最大重试 / 退避 / 冷却 / 启用开关
- 7 条系统规则不可删除, 可调参
- 规则修改走变更审批
- 决策流程可视化: 失败 → 匹配 → retries<max → 入队 / ≥max → DLQ / 无规则 → 待人工

### DLQ 子面板 (Tab 或折叠)
- 统计: 总量 / 滞留>3天 / 滞留>7天 / 本周归档
- SLA: PIPE-09a (>3d P2) / PIPE-09b (>7d P1) / PIPE-09c (>500 P0)
- 列表: Query ID / 引擎 / 错误码 / Prompt / 总 attempts / 入 DLQ 时间 / 滞留天数
- 处置: 归档(+reason) / 标 Bug(+issue) / 强制重试(super_admin)
- CSV 导出

## 2. 引擎健康 /admin/pipeline/tracker/engines

按 ADMIN_PRD_B_PIPELINE §2.3:
- 3 列 grid, 每引擎一卡:
  - 当前 adapter_mode (web/api) + 24h 成功率 (大号) + 对比昨日 Δ
  - 近 24h: 样本数 / P50 / P95
  - 错误码分布 (水平条)
  - "API 降级中" 黄色条 (如适用, 含"恢复 Web"按钮)
- 行动按钮:
  - 查看失败样本 → 右抽屉最近 10 条失败 (payload + 截图)
  - 切换降级 API → 二次确认 (diff preview: Web vs API 差异) → 审计含 reason_text + diff_snapshot_id
  - 停采 → 二次确认 → POST pause + reason

## 3. API 实现

### Tracker API (§5.2)
GET    /pipeline/tracker/attempts?engine=&status=&error_code=&from=&to=&query_id=&cursor=&limit=
GET    /pipeline/tracker/attempts/:id
GET    /pipeline/tracker/attempts/:id/retry-chain
POST   /pipeline/tracker/attempts/:id/retry { strategy, reason }
POST   /pipeline/tracker/attempts/batch-retry { ids[], strategy, reason }
POST   /pipeline/tracker/attempts/batch-dlq { ids[], reason }
POST   /pipeline/tracker/attempts/batch-ignore { ids[], reason }
GET    /pipeline/tracker/attempts/summary
GET    /pipeline/tracker/attempts/dlq?cursor=&limit=
GET    /pipeline/tracker/attempts/dlq/stats
POST   /pipeline/tracker/attempts/dlq/:id/archive { reason }
POST   /pipeline/tracker/attempts/dlq/:id/link-bug { bugId, reason }
POST   /pipeline/tracker/attempts/dlq/:id/force-retry { reason }  → super_admin
GET    /pipeline/tracker/attempts/dlq/export-csv
GET    /pipeline/tracker/retry-rules
POST   /pipeline/tracker/retry-rules             → 走 CR
PUT    /pipeline/tracker/retry-rules/:id         → 走 CR
DELETE /pipeline/tracker/retry-rules/:id         (is_system_default 不可删)

### 引擎 API (§5.2)
GET    /pipeline/tracker/engines
GET    /pipeline/tracker/engines/:engine/health
GET    /pipeline/tracker/engines/:engine/failures?limit=10
POST   /pipeline/tracker/engines/:engine/adapter-mode { mode, reason, diff_snapshot_id }  → 走 CR
POST   /pipeline/tracker/engines/:engine/pause { reason }   → 走 CR
POST   /pipeline/tracker/engines/:engine/resume { reason }  → 走 CR

## 4. 实时性

- Attempt 列表: SWR + 5s revalidate + 页面可见性检测
- 引擎健康: SWR + 30s revalidate
- 汇总条 + DLQ 计数: 独立 SWR hook, 10s

## 5. 测试

- 单测: retry_strategy_rules 匹配优先级 (category+subcategory > category > default)
- 单测: DLQ SLA 告警规则 (3天/7天/500条)
- 集成: Attempt 失败 → 自动匹配规则 → 入重试队列 → 达上限 → DLQ
- 集成: adapter-mode 切换 → 新 Attempt 走 API → 审计含 diff_snapshot_id
- 集成: 批量重试 200 条 → 拆分 50/批 + 进度条
- verify-admin-session-A2.2.sh

完成后更新 CLAUDE.md (Tracker 模块说明)。

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### 三层 QA

**Executable Acceptance**:
- [ ] Attempt 列表 TanStack Table 虚拟滚动 10 万条不卡
- [ ] 详情抽屉 7 个 Tab 都能渲染 (HAR/HTML/截图/日志可能为空 → 优雅降级)
- [ ] 错误码快筛 chip 点击 → 列表立即过滤
- [ ] DLQ 强制重试 → super_admin only, 普通角色 403
- [ ] 引擎卡片 adapter-mode 切换 → diff preview 展示 + 审计完整

**Adversarial**:
- [ ] 大 DLQ (1000+ 条): CSV 导出是否 stream 而非一次性 buffer
- [ ] 批量重试成本放大: ≥50 条显示成本预览 + 二次确认
- [ ] 重试链循环: Attempt A retry → B retry → A? (应有 retry_of_attempt_id 链长上限)
- [ ] 引擎停采 race: "停采" 写入与"新任务入队"的时序

**Spec Compliance**:
- [ ] §2.2 Attempt 详情抽屉的 7 个 Tab 全实现
- [ ] §2.2.1 自动重试规则面板 + 7 条系统规则
- [ ] §2.3 引擎健康页的 4 个关键动作 (查样本/切降级/停采/恢复)
- [ ] Attempt 表 schema 与 PRD §2.1 完全一致

### Phase Gate

A-Gate 2.2 (60min): 人类在 staging 模拟"豆包挂了 2 小时" — 从引擎健康页发现问题 → 进 Attempt 列表筛选失败 → 查看 HAR/截图定位根因 → 批量重试或切降级。记录 MTTR 与卡点。

---

## Session A2.3 · Tracker 深化: Trace & Lineage + 变更审批中心

### 前置依赖

- Session A2.2 完成
- **必读**: [`ADMIN_PRD_B_PIPELINE.md`](./ADMIN_PRD_B_PIPELINE.md) §2.4 (Trace) + §4.3 (变更审批)

### 目标

补全 Tracker 最后一页 (链路追溯) + 横切模块变更审批中心。

### Prompt

```
你是 GENPANO Admin 的实施 Session A2.3。

请先阅读:
- CLAUDE.md
- docs/ADMIN_PRD_B_PIPELINE.md §2.4 (链路追溯) + §4.3 (变更审批) + 对应 API
- Session A2 + A2.2 的 Tracker 页面
- design/prototype-admin.html (tracker-trace + pipeline-changes 原型)

## 1. 链路追溯 /admin/pipeline/tracker/trace

按 ADMIN_PRD_B_PIPELINE §2.4:
- 搜索框: Response ID / 品牌 ID + 日期 / User email + 时间窗口
- Sankey 图 (D3): brand → topic → prompt_template(version) → query(profile) → response → parsed_mentions
- 节点点击 → 右侧抽屉全部字段 + 审计 log
- "查看所有执行尝试" → 跳 §2.2 Attempt 列表并筛选 query_id

### 数据 Lineage
ALTER TABLE topics/prompts/queries/ai_responses ADD COLUMN lineage_trace_id UUID
CREATE INDEX ON ai_responses (lineage_trace_id)

边界: Sankey 节点 ≤ 200 (超过裁剪 + 提示)。不允许导出 PDF。

### API
GET    /pipeline/tracker/trace?response_id=&brand_id=&date=&email=&window=
GET    /pipeline/tracker/trace/:traceId

## 2. 变更审批中心 /admin/pipeline/changes

按 ADMIN_PRD_B_PIPELINE §4.3:
- 5 种必审变更: adapter_switch / prompt_activate / engine_pause / retry_rule / proxy_toggle / account_add
- 列表: Pending / Approved / Rejected / Rolled-back Tab
- 详情抽屉: 变更类型 / 影响范围 / 发起人 / 理由 / diff + dry-run
- "Approve & Apply" / "Reject" / 30 天回滚
- Solo 模式: 创建者 = 审批者, 勾选"我已审查" + 理由
- Phase 2: two-eyes 双人复核

### API
GET    /pipeline/changes?status=
GET    /pipeline/changes/:id
POST   /pipeline/changes/:id/approve { reason }
POST   /pipeline/changes/:id/reject { reason }
POST   /pipeline/changes/:id/rollback { reason }

## 3. 测试

- 集成: Trace 查询能拼出完整 Topic→Prompt→Query→Response 链路
- 集成: 所有高危动作 (prompt activate / engine pause / ...) 必须先创建 CR → 409 if 直调
- 集成: Solo self-approve → 审计完整 (requested_by = approved_by)
- verify-admin-session-A2.3.sh

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### 三层 QA

**Executable Acceptance**:
- [ ] Trace 搜索 Response ID → Sankey 完整链路 (5 层)
- [ ] Sankey 节点 > 200 时自动裁剪 + 友好提示
- [ ] 所有 5 种高危变更走 CR (直调返回 409 + change_request_id)
- [ ] Solo self-approve 后动作真正执行

**Adversarial**:
- [ ] trace_id 在异步 / 重试场景下是否会丢失
- [ ] Sankey 千级节点性能 (D3 裁剪)
- [ ] CR 被绕过 (API 直写未走 CR) → DB 层是否有拦截
- [ ] 30 天回滚窗口过期后尝试回滚 → 友好拒绝

**Spec Compliance**:
- [ ] §2.4 Sankey 用 D3 而非手写 SVG
- [ ] §2.4 lineage_trace_id 全链路贯穿 4 张表
- [ ] §4.3 全部 5 种必审变更接入 CR
- [ ] §4.3 审批 SLA 计入 Dashboard 告警

### Phase Gate

A-Gate 2.3 (30min): 人类用 Trace 定位一条"看起来不对"的 Response 的完整链路; 模拟"紧急回滚 Prompt v3"通过 CR 完成, 验证 audit + rollback。

---

## Session A2.4 · Analyzer: 质量分析 + 人工质检

### 前置依赖

- Session A2 完成 (ai_responses 扩展字段 + response_quality_daily 视图已建)
- Session A2.2 完成 (Tracker 页面可用, Analyzer 需要"跳转 Tracker"联动)
- **必读**: [`ADMIN_PRD_B_PIPELINE.md`](./ADMIN_PRD_B_PIPELINE.md) §3 (Analyzer 全文) + §5.3 (Analyzer API)

### 目标

实现 Analyzer 全部 2 页: **质量分析 (Per-Query 分析结果 + 趋势仪表盘)** 和 **人工质检 (抽样 + 三栏标注)**。

### Prompt

```
你是 GENPANO Admin 的实施 Session A2.4。

请先阅读:
- CLAUDE.md
- docs/ADMIN_PRD_B_PIPELINE.md §3 (Analyzer 全文) + §5.3 (Analyzer + 变更审批 API)
- Session A2 建好的 ai_responses 扩展字段 + response_quality_daily 物化视图
- design/prototype-admin.html (analyzer-quality + analyzer-qa 原型页面)

## 1. 质量分析 /admin/pipeline/analyzer/quality

按 ADMIN_PRD_B_PIPELINE §3.1:

### Per-Query 分析结果面板
- 筛选: 引擎 / 行业 / 日期范围 / Query/Brand 搜索
- TanStack Table: Query ID / Prompt 摘要 / 引擎 / 品牌命中数 / 情感 / 引用数 / 提及位置 / PANO A / 解析状态 / 时间
- 点击展开 Query 分析详情抽屉:
  - 品牌提及: 品牌列表 + 位置(top/mid/tail) + 原文高亮
  - 情感分析: 每品牌情感分 + 分类 + 置信度
  - 引用分析: URL + Tier + Authority Score + 归因方式
  - PANO Score 分解: 5 维度原始值
  - 原始 Response 对照: 左分析 / 右原文 (高亮对应)
  - "查看执行详情" → 跳 Tracker Attempt 抽屉

### 质量趋势仪表盘
- 解析成功率趋势 (7d) — 按引擎叠加 AreaChart
- 品牌识别 Precision (7d) — 自动 vs 人工标注对比
- 引擎间偏差 — 3 引擎情感分类分布对比
- 引用覆盖率趋势
- 异常检测: 偏离 2σ → 标红 + 告警

### 4 KPI 卡片 (页面顶部)
- 解析成功率 / 品牌识别 Precision / 引用覆盖率 / 平均品牌数/Response

## 2. 人工质检 /admin/pipeline/analyzer/qa

按 ADMIN_PRD_B_PIPELINE §3.2:

### 数据模型 (A2 若未建)
response_qa_samples       — §3.2 定义 (response_id, engine, industry, sampled_at, assigned_to, status, labeled_at)
response_qa_labels        — §3.2 定义 (sample_id, labeler_id, overall_correct, error_categories[], corrected_brands, corrected_sentiment, notes)
response_qa_weekly        — §3.2 物化视图 (precision_overall, wrong_brand_rate per week × engine)

### UI
- KPI 面板: 本周抽样数 / 已标注 / 待标注 / Overall Precision
- 待审队列: 每行一条 Response (Prompt 摘要 / 引擎 / 自动品牌 / 情感 / 引用)
- 三栏对比抽屉:
  - 左: 原始 Response 文本
  - 中: 自动抽取结果 (可编辑修正)
  - 右: 反馈表单 (correct / wrong_brand / wrong_sentiment / missed_mention / hallucination / bad_citation)
- 校准回写: 人工标注 → response_qa_labels, 每周汇总 precision/recall
- 与 Tracker 联动: "查看执行详情" → 跳 Tracker Attempt 详情
- 每日自动抽样 200 条 (按引擎/行业分层)
- 标注数据不直接改 ai_responses, 离线校准回写

### API
GET    /pipeline/analyzer/quality/queries?engine=&industry=&from=&to=&q=&cursor=&limit=
GET    /pipeline/analyzer/quality/queries/:id
GET    /pipeline/analyzer/quality/trend?days=7
GET    /pipeline/analyzer/quality/kpi
GET    /pipeline/analyzer/qa/samples?status=&engine=&cursor=&limit=
GET    /pipeline/analyzer/qa/samples/:id
POST   /pipeline/analyzer/qa/samples/:id/label { overall_correct, error_categories[], ... }
POST   /pipeline/analyzer/qa/samples/:id/skip { reason }
GET    /pipeline/analyzer/qa/stats

## 3. 测试

- 单测: 解析成功率计算逻辑 (partial 算 0.5?)
- 单测: QA 抽样分层逻辑 (按引擎×行业均匀)
- 集成: QA 标注 → response_qa_labels 写入 → weekly precision 更新
- 集成: Analyzer → "查看执行详情" → 跳 Tracker Attempt 正确
- 集成: 异常检测 (seed 偏离数据) → 标红 + 告警
- verify-admin-session-A2.4.sh

完成后更新 CLAUDE.md (Analyzer 模块说明)。

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### 三层 QA

**Executable Acceptance**:
- [ ] Per-Query 结果列表 + 详情抽屉全字段渲染
- [ ] 质量趋势 4 张图全部展示 (Recharts)
- [ ] QA 三栏标注抽屉: 左原文 / 中自动结果(可编辑) / 右反馈
- [ ] "查看执行详情" 跨 Analyzer→Tracker 跳转正确
- [ ] 自动抽样 cron 每日生成 200 条 (按引擎/行业分层)

**Adversarial**:
- [ ] QA 标注并发: 两人同时标同一 sample → 乐观锁
- [ ] 抽样偏差: 特定引擎 Response 过少 → 分层抽样是否真均匀
- [ ] 异常检测 2σ: 样本量太小时是否误报
- [ ] 大量 partial parse → 成功率计算口径

**Spec Compliance**:
- [ ] §3.1 Per-Query 详情的 6 个展示区全实现
- [ ] §3.1 趋势仪表盘的 5 项指标全展示
- [ ] §3.2 三栏标注 + 6 种反馈类别
- [ ] §3.2 标注不直接改 ai_responses (离线回写)

### Phase Gate

A-Gate 2.4 (45min): 人类在 QA 界面标 50 条样本 (三栏对比); 在质量面板发现一个引擎的情感偏差并跳转 Tracker 查原因。全模块一体化验收。

---

## Session A3 · 知识图谱运营中心

### 前置依赖

- Session A1 + A2 完成
- App Session 1.5 完成 (KG 数据已入库，品牌提交机制已存在)

### 目标

实现 ADMIN_PRD §4.3 全部子模块 (§8.1 的 M4 + §8.2 的 S1 + S2)。

### Prompt

```
你是 GENPANO Admin 的实施 Session A3。

请先阅读:
- CLAUDE.md
- docs/ADMIN_PRD.md §4.3 (KG 全部子模块)
- 现有 src/platform/knowledge-graph/** + src/platform/discovery/** (App Session 1.5 产出)
- 现有 kg_* 表结构

## 1. 数据模型新增

kg_review_queue  (id, target_type enum('brand','product','brand_submission','relation'),
                 target_id, submitted_by, status enum('pending','approved','rejected','merged'),
                 reviewer_id, reason, reviewed_at, created_at)
alias_conflicts  (id, alias_value, language, candidate_ids JSONB[], resolved_to_id, resolved_at)

## 2. 行业 & 品类树 /admin/kg/industries

- 左侧: 4 个行业列表
- 右侧: 选中行业的品类树 (AntG6 树状 or 简洁 shadcn/ui Accordion 嵌套)
- 每个品类节点: 显示品牌数 / 产品数 / 近 7 天 Topic 增量
- 操作: 新建子品类 / 重命名 / 移动 / 标记 deprecated
- "用 LLM 补全子品类" 按钮:
  - 触发 LLM 调用 -> 预览结果 -> 批量入库 / 单条审核

## 3. 品牌审核 /admin/kg/brands

核心页面, 采用 "表 + 详情抽屉" 模式:

表列: 品牌名 / 行业 / 品类归属 / 来源 (LLM/submission/seed) / 置信度 / 状态 / 创建时间
筛选: 状态 / 行业 / 来源 / 置信度区间
搜索: 品牌名 (含别名)

抽屉详情:
- 基本信息 (name_zh / name_en / primary / positioning / price_range / parent_company / origin)
- 所有别名 (按 language + type 分组)
- 关系边 (COMPETES_WITH / SAME_GROUP + 置信度)
- 近 14 天随机 10 条 mention 样本 (含 Response 原文 + 引擎)
- Discovery source (LLM 原始输出, 折叠 JSON)

批量操作:
- approve (批量) - reason 可选
- reject (批量) - reason 必填
- merge (单条) - 选择目标品牌, 别名合并

## 4. 产品审核 /admin/kg/products

同品牌结构, 字段多: 关联品牌 / 关联品类 / keyFeatures

## 5. 别名与关系编辑器 /admin/kg/aliases-relations

两个 Tab:

Tab 1: 别名冲突
- 列出所有"同一别名被多个目标认领"的冲突
- 每行展示: 别名 / 语言 / 候选目标列表 (带置信度)
- 运营决定归属 -> 批量"归属到 X"

Tab 2: 关系边清理
- confidence < 0.3 的边
- 类型矛盾的边 (如既 COMPETES_WITH 又 SAME_GROUP)
- 批量调整置信度 / 删除

## 6. Brand Submission Inbox /admin/kg/brand-submissions

最重要的日常审核入口:

- Inbox 风格 (单列列表 + 右抽屉)
- 顶部筛选: 状态 (pending / approved / rejected / merged), 行业, 提交时间
- 每条: 用户 email / 提交时间 / 行业 / 品牌名 / 用户补充信息 / LLM 预验证徽章

抽屉内容:
- 用户提交原始内容
- LLM 预验证结果 (存在性 / 行业归属 / 可能官方名称)
- Action: approve / reject / merge
  - approve -> 触发 KG 入库流程 + 异步产品发现
    **Bootstrap 触发（Outbox Pattern）**: Approve 动作同步写入 `brand_bootstrap_jobs` 表一条（status=pending）。Planner 5 分钟轮询 worker 认领并启动首日采集。**禁止**在 API handler 内直接触发同步采集（会导致 Admin 接口超时）。
  - reject -> reason 必填, 发回邮
  - merge -> 选择已有品牌, alias 追加

SLA 监控:
- 超 24h 未处理 -> 列表项红色标记 + 首页告警

## 7. Discovery Logs /admin/kg/discovery-logs

- 列表: 时间 / LLM / Prompt 类型 (品牌发现/产品发现) / 行业 / 入库数量 / 失败数
- 详情: 完整 LLM input + output (JSON viewer)
- 筛选: 时间 / LLM / 类型
- 质量指标: 近 30 天 LLM 发现品牌的 approved 比率 (顶部 KPI)

## 8. API 清单

所有走 requireRole + withAudit:

GET    /admin/api/v1/kg/industries
POST   /admin/api/v1/kg/categories        (create under parent)
PATCH  /admin/api/v1/kg/categories/:id    (rename / move / deprecate)
POST   /admin/api/v1/kg/categories/llm-suggest
GET    /admin/api/v1/kg/brands?status=...
GET    /admin/api/v1/kg/brands/:id        (含 mentions + discovery source)
POST   /admin/api/v1/kg/brands/:id/approve
POST   /admin/api/v1/kg/brands/:id/reject
POST   /admin/api/v1/kg/brands/batch-review (body: action, ids, reason)
POST   /admin/api/v1/kg/brands/:id/merge  (body: targetId, reason)

同类端点对 /products

GET    /admin/api/v1/kg/aliases/conflicts
POST   /admin/api/v1/kg/aliases/resolve
GET    /admin/api/v1/kg/relations/issues
POST   /admin/api/v1/kg/relations/batch-update

GET    /admin/api/v1/kg/brand-submissions?status=...
GET    /admin/api/v1/kg/brand-submissions/:id
POST   /admin/api/v1/kg/brand-submissions/:id/approve
POST   /admin/api/v1/kg/brand-submissions/:id/reject
POST   /admin/api/v1/kg/brand-submissions/:id/merge

GET    /admin/api/v1/kg/discovery-logs?from=...
GET    /admin/api/v1/kg/discovery-logs/:id

## 9. 批量操作的幂等性 + 审计

批量 approve/reject 必须幂等:
- 重复 approve 已 approved 的品牌 -> noop (但仍写一条 audit)
- batch 操作审计要精细: 每个 target_id 一条 audit 记录, reason 共用

## 10. 测试

- 单测: KG 关系边置信度更新逻辑
- 集成: approve brand submission -> kg_brands 出现 -> 触发产品发现
- 集成: merge 品牌 -> 源品牌的别名和关系合并到目标, 源品牌状态变 merged
- verify-admin-session-A3.sh

完成后更新 CLAUDE.md (新增: KG 运营模块), 并在 PRD.md 中补一个
"KG 审核流程" 的链接指向本 Admin 模块。

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### 对抗性验证 (adversarial-A3.md 要点)

- Merge 并发: 同时 merge A→B 和 B→C 会不会形成环 / 丢数据
- Approve 触发异步任务: 审核员连点 2 次 approve 会不会重复触发产品发现
- LLM 预验证: reject 后的 submission 重新激活会不会穿透缓存
- 大批量 reject: 1000 条批量 reject 的性能 + 邮件风暴
- 别名归属后反悔: 撤销是否可行

### 规约对齐 (compliance-A3.md 要点)

- §4.3.1-§4.3.6 每个子页面字段齐全?
- §4.3.5 的 24h SLA 监控是否上首页告警?
- §5.2 审计: 所有 KG 写入都有 audit?

### Phase Gate

A-Gate 3 (45min): 人类处理一批真实 / mock 的 20 条 Brand Submission，记录平均耗时 / 误判率。

---

## Session A3.1 · 实体合并/拆分 & 信任分 (KG 深化 · Part 1/3)

### 前置依赖

- Session A3 完成
- 深化规格: [`ADMIN_PRD_C_KG.md`](./ADMIN_PRD_C_KG.md) §C7

### 新增子页

- **C7 Entity Merger/Splitter** `/admin/kg/entity-ops`
  - 同品牌不同拼写 / 同产品重复入库的合并 (保留 ID, 迁移别名, 重建关系)
  - 误合并实体的拆分 (支持从 `entity_merge_log` 逆向还原)
  - 状态机可视化: `discovered → submitted → approved → active` + 分支 (rejected / merged / inactive)
- **信任分四档体系** (`submission_trust_score`):
  - `fast_track` (自动通过, 仅写 audit) / `normal` (人工审核) / `review_required` (强制两层审核) / `blocked` (拒绝)

### 新增表

- `kg_brand_aliases` (brand_id, alias_text, locale, source, confidence)
- `kg_brand_relation_history` (id, brand_a, brand_b, relation_type, confidence, created_at, deprecated_at)
- `kg_product_lines` (id, brand_id, line_name, parent_line_id)
- `submission_trust_score` (user_id, tier, score, last_updated_at, reason)
- `entity_merge_log` (id, source_entity_id, target_entity_id, entity_type, merged_by, merged_at, can_split_until)
- `discovery_feedback_negatives` (discovery_id, reviewer_id, reason_code, feedback_notes)

### 三层 QA

**Executable Acceptance**:
```bash
# 合并操作能迁移别名 + 保留关系
curl -X POST /admin/api/v1/kg/entities/merge -d '{"source":"brand_123","target":"brand_456"}'
SELECT count(*) FROM kg_brand_aliases WHERE brand_id = 'brand_456'; -- 期望 = 原来 target 的 + source 的
# 拆分在 7 天窗口内可回滚
curl -X POST /admin/api/v1/kg/entities/split -d '{"merge_id":"merge_789"}'
```

**Adversarial**: "合并后关系边的 confidence 如何加权? 如果 source 有 `COMPETES_WITH target`, 合并后这条边是否删除?"

**Spec Compliance**: "对照 §C7 检查: 状态机转换是否全有 audit、信任分 `fast_track` 是否真的只写 audit 不要人工、`can_split_until` 是否默认 7 天?"

### Phase Gate

A-Gate 3.1 (45min): 人类处理 10 组合并/拆分 case, 记录耗时 + 数据一致性。

---

## Session A3.2 · KG Diff Viewer (KG 深化 · Part 2/3)

### 前置依赖

- Session A3 + A3.1 完成
- 深化规格: [`ADMIN_PRD_C_KG.md`](./ADMIN_PRD_C_KG.md) §C8

### 新增子页

- **C8 KG Diff Viewer** `/admin/kg/diff?from=2026-04-15&to=2026-04-16`
  - 每日快照 + 两日 diff (新增/删除/修改品牌 / 产品 / 关系)
  - 用树视图 (AntV G6 v5) 高亮变化节点
  - 可回滚单条变更 (revert 动作写 `admin_audit_log`)

### 新增表

- `kg_daily_snapshot` (snapshot_date, entity_type, entity_id, payload_json, parent_id)
- `kg_daily_diff_cache` (from_date, to_date, diff_summary, computed_at, payload_json)

### 三层 QA

**Executable Acceptance**:
```bash
# 昨日 vs 今日 diff 能返回结构化结果
curl /admin/api/v1/kg/diff?from=2026-04-15&to=2026-04-16 | jq '.summary'
# 变化数据能在 G6 树上高亮
```

**Adversarial**: "快照表会不会爆大 (每天全量 × 365 天)? 如何做压缩 / 归档?"

**Spec Compliance**: "对照 §C8 检查: diff 是否用 cache 避免重算、回滚是否真触发 kg_brand_relation_history 写入?"

### Phase Gate

A-Gate 3.2 (30min): 人类在 staging 查最近 7 天 diff、回滚一条误录入的关系。

---

## Session A3.3 · KG 质量监控 & LLM 预算闸门 (KG 深化 · Part 3/3)

### 前置依赖

- Session A3 + A3.1 + A3.2 完成
- 深化规格: [`ADMIN_PRD_C_KG.md`](./ADMIN_PRD_C_KG.md) §C9

### 新增子页

- **C9 KG Quality Monitor** `/admin/kg/quality`
  - Overall score = `w1·(1-hallucination_rate) + w2·(1-alias_conflict_rate) + w3·(1-orphan_rate) + w4·relation_confidence_median + w5·SLA`
  - 孤儿实体列表 (无关系 / 无 Topic 命中的品牌/产品)
  - LLM 预算闸门: `daily_kg_llm_budget` 超阈值自动 disable Discovery & Hallucination Verification

### 新增表

- `kg_quality_metrics` (date, hallucination_rate, alias_conflict_rate, orphan_rate, relation_confidence_median, sla_attainment, overall_score)
- `kg_orphan_list` (entity_type, entity_id, reason, detected_at)
- `daily_kg_llm_budget` (date, budget_cny, consumed_cny, disabled_at, disabled_reason)

### 三层 QA

**Executable Acceptance**:
```bash
# overall_score 能每日跑出
SELECT overall_score FROM kg_quality_metrics WHERE date = CURRENT_DATE - 1;
# 预算超了自动 disable
SELECT disabled_at, disabled_reason FROM daily_kg_llm_budget WHERE date = CURRENT_DATE;
```

**Adversarial**: "overall_score 权重 w1-w5 是否文档化? 如果某天 hallucination_rate 跳升, 系统是否自动告警还是等人去看?"

**Spec Compliance**: "对照 §C9 检查: 预算闸门是否真关掉 LLM (断电层在 pipeline, 不只是 UI 开关)、孤儿实体判定条件是否合规?"

### Phase Gate

A-Gate 3.3 (30min): 人类模拟"LLM 预算提前用尽", 验证闸门真关掉后续调用 + 告警推送到飞书。

---

## Session A4 · 成本 & 告警 & 调度 & 商务 & MCP

### 前置依赖

- Session A1-A3 完成
- App Session 3 完成 (分析 API + MCP Server 可用)

### 目标

实现 ADMIN_PRD §4.4 全部子模块 + §8.1 的 M5 + M6 + §8.2 的 S4-S7。

### Prompt

```
你是 GENPANO Admin 的实施 Session A4。

请先阅读:
- CLAUDE.md
- docs/ADMIN_PRD.md §4.4 全部
- 现有 src/mcp-server/**, /api/v1/** (App Session 3 产出)
- Session A1-A3 的 withAudit / AdminLayout / KG Review Queue

## 1. 数据模型新增

cost_daily         (date, engine, category enum('llm_api','proxy','scrape_compute','email'),
                   industry_id?, brand_id?, amount_cny, token_count, calls_count)
  -- materialized view, 每日 03:00 refresh

budget_config      (scope enum('global','engine','industry'), key, value_json, updated_at, updated_by)

alerts             (id, severity enum('P0','P1','P2','P3'), module, title, detail_md,
                   first_seen_at, last_seen_at, count, status enum('new','acknowledged','resolved'),
                   owner_id?, resolved_at?, created_at)

commercial_leads   (id, source, company, contact_name, email, phone, industry, note,
                   status enum('new','contacted','qualified','won','lost'),
                   assigned_to?, followup_at?, created_at, updated_at)

announcements      (id, title, body_md, link?, audience enum('all','industry'), audience_ref?,
                   priority, starts_at, ends_at, enabled, created_by, created_at)

mcp_request_samples (id, api_key_id, tool, payload_redacted JSONB, latency_ms, status,
                   error_type?, created_at)
  -- 采样率 10% (ADMIN_PRD §10.2), 保留 30 天

## 2. 成本看板 /admin/cost/daily

按 ADMIN_PRD §4.4.1:

顶部 KPI (4 格):
- 当日总成本 / 本月累计 / 预算余额 / 预估月度支出
- 余额 < 20% -> 红色

三级下钻:
- 堆叠面积图: 近 30 天 × 引擎 × category (Recharts Area)
- 饼图: 当日 按行业
- 水平条形: 当日 品牌 Top 10

预算管理卡:
- 当日硬上限 (显示 + 修改, 二次确认 + reason)
- 当前使用 % 进度条
- "紧急提高预算" 入口 (input + 二次确认 + 写审计)

超预算自动停采:
- 后端 cron / hook 检查: 当日成本 ≥ 每日上限 -> engine_runtime_config.is_paused = true
- 写入 alerts 表 (P0)
- Admin 首页红条告警

## 3. 告警中心 /admin/alerts

按 ADMIN_PRD §4.4.2:
- Inbox 列表 (new / acknowledged / resolved tab)
- 顶栏筛选 (severity / module / 时间)
- 每条: icon + 标题 + 模块 + 首次/最后 + 次数 + 状态
- 动作: 认领 / 标记已解决 / 批量解决

告警来源 (后端产生, Admin 消费):
- 成功率跌破阈值
- 账号池水位低
- 成本超预算
- Brand Submission SLA 超时
- 系统错误聚合 (同类 error + 频率)

## 4. 调度配置 /admin/schedule

按 ADMIN_PRD §4.4.3, MVP 最小:
- 总 kill switch (停止所有平台调度)
- 每日开始时间 (UTC offset)
- 分层频率 (high / medium / low) - MVP 显示只读
- 单次采集预算 (daily query cap)

手动触发区:
- 立即对某品牌跑一次全量采集:
  表单: 选品牌 + 选引擎 (多选) + 数量上限 + reason + 二次确认
- 补采某 Topic:
  表单: Topic ID + 二次确认

## 5. 公告 & 邮件 /admin/comms

按 ADMIN_PRD §4.4.4:

### 公告 Banner CRUD
- 列表 + 新建 / 编辑 / 启用 / 停用
- 预览: 同 App 实际渲染效果
- audience: all / industry (下拉选 4 行业)
- 同时最多 1 条启用 (按 priority 高优)

### 邮件模板
- 列表 (只读): 验证 / 欢迎 / 密码重置 / Brand Submission 批复 / 周报
- 每条 -> 预览 (zh-CN / en-US 切换) + "发测试邮件到 [admin@xx]"
- ❌ 禁止在 UI 改模板 HTML

## 6. 商务线索 /admin/commercial/leads

按 ADMIN_PRD §4.4.5:
- 列表: 来源 / 公司 / 联系人 / 行业 / 提交时间 / 状态 / 跟进日期
- 筛选: 状态 / 来源 / 行业 / 时间
- 行点击 -> 详情抽屉:
  - 完整信息
  - 状态变更 (下拉)
  - 备注历史
  - 跟进日期编辑
- 导出 CSV (super_admin 或 bizdev)

## 7. Agent/MCP 运营 /admin/mcp-ops

按 ADMIN_PRD §4.4.6:

### API Key 列表
- 字段: 用户 / Key 名称 (masked) / 创建时间 / 最近调用 / 调用量 24h/7d/30d / 限流命中 / 状态
- 动作: 调整 rate limit (表单) / suspend / 查看详情

### MCP 调用趋势
- 每个 MCP tool 的日调用数 + P95 延迟 + 错误率
- 近 14 天趋势 (堆叠面积图 + 折线)

### 抽样查询
- 随机抽 20 条 MCP 请求的 payload
- 显示: 时间 / tool / api_key (masked) / payload_redacted / 延迟 / 状态
- 筛选: tool / 时间 / 状态

## 8. API 清单

全部走 requireRole + withAudit:

GET    /admin/api/v1/cost/daily?from=...
GET    /admin/api/v1/cost/by-engine
GET    /admin/api/v1/cost/by-industry
GET    /admin/api/v1/cost/by-brand
GET    /admin/api/v1/budget
POST   /admin/api/v1/budget/:scope/:key  (update, reason 必填)
GET    /admin/api/v1/alerts?status=...
POST   /admin/api/v1/alerts/:id/acknowledge
POST   /admin/api/v1/alerts/:id/resolve
POST   /admin/api/v1/alerts/batch-resolve
GET    /admin/api/v1/schedule/config
PATCH  /admin/api/v1/schedule/config
POST   /admin/api/v1/schedule/kill-switch
POST   /admin/api/v1/schedule/manual-trigger
GET    /admin/api/v1/announcements
POST   /admin/api/v1/announcements
PATCH  /admin/api/v1/announcements/:id
DELETE /admin/api/v1/announcements/:id
GET    /admin/api/v1/email/templates
POST   /admin/api/v1/email/templates/:key/test-send
GET    /admin/api/v1/leads?status=...
PATCH  /admin/api/v1/leads/:id
GET    /admin/api/v1/mcp-ops/api-keys
GET    /admin/api/v1/mcp-ops/tools-stats
GET    /admin/api/v1/mcp-ops/request-samples
POST   /admin/api/v1/mcp-ops/api-keys/:id/rate-limit

## 9. 首页 Overview 聚合

把 Session A2 + A3 + A4 的核心指标聚合到 /admin (首页):

按 ADMIN_PRD §3.2:
- 顶部告警条 (取 alerts 表 severity=P0 的前 3 条)
- 4 格 KPI (成功率 / 成本 / 新注册 / 活跃 Project) - 新接口 GET /admin/api/v1/overview
- Pipeline 四层漏斗 mini (link to /admin/pipeline/overview)
- 引擎健康 mini (3 个引擎的条形)
- 待办 Inbox (kg_review_queue + brand_submissions + 失败任务 + 线索)
- 近 7 天趋势 (3 个小图)

## 10. 测试

- 集成: 模拟 LLM 成本激增 -> 触发 alert + engine pause
- 集成: 调度手动触发 -> Query 入队 -> 跑完回写
- 集成: announcement 启用 -> App 前端实际看到 banner
- verify-admin-session-A4.sh

完成后:
- 更新 CLAUDE.md "Admin 模块" 节
- 把 §8.3 Phase 2 预留的 Org/Billing/Approvals 写入 CLAUDE.md "已知预留"
- Phase Gate A-Gate 4 就绪

---
**Token 强引要求**: 所有颜色、间距、尺寸必须从 `src/theme/tokens.ts` 读取；禁止硬编码 hex / rem / px。详见 `DESIGN_TOKENS.md`。
```

### 对抗性验证 (adversarial-A4.md 要点)

- 预算修改 race: 多人同时改预算 -> 乐观锁
- 告警风暴: 同类错误爆量 -> 去重 / 聚合窗口
- MCP 采样: 10% 采样是否泄露高敏 payload
- Announcement priority 冲突: 两条同 priority 同时 enabled
- 手动触发 DoS: 用手动触发绕过预算
- CSV 导出: 大 lead 表 100k 行内存爆炸

### 规约对齐 (compliance-A4.md 要点)

- §4.4.1 成本归因三级视图齐全?
- §4.4.2 告警来源 5 类全对接?
- §4.4.5 MVP 边界: **不** 做订单 / 发票 / Stripe?
- §4.4.6 MCP 调用 10% 采样率生效?
- §3.2 首页聚合的所有块都可见?

### Phase Gate

A-Gate 4 (1 day): Frank 用 Admin 做一整天运维，目标是"20min 内完成日常巡检"。记录体感阻塞点，形成 Fix Session 或 Phase 2 需求。

---

## 测试任务补丁 · A2.2 / A2.3 / A2.4 / A3 (2026-04-21 Review 新增)

> Review 2026-04-21 §2 指出 Admin 侧 4 个 Session 缺测试任务说明, 本节作为它们的**测试任务附录**. 各 Session 的"三层 QA / 测试"小节必须消费本附录.

### A2.2 (Tracker 核心) 测试任务

**L1 Harness** (Admin 侧追加到 `scripts/admin/ci-check.mjs`):
- `adapter-har-must-sanitize`: Admin HAR 文件上传必须经 `sanitizeHar()` 函数, 禁直接写 S3
- `har-routeFromHAR-usage`: Admin 调试回放入口必须用 `page.routeFromHAR()`, 不准真访问外网

**L2 单测**: `proxy-scheduler.test.ts`, `account-quarantine.test.ts` (7d 冷却算法)

**L3 集成**: `har-replay-all-adapters.test.ts` — 消费 TEST_STRATEGY §12.2 HAR fixture 矩阵 (3 引擎 × 9 错误码), 验证 Admin Tracker UI 回放时解析结果等于 `.expected.json`

**L4 E2E**: `admin-scheduler-dashboard.spec.ts` + `admin-har-replay-ui.spec.ts` Visual baseline

**专项 (§10.1 表中单列的 A2.2)**: `har-golden-replay.test.ts` 跑 27 份 HAR fixture 各 1 次, 任何一条预期失配 → CI 红.

### A2.3 (Tracker 深化 + 变更审批) 测试任务

**L1 Harness**:
- `kg-change-type-enum`: `admin_change_audit.change_type` 枚举必须含 `KG_MERGE / KG_SPLIT / KG_DEMOTE / KG_RECLASSIFY / KG_DOMAIN_LINK / KG_DOMAIN_UNLINK` (此前只有 CREATE/UPDATE/DELETE), grep 字段定义文件补齐

**L2 单测**: `kg-audit-log.test.ts` — 每种 change_type 写入审计的字段完整性 (actor / target_before / target_after / reason / related_response_ids)

**L4 E2E**: Admin 对 KG 做 1 次 merge + 1 次 reject 操作, 截屏 diff viewer 有前后对比

### A2.4 (Analyzer 质量 / 人工质检) 测试任务

**L1 Harness**:
- `qa-sample-stratify-min`: QA campaign 采样器必须至少覆盖 5 层 `(engine × intent × dimension × profileGroup × sentiment_bucket)`, grep 采样函数签名确保 5 个 stratify key 都被传入

**L2 单测**: `qa-sampler.test.ts` — 分层抽样算法 (比如某层样本数 < 5 时回退策略), 5 个边界测试

**L3 集成**: `qa-campaign-e2e.test.ts` — 启动 campaign → 分配任务 → 标注完成 → 结果落库 → Trust Score 更新

**L4 E2E + Visual**: `admin-qa-dashboard.spec.ts` 含"样本不足"空态 visual baseline

### A3 (KG 运营 + Trust Score + 幻觉检测) 测试任务

**L1 Harness**:
- `trust-score-formula`: Trust Score 计算公式必须在 `src/admin/trust/formula.ts` 单入口, 禁业务代码自行计算
- `hallucination-detector-threshold`: 幻觉阈值 (默认 0.3) 必须走 `parameter_service.get('hallucination_threshold')`, 禁 literal 硬编码

**L2 单测**: 
- `trust-score.test.ts` — Trust Score 衰减公式 (参考 PRD §4.8 若定义否则用 `raw = extract_success_rate × citation_attribution_rate × (1 - hallucination_rate)`) + 11 个边界值
- `hallucination-detect.test.ts` — 幻觉检测规则引擎 (已知品牌不在知识图谱中出现 / 引用的 URL 域名与品牌域名库无交集 / 产品规格与产品库不一致) 5 case

**L3 集成**: `trust-trend-ingest.test.ts` — 每日聚合 Trust Score 写入 `metric_snapshots`, 折线图消费

**L4 E2E**: `admin-trust-dashboard.spec.ts` 含引擎 Trust 对比图 Visual baseline

---

## Session A5 · Citation Tier CRUD + MCP Token 签发 (2026-04-21 新增)

### 前置依赖
- A0 (Auth) + A1 (脚手架) 完成
- App 侧 PRD §4.2.6 (Citation Tier) 与 §4.5.2 (MCP Server) 已冻结
- 决策 #19 (Citation Tier 表禁硬编码) 已固化

### 目标

- 实现 `citation_domain_authority` 表的 Admin CRUD (5 级 Tier 权重 + Tier 2/3 域名归类 + 置信度调整)
- 实现 API Token 签发 / 废除 / 审计 (MCP Server 消费)
- 两者都是"决策 #19 + MCP Day-1 auth 要求"的 Admin 侧缺失闭环

### 交付物

- `/admin/citation/tier-crud` 页面 (列表 + 编辑 modal + 历史回溯重算 job)
- `/admin/mcp/tokens` 页面 (签发 + 禁用 + 审计 + rate-limit 配额设置)
- Backend API `/admin/api/v1/citation/tier/*` + `/admin/api/v1/mcp/tokens/*`
- 回溯重算 worker `scripts/admin/recompute-citation-authority.ts`

### PRD / 决策对应

- App PRD §4.2.6 (Citation Tier + citation_domain_authority)
- App PRD §4.5.2 (MCP Server 工具集)
- 决策 #9 (MCP Day-1 Bearer Token 强制)
- 决策 #19 (Citation Tier + URL 归一化)

### Prompt

```
继续 GENPANO Admin 开发。

开工前必读:
1. docs/ADMIN_PRD.md 对应 Citation & MCP 章节
2. docs/PRD.md §4.2.6 + §4.5.2 全文
3. CLAUDE.md 决策 #9, #19
4. docs/TEST_STRATEGY.md §10.1 A5 行 (测试覆盖要求)

本 Session 目标: 补 Admin 侧对 Citation Tier 参数服务 和 MCP Token 签发 的运营界面, 使 App 侧
PRD §4.2.6/§4.5.2 的运行时依赖项有运营入口. 没有本 Session, App 决策 #19 的"Tier 不硬编码"
和 #9 的"MCP Bearer Day-1"都只有 schema 没有运营入口.

## 1. Citation Tier 参数管理

### 1.1 表结构确认 (若 A2/A3 尚未迁移, 本 Session 迁)
- `citation_domain_authority` (5 级 Tier 权重表, seed 必须运行时加载, 不硬编码)
- `citation_domain_classifications` (域名 → Tier 归属, 源 '官方域名库' / 'Tier 2 权威媒体' / 'Tier 3 KOL' / 'Tier 4 UGC')

### 1.2 /admin/citation/tier-crud UI
- 顶部 5 行 Tier 权重行 (slider 0.0-1.0 + 绝对值) + Save
- 下方域名分类表 (TanStack Table 分页 + 搜索 + 批量改 Tier)
- 编辑后触发 side effect: "本次权重变化是否重算历史 citation_share? [确认/取消]"

### 1.3 回溯重算 job
- Worker `scripts/admin/recompute-citation-authority.ts`
- 参数: `--from=YYYY-MM-DD --to=YYYY-MM-DD --brand_id=<可选>`
- 行为: 拉时间段内 `ai_response_citations`, 按新 Tier 权重重算每条 citation 的 tier_weight, 更新 `ai_response_citations.effective_tier_weight` + 汇总到 `metric_snapshots.citation_share`
- 幂等: 多次跑结果一致 (无递归放大)

### 1.4 审计
- 权重修改 / 域名分类修改都写 `admin_change_audit.change_type='CITATION_TIER_UPDATE'`
- 回溯重算 job 触发写 `admin_jobs.job_type='citation_authority_recompute'`, 包含影响行数和耗时

## 2. MCP Token 签发

### 2.1 表结构
- `mcp_api_tokens(id, user_id, label, token_hash, scopes text[], rate_limit_rpm, expires_at, revoked_at, created_by_admin_id, created_at)`
- Token 明文 JWT + secret, Admin UI 只在创建时显示一次, 其后永远 ***

### 2.2 /admin/mcp/tokens UI
- 列表: user / label / scopes / rate_limit / 创建时间 / 状态 (active/revoked/expired) / 最后使用
- 签发 modal: 选 user + label + scopes 多选 + rate_limit + 有效期
- 签发成功显示 Token 明文 + 一次性复制按钮 + 警告 "此 Token 仅显示一次"
- 撤销: 一键 revoked_at=NOW(), 黑名单 60s 内全节点同步 (通过 Redis pub-sub)

### 2.3 API Contract
- `POST /admin/api/v1/mcp/tokens` 创建 (返回明文)
- `GET /admin/api/v1/mcp/tokens` 列表 (永远不返回 token_hash 解密)
- `POST /admin/api/v1/mcp/tokens/:id/revoke`
- `GET /admin/api/v1/mcp/tokens/:id/audit` 该 token 的调用审计 (最近 1000 条)

### 2.4 App 侧消费
- App 的 MCP middleware 校验 token_hash 时必须走 `mcp_token_service.verify()` 单入口
- 该服务内部: (a) 查 DB + 缓存 60s; (b) 查 Redis 黑名单; (c) 写调用审计 `mcp_call_audit`
- 任何 App 代码若直接 `jwt.verify(bearer)` → harness 拦截 `mcp-token-bearer-only`

## 3. 测试 (详见 TEST_STRATEGY §10.1 A5 行)

### 3.1 L1 Harness
- `citation-tier-seed-required`: 启动时若 `citation_domain_authority` 5 行不齐, fail-fast (parameter_service)
- `mcp-token-bearer-only`: App MCP path `/api/mcp/**` 处理器必须先走 verifyMcpToken, grep 缺失即报
- `mcp-token-jwt-exp`: `jwt.sign(...)` 调用必须含 `expiresIn` 不超过 configured_max (默认 365d)

### 3.2 L2 单测
- `tier-crud.test.ts` (CRUD + 回溯 job 幂等)
- `mcp-token-issue.test.ts` (签发+明文只发 1 次+revoke 广播)

### 3.3 L3 契约
- `mcp-token-bearer-contract.test.ts` (消费 openapi.yaml 定义的 /api/mcp/* 端点, 无 Bearer 返 401, 错 Bearer 返 401, 正确 Bearer 返 200)

### 3.4 L4 E2E + Visual
- `admin-tier-crud.spec.ts` + `admin-mcp-token.spec.ts` visual baseline 各 1 份

## 4. 验收

- /admin/citation/tier-crud 页面 5 Tier 权重可编辑, Save 后 App 侧 PANO A 指标下次计算反映新权重
- /admin/mcp/tokens 签发 Token 后, 用该 Token 调 `/api/mcp/genpano_get_panorama` 返 200
- Revoke 后 60s 内再调返 401
- 历史 14 天 citation_share 回溯重算能跑完 (单品牌 < 30s)

请开始执行。每完成一个大步骤，简要汇报进展。
```

### 预期产出
- `/admin/citation/tier-crud` + `/admin/mcp/tokens` 两个 Admin 页面
- `mcp_api_tokens` 表迁移 + Prisma model
- 回溯重算 worker script
- 5 条测试文件 (见 §3)
- A5 审计日志字段扩展

### 验收标准
- [ ] Citation Tier 权重可通过 Admin UI 修改, 修改后 App 侧下次计算生效
- [ ] 可一键触发历史 14 天回溯重算, 结果幂等
- [ ] MCP Token 签发明文仅展示 1 次, revoke 后 60s 全节点生效
- [ ] TEST_STRATEGY §10.1 A5 行 4 层全绿
- [ ] Harness `citation-tier-seed-required` / `mcp-token-bearer-only` / `mcp-token-jwt-exp` 3 条纳入 `scripts/admin/ci-check.mjs` 并跑绿

### Phase Gate

A-Gate 5 (半天): Frank 验证 Tier 调权 → 回溯重算 → App 面板指标变动的端到端闭环, 并试发 1 个 MCP Token 调用成功; 记录操作耗时预期 < 10 分钟.

### A5 与其他 Session 依赖

- **前置**: A0 + A1
- **并行**: 可与 A3.1-A3.3 并发
- **被依赖**: App Session 5 (MCP Server 实现) 上线前必须等 A5 就位, 否则 Token 签发路径为空

---

## Admin Fix Session (如果需要)

A-Gate 4 后预期会发现 10-20 个体验 / bug 问题，开一次 Fix Session 统一修复：

```
请阅读 CLAUDE.md + docs/ADMIN_PRD.md + review/admin-session-A*-adversarial.md。

以下是 A-Gate 4 整日试运营发现的问题，逐项修复:

## 严重 (必修)
1. ...

## 一般 (尽量修)
2. ...

## 体验优化
3. ...

修完跑一遍 verify-admin-session-A{1..4}.sh 确认不 regress，更新 CLAUDE.md 已知问题。
```

---

## 资源估算 (Admin 全部 Session)

| Session | 覆盖范围 | 人类时间 | AI 时间 | 日历时间 |
|---|---|---|---|---|
| A0 认证脚手架 | 登录/会话/密码/re-auth | 1h | 3-4h | 1 天 |
| A1 脚手架+账号 | Layout/RBAC/审计/用户运营 | 2h (Review) | 4-6h | 1.5 天 |
| A2 Dashboard+Planner 核心 | 全部数据模型+Dashboard+调度+生成管线+资源 | 3h (Review+手测) | 10-12h | 2.5 天 |
| A2.1 Planner 深化 | Prompt 模板(A/B)+ProfileGroup | 2h | 6h | 1.5 天 |
| A2.2 Tracker 核心 | Attempt 列表+引擎健康+DLQ+重试规则 | 3h (Review+手测) | 10h | 2 天 |
| A2.3 Tracker 深化+变更审批 | Trace/Lineage+变更审批中心 | 2h | 5h | 1 天 |
| A2.4 Analyzer | 质量分析+人工质检 | 2h | 6h | 1.5 天 |
| A3 KG 运营 | 行业/品牌/产品/别名/Submission/Discovery | 2h (Review) | 4-6h | 1.5 天 |
| A4 成本+告警+商务+MCP | 成本看板+告警中心+调度+公告+线索+MCP | 3h (Review) | 5-7h | 2 天 |
| Fix Session | Phase Gate 后修复 | 2h | 3-5h | 1 天 |
| **合计** | | **~22h** | **~56-67h** | **~15 天** |

Pipeline 模块 (A2 系列) 从 1 个 Session 扩展为 5 个，反映了 Planner/Tracker/Analyzer 三大模块的实际复杂度。可并行: A2.1 和 A2.2 可并发; A1 完成后 A2/A3 可并发; A4 需等 A2+A3 合并后做首页聚合。

---

## 附录: Admin Session 之间的依赖图

```
              A0 (认证脚手架)
                    ↓
              A1 (脚手架 + 账号)
             /                 \
            ↓                   ↓
    A2 (Dashboard+Planner)    A3 (KG)
       ↓         ↓               |
    A2.1    A2.2 (可并行)         |
    (Prompt  (Tracker 核心)       |
     +Profile)    ↓               |
            A2.3 (Trace+变更审批) |
                  ↓               |
            A2.4 (Analyzer)       |
                  \              /
                   ↘            ↙
              A4 (成本 + 告警 + 商务 + MCP)
                        ↓
                  Fix Session
                        ↓
                    上线部署
```

---

**End of Admin Sessions Plan v2.0** (2026-04-19 · Planner/Tracker/Analyzer 重构)
