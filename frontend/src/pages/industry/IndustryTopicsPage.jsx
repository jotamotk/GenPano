/**
 * IndustryTopicsPage — /industry/topics (PRD §4.6.1g v3.2, 2026-04-21)
 * ──────────────────────────────────────────────────────────────────
 * 行业 Topic 格局 5-段式:
 *   ① Sticky Filter Bar (复用 BrandAnalysisFilterBar)
 *   ② Topics Hero (活跃 Topic / 新兴 Topic / 平均情感 — 3 卡)
 *   ③ 新兴 / 衰退 Topic 雷达 (2 列 Top 5 卡, 金边 / 灰边)
 *   ④ Topic × Intent 交叉矩阵 (Top 8 × 4 Intent 堆叠 100% 相对占比, 组件共享自 components/topics/)
 *   ⑤ Topic Detail Drawer (点击 ③/④ 任意 Topic → 600px 右抽屉)
 *
 * v3.2 (2026-04-21) 变更:
 *   - 删除原段 ③ Brand × Topic 覆盖热图 (IndustryTopicCoverageHeatmap): 数据语义与 Brand Mode
 *     Visibility 页 BrandTopicHeatmap (mentionRate 0-1 真实比值) 重复, 本页 brandTopicHits 0-100
 *     合成 ordinal 只是"相对位感", MVP mock 期两张图回答同一问题. 留 Visibility 那张更贴近
 *     用户"我在哪些 Topic 上强/弱"叙事.
 *   - 段 ④ Topic × Intent Matrix 组件从 components/industry/ 迁到 components/topics/ 以便 Brand Mode 复用 (决策详见 PRD §4.2.5 / CLAUDE.md 决策 #20 v3.2 补注).
 *
 * v3.1 (保留) 字段契约 (§4.6.1g.D 硬约束):
 *   - 禁 topic.title (→ topic.topicName)
 *   - 禁 topic.heat (→ topic.mentionCount, 且 UI 不再展示绝对数量)
 *   - 禁 topic.industryId / topic.categoryName (行业 Topic 不分品类)
 *   - 禁 typeof 宽松判断 isEmerging (严格 === true)
 *   - v3.1 新增: 禁以"热度 / 提及量"作为主视觉 (Scatter 已删除)
 *
 * §4.6.0a 边界: 不在 UI 出现 "本页只做 / 详情请进入 X".
 */
import React, { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useProject } from '../../contexts/ProjectContext';
import BrandAnalysisFilterBar from '../../components/filters/BrandAnalysisFilterBar';
import { useBrandAnalysisFilters } from '../../hooks/useBrandAnalysisFilters';

import IndustryTopicsHero from '../../components/industry/IndustryTopicsHero';
import IndustryTopicEmergingRadar from '../../components/industry/IndustryTopicEmergingRadar';
import TopicIntentMatrix from '../../components/topics/TopicIntentMatrix';
import IndustryTopicDetailDrawer from '../../components/industry/IndustryTopicDetailDrawer';

import { INDUSTRIES, BRANDS, INDUSTRY_TOPIC_HEATMAP } from '../../data/mock';

export default function IndustryTopicsPage() {
  const [searchParams] = useSearchParams();
  const { activeProject } = useProject();
  const { filters } = useBrandAnalysisFilters();
  void filters;

  const [selectedTopic, setSelectedTopic] = useState(null);

  /* Resolve industry: ?industryId= → activeProject.industryId → 'beauty' */
  const industryId =
    searchParams.get('industryId') || activeProject?.industryId || 'beauty';
  const industry =
    INDUSTRIES.find((i) => i.id === industryId) || INDUSTRIES[0];

  const industryBrands = BRANDS.filter((b) => b.industryId === industry.id)
    .length
    ? BRANDS.filter((b) => b.industryId === industry.id)
    : BRANDS;

  const primaryBrandId = activeProject?.primaryBrandId || null;

  const handleTopicClick = useCallback((topic) => {
    if (topic) setSelectedTopic(topic);
  }, []);
  const handleClose = useCallback(() => setSelectedTopic(null), []);

  return (
    <div className="space-y-3">
      {/* ── 段 ② Topics Hero (page banner) ── */}
      <IndustryTopicsHero
        industryName={`${industry.icon || ''} ${industry.name} Topic 格局`.trim()}
        heatmap={INDUSTRY_TOPIC_HEATMAP}
      />

      {/* ── 段 ① Filter bar (sticky, 复用 Brand Mode FilterBar) ── */}
      <BrandAnalysisFilterBar />

      {/* ── 段 ③ 新兴 / 衰退 Topic 雷达 ── */}
      <IndustryTopicEmergingRadar
        topics={INDUSTRY_TOPIC_HEATMAP}
        brands={industryBrands}
        limit={5}
        onTopicClick={handleTopicClick}
      />

      {/* ── 段 ④ Topic × Intent 交叉矩阵 (组件共享 Brand Mode) ── */}
      <TopicIntentMatrix
        topics={INDUSTRY_TOPIC_HEATMAP}
        limit={8}
        onTopicClick={handleTopicClick}
      />

      {/* ── 段 ⑤ Topic Detail Drawer (点击 ③/④ 触发) ── */}
      <IndustryTopicDetailDrawer
        open={selectedTopic != null}
        topic={selectedTopic}
        brands={industryBrands}
        primaryBrandId={primaryBrandId}
        onClose={handleClose}
      />
    </div>
  );
}
