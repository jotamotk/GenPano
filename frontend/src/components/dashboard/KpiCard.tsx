import { Card, Badge, MetricLabel } from '../ui';
import { MiniSparkline } from '../charts';

/**
 * KpiCard — Reusable KPI metric card for Brand Mode pages.
 *
 * Props:
 *   label: string — KPI name (e.g., "提及率", "SoV")
 *   value: string — formatted display value (e.g., "24.5%", "#3")
 *   delta: number — period-over-period change (e.g., +3.2 or -1.5)
 *   deltaLabel: string — optional delta context (e.g., "vs last 7d")
 *   sparkData: number[] — array of 14 data points for MiniSparkline
 *   sparkColor: string — sparkline color, default 'var(--color-accent)'
 *   subMetrics: Array<{label: string, value: string, engine?: string}> — optional engine breakdown (up to 3)
 *   onClick: function — optional click handler
 *   className: string — additional classes
 */
export default function KpiCard({
  label,
  value,
  delta,
  deltaLabel = '',
  helpText,
  sparkData = [],
  sparkColor = 'var(--color-accent)',
  subMetrics = [],
  onClick,
  className = '',
}) {
  // Determine delta badge variant based on sign
  const getDeltaVariant = () => {
    if (delta > 0) return 'green';
    if (delta < 0) return 'red';
    return 'default';
  };

  const deltaVariant = getDeltaVariant();
  const deltaText = delta > 0 ? `+${delta}` : String(delta);

  return (
    <Card
      className={`p-4 ${className}`.trim()}
      onClick={onClick}
      hover={!!onClick}
    >
      {/* Top row: label + delta pill */}
      <div className="flex items-center justify-between mb-3">
        <MetricLabel helpText={helpText} className="text-sm text-themed-muted font-medium">
          {label}
        </MetricLabel>
        {delta !== undefined && (
          <Badge variant={deltaVariant} size="sm">
            {deltaText} {deltaLabel}
          </Badge>
        )}
      </div>

      {/* Middle: large value */}
      <div className="mb-3">
        <span className="text-2xl font-bold text-themed-primary tabular-nums">
          {value}
        </span>
      </div>

      {/* Sparkline */}
      {sparkData && sparkData.length > 0 && (
        <div className="mb-3 h-8 w-full">
          <MiniSparkline data={sparkData} color={sparkColor} />
        </div>
      )}

      {/* Sub-metrics (engine breakdown) */}
      {subMetrics && subMetrics.length > 0 && (
        <div className="flex gap-2">
          {subMetrics.slice(0, 3).map((metric, idx) => (
            <div key={idx} className="flex-1 text-center p-2 rounded bg-themed-subtle">
              <p className="text-xs text-themed-muted mb-1">{metric.label}</p>
              <p className="text-sm font-semibold text-themed-primary tabular-nums">
                {metric.value}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
