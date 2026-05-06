import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Graph } from '@antv/g6';
import { Badge, Card } from '../components/ui';
import { useIndustries, useIndustryKg } from '../hooks/useIndustries';
import {
  LoadingCard,
  EmptyCard,
  ErrorCard,
} from './brand/BrandVisibilityPage';
import type { KGNode, KGEdge } from '../api/industries';

/* Phase 5 §"mock 退役" — 整页来自 GET /v1/industries/:id/kg.
   Removes BRANDS / RAW_NODES / RAW_LINKS hard-coded mocks. */
export default function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const industriesQ = useIndustries();
  const list = industriesQ.data?.items ?? [];
  const industryParam = params.get('industryId');
  const industryId = industryParam
    ? Number(industryParam)
    : list.length > 0
      ? list[0].industry_id
      : null;
  const { data, isLoading, error, refetch } = useIndustryKg(industryId);

  useEffect(() => {
    if (!data || !containerRef.current) return;
    const cleanup = renderGraph(
      containerRef.current,
      graphRef,
      data.nodes,
      data.edges,
      (id) => {
        if (id.startsWith('br-')) {
          const numeric = Number(id.slice(3));
          if (!Number.isNaN(numeric)) {
            navigate(`/brands/${numeric}?tab=overview`);
          }
        }
      },
    );
    return cleanup;
  }, [data, navigate]);

  if (industriesQ.isLoading || isLoading) return <LoadingCard />;
  if (error)
    return (
      <ErrorCard
        msg={error instanceof Error ? error.message : 'unknown'}
        onRetry={() => refetch()}
      />
    );
  if (!data || data.state === 'empty' || data.nodes.length === 0)
    return <EmptyCard onRefresh={() => refetch()} title="知识图谱" />;

  const setIndustry = (id: number) => {
    const next = new URLSearchParams(params);
    next.set('industryId', String(id));
    setParams(next);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <h2 className="text-heading-2 font-bold text-themed-primary">
            知识图谱
          </h2>
          <span className="text-xs text-themed-muted">
            {data.nodes.length} 节点 · {data.edges.length} 边
          </span>
        </div>
        <select
          className="t-input text-sm"
          value={industryId ?? ''}
          onChange={(e) => setIndustry(Number(e.target.value))}
        >
          {list.map((it) => (
            <option key={it.industry_id} value={it.industry_id}>
              {it.name}
            </option>
          ))}
        </select>
      </div>

      <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
        <div ref={containerRef} style={{ height: 600, width: '100%' }} />
      </Card>
    </div>
  );
}

function renderGraph(
  container: HTMLElement,
  graphRef: React.MutableRefObject<Graph | null>,
  nodes: KGNode[],
  edges: KGEdge[],
  onNodeClick: (id: string) => void,
): () => void {
  if (graphRef.current) {
    graphRef.current.destroy();
    graphRef.current = null;
  }
  const width = container.clientWidth || 800;
  const g = new Graph({
    container,
    width,
    height: 600,
    data: {
      nodes: nodes.map((n) => ({
        id: n.id,
        style: {
          fill: nodeColor(n.type),
          stroke: nodeBorder(n.type),
          labelText: n.name,
          labelFontSize: 11,
          size: nodeSize(n.type),
        },
      })),
      edges: edges.map((e, idx) => ({
        id: `edge-${idx}`,
        source: e.source,
        target: e.target,
        style: {
          stroke: edgeColor(e.type),
          lineWidth: e.weight ? Math.min(3, 1 + e.weight * 0.5) : 1,
        },
      })),
    },
    layout: { type: 'force', preventOverlap: true, nodeStrength: -50 },
    behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
  });
  g.render();
  g.on('node:click', (evt: { target: { id: string } }) => {
    onNodeClick(evt.target.id);
  });
  graphRef.current = g;
  return () => {
    g.destroy();
    graphRef.current = null;
  };
}

function nodeColor(type: string): string {
  switch (type) {
    case 'brand':
      return '#635bff';
    case 'product':
      return '#16a34a';
    case 'category':
      return '#f59e0b';
    case 'industry':
      return '#dc2626';
    default:
      return '#64748b';
  }
}

function nodeBorder(type: string): string {
  return type === 'brand' || type === 'product' ? '#1e293b' : '#475569';
}

function nodeSize(type: string): number {
  switch (type) {
    case 'industry':
      return 36;
    case 'category':
      return 28;
    case 'brand':
      return 22;
    default:
      return 18;
  }
}

function edgeColor(type: string): string {
  switch (type) {
    case 'COMPETES_WITH':
      return '#dc2626';
    case 'SAME_GROUP':
      return '#635bff';
    case 'IN_CATEGORY':
      return '#f59e0b';
    case 'BELONGS_TO':
      return '#16a34a';
    case 'HAS_PRODUCT':
      return '#0ea5e9';
    default:
      return '#94a3b8';
  }
}
