/**
 * Sparkline — tiny inline SVG sparkline (no heavy chart lib on marketing page).
 * stroke uses CSS variable so theme can swap colors without code change.
 *
 * Moved verbatim from LandingPage.tsx (lines 488-506).
 */

interface SparklineProps {
  points: number[];
  strokeVar?: string;
  width?: number;
  height?: number;
}

export function Sparkline({
  points,
  strokeVar = '--color-chart-1',
  width = 160,
  height = 36,
}: SparklineProps) {
  if (!points?.length) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = width / (points.length - 1);
  const d = points
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
      <path d={d} fill="none" stroke={`var(${strokeVar})`} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
