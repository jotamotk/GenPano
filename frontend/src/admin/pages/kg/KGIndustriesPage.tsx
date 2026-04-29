import React, { useEffect, useRef } from 'react';
import { Graph } from '@antv/g6';

/**
 * Module C · KG Industries / 品类树
 *
 * AntV G6 v5 mini visualization. Applies the 8 pitfalls captured in
 * `feedback_genpano_g6_knowledge_graph.md`:
 *   1. radial layout (not force) — predictable arc, no settling jitter
 *   2. no hover-activate — opacity stays stable
 *   3. amplify-winner — focus node sized up
 *   4. shadowBlur explicit on base style
 *   5. external label — keep label outside node disk for short text
 *   6. autoFit container box
 *   7. single composer (one Graph instance, kept in ref)
 *   8. explicit opacity on every state (no defaults)
 *
 * Step 9 ships a 4-industry static tree; live data lands once the KG
 * Platform Layer (Session 1.5') is wired into Admin read-only API.
 */

const RAW = {
  nodes: [
    { id: 'root', data: { label: '行业根', kind: 'root' } },
    { id: 'ind-beauty', data: { label: '美妆个护', kind: 'industry' } },
    { id: 'ind-luxury', data: { label: '奢侈品', kind: 'industry' } },
    { id: 'ind-food', data: { label: '食品饮料', kind: 'industry' } },
    { id: 'ind-fashion', data: { label: '服装时尚', kind: 'industry' } },
    { id: 'cat-skincare', data: { label: '护肤', kind: 'category' } },
    { id: 'cat-makeup', data: { label: '彩妆', kind: 'category' } },
    { id: 'cat-fragrance', data: { label: '香水', kind: 'category' } },
    { id: 'cat-watch', data: { label: '腕表', kind: 'category' } },
    { id: 'cat-bag', data: { label: '箱包', kind: 'category' } },
    { id: 'cat-beverage', data: { label: '饮料', kind: 'category' } },
    { id: 'cat-snack', data: { label: '零食', kind: 'category' } },
    { id: 'cat-apparel', data: { label: '服装', kind: 'category' } },
    { id: 'cat-shoes', data: { label: '鞋履', kind: 'category' } },
  ],
  edges: [
    { id: 'e1', source: 'root', target: 'ind-beauty' },
    { id: 'e2', source: 'root', target: 'ind-luxury' },
    { id: 'e3', source: 'root', target: 'ind-food' },
    { id: 'e4', source: 'root', target: 'ind-fashion' },
    { id: 'e5', source: 'ind-beauty', target: 'cat-skincare' },
    { id: 'e6', source: 'ind-beauty', target: 'cat-makeup' },
    { id: 'e7', source: 'ind-beauty', target: 'cat-fragrance' },
    { id: 'e8', source: 'ind-luxury', target: 'cat-watch' },
    { id: 'e9', source: 'ind-luxury', target: 'cat-bag' },
    { id: 'e10', source: 'ind-food', target: 'cat-beverage' },
    { id: 'e11', source: 'ind-food', target: 'cat-snack' },
    { id: 'e12', source: 'ind-fashion', target: 'cat-apparel' },
    { id: 'e13', source: 'ind-fashion', target: 'cat-shoes' },
  ],
};

function colorForKind(kind: string): string {
  if (kind === 'root') return '#1e293b';
  if (kind === 'industry') return '#0ea5e9';
  return '#10b981';
}

function sizeForKind(kind: string): number {
  if (kind === 'root') return 36;
  if (kind === 'industry') return 28;
  return 18;
}

export default function KGIndustriesPage() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (graphRef.current) return; // pitfall 7: single composer

    const graph = new Graph({
      container: el,
      autoFit: 'view', // pitfall 6
      layout: { type: 'radial', unitRadius: 110, focusNode: 'root' }, // pitfall 1
      data: RAW,
      node: {
        style: (model) => {
          const kind = (model?.data?.kind as string) ?? 'category';
          const isFocus = model?.id === 'root';
          return {
            size: isFocus ? sizeForKind(kind) + 8 : sizeForKind(kind), // pitfall 3
            fill: colorForKind(kind),
            stroke: '#fff',
            lineWidth: 1.5,
            opacity: 1, // pitfall 8 — explicit
            labelOpacity: 1, // pitfall 8
            labelText: (model?.data?.label as string) ?? '',
            labelPlacement: 'bottom', // pitfall 5 — external label
            labelOffsetY: 6,
            labelFontSize: 11,
            labelFill: '#1e293b',
            shadowBlur: 0, // pitfall 4 — explicit zero, not undefined
          };
        },
      },
      edge: {
        style: {
          stroke: '#cbd5e1',
          lineWidth: 1,
          opacity: 0.7, // pitfall 8
        },
      },
      behaviors: ['drag-canvas', 'zoom-canvas'], // pitfall 2 — NO 'hover-activate'
    });

    graph
      .render()
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.warn('[admin-kg] G6 render failed', err);
      });
    graphRef.current = graph;

    return () => {
      try {
        graph.destroy();
      } catch {
        /* no-op */
      }
      graphRef.current = null;
    };
  }, []);

  return (
    <div className="max-w-[1200px]">
      <div className="mb-3">
        <h1
          className="text-xl font-bold"
          style={{ color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}
        >
          行业 / 品类树
        </h1>
        <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
          ADMIN_PRD §4.3.1 · AntV G6 v5 radial layout. Step 9 静态 demo 树, 真实数据接入待 Session 1.5' Admin 只读 API.
        </p>
      </div>
      <div
        className="rounded p-2"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-subtle)',
          height: 540,
        }}
      >
        <div ref={containerRef} className="w-full h-full" />
      </div>
    </div>
  );
}
