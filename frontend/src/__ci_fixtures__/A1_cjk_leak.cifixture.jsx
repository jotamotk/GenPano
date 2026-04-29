/**
 * HARNESS SELF-SEEDED VIOLATION · Rule A1 (cjk-in-jsx-text-node)
 *
 * PURPOSE: proves the A1 grep rule actually catches CJK Chinese in a JSX
 * text node (rather than in an i18n key value). Selftest asserts ci-check.mjs
 * reports at least one violation inside this file.
 *
 * DO NOT IMPORT, RENDER, OR LINT-FIX. This file is excluded from Vite build
 * (vite.config.js rollupOptions.external), from tsconfig, from prettier, and
 * from vitest/playwright.
 *
 * Fixture for CJK hardcoded text detection.
 */

export function A1_CjkLeak() {
  return (
    <div>
      <h1>总览面板</h1>
      <p>这是一段中文硬编码文案，违反 A1 规则。</p>
    </div>
  );
}
