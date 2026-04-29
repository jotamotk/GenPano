import React from 'react';

/**
 * Shared placeholder for admin pages whose data wiring lives in later
 * Sessions (1.2' / 3' / Steps 4-7). Keeps Step 9 scope honest: the route
 * skeleton is real, the data layer is a typed `TODO`.
 */
export interface AdminPlaceholderPageProps {
  title: string;
  description: string;
  prdSection: string;
  pendingSession: string;
  module: 'A' | 'B' | 'C' | 'D';
}

export default function AdminPlaceholderPage({
  title,
  description,
  prdSection,
  pendingSession,
  module,
}: AdminPlaceholderPageProps) {
  return (
    <div className="max-w-[960px]">
      <div className="flex items-baseline gap-3 mb-2">
        <h1
          className="text-xl font-bold"
          style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}
        >
          {title}
        </h1>
        <span
          className="text-[11px] font-bold px-1.5 py-0.5 rounded"
          style={{
            background: 'var(--color-bg-page)',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-muted)',
          }}
        >
          Module {module}
        </span>
      </div>
      <p className="text-xs mb-5" style={{ color: 'var(--color-text-muted)' }}>
        {description}
      </p>

      <div
        className="rounded p-4"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px dashed var(--color-border-subtle)',
        }}
      >
        <div
          className="text-[13px] font-semibold mb-2"
          style={{ color: 'var(--color-text-primary)' }}
        >
          数据接入 pending
        </div>
        <ul
          className="text-xs space-y-1.5"
          style={{ color: 'var(--color-text-muted)' }}
        >
          <li>
            真相源: <code>{prdSection}</code>
          </li>
          <li>
            数据层接入 Session: <code>{pendingSession}</code>
          </li>
          <li>本页 Step 9 仅交付 route + 入口卡, 后端契约稳定后回填表格 / 图表 / 操作.</li>
        </ul>
      </div>
    </div>
  );
}
