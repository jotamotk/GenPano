import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList
} from 'recharts';

/**
 * Horizontal bar chart for category distributions.
 * @param {Object[]} data - Array of { name, value, color? }
 * @param {number} height - Chart height
 * @param {string} defaultColor - Fallback bar color
 * @param {boolean} showLabels - Render inline value labels (default: true)
 * @param {string}  valueSuffix - Label suffix, default '%'
 * @param {boolean} monochrome - Ignore per-entry color and use defaultColor uniformly
 */
export default function HorizontalBar({
  data = [],
  height,
  defaultColor = 'var(--color-accent)',
  showLabels = true,
  valueSuffix = '%',
  monochrome = false,
}) {
  if (!data.length) return null;

  const h = height || Math.max(data.length * 40, 120);
  const maxValue = Math.max(...data.map((d) => d.value || 0));

  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 0, right: showLabels ? 40 : 8, left: 0, bottom: 0 }}
      >
        <XAxis type="number" hide domain={[0, Math.ceil(maxValue * 1.1)]} />
        <YAxis
          type="category"
          dataKey="name"
          axisLine={false}
          tickLine={false}
          width={56}
          tick={{ fontSize: 12, fill: 'var(--color-text-secondary)' }}
        />
        <Tooltip
          formatter={(value) => [`${value}${valueSuffix}`]}
          contentStyle={{
            background: 'var(--color-tooltip-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(50,50,93,0.1)',
            fontSize: 12,
            padding: '6px 10px',
          }}
          cursor={{ fill: 'var(--color-chart-cursor)' }}
        />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={14}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={monochrome ? defaultColor : (entry.color || defaultColor)} />
          ))}
          {showLabels && (
            <LabelList
              dataKey="value"
              position="right"
              offset={6}
              formatter={(v) => `${v}${valueSuffix}`}
              style={{ fill: 'var(--color-text-primary)', fontSize: 11, fontWeight: 600 }}
            />
          )}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
