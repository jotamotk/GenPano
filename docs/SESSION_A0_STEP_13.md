# Session A0 · Step 13 Prompt (To CC)

> 背景: Step 11.6 刚回滚 Step 11.5 的虚假偏差 (failedLoginCount/lockedUntil DB 持久化), 顺便发现 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` A1 段 `§2. Admin 数据模型迁移` 的 inline Prisma schema 清单 **与 A0 实落字段存在反向 drift** — 本 Step 趁 Frank 跑 Phase Gate 的空档, 把 A1 启动时最大的两个坑一次性关掉, 并固化 §0 新规则阻止这类 drift 再发生。
>
> 发起时间: 2026-04-21
> 本 Step 性质: **纯文档 patch, 不碰任何 .ts/.tsx/.prisma 代码**
> 预期耗时: 15 分钟

---

# Step 13 · A1 Spec 反向同步 + §0 规则 8 固化

## 背景 · 为什么要做这个 Step

A0 实施过程中, CLAUDE.md #24 记录了 AdminUser 扩 3 字段 (`forcePasswordChangeAt` / `lastPasswordAt` / `lastLoginAt`, Prisma DSL 下 `force_password_change_at` / `last_password_at` / `last_login_at`), ADMIN_PRD §5.6.8 已同步。但 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` **A1 段 §2 的 inline Prisma schema 清单**:

```
line 452:  admin_users  (id, email, password_hash, role enum, status, totp_secret?, created_at, updated_at, last_login_at)
```

**两处漂移**:
1. `totp_secret?` · **phantom 字段** — A0 没落地, ADMIN_PRD §5.6.8 也没有, 是 A1 Prompt 写作时独立想象的 (§0 规则 1 明令禁止的"完整重抄 + 独立想象"反模式)
2. **缺 A0 实落的 3 字段** · `force_password_change_at` / `last_password_at` / `last_login_at` (虽然 `last_login_at` 重复出现在 line 452 末尾, 但 `force_password_change_at` / `last_password_at` 完全缺失)

A1 启动时若 CC 直接按 line 452 的 inline schema 写 Prisma model, 会产生: (a) 新增一个 DB 列 `totp_secret` — 不在 PRD, 后面 migration 又要回收; (b) 漏掉 A0 已落地的 2 字段 — schema diff 报冲突。

**同时 A1 line 458 的 REVOKE 语句** `REVOKE UPDATE, DELETE ON admin_audit_log FROM application_role;` — role 名 `application_role` 是**占位符**, 本地 Postgres 实际角色名可能不存在, 需要 A1 实施时明确化 (或加 TODO)。

**根因** · §0 目前 7 条规则里**没有一条**覆盖"Session X 完工后, 下游未开工 Session Y 的 Prompt 里引用 X 产出字段清单的地方要反向同步"。本 Step 顺便把这条固化为规则 8。

## 真相源索引 (§0 规则 5)

实施前必读:
- A1 inline schema drift 位置 → `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` line 449-459 (§2. Admin 数据模型迁移)
- AdminUser 真实字段清单 → `docs/ADMIN_PRD.md §5.6.8` + `CLAUDE.md` 决策 #24 C1.3 (Step 11.6 回滚后)
- §0 现有规则列表 → `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` line 55-157

## Task 1 · A1 §2 inline schema 回填 (关 A1 最大坑)

### 1.1 定位

`docs/ADMIN_CLAUDE_CODE_SESSIONS.md` line 449-459 当前内容约为:

```
## 2. Admin 数据模型迁移 (Prisma)

新增以下表 (字段以 ADMIN_PRD §4.1.4 + §5.2 + §5.5 + §4.4.8 对应部分为准):
  admin_users          (id, email, password_hash, role enum, status, totp_secret?, created_at, updated_at, last_login_at)
  admin_audit_log      (id, operator_id, action, target_type, target_id, diff_json, reason, ip, ua, created_at)
  user_moderation_actions (id, user_id, operator_id, action, reason, expires_at, created_at)
  user_activity_stats  (user_id primary key, last_login_at, login_count_30d, project_count, api_call_count_7d, updated_at) -- 定时 job 填充

迁移额外执行:
  REVOKE UPDATE, DELETE ON admin_audit_log FROM application_role;
  -- 只保留 INSERT + SELECT
```

### 1.2 整段替换为 (按 §0 规则 1 · 不重抄真相源, 改为增量引用式)

```
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
```

### 1.3 注意保留

- line 460 及之后的 `## 3. RBAC 中间件` / `## 4. 审计日志自动接入` / ... 全部不动
- `admin_audit_log` 的 `withAudit` 段 (line 468-476) 不动
- A1 §9 测试段 (line 540) 提到 `任何写操作 -> admin_audit_log 有记录` 不动
- A1 "预期产出" 段 line 557 `Prisma migration (新增 4 张表 + REVOKE 语句)` 不动 (仍正确)

## Task 2 · §0 新增规则 8 · Cross-Session Boundary 反向同步

### 2.1 定位

`docs/ADMIN_CLAUDE_CODE_SESSIONS.md` line 143-153 (规则 7 · Session 完成时反查一致性) 末尾, 在 line 153 "不一致 → 不能 merge, 补齐后重跑。" **之后, line 155 `---` 之前**插入新段。

### 2.2 新增内容

```
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
```

## Task 3 · SESSION_PROGRESS.md 过时语清理 (Step 14 后补充发现)

Step 14 执行时 CC 主动发现 `docs/SESSION_PROGRESS.md` 还有两处与 A0 已宣绿事实不一致的过时语句, 未并入 Step 14 scope (Step 14 只管 A0 表格行 + "Admin Track 当前唯一关注"段), 本 Step 顺手一并清理, 免得再发 Step 14.1。

### 3.1 "当前关键路径"流程图 (约 line 103-125)

定位 `docs/SESSION_PROGRESS.md` "当前关键路径"段, 现有流程图仍写 `Session A0 Phase Gate 9 项 (Frank 亲跑)` 为当前卡点 + FAIL/PASS 双路分支, 整段替换为反映 A0 已宣绿 + 阻塞转 App Track 的新版:

~~~
## 当前关键路径 (2026-04-21 A0 宣绿后)

```
[Admin Track A0 已宣绿, 后续 Admin Session 阻塞 App Session 0-3 完成]
     │
     ▼
┌─────────────────────────────┐
│  当前可推进 (App Track)     │
├─────────────────────────────┤
│  Session 1.2 · Adapter      │ (真实 Playwright + golden HAR, 加固 Session 1)
│  Session 2 · Pipeline       │ (核心 Planner, 推荐优先)
└─────────────────────────────┘
              │
              ▼ (App Session 0-3 全绿后)
      Admin Session A1 解锁
```

**建议**: 直推 **App Session 2** (Pipeline Planner), Session 1.2 可在 Session 3 之前的空档补。
~~~

(注: 上面代码块在 markdown 源文件里用标准三反引号, 本 Prompt 用 `~~~` 只是为了嵌套展示。CC 实施时外层用三反引号即可。)

### 3.2 CLAUDE.md 决策对照表 #24 行备注 (约 line 136)

定位 `docs/SESSION_PROGRESS.md` "CLAUDE.md 决策号与 Session 对照"表, #24 行现有备注约为:

```
| #24 | Session A0 | Admin 认证脚手架 (本文档编写时 Step 11.5 已完成, Phase Gate 未跑) | 2026-04-21 |
```

替换为:

```
| #24 | Session A0 | Admin 认证脚手架 (A/B/C1.1-C1.3/C2/C3/C4/D/E/F/G 七段齐备, Phase Gate 9/9 PASS, 2026-04-21 宣绿) | 2026-04-21 |
```

## Task 4 · 反查一致性 (§0 规则 7)

Task 1 + Task 2 + Task 3 全执行完后跑:

```bash
# 验收 1: A1 inline schema 不再含 totp_secret 字段名 (phantom 删干净)
grep -n 'totp_secret' docs/ADMIN_CLAUDE_CODE_SESSIONS.md
# 期望: 0 命中 (A1 内 phantom 彻底清除)

# 验收 2: A1 inline schema 改为引用式 (按 §0 规则 1)
grep -n 'force_password_change_at\|lastPasswordAt\|CLAUDE.md #24' docs/ADMIN_CLAUDE_CODE_SESSIONS.md | head -10
# 期望: A1 §2 段至少命中 1 条 (引用 C1.3 或新 3 字段)

# 验收 3: §0 新增规则 8
grep -cn '### 规则 8:' docs/ADMIN_CLAUDE_CODE_SESSIONS.md
# 期望 = 1

# 验收 4: REVOKE 占位符已标记
grep -n 'app_role_placeholder' docs/ADMIN_CLAUDE_CODE_SESSIONS.md
# 期望 ≥1 (Task 1.2 新加 placeholder, A1 开工前由 Frank 确认)

# 验收 5: §0 依然 8 条 (不 7 不 9)
grep -cE '^### 规则 [1-9]:' docs/ADMIN_CLAUDE_CODE_SESSIONS.md
# 期望 = 8

# 验收 6: SESSION_PROGRESS.md "当前关键路径" 已反映 A0 宣绿
grep -n '2026-04-21 A0 宣绿后\|A0 已宣绿' docs/SESSION_PROGRESS.md
# 期望 ≥1

# 验收 7: SESSION_PROGRESS.md #24 行备注已更新
grep -n 'Phase Gate 9/9 PASS, 2026-04-21 宣绿' docs/SESSION_PROGRESS.md
# 期望 ≥1 (同时"Phase Gate 未跑"旧语必须清零, 见 8)

# 验收 8: SESSION_PROGRESS.md 旧"Phase Gate 未跑"/"Frank 亲跑"语清零
grep -nE 'Phase Gate 未跑|Frank 亲跑' docs/SESSION_PROGRESS.md
# 期望 = 0
```

所有 8 条都必须达到期望值, 否则不 done。

## 不动区

- CLAUDE.md · 本 Step **零改动** (Step 11.6 的 #24 C1.1/C1.2/C1.3 + C2 + A 段已到位)
- `docs/ADMIN_PRD.md` · 本 Step **零改动** (Step 11.6 的 §5.6.8 已到位)
- 任何 `.prisma` / `.ts` / `.tsx` / `.sql` 文件 · 本 Step **零改动**
- `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` Session A0 段 · 零改动 (只改 §0 + A1)
- `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` A2/A2.1-A2.4/A3/A3.1-A3.3/A4/A5 段 · 零改动 (未开工 Session 的字段 drift 先不扩到这里, 等各自前置 Session 开工前单独跑"反向同步审计"走规则 8)
- `docs/SESSION_A0_STEP_11_5.md` + `docs/SESSION_A0_STEP_11_6.md` + `docs/SESSION_A0_STEP_14.md` (若存在) · 零改动 (历史档案)
- `docs/SESSION_PROGRESS.md` · **只改 line 103-125 "当前关键路径"段 + line 136 决策表 #24 行备注** (Task 3.1 / 3.2), 其余段 (A0 表格行 / Admin Track 当前状态段 · Step 14 已完成) 一律零改动

## 完成后报告格式

```
# Step 13 完成报告

## Task 1 · A1 §2 inline schema 反向同步
- 原 line 449-459 段删除并重写, 新段行号范围: X-Y (新增/减少 N 行)
- 删除字段: totp_secret? (A0 未落, PRD §5.6.8 无)
- 引用补充: A0 已落 3 字段 (force_password_change_at / last_password_at / last_login_at)
- REVOKE placeholder: <app_role_placeholder> (标记 TODO 待 A1 开工前确认)

## Task 2 · §0 新增规则 8
- 插入位置: line X (原 line 153 "不一致 → 不能 merge" 之后)
- 规则标题: 规则 8: Cross-Session Boundary 反向同步
- 核心条款: 4 条 (完工反向 grep / phantom 拦截 / 日期锚点 / 跨仓扩展)
- 反例 2 条 (Step 11.5 / A1 line 452)

## Task 3 · SESSION_PROGRESS.md 过时语清理
- 3.1 "当前关键路径"流程图整段替换 (行号 X-Y, Δ ±N 行)
- 3.2 决策对照表 #24 行备注更新 (行号 Z)

## Task 4 · 反查 grep (8 条)
- 验收 1 (totp_secret 清零): X (期望 0)
- 验收 2 (引用式补充): X (期望 ≥1)
- 验收 3 (规则 8 存在): X (期望 1)
- 验收 4 (REVOKE placeholder): X (期望 ≥1)
- 验收 5 (§0 共 8 条): X (期望 8)
- 验收 6 (SESSION_PROGRESS 当前关键路径已更新): X (期望 ≥1)
- 验收 7 (SESSION_PROGRESS #24 备注已更新): X (期望 ≥1)
- 验收 8 (SESSION_PROGRESS 旧"Phase Gate 未跑"清零): X (期望 0)

## 文件尺寸
- docs/ADMIN_CLAUDE_CODE_SESSIONS.md: X bytes, Y lines (Δ vs Step 11.6 end)

## 下游 Session 同步清单 (规则 8 自执行)
grep A0 产出字段 (force_password_change_at / last_password_at / last_login_at) 在 SESSIONS/PRD/CLAUDE.md 的引用:
- A0 段: X 处 (预期)
- A1 段: Y 处 (本 Step 修复后应 ≥1 引用式)
- A2-A5 段: Z 处 (若 > 0, 报告给 Frank 决定是否本 Step 一并同步)
- ADMIN_PRD.md: W 处
- CLAUDE.md: V 处
```

## 异常处理

- Task 1 改写后 markdown 代码块嵌套异常 (外层 ``` 与内层冲突) → 用 4 空格缩进代替内层 ```, 或用 `~~~` 三波浪号替代。报告给 Frank 看最终渲染是否正常。
- Task 3 验收 3 "§0 共 8 条" 如果 grep 命中 9 条以上, 说明文档已存在规则 8 残留 — 停, 报告给 Frank 看是否重复插入。
- Task 3 验收 4 若"app_role_placeholder" grep 0 命中, 说明 Task 1.2 的 REVOKE 段没落地 — 补写后重跑。
- A2-A5 段 grep 命中 force_password_change_at 等字段 (验收报告里 Z > 0) → 停, 报告, 不得自行扩展改动范围 (A2-A5 的 phantom 反向同步留给各自前置 Session 开工前单独处理, 保持 Step 13 边界干净)。
