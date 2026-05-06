import { useState, useMemo } from 'react';
import { Badge, Button, Card } from '../components/ui';
import ProfileGroupFilter, { ProfileGroupSampleWarning } from '../components/filters/ProfileGroupFilter';
import ProjectRequiredBanner from '../components/ProjectRequiredBanner';
import TopicIntentMatrix from '../components/topics/TopicIntentMatrix';
import { TOPICS, PROMPTS, QUERIES, RESPONSES, INDUSTRY_TOPIC_HEATMAP } from '../data/mock';

/* ─────────────────────────────────────────────────────────────
   TopicsPage — PRD §4.2 four-layer drill-down
   Topic → Prompt → Query → Response
   ─────────────────────────────────────────────────────────────
   Structure is PRD-driven. Style is token-driven (no inline hex).
*/

const INTENT_LABELS = {
  informational: '信息型',
  commercial:    '商业型',
  transactional: '交易型',
  navigational:  '导航型',
};

const INTENT_VARIANTS = {
  informational: 'blue',
  commercial:    'green',
  transactional: 'orange',
  navigational:  'purple',
};

const DIMENSION_VARIANTS = {
  产品: 'purple',
  品牌: 'blue',
  品类: 'green',
  竞品: 'orange',
};

const STATUS_MAP = {
  success: { label: '成功', varColor: '--color-success', icon: '✓' },
  failed:  { label: '失败', varColor: '--color-danger',  icon: '✗' },
  timeout: { label: '超时', varColor: '--color-warning', icon: '⏱' },
};

/* ── Small UI helpers ─────────────────────────────────────── */

function SentimentBar({ positive = 40, neutral = 30, warning = 20, brand = 10 }) {
  return (
    <div className="flex items-center overflow-hidden rounded-pill h-2.5 w-[150px]">
      <div style={{ width: `${positive}%`, background: 'var(--color-sentiment-positive)' }} />
      <div style={{ width: `${neutral}%`,  background: 'var(--color-sentiment-neutral)' }} />
      <div style={{ width: `${warning}%`,  background: 'var(--color-sentiment-warning)' }} />
      <div style={{ width: `${brand}%`,    background: 'var(--color-sentiment-brand)' }} />
    </div>
  );
}

function FilterBar({ search, onSearch, dimension, onDimension, intent, onIntent }) {
  const dimensions = ['全部', '产品', '品牌', '品类', '竞品'];
  const intents = [
    { id: '', label: '全部意图' },
    { id: 'informational', label: '信息型' },
    { id: 'commercial', label: '商业型' },
    { id: 'transactional', label: '交易型' },
    { id: 'navigational', label: '导航型' },
  ];
  return (
    <Card className="p-3">
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="flex-1 min-w-[240px] max-w-[420px]">
          <div className="flex items-center gap-2 h-10 px-3 rounded-btn bg-themed-subtle border border-themed-subtle">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5} className="text-themed-muted">
              <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              placeholder="搜索 Topic 或 Prompt..."
              className="flex-1 bg-transparent text-sm text-themed-primary placeholder:text-themed-faint outline-none"
            />
          </div>
        </div>

        {/* Dimension pills */}
        <div className="flex items-center gap-1.5">
          {dimensions.map((d) => {
            const active = (d === '全部' && !dimension) || d === dimension;
            return (
              <button
                key={d}
                onClick={() => onDimension(d === '全部' ? '' : d)}
                className={`px-3 py-1.5 rounded-pill text-xs font-medium transition-colors ${
                  active
                    ? 'text-themed-accent'
                    : 'text-themed-muted border border-themed hover:text-themed-primary'
                }`}
                style={active ? { background: 'var(--color-accent-bg-light)' } : undefined}
              >
                {d}
              </button>
            );
          })}
        </div>

        <div className="h-5 w-px bg-themed-card" />

        {/* Intent pills — PRD §4.2.5 / §4.6.1a-filter 2026-04-16 */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-themed-muted shrink-0">意图</span>
          {intents.map((i) => {
            const active = (i.id === '' && !intent) || i.id === intent;
            return (
              <button
                key={i.id}
                onClick={() => onIntent(i.id)}
                className={`px-3 py-1.5 rounded-pill text-xs font-medium transition-colors ${
                  active
                    ? 'text-themed-accent'
                    : 'text-themed-muted border border-themed hover:text-themed-primary'
                }`}
                style={active ? { background: 'var(--color-accent-bg-light)' } : undefined}
              >
                {i.label}
              </button>
            );
          })}
        </div>

        {/* Profile Group filter — PRD §4.2.5 / §4.2.3a */}
        <div className="h-5 w-px bg-themed-card" />
        <ProfileGroupFilter />

        <div className="flex-1" />
        <Button variant="outline" size="sm">导出 CSV</Button>
      </div>
    </Card>
  );
}

function Breadcrumb({ items, onNavigate }) {
  return (
    <div className="flex items-center gap-1.5 text-sm mb-5">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-themed-muted">/</span>}
          {i < items.length - 1 ? (
            <button
              onClick={() => onNavigate(item.view)}
              className="text-themed-muted hover:text-themed-primary transition-colors"
            >
              {item.label}
            </button>
          ) : (
            <span className="font-medium text-themed-primary">{item.label}</span>
          )}
        </span>
      ))}
    </div>
  );
}

/* ── Layer 1: Topics grid ─────────────────────────────────── */

function TopicsView({ onSelectTopic }) {
  const [search, setSearch] = useState('');
  const [dimension, setDimension] = useState('');
  const [intent, setIntent] = useState('');

  const filtered = useMemo(() => {
    return TOPICS.filter((t) => {
      if (dimension && t.dimension !== dimension) return false;
      if (search && !t.name.toLowerCase().includes(search.toLowerCase())) return false;
      // Intent filter: aggregates by intent of contained Prompts (PRD §4.2.5 2026-04-16)
      if (intent) {
        const topicPrompts = (PROMPTS || []).filter((p) => p.topicId === t.id);
        const hasMatchingIntent = topicPrompts.some((p) => p.intent === intent);
        if (!hasMatchingIntent) return false;
      }
      return true;
    });
  }, [search, dimension, intent]);

  return (
    <div className="space-y-6">
      <FilterBar search={search} onSearch={setSearch} dimension={dimension} onDimension={setDimension} intent={intent} onIntent={setIntent} />

      {/* Profile-group degradation banner — PRD §4.2.3a 聚合语义 */}
      <ProfileGroupSampleWarning />

      {/* Topic × Intent 交叉矩阵 — PRD §4.2.5 2026-04-21 v3.2
          组件共享自 Industry Mode (`components/topics/TopicIntentMatrix`), 数据源 INDUSTRY_TOPIC_HEATMAP
          (含 topicName/mentionCount 字段, 与 TOPICS 的 name/id 形态不同, 直接复用更稳).
          目的: 让品牌在自己侧也能一眼看"我正在追踪的 Topic 背后意图分布 — 查资料 vs 查购买",
          承接内容策略 vs 电商策略优先级的决策锚点. */}
      <TopicIntentMatrix
        topics={INDUSTRY_TOPIC_HEATMAP}
        limit={8}
      />

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">监测 Topic 数</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">{TOPICS.length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Prompts 总数</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {TOPICS.reduce((s, t) => s + t.promptCount, 0)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Queries 总数</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {TOPICS.reduce((s, t) => s + t.queryCount, 0)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Responses 总数</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {TOPICS.reduce((s, t) => s + t.responseCount, 0)}
          </div>
        </Card>
      </div>

      {/* Topics table */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-themed-card">
          <h3 className="text-sm font-semibold text-themed-primary">监测 Topics</h3>
          <Button variant="primary" size="sm">+ 新增 Topic</Button>
        </div>
        <table className="t-table w-full">
          <thead>
            <tr>
              <th>Topic</th>
              <th>维度</th>
              <th>关联品牌</th>
              <th className="text-right">Prompts</th>
              <th className="text-right">Queries</th>
              <th className="text-right">Responses</th>
              <th>情感分布</th>
              <th>最近采集</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((topic) => (
              <tr
                key={topic.id}
                className="cursor-pointer"
                onClick={() => onSelectTopic(topic)}
              >
                <td>
                  <div className="flex items-center gap-2">
                    {topic.priority === 'key' && (
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: 'var(--color-accent)' }}
                        title="重点监测"
                      />
                    )}
                    <span className="font-medium text-themed-primary">{topic.name}</span>
                  </div>
                </td>
                <td><Badge variant={DIMENSION_VARIANTS[topic.dimension]} size="sm">{topic.dimension}</Badge></td>
                <td className="text-themed-muted">{topic.brand || '—'}</td>
                <td className="text-right tabular-nums font-semibold text-themed-primary">{topic.promptCount}</td>
                <td className="text-right tabular-nums text-themed-primary">{topic.queryCount}</td>
                <td className="text-right tabular-nums text-themed-muted">{topic.responseCount}</td>
                <td><SentimentBar positive={35} neutral={25} warning={25} brand={15} /></td>
                <td className="text-themed-muted text-xs">{topic.lastCollected}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-12 text-themed-muted">无匹配的 Topic</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ── Layer 2: Prompts for a topic ─────────────────────────── */

function PromptsView({ topic, onSelectPrompt }) {
  const prompts = PROMPTS[topic.id] || [];

  return (
    <div className="space-y-6">
      {/* Topic header card */}
      <Card className="p-5">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div>
            <h2 className="text-xl font-brand font-bold text-themed-primary mb-2">{topic.name}</h2>
            <div className="flex items-center gap-3 flex-wrap">
              <Badge variant={DIMENSION_VARIANTS[topic.dimension]} size="sm">{topic.dimension}</Badge>
              {topic.brand && <span className="text-sm text-themed-muted">{topic.brand}</span>}
              <span className="text-xs text-themed-muted">· 来源: {topic.source}</span>
              <span className="text-xs text-themed-muted">· 最近采集: {topic.lastCollected}</span>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="text-right">
              <div className="text-2xl font-brand font-bold text-themed-accent tabular-nums">{prompts.length}</div>
              <div className="text-xs text-themed-muted">Prompts</div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">{topic.queryCount}</div>
              <div className="text-xs text-themed-muted">Queries</div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">{topic.responseCount}</div>
              <div className="text-xs text-themed-muted">Responses</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Prompts table */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-themed-card">
          <h3 className="text-sm font-semibold text-themed-primary">Prompts</h3>
          <Button variant="outline" size="sm">+ 添加 Prompt</Button>
        </div>
        <table className="t-table w-full">
          <thead>
            <tr>
              <th>Prompt 提示语</th>
              <th>Intent</th>
              <th className="text-right">Queries</th>
              <th className="text-right">引擎覆盖</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr
                key={prompt.id}
                className="cursor-pointer"
                onClick={() => onSelectPrompt(prompt)}
              >
                <td className="font-medium text-themed-primary">"{prompt.text}"</td>
                <td><Badge variant={INTENT_VARIANTS[prompt.intent]} size="sm">{INTENT_LABELS[prompt.intent]}</Badge></td>
                <td className="text-right tabular-nums font-semibold text-themed-accent">{prompt.queryCount}</td>
                <td className="text-right">
                  <span
                    className="inline-block text-xs font-semibold px-2 py-0.5 rounded-badge"
                    style={{
                      background:
                        prompt.coverage === '100%'
                          ? 'var(--color-success-bg)'
                          : 'var(--color-warning-bg)',
                      color:
                        prompt.coverage === '100%'
                          ? 'var(--color-success-text)'
                          : 'var(--color-warning-text)',
                    }}
                  >
                    {prompt.coverage}
                  </span>
                </td>
              </tr>
            ))}
            {prompts.length === 0 && (
              <tr>
                <td colSpan={4} className="text-center py-12 text-themed-muted">暂无 Prompt 数据</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ── Layer 3: Queries for a prompt ────────────────────────── */

function QueriesView({ topic, prompt, onSelectQuery }) {
  const queries = QUERIES[prompt.id] || [];
  const successCount = queries.filter((q) => q.status === 'success').length;
  const successRate = queries.length > 0 ? Math.round((successCount / queries.length) * 100) : 0;
  const enginesCovered = new Set(queries.map((q) => q.engine)).size;

  return (
    <div className="space-y-6">
      {/* Prompt header */}
      <Card className="p-5">
        <div className="text-xs text-themed-muted mb-2">Topic: {topic.name}</div>
        <p className="text-base font-medium text-themed-primary mb-3 leading-relaxed">"{prompt.text}"</p>
        <div className="flex items-center gap-3">
          <Badge variant={INTENT_VARIANTS[prompt.intent]} size="sm">{INTENT_LABELS[prompt.intent]}</Badge>
          <span className="text-xs text-themed-muted">引擎覆盖: {prompt.coverage}</span>
        </div>
      </Card>

      {/* Query stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">执行总数</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">{queries.length}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">成功率</div>
          <div
            className="text-2xl font-brand font-bold tabular-nums"
            style={{
              color: successRate >= 80 ? 'var(--color-success-text)' : 'var(--color-warning-text)',
            }}
          >
            {successRate}%
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">覆盖引擎</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">{enginesCovered}</div>
        </Card>
      </div>

      {/* Queries table */}
      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-4 border-b border-themed-card">
          <h3 className="text-sm font-semibold text-themed-primary">Query 执行记录</h3>
        </div>
        <table className="t-table w-full">
          <thead>
            <tr>
              <th>引擎</th>
              <th>Profile</th>
              <th>执行时间</th>
              <th>状态</th>
              <th className="text-right">品牌提及</th>
            </tr>
          </thead>
          <tbody>
            {queries.map((query) => {
              const st = STATUS_MAP[query.status] || STATUS_MAP.success;
              const hasResponse = !!RESPONSES[query.id];
              return (
                <tr
                  key={query.id}
                  className={hasResponse ? 'cursor-pointer' : 'opacity-60'}
                  onClick={() => hasResponse && onSelectQuery(query)}
                >
                  <td className="font-medium text-themed-primary">{query.engine}</td>
                  <td className="text-themed-muted">{query.profile}</td>
                  <td className="text-themed-muted text-xs tabular-nums">{query.time}</td>
                  <td>
                    <span
                      className="inline-flex items-center gap-1 text-xs font-semibold"
                      style={{ color: `var(${st.varColor})` }}
                    >
                      <span>{st.icon}</span> {st.label}
                    </span>
                  </td>
                  <td className="text-right tabular-nums font-semibold text-themed-primary">
                    {query.status === 'success' ? query.brandMentions : '—'}
                  </td>
                </tr>
              );
            })}
            {queries.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-12 text-themed-muted">暂无 Query 数据</td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

/* ── Layer 4: Response detail ─────────────────────────────── */

function ResponseView({ query }) {
  const response = RESPONSES[query.id];
  if (!response) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-themed-muted">该 Query 暂无 Response 数据</p>
      </Card>
    );
  }
  const { analysis } = response;

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="p-5">
        <div className="flex items-center gap-4 mb-3 flex-wrap">
          <Badge variant="accent" size="sm">{response.engine}</Badge>
          <span className="text-xs text-themed-muted">{response.profile}</span>
          <span className="text-xs text-themed-muted tabular-nums">{response.time}</span>
        </div>
        <div className="p-3 rounded-btn bg-themed-subtle">
          <div className="text-xs text-themed-muted">Prompt</div>
          <p className="text-sm font-medium text-themed-primary mt-1">"{response.prompt}"</p>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Raw text */}
        <div className="lg:col-span-2">
          <Card className="p-5">
            <div className="flex items-center justify-between border-b border-themed-card pb-3 mb-4">
              <h3 className="text-sm font-semibold text-themed-primary">AI 原始回答</h3>
              <span className="text-xs text-themed-muted tabular-nums">{analysis.wordCount} 字</span>
            </div>
            <div className="text-sm leading-relaxed whitespace-pre-wrap text-themed-body">
              {response.rawText}
            </div>
          </Card>
        </div>

        {/* Analysis sidebar */}
        <div className="space-y-4">
          <Card className="p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-themed-muted mb-2">推荐类型</h4>
            <Badge variant="accent" size="md">{analysis.recommendationType}</Badge>
          </Card>

          <Card className="p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-themed-muted mb-3">品牌提及</h4>
            <div className="space-y-3">
              {analysis.brands.map((brand, i) => (
                <div key={i} className="flex items-center justify-between p-2.5 rounded-btn bg-themed-subtle">
                  <div>
                    <div className="text-sm font-medium text-themed-primary">{brand.name}</div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[11px] text-themed-muted">位次 {brand.position}</span>
                      <span
                        className="text-[11px] font-semibold"
                        style={{
                          color:
                            brand.sentiment === '正面'
                              ? 'var(--color-success-text)'
                              : brand.sentiment === '负面'
                              ? 'var(--color-danger-text)'
                              : 'var(--color-text-muted)',
                        }}
                      >
                        {brand.sentiment}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-brand font-bold text-themed-accent tabular-nums">
                      {(brand.sentimentScore * 100).toFixed(0)}
                    </div>
                    <div className="text-[10px] text-themed-muted">情感分</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-themed-muted mb-3">产品提及</h4>
            <div className="space-y-3">
              {analysis.products.map((product, i) => (
                <div key={i} className="p-2.5 rounded-btn bg-themed-subtle">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-themed-primary">{product.name}</span>
                    <span className="text-[11px] text-themed-muted">{product.brand}</span>
                  </div>
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {product.keywords.map((kw, ki) => (
                      <span
                        key={ki}
                        className="text-[10px] px-1.5 py-0.5 rounded-badge"
                        style={{
                          background: 'var(--color-accent-subtle)',
                          color: 'var(--color-accent-text)',
                        }}
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {analysis.citations && analysis.citations.length > 0 && (
            <Card className="p-4">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-themed-muted mb-3">引用来源</h4>
              <div className="space-y-2">
                {analysis.citations.map((cite, i) => (
                  <a
                    key={i}
                    href={cite.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-xs truncate text-themed-accent hover:underline"
                  >
                    {cite.url}
                  </a>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Page controller ──────────────────────────────────────── */

export default function TopicsPage() {
  const [view, setView] = useState('topics');
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [selectedQuery, setSelectedQuery] = useState(null);

  const goTo = {
    topics:   () => { setView('topics'); setSelectedTopic(null); setSelectedPrompt(null); setSelectedQuery(null); },
    prompts:  (topic)  => { setView('prompts');  setSelectedTopic(topic); setSelectedPrompt(null); setSelectedQuery(null); },
    queries:  (prompt) => { setView('queries');  setSelectedPrompt(prompt); setSelectedQuery(null); },
    response: (query)  => { setView('response'); setSelectedQuery(query); },
  };

  const breadcrumb = [{ label: 'Topics', view: 'topics' }];
  if (selectedTopic && view !== 'topics') {
    breadcrumb.push({ label: selectedTopic.name, view: 'prompts' });
  }
  if (selectedPrompt && (view === 'queries' || view === 'response')) {
    const short = selectedPrompt.text.length > 30 ? selectedPrompt.text.slice(0, 30) + '...' : selectedPrompt.text;
    breadcrumb.push({ label: short, view: 'queries' });
  }
  if (selectedQuery && view === 'response') {
    breadcrumb.push({ label: `${selectedQuery.engine} · ${selectedQuery.profile}`, view: 'response' });
  }

  const onBreadcrumb = (target) => {
    if (target === 'topics')  goTo.topics();
    else if (target === 'prompts') { setView('prompts');  setSelectedPrompt(null); setSelectedQuery(null); }
    else if (target === 'queries') { setView('queries');  setSelectedQuery(null); }
  };

  return (
    <div>
      {/* PRD §4.1.1d E4 — Gated-surface banner.
          Topics drilldown depends on a Project for scope/filter semantics, so
          authenticated-zero-Project users see a conversion prompt at the top.
          The banner self-gates (auth + projects.length===0 + not dismissed). */}
      <ProjectRequiredBanner />

      {view !== 'topics' && <Breadcrumb items={breadcrumb} onNavigate={onBreadcrumb} />}

      {view === 'topics'   && <TopicsView onSelectTopic={(topic) => goTo.prompts(topic)} />}
      {view === 'prompts'  && selectedTopic  && <PromptsView topic={selectedTopic} onSelectPrompt={(p) => goTo.queries(p)} />}
      {view === 'queries'  && selectedTopic  && selectedPrompt  && <QueriesView topic={selectedTopic} prompt={selectedPrompt} onSelectQuery={(q) => goTo.response(q)} />}
      {view === 'response' && selectedQuery  && <ResponseView query={selectedQuery} />}
    </div>
  );
}
