/**
 * HARNESS SELF-SEEDED VIOLATION · Rule C11-1 (mentionrate-literal-in-range)
 *
 * PURPOSE: proves the C11-1 regex catches mentionRate literals ≥ 1 in
 * mock/data files. The 1620 below is the exact "1620% bug" that triggered
 * Decision #20 — stored 16.20 but rendered as (v*100).toFixed(1)%.
 *
 * DO NOT IMPORT. See A1_cjk_leak.cifixture.jsx for fixture policy.
 */

/* eslint-disable */
export const BROKEN_BRANDS = [
  { id: 'test-a', name: 'TestA', mentionRate: 1620 },
  { id: 'test-b', name: 'TestB', mentionRate: 3.14 },
];
