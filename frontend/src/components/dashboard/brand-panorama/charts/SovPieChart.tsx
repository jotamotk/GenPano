import React from 'react';
import {
  ResponsiveContainer,
  PieChart, Pie, Cell,
  Tooltip, Legend,
} from 'recharts';
import { SOV_COLORS } from '../lib/constants';

type SovDatum = { name: string; value: number };

type SovPieChartProps = {
  data: SovDatum[] | null | undefined;
  primaryName: string;
};

export default function SovPieChart({ data, primaryName }: SovPieChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[240px] text-sm text-themed-muted">
        暂无声量份额数据
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius={88}
          innerRadius={48}
          paddingAngle={2}
          isAnimationActive={false}
        >
          {data.map((entry, i) => {
            const isPrimary = entry.name === primaryName;
            const isOthers = entry.name === '其他' || entry.name === 'Others';
            const fill = isPrimary
              ? 'var(--color-accent)'
              : isOthers
                ? 'var(--color-chart-line-grid)'
                : SOV_COLORS[(i + 1) % SOV_COLORS.length];
            return (
              <Cell
                key={entry.name}
                fill={fill}
                stroke="var(--color-bg-card)"
                strokeWidth={2}
              />
            );
          })}
        </Pie>
        <Tooltip
          contentStyle={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            borderRadius: 'var(--radius-btn)',
            fontSize: 12,
            boxShadow: 'var(--shadow-card-hover)',
          }}
          formatter={(v, name) => [`${v}%`, name]}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 11, color: 'var(--color-text-muted)' }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
