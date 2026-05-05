/**
 * IndustryMoversRow — PRD §4.6.1e §B 段 ⑤ (异动 Top 3)
 * ───────────────────────────────────────────────
 * 近 7d 按 |change| desc 排序取 Top 3. 正涨绿 / 负跌红.
 * 点击卡 → /brand/overview?brandId=:id (跨 Mode 跳转).
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { topByAbsField } from '../../lib/industry/statistics';

export default function IndustryMoversRow({ brands = [] }) {
  const navigate = useNavigate();
  const movers = topByAbsField(brands, 'change', 3);

  if (!movers.length) {
    return null;
  }

  return (
    <div className="space-y-2">
      <div className="text-[13px] font-medium text-themed-primary">
        近 7 天异动 Top 3
      </div>
      <div className="grid grid-cols-3 gap-3">
        {movers.map((b) => {
          const delta = parseFloat(b.change);
          const isUp = delta > 0;
          const color = isUp ? 'var(--color-success)' : 'var(--color-danger)';
          return (
            <div
              key={b.id}
              onClick={() => navigate(`/brand/overview?brandId=${b.id}`)}
              className="t-card t-card-interactive p-3 cursor-pointer"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-[13px] font-medium text-themed-primary">
                    {b.name}
                  </div>
                  <div className="text-[11px] text-themed-muted mt-0.5">
                    {b.positioning}
                  </div>
                </div>
                <div
                  className="flex items-center gap-1 text-sm font-semibold tabular-nums"
                  style={{ color }}
                >
                  {isUp ? (
                    <TrendingUp size={14} />
                  ) : (
                    <TrendingDown size={14} />
                  )}
                  {b.change}
                </div>
              </div>
              <div className="mt-2 flex items-center gap-3 text-[11px] text-themed-muted">
                <span>PANO {Math.round(b.panoScore)}</span>
                <span>·</span>
                <span>SoV {(b.sov || 0).toFixed(1)}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
