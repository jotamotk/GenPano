/**
 * IndustryTopicDetailDrawer — PRD §4.6.1g §B 段 ⑥ (v3.1, 2026-04-20)
 * ────────────────────────────────────────────────────────────────────
 * 点击段 ③/④/⑤ 任意 Topic 弹出右侧抽屉 (600px, Framer Motion 滑入).
 * 内容:
 *   - Topic 名 + dimension tag (品类/品牌/产品, 启发式推断)
 *   - 3 大指标: avgSentiment / brandCoverage / primaryIntent
 *     (v3.1 删除"提及量": MVP mock 绝对量不科学, 只保留相对/比较型指标)
 *   - 前 3 引用域 (按 topicId hash 从本地小样本池合成, 不建新 mock)
 *   - 关联 Top 3 品牌 (统计 brandTopicHits 排前三)
 *   - CTA: 去 Brand Mode 看主品牌在此 Topic 表现 →
 *
 * 关闭: Esc / 点击遮罩 / 关闭按钮.
 */
import React, { useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ArrowRight, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  brandTopicHits,
  topicIntentBreakdown,
} from '../../lib/industry/statistics';

// 与 段 ⑥ 共用 Intent 配色 (chart-2 / 3 / 6 / 7)
const INTENT_META = {
  informational: { label: '信息型', color: 'var(--color-chart-2)' },
  commercial: { label: '商业型', color: 'var(--color-chart-3)' },
  transactional: { label: '交易型', color: 'var(--color-chart-6)' },
  navigational: { label: '导航型', color: 'var(--color-chart-7)' },
};

// 启发式 dimension 推断 (topic.dimension 字段若未来补齐则优先使用)
function inferDimension(topic) {
  if (topic?.dimension) return topic.dimension;
  const name = topic?.topicName || '';
  if (/品牌|集团|梗|KOL|达人/.test(name)) return '品牌';
  if (/产品|SKU|香水|口红|眼影|面霜|精华|粉底|洁面|包袋|风衣|外套|腕表/.test(name))
    return '产品';
  return '品类';
}

// 小样本权威域池 — 仅用于详情 Drawer 合成展示, 不落 mock (§G.1 合规)
const DOMAIN_POOL = [
  { domain: 'xiaohongshu.com', label: '小红书', tier: 3 },
  { domain: 'zhihu.com', label: '知乎', tier: 2 },
  { domain: 'weibo.com', label: '微博', tier: 3 },
  { domain: 'douyin.com', label: '抖音', tier: 3 },
  { domain: 'bilibili.com', label: '哔哩哔哩', tier: 3 },
  { domain: 'vogue.com.cn', label: 'Vogue 中国', tier: 2 },
  { domain: 'elle.com.cn', label: 'ELLE 中国', tier: 2 },
  { domain: 'harpersbazaar.cn', label: '时尚芭莎', tier: 2 },
  { domain: 'gq.com.cn', label: 'GQ 中国', tier: 2 },
  { domain: 'wikipedia.org', label: 'Wikipedia', tier: 2 },
  { domain: 'jingdaily.com', label: 'Jing Daily', tier: 2 },
  { domain: 'businessoffashion.com', label: 'BoF', tier: 2 },
];

function _hash(key) {
  let h = 0x811c9dc5;
  const s = String(key);
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h >>> 0;
}

function topicTopDomains(topic, n = 3) {
  if (!topic) return [];
  const seed = _hash(topic.topicId || topic.topicName);
  // 基于 seed 做 Fisher-Yates 稳定挑选
  const pool = [...DOMAIN_POOL];
  const picked = [];
  let s = seed;
  for (let i = 0; i < n && pool.length > 0; i += 1) {
    s = (s * 1664525 + 1013904223) >>> 0;
    const idx = s % pool.length;
    const item = pool.splice(idx, 1)[0];
    s = (s * 22695477 + 1) >>> 0;
    // 权重 30-95, 按挑选顺序递减
    const weight = 95 - i * 22 - (s % 12);
    picked.push({ ...item, weight: Math.max(30, weight) });
  }
  return picked;
}

function sentimentTone(s) {
  if (s >= 0.7) return 'var(--color-success)';
  if (s <= 0.4) return 'var(--color-danger)';
  return 'var(--color-warning)';
}

export default function IndustryTopicDetailDrawer({
  open,
  topic,
  brands = [],
  primaryBrandId = null,
  onClose,
}) {
  const navigate = useNavigate();

  // Esc 关闭
  useEffect(() => {
    if (!open) return undefined;
    const handler = (e) => {
      if (e.key === 'Escape' && onClose) onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  const data = useMemo(() => {
    if (!topic) return null;

    const dimension = inferDimension(topic);
    const hitsByBrand = brands
      .map((b) => ({ brand: b, hits: brandTopicHits(b, topic) }))
      .sort((a, b) => b.hits - a.hits);
    const relatedTop3 = hitsByBrand.slice(0, 3);
    const brandCoverage = hitsByBrand.filter((x) => x.hits >= 15).length;
    const intent = topicIntentBreakdown(topic);
    const domains = topicTopDomains(topic, 3);

    return {
      dimension,
      brandCoverage,
      intent,
      domains,
      relatedTop3,
    };
  }, [topic, brands]);

  const gotoBrandMode = () => {
    if (!primaryBrandId) {
      navigate('/brand/topics');
    } else {
      navigate(
        `/brand/topics?brandId=${primaryBrandId}&topicId=${topic?.topicId || ''}`
      );
    }
  };

  return (
    <AnimatePresence>
      {open && topic && data && (
        <>
          {/* 遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            onClick={onClose}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.32)',
              zIndex: 60,
            }}
          />
          {/* 抽屉 */}
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
            className="t-card p-0 flex flex-col"
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              height: '100vh',
              width: 600,
              maxWidth: '96vw',
              zIndex: 61,
              background: 'var(--color-surface)',
              borderLeft: '1px solid var(--color-border-subtle)',
              boxShadow: 'var(--shadow-elev-high)',
              overflowY: 'auto',
            }}
            role="dialog"
            aria-modal="true"
            aria-label={`Topic 详情: ${topic.topicName}`}
          >
            {/* Header */}
            <div
              className="flex items-start justify-between gap-3 px-5 py-4 sticky top-0"
              style={{
                background: 'var(--color-surface)',
                borderBottom: '1px solid var(--color-border-subtle)',
                zIndex: 2,
              }}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-full"
                    style={{
                      background: 'var(--color-surface-subtle)',
                      color: 'var(--color-text-muted)',
                    }}
                  >
                    {data.dimension}
                  </span>
                  {topic.isEmerging && (
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded-full"
                      style={{
                        background:
                          'color-mix(in srgb, var(--color-warning) 14%, transparent)',
                        color: 'var(--color-warning)',
                      }}
                    >
                      新兴 Topic
                    </span>
                  )}
                </div>
                <div className="text-[15px] font-semibold text-themed-primary mt-1.5 truncate">
                  {topic.topicName}
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1 rounded hover:bg-themed-subtle text-themed-muted"
                aria-label="关闭"
              >
                <X size={16} />
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-4 space-y-5">
              {/* 3 大指标 (v3.1 删除"提及量" — MVP mock 绝对量不科学) */}
              <div className="grid grid-cols-3 gap-2">
                <div className="t-card p-3">
                  <div className="text-[10px] text-themed-muted">平均情感</div>
                  <div
                    className="text-[18px] font-semibold tabular-nums mt-0.5"
                    style={{ color: sentimentTone(topic.avgSentiment) }}
                  >
                    {Math.round((topic.avgSentiment || 0) * 100)}%
                  </div>
                </div>
                <div className="t-card p-3">
                  <div className="text-[10px] text-themed-muted">品牌覆盖</div>
                  <div className="text-[18px] font-semibold text-themed-primary tabular-nums mt-0.5">
                    {data.brandCoverage}
                    <span className="text-[11px] text-themed-muted font-normal ml-0.5">
                      / {brands.length}
                    </span>
                  </div>
                </div>
                <div className="t-card p-3">
                  <div className="text-[10px] text-themed-muted">主 Intent</div>
                  <div
                    className="text-[13px] font-semibold tabular-nums mt-1"
                    style={{
                      color: INTENT_META[data.intent.dominant]?.color,
                    }}
                  >
                    {INTENT_META[data.intent.dominant]?.label || '—'}
                  </div>
                </div>
              </div>

              {/* Intent 分布条 */}
              <div>
                <div className="text-[11px] text-themed-muted mb-1.5">
                  Intent 分布
                </div>
                <div
                  className="flex overflow-hidden rounded-full"
                  style={{
                    height: 14,
                    background: 'var(--color-surface-subtle)',
                  }}
                >
                  {['informational', 'commercial', 'transactional', 'navigational'].map(
                    (k) => {
                      const pct = data.intent[k];
                      if (pct <= 0) return null;
                      return (
                        <div
                          key={k}
                          title={`${INTENT_META[k].label}: ${pct}%`}
                          style={{
                            width: `${pct}%`,
                            background: INTENT_META[k].color,
                          }}
                        />
                      );
                    }
                  )}
                </div>
                <div className="flex items-center justify-between mt-1.5 text-[10px] text-themed-muted tabular-nums">
                  {['informational', 'commercial', 'transactional', 'navigational'].map(
                    (k) => (
                      <span key={k} className="flex items-center gap-1">
                        <span
                          style={{
                            display: 'inline-block',
                            width: 8,
                            height: 8,
                            background: INTENT_META[k].color,
                            borderRadius: 2,
                          }}
                        />
                        <span>{INTENT_META[k].label.replace('型', '')}</span>
                        <span className="text-themed-muted">
                          {data.intent[k]}%
                        </span>
                      </span>
                    )
                  )}
                </div>
              </div>

              {/* 前 3 引用域 */}
              <div>
                <div className="text-[11px] text-themed-muted mb-2">
                  前 3 引用来源域
                </div>
                <div className="space-y-1.5">
                  {data.domains.map((d) => (
                    <div
                      key={d.domain}
                      className="flex items-center gap-2 px-2 py-1.5 rounded-card"
                      style={{
                        background: 'var(--color-surface-subtle)',
                      }}
                    >
                      <ExternalLink
                        size={12}
                        className="text-themed-muted flex-shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] text-themed-primary font-medium truncate">
                          {d.label}
                        </div>
                        <div className="text-[10px] text-themed-muted truncate">
                          {d.domain}
                        </div>
                      </div>
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded-full tabular-nums"
                        style={{
                          background: 'var(--color-surface)',
                          color: 'var(--color-text-muted)',
                        }}
                      >
                        T{d.tier}
                      </span>
                      <span className="text-[11px] text-themed-primary font-medium tabular-nums">
                        {d.weight}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 关联 Top 3 品牌 */}
              <div>
                <div className="text-[11px] text-themed-muted mb-2">
                  关联 Top 3 品牌
                </div>
                <div className="space-y-1.5">
                  {data.relatedTop3.map(({ brand, hits }, i) => {
                    const isPrimary = brand.id === primaryBrandId;
                    return (
                      <div
                        key={brand.id}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-card cursor-pointer hover:bg-themed-subtle"
                        style={
                          isPrimary
                            ? {
                                background:
                                  'color-mix(in srgb, var(--color-primary) 8%, transparent)',
                              }
                            : undefined
                        }
                        onClick={() => navigate(`/brand/overview?brandId=${brand.id}`)}
                      >
                        <span
                          className="text-[10px] font-semibold text-themed-muted tabular-nums"
                          style={{ minWidth: 18 }}
                        >
                          #{i + 1}
                        </span>
                        {isPrimary && (
                          <span
                            className="text-[10px] font-semibold"
                            style={{ color: 'var(--color-primary)' }}
                          >
                            ▲
                          </span>
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="text-[12px] text-themed-primary font-medium truncate">
                            {brand.name}
                          </div>
                          <div className="text-[10px] text-themed-muted truncate">
                            {brand.positioning || '—'}
                          </div>
                        </div>
                        <span className="text-[11px] text-themed-primary font-medium tabular-nums">
                          {hits}
                        </span>
                        <span className="text-[10px] text-themed-muted">强度</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Footer CTA */}
            <div
              className="mt-auto px-5 py-3 sticky bottom-0"
              style={{
                background: 'var(--color-surface)',
                borderTop: '1px solid var(--color-border-subtle)',
              }}
            >
              <button
                onClick={gotoBrandMode}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-card text-[12px] font-medium"
                style={{
                  background: 'var(--color-primary)',
                  color: '#fff',
                }}
              >
                去 Brand Mode 看主品牌在此 Topic 表现
                <ArrowRight size={14} />
              </button>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
