import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Graph } from '@antv/g6';
import { Card } from '../components/ui';
import { BRANDS as GLOBAL_BRANDS } from '../data/mock';

/* ══════════════════════════════════════════════════════════════
   Knowledge Graph — AntV G6 force layout
   PRD 4.0.1a: Industry → Category → Brand → Product + 关系边
   PRD 4.1.1b (rev 2026-04-16): 行业探索视图 = 直达 Brand Overview.
     ⚠️ 开发者约束 (不作为 UI 文案 — PRD §4.6.0a):
     - 品牌节点点击 / 列表行点击 → navigate('/brands/:id?from=industry')
     - 不再展示 "Brand Detail Panel" 侧栏 (双入口反模式).
     - 列表行不保留 "创建监测项目" 按钮; 监控动作由 Brand Detail 顶栏的
       <WatchBrandButton> 6 状态机统一承担.
   颜色全部走 design tokens (frontend/src/index.css)
   ══════════════════════════════════════════════════════════════ */

// ── Mock 数据 (美妆个护行业) ──────────────────────────────────
const RAW_NODES = [
  { id: 'ind-beauty', label: '美妆个护', type: 'industry' },

  { id: 'cat-skincare',  label: '护肤', type: 'category', level: 1 },
  { id: 'cat-makeup',    label: '彩妆', type: 'category', level: 1 },
  { id: 'cat-fragrance', label: '香水', type: 'category', level: 1 },
  { id: 'cat-serum',     label: '精华', type: 'category', level: 2 },
  { id: 'cat-cream',     label: '面霜', type: 'category', level: 2 },
  { id: 'cat-sunscreen', label: '防晒', type: 'category', level: 2 },
  { id: 'cat-foundation',label: '粉底', type: 'category', level: 2 },
  { id: 'cat-lipstick',  label: '口红', type: 'category', level: 2 },

  { id: 'br-estee',   label: '雅诗兰黛', type: 'brand', group: 'Estée Lauder', panoScore: 82 },
  { id: 'br-lancome', label: '兰蔻',     type: 'brand', group: "L'Oréal",      panoScore: 78 },
  { id: 'br-lamer',   label: '海蓝之谜', type: 'brand', group: 'Estée Lauder', panoScore: 88 },
  { id: 'br-chanel',  label: '香奈儿',   type: 'brand',                         panoScore: 85 },
  { id: 'br-sk2',     label: 'SK-II',    type: 'brand', group: 'P&G',          panoScore: 75 },
  { id: 'br-dior',    label: '迪奥',     type: 'brand', group: 'LVMH',         panoScore: 80 },
  { id: 'br-proya',   label: '珀莱雅',   type: 'brand',                         panoScore: 71 },
  { id: 'br-winona',  label: '薇诺娜',   type: 'brand',                         panoScore: 68 },

  { id: 'pr-anr',              label: '小棕瓶精华',   type: 'product', brand: 'br-estee'   },
  { id: 'pr-genifique',        label: '小黑瓶精华',   type: 'product', brand: 'br-lancome' },
  { id: 'pr-lamer-cream',      label: '经典面霜',     type: 'product', brand: 'br-lamer'   },
  { id: 'pr-pitera',           label: '神仙水',       type: 'product', brand: 'br-sk2'     },
  { id: 'pr-chanel-n5',        label: 'N°5 香水',     type: 'product', brand: 'br-chanel'  },
  { id: 'pr-dior-foundation',  label: '锁妆粉底液',   type: 'product', brand: 'br-dior'    },
  { id: 'pr-dior-lip',         label: '烈艳蓝金唇膏', type: 'product', brand: 'br-dior'    },
  { id: 'pr-proya-serum',      label: '双抗精华',     type: 'product', brand: 'br-proya'   },
  { id: 'pr-estee-cream',      label: '多效面霜',     type: 'product', brand: 'br-estee'   },
  { id: 'pr-winona-cream',     label: '舒敏面霜',     type: 'product', brand: 'br-winona'  },
];

const RAW_LINKS = [
  { source: 'cat-skincare',  target: 'ind-beauty',   type: 'BELONGS_TO' },
  { source: 'cat-makeup',    target: 'ind-beauty',   type: 'BELONGS_TO' },
  { source: 'cat-fragrance', target: 'ind-beauty',   type: 'BELONGS_TO' },
  { source: 'cat-serum',     target: 'cat-skincare', type: 'BELONGS_TO' },
  { source: 'cat-cream',     target: 'cat-skincare', type: 'BELONGS_TO' },
  { source: 'cat-sunscreen', target: 'cat-skincare', type: 'BELONGS_TO' },
  { source: 'cat-foundation',target: 'cat-makeup',   type: 'BELONGS_TO' },
  { source: 'cat-lipstick',  target: 'cat-makeup',   type: 'BELONGS_TO' },

  { source: 'br-estee',   target: 'cat-serum',      type: 'IN_CATEGORY' },
  { source: 'br-lancome', target: 'cat-serum',      type: 'IN_CATEGORY' },
  { source: 'br-lamer',   target: 'cat-cream',      type: 'IN_CATEGORY' },
  { source: 'br-sk2',     target: 'cat-serum',      type: 'IN_CATEGORY' },
  { source: 'br-chanel',  target: 'cat-fragrance',  type: 'IN_CATEGORY' },
  { source: 'br-dior',    target: 'cat-foundation', type: 'IN_CATEGORY' },
  { source: 'br-dior',    target: 'cat-lipstick',   type: 'IN_CATEGORY' },
  { source: 'br-proya',   target: 'cat-serum',      type: 'IN_CATEGORY' },
  { source: 'br-winona',  target: 'cat-cream',      type: 'IN_CATEGORY' },

  { source: 'br-estee',   target: 'br-lancome', type: 'COMPETES_WITH' },
  { source: 'br-estee',   target: 'br-sk2',     type: 'COMPETES_WITH' },
  { source: 'br-lancome', target: 'br-sk2',     type: 'COMPETES_WITH' },
  { source: 'br-chanel',  target: 'br-dior',    type: 'COMPETES_WITH' },
  { source: 'br-proya',   target: 'br-winona',  type: 'COMPETES_WITH' },

  { source: 'br-estee',   target: 'br-lamer',   type: 'SAME_GROUP' },

  { source: 'pr-anr',              target: 'br-estee',   type: 'HAS_PRODUCT' },
  { source: 'pr-genifique',        target: 'br-lancome', type: 'HAS_PRODUCT' },
  { source: 'pr-lamer-cream',      target: 'br-lamer',   type: 'HAS_PRODUCT' },
  { source: 'pr-pitera',           target: 'br-sk2',     type: 'HAS_PRODUCT' },
  { source: 'pr-chanel-n5',        target: 'br-chanel',  type: 'HAS_PRODUCT' },
  { source: 'pr-dior-foundation',  target: 'br-dior',    type: 'HAS_PRODUCT' },
  { source: 'pr-dior-lip',         target: 'br-dior',    type: 'HAS_PRODUCT' },
  { source: 'pr-proya-serum',      target: 'br-proya',   type: 'HAS_PRODUCT' },
  { source: 'pr-estee-cream',      target: 'br-estee',   type: 'HAS_PRODUCT' },
  { source: 'pr-winona-cream',     target: 'br-winona',  type: 'HAS_PRODUCT' },

  { source: 'pr-anr', target: 'pr-genifique', type: 'COMPETES_WITH' },
  { source: 'pr-anr', target: 'pr-pitera',    type: 'COMPETES_WITH' },

  { source: 'pr-proya-serum', target: 'pr-anr',         type: 'BUDGET_ALT_OF' },
  { source: 'pr-anr',         target: 'pr-lamer-cream', type: 'UPGRADES_TO'   },
  { source: 'pr-anr',         target: 'pr-estee-cream', type: 'PAIRS_WITH'    },
];

// ── 图谱节点 → 全局 BRANDS.id 映射 ──────────────────────────
// 知识图谱内部 id (br-xxx) 是为可视化布局服务, 全局 BRANDS 用业务 id.
// 点击品牌节点跳转 /brands/:id 时通过此表解析.
// 缺省 (例: 珀莱雅/薇诺娜尚未进入 mock BRANDS) → null, 点击不跳转.
const GRAPH_BRAND_TO_GLOBAL_ID = {
  'br-estee':   'estee-lauder',
  'br-lancome': 'lancome',
  'br-lamer':   'la-mer',
  'br-chanel':  'chanel',
  'br-sk2':     'sk-ii',
  'br-dior':    'dior',
  // 未进入 mock BRANDS 的品牌点击不跳转 (后续 mock 扩展时填上)
  'br-proya':   null,
  'br-winona':  null,
};

function resolveGlobalBrandId(graphNodeId) {
  if (!graphNodeId) return null;
  if (Object.prototype.hasOwnProperty.call(GRAPH_BRAND_TO_GLOBAL_ID, graphNodeId)) {
    return GRAPH_BRAND_TO_GLOBAL_ID[graphNodeId];
  }
  // Fallback: try matching by Chinese label against GLOBAL_BRANDS.name
  const node = RAW_NODES.find((n) => n.id === graphNodeId);
  if (!node) return null;
  const hit = GLOBAL_BRANDS.find((b) => b.name === node.label || b.nameEn === node.label);
  return hit?.id || null;
}

// ── Token-driven 视觉配置 (颜色在 mount 时从 CSS 变量解析) ──
// token 字段是 CSS 变量名，运行时读 getComputedStyle 拿值给 G6
// labelInside: industry 字在圆内（白字），其它节点 label 放在节点下方（深色字）
const NODE_TYPE_CFG = {
  industry: { token: '--color-accent',  size: 64, font: 13, weight: 700, labelInside: true  },
  category: { token: '--color-chart-3', size: 36, font: 12, weight: 600, labelInside: false },
  brand:    { token: '--color-chart-7', size: 44, font: 12, weight: 700, labelInside: false },
  product:  { token: '--color-chart-2', size: 26, font: 11, weight: 500, labelInside: false },
};

const EDGE_TYPE_CFG = {
  BELONGS_TO:    { token: '--color-border-strong', dash: [4, 3], width: 1, opacity: 0.45 },
  IN_CATEGORY:   { token: '--color-chart-3',       dash: [3, 2], width: 1, opacity: 0.35 },
  HAS_PRODUCT:   { token: '--color-accent-2',      dash: [3, 2], width: 1, opacity: 0.35 },
  COMPETES_WITH: { token: '--color-danger',                       width: 2, opacity: 0.75 },
  SAME_GROUP:    { token: '--color-warning',       dash: [6, 3], width: 2, opacity: 0.65 },
  BUDGET_ALT_OF: { token: '--color-success',                      width: 2, opacity: 0.75 },
  UPGRADES_TO:   { token: '--color-chart-3',                      width: 2, opacity: 0.75, arrow: true },
  PAIRS_WITH:    { token: '--color-accent-2',      dash: [5, 3], width: 2, opacity: 0.65 },
};

const RELATION_LABELS = {
  COMPETES_WITH: '竞争',
  SAME_GROUP:    '同集团',
  BUDGET_ALT_OF: '平替',
  UPGRADES_TO:   '升级',
  PAIRS_WITH:    '搭配',
};

const TYPE_LABELS = { industry: '行业', category: '品类', brand: '品牌', product: '产品' };

// 在 mount 时读 CSS 变量，避免每次 render 都查 DOM
function resolveTokens() {
  const root = getComputedStyle(document.documentElement);
  const get = (name) => root.getPropertyValue(name).trim() || '#999';
  const nodes = {};
  Object.entries(NODE_TYPE_CFG).forEach(([k, v]) => { nodes[k] = { ...v, color: get(v.token) }; });
  const edges = {};
  Object.entries(EDGE_TYPE_CFG).forEach(([k, v]) => { edges[k] = { ...v, color: get(v.token) }; });
  return { nodes, edges, textPrimary: get('--color-text-primary'), bgCard: get('--color-bg-card') };
}

// ── G6 Graph Component ───────────────────────────────────────
function G6Graph({ width, height, onNodeSelect, selectedId, filterType }) {
  const containerRef = useRef(null);
  const graphRef = useRef(null);
  const tokensRef = useRef(null);
  // hover handler 里需要读最新的 selectedId / filterType，但不能让它们重建 graph
  const selectedIdRef = useRef(selectedId);
  const filterTypeRef = useRef(filterType);
  useEffect(() => { selectedIdRef.current = selectedId; }, [selectedId]);
  useEffect(() => { filterTypeRef.current = filterType; }, [filterType]);
  // 统一状态写入入口 (hoist 到组件 scope 让 reactive effect 可调)
  // 所有 setElementState 调用都必须经过这个函数 / hover 的组合函数,
  // 否则多个 useEffect 会互相覆盖, 产生 "选中后状态就乱了" 的 bug.
  const applyBaseStatesRef = useRef(null);
  // 标记鼠标当前是否悬停在某节点上, 避免 selected/filter 变化时把 hover 状态抹掉
  const hoveringNodeIdRef = useRef(null);

  // 预算每个节点的邻居（只算一次）
  const neighborsRef = useRef(null);
  if (neighborsRef.current === null) {
    const m = new Map();
    RAW_NODES.forEach((n) => m.set(n.id, new Set([n.id])));
    RAW_LINKS.forEach((l) => {
      m.get(l.source)?.add(l.target);
      m.get(l.target)?.add(l.source);
    });
    neighborsRef.current = m;
  }

  // Build / mount once per width-height change
  useEffect(() => {
    if (!containerRef.current || !width || !height) return;

    const tokens = resolveTokens();
    tokensRef.current = tokens;

    const data = {
      nodes: RAW_NODES.map((n) => ({
        id: n.id,
        data: n,
      })),
      edges: RAW_LINKS.map((l, i) => ({
        id: `e-${i}`,
        source: l.source,
        target: l.target,
        data: l,
      })),
    };

    const graph = new Graph({
      container: containerRef.current,
      width,
      height,
      data,
      layout: {
        // Radial: industry 居中，按 BFS 跳数一圈一圈放外层
        // 比 d3-force 更适合明确的层级结构（ind→cat→brand→product）
        type: 'radial',
        center: [width / 2, height / 2],
        focusNode: 'ind-beauty',
        unitRadius: 130,
        preventOverlap: true,
        nodeSize: (node) => (tokens.nodes[node.data?.type]?.size || 32) + 18,
        nodeSpacing: 24,
        maxPreventOverlapIteration: 800,
        strictRadial: false,   // 允许节点小幅切向调整以避免重叠
        sortBy: 'data',        // 同一圈按数据顺序稳定排列
      },
      node: {
        type: 'circle',
        style: {
          fill: (d) => tokens.nodes[d.data.type]?.color || '#999',
          size: (d) => tokens.nodes[d.data.type]?.size || 32,
          stroke: tokens.bgCard,
          lineWidth: 1.5,
          cursor: 'pointer',
          // ⚠️ 必须显式写 opacity/labelOpacity, 否则 G6 v5 从 inactive(0.22)
          // 清除状态时不知道回归目标值, 节点会"卡"在半透明
          opacity: 1,
          labelOpacity: 1,
          shadowBlur: 0,
          // label
          labelText: (d) => d.data.label,
          labelFontSize: (d) => tokens.nodes[d.data.type]?.font || 11,
          labelFontWeight: (d) => tokens.nodes[d.data.type]?.weight || 600,
          labelPlacement: (d) => (tokens.nodes[d.data.type]?.labelInside ? 'center' : 'bottom'),
          labelTextAlign: 'center',
          labelFill: (d) => (tokens.nodes[d.data.type]?.labelInside ? '#fff' : tokens.textPrimary),
          labelOffsetY: (d) => (tokens.nodes[d.data.type]?.labelInside ? 0 : 4),
          labelBackground: (d) => !tokens.nodes[d.data.type]?.labelInside,
          labelBackgroundFill: tokens.bgCard,
          labelBackgroundOpacity: 0.92,
          labelBackgroundRadius: 3,
          labelBackgroundPadding: [1, 5],
        },
        state: {
          // 视觉策略：active/selected 主动放大跳出，inactive 安静退后
          active: {
            opacity: 1,
            labelOpacity: 1,
            size: (d) => Math.round((tokens.nodes[d.data.type]?.size || 32) * 1.18),
            lineWidth: 3,
            stroke: '#fff',
            shadowColor: (d) => tokens.nodes[d.data.type]?.color || '#999',
            shadowBlur: 14,
            labelFontWeight: 700,
            labelFontSize: (d) => (tokens.nodes[d.data.type]?.font || 11) + 1,
          },
          selected: {
            opacity: 1,
            labelOpacity: 1,
            size: (d) => Math.round((tokens.nodes[d.data.type]?.size || 32) * 1.24),
            lineWidth: 4,
            stroke: '#fff',
            shadowColor: (d) => tokens.nodes[d.data.type]?.color || '#999',
            shadowBlur: 22,
            labelFontWeight: 800,
            labelFontSize: (d) => (tokens.nodes[d.data.type]?.font || 11) + 2,
          },
          inactive: {
            opacity: 0.22,
            labelOpacity: 0.12,
          },
        },
      },
      edge: {
        type: 'line',
        style: {
          stroke: (d) => tokens.edges[d.data.type]?.color || '#999',
          lineWidth: (d) => tokens.edges[d.data.type]?.width || 1,
          lineDash: (d) => tokens.edges[d.data.type]?.dash || [],
          opacity: (d) => tokens.edges[d.data.type]?.opacity || 0.4,
          endArrow: (d) => !!tokens.edges[d.data.type]?.arrow,
          endArrowSize: 6,
          endArrowFill: (d) => tokens.edges[d.data.type]?.color || '#999',
          // hover label (off by default)
          labelText: (d) => RELATION_LABELS[d.data.type] || '',
          labelFontSize: 9,
          labelFontWeight: 500,
          labelFill: (d) => tokens.edges[d.data.type]?.color || '#999',
          labelBackground: true,
          labelBackgroundFill: tokens.bgCard,
          labelBackgroundOpacity: 0.95,
          labelBackgroundLineWidth: 0.5,
          labelBackgroundStroke: (d) => tokens.edges[d.data.type]?.color || '#999',
          labelBackgroundRadius: 4,
          labelBackgroundPadding: [2, 5],
          labelOpacity: 0,
        },
        state: {
          active: {
            opacity: 1,
            lineWidth: (d) => (tokens.edges[d.data.type]?.width || 1) + 1.5,
            labelOpacity: 1,
          },
          inactive: {
            opacity: 0.06,
            labelOpacity: 0,
          },
        },
      },
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        'drag-element',
        // 不用 G6 内置的 hover-activate（v5 中鼠标快速移出 canvas 不触发 leave）
        // 改用下面手写的 pointerenter/leave 完全控制
      ],
      animation: { duration: 280 },
    });

    graphRef.current = graph;
    graph.render();

    // Radial 是确定性布局，render 后就有最终位置，fit 一次即可
    const fitTimer = setTimeout(() => {
      try {
        if (!graph.destroyed) graph.fitView({ padding: [40, 60, 40, 60], rules: { ratioRule: 'min' } });
      } catch (e) { /* noop */ }
    }, 250);

    // 统一状态组合: 根据 {selectedId, filterType, hoveringNodeId} 三个维度,
    // 一次性为所有 **节点 + 边** 计算最终 state, 避免多路径竞争写入.
    // 规则:
    //   hover 时: 邻居节点 active / 其余 inactive; 直连边 active / 其余 inactive
    //   选中时 (无 hover): selected 节点 selected; 直连边 active; 其余默认 (或被 filter dim)
    //   filter 时: 匹配节点/边默认; 不匹配 inactive
    const composeAndApply = () => {
      if (graph.destroyed) return;
      const sel = selectedIdRef.current;
      const ft = filterTypeRef.current;
      const hovered = hoveringNodeIdRef.current;
      const allNodes = graph.getNodeData();
      const allEdges = graph.getEdgeData();
      const states = {};

      if (hovered) {
        // ── Hover 路径: 邻居高亮, 其余 dim ──
        const nb = neighborsRef.current.get(hovered) || new Set([hovered]);
        allNodes.forEach((n) => {
          const isSelected = sel && n.id === sel;
          if (nb.has(n.id)) {
            states[n.id] = isSelected ? ['selected', 'active'] : 'active';
          } else {
            states[n.id] = 'inactive';
          }
        });
        // 边: 至少一端是 hovered 节点 → active, 否则 inactive
        allEdges.forEach((e) => {
          const touchesHovered = e.source === hovered || e.target === hovered;
          states[e.id] = touchesHovered ? 'active' : 'inactive';
        });
      } else if (sel) {
        // ── 选中路径 (无 hover): 选中节点突出, 直连边高亮 ──
        const nb = neighborsRef.current.get(sel) || new Set([sel]);
        allNodes.forEach((n) => {
          const isSelected = n.id === sel;
          const dimmedByFilter = ft && n.data.type !== ft;
          if (isSelected) states[n.id] = 'selected';
          else if (dimmedByFilter) states[n.id] = 'inactive';
          else states[n.id] = [];
        });
        // 边: 至少一端是选中节点 → active, 两端都被 filter 排除 → inactive, 否则默认
        allEdges.forEach((e) => {
          const touchesSel = e.source === sel || e.target === sel;
          if (touchesSel) {
            states[e.id] = 'active';
          } else if (ft) {
            // filter 模式: 两端有任一不匹配 → dim
            const srcNode = allNodes.find((n) => n.id === e.source);
            const tgtNode = allNodes.find((n) => n.id === e.target);
            const srcMatch = srcNode && srcNode.data.type === ft;
            const tgtMatch = tgtNode && tgtNode.data.type === ft;
            states[e.id] = (srcMatch && tgtMatch) ? [] : 'inactive';
          } else {
            states[e.id] = [];
          }
        });
      } else if (ft) {
        // ── 仅 Filter 路径 ──
        allNodes.forEach((n) => {
          states[n.id] = n.data.type === ft ? [] : 'inactive';
        });
        allEdges.forEach((e) => {
          const srcNode = allNodes.find((n) => n.id === e.source);
          const tgtNode = allNodes.find((n) => n.id === e.target);
          const srcMatch = srcNode && srcNode.data.type === ft;
          const tgtMatch = tgtNode && tgtNode.data.type === ft;
          states[e.id] = (srcMatch && tgtMatch) ? [] : 'inactive';
        });
      } else {
        // ── 空闲: 全部恢复默认 ──
        allNodes.forEach((n) => { states[n.id] = []; });
        allEdges.forEach((e) => { states[e.id] = []; });
      }

      try { graph.setElementState(states); } catch (e) { /* noop */ }
    };
    applyBaseStatesRef.current = composeAndApply;

    // Click → select node, click empty canvas → deselect
    graph.on('node:click', (e) => {
      const d = graph.getNodeData(e.target.id);
      onNodeSelect?.(d?.data || null);
    });
    graph.on('canvas:click', () => onNodeSelect?.(null));

    // Hover: 只更新 hoveringNodeIdRef, 让 composeAndApply 生成完整状态
    graph.on('node:pointerenter', (e) => {
      if (graph.destroyed) return;
      hoveringNodeIdRef.current = e.target.id;
      composeAndApply();
    });

    const clearHover = () => {
      if (graph.destroyed) return;
      if (hoveringNodeIdRef.current === null) return;
      hoveringNodeIdRef.current = null;
      composeAndApply();
    };

    // 离开节点 / 离开画布 / 窗口失焦 → 清 hover 后恢复基础态
    graph.on('node:pointerleave', clearHover);
    graph.on('canvas:pointerleave', clearHover);
    graph.on('canvas:pointerout',   clearHover);

    // 兜底：DOM 容器的 mouseleave（G6 内部事件可能在某些边界情况下不触发）
    const onContainerLeave = () => clearHover();
    containerRef.current?.addEventListener('mouseleave', onContainerLeave);

    // 把 cleanup 的 listener 引用挂到 graph 上方便 useEffect cleanup 取
    graph.__containerLeaveHandler = onContainerLeave;

    return () => {
      clearTimeout(fitTimer);
      try { containerRef.current?.removeEventListener('mouseleave', graph.__containerLeaveHandler); } catch (e) { /* noop */ }
      applyBaseStatesRef.current = null;
      hoveringNodeIdRef.current = null;
      graph.destroy();
      graphRef.current = null;
    };
  }, [width, height, onNodeSelect]);

  // 统一 reactive 入口: selectedId / filterType 任一变化 → 重新组合状态
  // (不在这里单独调 setElementState, 避免与 hover 竞争)
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || graph.destroyed) return;
    applyBaseStatesRef.current?.();
  }, [selectedId, filterType]);

  return <div ref={containerRef} className="w-full h-full" />;
}

// ── 详情面板已移除 (PRD §4.1.1b rev 2026-04-16) —
//   品牌节点点击直达 /brands/:id, 不再有侧栏 Brand Detail Panel.
//   非品牌节点 (industry/category/product) 维持选中视觉, 不打开任何面板.

// ── List View (PRD 4.1.1b ② 列表视图) ────────────────────────
// 行点击 → 直达 /brands/:id (PRD §4.1.1b rev 2026-04-16). 不再展开行内
// 详情, 不再提供 "创建监测项目" 按钮 — 监控动作由 Brand Detail 顶栏的
// <WatchBrandButton> 6 状态机统一承担.
function BrandListView({ onBrandClick }) {
  const [sortKey, setSortKey] = useState('panoScore');
  const [sortDir, setSortDir] = useState('desc');
  const [searchTerm, setSearchTerm] = useState('');

  const brands = RAW_NODES
    .filter((n) => n.type === 'brand')
    .map((n) => ({
      ...n,
      panoScore: n.panoScore || 0,
      group: n.group || '—',
      categories: RAW_LINKS
        .filter((l) => l.source === n.id && l.type === 'IN_CATEGORY')
        .map((l) => RAW_NODES.find((nn) => nn.id === l.target)?.label)
        .filter(Boolean),
      products: RAW_NODES.filter((p) => p.type === 'product' && p.brand === n.id),
      competitors: RAW_LINKS
        .filter((l) => l.type === 'COMPETES_WITH' && (l.source === n.id || l.target === n.id))
        .map((l) => {
          const otherId = l.source === n.id ? l.target : l.source;
          return RAW_NODES.find((nn) => nn.id === otherId)?.label;
        })
        .filter(Boolean),
    }));

  const filtered = brands.filter(
    (b) => !searchTerm || b.label.toLowerCase().includes(searchTerm.toLowerCase())
  );
  const sorted = [...filtered].sort((a, b) => {
    const aVal = a[sortKey] ?? 0;
    const bVal = b[sortKey] ?? 0;
    return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
  });

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortIcon = ({ active, dir }) => (
    <span className="ml-1 text-[10px]" style={{ opacity: active ? 1 : 0.3 }}>
      {active && dir === 'asc' ? '▲' : '▼'}
    </span>
  );

  return (
    <div className="space-y-3 h-full flex flex-col">
      {/* Search & filter bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <input
            type="text"
            placeholder="搜索品牌..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="t-input w-full pl-9 pr-4 py-2 text-sm"
          />
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-themed-muted"
            fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}
          >
            <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
          </svg>
        </div>
        <span className="text-xs text-themed-muted">
          共 {sorted.length} 个品牌
        </span>
      </div>

      {/* Table — row click 直达 /brands/:id, 不再展开行内详情 */}
      <Card className="flex-1 overflow-auto p-0">
        <table className="t-table w-full">
          <thead>
            <tr>
              <th>品牌</th>
              <th>品类</th>
              <th>集团</th>
              <th className="cursor-pointer select-none" onClick={() => toggleSort('panoScore')}>
                PANO Score <SortIcon active={sortKey === 'panoScore'} dir={sortDir} />
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((brand) => (
              <tr
                key={brand.id}
                className="cursor-pointer hover:bg-themed-subtle transition-colors"
                onClick={() => onBrandClick?.(brand)}
              >
                <td>
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ background: 'var(--color-chart-7)' }}
                    />
                    <span className="font-medium text-themed-primary">{brand.label}</span>
                  </div>
                </td>
                <td>
                  <div className="flex gap-1 flex-wrap">
                    {brand.categories.map((c) => (
                      <span key={c} className="t-badge-default px-1.5 py-0.5 rounded-badge text-[10px] font-medium">
                        {c}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="text-[12px] text-themed-muted">{brand.group}</td>
                <td>
                  <span className="font-bold tabular-nums" style={{ color: 'var(--color-accent)' }}>
                    {brand.panoScore}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── 主页面 ────────────────────────────────────────────────────
export default function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const containerRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [selectedNode, setSelectedNode] = useState(null);
  const [filterType, setFilterType] = useState(null);
  const [viewMode, setViewMode] = useState('graph');

  // PRD §4.1.1b: 品牌节点点击 → 直达 Brand Overview, 不再开侧边详情面板.
  // 非品牌节点 (industry/category/product) 维持选中视觉, 不打开任何面板.
  const handleNodeSelect = (node) => {
    if (!node) {
      setSelectedNode(null);
      return;
    }
    // Toggle: 再次点击已选中的非品牌节点 → 取消选中
    if (selectedNode && selectedNode.id === node.id) {
      setSelectedNode(null);
      return;
    }
    if (node.type === 'brand') {
      const globalId = resolveGlobalBrandId(node.id);
      if (globalId) {
        navigate(`/brands/${globalId}?from=industry&industryId=beauty`);
        return;
      }
      // 未映射 — 兜底保留选中视觉 (Mock 缺数据时不阻塞用户)
    }
    setSelectedNode(node);
  };

  const handleListBrandClick = (graphBrandNode) => {
    const globalId = resolveGlobalBrandId(graphBrandNode.id);
    if (globalId) {
      navigate(`/brands/${globalId}?from=industry&industryId=beauty`);
    }
  };

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width, height });
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const nodeTypes = [
    { type: 'industry', label: '行业', token: '--color-accent',  count: RAW_NODES.filter((n) => n.type === 'industry').length },
    { type: 'category', label: '品类', token: '--color-chart-3', count: RAW_NODES.filter((n) => n.type === 'category').length },
    { type: 'brand',    label: '品牌', token: '--color-chart-7', count: RAW_NODES.filter((n) => n.type === 'brand').length },
    { type: 'product',  label: '产品', token: '--color-chart-2', count: RAW_NODES.filter((n) => n.type === 'product').length },
  ];

  const edgeTypes = [
    { type: 'COMPETES_WITH', label: '竞争关系',     token: '--color-danger' },
    { type: 'SAME_GROUP',    label: '同集团',       token: '--color-warning' },
    { type: 'BUDGET_ALT_OF', label: '平替',         token: '--color-success' },
    { type: 'UPGRADES_TO',   label: '升级路径',     token: '--color-chart-3' },
    { type: 'PAIRS_WITH',    label: '搭配推荐',     token: '--color-accent-2' },
  ];

  // KG page has no project / industry context state of its own — read it
  // from URL ?industryId=. Numeric ids hit /v1/industries/:id/kg; mock
  // ('beauty') skips.
  const kgIndustryParam = new URLSearchParams(window.location.search).get(
    'industryId',
  );
  const liveKgIndustryId = kgIndustryParam && /^\d+$/.test(kgIndustryParam)
    ? Number(kgIndustryParam)
    : null;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-brand font-bold text-themed-primary">行业知识图谱</h2>
          {/* View Mode Toggle (PRD 4.1.1b) */}
          <div className="flex rounded-btn overflow-hidden border border-themed">
            {[
              { id: 'graph', label: 'Graph' },
              { id: 'list',  label: 'List'  },
            ].map((v) => (
              <button
                key={v.id}
                onClick={() => setViewMode(v.id)}
                className="px-3.5 py-1.5 text-[12px] font-semibold transition-colors"
                style={{
                  background: viewMode === v.id ? 'var(--color-accent)' : 'transparent',
                  color: viewMode === v.id ? '#fff' : 'var(--color-text-muted)',
                }}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-5">
          {nodeTypes.map((nt) => (
            <div key={nt.type} className="flex items-center gap-1.5">
              <span className="text-xl font-brand font-bold tabular-nums" style={{ color: `var(${nt.token})` }}>
                {nt.count}
              </span>
              <span className="text-[12px] text-themed-muted">{nt.label}</span>
            </div>
          ))}
          <div className="flex items-center gap-1.5">
            <span className="text-xl font-brand font-bold tabular-nums" style={{ color: 'var(--color-danger)' }}>
              {RAW_LINKS.length}
            </span>
            <span className="text-[12px] text-themed-muted">关系边</span>
          </div>
        </div>
      </div>

      {/* Main layout */}
      {viewMode === 'graph' ? (
        <div className="flex gap-3" style={{ height: 'calc(100vh - 168px)' }}>
          {/* Graph area */}
          <Card className="flex-1 p-0 overflow-hidden">
            <div ref={containerRef} className="w-full h-full relative">
              {dimensions.width > 0 && (
                <G6Graph
                  width={dimensions.width}
                  height={dimensions.height}
                  onNodeSelect={handleNodeSelect}
                  selectedId={selectedNode?.id}
                  filterType={filterType}
                />
              )}
              {/* Watermark */}
              <div
                className="absolute top-3 left-3 text-[11px] font-medium px-3 py-1.5 rounded-btn"
                style={{
                  background: 'var(--color-accent-bg-light)',
                  color: 'var(--color-accent)',
                  backdropFilter: 'blur(8px)',
                }}
              >
                美妆个护 · Industry Knowledge Graph
              </div>
              {/* Instructions */}
              <div
                className="absolute bottom-3 left-3 text-[10px] px-3 py-1.5 rounded-btn text-themed-muted"
                style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-card)' }}
              >
                滚轮缩放 · 拖拽平移 · 点击节点查看详情 · 悬停查看关系
              </div>
            </div>
          </Card>

          {/* Side panel */}
          <div className="w-[240px] flex flex-col gap-3 flex-shrink-0">
            {/* Legend & Filter */}
            <Card className="p-4">
              <h3 className="text-[13px] font-semibold mb-3 text-themed-primary">图例与筛选</h3>
              <div className="space-y-3">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wider mb-1.5 text-themed-muted">
                    节点类型
                  </div>
                  <div className="space-y-1">
                    {nodeTypes.map((nt) => (
                      <button
                        key={nt.type}
                        onClick={() => setFilterType((f) => (f === nt.type ? null : nt.type))}
                        className="flex items-center gap-2 w-full text-left px-2 py-1.5 rounded-btn transition-colors text-[12px] text-themed-primary"
                        style={{
                          opacity: filterType && filterType !== nt.type ? 0.4 : 1,
                          background: filterType === nt.type ? 'var(--color-accent-bg-light)' : 'transparent',
                          border: filterType === nt.type ? '1px solid var(--color-accent-alpha-30)' : '1px solid transparent',
                        }}
                      >
                        <span
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ background: `var(${nt.token})` }}
                        />
                        <span>{nt.label}</span>
                        <span className="ml-auto text-[10px] tabular-nums text-themed-muted">{nt.count}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="pt-3 border-t border-themed">
                  <div className="text-[10px] font-semibold uppercase tracking-wider mb-1.5 text-themed-muted">
                    关系类型
                  </div>
                  <div className="space-y-1">
                    {edgeTypes.map((et) => (
                      <div key={et.type} className="flex items-center gap-2 px-2 py-1 text-[12px] text-themed-primary">
                        <span
                          className="w-5 flex-shrink-0"
                          style={{ height: 2, background: `var(${et.token})`, borderRadius: 1 }}
                        />
                        <span>{et.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {filterType && (
                  <button
                    onClick={() => setFilterType(null)}
                    className="w-full text-[11px] py-1.5 rounded-btn transition-colors text-themed-muted"
                    style={{ background: 'var(--color-bg-badge)' }}
                  >
                    清除筛选
                  </button>
                )}
              </div>
            </Card>
            {/* PRD §4.1.1b (rev 2026-04-16): 旧 Brand Detail Panel 已下线,
                品牌节点点击直达 /brands/:id (双入口反模式根除). */}
          </div>
        </div>
      ) : (
        <div style={{ height: 'calc(100vh - 168px)' }}>
          <BrandListView onBrandClick={handleListBrandClick} />
        </div>
      )}
    </div>
  );
}
