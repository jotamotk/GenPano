/*
 * BrandTopicHeatmap — PRD §4.6-IA-v2.L (2026-04-20, Session T6')
 * ────────────────────────────────────────────────────────────────
 * Brand × Topic heatmap used on Visibility (sequential color, mention
 * rate / SoV) and Sentiment (diverging color, sentiment score).
 *
 * Props:
 *   rows              [{ brandId, brandName, values: [{ topicId, topicLabel, value, sample }] }]
 *   scale             'sequential' | 'diverging'
 *   metric            'mentionRate' | 'sov' | 'sentiment' | 'sovDelta'
 *   highlightBrandId  row to mark as "the current brand" (adds left accent bar)
 *   onCellClick       (brandId, topicId) => void
 *   loading           boolean
 *   emptyHint         string
 *
 * Harness C9 forbids chart-N / sentiment-* token reuse and inline hex
 * here — only --color-heatmap-* may be referenced.
 */
import React from 'react';

/* Thresholds chosen to match DESIGN_TOKENS "Heatmap 色带" table. */
function seqTokenFor(value) {
  if (value == null || Number.isNaN(value)) return 'var(--color-heatmap-seq-0)';
  const v = Math.max(0, Math.min(1, value));
  if (v < 0.02) return 'var(--color-heatmap-seq-0)';
  if (v < 0.1)  return 'var(--color-heatmap-seq-1)';
  if (v < 0.25) return 'var(--color-heatmap-seq-2)';
  if (v < 0.5)  return 'var(--color-heatmap-seq-3)';
  if (v < 0.75) return 'var(--color-heatmap-seq-4)';
  return 'var(--color-heatmap-seq-5)';
}

function divTokenFor(value) {
  if (value == null || Number.isNaN(value)) return 'var(--color-heatmap-div-zero)';
  const v = Math.max(-1, Math.min(1, value));
  if (v < -0.5) return 'var(--color-heatmap-div-neg-2)';
  if (v < -0.1) return 'var(--color-heatmap-div-neg-1)';
  if (v <= 0.1) return 'var(--color-heatmap-div-zero)';
  if (v <= 0.5) return 'var(--color-heatmap-div-pos-1)';
  return 'var(--color-heatmap-div-pos-2)';
}

function formatValue(value, metric) {
  if (value == null || Number.isNaN(value)) return '—';
  if (metric === 'sentiment' || metric === 'sovDelta') {
    return value.toFixed(2);
  }
  // default: mentionRate / sov — render as %
  return `${(value * 100).toFixed(1)}%`;
}

function cellTextColor(bgToken) {
  // Dark on light, white on dark. We only need this for the 3 darkest tokens.
  const dark = ['var(--color-heatmap-seq-4)', 'var(--color-heatmap-seq-5)', 'var(--color-heatmap-div-neg-2)', 'var(--color-heatmap-div-pos-2)'];
  return dark.includes(bgToken) ? '#FFFFFF' : 'var(--color-text-primary)';
}

export default function BrandTopicHeatmap({
  rows = [],
  scale = 'sequential',
  metric = 'mentionRate',
  highlightBrandId,
  onCellClick,
  loading = false,
  emptyHint = '暂无样本',
}) {
  if (loading) {
    return (
      <div
        className="rounded-card p-4 text-xs text-themed-muted"
        style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
      >
        加载中…
      </div>
    );
  }
  if (!rows || rows.length === 0) {
    return (
      <div
        className="rounded-card p-4 text-xs text-themed-muted"
        style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
      >
        {emptyHint}
      </div>
    );
  }

  // Use the first row's topic order as the column header source.
  const topics = rows[0].values.map((v) => ({ topicId: v.topicId, topicLabel: v.topicLabel }));
  const tokenFor = scale === 'diverging' ? divTokenFor : seqTokenFor;

  return (
    <div
      className="rounded-card overflow-hidden"
      style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
    >
      <div className="overflow-x-auto">
        <table className="w-full" style={{ borderCollapse: 'separate', borderSpacing: 0 }}>
          <thead>
            <tr>
              <th
                className="text-left text-[11px] font-medium text-themed-muted px-3 py-2"
                style={{ background: 'var(--color-bg-subtle)', borderBottom: '1px solid var(--color-border-subtle)' }}
              >
                品牌 \ Topic
              </th>
              {topics.map((t) => (
                <th
                  key={t.topicId}
                  className="text-left text-[11px] font-medium text-themed-muted px-2 py-2 whitespace-nowrap"
                  style={{
                    background: 'var(--color-bg-subtle)',
                    borderBottom: '1px solid var(--color-border-subtle)',
                    minWidth: 84,
                    maxWidth: 120,
                  }}
                  title={t.topicLabel}
                >
                  {t.topicLabel.length > 10 ? `${t.topicLabel.slice(0, 10)}…` : t.topicLabel}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isHighlight = row.brandId === highlightBrandId;
              return (
                <tr key={row.brandId}>
                  <td
                    className="px-3 py-2 text-xs font-medium whitespace-nowrap"
                    style={{
                      background: 'var(--color-bg-card)',
                      color: isHighlight ? 'var(--color-accent)' : 'var(--color-text-primary)',
                      borderLeft: isHighlight ? '3px solid var(--color-accent)' : '3px solid transparent',
                      borderBottom: '1px solid var(--color-border-subtle)',
                    }}
                  >
                    {row.brandName}
                  </td>
                  {row.values.map((cell) => {
                    const bgToken = tokenFor(cell.value);
                    const color = cellTextColor(bgToken);
                    return (
                      <td
                        key={cell.topicId}
                        className="px-2 py-2 text-xs font-medium text-center cursor-pointer transition-opacity"
                        style={{
                          background: bgToken,
                          color,
                          borderBottom: '1px solid var(--color-border-subtle)',
                          minWidth: 84,
                        }}
                        title={`${row.brandName} × ${cell.topicLabel}: ${formatValue(cell.value, metric)}${cell.sample != null ? ` · 样本 ${cell.sample}` : ''}`}
                        onClick={() => onCellClick?.(row.brandId, cell.topicId)}
                        onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.85'; }}
                        onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                      >
                        {formatValue(cell.value, metric)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
