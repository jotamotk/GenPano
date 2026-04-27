import React, { useState } from 'react';
import { Badge, Button, Card, Tabs } from '../components/ui';
import { PanoRing, DonutChart, HorizontalBar, TrendChart } from '../components/charts';
import { BRANDS, SOV_DATA } from '../data/mock';
import { useNavigate } from 'react-router-dom';

export default function IndustryPage() {
  const navigate = useNavigate();
  const [showEmbedModal, setShowEmbedModal] = useState(false);
  const [trendTab, setTrendTab] = useState('30days');

  // Category distribution data for HorizontalBar — 单一主色 (HorizontalBar monochrome 模式统一渲染)
  // 视觉诉求: 让 value 的高低差异成为唯一视觉变量, 不要用 6 种颜色分散注意力
  const categories = [
    { name: '抗衰', value: 85 },
    { name: '美白', value: 72 },
    { name: '保湿', value: 68 },
    { name: '防晒', value: 61 },
    { name: '清洁', value: 54 },
    { name: '彩妆', value: 48 },
  ];

  // Industry trend data (30 days)
  const industryTrendData = Array.from({ length: 30 }, (_, i) => ({
    name: `${i + 1}`,
    avgPano: 62 + Math.sin(i / 5) * 8 + Math.random() * 3,
    topBrand: 78 + Math.sin(i / 4) * 5 + Math.random() * 2,
    myBrand: 72 + Math.sin(i / 6) * 6 + Math.random() * 4,
  }));

  const trendLines = [
    { key: 'topBrand', label: 'Top 品牌均分', color: '#0abb87' },
    { key: 'myBrand', label: '我的品牌', color: '#635bff' },
    { key: 'avgPano', label: '行业平均', color: '#8898aa', dashed: true, area: false },
  ];

  const trendTabs = [
    { id: '7days', label: '7天' },
    { id: '30days', label: '30天' },
    { id: '90days', label: '90天' },
  ];

  // Top brands for industry ranking (sorted by panoScore)
  const topBrands = [...BRANDS]
    .sort((a, b) => b.panoScore - a.panoScore)
    .slice(0, 8);

  return (
    <div className="space-y-8">
      {/* Top Row - Share of Voice and Category Distribution */}
      <div className="grid grid-cols-2 gap-6">
        {/* Left: Share of Voice — Donut 放大居中, 图例 2 列以容纳 Top 8+其他 */}
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-themed-primary mb-4">
            Share of Voice
          </h3>
          <div className="flex items-center gap-6">
            <div className="flex-shrink-0">
              <DonutChart segments={SOV_DATA} size={200} />
            </div>
            <div className="flex-1 grid grid-cols-2 gap-x-4 gap-y-2">
              {SOV_DATA.map((item) => (
                <div key={item.name} className="flex items-center gap-2 min-w-0">
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: item.color }}
                  />
                  <span className="text-xs text-themed-primary truncate flex-1">
                    {item.name}
                  </span>
                  <span className="text-xs font-semibold text-themed-primary tabular-nums">
                    {item.value}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Right: Popular Categories Topic Distribution */}
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-themed-primary mb-4">
            热门品类 Topic 分布
          </h3>
          <HorizontalBar data={categories} monochrome showLabels />
        </Card>
      </div>

      {/* Industry Trend Chart (PRD 4.6.1) */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-semibold text-themed-primary">行业趋势</h3>
          <Tabs tabs={trendTabs} active={trendTab} onChange={setTrendTab} />
        </div>
        <TrendChart
          data={trendTab === '7days' ? industryTrendData.slice(-7) : industryTrendData}
          lines={trendLines}
          height={220}
        />
      </Card>

      {/* Bottom: Industry PANO Score Ranking */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-sm font-semibold text-themed-primary">
            行业 PANO Score 排行榜
          </h3>
          <Button variant="secondary" size="sm" onClick={() => setShowEmbedModal(true)}>
            嵌入代码
          </Button>
        </div>

        {/* PRD §4.1.1b (rev 2026-04-16) + 知识图谱"放大胜利者"约束:
             Top 1 以 Hero 卡片跨整行, 2-8 名进入 4 列网格 (第 8 位落在第 2 行中间, 可接受).
             ?from=industry + entry_source=industry_row_cta — 6 枚举之一, 用于归因 /projects/new */}
        {topBrands.length > 0 && (() => {
          const [hero, ...rest] = topBrands;
          const heroChange = hero.change.startsWith('+');
          return (
            <div className="space-y-4">
              {/* Hero: Top 1 放大胜利者 — 横向布局, Ring 左, 品牌+指标右 */}
              <Card
                className="p-6 hover relative overflow-hidden"
                style={{
                  background: 'linear-gradient(135deg, var(--color-bg-card) 0%, var(--color-bg-badge) 100%)',
                  boxShadow: '0 8px 24px rgba(99,91,255,0.12)',
                  borderLeft: '4px solid var(--color-accent)',
                }}
                onClick={() =>
                  navigate(
                    `/brands/${hero.id}?from=industry&industryId=${hero.industryId || 'beauty'}&entry_source=industry_row_cta`,
                  )
                }
              >
                <div className="flex items-center gap-8">
                  {/* PanoRing 放大到 150, Top 1 应在 SoV/排行榜同时占据视觉中心 */}
                  <div className="flex-shrink-0">
                    <PanoRing score={hero.panoScore} size={150} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-2">
                      <Badge variant="accent" size="md">#1</Badge>
                      <Badge variant={heroChange ? 'green' : 'orange'} size="sm">
                        {hero.change}
                      </Badge>
                      <span className="text-xs text-themed-muted tracking-wider font-semibold">
                        行业领军
                      </span>
                    </div>
                    <h4 className="text-2xl font-bold text-themed-primary mb-4">
                      {hero.name}
                    </h4>
                    <div className="grid grid-cols-3 gap-4 max-w-xl">
                      <div>
                        <p className="text-xs text-themed-muted mb-1">提及率</p>
                        <p className="text-lg font-semibold text-themed-primary tabular-nums">
                          {hero.mentionRate}%
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-themed-muted mb-1">排名</p>
                        <p className="text-lg font-semibold text-themed-primary tabular-nums">
                          #{hero.ranking}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-themed-muted mb-1">情感</p>
                        <p className="text-lg font-semibold text-themed-primary tabular-nums">
                          {(hero.sentiment * 100).toFixed(0)}%
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </Card>

              {/* 其余 2-8 名: 4 列网格 */}
              <div className="grid grid-cols-4 gap-4">
                {rest.map((brand, idx) => (
                  <Card
                    key={brand.id}
                    className="p-5 flex flex-col items-center text-center hover relative"
                    onClick={() =>
                      navigate(
                        `/brands/${brand.id}?from=industry&industryId=${brand.industryId || 'beauty'}&entry_source=industry_row_cta`,
                      )
                    }
                  >
                    {/* Rank Badge */}
                    <div className="absolute top-4 left-4">
                      <Badge variant="accent" size="md">
                        #{idx + 2}
                      </Badge>
                    </div>

                    {/* PanoRing */}
                    <div className="my-4">
                      <PanoRing score={brand.panoScore} size={100} />
                    </div>

                    {/* Brand Name */}
                    <h4 className="text-sm font-semibold text-themed-primary mt-2">
                      {brand.name}
                    </h4>

                    {/* Change Badge */}
                    <Badge
                      variant={brand.change.startsWith('+') ? 'green' : 'orange'}
                      size="sm"
                      className="mt-3"
                    >
                      {brand.change}
                    </Badge>

                    {/* Key Metrics */}
                    <div className="mt-4 w-full pt-4 border-t border-themed text-left space-y-2">
                      <div className="flex justify-between text-xs">
                        <span className="text-themed-muted">提及率</span>
                        <span className="font-semibold text-themed-primary tabular-nums">
                          {brand.mentionRate}%
                        </span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-themed-muted">排名</span>
                        <span className="font-semibold text-themed-primary tabular-nums">
                          #{brand.ranking}
                        </span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-themed-muted">情感</span>
                        <span className="font-semibold text-themed-primary tabular-nums">
                          {(brand.sentiment * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          );
        })()}
      </Card>

      {/* Embed Code Modal (PRD 4.6.3) */}
      {showEmbedModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }}>
          <div className="bg-white rounded-xl shadow-2xl p-6 w-[560px] max-w-[90vw]" style={{ boxShadow: '0 25px 50px rgba(50,50,93,0.25)' }}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-base font-semibold text-themed-primary">嵌入行业排行榜</h3>
              <button onClick={() => setShowEmbedModal(false)} className="text-themed-muted hover:text-themed-primary text-lg">×</button>
            </div>
            <p className="text-sm text-themed-secondary mb-4">将行业 PANO Score 排行榜嵌入到博客、邮件或客户报告中。</p>
            <div className="rounded-lg border border-themed p-3 mb-4" style={{ background: 'var(--color-bg-badge)' }}>
              <code className="text-xs text-themed-secondary break-all leading-relaxed">
                {'<iframe src="https://genpano.com/embed/industry/beauty/leaderboard?theme=light" width="100%" height="400" frameborder="0"></iframe>'}
              </code>
            </div>
            <div className="flex items-center gap-3 mb-4">
              <span className="text-xs text-themed-muted">主题:</span>
              <button className="px-3 py-1 rounded text-xs font-medium border border-[var(--color-accent)] text-white" style={{ background: 'var(--color-accent)' }}>浅色</button>
              <button className="px-3 py-1 rounded text-xs font-medium border border-themed text-themed-muted">深色</button>
            </div>
            <div className="flex gap-3">
              <Button variant="primary" size="sm" className="flex-1">复制代码</Button>
              <Button variant="outline" size="sm" className="flex-1">预览</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
