# Codex Account Handoff

Codex account switching does not guarantee that the new account inherits the
current chat thread, active agent state, compressed context, local app session,
or in-memory reasoning history.

For Genpano, durable collaboration state must live in the repository and in
GitHub:

- `AGENTS.md`
- `docs/AI_LEAD_WORKFLOW.md`
- `docs/AI_LEAD_CLAUDE_COLLABORATION.md`
- PRD documents and stable PRD requirement IDs
- GitHub Epic issues and Agent task issues
- pull requests, review comments, and CI/CD runs
- deployment logs, server diagnostics, and live Playwright evidence

Chat is useful for clarification, but it is not the source of truth.

## Before Switching Accounts

The current agent must leave a handoff note in the relevant GitHub issue, PR, or
repo document. The note must include:

- current user goal
- current branch and base branch
- linked Epic issue, Agent task issue, and PR
- owner Agent role
- files changed or expected to change
- allowed scope and forbidden scope
- current verification state
- CI/CD run links or blocker summary
- production URL or route being verified
- exact next action
- unresolved questions or risks

If the work is production-facing or user-visible, include the live verification
target: `http://116.62.36.173/`.

## After Switching Accounts

The new agent must not rely on missing chat history. It must rebuild context from
durable state:

1. Read `AGENTS.md`.
2. Read `docs/AI_LEAD_WORKFLOW.md`.
3. Read `docs/AI_LEAD_CLAUDE_COLLABORATION.md` when another coding agent is
   involved.
4. Read the linked PRD requirement IDs.
5. Read the Epic issue, Agent task issue, PR, review comments, and latest CI/CD
   run.
6. Inspect the current branch and worktree status before editing.
7. If production behavior is uncertain, use GitHub Actions, deployment logs,
   server diagnostics, or live checks instead of guessing.
8. After deployed functionality is merged, verify online behavior with
   Playwright E2E against `http://116.62.36.173/`.

## Handoff Template

```md
## Account Handoff

- User goal:
- Current role:
- Current branch:
- Base branch:
- Epic issue:
- Agent task issue:
- PR:
- PRD source:
- Allowed scope:
- Forbidden scope:
- Changed files:
- Verification completed:
- Verification not completed:
- CI/CD or deploy state:
- Live URL or route:
- Blockers:
- Risks:
- Exact next action:
```

## Prompt For The Next Agent

```text
You are taking over Genpano work after a Codex account switch. Do not assume any
chat/thread context has carried over.

Workspace: C:\Users\frank.wang\genpano
Production URL: http://116.62.36.173/

First, read these files:
- AGENTS.md
- docs/AI_LEAD_WORKFLOW.md
- docs/AI_LEAD_CLAUDE_COLLABORATION.md
- docs/CODEX_ACCOUNT_HANDOFF.md
- the relevant PRD docs and stable PRD requirement IDs linked from the issue

Then inspect durable GitHub state:
- Epic issue:
- Agent task issue:
- PR:
- latest CI/CD run:
- latest deploy or server diagnostics evidence:
- latest Playwright/live verification evidence:

Rules:
- Treat GitHub issues, PRs, review comments, and CI/CD runs as durable state.
- Chat history is not source of truth.
- Do not guess when production behavior is uncertain; use GitHub Actions,
  deploy logs, server diagnostics, or live checks.
- Before changing Admin UI, verify the actual Admin shell and route boundary.
- Worker Agents do not merge. AI Lead owns merge sequencing.
- After merged production-facing work, verify online with Playwright E2E against
  http://116.62.36.173/.

Start by posting a concise takeover receipt:
- files read
- current branch/status
- linked issue/PR/PRD
- understood scope
- current blocker or next action
```

## Recovery Rule

If issue text, PR text, local code, CI/CD logs, or live product behavior
disagree, stop and route the conflict through the AI Lead workflow. Do not guess.
