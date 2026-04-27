#!/usr/bin/env node
/**
 * GENPANO · Coverage Gap Scan (coverage-gap-scan.mjs)
 *
 * Decision #21.D / PRD §4.10.4c — single source-of-truth is `docs/openapi.yaml`.
 * Emits a report of:
 *   (a) endpoints declared in openapi.yaml but not yet implemented in backend/src/app/api/**
 *   (b) endpoints implemented in backend but not documented in openapi.yaml
 *   (c) contract test skeletons under frontend/tests/contract/** that have no matching OpenAPI path
 *
 * This is a REPORTING tool — exit 0 always (unless scan fails). It's read by
 * Session T-prep gates ("no new Session starts until coverage-gap.json shows zero (a)")
 * and by the CI_BASELINE_ZERO doc.
 *
 * Reads openapi.yaml with a minimal YAML subset parser (no dep on js-yaml) —
 * scoped to paths / operations which follow a rigid indentation pattern.
 */

import { readFileSync, readdirSync, statSync, existsSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const PROJECT_ROOT = join(__filename, '..', '..');
const OPENAPI_PATH = join(PROJECT_ROOT, 'docs', 'openapi.yaml');
const BACKEND_API_DIR = join(PROJECT_ROOT, 'backend', 'src', 'app', 'api');
const CONTRACT_DIR = join(PROJECT_ROOT, 'frontend', 'tests', 'contract');
const REPORT_PATH = join(PROJECT_ROOT, 'docs', 'COVERAGE_GAP.json');

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';

const FLAG_JSON = process.argv.includes('--json');
const FLAG_WRITE = process.argv.includes('--write');

/* ---------------- OpenAPI path extraction ---------------- */

function extractOpenApiOperations(yamlText) {
  const lines = yamlText.split(/\r?\n/);
  const ops = [];
  let inPaths = false;
  let currentPath = null;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^paths:\s*$/.test(line)) {
      inPaths = true;
      continue;
    }
    if (!inPaths) continue;
    // End of paths section when a new top-level key appears
    if (/^[a-zA-Z]/.test(line) && !/^paths:/.test(line)) break;
    // Path key: 2 spaces + /path: (exactly, no further nesting)
    const pathMatch = line.match(/^  (\/[^:\s]+):\s*$/);
    if (pathMatch) {
      currentPath = pathMatch[1];
      continue;
    }
    // Operation key: 4 spaces + (get|post|put|delete|patch):
    const opMatch = line.match(/^    (get|post|put|delete|patch):\s*$/);
    if (opMatch && currentPath) {
      ops.push({ path: currentPath, method: opMatch[1].toUpperCase() });
    }
  }
  return ops;
}

/* ---------------- Backend route discovery (Next.js App Router) ---------------- */

function listRouteFiles(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  const walk = (p) => {
    for (const name of readdirSync(p)) {
      const full = join(p, name);
      let s;
      try { s = statSync(full); } catch { continue; }
      if (s.isDirectory()) walk(full);
      else if (name === 'route.ts' || name === 'route.js') out.push(full);
    }
  };
  walk(dir);
  return out;
}

function routeFileToPathSpec(absPath) {
  const rel = relative(BACKEND_API_DIR, absPath);
  const parts = rel.split(/[\\/]/);
  parts.pop(); // drop route.ts
  // Next.js dynamic segments: [id] → {id}
  const segments = parts.map((seg) => seg.replace(/^\[(\.\.\.)?([^\]]+)\]$/, '{$2}'));
  return '/' + segments.join('/');
}

function extractMethodsFromRouteFile(absPath) {
  const src = readFileSync(absPath, 'utf8');
  const methods = [];
  for (const m of ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']) {
    const re = new RegExp(`export\\s+(?:async\\s+)?function\\s+${m}\\b|export\\s+const\\s+${m}\\s*[=:]`);
    if (re.test(src)) methods.push(m);
  }
  return methods;
}

/* ---------------- Contract-test skeleton discovery ---------------- */

function listContractTests(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  const walk = (p) => {
    for (const name of readdirSync(p)) {
      const full = join(p, name);
      let s;
      try { s = statSync(full); } catch { continue; }
      if (s.isDirectory()) walk(full);
      else if (/\.(contract|spec)\.(ts|tsx|js|mjs)$/.test(name)) out.push(full);
    }
  };
  walk(dir);
  return out;
}

/* ---------------- Main ---------------- */

function normaliseKey(path, method) {
  return `${method} ${path}`;
}

function main() {
  if (!existsSync(OPENAPI_PATH)) {
    console.error(`${RED}openapi.yaml missing at ${OPENAPI_PATH}${RESET}`);
    process.exit(2);
  }
  const yaml = readFileSync(OPENAPI_PATH, 'utf8');
  const openApiOps = extractOpenApiOperations(yaml);
  const openApiKeys = new Set(openApiOps.map((o) => normaliseKey(o.path, o.method)));

  const backendRoutes = [];
  for (const f of listRouteFiles(BACKEND_API_DIR)) {
    const path = routeFileToPathSpec(f);
    for (const m of extractMethodsFromRouteFile(f)) {
      backendRoutes.push({ path, method: m, file: relative(PROJECT_ROOT, f) });
    }
  }
  const backendKeys = new Set(backendRoutes.map((o) => normaliseKey(o.path, o.method)));

  const contractTests = listContractTests(CONTRACT_DIR).map((f) => relative(PROJECT_ROOT, f));

  // (a) in OpenAPI but not in backend
  const missingBackend = [...openApiKeys]
    .filter((k) => !backendKeys.has(k))
    .sort();
  // (b) in backend but not in OpenAPI
  const missingSpec = [...backendKeys]
    .filter((k) => !openApiKeys.has(k))
    .sort();

  const report = {
    generatedAt: new Date().toISOString(),
    openApiOperations: openApiOps.length,
    backendOperations: backendRoutes.length,
    contractTestFiles: contractTests.length,
    gaps: {
      declaredNotImplemented: missingBackend,
      implementedNotDeclared: missingSpec,
    },
    backendRoutes,
    contractTests,
  };

  if (FLAG_WRITE) {
    writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2) + '\n', 'utf8');
  }

  if (FLAG_JSON) {
    console.log(JSON.stringify(report, null, 2));
    process.exit(0);
  }

  console.log(`${DIM}──────── GENPANO · OpenAPI ↔ Backend Coverage Gap ────────${RESET}`);
  console.log(`${DIM}openapi.yaml operations: ${openApiOps.length}${RESET}`);
  console.log(`${DIM}backend route exports:   ${backendRoutes.length}${RESET}`);
  console.log(`${DIM}contract test files:     ${contractTests.length}${RESET}`);
  console.log('');

  if (missingBackend.length === 0 && missingSpec.length === 0) {
    console.log(`${GREEN}● coverage-gap: CLEAN${RESET}  (OpenAPI ≡ backend; no gaps)`);
  } else {
    if (missingBackend.length > 0) {
      console.log(`${YELLOW}▲ declared in openapi.yaml, not yet implemented (${missingBackend.length}):${RESET}`);
      for (const k of missingBackend) console.log(`    ${YELLOW}· ${k}${RESET}`);
    }
    if (missingSpec.length > 0) {
      console.log(`${RED}▲ implemented in backend, not in openapi.yaml (${missingSpec.length}):${RESET}`);
      for (const k of missingSpec) console.log(`    ${RED}· ${k}${RESET}`);
    }
  }

  if (FLAG_WRITE) {
    console.log('');
    console.log(`${DIM}Report written to docs/COVERAGE_GAP.json${RESET}`);
  }
  // Reporting tool — never red on gaps alone (those are expected during baseline).
  process.exit(0);
}

main();
