/**
 * HARNESS SELF-SEEDED VIOLATION · Rule C14-1 (analysis-page-density)
 *
 * PURPOSE: proves C14-1 catches <h1 text-2xl/3xl/4xl> and <h2 text-2xl+> in
 * analysis-page contexts. This fixture intentionally uses text-3xl on an h1.
 *
 * DO NOT IMPORT. See A1_cjk_leak.cifixture.jsx for fixture policy.
 */

/* eslint-disable */
export function C14_H1Text3xl() {
  return (
    <div>
      <h1 className="text-3xl font-bold">Dashboard</h1>
      <h2 className="text-2xl">Section</h2>
    </div>
  );
}
