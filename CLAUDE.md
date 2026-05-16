# CLAUDE.md

This repository's rules for ALL agents live in [AGENTS.md](./AGENTS.md). Claude Code: read AGENTS.md as your primary contract; do not infer from this file alone.

Why: AGENTS.md is the canonical, agent-agnostic source. Duplicating rules here would let CLAUDE.md drift out of sync with the GitHub CI lints (`.github/workflows/pr-body-lint.yml`) that actually gate merges. The CI is the enforcement layer; AGENTS.md describes what that CI requires.
