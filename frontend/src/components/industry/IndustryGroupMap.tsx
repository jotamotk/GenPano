/**
 * IndustryGroupMap — PRD §4.6.1e §B 段 ⑥ (v2 新增)
 * ──────────────────────────────────────────
 * 按 BRANDS.parentCompany 聚合的集团版图. Top 5 集团卡片 grid.
 * 每卡: 集团名 + 旗下品牌数 + 合计 SoV + 最大品牌 + 品牌气泡排开
 * (按 panoScore desc).
 *
 * 回答用户问题: "集团版图如何切? 母集团 + 兄弟品牌的合计 SoV 是多少?"
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { aggregateByGroup } from '../../lib/industry/statistics';

function sentimentColor(s) {
  if (s >= 0.75) return 'var(--color-success)';
  if (s >= 0.6) return 'var(--color-chart-3)';
  return 'var(--color-warning)';
}

export default function IndustryGroupMap({
  brands = [],
  primaryBrandId = null,
  limit = 5,
}) {
  const groups = aggregateByGroup(brands).slice(0, limit);
  const navigate = useNavigate();

  if (!groups.length) {
    return null;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <div className="text-[13px] font-medium text-themed-primary">
          集团版图 · Top {limit}
        </div>
        <div className="text-[11px] text-themed-muted">
          按合计 SoV 降序 · 集团维度竞争格局
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {groups.map((g) => {
          const myInGroup = g.brands.some((b) => b.id === primaryBrandId);
          return (
            <div
              key={g.groupName}
              className={`t-card p-3 space-y-2 ${
                myInGroup ? 'ring-1 ring-[var(--color-accent)]/50' : ''
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-[13px] font-medium text-themed-primary">
                    {g.groupName}
                    {myInGroup && (
                      <span className="ml-1.5 text-[10px] text-[var(--color-accent)]">
                        (我的集团)
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-themed-muted mt-0.5">
                    {g.brandCount} 个品牌 · 头部: {g.maxBrand?.name}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-semibold text-themed-primary tabular-nums">
                    {g.totalSov}%
                  </div>
                  <div className="text-[10px] text-themed-muted">合计 SoV</div>
                </div>
              </div>

              {/* Brand bubbles */}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {g.brands.map((b) => {
                  const isMine = b.id === primaryBrandId;
                  const size = 10 + Math.sqrt((b.panoScore || 50) / 5);
                  return (
                    <button
                      key={b.id}
                      onClick={() =>
                        navigate(`/brand/overview?brandId=${b.id}`)
                      }
                      title={`${b.name} · PANO ${Math.round(
                        b.panoScore
                      )} · SoV ${(b.sov || 0).toFixed(1)}%`}
                      className="flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] hover:opacity-80 transition-opacity"
                      style={{
                        background: isMine
                          ? 'var(--color-accent)'
                          : `${sentimentColor(b.sentiment)}22`,
                        color: isMine ? 'white' : 'var(--color-text-primary)',
                      }}
                    >
                      <span
                        className="rounded-full"
                        style={{
                          width: size,
                          height: size,
                          background: isMine
                            ? 'white'
                            : sentimentColor(b.sentiment),
                        }}
                      />
                      <span className="truncate max-w-[80px]">{b.name}</span>
                    </button>
                  );
                })}
              </div>

              <div className="flex items-center justify-between text-[11px] text-themed-muted border-t border-themed-subtle pt-2">
                <span>均 PANO {g.avgPano}</span>
                <span>均情感 {(g.avgSentiment * 100).toFixed(0)}%</span>
                <span>合计提及 {g.totalMentionRate.toFixed(1)}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
