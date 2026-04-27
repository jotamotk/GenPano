import { PieChart, Pie, Cell } from 'recharts';

const TIERS = [
  { min: 90, label: 'A+' },
  { min: 80, label: 'A' },
  { min: 70, label: 'B' },
  { min: 60, label: 'C' },
  { min: 40, label: 'D' },
  { min: 0,  label: 'F' },
];

export default function PanoRing({ score = 75, size = 120 }) {
  const tier = TIERS.find(t => score >= t.min)?.label || 'F';

  const color = score >= 80 ? 'var(--color-accent)'
    : score >= 60 ? 'var(--color-success)'
    : score >= 40 ? 'var(--color-warning)'
    : 'var(--color-danger)';

  const data = [
    { value: score },
    { value: 100 - score },
  ];

  const innerR = size * 0.32;
  const outerR = size * 0.44;

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <PieChart width={size} height={size}>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={innerR}
          outerRadius={outerR}
          startAngle={90}
          endAngle={-270}
          dataKey="value"
          stroke="none"
          cornerRadius={outerR}
        >
          <Cell fill={color} />
          <Cell fill="var(--color-bg-progress-track)" />
        </Pie>
      </PieChart>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-semibold tabular-nums" style={{ color, fontSize: size > 100 ? 22 : 16, letterSpacing: '-0.03em' }}>
          {Math.round(score)}
        </span>
        <span className="text-themed-muted font-medium" style={{ fontSize: size > 100 ? 11 : 9 }}>
          {tier}
        </span>
      </div>
    </div>
  );
}
