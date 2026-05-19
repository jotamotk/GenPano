# INCIDENTS — Rules 的起源故事

每条规则只链此处对应 anchor。规则正文不带 PR 编号。按时间倒序。

---

## <a id="1283"></a>#1283 (2026-05) — PANO live gate stabilization

PANO live test-environment 的 acceptance gate 反复失败。问题点：观测窗口未覆盖完整 recovery loop，
status 被过早判定。

**触发规则**：[rules/testing/acceptance-evidence.md](testing/acceptance-evidence.md) 的
"Live mutation gate 的轮询窗口" 节。

---

## <a id="1167"></a>#1167 (2026-05) — Admin Surface PANO gate

Admin surface 的 live 验证 gate。

**触发规则**：[rules/frontend/admin-surface.md](frontend/admin-surface.md)、
[rules/testing/acceptance-evidence.md](testing/acceptance-evidence.md)。

---

## <a id="1067"></a>#1067 — CI Enforcement (pr-body-lint)

PR body lint 上线为 Layer 1 hard gate。三段必填字段定型：`## Linked Work` / `## Root Cause Gate` /
`## Verification Evidence Ledger`。

**触发规则**：[rules/security/enforcement.md](security/enforcement.md)。

---

## <a id="948-960"></a>#948 → #953 → #960 — Evidence-First Shipping 起源

契约变化的跨边界验证缺失。原 #953 改 backend 让 `formula_status: partial` 发出 trustworthy 值，
未验证 frontend gate `canUseContractMetricValue` 是否接受新值。backend + frontend 测试套件
都过了，bug 仅在用户手追 live API response 到 consumer 函数时浮现。

**关键结论**：Symmetric failure to Evidence-First Debugging —— "tests green" 不足，当 contract
value set 改变时。

**触发规则**：[rules/testing/evidence-first-shipping.md](testing/evidence-first-shipping.md)。

---

## <a id="905"></a>#905 → #913 → #934 → #935 → #942 → #943 — Evidence-First Debugging 起源

5 轮 PR 才落实际根因。前 4 轮基于代码路径假设（"Admin Tracker 用 `list_queries` SQL"、
"formatter 是 bug surface"、"`profile_id IS NULL` 是阻塞 gate"），从未对照 broken endpoint
的真实响应验证。PR #943（真正 fix）只花 30 秒读 SQL，是 `grep "format_attempt_analysis_fields"`
揭示该 surface 由 `fetch_response_analyzer_status` 服务的——不同 SQL，stripped-down `SELECT`。

**关键结论**：诊断标签（如 `_profile_state="query_profile_id_null"`）不是 code gate；相关性不是因果。
验证实际控制流。

**触发规则**：[rules/testing/evidence-first-debug.md](testing/evidence-first-debug.md)、
[rules/global/orchestrator-discipline.md](global/orchestrator-discipline.md)。

---

## <a id="admin-surface-2026-05-02"></a>2026-05-02 — Admin Surface Rule decision

记录决策：

- 产品 surface 叫 **Admin**。不要引入第二个产品（如 "Query Tool Admin"）
- 橙色 `/admin` operator console 是唯一 Admin UI
- 禁止 `frontend/src/admin/**` / `frontend/src/pages/admin/**` / `frontend-admin/**` /
  Next.js `app/admin/**` 等第二 Admin frontend
- legacy Flask `admin_console/` 包被移除

**触发规则**：[rules/frontend/admin-surface.md](frontend/admin-surface.md)、
[rules/backend/admin-boundary.md](backend/admin-boundary.md)。
