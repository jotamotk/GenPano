/**
 * HARNESS SELF-SEEDED VIOLATION · Rule B1 (sparkline-numeric-default)
 *
 * PURPOSE: proves the B1 grep catches MiniSparkline props with numeric
 * width/height literals that would pixel-lock parent layout. Default must
 * be '100%' string; this file deliberately sets 260 and 48.
 *
 * DO NOT IMPORT. Excluded from build & tests — see A1_cjk_leak.cifixture.jsx.
 */

/* eslint-disable */
const MiniSparkline = ({ width, height, data }) => null;

export function B1_SparklineLiteral() {
  const data = [1, 2, 3, 4, 5];
  return <MiniSparkline width={260} height={48} data={data} />;
}
