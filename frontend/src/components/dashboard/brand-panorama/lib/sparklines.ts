/* ── Sparkline data builders ──
   live: passes through provided sparklineOverride arrays
   mock: synthesizes from trendData using deterministic formulas
   Keep formulas byte-identical with the historical inline version. */

export type TrendRow = {
  day?: number;
  mentionRate?: number | null;
  sentiment?: number | null;
  [key: string]: unknown;
};

export type SparklineOverride = {
  mention?: number[];
  sov?: number[];
  sentiment?: number[];
  citation?: number[];
  rank?: number[];
};

export function buildSparklines(args: {
  isLive: boolean | undefined;
  trendData: TrendRow[];
  sovValue: number | null;
  industryRank: number | null;
  sparklineOverride: SparklineOverride | undefined;
}): {
  sparkMention: number[];
  sparkSov: number[];
  sparkSent: number[];
  sparkCite: number[];
  sparkRank: number[];
} {
  const { isLive, trendData, sovValue, industryRank, sparklineOverride } = args;
  const sparkMention = isLive
    ? (sparklineOverride?.mention ?? [])
    : trendData.map((d) => d.mentionRate ?? 0);
  const sparkSov = isLive
    ? (sparklineOverride?.sov ?? [])
    : trendData.map((d, i) => Math.max(0, Math.round(
        (sovValue || (d.mentionRate ?? 0) * 0.6) + Math.sin(i / 4) * 2 + (i % 7 === 0 ? -1.5 : 0.4)
      )));
  const sparkSent = isLive
    ? (sparklineOverride?.sentiment ?? [])
    : trendData.map((d) => Math.round((d.sentiment ?? 0) * 100));
  const sparkCite = isLive
    ? (sparklineOverride?.citation ?? [])
    : trendData.map((_, i) => Math.round(15 + Math.sin(i / 5) * 2));
  const sparkRank = isLive
    ? (sparklineOverride?.rank ?? [])
    : trendData.map((_, i) => {
        const progress = i / Math.max(trendData.length - 1, 1);
        const base     = (industryRank ?? 1) + 2 * (1 - progress);
        const jitter   = Math.sin(i / 3) * 0.35;
        return Math.max(1, Math.round((base + jitter) * 10) / 10);
      });
  return { sparkMention, sparkSov, sparkSent, sparkCite, sparkRank };
}
