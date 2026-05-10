import React, { useMemo } from 'react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell,
} from 'recharts';
import { Card, Badge, MetricLabel } from '../ui';

/* ─────────────────────────────────────────────────────────────
   ContentGapPanel — PRD §4.2.7.B 内容策略: 反向 "被提及 − 被归因" 缺口
   ─────────────────────────────────────────────────────────────
   两个子区块:
     ① Top N gap Topics 表格 — 按 gapRatio 降序
     ② 页面类型分布对比 — 三列堆叠对比图 (我 vs 行业中位 vs Top 竞品)

   Props:
     - topics: CONTENT_GAP_TOPICS (Array<{ topicId, topicText, ... gapRatio }>)
     - distribution: CONTENT_GAP_PAGE_TYPE_DISTRIBUTION (Array<{ pageType, me, industryMedian, topCompetitor }>)
     - maxTopics: 默认 10, 展示 Top N

   UI 语言走用户价值 ("缺口占比"), 不写开发者约束.
─────────────────────────────────────────────────────────────── */

const gapRatioSev = (r) => {
  if (r >= 0.6) return { label: '重度', color: 'var(--color-danger)', variant: 'red' };
  if (r >= 0.45) return { label: '中度', color: 'var(--color-warning)', variant: 'orange' };
  return { label: '轻度', color: 'var(--color-accent)', variant: 'accent' };
};

export default function ContentGapPanel({
  topics = [],
  distribution = [],
  maxTopics = 10,
}) {
  const topN = useMemo(() => topics.slice(0, maxTopics), [topics, maxTopics]);

  return (
    <div className="space-y-6">
      {/* ① Top gap topics */}
      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-themed-subtle flex items-baseline justify-between">
          <div>
            <h3 className="text-sm font-semibold text-themed-primary">
              <MetricLabel helpText="这些话题里主品牌被提到很多，但 AI 很少把它们归因到官方或合作内容上。">
                内容缺口 Top {topN.length}
              </MetricLabel>
            </h3>
          </div>
          <Badge variant="default" size="sm">
            <MetricLabel helpText="缺口占比 = (被提及 - 被归因) / 被提及">
              缺口占比
            </MetricLabel>
          </Badge>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full t-table">
            <thead>
              <tr>
                <th className="text-left py-2.5 px-5 text-xs font-medium text-themed-muted">话题</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">品类路径</th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  <MetricLabel helpText="该话题下进入分析范围的 AI 回答数量。">相关回答数</MetricLabel>
                </th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  <MetricLabel helpText="相关回答中提到主品牌的次数。">被提及</MetricLabel>
                </th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  <MetricLabel helpText="相关回答中把内容或引用归因到主品牌官方或合作资产的次数。">被归因</MetricLabel>
                </th>
                <th className="text-right py-2.5 px-4 text-xs font-medium text-themed-muted">
                  <MetricLabel helpText="缺口占比 = (被提及 - 被归因) / 被提及。">缺口占比</MetricLabel>
                </th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">Top 竞品</th>
                <th className="text-left py-2.5 px-4 text-xs font-medium text-themed-muted">主要页面类型</th>
              </tr>
            </thead>
            <tbody>
              {topN.map((t) => {
                const sev = gapRatioSev(t.gapRatio);
                return (
                  <tr key={t.topicId} className="border-t border-themed-subtle hover:bg-themed-subtle transition-colors">
                    <td className="py-2.5 px-5 text-sm text-themed-primary max-w-[260px]">
                      <span className="line-clamp-1">{t.topicText}</span>
                    </td>
                    <td className="py-2.5 px-4 text-xs text-themed-muted">{t.categoryPath}</td>
                    <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {t.relevantResponses}
                    </td>
                    <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {t.myMentions}
                    </td>
                    <td className="py-2.5 px-4 text-right text-sm tabular-nums text-themed-secondary">
                      {t.myAttributions}
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      <span
                        className="inline-flex items-center gap-1.5 text-sm font-semibold tabular-nums"
                        style={{ color: sev.color }}
                      >
                        {Math.round(t.gapRatio * 100)}%
                        <Badge variant={sev.variant} size="sm">{sev.label}</Badge>
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-xs text-themed-secondary">
                      <span className="inline-flex items-center gap-1">
                        <span className="font-medium">{t.topCompetitorBrand}</span>
                        <span className="text-themed-muted tabular-nums">· {t.topCompetitorAttributions}</span>
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-xs text-themed-muted">{t.topPageType}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ② Page-type distribution comparison */}
      <Card className="p-5">
        <div className="mb-4 flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-sm font-semibold text-themed-primary">
              <MetricLabel helpText="AI 给出的引用链接落在什么类型的页面，用于比较主品牌、行业中位和 Top 竞品的内容资产结构。">
                页面类型分布对比
              </MetricLabel>
            </h3>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart
            data={distribution}
            margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
          >
            <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="pageType"
              tick={{ fontSize: 11, fill: 'var(--color-chart-axis-text)' }}
              axisLine={{ stroke: 'var(--color-border-subtle)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--color-chart-axis-text)' }}
              axisLine={{ stroke: 'var(--color-border-subtle)' }}
              tickLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 'var(--radius-btn)',
                fontSize: 12,
                boxShadow: 'var(--shadow-card-hover)',
              }}
              formatter={(value) => [`${value}%`, undefined]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="square" />
            <Bar dataKey="me" name="我" fill="var(--color-accent)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="industryMedian" name="行业中位" fill="var(--color-chart-3)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="topCompetitor" name="Top 竞品" fill="var(--color-chart-6)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
