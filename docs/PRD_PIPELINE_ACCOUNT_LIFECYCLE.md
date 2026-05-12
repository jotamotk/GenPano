# PRD: Pipeline Account Lifecycle and SMS Registration

Source issues: Refs #596, #611, #612

This PRD locks the shared account lifecycle contract for LLM execution. It is a
coordination document for worker issues #613 through #621. It does not authorize
business-code changes by the AI Lead.

## Requirement IDs

### PRD-PIPE-ACCT-001 Shared SMS Provider Architecture

All SMS registration and SMS re-login work for LLM accounts must use the shared
provider, registration lock, account pool, and `auto_login` handler architecture.
ChatGPT must plug into the same boundary used by the existing Doubao and
DeepSeek SMS handlers. It must not introduce a ChatGPT-only registration task,
ChatGPT-only account table, or parallel provider stack.

Acceptance:
- Providers expose a shared interface for number discovery, guarded purchase,
  SMS polling, release, cost metadata, and redacted diagnostics.
- Login handlers remain per-engine only for browser and page-flow behavior.
- Shared orchestration owns locks, account-pool state transitions, cookie
  write-back, retry limits, and registration logs.
- Existing Doubao and DeepSeek auto-registration behavior is preserved and is
  covered by regression tests before ChatGPT SMS handler acceptance.

### PRD-PIPE-ACCT-002 Expired Account State

Expired login material is a first-class account state across all LLMs. It is
distinct from cooldown and banned.

Acceptance:
- `cookies_expired`, token invalidation, session-expired UI copy, and redirects
  to login/sign-in while cookies were injected must mark the account `expired`.
- `expired` means the account can be recovered by the shared re-login path; it
  is not a rate-limit cooldown and is not a ban.
- The scheduler must rotate away from expired accounts and avoid treating the
  attempt as a successful model-quality failure.
- Admin/API surfaces must accept, persist, filter, and display `expired` without
  forcing it into `cooldown`, `banned`, or `active`.
- Recovery attempts must record the previous state, new state, reason code,
  engine, account identifier, and redacted evidence.

### PRD-PIPE-ACCT-003 HeroSMS Guarded Provider

HeroSMS support is allowed only as a guarded provider behind the shared SMS
provider boundary. Discovery is read-only until a purchase guard proves all
constraints.

Acceptance:
- HeroSMS ChatGPT/OpenAI number discovery must use United States inventory only.
- Purchase code must require a physical number, ChatGPT/OpenAI service match,
  and unit price less than or equal to USD 0.60.
- There is no fallback to non-physical numbers, higher-price numbers, other
  countries, or unrelated HeroSMS services.
- If no compliant offer exists, the flow must block with diagnostics and must
  not buy a number.
- `HERO_SMS_API_KEY` is available only through GitHub Actions secrets or runtime
  secret injection. It must not be written to repository files, logs, audit
  records, screenshots, PR text, issue comments, or test output.

### PRD-PIPE-ACCT-004 False-Success Safety

Registration and re-login may only report success after a real authenticated
session is verified and cookies/session data are written through the shared
account lifecycle path.

Acceptance:
- CAPTCHA, risk-device, risk-score, SMS timeout, provider exhaustion, manual
  challenge, and unknown page states must surface explicit non-success states.
- Required challenge states include `requires_manual_challenge` or a more
  specific reason. They must never be stored as successful registration or
  successful re-login.
- ChatGPT shell pages, login pages, session-expired pages, risk pages, and
  CAPTCHA pages must not be saved as model responses.
- Regression coverage must prove Doubao and DeepSeek still reject false success
  after shared-provider refactors.

### PRD-PIPE-ACCT-005 Keep-Alive, Observability, and Redaction

Cookie keep-alive is part of the shared account lifecycle. Observability must
explain account recovery without exposing secrets.

Acceptance:
- Keep-alive runs across supported LLMs through the shared lifecycle path, with
  engine-specific probes allowed only inside handlers.
- Keep-alive must mark `expired` when a probe sees token invalidation,
  session-expired UI, login redirects, or equivalent engine-specific signals.
- Observability must include engine, account id or masked account reference,
  previous state, new state, reason code, provider name, price bucket, run id,
  and timestamps.
- Raw cookies, localStorage tokens, SMS text, full phone numbers, activation
  secrets, and provider API keys must be redacted from logs, audit records,
  screenshots, PR output, and GitHub issue comments.
- Phone numbers may be stored or displayed only in masked form unless an
  existing lower-level secret store explicitly requires encrypted raw value.

## Acceptance Mapping

| Issue | Owner Agent | Required PRD IDs | Acceptance focus |
| --- | --- | --- | --- |
| #613 | pipeline-data-agent | PRD-PIPE-ACCT-001, PRD-PIPE-ACCT-004, PRD-PIPE-ACCT-005 | Refactor provider boundary without changing Doubao/DeepSeek behavior; keep shared locks, logs, and redaction. |
| #614 | release-ci-agent | PRD-PIPE-ACCT-003, PRD-PIPE-ACCT-005 | Read-only HeroSMS discovery; no purchase; prove US physical ChatGPT/OpenAI offer and price guard evidence without leaking `HERO_SMS_API_KEY`. |
| #615 | pipeline-data-agent | PRD-PIPE-ACCT-002, PRD-PIPE-ACCT-005 | Mark expired cookies/token/session/login-redirect signals as `expired` across all LLMs with observable redacted transitions. |
| #616 | pipeline-data-agent | PRD-PIPE-ACCT-001, PRD-PIPE-ACCT-003, PRD-PIPE-ACCT-004, PRD-PIPE-ACCT-005 | Add HeroSMS provider behind shared boundary with cost, physical-number, no-fallback, false-success, and redaction guards. |
| #617 | pipeline-data-agent | PRD-PIPE-ACCT-001, PRD-PIPE-ACCT-002, PRD-PIPE-ACCT-003, PRD-PIPE-ACCT-004 | Add ChatGPT SMS handler on shared `auto_login`; handle expired recovery and manual challenge states without fake success. |
| #618 | pipeline-data-agent | PRD-PIPE-ACCT-002, PRD-PIPE-ACCT-005 | Harden cookie keep-alive across supported LLMs and ensure expired detection is shared and observable. |
| #619 | backend-api-agent | PRD-PIPE-ACCT-002, PRD-PIPE-ACCT-005 | Admin Accounts API accepts and exposes `expired` without leaking cookies, SMS, phone, or provider secrets. |
| #620 | review-agent | PRD-PIPE-ACCT-001, PRD-PIPE-ACCT-002, PRD-PIPE-ACCT-003, PRD-PIPE-ACCT-004, PRD-PIPE-ACCT-005 | Review architecture, cost guard, state transitions, false-success safety, and redaction across worker PRs. |
| #621 | qa-e2e-agent | PRD-PIPE-ACCT-001, PRD-PIPE-ACCT-002, PRD-PIPE-ACCT-003, PRD-PIPE-ACCT-004, PRD-PIPE-ACCT-005 | Live verify ChatGPT recovery plus Doubao/DeepSeek auto-registration regression coverage after deploy. |

## Current Implementation Snapshot

Observed on 2026-05-12:
- `geo_tracker/agent/sms_login/__init__.py` has a handler registry for Doubao
  and DeepSeek.
- `geo_tracker/agent/sms_login/base.py` centralizes SMS login orchestration,
  LubanSMS access, CAPTCHA handling, phone release, and cookie export.
- `geo_tracker/tasks/celery_tasks.py` has an `auto_login` task and current
  account recovery flow.
- `geo_tracker/pool/account_pool.py` currently treats `cookies_expired` as
  cooldown. Worker issue #615 owns the implementation change to the new
  `expired` state.
- `backend/app/api/admin/accounts/router.py` currently documents account status
  updates around active, banned, and cooldown. Worker issue #619 owns the Admin
  API change for `expired`.

No business-code behavior is changed by this PRD.
