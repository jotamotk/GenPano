import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';

/**
 * Reusable trend line/area chart.
 * @param {Object[]} data - Array of objects with a 'name' key for x-axis
 * @param {Object[]} lines - Array of { key, label, color, dashed?, area? }
 * @param {number} height - Chart height in px
 */
export default function TrendChart({ data = [], lines = [], height = 220 }) {
  if (!data.length || !lines.length) return null;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
        <defs>
          {lines.filter(l => l.area !== false).map(line => (
            <linearGradient key={line.key} id={`grad-${line.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={line.color} stopOpacity={0.12} />
              <stop offset="100%" stopColor={line.color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>

        <CartesianGrid
          strokeDasharray="none"
          stroke="var(--color-chart-line-grid)"
          vertical={false}
        />

        <XAxis
          dataKey="name"
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 11, fill: 'var(--color-chart-axis-text)' }}
          dy={8}
        />

        <YAxis
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 11, fill: 'var(--color-chart-axis-text)' }}
          width={40}
        />

        <Tooltip
          contentStyle={{
            background: 'var(--color-tooltip-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(50,50,93,0.1)',
            fontSize: 12,
            padding: '8px 12px',
          }}
          cursor={{ stroke: 'var(--color-accent)', strokeWidth: 1, strokeDasharray: '3 3' }}
        />

        <Legend
          verticalAlign="bottom"
          height={32}
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 12, color: 'var(--color-text-muted)' }}
        />

        {lines.map(line => (
          <Area
            key={line.key}
            type="monotone"
            dataKey={line.key}
            name={line.label}
            stroke={line.color}
            strokeWidth={line.dashed ? 1.5 : 2}
            strokeDasharray={line.dashed ? '5 4' : undefined}
            fill={line.area !== false ? `url(#grad-${line.key})` : 'none'}
            dot={false}
            activeDot={line.dashed ? false : { r: 3, strokeWidth: 0, fill: line.color }}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
