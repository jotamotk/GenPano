# ADR-006: MCP 鉴权 Bearer API Key（不上 OAuth）

**Status**: Accepted
**Date**: 2026-05-04

**Context**:
PRD §4.5.2 + §4.5.2.1 要求 MCP Server 走单一鉴权链路。可选方案：① Bearer API key（用户在 settings 自助生成 / 撤销）；② OAuth 2.0（client_id + scope + redirect 授权流）；③ 兼有（API key 给 Agent，OAuth 给第三方应用）。

**Decision**:
Phase M 仅实现 Bearer API key：用户 `/settings/api-keys` 生成 `gp_sk_<32 字符>` token，存 bcrypt hash + 前缀明文（供识别）。MCP 端点 `/mcp/v1` 强制 Bearer header；未带 / 失效返 `401 + code=MCP_AUTH_REQUIRED`（PRD §687 契约）。Scope 模型用 JSONB（`{tools: [...], resources: [...], projects: [...]}`），`*` 表全开。Rate limit 60 req/min/key（默认），超限 429 + `Retry-After`。

**Consequences**:
- ✅ 实现成本低（M1 仅 0.3 周）。
- ✅ Agent 用户体验好：复制 token 即用，无浏览器跳转。
- ✅ 与 OpenAI / Anthropic / Google 主流 SDK 自然兼容（普遍支持 Bearer token header）。
- ⚠️ 不支持第三方应用代用户调（OAuth 场景）。当前用户群以"自己调自己 Agent"为主，Phase 2 必要时可加。
- ⚠️ token 一旦泄露立即可越权，撤销机制（`revoked_at`）必须可靠；FE 显示"仅一次"机制 + `last_used_at` 监控。

**Alternatives**:
- **OAuth 2.0**：标准、scope 灵活，但实现成本 1 周以上、用户接入复杂，PRD §659 已要求"Day 1 单一鉴权链路"。Phase 2 评估。
- **mTLS / 短期 JWT**：Agent 接入门槛高，否决。
