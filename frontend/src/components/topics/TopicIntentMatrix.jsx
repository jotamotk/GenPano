/**
 * TopicIntentMatrix — Topic × Intent 堆叠 100% 矩阵
 * ────────────────────────────────────────────────────
 * Mode-agnostic: 同时被 Brand Mode (/brand/topics, PRD §4.2.5 "Topic × Intent 格局")
 * 和 Industry Mode (/industry/topics, PRD §4.6.1g v3.2 段 ④) 引用.
 *
 * 2026-04-21 v3.2: 从 `components/industry/IndustryTopicIntentMatrix.jsx` 重命名并上移到
 * `components/topics/`. 组件本身零 brand 概念依赖 (只用 topic.topicName /
 * topic.mentionCount 排序 + statistics.topicIntentBreakdown 合成占比), 因此可直接
 * 被两个 Mode 并行消费, 无需 fork 或 prop 扩展.
 *
 * Props:
 *   topics        [{ topicId, topicName, mentionCount, ... }] — 上游已按领域过滤
 *   limit         截取 Top N (default 8), 按 mentionCount desc
 *   onTopicClick  (topic) => void — 点击行跳转/开抽屉
 *
 * 4 Intent 颜色 (非 heatmap, 用 chart-N 系列, C9-1 exempt):
 *   - informational: chart-2 (蓝)
 *   - commercial:    chart-3 (紫)
 *   - transactional: chart-6 (绿)
 *   - navigational:  chart-7 (橙)
 */
import React, { useMemo } from 'react';
import { topicIntentBreakdown } from '../../lib/industry/statistics';

const INTENT_ORDER = [
  {
    key: 'informational',
    label: '信息 (Info)',
    color: 'var(--color-chart-2)',
  },
  {
    key: 'commercial',
    label: '商业 (Commercial)',
    color: 'var(--color-chart-3)',
  },
  {
    key: 'transactional',
    label: '交易 (Transactional)',
    color: 'var(--color-chart-6)',
  },
  {
    key: 'navigational',
    label: '导航 (Navigational)',
    color: 'var(--color-chart-7)',
  },
];

const DOMINANT_LABEL = {
  informational: '信息型',
  commercial: '商业型',
  transactional: '交易型',
  navigational: '导航型',
};

export default function TopicIntentMatrix({
  topics = [],
  limit = 8,
  onTopicClick,
}) {
  const rows = useMemo(
    () =>
      [...topics]
        .sort((a, b) => (b.mentionCount || 0) - (a.mentionCount || 0))
        .slice(0, limit)
        .map((t) => ({
          topic: t,
          breakdown: topicIntentBreakdown(t),
        })),
    [topics, limit]
  );

  return (
    <div className="t-card p-3 space-y-3">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[13px] font-medium text-themed-primary">
            Topic × Intent 交叉矩阵
          </div>
          <div className="text-[11px] text-themed-muted mt-0.5">
            同一 Topic 背后是查资料还是查购买 · 决定内容策略 vs 电商策略优先级
          </div>
        </div>
        <div className="flex items-center gap-3 text-[10px]">
          {INTENT_ORDER.map((i) => (
            <div key={i.key} className="flex items-center gap-1">
              <span
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  background: i.color,
                  borderRadius: 2,
                }}
              />
              <span className="text-themed-muted">{i.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        {rows.map(({ topic, breakdown }) => (
          <div
            key={topic.topicId}
            className="flex items-center gap-3 cursor-pointer hover:bg-themed-subtle px-1 py-1 rounded-card"
            onClick={() => onTopicClick && onTopicClick(topic)}
          >
            <div className="w-[160px] truncate text-[12px] text-themed-primary">
              {topic.topicName}
            </div>
            <div
              className="flex-1 flex overflow-hidden rounded-full"
              style={{ height: 18, background: 'var(--color-surface-subtle)' }}
            >
              {INTENT_ORDER.map((i) => {
                const pct = breakdown[i.key];
                if (pct <= 0) return null;
                return (
                  <div
                    key={i.key}
                    className="flex items-center justify-center text-[9px] font-medium"
                    style={{
                      width: `${pct}%`,
                      background: i.color,
                      color: '#fff',
                    }}
                    title={`${i.label}: ${pct}%`}
                  >
                    {pct >= 12 ? `${pct}%` : ''}
                  </div>
                );
              })}
            </div>
            <div className="w-[86px] text-right">
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full"
                style={{
                  background: 'var(--color-surface-subtle)',
                  color: INTENT_ORDER.find((i) => i.key === breakdown.dominant)
                    ?.color,
                }}
              >
                {DOMINANT_LABEL[breakdown.dominant]}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
