/**
 * Landing page localization dictionary.
 *
 * Moved verbatim from LandingPage.tsx (lines 43-359). Do not edit copy here
 * without product/i18n sign-off; this is a behavior-preserving move.
 */
export const COPY = {
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
          title: '面板 · 品牌总览',
          desc: '核心 KPI、PANO、竞品象限与趋势集中展示。',
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
      title: 'From brand overview to product drilldown',
      cards: [
        {
          title: 'Dashboard · Brand overview',
          desc: 'Core KPIs, PANO, competitor quadrant, and trend in one view.',
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
