# OPERATOR QUICKSTART — VM-per-Account 架构上线 (Refs Epic #1110)

> 一页纸操作员手册, 串起从 PR review 到生产 100% 切换的全流程。详细 step-by-step 指向已有 RUNBOOK / ADR / monitoring queries。

**适用范围**: Epic #1110 (VM-per-Account 架构 for #963 豆包抓取失败修复) 的全生命周期, 从 7 PR review 到 Phase 3 cleanup。

**前提**: 已 review 通过批准本 plan (saved at `/root/.claude/plans/fancy-snuggling-treehouse.md`)。

---

## 总览: 5 个阶段 × 关键 artifact

```
Stage A: Review 7 PR  ──────► Stage B: Merge 5 PR (按依赖链)
                                              │
                                              ▼
Stage C: Deploy test 验证 ──► Stage D: Ramp 6 步 (Epic #1110)
                                              │
                                              ▼
                                Stage E: Cleanup #1124 (30 天后)
```

| Stage | 谁做 | 输入 | 输出 | 阻塞条件 |
|---|---|---|---|---|
| A. PR Review | 用户 (Tech Lead) | 7 个 draft PR | 5 个 approved + 2 个 hold (#1112, #1124) | 任一 P0 issue → revert |
| B. Merge | 用户 | approved PR | main HEAD 含 5 个新功能 (flag-off 死代码) | CI 必须全绿 |
| C. Deploy 验证 | 操作员 | main HEAD deploy 到 test env | 24h 蓝绿 baseline `engine_health_5min` 无差异 | 任一 baseline 退化 → revert main |
| D. Ramp | 操作员 (按 `docs/RUNBOOK_vm_per_account_ramp.md`) | 5 VM 双开 + 10 logged-in profile | 6 步 ramp 1→100%, #963 关闭 | 任一步 3-门 NO-GO → 回退账号 |
| E. Cleanup | 用户 + 操作员 | Step 6 + 30 天观察 | DOUBAO_COOKIES_JSON deprecation 落地 | 30 天窗口未到 → 等 |

---

## Stage A: PR Review (用户, ~2-4 小时)

7 个 draft PR 按依赖 + 风险排序 review。**先 review 高风险的 (#1120 重构), 再 review 累加的**。

| 顺序 | PR | 风险点 | Review 焦点 |
|---|---|---|---|
| 1 | **#1120** (重构) | ⚠️ 中-高: 700+ LOC 搬动, 影响 8 engine | **必做**: `git diff main..origin/claude/vm-arch/phase1-browser-connector-refactor -- geo_tracker/agent/guest_executor.py`, 重点看 `_browser_query` 函数体跟 main 一致 (PR #1107 的 190 行 SPA 恢复代码必须存在, agent 初版 `8ef0c71` 误删过, `4a9c889` 复原)。跑全 8 engine HAR replay fixture 通过。 |
| 2 | **#1121** (集成) | ⚠️ 中: schema migration + flag 默认 off | `VM_EXECUTOR_ENABLED` 默认 `false` (router.py:_flag_enabled hardcoded); `chk_exec_mode_cookies` CHECK 约束防 R2.5 自爆; alembic up+down 在 SQLite 测试通过 (CHECK 是 Postgres-only branch) |
| 3 | **#1119** (vm_side) | 低: 独立 stack | `vm_side/runner.py` 无 `add_cookies()` / `new_context()`; 无 `import geo_tracker`; CI cross-component smoke 跑通 |
| 4 | **#1122** (Admin UI) | 中: 新 UI 路径 + 5 endpoint | `/admin/api/vm/*` 全部 401 unauth; vm_session 账号创建 reject cookies_json (R2.5 三层防御: DB + backend + frontend) |
| 5 | **#1123** (ramp ADR+runbook) | 低: 仅 doc | ADR-016 符合 ADR-001 style; RUNBOOK 6 步 + 每步 rollback; monitoring queries 在 ai_responses schema 上能跑 |
| ⏸ | **#1112** (M1 PoC) | 已被 #1119 superseded | 用户决定 close 或保留 archive |
| ⏸ | **#1124** (cleanup) | 高风险: 真的删代码 | **HOLD 30 天**, 等 ramp 100% 完成 + 30 天观察才能 unblock |

**Review 任一 P0 issue → 在 PR 上 review comment 拒掉 → Leader (我) revert + 重 dispatch agent 修。**

---

## Stage B: Merge 5 PR (用户, ~30 分钟)

**严格按依赖链 merge, 中间留至少 10 分钟让 CI rebase**:

```bash
# 1. 先 merge 独立的 (base=main)
gh pr merge 1119 --squash   # vm_side, 独立
gh pr merge 1120 --squash   # refactor, 独立

# 2. rebase 后续 PR 到新 main (PR 自动触发 rebase, 等 CI 重跑通过)
# (UI 上点 "Update branch" 或等 #1121 author/CI 自动 rebase)
gh pr merge 1121 --squash   # RemoteCDP, 依赖 #1120

gh pr merge 1122 --squash   # Admin UI, 依赖 #1121

gh pr merge 1123 --squash   # ADR + runbook, 独立 (可任何时间)
```

**注意**: `gh` CLI 在 web 容器不可用, 用 GitHub UI 或 `mcp__github__merge_pull_request` 工具。

每个 merge 后 watch Build & Deploy run。如果 deploy 失败 → 立刻 `git revert` 该 commit + push, 等下次 deploy 验证回到 baseline。

---

## Stage C: Deploy + 验证 (操作员, ~24 小时蓝绿)

5 PR merge 后 main HEAD 已经包含所有兼容架构代码, 但 `VM_EXECUTOR_ENABLED=false` 默认 off → 生产行为零变化。

### Pre-flight (P-1 到 P-5)

按 `docs/RUNBOOK_vm_per_account_ramp.md` §0 五项检查, 全部 EVIDENCE-checked 在 Epic #1110 上:

| Check | 命令 | 期望 |
|---|---|---|
| P-1 | `git log origin/main --grep "#1119\|#1120\|#1121\|#1122\|#1123" --oneline` | 5 commits 存在; last deploy SHA = `main` HEAD |
| P-2 | SSH 5 VMs: `systemctl status chrome-doubao chrome-deepseek x11vnc websockify tailscaled` | 全 active(running) × 5 VMs |
| P-3 | noVNC 检查 10 profile (5×doubao + 5×deepseek) 登录态 + `cdp_check.sh <vm> <port>` | 全 10 返回 `loginState:authenticated` |
| P-4 | 生产 env `VM_EXECUTOR_ENABLED` value | `false` 或 unset (router 默认 false) |
| P-5 | `engine_health_5min` 过去 7d baseline 截图 + `engine_id IN ('doubao','deepseek-CN')` 数据 | EVIDENCE 到 Epic #1110 |

### 蓝绿验证 (24h)

`engine_health_5min` 在 deploy 前后对比:
- `success_rate` 跟 baseline 差异 < 1pp ✓
- `p95_latency_ms` 跟 baseline 差异 < 10% ✓
- `error_breakdown` 无新错误码出现 ✓

任一项退化 → revert main HEAD 5 commits, 重启讨论。**Phase 1 兼容架构是死代码 deploy, 如果引入回归就是 #1120 重构 R1.4 风险触发, 必须 root cause + 修后重 deploy。**

---

## Stage D: Ramp 执行 (操作员, 2-4 周分流)

**这是 Epic #1110 真正打开 vm_session 路径的阶段**。所有细节在已有 RUNBOOK, 这里只指引:

- 主 RUNBOOK: `docs/RUNBOOK_vm_per_account_ramp.md` (PR #1123 落地后在 main)
- ADR 决策: `docs/ADR/016-vm-per-account-ramp.md`
- Monitoring queries: `docs/monitoring/vm_per_account_queries.md` (Q-BASELINE-1/2/3, Q-3GATE, Q-R16-SINGLE/CROSS, Q-STEP-*, Q-USER-SYMPTOM-REPLAY)
- 3-门 helper script: `scripts/vm_ramp/delta_check.py --engine doubao --window-hours 24`

### 6 步 ramp 时序 (每步独立, 间隔 24h 观察)

| Step | 动作 | 流量 | GO 门 | NO-GO 回退 |
|---|---|---|---|---|
| 1 | Admin UI 创 1 个 vm_session 豆包账号 | ~1% | 错误率 ≤ baseline×0.5 + 人机不回归 + p95≤baseline×1.5 | UPDATE 该账号 execution_mode='local_cookie', 秒级生效 |
| 2 | 创 2 个 (累计 3) | ~3-5% | 同上 | 退到 Step 1 |
| 3 | 创 2 个 (累计 5) | ~10-15% | 同上 + R1.6 cross-engine 关联检查 | 退到 Step 2 |
| 4 | 加 5 个 vm_session DeepSeek 账号 (DeepSeek 启用) | DS ~10-15% | DS 单独 3-门 + R1.6 跨 engine 不连带 | 把 DS 全标 local |
| 5 | 累计 50% (两 engine 各加账号) | ~50% | 3-门 + R1.6 | 退到 Step 4 |
| 6 | 全部 doubao + DS 账号 → vm_session | 100% | 3-门 + **User-Symptom Replay 184968/184971/184974 真实回放成功** | 退回任一前序 step |

每步独立 PR 在 Epic #1110 上挂 EVIDENCE 评论 (含 SQL readback + 3-门数值 + screenshot)。

**Step 6 GO 后 → Epic #1110 起 30 天观察窗口计时, 期间不准 unblock #1124**。

---

## Stage E: Cleanup (用户 + 操作员, Step 6 GO 后 30 天)

30 天后:

1. **Operator 验收**: 跑 `delta_check.py --engine doubao --window-hours 720` (30 天), 确认 3-门指标全部稳定, 在 Epic #1110 上挂 `EVIDENCE: 30-day clean window READY` 评论
2. **用户**: review PR #1124, 改 ADAPTER_CONTRACT.md 里的 `DEPRECATED-<TODO>` 占位符为实际 merge date (e.g. `DEPRECATED-2026-06-30`), undraft, merge
3. **Operator**: 确认 deploy 后 `grep DOUBAO_COOKIES_JSON` 生产 codebase 无引用; `backend/tests/lint/test_no_doubao_cookies_json.py` CI grep test 仍通过
4. **关闭 Issue #963** (用 `User-Symptom Replay` 184968/184971/184974 真实回放成功证据 + `Business success proven` 标签); 关闭 Epic #1110

---

## 紧急程序: 单 VM 故障 (任何阶段)

- **VM 整机死亡** (network 不通, console 不可访问): `login_watchdog` heartbeat 90s 内未收到 → orchestrator 把该 VM 上所有 vm_session 账号自动暂停; Admin UI 显示红条
- **session 死了** (captcha / 跳登录): `login_watchdog` 检到 → Slack webhook 触发 (含 noVNC URL + [告诉系统解完了] 按钮) → 操作员任意设备 (含手机) 打开 Tailscale, 浏览器进 noVNC, 鼠标/触屏过 captcha → 点 Slack 按钮 → POST `/admin/api/vm/relogin_done` → 该 VM 恢复 ACTIVE
- **同 VM 内 一 engine 触发风控连带另一 engine** (R1.6): 把该 VM 上的 DeepSeek profile 改 execution_mode=local_cookie 或暂停; 评估是否 R1.6 风险普遍 → 触发"1 VM 1 engine"回退 (5 VM → 10 VM, 成本翻倍)
- **生产 #963 错误率显著上升** (vm_session 路径错误率超 baseline): 立刻 `UPDATE llm_accounts SET execution_mode='local_cookie' WHERE execution_mode='vm_session'` (秒级全量回退), Slack 通知 + 在 Epic #1110 留 INCIDENT 评论

---

## 联系 / 升级

- **Architecture / plan questions**: AI Leader (this session, 见 `/root/.claude/plans/fancy-snuggling-treehouse.md`)
- **PR review approval**: Tech Lead (用户)
- **VM provisioning / 阿里云**: DevOps
- **Operator on-call**: SRE rotation
- **不在 SOP 内的决策**: 在 Epic #1110 上发 `HUMAN DECISION NEEDED` 评论 + 等 Tech Lead 回复

---

## 全 7 PR 速查

| Issue | PR | Branch | Status (2026-05-17) |
|---|---|---|---|
| #1111 (M1 PoC) | [#1112](https://github.com/jotamotk/trash_test/pull/1112) | claude/explore-architecture-alternatives-8o42z | draft, superseded by #1119 |
| #1113 (refactor) | [#1120](https://github.com/jotamotk/trash_test/pull/1120) | claude/vm-arch/phase1-browser-connector-refactor | draft, 4/4 CI ✅ |
| #1114 (集成) | [#1121](https://github.com/jotamotk/trash_test/pull/1121) | claude/vm-arch/phase1-remote-cdp-router | draft, 4/4 CI ✅ |
| #1115 (vm_side) | [#1119](https://github.com/jotamotk/trash_test/pull/1119) | claude/vm-arch/phase2-vm-side-runner | draft, 5/5 CI ✅ |
| #1116 (Admin UI) | [#1122](https://github.com/jotamotk/trash_test/pull/1122) | claude/vm-arch/phase2-admin-vm-accounts | draft, 4/4 CI ✅ |
| #1117 (ramp) | [#1123](https://github.com/jotamotk/trash_test/pull/1123) | claude/vm-arch/phase2-ramp-adr-runbook | draft, 4/4 CI ✅ |
| #1118 (cleanup) | [#1124](https://github.com/jotamotk/trash_test/pull/1124) | claude/vm-arch/phase3-cleanup-doubao-cookies | draft, ⚠️ DO NOT MERGE 30 天 |

**Epic 跟踪**: [#1110](https://github.com/jotamotk/trash_test/issues/1110) | **原 incident**: [#963](https://github.com/jotamotk/trash_test/issues/963)
