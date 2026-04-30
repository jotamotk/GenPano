import { useEffect, useMemo, useState } from 'react'
import { useLanguage } from '../context/LanguageContext'

const ENGINES = [
  { name: 'ChatGPT', color: 'var(--color-success)' },
  { name: '豆包', enName: 'Doubao', color: 'var(--color-chart-2)' },
  { name: 'DeepSeek', color: 'var(--color-chart-3)' },
]

const COPY = {
  zh: {
    badge: '生成引擎优化 · GEO',
    headlineA: '看见 AI 答案里的',
    headlineB: '品牌位次。',
    features: [
      '覆盖 ChatGPT、豆包、DeepSeek 等主流生成式引擎',
      '追踪 Nike、GUCCI、Louis Vuitton 等品牌在 AI 答案中的出现率和排序',
      '当竞品进入高意图答案，及时提示销售与运营团队',
    ],
    scoreTitle: 'Nike / GUCCI / Louis Vuitton — GEO 得分',
    queriesTitle: '实时查询',
    queryCount: '今日 12,408 条',
    queries: [
      'Nike 和 ASICS 哪个更适合宽脚通勤跑？',
      'GUCCI 入门款包袋，预算 1.5 万怎么选？',
      'ZEGNA 与 BOSS 男士商务西装差异？',
      'Louis Vuitton 经典包型适合送礼吗？',
      "Salomon、ARC'TERYX 徒步装备怎么搭？",
      'CHANEL 香水和 Valentino 美妆怎么选？',
      'Crocs 洞洞鞋夏季穿搭推荐',
      'Max Mara 大衣经典款怎么选？',
      'ROLEX 入门款腕表有哪些选择？',
    ],
    brandLabel: '联蔚官网公开品牌',
    brands: ['ZEGNA', 'BOSS', 'VALENTINO', 'CHANEL', 'GUCCI', 'Louis Vuitton', 'Nike', 'ASICS', 'Salomon', 'Crocs'],
  },
  en: {
    badge: 'Generative Engine Optimization · GEO',
    headlineA: 'See where brands rank',
    headlineB: 'inside AI answers.',
    features: [
      'Cover ChatGPT, Doubao, DeepSeek and other mainstream generative engines',
      'Track visibility and ranking for Nike, GUCCI, Louis Vuitton and other brands inside AI answers',
      'Alert sales and operations teams when competitors enter high-intent answers',
    ],
    scoreTitle: 'Nike / GUCCI / Louis Vuitton — GEO score',
    queriesTitle: 'Live Queries',
    queryCount: '12,408 today',
    queries: [
      'Nike vs ASICS for wide-foot daily running shoes',
      'best entry GUCCI bag under a clear budget',
      'ZEGNA vs BOSS for men’s business suits',
      'is a classic Louis Vuitton bag a good gift?',
      "Salomon and ARC'TERYX hiking kit combinations",
      'CHANEL fragrance vs Valentino beauty gifts',
      'Crocs summer styling ideas',
      'classic Max Mara coat recommendations',
      'entry ROLEX watches for daily wear',
    ],
    brandLabel: 'Brands shown on LianWei site',
    brands: ['ZEGNA', 'BOSS', 'VALENTINO', 'CHANEL', 'GUCCI', 'Louis Vuitton', 'Nike', 'ASICS', 'Salomon', 'Crocs'],
  },
}

const W = 720
const H = 122
const PAD_X = 34
const PAD_Y = 18
const POINTS = 30

function useTicker(intervalMs: number) {
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => {
      setTick(value => value + 1)
    }, intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])

  return tick
}

function xFor(index: number) {
  return PAD_X + (index / (POINTS - 1)) * (W - PAD_X * 2)
}

function yFor(value: number) {
  return PAD_Y + (1 - value / 100) * (H - PAD_Y * 2)
}

function createSeries(tick: number) {
  return ENGINES.map((engine, engineIndex) => {
    const values = Array.from({ length: POINTS }, (_, index) => {
      const progress = index / (POINTS - 1)
      const wave =
        Math.sin((progress * Math.PI * 4.2) + tick * 0.28 + engineIndex * 1.55) * 13 +
        Math.cos((progress * Math.PI * 2.4) + tick * 0.14 + engineIndex * 0.82) * 6
      const trend = (progress - 0.5) * (engineIndex === 1 ? 5 : 10)
      return Math.max(24, Math.min(82, 52 + wave + trend + engineIndex * 2))
    })
    const path = values
      .map((value, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index).toFixed(1)} ${yFor(value).toFixed(1)}`)
      .join(' ')
    const area = `${path} L ${xFor(POINTS - 1).toFixed(1)} ${H - PAD_Y} L ${xFor(0).toFixed(1)} ${H - PAD_Y} Z`
    return { ...engine, values, path, area }
  })
}

export default function AuthVisualPanel() {
  const { language } = useLanguage()
  const isZh = language === 'zh'
  const content = isZh ? COPY.zh : COPY.en
  const chartTick = useTicker(1600)
  const queryTick = useTicker(2600)

  const series = useMemo(() => createSeries(chartTick), [chartTick])
  const score = 78 + Math.round(Math.sin(chartTick * 0.45) * 4)
  const visibleQueries = useMemo(
    () => Array.from({ length: 5 }, (_, index) => content.queries[(queryTick + index) % content.queries.length]),
    [content.queries, queryTick],
  )

  return (
    <aside
      className="hidden lg:flex flex-1 min-w-0 flex-col relative overflow-hidden border-r"
      style={{
        background: 'var(--color-auth-visual-bg)',
        borderColor: 'var(--color-border-subtle)',
      }}
      aria-hidden="true"
    >
      <div
        className="flex h-screen w-full justify-center overflow-hidden"
        style={{
          paddingBlock: 'clamp(22px, 3.4vh, 40px)',
          paddingInline: 'clamp(32px, 4.5vw, 64px)',
        }}
      >
        <div
          className="flex h-full w-full flex-col"
          style={{ maxWidth: 'min(100%, clamp(620px, 40vw, 760px))' }}
        >
          <div
            className="mb-4 inline-flex w-fit items-center gap-2 rounded-pill border bg-white/88 px-3 py-1.5 text-sm font-medium shadow-sm"
            style={{
              color: 'var(--color-text-secondary)',
              borderColor: 'var(--color-border-subtle)',
            }}
          >
            <span
              className="flex h-4 w-4 items-center justify-center rounded-pill"
              style={{ background: 'var(--color-accent-subtle)' }}
            >
              <span className="h-2 w-2 rounded-pill" style={{ background: 'var(--color-accent)' }} />
            </span>
            {content.badge}
          </div>

          <h2
            className="font-brand font-semibold"
            style={{
              color: 'var(--color-text-primary)',
              fontSize: 'clamp(34px, 4.75vh, 48px)',
              lineHeight: 1.04,
              letterSpacing: 0,
            }}
          >
            <span className="block">{content.headlineA}</span>
            <span
              className="block bg-clip-text text-transparent"
              style={{
                backgroundImage: 'linear-gradient(135deg, var(--color-accent) 0%, var(--color-chart-3) 100%)',
              }}
            >
              {content.headlineB}
            </span>
          </h2>

          <ul className="space-y-1.5" style={{ marginTop: 'clamp(16px, 2vh, 22px)' }}>
            {content.features.map(item => (
              <li key={item} className="flex items-start gap-3 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                <span
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-pill"
                  style={{ background: 'var(--color-accent-subtle)', color: 'var(--color-accent)' }}
                >
                  <CheckIcon />
                </span>
                <span className="leading-6">{item}</span>
              </li>
            ))}
          </ul>

          <div className="min-h-0 flex-1 space-y-3" style={{ marginTop: 'clamp(18px, 2.4vh, 26px)' }}>
            <section
              className="rounded-card-lg border bg-white shadow-card-hover"
              style={{
                borderColor: 'var(--color-border-subtle)',
                padding: 'clamp(12px, 1.55vh, 16px)',
              }}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 items-center gap-2 text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                  <span className="h-2.5 w-2.5 shrink-0 rounded-pill" style={{ background: 'var(--color-chart-3)' }} />
                  <span className="truncate">{content.scoreTitle}</span>
                </div>
                <div className="flex shrink-0 items-baseline gap-2">
                  <span className="font-mono text-3xl font-semibold leading-none text-themed-primary">{score}</span>
                  <span className="text-xs font-semibold text-themed-success">▲ 4.2</span>
                </div>
              </div>

              <div className="mt-3 overflow-hidden" style={{ height: 'clamp(78px, 11.5vh, 128px)' }}>
                <svg
                  className="h-full w-full"
                  viewBox={`0 0 ${W} ${H}`}
                  preserveAspectRatio="xMidYMid meet"
                  role="presentation"
                >
                  <defs>
                    {series.map((item, index) => (
                      <linearGradient key={item.name} id={`auth-visual-grad-${index}`} x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor={item.color} stopOpacity="0.2" />
                        <stop offset="100%" stopColor={item.color} stopOpacity="0" />
                      </linearGradient>
                    ))}
                    <linearGradient id="auth-visual-fade" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="white" stopOpacity="0" />
                      <stop offset="100%" stopColor="white" stopOpacity="0.72" />
                    </linearGradient>
                  </defs>
                  {[0.25, 0.5, 0.75].map(grid => (
                    <line
                      key={grid}
                      x1={PAD_X}
                      x2={W - PAD_X}
                      y1={PAD_Y + grid * (H - PAD_Y * 2)}
                      y2={PAD_Y + grid * (H - PAD_Y * 2)}
                      stroke="var(--color-border-subtle)"
                      strokeDasharray="4 10"
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}
                  {series.map((item, index) => {
                    const lastValue = item.values[item.values.length - 1]
                    return (
                      <g key={item.name}>
                        <path d={item.area} fill={`url(#auth-visual-grad-${index})`} />
                        <path
                          d={item.path}
                          fill="none"
                          stroke={item.color}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2.8"
                          vectorEffect="non-scaling-stroke"
                        />
                        <circle cx={xFor(POINTS - 1)} cy={yFor(lastValue)} r="4.5" fill={item.color} />
                      </g>
                    )
                  })}
                  <rect x="0" y={H - 38} width={W} height="38" fill="url(#auth-visual-fade)" />
                </svg>
              </div>

              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                {ENGINES.map(engine => (
                  <span key={engine.name} className="inline-flex items-center gap-2">
                    <span className="h-1.5 w-4 rounded-pill" style={{ background: engine.color }} />
                    {isZh ? engine.name : engine.enName || engine.name}
                  </span>
                ))}
              </div>
            </section>

            <section
              className="rounded-card-lg border bg-white shadow-card"
              style={{
                borderColor: 'var(--color-border-subtle)',
                padding: 'clamp(12px, 1.55vh, 16px)',
              }}
            >
              <div className="mb-2 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
                  <span className="h-2.5 w-2.5 rounded-pill" style={{ background: 'var(--color-danger)' }} />
                  {content.queriesTitle}
                </div>
                <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>{content.queryCount}</span>
              </div>

              <div>
                {visibleQueries.map((query, index) => (
                  <div
                    key={`${query}-${queryTick}`}
                    className={`animate-fade-in grid grid-cols-[12px_minmax(0,1fr)_34px] items-center gap-3 border-t text-sm ${
                      index === 4 ? '[@media(max-height:760px)]:hidden' : ''
                    }`}
                    style={{
                      borderColor: 'var(--color-border-subtle)',
                      color: 'var(--color-text-secondary)',
                      paddingBlock: 'clamp(5px, 0.78vh, 9px)',
                    }}
                  >
                    <span
                      className="h-2.5 w-2.5 rounded-pill"
                      style={{ background: ENGINES[(queryTick + index) % ENGINES.length].color }}
                    />
                    <span className="truncate">{query}</span>
                    <span className="text-right font-medium" style={{ color: 'var(--color-text-muted)' }}>
                      #{index + 1}
                    </span>
                  </div>
                ))}
              </div>
            </section>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
              <span>{content.brandLabel}</span>
              {content.brands.map((brand, index) => (
                <span key={brand} className="inline-flex items-center gap-1.5">
                  <span
                    className="h-1.5 w-1.5 rounded-pill"
                    style={{ background: ENGINES[index % ENGINES.length].color }}
                  />
                  {brand}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}

function CheckIcon() {
  return (
    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.4} d="M5 13l4 4L19 7" />
    </svg>
  )
}
