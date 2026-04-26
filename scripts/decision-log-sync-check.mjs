#!/usr/bin/env node
// decision-log-sync-check.mjs
//
// Drift guard between CLAUDE.md "## 关键设计决策" body and docs/DECISION_LOG.md index table.
//
// Behavior:
//   1. Grep CLAUDE.md for `^N\. \*\*` (decision body anchors), find max N.
//   2. Count rows in DECISION_LOG.md table (lines matching `^| N |` where N is digits).
//   3. If max(CLAUDE.md) !== rowCount(DECISION_LOG.md), exit 1 with descriptive diff.
//   4. Also flag if any decision number in [1..maxN] is missing from EITHER side.
//
// Exit codes:
//   0 = in sync
//   1 = drift detected (PR block)
//   2 = file missing or unreadable

import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '..');

const CLAUDE_MD = resolve(REPO_ROOT, 'CLAUDE.md');
const DECISION_LOG = resolve(REPO_ROOT, 'docs', 'DECISION_LOG.md');

function fail(msg, code = 1) {
  console.error(`[decision-log-sync-check] FAIL: ${msg}`);
  process.exit(code);
}

function ok(msg) {
  console.log(`[decision-log-sync-check] OK: ${msg}`);
}

if (!existsSync(CLAUDE_MD)) fail(`CLAUDE.md not found at ${CLAUDE_MD}`, 2);
if (!existsSync(DECISION_LOG)) fail(`DECISION_LOG.md not found at ${DECISION_LOG}`, 2);

const claudeText = readFileSync(CLAUDE_MD, 'utf8');
const logText = readFileSync(DECISION_LOG, 'utf8');

// Step 1 — find decision numbers in CLAUDE.md body
// Pattern: line starts with "N. **" where N is one or more digits
const claudeNumbers = new Set();
const claudeRe = /^(\d+)\. \*\*/gm;
let m;
while ((m = claudeRe.exec(claudeText)) !== null) {
  claudeNumbers.add(parseInt(m[1], 10));
}

if (claudeNumbers.size === 0) {
  fail('No decision anchors `^N\\. \\*\\*` found in CLAUDE.md — wrong file?');
}

const maxClaude = Math.max(...claudeNumbers);

// Step 2 — find decision numbers in DECISION_LOG.md index table
// Pattern: line starts with "| N |" where N is digits (the leading row column)
const logNumbers = new Set();
const logRe = /^\|\s*(\d+)\s*\|/gm;
while ((m = logRe.exec(logText)) !== null) {
  logNumbers.add(parseInt(m[1], 10));
}

if (logNumbers.size === 0) {
  fail('No table rows `| N |` found in DECISION_LOG.md — wrong file?');
}

const maxLog = Math.max(...logNumbers);

// Step 3 — compare max
if (maxClaude !== maxLog) {
  fail(
    `max decision number drift: CLAUDE.md = ${maxClaude}, DECISION_LOG.md = ${maxLog}. ` +
    `Either a decision body was added without an index row, or vice versa. Editing rule #1: same PR.`
  );
}

// Step 4 — gap check (every N in [1..max] must appear on both sides)
const missingFromClaude = [];
const missingFromLog = [];
for (let n = 1; n <= maxClaude; n++) {
  if (!claudeNumbers.has(n)) missingFromClaude.push(n);
  if (!logNumbers.has(n)) missingFromLog.push(n);
}

if (missingFromClaude.length > 0 || missingFromLog.length > 0) {
  const parts = [];
  if (missingFromClaude.length > 0) {
    parts.push(`missing from CLAUDE.md body: [${missingFromClaude.join(', ')}]`);
  }
  if (missingFromLog.length > 0) {
    parts.push(`missing from DECISION_LOG.md index: [${missingFromLog.join(', ')}]`);
  }
  fail(`gap detected — ${parts.join(' / ')}. Editing rule #3: numbers are monotonic, never renumber.`);
}

ok(`${maxClaude} decisions, fully in sync between CLAUDE.md body and DECISION_LOG.md index.`);
process.exit(0);
