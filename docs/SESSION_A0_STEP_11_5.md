# Session A0 · Step 11.5 Prompt (To CC)

> 背景: Step 11 的 C 段登记不完整 + ADMIN_PRD §5.6.8 缺少反向同步, 本 Step 一次性补齐。
> 发起时间: 2026-04-21
> 触发来源: Frank 在 PowerShell 深度反查中发现 C1 只写了 1 项偏差 (应有 4 项), 且 `failed_login_count` / `locked_until` 在 ADMIN_PRD 中 0 匹配。

---

# Step 11.5 · CLAUDE.md #24 C 段补全 + ADMIN_PRD §5.6.8 反向同步

## 背景

Step 11 的 C 段只登记了 1 项偏差 (SQL 原生类型 → Prisma DSL 映射), 实际 Session A0 落地过程中偏离原始 Prompt / ADMIN_PRD §5.6.8 的地方至少有 4 处, 且新扩字段 (`failedLoginCount` / `lockedUntil`) 没有反向同步回 ADMIN_PRD §5.6.8 admin_users 真相源 — 违反 `docs/ADMIN_CLAUDE_CODE_SESSIONS.md` §0 规则 4 (双向同步) 与规则 7 (完工一致性检查)。本 Step 把 C1 一条拆成 C1.1 / C1.2 / C1.3 / C1.4 四条, 并反向 patch ADMIN_PRD §5.6.8。

## 任务 1 · 重写 CLAUDE.md #24 C 段

定位 `CLAUDE.md` 决策 #24 的 C 段起始行 (标题: `**C. 与 ADMIN_PRD §5.6 schema 的偏差 (C1/C2, 必须记录, 未来 migration 须参考)**`), 整段用下面的内容替换 (C1 从 1 条变 4 条, C2 保留语义只做复制对齐):

```
**C. 与 ADMIN_PRD §5.6 schema 的偏差 (C1/C2, 必须记录, 未来 migration 须参考)**

**C1.1 (字段类型偏差 · Prisma DSL 限制)**: ADMIN_PRD §5.6.8 写 uuid / varchar / text 等 SQL 原生类型, Prisma schema 落地时统一变 String @id @default(uuid()) / String / String. 理由: Prisma DSL 不支持 SQL 原生 uuid/varchar 关键字, 运行时仍落 PostgreSQL uuid 列 (@db.Uuid 精修留给 Session A1 migration 合并扫).

**C1.2 (字段命名 + 类型双偏差 · Q2 对齐结果)**: 原始 Prompt §3 指定 `mustChangePasswd Boolean`, 实施落地为 `forcePasswordChangeAt DateTime?`. 理由: Boolean 只能表达"必须改"的静态状态, DateTime? 可同时表达"何时设为必须改"+"null=未触发"二义, 更适配 super_admin bootstrap 首登强制改密 + ops_admin 被管理员手动 reset 两种触发路径. Q2 alignment 已确认此偏差. ADMIN_PRD §5.6.8 admin_users 需同步改此字段语义 (见任务 2).

**C1.3 (实施路径偏差 · 就地扩写)**: Session 0-rev 已先行落地 AdminUser 基础模型 (id/email/passwordHash/role/status 等), Session A0 采取"就地扩写" 5 个新字段 (`forcePasswordChangeAt` / `lastPasswordAt` / `lastLoginAt` / `failedLoginCount` / `lockedUntil`) 而非新建模型. 理由: 避免 schema 分裂 + migration 冲突, 与 Session 0-rev 产物自然合流.

**C1.4 (Rate Limiter 持久化偏差 · 原 Prompt §5 → DB 持久化)**: 原始 Prompt §5 指定 rate limiter 用 "in-memory Map + TTL", 实施落地改为 DB 持久化 (新增 `failedLoginCount Int @default(0)` + `lockedUntil DateTime?` 两字段). 理由: Next.js serverless 冷启动会清空内存, Map+TTL 方案等于给了攻击者"等冷启动即可重置计数"的侧信道; DB 持久化确保跨实例 + 跨冷启动一致性. 15 min 自动解锁逻辑改为 `lockedUntil < now()` 比较而非 TTL 计时器. ADMIN_PRD §5.6.8 admin_users 需同步加此二字段 (见任务 2).

**C2 (super_admin 单值 · MVP 范围界定)**: ADMIN_PRD §5.6.1 列了 3 角色 (super_admin / ops_admin / viewer), Session A0 落地只开 super_admin 单值 CHECK, ops_admin / viewer 推到 Session A1. 理由: A0 只做 auth 地基, 多角色权限矩阵与审计面板一起落在 A1 更内聚.
```

## 任务 2 · 反向同步 ADMIN_PRD §5.6.8 admin_users

### 2.1 表格字段追加

定位 `docs/ADMIN_PRD.md` §5.6.8 admin_users 表格行 (当前结尾 `..., created_at, updated_at |`), 把 `updated_at` 前插入 5 个字段, 替换后整行如下:

```
..., force_password_change_at (timestamp, nullable, null=正常 / 非null=首登强制改密), last_password_at (timestamp), last_login_at (timestamp, nullable), failed_login_count (int, default 0, rate limiter 连续失败计数器), locked_until (timestamp, nullable, null=未锁定 / > now()=锁定中, 15min 后自动解锁), created_at, updated_at |
```

注意: `force_password_change_at` / `last_password_at` / `last_login_at` 如果 §5.6.8 原表已存在, 不要重复写; `failed_login_count` 和 `locked_until` 必须追加。

### 2.2 语义补注

在 §5.6.8 admin_users 表格下方追加一段:

```
**语义补注 (Session A0, 2026-04-21)**:
- `force_password_change_at`: DateTime? 替代原 PRD 可能的 `must_change_passwd Boolean` 写法. null=正常登录, 非 null=首登或被 reset 后必须改密才能进 Admin. Session A0 bootstrap 脚本 seed super_admin 时会写入当前时间触发首登改密.
- `failed_login_count` + `locked_until`: Rate limiter DB 持久化实现 (替代 in-memory Map+TTL, 避免 Next.js serverless 冷启动导致的计数器重置侧信道). 5 次连续失败 → locked_until = now() + 15min, 下次登录尝试若 `locked_until > now()` 直接拒绝并返回 "账户已锁定, 请 15 分钟后重试".
```

### 2.3 Footnote

§5.6.8 章节末尾追加:

```
> 2026-04-21 · Session A0 落地扩 5 字段 (force_password_change_at / last_password_at / last_login_at / failed_login_count / locked_until), 与 CLAUDE.md #24 C1.2 / C1.4 偏差记录双向同步.
```

## 任务 3 · 反查一致性 grep (§0 规则 7 自检)

执行完任务 1 + 任务 2 后, 在 `GENPANO/` 根目录跑:

```bash
# 验收 1: CLAUDE.md C1 四分支都落位 (期望 = 4)
grep -n 'C1\.[1-4]' CLAUDE.md | wc -l

# 验收 2: ADMIN_PRD 新字段同步到位 (期望 ≥ 3)
grep -nE 'failed_login_count|locked_until' docs/ADMIN_PRD.md | wc -l
```

两条都达标才能报 Step 11.5 done。

## 不动区

- CLAUDE.md #24 的 A / B / D / E / F 段不动
- CLAUDE.md #25 不动
- C2 段语义不动 (只重排在 C1.1/1.2/1.3/1.4 之后)
- `backend/.env.example` 不动 (Step 11 已完成)
- Prisma schema / 代码 / middleware / 任何 .ts / .tsx 文件全部不动 — 本 Step 只改 CLAUDE.md 和 docs/ADMIN_PRD.md 两个文件

## 完成后请报告

1. `CLAUDE.md` #24 C 段新增行号范围
2. `docs/ADMIN_PRD.md` §5.6.8 admin_users 表格行号改动 + 语义补注 + footnote 的插入行号
3. 两条 grep 验收的输出 (`wc -l` 数字)
4. 两个文件当前的 byte size 和 line count
