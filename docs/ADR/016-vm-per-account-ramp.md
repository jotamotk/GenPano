# ADR-016: VM-per-Account 灰度 ramp (Phase 2)

**Status**: Proposed
**Date**: 2026-05-17

**Context**:
Issue #963 (P0 豆包抓取) 经过 15+ 个外围补丁 (ricochet 检测 / QG 代理切换 / 3-strike ban / lock-safe migration / SPA-homepage 恢复) 仍三种失败模式持续: ① `context.add_cookies(31个)` 不报错但 `existing-cookie auth proof failed: doubao_not_logged_in` 出现 82+ 次 (注入式 session 跟真实登录在指纹/JS state 上对不上); ② `domcontentloaded` 后页面标题空白随后 `Target...has been closed`; ③ 高频人机验证 (在 cookie 失败→新账号 SMS 注册路径被触发)。根因是注入式 cookie session 跟真实用户登录会话在指纹/JS state/storage 时序上不一致, 补丁无法修"注入"动作本身。Phase 1 (PR #1119 vm_side runner + PR #1120 BrowserConnector ABC 重构 + PR #1121 RemoteCDPConnector + `llm_accounts.execution_mode/vm_id` schema + select_executor router + `VM_EXECUTOR_ENABLED` flag + PR #1122 Admin UI "新建 VM 账号"入口) 全部 ship 生产, flag-off 蓝绿 24h 验证零回归, 为 Phase 2 灰度做基础。`engine_health_5min` 物化视图 (ADAPTER_CONTRACT.md §10.4) 已就位, 扩展按 `attempts[].execution_mode` 切片即可同窗口对比 baseline (`local_cookie`) vs 灰度组 (`vm_session`)。Issue #963 历史教训另一面: 一步切流量 ≥ 1 account's worth 即等于 R1.4/R1.6 (跨 engine 反检测关联) 核爆, 必须按 account 颗粒灰度。

**Decision**:
执行 6 步灰度 ramp, 颗粒度按 **`vm_session` 账号数**而非 query 百分比 (账号是 `attempts[].execution_mode` 切片的天然 key, 保 correlation tracking; 而 query-% gating 会让同一 account 的 attempts 跨 mode, 失去对比口径)。每步 24h 观察期 + 三门指标 (相对同 engine_id 同窗口 `local_cookie` baseline): **错误率 ≤ baseline × 0.5**, **人机验证率 ≤ baseline × 1.0 (不回归)**, **latency p95 ≤ baseline × 1.5**。每步独立 PR (env 改动 + Admin UI 创建账号操作 readback), 由操作员 GO/NO-GO 决定进退。6 步分布:

| 步 | 目标 (vm_session 账号) | 目标流量份额 | engine 集合 | 观察期 |
|---|---|---|---|---|
| Step 1 | 1 doubao | ~1% doubao 流量 | doubao only | 24h |
| Step 2 | 3 doubao | ~3-5% doubao | doubao only | 24h |
| Step 3 | 5 doubao | ~10-15% doubao | doubao only | 24h (R1.6 单 engine 自洽验证) |
| Step 4 | 5 doubao + 5 deepseek-CN | ~10-15% doubao + ~100% deepseek 渐起 | doubao + deepseek-CN | 24h (R1.6 跨 engine 关联门) |
| Step 5 | 全 doubao 账号 50% + 全 deepseek-CN 账号 50% | ~50% 两 engine | doubao + deepseek-CN | 24h |
| Step 6 | 全 doubao + 全 deepseek-CN 账号 100% vm_session | ~100% 两 engine | doubao + deepseek-CN | 30d 长观察 → Issue #1118 (Phase 3 cleanup) |

ChatGPT 留在 `local_cookie`, 不进本次 ramp (MVP 3 引擎之一, 但 #963 不涉及, Phase 3+ 决策)。**回滚** 任何 NO-GO 通过 `UPDATE llm_accounts SET execution_mode='local_cookie' WHERE id IN (...)` 秒级生效 (router 下一次 select 即走 LocalLaunchConnector); 不需 redeploy, 不需重启进程。

**Consequences**:

- ✅ 每步 blast radius ≤ 1 个 account's worth of queries (vs 一步全切的 N 个 account 同时坏掉)。
- ✅ 三门指标按 `attempts[].execution_mode` 切片同窗口对比, 排除时段/账号热度等混杂因子。
- ✅ 秒级回滚 (DB UPDATE) — 比 redeploy / config push 快 ~100x, 适合 24h 观察期出 NO-GO 时立即止血。
- ⚠️ 成本: 5 VM × ~¥150/月 = ¥750/月; 流量 + 系统盘 ~¥350/月; **Pilot 总成本 ~¥1000-1100/月** (Phase 0 plan 已锁定预算红线 ¥1500/月)。
- ⚠️ 操作员负担: 每步 24h 内必须 (a) 跑 monitoring 查询 / (b) 决定 GO/NO-GO / (c) 必要时回滚 + 在 Epic #1110 评论留 EVIDENCE。每步至少 30 分钟操作员时间。
- ⚠️ 6 步 × 24h = 6 天最短窗口; 实际含 NO-GO 回滚 + 重做 + Step 6 后 30 天长观察, 总历时 6-10 周。
- ⚠️ R1.6 跨 engine 关联风险在 Step 4 暴露 (同 VM 内 doubao + deepseek 双开第一次同台): 若 1 engine 风控触发后另一 engine 也连带, 回滚到 Step 3 + 评估是否拆 1 VM 1 engine (10 VM, 成本翻倍 ¥2000/月)。
- ⚠️ R2.5 同账号双 mode 自爆已由 Phase 1 DB CHECK 阻止 (`CHECK (execution_mode = 'local_cookie' OR cookies_json IS NULL)`), Admin UI 切换 mode 要求先清 cookies。

**Rollback paths (每步独立)**:

- Step N NO-GO → `UPDATE llm_accounts SET execution_mode='local_cookie' WHERE id IN (<本步新增账号>)` → 验证 attempts[].execution_mode 切片中 vm_session 计数停止增长 → 在 Epic #1110 留 EVIDENCE 含 query exit + counts + 触发指标 + 候选 root cause → 决定回到 Step N-1 重做或回到 Step 0 (全 local_cookie) 重新评估。
- 任何步骤的 fleet 级 incident (5 VM > 1 同时挂 / Tailscale 中断 / login_watchdog 集体 dead) → 直接走 Step 0 (全 vm_session 账号回 local_cookie), 然后查 VM fleet 健康, 不算"步骤 NO-GO", 算 "infrastructure incident"。
- Step 4 (跨 engine) NO-GO 且根因是同 VM 双开关联 → 回 Step 3 + 拆 1 VM 1 engine 提案 (10 VM, ¥2000/月) → 重新跑 Step 4-6, 在 ADR 上追加 "ADR-016a Superseded by ADR-016 + 拆 VM 决议"。
- Step 6 100% 后 30 天观察窗口内任何 5xx 异常 / 错误率回归 / DB FK 异常 → 回滚到 Step 5 (50%), Phase 3 cleanup (#1118) 推迟。**不允许在 30 天窗口内删除 `local_cookie` 路径代码** — 这是逃生通道。

**Alternatives**:

- **Query-percentage gating** (e.g. `if hash(query_id) % 100 < N: route vm`) — 否决: ① 同一 `account_id` 的 attempts 跨 mode, 失去 `attempts[].execution_mode` 切片的对比口径 (同 account 的 attempt[0]=local 失败 + attempt[1]=vm 成功就无法判断 "vm 真的更好" 还是 "第二次 attempt 总更好"); ② Router 实现位置错 (router 拿到的是 account 不是 query); ③ pool selection 算法已按 account 颗粒挑, 强加 query-% 在外层等于 double-gating, 状态机更复杂。
- **Service-mesh canary (Istio / Linkerd / Envoy)** — 否决: ① 当前栈是 FastAPI + Celery, 引入 service mesh 是 10x over-engineering; ② 我们要按 `account_id` 路由不是按 URL 路由, mesh 的 weight-based routing 不匹配; ③ 一个 VM_EXECUTOR_ENABLED env flag + `execution_mode` 列就够。
- **One-step big-bang switch (Phase 1 ship 后直接 5 VM 全开 100%)** — 否决: 即 R1.4 (重构回归) + R1.6 (跨 engine 关联) 同时核爆的最坏场景, 没有渐进数据支撑回退到哪一步, 而且 #963 已经反复证明 "未观察就上线" 会复现失败模式 (一步全切 = 一次性把 baseline 撤掉, 失去对比项)。
- **Shadow traffic (vm_session 跟 local_cookie 同 query 跑双份, 写 shadow_responses 表)** — 否决: ① 本 plan 显式 out-of-scope ("VM 写 ai_responses 跟 browser 同等地位, 不走 shadow_responses 中间表"); ② shadow 一倍流量等于 2x 反检测压力, 加速 doubao 风控触发; ③ 引入新表 = 新 ADR + Adapter Harness F4-1/F4-2/F4-3 更新, 推迟整个 epic ≥ 2 周。
- **A/B test (账号随机分配 mode, 不灰度只对比)** — 否决: ① 业务结论已经是 "vm_session 必须替代 local_cookie" (#963 cookie 注入失败硬证据), 不是寻求 "哪个更好" 的探索; ② A/B 长跑等于把生产 50% 流量持续暴露在已知失败的 local_cookie 路径上, 业务损失。
