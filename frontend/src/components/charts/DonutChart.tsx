import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

export default function DonutChart({ segments = [], size = 200 }) {
  if (!segments || segments.length === 0) return null;

  const innerR = size * 0.28;
  const outerR = size * 0.42;

  return (
    <div style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={segments}
            cx="50%"
            cy="50%"
            innerRadius={innerR}
            outerRadius={outerR}
            dataKey="value"
            nameKey="name"
            stroke="var(--color-bg-card)"
            strokeWidth={2}
            paddingAngle={1}
          >
            {segments.map((entry, idx) => (
              <Cell key={idx} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name) => [`${value}%`, name]}
            contentStyle={{
              background: 'var(--color-tooltip-bg)',
              border: '1px solid var(--color-border)',
              borderRadius: 6,
              boxShadow: '0 4px 12px rgba(50,50,93,0.1)',
              fontSize: 12,
              padding: '6px 10px',
            }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
