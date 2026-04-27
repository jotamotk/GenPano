import { LineChart, Line, ResponsiveContainer } from 'recharts';

// width / height 默认为 '100%' — 让 Recharts 的 ResponsiveContainer 真正响应父容器尺寸.
// 调用方若包在 `<div className="h-7 flex-1">` / `<div style={{width:200,height:40}}>` 里,
// Sparkline 会自动撑满; 调用方也可显式传入数值 (width={100}) 走固定宽度.
export default function MiniSparkline({ data = [], color, width = '100%', height = '100%' }) {
  if (!data || data.length === 0) return null;

  const chartData = data.map((v, i) => ({ v, i }));
  const strokeColor = color || 'var(--color-accent)';

  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={strokeColor}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
