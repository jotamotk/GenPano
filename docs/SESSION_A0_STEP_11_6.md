# Session A0 · Step 11.6 Prompt (To CC)

> 背景: Step 11.5 把"failedLoginCount + lockedUntil DB 持久化"当成偏差写入 CLAUDE.md #24 C1.3/C1.4 + ADMIN_PRD §5.6.8, 但 Phase Gate 执行前 CC grep 真实代码发现 schema.prisma 只有 3 新字段 (无 failedLoginCount/lockedUntil), rate-limiter.ts 仍用 in-memory Map (原 Prompt §5 方案)。C1.4 记录的偏差不存在。本 Step 回滚虚假偏差 + 修补 Phase Gate S4 (JWT secret lazy check → boot-time fast-fail)。
>
> 发起时间: 2026-04-21
> 决策: 方案 A (回滚文档, 文档 = 代码) + S4 修补 (boot-time assert)

---

# Step 11.6 · 回滚 Step 11.5 虚假偏差 + S4 boot-time fast-fail 修补

## 背景

Step 11.5 把"failedLoginCount + lockedUntil DB 持久化"当成偏差写入 CLAUDE.md #24 C1.3/C1.4 + ADMIN_PRD §5.6.8, 但 Phase Gate 执行前你 grep 真实代码发现:

- `backend/prisma/schema.prisma:661-687` 只有 3 新字段 (`forcePasswordChangeAt` / `lastPasswordAt` / `lastLoginAt`), **无** `failedLoginCount` / `lockedUntil`
- `backend/src/admin/auth/rate-limiter.ts:31-32` 仍用 `new Map<string, Bucket>()`, 即原 Prompt §5 in-memory Map + TTL 方案

**结论**: C1.4 记录的偏差不存在, 代码按原 Prompt 落地是对的; Step 11.5 推入错误前提, 现在回滚文档 (方案 A: 文档 = 代码, DB 持久化推到 Session A1)。

另外 Phase Gate 跑前检查发现 **S4 "JWT secret fast-fail" 是 lazy** (`signAccessToken()` 首次调用才抛 `AdminJwtSecretMissingError`), 不符合 "server must refuse to start if SECRET missing" 的安全意图。本 Step 一并修为 boot-time assert。

## 执行前自检 (§0 规则 2 · Pre-flight Grep)

开工前务必先跑下面一条命令, 把"虚假偏差"在 repo 内扩散的所有位置找出来:

```bash
grep -nE 'failedLoginCount|lockedUntil|failed_login_count|locked_until' \
  CLAUDE.md \
  docs/ADMIN_PRD.md \
  docs/ADMIN_CLAUDE_CODE_SESSIONS.md \
  docs/DATA_MODEL.md \
  docs/CLAUDE_CODE_SESSIONS.md \
  docs/SESSION_PROGRESS.md 2>/dev/null
```

报告所有命中 (行号 + 上下文片段)。如果命中超过 CLAUDE.md + ADMIN_PRD 两个文件的范围, **停下来讨论范围**再动手。`docs/SESSION_A0_STEP_11_5.md` 命中预期, 该文档是 Step 11.5 原始 Prompt 存档, **不**回滚 (作为历史记录保留)。

## Task 1 · 回滚 CLAUDE.md #24 C 段

### 1.1 规则

1. **C1.4 整条删除** (rate limiter DB 持久化偏差 — 不存在)
2. **C1.3 改字段数**: "5 个新字段 (`forcePasswordChangeAt` / `lastPasswordAt` / `lastLoginAt` / `failedLoginCount` / `lockedUntil`)" → "3 个新字段 (`forcePasswordChangeAt` / `lastPasswordAt` / `lastLoginAt`)"
3. **C1.1 / C1.2 / C2 保留不变** (语义未动)

回滚后 C 段顺序: **C1.1 → C1.2 → C1.3 → C2** (共 4 条, 不是 5 条)。C2 行号上移。

### 1.2 附带: CLAUDE.md #24 A 段 也可能含错误字段清单

CLAUDE.md #24 A 段 Step 11 deliverable 部分 (约行 236) 若有"AdminUser 扩 5 字段"或列出 `failedLoginCount` / `lockedUntil` 的地方, 同步改为 3 字段 + 删这两个名字。

**执行**: Read `CLAUDE.md` 行 230-270, 把 A 段 AdminUser 字段列表与 C 段一起更新, 保持全 #24 决策内部一致。

## Task 2 · 回滚 ADMIN_PRD §5.6.8 admin_users

### 2.1 表格行: 删除 2 字段

原 Step 11.5 追加的:

```
..., failed_login_count (int, default 0, rate limiter 连续失败计数器), locked_until (timestamp, nullable, null=未锁定 / > now()=锁定中, 15min 自动解锁), ...
```

**删掉** `failed_login_count` 和 `locked_until` 两个字段; 保留 `force_password_change_at`, `last_password_at`, `last_login_at`, `created_at`, `updated_at`。

### 2.2 语义补注: 删除 "failed_login_count + locked_until" 那段

保留 `force_password_change_at` 的第一段; **删除** `failed_login_count + locked_until: Rate limiter DB 持久化实现 ...` 的第二段。

### 2.3 Footnote 修改

原:
```
> 2026-04-21 · Session A0 落地扩 5 字段 (force_password_change_at / last_password_at / last_login_at / failed_login_count / locked_until), 与 CLAUDE.md #24 C1.2 / C1.4 偏差记录双向同步.
```

改为:
```
> 2026-04-21 · Session A0 落地扩 3 字段 (force_password_change_at / last_password_at / last_login_at), 与 CLAUDE.md #24 C1.2 偏差记录双向同步. (Step 11.5 误报 "DB 持久化 rate limiter" 偏差已在 Step 11.6 回滚; rate limiter 按原 Prompt §5 in-memory Map + TTL 方案落地, 无偏差.)
```

## Task 3 · 修 S4 · JWT Secret boot-time fast-fail

### 3.1 问题诊断

当前 `backend/src/admin/auth/jwt.ts` (或等价模块) 的 secret 检查是 **lazy**: `signAccessToken()` 首次被调用时才 throw `AdminJwtSecretMissingError`。Phase Gate S4 意图是"server 必须在启动时就因 SECRET 缺失拒绝监听端口", 以降低侦察面。

### 3.2 实施

导出一个显式的 `assertAdminJwtSecretPresent()` 函数 (若已存在, 复用; 若仅存在 lazy 内部校验, 抽出来), 并在 auth 模块入口主动调用一次 — 在 Next.js boot / middleware 注册链路上, 确保 SECRET 缺失抛错在 `listen()` 之前发生, 阻止端口绑定。

具体位置由 CC 根据当前代码结构决定 (候选: `backend/src/admin/auth/index.ts` 顶部 module scope / `backend/middleware.ts` edge runtime 初始化 / `backend/src/app/admin/api/**/route.ts` 首个 import 链), 关键是 **boot-time** 触发, 不是 first-request。

### 3.3 单测

在 `backend/tests/unit/admin/auth/jwt.test.ts` (或同级 secret-assert.test.ts) 新增两个 case:

```typescript
describe('assertAdminJwtSecretPresent · boot-time fast-fail', () => {
  const originalSecret = process.env.ADMIN_JWT_SECRET;
  afterEach(() => { process.env.ADMIN_JWT_SECRET = originalSecret; });

  test('throws when ADMIN_JWT_SECRET is unset', () => {
    delete process.env.ADMIN_JWT_SECRET;
    expect(() => assertAdminJwtSecretPresent()).toThrow(AdminJwtSecretMissingError);
  });

  test('throws when ADMIN_JWT_SECRET < 32 bytes', () => {
    process.env.ADMIN_JWT_SECRET = 'short-secret-below-32-bytes';
    expect(() => assertAdminJwtSecretPresent()).toThrow(AdminJwtSecretMissingError);
  });
});
```

### 3.4 手测验证

```bash
cd backend
unset ADMIN_JWT_SECRET
npm run dev 2>&1 | head -20
# 期望: 启动阶段抛 AdminJwtSecretMissingError, 进程立即退出, 不监听 4000 端口
echo "exit code: $?"  # 期望非 0

# 恢复
export ADMIN_JWT_SECRET="<64字符+ 的生产随机串>"
npm run dev &
sleep 3
curl -sI http://localhost:4000/admin/api/v1/auth/login   # 期望 200/405 均可, 证明端口绑定
```

截取两次输出。

## Task 4 · 反查 grep 一致性 (§0 规则 7)

Task 1 + 2 + 3 全执行完后跑:

```bash
# 验收 1: C 段只剩 3 条 (C1.1/C1.2/C1.3, 无 C1.4)
grep -c 'C1\.[1-4]' CLAUDE.md                    # 期望 = 3

# 验收 2: ADMIN_PRD 无虚假字段残留
grep -cE 'failed_login_count|locked_until' docs/ADMIN_PRD.md   # 期望 = 0

# 验收 3: CLAUDE.md 无虚假字段残留 (SESSION_A0_STEP_11_5.md 不查)
grep -nE 'failedLoginCount|lockedUntil' CLAUDE.md              # 期望 0 命中

# 验收 4: S4 修补点存在
grep -n 'assertAdminJwtSecretPresent' backend/src/admin/auth/*.ts   # 期望 ≥2 行 (声明 + 主动调用)

# 验收 5: S4 单测覆盖
grep -c 'assertAdminJwtSecretPresent' backend/tests/unit/admin/auth/*.ts   # 期望 ≥2
```

## Task 5 · Vitest + 启动手测

```bash
cd backend && npm test -- tests/unit/admin/auth
```

期望: 原 63 例 + 新 2 例 = 65 例全 pass。

然后跑 Task 3.4 的启动手测 (unset → 起不来 / set → 起来)。

## 不动区

- `backend/src/admin/auth/rate-limiter.ts` · 保持 in-memory Map 方案 **不动** (原 Prompt §5 方案正确)
- `backend/prisma/schema.prisma` · 3 字段 **不加** 2 字段 (现状不变)
- `backend/.env.example` · 不动 (Step 11 已完成)
- CLAUDE.md 其他决策 #1-#23, #25 · 不动
- `docs/SESSION_A0_STEP_11_5.md` · 作为历史 Prompt 档案保留 (不回滚不删除)
- 其他代码 / 其他文档 · 不动

## 完成后报告格式

```
# Step 11.6 完成报告

## Pre-flight Grep 命中清单
(命中文件列表 + 行号)

## Task 1 · CLAUDE.md #24
- C1.4 删除: 原行号 X, 删除 Y 字符
- C1.3 字段列表: 5 字段 → 3 字段
- A 段 AdminUser 字段列表: 同步修正 (行号 + diff)
- 回滚后 C 段行号范围: X-Y

## Task 2 · ADMIN_PRD §5.6.8
- 2.1 表格行删除 2 字段 (行号 X)
- 2.2 语义补注删除第二段 (行号 Y)
- 2.3 Footnote 重写 (行号 Z)

## Task 3 · S4 修补
- 修改文件: backend/src/admin/auth/xxx.ts (+N 行)
- 主动调用位置: 文件 + 行号
- 单测新增: 文件 + 2 case

## Task 4 · 反查 grep (5 条)
- 验收 1: X (期望 3)
- 验收 2: X (期望 0)
- 验收 3: X (期望 0)
- 验收 4: X (期望 ≥2)
- 验收 5: X (期望 ≥2)

## Task 5 · Vitest + 启动手测
- vitest: X/X passed
- unset 启动: exit code X (期望非 0), 错误信息
- set 启动: 端口 4000 绑定成功

## 文件尺寸
- CLAUDE.md: X bytes, Y lines
- docs/ADMIN_PRD.md: X bytes, Y lines

## A0 宣绿候补评估
剩 Phase Gate 9 项待执行 (Step 12): 是否已就绪?
```

## 任何异常的处理

- Pre-flight grep 命中超出预期范围 → 停, 回报范围让我(Frank) 决定是否扩大回滚
- Task 3 发现已有 boot-time 断言 (非 lazy) → 停, 回报实际代码结构, 可能 S4 只是 Phase Gate 检测方式问题而非代码问题
- 任何 Task 4 验收数字不符 → 停, 回报哪条, 不得强制通过
