/**
 * LandingPage.jsx — v2.1 (Stripe Light, 2026-04-17)
 *
 * 设计依据:
 *   - docs/DESIGN_TOKENS.md  (唯一样式真相源, 本页只能引用已存在的 CSS 变量)
 *   - docs/LANDING_REDESIGN.md §4 v2.1
 *
 * ⚠️ 强制约束 (见 memory: feedback_genpano_landing_v21):
 *   1. 颜色 / 圆角 / 阴影 / 字体 100% 消费 docs/DESIGN_TOKENS.md 的 CSS 变量, 不新增 token
 *   2. 所有 CTA 指向真实路由 (/register /login /industry), 禁用 #cta / #register 锚点占位
 *   3. 所有 CTA 带 ?from=landing_<位置> UTM (PRD §4.11)
 *   4. 品牌渐变只有一条: linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)
 *   5. 主字体 Nunito (已在 frontend/src/index.css 全局挂载到 body), 不引入 JetBrains Mono / Geist
 *   6. 不渲染 macOS 终端红/黄/绿点 mock
 *   7. 禁止开发者约束文字泄漏到用户 UI
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import LandingNavQuickCreateButton from '../components/landing/LandingNavQuickCreateButton';
import {
  Sparkles,
  ArrowRight,
  Check,
  X,
  Search,
  Gauge,
  BarChart3,
  Network,
  FileText,
  Shield,
  Target,
  Zap,
  Globe,
  Code2,
  Cpu,
  LineChart as LineChartIcon,
} from 'lucide-react';

/* ──────────────────────────────────────────────────────────────
   i18n — copy dictionary (zh-CN / en-US)
   ────────────────────────────────────────────────────────────── */
const COPY = {
  'zh-CN': {
    nav: {
      product: '产品',
      method: '方法论',
      industries: '行业',
      agents: 'For Agents',
      docs: '文档',
      login: '登录',
      register: '免费开始',
    },
    hero: {
      eyebrow: 'GEO · Generative Engine Optimization',
      h1_a: '你的品牌在 AI 回答里，',
      h1_highlight: '占多少位置',
      h1_b: '？',
      sub: '免费监测 ChatGPT / 豆包 / DeepSeek 中的品牌可见度、情感和引用份额。每日全量采集，Agent 原生接口，1 分钟看到你在行业里的真实位置。',
      meta: '已覆盖 4 个行业 · 200+ 品牌 · 每日 10K+ Query · 永久免费',
      cta_primary: '免费开始监测',
      cta_secondary: '先探索行业数据',
      cta_tertiary: '已有账号？登录',
    },
    problem: {
      title: '传统 SEO 指标，在 AI 回答里失效了',
      subtitle: '用户问题的答案正从 10 条蓝链变成 1 段 AI 回答。你的品牌出现在那段回答里吗？',
      left_title: '传统 SEO 能告诉你',
      left_items: [
        '网站在 Google 的关键词排名',
        '月度自然搜索流量',
        '反向链接数量',
      ],
      right_title: '但它没办法回答',
      right_items: [
        '你在 ChatGPT 回答里的提及率',
        '豆包推荐品牌时你排第几',
        'AI 是正面 / 中性 / 负面评价你',
        '引用了你网站还是竞品网站',
      ],
    },
    method: {
      eyebrow: '方法论',
      title: 'PANO Score',
      subtitle: '一个量化品牌在 AI 回答中表现的综合指标',
      formula_label: '计算公式',
      formula: 'PANO = 0.35 × 提及率 + 0.25 × SoV + 0.20 × 情感 + 0.15 × 引用份额 + 0.05 × 排名',
      dims_title: '5 个维度',
      dims: [
        { k: '提及率', v: '品类型 Query 中被提到的百分比', tone: 'chart-1' },
        { k: 'SoV', v: '在命中任一品牌的回答里, 被提到的份额', tone: 'chart-2' },
        { k: '情感', v: '提及语境的正负面倾向 (-1 ~ +1)', tone: 'chart-3' },
        { k: '引用份额', v: 'AI 回答中引用你官网 / 内容的比例', tone: 'chart-4' },
        { k: '行业排名', v: '在同行业所有品牌中的 PANO 百分位', tone: 'chart-5' },
      ],
    },
    product: {
      eyebrow: '产品',
      title: '从宏观市场到单品牌，四层下钻',
      cards: [
        {
          title: '面板 · 市场宏观视角',
          desc: '5 KPI 一屏总览 (提及率 / SoV / 情感 / 引用份额 / 行业排名) + PanoScore Hero + 竞品四象限 + 趋势对比。',
          badge: '每日刷新',
        },
        {
          title: '品牌详情 · 4 子 Tab',
          desc: '概览 / 诊断 / 产品 / 引擎对比。PanoRing + 4 维分解 + 位置分布 + BCG 产品矩阵 + Quick Wins / Strategic Bets。',
          badge: '单品牌深度',
        },
        {
          title: 'Topics · 4 层 Drilldown',
          desc: 'Topic → Prompt → Query → Response 逐层展开, 看到每一条 AI 回答是怎么产生的。',
          badge: '可审计',
        },
        {
          title: '知识图谱',
          desc: '品类 × 品牌 × 产品关系网, AntV G6 径向布局, 识别同集团 / 平替 / 互补, 驱动 Topic 自动生成。',
          badge: 'LLM + 挖掘',
        },
      ],
    },
    industries: {
      eyebrow: '行业',
      title: '首批 4 个行业已就绪, 注册即可浏览',
      subtitle: '行业数据每日全量采集, 无需等待。你的品牌不在列表中？注册后提交, 平台验证后纳入公共知识图谱, 所有同行受益。',
      table: [
        { slug: 'beauty', name: '美妆个护', brands: 68, queries: '2.4K / 日', engines: '3', status: '就绪' },
        { slug: 'luxury', name: '奢侈品', brands: 42, queries: '1.8K / 日', engines: '3', status: '就绪' },
        { slug: 'fnb', name: '食品饮料', brands: 55, queries: '2.1K / 日', engines: '3', status: '就绪' },
        { slug: 'fashion', name: '服装时尚', brands: 60, queries: '2.3K / 日', engines: '3', status: '就绪' },
      ],
      col: { brand: '品牌数', query: 'Query 量', engine: '引擎', status: '状态', action: '' },
      view: '查看 →',
      browse_all: '探索全部行业',
    },
    voices: {
      eyebrow: '反馈',
      title: '来自早期用户',
      items: [
        {
          quote: '第一次看清楚品牌在 ChatGPT 和豆包里的真实位置, 老板再问"AI 搜索我们怎么样"我有答案了。',
          who: '李 · 美妆品牌 GEO 负责人',
          brand: 'Brand A',
        },
        {
          quote: 'PANO Score 把 5 个维度压成一个数, 汇报给 CMO 简单多了。诊断里的 Quick Wins 是能直接做的。',
          who: '王 · 奢侈品牌市场总监',
          brand: 'Brand B',
        },
        {
          quote: 'MCP Server 能把数据直接喂给我们自建的 Agent, 做竞品监控 / 内容选题再也不用手动导 CSV。',
          who: 'Sarah · DTC SaaS 增长',
          brand: 'Brand C',
        },
      ],
    },
    agents: {
      eyebrow: 'For Agents',
      title: 'Agent 原生接口, 不是 SEO 工具的外挂',
      subtitle: '每一个指标都有结构化 API, 每一份报告都可被 AI Agent 消费。',
      features: [
        { icon: 'code', title: 'REST + MCP Server', desc: 'OpenAPI 文档, 支持 Claude / ChatGPT Plugin 直接接入' },
        { icon: 'shield', title: 'No PII in payloads', desc: '遵循 PRD §4.11.5 红线, 事件属性零 PII' },
        { icon: 'cpu', title: '每日全量采集', desc: '不按量计费, 不按 seats 限流, 免费版覆盖 MVP 全功能' },
      ],
      code_title: 'mcp.config.json',
      code: `{
  "mcpServers": {
    "genpano": {
      "command": "npx",
      "args": ["-y", "@genpano/mcp-server"],
      "env": {
        "GENPANO_API_KEY": "\${GENPANO_API_KEY}"
      }
    }
  }
}`,
      cta: '阅读 Agent 文档',
    },
    final: {
      title: '1 分钟看到你的品牌在 AI 里长什么样',
      subtitle: '注册后直接看到行业真实数据, 无需等待采集, 无需连接第三方, 永久免费。',
      cta_primary: '免费开始监测',
      cta_secondary: '先探索行业数据',
    },
    footer: {
      tagline: 'Agent-native 免费 GEO 监测平台',
      col_product: '产品',
      col_resources: '资源',
      col_company: '公司',
      links: {
        product: ['面板', '品牌', 'Topics', '知识图谱'],
        resources: ['文档', 'API', 'MCP Server', 'Changelog'],
        company: ['关于', '博客', '隐私', '条款'],
      },
      copyright: '© 2026 GENPANO · All rights reserved',
      lang_label: '语言',
    },
  },

  'en-US': {
    nav: {
      product: 'Product',
      method: 'Method',
      industries: 'Industries',
      agents: 'For Agents',
      docs: 'Docs',
      login: 'Log in',
      register: 'Start free',
    },
    hero: {
      eyebrow: 'GEO · Generative Engine Optimization',
      h1_a: 'How visible is your brand',
      h1_highlight: 'inside AI answers',
      h1_b: '?',
      sub: 'Free monitoring for brand mention, sentiment and citation share across ChatGPT, Doubao and DeepSeek. Daily full-crawl, agent-native API. See your real position in one minute.',
      meta: '4 industries · 200+ brands · 10K+ queries/day · Forever free',
      cta_primary: 'Start monitoring free',
      cta_secondary: 'Explore industry data',
      cta_tertiary: 'Already have an account? Log in',
    },
    problem: {
      title: 'Classic SEO metrics stop working inside AI answers',
      subtitle: 'Users are shifting from 10 blue links to a single AI paragraph. Is your brand inside that paragraph?',
      left_title: 'Classic SEO tells you',
      left_items: [
        'Keyword ranking on Google',
        'Monthly organic traffic',
        'Backlink count',
      ],
      right_title: 'But it cannot answer',
      right_items: [
        'Your mention rate inside ChatGPT answers',
        'Your rank when Doubao recommends a brand',
        'Whether AI speaks positively or negatively about you',
        'Whether AI cites your site or your competitor',
      ],
    },
    method: {
      eyebrow: 'Method',
      title: 'PANO Score',
      subtitle: 'A single composite that quantifies your brand inside AI answers',
      formula_label: 'Formula',
      formula: 'PANO = 0.35 × Mention + 0.25 × SoV + 0.20 × Sentiment + 0.15 × Citation + 0.05 × Rank',
      dims_title: '5 dimensions',
      dims: [
        { k: 'Mention rate', v: '% of category-dimension queries that surface your brand', tone: 'chart-1' },
        { k: 'SoV', v: 'Share of voice inside answers that surface any brand', tone: 'chart-2' },
        { k: 'Sentiment', v: 'Polarity of your mentions (-1 to +1)', tone: 'chart-3' },
        { k: 'Citation share', v: 'Share of citations pointing to your site/content', tone: 'chart-4' },
        { k: 'Rank', v: 'PANO percentile inside your industry', tone: 'chart-5' },
      ],
    },
    product: {
      eyebrow: 'Product',
      title: 'From market macro down to a single brand — four-layer drilldown',
      cards: [
        {
          title: 'Dashboard · Market macro',
          desc: '5 KPIs at a glance (Mention / SoV / Sentiment / Citation / Rank) + PanoScore hero + competitor quadrant + trend.',
          badge: 'Daily refresh',
        },
        {
          title: 'Brand detail · 4 tabs',
          desc: 'Overview / Diagnostics / Products / Engine. PanoRing, 4-dim breakdown, position map, BCG matrix, Quick Wins.',
          badge: 'Single-brand depth',
        },
        {
          title: 'Topics · 4-layer drilldown',
          desc: 'Topic → Prompt → Query → Response. Audit the exact AI answer behind every data point.',
          badge: 'Auditable',
        },
        {
          title: 'Knowledge graph',
          desc: 'Category × brand × product graph on AntV G6 (radial). Powers automatic topic generation.',
          badge: 'LLM + mining',
        },
      ],
    },
    industries: {
      eyebrow: 'Industries',
      title: 'First 4 industries are live — browse right after sign-up',
      subtitle: 'Full-crawl every day, no wait. Brand missing? Submit after sign-up; once verified it joins the public graph and everyone benefits.',
      table: [
        { slug: 'beauty', name: 'Beauty & PC', brands: 68, queries: '2.4K/d', engines: '3', status: 'Ready' },
        { slug: 'luxury', name: 'Luxury', brands: 42, queries: '1.8K/d', engines: '3', status: 'Ready' },
        { slug: 'fnb', name: 'Food & Bev', brands: 55, queries: '2.1K/d', engines: '3', status: 'Ready' },
        { slug: 'fashion', name: 'Fashion', brands: 60, queries: '2.3K/d', engines: '3', status: 'Ready' },
      ],
      col: { brand: 'Brands', query: 'Queries', engine: 'Engines', status: 'Status', action: '' },
      view: 'View →',
      browse_all: 'Browse all industries',
    },
    voices: {
      eyebrow: 'Voices',
      title: 'From early users',
      items: [
        {
          quote: 'First time we can actually see our position inside ChatGPT and Doubao. I finally have an answer when my boss asks "how do we show up in AI search".',
          who: 'Li · GEO lead, beauty brand',
          brand: 'Brand A',
        },
        {
          quote: 'PANO Score compresses 5 dimensions into one number. Reporting up to CMO is much easier. Quick Wins are directly executable.',
          who: 'Wang · CMO, luxury brand',
          brand: 'Brand B',
        },
        {
          quote: 'MCP Server lets our in-house agent consume the data directly. No more manual CSV exports for competitor monitoring.',
          who: 'Sarah · Growth, DTC SaaS',
          brand: 'Brand C',
        },
      ],
    },
    agents: {
      eyebrow: 'For Agents',
      title: 'Agent-native. Not a bolt-on to an SEO suite.',
      subtitle: 'Every metric has a typed API. Every report is consumable by agents.',
      features: [
        { icon: 'code', title: 'REST + MCP Server', desc: 'OpenAPI spec, works with Claude / ChatGPT plugins out of the box' },
        { icon: 'shield', title: 'No PII in payloads', desc: 'Per PRD §4.11.5 — zero PII inside event properties' },
        { icon: 'cpu', title: 'Daily full-crawl', desc: 'No per-query metering, no seat caps, MVP free tier covers everything' },
      ],
      code_title: 'mcp.config.json',
      code: `{
  "mcpServers": {
    "genpano": {
      "command": "npx",
      "args": ["-y", "@genpano/mcp-server"],
      "env": {
        "GENPANO_API_KEY": "\${GENPANO_API_KEY}"
      }
    }
  }
}`,
      cta: 'Read the agent docs',
    },
    final: {
      title: 'See your brand inside AI in under a minute',
      subtitle: 'Real industry data right after sign-up. No waiting to crawl, no third-party connections, forever free.',
      cta_primary: 'Start monitoring free',
      cta_secondary: 'Explore industry data',
    },
    footer: {
      tagline: 'Agent-native free GEO monitoring',
      col_product: 'Product',
      col_resources: 'Resources',
      col_company: 'Company',
      links: {
        product: ['Dashboard', 'Brands', 'Topics', 'Knowledge graph'],
        resources: ['Docs', 'API', 'MCP Server', 'Changelog'],
        company: ['About', 'Blog', 'Privacy', 'Terms'],
      },
      copyright: '© 2026 GENPANO · All rights reserved',
      lang_label: 'Language',
    },
  },
};

/* ──────────────────────────────────────────────────────────────
   Locale hook — URL ?locale → localStorage → cookie → navigator → zh-CN
   契约见 docs/LANDING_REDESIGN.md §7
   ────────────────────────────────────────────────────────────── */
function readCookie(name) {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[1]) : null;
}
function writeCookie(name, value) {
  if (typeof document === 'undefined') return;
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${oneYear}; Path=/; SameSite=Lax`;
}
function detectInitialLocale() {
  if (typeof window === 'undefined') return 'zh-CN';
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get('locale');
  if (fromUrl === 'zh-CN' || fromUrl === 'en-US') return fromUrl;
  const fromLs = window.localStorage?.getItem('genpano_locale');
  if (fromLs === 'zh-CN' || fromLs === 'en-US') return fromLs;
  const fromCookie = readCookie('genpano_locale');
  if (fromCookie === 'zh-CN' || fromCookie === 'en-US') return fromCookie;
  const nav = (navigator.language || 'zh-CN').toLowerCase();
  return nav.startsWith('zh') ? 'zh-CN' : 'en-US';
}

function useLocale() {
  const [locale, setLocale] = useState('zh-CN');
  useEffect(() => {
    setLocale(detectInitialLocale());
  }, []);
  const change = useCallback((next) => {
    setLocale(next);
    try {
      window.localStorage?.setItem('genpano_locale', next);
      writeCookie('genpano_locale', next);
    } catch {
      /* ignore */
    }
  }, []);
  return [locale, change];
}

/* ──────────────────────────────────────────────────────────────
   Analytics stub (landing_cta_click / landing_locale_switch)
   真实实现走 frontend/src/lib/analytics (PRD §4.11)
   ────────────────────────────────────────────────────────────── */
function track(event, props = {}) {
  if (typeof window === 'undefined') return;
  if (window.__genpano_track) {
    try { window.__genpano_track(event, props); } catch { /* no-op */ }
  }
}

/* ──────────────────────────────────────────────────────────────
   Shared bits
   ────────────────────────────────────────────────────────────── */
const MAX_W = 'max-w-[1200px] mx-auto px-6';

function Eyebrow({ children }) {
  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1 text-xs font-semibold uppercase tracking-wider"
      style={{
        color: 'var(--color-accent)',
        backgroundColor: 'rgba(96, 91, 255, 0.08)',
        borderRadius: '999px',
        letterSpacing: '0.08em',
      }}
    >
      {children}
    </div>
  );
}

function PrimaryCTA({ to, from, children, icon = true, onClick }) {
  const href = `${to}?from=landing_${from}`;
  return (
    <Link
      to={href}
      onClick={() => { track('landing_cta_click', { cta: 'primary', from }); onClick?.(); }}
      className="t-btn-primary inline-flex items-center justify-center gap-2"
      style={{ paddingLeft: '24px', paddingRight: '24px', height: '48px', fontWeight: 600 }}
    >
      {icon && <Sparkles size={16} strokeWidth={2} />}
      {children}
    </Link>
  );
}

function SecondaryCTA({ to, from, children }) {
  const href = `${to}?from=landing_${from}`;
  return (
    <Link
      to={href}
      onClick={() => track('landing_cta_click', { cta: 'secondary', from })}
      className="t-btn-secondary inline-flex items-center justify-center gap-2"
      style={{ paddingLeft: '24px', paddingRight: '24px', height: '48px', fontWeight: 600 }}
    >
      {children}
      <ArrowRight size={16} strokeWidth={2} />
    </Link>
  );
}

function LogoMark({ size = 32 }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 'var(--radius-card)',
        background: 'linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: 'var(--shadow-btn)',
      }}
    >
      <span style={{ color: '#fff', fontWeight: 800, fontSize: size * 0.45, letterSpacing: '-0.04em' }}>G</span>
    </div>
  );
}

/* Tiny inline SVG sparkline (no heavy chart lib on marketing page).
   stroke uses CSS variable so theme can swap colors without code change. */
function Sparkline({ points, strokeVar = '--color-chart-1', width = 160, height = 36 }) {
  if (!points?.length) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = width / (points.length - 1);
  const d = points
    .map((v, i) => {
      const x = i * step;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
      <path d={d} fill="none" stroke={`var(${strokeVar})`} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ──────────────────────────────────────────────────────────────
   Sections
   ────────────────────────────────────────────────────────────── */

function Masthead({ locale, setLocale, t }) {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        backgroundColor: 'rgba(255,255,255,0.85)',
        backdropFilter: 'saturate(180%) blur(8px)',
        borderBottom: '1px solid var(--color-border-card)',
      }}
    >
      <div className={`${MAX_W} flex items-center justify-between`} style={{ height: 64 }}>
        <Link to="/" className="flex items-center gap-2" aria-label="GENPANO home">
          <LogoMark size={28} />
          <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}>
            GENPANO
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-7">
          {[
            { label: t.nav.product, href: '#product' },
            { label: t.nav.method, href: '#method' },
            { label: t.nav.industries, href: '#industries' },
            { label: t.nav.agents, href: '#agents' },
          ].map((l) => (
            <a
              key={l.href}
              href={l.href}
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--color-text-body-soft)',
                textDecoration: 'none',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-text-primary)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--color-text-body-soft)')}
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              const next = locale === 'zh-CN' ? 'en-US' : 'zh-CN';
              setLocale(next);
              track('landing_locale_switch', { from: locale, to: next });
            }}
            className="inline-flex items-center gap-1.5"
            style={{
              height: 32,
              padding: '0 10px',
              borderRadius: 'var(--radius-btn)',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--color-text-body-soft)',
              backgroundColor: 'transparent',
              border: '1px solid var(--color-border-card)',
              cursor: 'pointer',
            }}
            aria-label="Toggle language"
          >
            <Globe size={12} strokeWidth={2} />
            {locale === 'zh-CN' ? 'EN' : '中文'}
          </button>

          {/* PRD §4.1.1d E3 — Landing nav quick-create button.
              Three auth/project states live inside the component; it is intentionally
              low-contrast so it never out-weighs the hero CTA. */}
          <LandingNavQuickCreateButton />

          <Link
            to="/login?from=landing_nav"
            onClick={() => track('landing_cta_click', { cta: 'tertiary', from: 'nav' })}
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: 'var(--color-text-body-soft)',
              textDecoration: 'none',
            }}
          >
            {t.nav.login}
          </Link>
          <Link
            to="/register?from=landing_nav"
            onClick={() => track('landing_cta_click', { cta: 'primary', from: 'nav' })}
            className="t-btn-primary inline-flex items-center gap-2"
            style={{ paddingLeft: 16, paddingRight: 16, height: 36, fontSize: 13 }}
          >
            <Sparkles size={14} strokeWidth={2} />
            {t.nav.register}
          </Link>
        </div>
      </div>
    </header>
  );
}

function Hero({ t }) {
  return (
    <section
      style={{
        backgroundColor: 'var(--color-bg-page)',
        paddingTop: 88,
        paddingBottom: 96,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Subtle radial glow */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: -220,
          right: -180,
          width: 620,
          height: 620,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(96, 91, 255, 0.12) 0%, transparent 60%)',
          pointerEvents: 'none',
        }}
      />

      <div className={MAX_W} style={{ position: 'relative' }}>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          <div className="lg:col-span-7">
            <Eyebrow>{t.hero.eyebrow}</Eyebrow>
            <h1
              style={{
                marginTop: 20,
                fontSize: 'clamp(40px, 6vw, 68px)',
                lineHeight: 1.05,
                fontWeight: 800,
                letterSpacing: '-0.03em',
                color: 'var(--color-text-primary)',
              }}
            >
              {t.hero.h1_a}
              <br />
              <span
                style={{
                  background: 'linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                {t.hero.h1_highlight}
              </span>
              {t.hero.h1_b}
            </h1>

            <p
              style={{
                marginTop: 24,
                maxWidth: 640,
                fontSize: 18,
                lineHeight: 1.6,
                color: 'var(--color-text-body-soft)',
              }}
            >
              {t.hero.sub}
            </p>

            <div style={{ marginTop: 36 }} className="flex flex-wrap items-center gap-3">
              <PrimaryCTA to="/register" from="hero_primary">{t.hero.cta_primary}</PrimaryCTA>
              <SecondaryCTA to="/industry" from="hero_secondary">{t.hero.cta_secondary}</SecondaryCTA>
              <Link
                to="/login?from=landing_hero_tertiary"
                onClick={() => track('landing_cta_click', { cta: 'tertiary', from: 'hero' })}
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: 'var(--color-text-body-soft)',
                  textDecoration: 'none',
                  marginLeft: 4,
                }}
              >
                {t.hero.cta_tertiary} →
              </Link>
            </div>

            <p
              style={{
                marginTop: 28,
                fontSize: 13,
                fontWeight: 500,
                color: 'var(--color-text-body-soft)',
                letterSpacing: '0.01em',
              }}
            >
              {t.hero.meta}
            </p>
          </div>

          <div className="lg:col-span-5">
            <HeroVisual />
          </div>
        </div>
      </div>
    </section>
  );
}

function HeroVisual() {
  // Flat dashboard-ish preview card, no browser chrome, no mac dots
  return (
    <div
      style={{
        backgroundColor: 'var(--color-bg-card)',
        borderRadius: 'var(--radius-card-lg)',
        border: '1px solid var(--color-border-card)',
        boxShadow: 'var(--shadow-elevated)',
        padding: 20,
      }}
    >
      <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-body-soft)', letterSpacing: '0.04em' }}>
          DASHBOARD · 面板
        </div>
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--color-accent)',
            backgroundColor: 'rgba(96, 91, 255, 0.1)',
            padding: '2px 8px',
            borderRadius: '999px',
          }}
        >
          LIVE
        </div>
      </div>

      {/* PanoScore Hero */}
      <div
        style={{
          backgroundColor: 'var(--color-bg-page)',
          borderRadius: 'var(--radius-card)',
          padding: '20px 18px',
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 11, color: 'var(--color-text-body-soft)', marginBottom: 6 }}>Brand A · 综合</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span
            style={{
              fontSize: 44,
              fontWeight: 800,
              letterSpacing: '-0.03em',
              background: 'linear-gradient(135deg, #605BFF 0%, #8B5CF6 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            82
          </span>
          <span style={{ fontSize: 13, color: 'var(--color-text-body-soft)', fontWeight: 500 }}>PANO Score</span>
          <span
            style={{
              marginLeft: 'auto',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--color-success, #16A34A)',
            }}
          >
            +6.2 WoW
          </span>
        </div>
        <div style={{ marginTop: 10 }}>
          <Sparkline
            points={[62, 64, 60, 68, 70, 74, 72, 78, 76, 80, 82]}
            strokeVar="--color-chart-1"
            width={320}
            height={40}
          />
        </div>
      </div>

      {/* 5 KPI grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          gap: 8,
        }}
      >
        {[
          { k: '提及率', v: '16.2%', stroke: '--color-chart-1' },
          { k: 'SoV', v: '24%', stroke: '--color-chart-2' },
          { k: '情感', v: '+0.79', stroke: '--color-chart-3' },
          { k: '引用', v: '11%', stroke: '--color-chart-4' },
          { k: '排名', v: '#2', stroke: '--color-chart-5' },
        ].map((m) => (
          <div
            key={m.k}
            style={{
              backgroundColor: 'var(--color-bg-page)',
              borderRadius: 'var(--radius-card)',
              padding: 10,
            }}
          >
            <div style={{ fontSize: 10, color: 'var(--color-text-body-soft)' }}>{m.k}</div>
            <div
              style={{
                fontSize: 16,
                fontWeight: 700,
                color: 'var(--color-text-primary)',
                marginTop: 2,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {m.v}
            </div>
            <div style={{ marginTop: 4 }}>
              <Sparkline
                points={Array.from({ length: 8 }, () => 40 + Math.floor(Math.random() * 40))}
                strokeVar={m.stroke}
                width={80}
                height={20}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Problem({ t }) {
  return (
    <section style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <h2
            style={{
              fontSize: 'clamp(28px, 3.6vw, 40px)',
              lineHeight: 1.2,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: 'var(--color-text-primary)',
            }}
          >
            {t.problem.title}
          </h2>
          <p
            style={{
              marginTop: 16,
              fontSize: 17,
              lineHeight: 1.6,
              color: 'var(--color-text-body-soft)',
            }}
          >
            {t.problem.subtitle}
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4" style={{ marginTop: 40 }}>
          <ComparisonCard
            tone="muted"
            icon={<X size={18} strokeWidth={2} />}
            title={t.problem.left_title}
            items={t.problem.left_items}
          />
          <ComparisonCard
            tone="accent"
            icon={<Check size={18} strokeWidth={2} />}
            title={t.problem.right_title}
            items={t.problem.right_items}
          />
        </div>
      </div>
    </section>
  );
}

function ComparisonCard({ tone, icon, title, items }) {
  const accent = tone === 'accent';
  return (
    <div
      className="t-card"
      style={{
        padding: 28,
        borderColor: accent ? 'rgba(96, 91, 255, 0.3)' : 'var(--color-border-card)',
        boxShadow: accent ? '0 8px 24px rgba(96, 91, 255, 0.08)' : 'var(--shadow-card)',
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 'var(--radius-card)',
          backgroundColor: accent ? 'rgba(96, 91, 255, 0.12)' : 'var(--color-bg-page)',
          color: accent ? 'var(--color-accent)' : 'var(--color-text-body-soft)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 16,
        }}
      >
        {icon}
      </div>
      <h3
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: 'var(--color-text-primary)',
          marginBottom: 12,
        }}
      >
        {title}
      </h3>
      <ul style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map((i, idx) => (
          <li
            key={idx}
            style={{
              fontSize: 15,
              lineHeight: 1.55,
              color: accent ? 'var(--color-text-primary)' : 'var(--color-text-body-soft)',
              paddingLeft: 20,
              position: 'relative',
            }}
          >
            <span
              style={{
                position: 'absolute',
                left: 0,
                top: 9,
                width: 6,
                height: 6,
                borderRadius: 3,
                backgroundColor: accent ? 'var(--color-accent)' : 'var(--color-border-card)',
              }}
            />
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Method({ t }) {
  return (
    <section id="method" style={{ backgroundColor: 'var(--color-bg-page)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <Eyebrow>{t.method.eyebrow}</Eyebrow>
          <h2
            style={{
              marginTop: 16,
              fontSize: 'clamp(28px, 3.6vw, 40px)',
              lineHeight: 1.2,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: 'var(--color-text-primary)',
            }}
          >
            {t.method.title}
          </h2>
          <p style={{ marginTop: 12, fontSize: 17, color: 'var(--color-text-body-soft)', lineHeight: 1.55 }}>
            {t.method.subtitle}
          </p>
        </div>

        {/* Formula card */}
        <div
          className="t-card"
          style={{ marginTop: 32, padding: 24, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}
        >
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: 'var(--color-text-body-soft)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}
          >
            {t.method.formula_label}
          </span>
          <code
            style={{
              fontFamily: 'Nunito, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
              fontSize: 14,
              color: 'var(--color-text-primary)',
              fontWeight: 600,
              backgroundColor: 'var(--color-bg-page)',
              padding: '10px 14px',
              borderRadius: 'var(--radius-btn)',
              border: '1px solid var(--color-border-card)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {t.method.formula}
          </code>
        </div>

        {/* 5 dim cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3" style={{ marginTop: 20 }}>
          {t.method.dims.map((d, i) => (
            <div key={i} className="t-card" style={{ padding: 18 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 4,
                  backgroundColor: `var(--color-${d.tone})`,
                  marginBottom: 10,
                }}
              />
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  color: 'var(--color-text-primary)',
                  marginBottom: 6,
                }}
              >
                {d.k}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--color-text-body-soft)' }}>
                {d.v}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ProductBento({ t }) {
  const icons = [
    <Gauge size={18} strokeWidth={2} key="g" />,
    <BarChart3 size={18} strokeWidth={2} key="b" />,
    <Search size={18} strokeWidth={2} key="s" />,
    <Network size={18} strokeWidth={2} key="n" />,
  ];
  return (
    <section id="product" style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <Eyebrow>{t.product.eyebrow}</Eyebrow>
          <h2
            style={{
              marginTop: 16,
              fontSize: 'clamp(28px, 3.6vw, 40px)',
              lineHeight: 1.2,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: 'var(--color-text-primary)',
            }}
          >
            {t.product.title}
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4" style={{ marginTop: 36 }}>
          {t.product.cards.map((c, i) => (
            <div key={i} className="t-card" style={{ padding: 28 }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 'var(--radius-card)',
                    backgroundColor: 'rgba(96, 91, 255, 0.10)',
                    color: 'var(--color-accent)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {icons[i]}
                </div>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: 'var(--color-text-body-soft)',
                    backgroundColor: 'var(--color-bg-page)',
                    padding: '4px 10px',
                    borderRadius: '999px',
                    letterSpacing: '0.04em',
                  }}
                >
                  {c.badge}
                </span>
              </div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text-primary)', marginBottom: 10 }}>
                {c.title}
              </h3>
              <p style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--color-text-body-soft)' }}>{c.desc}</p>

              <div style={{ marginTop: 18 }}>
                <Sparkline
                  points={[30, 42, 38, 54, 48, 62, 60, 72, 68, 80]}
                  strokeVar={`--color-chart-${(i % 5) + 1}`}
                  width={260}
                  height={34}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Industries({ t }) {
  return (
    <section id="industries" style={{ backgroundColor: 'var(--color-bg-page)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 760 }}>
          <Eyebrow>{t.industries.eyebrow}</Eyebrow>
          <h2
            style={{
              marginTop: 16,
              fontSize: 'clamp(28px, 3.6vw, 40px)',
              lineHeight: 1.2,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: 'var(--color-text-primary)',
            }}
          >
            {t.industries.title}
          </h2>
          <p style={{ marginTop: 12, fontSize: 16, color: 'var(--color-text-body-soft)', lineHeight: 1.55 }}>
            {t.industries.subtitle}
          </p>
        </div>

        <div className="t-card" style={{ marginTop: 28, padding: 8, overflow: 'hidden' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFeatureSettings: '"tnum"',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border-card)' }}>
                {['', t.industries.col.brand, t.industries.col.query, t.industries.col.engine, t.industries.col.status, ''].map(
                  (h, i) => (
                    <th
                      key={i}
                      style={{
                        textAlign: i === 0 || i === 5 ? 'left' : 'right',
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--color-text-body-soft)',
                        padding: '14px 16px',
                        letterSpacing: '0.06em',
                        textTransform: 'uppercase',
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {t.industries.table.map((row, i) => (
                <tr
                  key={row.slug}
                  style={{
                    borderBottom:
                      i === t.industries.table.length - 1 ? 'none' : '1px solid var(--color-border-card)',
                  }}
                >
                  <td
                    style={{
                      padding: '18px 16px',
                      fontSize: 15,
                      fontWeight: 600,
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    {row.name}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right', color: 'var(--color-text-body-soft)' }}>
                    {row.brands}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right', color: 'var(--color-text-body-soft)' }}>
                    {row.queries}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right', color: 'var(--color-text-body-soft)' }}>
                    {row.engines}
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right' }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--color-success, #16A34A)',
                        backgroundColor: 'rgba(22, 163, 74, 0.10)',
                        padding: '3px 8px',
                        borderRadius: '999px',
                      }}
                    >
                      ● {row.status}
                    </span>
                  </td>
                  <td style={{ padding: '18px 16px', textAlign: 'right' }}>
                    <Link
                      to={`/industry?category=${row.slug}&from=landing_industries_row`}
                      onClick={() =>
                        track('landing_cta_click', { cta: 'industries_row', from: 'industries_row', category: row.slug })
                      }
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: 'var(--color-accent)',
                        textDecoration: 'none',
                      }}
                    >
                      {t.industries.view}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'center' }}>
          <SecondaryCTA to="/industry" from="industries_browse_all">
            {t.industries.browse_all}
          </SecondaryCTA>
        </div>
      </div>
    </section>
  );
}

function Voices({ t }) {
  return (
    <section style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div style={{ maxWidth: 720 }}>
          <Eyebrow>{t.voices.eyebrow}</Eyebrow>
          <h2
            style={{
              marginTop: 16,
              fontSize: 'clamp(28px, 3.6vw, 40px)',
              lineHeight: 1.2,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: 'var(--color-text-primary)',
            }}
          >
            {t.voices.title}
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4" style={{ marginTop: 32 }}>
          {t.voices.items.map((v, i) => (
            <div key={i} className="t-card" style={{ padding: 28, display: 'flex', flexDirection: 'column', gap: 20 }}>
              <p
                style={{
                  fontSize: 15,
                  lineHeight: 1.65,
                  color: 'var(--color-text-primary)',
                  fontWeight: 500,
                }}
              >
                “{v.quote}”
              </p>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 13, color: 'var(--color-text-body-soft)' }}>{v.who}</div>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: 'var(--color-accent)',
                    backgroundColor: 'rgba(96, 91, 255, 0.10)',
                    padding: '3px 10px',
                    borderRadius: '999px',
                  }}
                >
                  {v.brand}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ForAgents({ t }) {
  const icons = {
    code: <Code2 size={16} strokeWidth={2} />,
    shield: <Shield size={16} strokeWidth={2} />,
    cpu: <Cpu size={16} strokeWidth={2} />,
  };
  return (
    <section id="agents" style={{ backgroundColor: 'var(--color-bg-page)', paddingTop: 96, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
          <div className="lg:col-span-5">
            <Eyebrow>{t.agents.eyebrow}</Eyebrow>
            <h2
              style={{
                marginTop: 16,
                fontSize: 'clamp(28px, 3.6vw, 40px)',
                lineHeight: 1.2,
                fontWeight: 800,
                letterSpacing: '-0.02em',
                color: 'var(--color-text-primary)',
              }}
            >
              {t.agents.title}
            </h2>
            <p style={{ marginTop: 14, fontSize: 16, lineHeight: 1.6, color: 'var(--color-text-body-soft)' }}>
              {t.agents.subtitle}
            </p>

            <ul style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 14 }}>
              {t.agents.features.map((f, i) => (
                <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                  <span
                    style={{
                      flex: 'none',
                      width: 32,
                      height: 32,
                      borderRadius: 'var(--radius-btn)',
                      backgroundColor: 'rgba(96, 91, 255, 0.10)',
                      color: 'var(--color-accent)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {icons[f.icon]}
                  </span>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}>{f.title}</div>
                    <div style={{ fontSize: 13, color: 'var(--color-text-body-soft)', marginTop: 2 }}>{f.desc}</div>
                  </div>
                </li>
              ))}
            </ul>

            <div style={{ marginTop: 28 }}>
              <Link
                to="/register?from=landing_agents&focus=mcp"
                onClick={() => track('landing_cta_click', { cta: 'agents', from: 'agents', focus: 'mcp' })}
                className="t-btn-primary inline-flex items-center gap-2"
                style={{ paddingLeft: 20, paddingRight: 20, height: 44 }}
              >
                <Sparkles size={14} strokeWidth={2} />
                {t.agents.cta}
              </Link>
            </div>
          </div>

          <div className="lg:col-span-7">
            <div
              className="t-card"
              style={{
                padding: 0,
                overflow: 'hidden',
                boxShadow: 'var(--shadow-elevated)',
              }}
            >
              {/* File header — NO macOS terminal dots */}
              <div
                style={{
                  padding: '12px 16px',
                  borderBottom: '1px solid var(--color-border-card)',
                  backgroundColor: 'var(--color-bg-page)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <FileText size={14} strokeWidth={2} style={{ color: 'var(--color-text-body-soft)' }} />
                <span
                  style={{
                    fontSize: 12,
                    fontFamily: 'Nunito, ui-monospace, SFMono-Regular, Menlo, monospace',
                    fontWeight: 600,
                    color: 'var(--color-text-body-soft)',
                  }}
                >
                  {t.agents.code_title}
                </span>
              </div>
              <pre
                style={{
                  margin: 0,
                  padding: 20,
                  fontFamily: 'Nunito, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                  fontSize: 13,
                  lineHeight: 1.65,
                  color: 'var(--color-text-primary)',
                  backgroundColor: 'var(--color-bg-card)',
                  overflowX: 'auto',
                }}
              >
                <code>{t.agents.code}</code>
              </pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FinalCTA({ t }) {
  return (
    <section style={{ backgroundColor: 'var(--color-bg-card)', paddingTop: 60, paddingBottom: 96 }}>
      <div className={MAX_W}>
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 'var(--radius-banner)',
            padding: '56px 48px',
            background:
              'linear-gradient(135deg, rgba(96,91,255,0.08) 0%, rgba(139,92,246,0.08) 100%), var(--color-bg-card)',
            border: '1px solid rgba(96, 91, 255, 0.22)',
          }}
        >
          {/* Decorative glow */}
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: -120,
              right: -80,
              width: 360,
              height: 360,
              borderRadius: '50%',
              background: 'radial-gradient(circle, rgba(96, 91, 255, 0.18) 0%, transparent 60%)',
              pointerEvents: 'none',
            }}
          />
          <div style={{ position: 'relative', maxWidth: 720 }}>
            <h2
              style={{
                fontSize: 'clamp(28px, 3.6vw, 40px)',
                lineHeight: 1.2,
                fontWeight: 800,
                letterSpacing: '-0.02em',
                color: 'var(--color-text-primary)',
              }}
            >
              {t.final.title}
            </h2>
            <p style={{ marginTop: 14, fontSize: 17, lineHeight: 1.55, color: 'var(--color-text-body-soft)' }}>
              {t.final.subtitle}
            </p>
            <div style={{ marginTop: 28 }} className="flex flex-wrap gap-3">
              <PrimaryCTA to="/register" from="final_primary">{t.final.cta_primary}</PrimaryCTA>
              <SecondaryCTA to="/industry" from="final_secondary">{t.final.cta_secondary}</SecondaryCTA>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer({ t }) {
  return (
    <footer
      style={{
        backgroundColor: 'var(--color-bg-card)',
        borderTop: '1px solid var(--color-border-card)',
        paddingTop: 56,
        paddingBottom: 40,
      }}
    >
      <div className={MAX_W}>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10">
          <div>
            <Link to="/" className="flex items-center gap-2" style={{ textDecoration: 'none' }}>
              <LogoMark size={28} />
              <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--color-text-primary)' }}>
                GENPANO
              </span>
            </Link>
            <p style={{ marginTop: 14, fontSize: 13, lineHeight: 1.55, color: 'var(--color-text-body-soft)' }}>
              {t.footer.tagline}
            </p>
          </div>

          <FooterCol title={t.footer.col_product} links={t.footer.links.product} />
          <FooterCol title={t.footer.col_resources} links={t.footer.links.resources} />
          <FooterCol title={t.footer.col_company} links={t.footer.links.company} />
        </div>

        <div
          className="flex items-center justify-between flex-wrap gap-4"
          style={{
            marginTop: 40,
            paddingTop: 24,
            borderTop: '1px solid var(--color-border-card)',
            fontSize: 13,
            color: 'var(--color-text-body-soft)',
          }}
        >
          <span>{t.footer.copyright}</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <Globe size={13} strokeWidth={2} />
            {t.footer.lang_label}
          </span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }) {
  return (
    <div>
      <h4
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: 'var(--color-text-primary)',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          marginBottom: 14,
        }}
      >
        {title}
      </h4>
      <ul style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {links.map((l, i) => (
          <li key={i}>
            <span
              style={{
                fontSize: 13,
                color: 'var(--color-text-body-soft)',
              }}
            >
              {l}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────
   MAIN
   ────────────────────────────────────────────────────────────── */
export default function LandingPage() {
  const [locale, setLocale] = useLocale();
  const t = COPY[locale];

  return (
    <div style={{ backgroundColor: 'var(--color-bg-page)', minHeight: '100vh' }}>
      <Masthead locale={locale} setLocale={setLocale} t={t} />
      <main>
        <Hero t={t} />
        <Problem t={t} />
        <Method t={t} />
        <ProductBento t={t} />
        <Industries t={t} />
        <Voices t={t} />
        <ForAgents t={t} />
        <FinalCTA t={t} />
      </main>
      <Footer t={t} />
    </div>
  );
}
