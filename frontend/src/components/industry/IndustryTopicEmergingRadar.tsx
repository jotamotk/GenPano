/**
 * IndustryTopicEmergingRadar — PRD §4.6.1g §B 段 ④ (v3.1, 2026-04-20)
 * ────────────────────────────────────────────────────────────────────
 * 两列: 新兴 Topic Top 5 (左, 金边) + 衰退 Topic Top 5 (右, 灰边).
 * 新兴 = emergingScore desc 中 isEmerging=true; 衰退 = emergingScore asc 剩余.
 * 每卡: Topic 名 + 情感 Badge + "首次出现 Nd 前" / "降幅 N%" + 关联 Top 3 品牌名带.
 * v3.1: 删除卡面 "N 次提及" (MVP mock 绝对量不科学), 保留相对型 "首次出现"/"降幅".
 */
import React, { useMemo } from 'react';
import { Sparkles, TrendingDown } from 'lucide-react';
import { emergingScore, brandTopicHits } from '../../lib/industry/statistics';

function topRelatedBrands(topic, brands, n = 3) {
  return [...brands]
    .map((b) => ({ brand: b, hits: brandTopicHits(b, topic) }))
    .sort((a, b) => b.hits - a.hits)
    .slice(0, n)
    .map((x) => x.brand);
}

function sentimentTone(s) {
  if (s >= 0.7) return 'var(--color-success)';
  if (s <= 0.4) return 'var(--color-danger)';
  return 'var(--color-warning)';
}

function TopicCard({ topic, brands, type, onClick }) {
  const related = topRelatedBrands(topic, brands);
  const borderColor =
    type === 'emerging' ? 'var(--color-warning)' : 'var(--color-text-muted)';
  const score = emergingScore(topic);
  return (
    <div
      onClick={onClick}
      className="t-card t-card-interactive p-3 cursor-pointer"
      style={{
        borderLeft: `3px solid ${borderColor}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            {type === 'emerging' ? (
              <Sparkles
                size={12}
                style={{ color: 'var(--color-warning)' }}
              />
            ) : (
              <TrendingDown
                size={12}
                style={{ color: 'var(--color-danger)' }}
              />
            )}
            <div className="text-[13px] font-medium text-themed-primary truncate">
              {topic.topicName}
            </div>
          </div>
          <div className="text-[11px] text-themed-muted mt-0.5 tabular-nums">
            {type === 'emerging'
              ? `首次出现 ${Math.max(3, 30 - Math.round(score / 3))} 天前`
              : `近期降幅 ${Math.round(Math.abs(score) * 0.8 + 5)}%`}
          </div>
        </div>
        <span
          className="text-[11px] px-2 py-0.5 rounded-full tabular-nums"
          style={{
            background: 'var(--color-surface-subtle)',
            color: sentimentTone(topic.avgSentiment),
          }}
        >
          {Math.round((topic.avgSentiment || 0) * 100)}%
        </span>
      </div>
      {related.length > 0 && (
        <div className="mt-2 flex items-center gap-1">
          <span className="text-[10px] text-themed-muted">关联:</span>
          {related.map((b) => (
            <span
              key={b.id}
              className="text-[10px] px-1.5 py-0.5 rounded-full truncate"
              style={{
                background: 'var(--color-surface-subtle)',
                color: 'var(--color-text-primary)',
                maxWidth: 72,
              }}
            >
              {b.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function IndustryTopicEmergingRadar({
  topics = [],
  brands = [],
  limit = 5,
  onTopicClick,
}) {
  const { emerging, declining } = useMemo(() => {
    const scored = topics.map((t) => ({ topic: t, score: emergingScore(t) }));
    const emerging = scored
      .filter((x) => x.topic.isEmerging === true)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
    const declining = scored
      .filter((x) => x.topic.isEmerging !== true)
      .sort((a, b) => a.score - b.score)
      .slice(0, limit);
    return {
      emerging: emerging.map((x) => x.topic),
      declining: declining.map((x) => x.topic),
    };
  }, [topics, limit]);

  return (
    <div className="t-card p-3 space-y-3">
      <div>
        <div className="text-[13px] font-medium text-themed-primary">
          新兴 / 衰退 Topic 雷达
        </div>
        <div className="text-[11px] text-themed-muted mt-0.5">
          谁在崛起 / 谁在退潮 · 点击卡看详情
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <div
            className="text-[11px] font-medium flex items-center gap-1"
            style={{ color: 'var(--color-warning)' }}
          >
            <Sparkles size={12} />
            新兴 Top {limit}
          </div>
          {emerging.length === 0 ? (
            <div className="text-[11px] text-themed-muted py-4 text-center">
              当前无新兴 Topic
            </div>
          ) : (
            emerging.map((t) => (
              <TopicCard
                key={t.topicId}
                topic={t}
                brands={brands}
                type="emerging"
                onClick={() => onTopicClick && onTopicClick(t)}
              />
            ))
          )}
        </div>
        <div className="space-y-2">
          <div
            className="text-[11px] font-medium flex items-center gap-1 text-themed-muted"
          >
            <TrendingDown size={12} />
            衰退 Top {limit}
          </div>
          {declining.length === 0 ? (
            <div className="text-[11px] text-themed-muted py-4 text-center">
              当前无显著衰退 Topic
            </div>
          ) : (
            declining.map((t) => (
              <TopicCard
                key={t.topicId}
                topic={t}
                brands={brands}
                type="declining"
                onClick={() => onTopicClick && onTopicClick(t)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
