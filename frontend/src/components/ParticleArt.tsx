const METRICS = [
  { label: 'Visibility', value: '64%', color: 'var(--color-accent)' },
  { label: 'Sentiment', value: '+8.4', color: 'var(--color-success)' },
  { label: 'Citations', value: '128', color: 'var(--color-chart-3)' },
]

const SIGNALS = [
  { x: 78, y: 116, label: 'Prompt' },
  { x: 78, y: 214, label: 'Brand' },
  { x: 78, y: 312, label: 'Citation' },
  { x: 442, y: 142, label: 'Topic' },
  { x: 442, y: 260, label: 'Intent' },
  { x: 442, y: 342, label: 'Report' },
]

export default function ParticleArt() {
  return (
    <div
      className="relative w-full h-full overflow-hidden select-none"
      style={{ background: 'var(--color-auth-visual-bg)' }}
    >
      <div className="absolute inset-0 opacity-[0.55]" aria-hidden="true">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(var(--color-auth-graph-line) 1px, transparent 1px), linear-gradient(90deg, var(--color-auth-graph-line) 1px, transparent 1px)',
            backgroundSize: '36px 36px',
          }}
        />
      </div>

      <div
        className="absolute left-1/2 top-1/2 w-[min(82%,560px)] aspect-[1.18] -translate-x-1/2 -translate-y-1/2 rounded-[28px] border bg-white/85 shadow-[0_22px_70px_rgba(28,34,58,0.14)]"
        style={{ borderColor: 'var(--color-border-subtle)' }}
      >
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 560 474" role="img" aria-label="GenPano brand signal visualization">
          <defs>
            <linearGradient id="signalLine" x1="70" y1="120" x2="490" y2="340" gradientUnits="userSpaceOnUse">
              <stop stopColor="#605BFF" stopOpacity="0.9" />
              <stop offset="0.48" stopColor="#3B82F6" stopOpacity="0.72" />
              <stop offset="1" stopColor="#0ABB87" stopOpacity="0.86" />
            </linearGradient>
            <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="10" stdDeviation="12" floodColor="#111827" floodOpacity="0.12" />
            </filter>
          </defs>

          <rect x="34" y="34" width="492" height="406" rx="22" fill="#FFFFFF" />
          <path d="M72 342C155 268 209 386 282 298C350 216 386 198 488 146" fill="none" stroke="url(#signalLine)" strokeWidth="3" strokeLinecap="round" />
          <path d="M74 184C146 106 225 154 280 224C347 309 407 330 486 284" fill="none" stroke="#605BFF" strokeWidth="1.5" strokeDasharray="7 9" strokeLinecap="round" opacity="0.55" />
          <path d="M96 382H464" stroke="#E5E7EB" strokeWidth="1" />
          <path d="M96 310H464" stroke="#E5E7EB" strokeWidth="1" />
          <path d="M96 238H464" stroke="#E5E7EB" strokeWidth="1" />
          <path d="M96 166H464" stroke="#E5E7EB" strokeWidth="1" />
          <path d="M96 94H464" stroke="#E5E7EB" strokeWidth="1" />

          <g filter="url(#softShadow)">
            <rect x="196" y="154" width="168" height="132" rx="20" fill="#030229" />
            <path d="M226 222C249 186 313 180 335 222C312 264 249 258 226 222Z" fill="#FFFFFF" fillOpacity="0.96" />
            <circle cx="280" cy="222" r="23" fill="#605BFF" />
            <circle cx="280" cy="222" r="8" fill="#FFFFFF" />
            <text x="280" y="258" textAnchor="middle" fontSize="13" fontWeight="700" fill="#FFFFFF" letterSpacing="1.2">GENPANO</text>
          </g>

          {SIGNALS.map((item) => (
            <g key={`${item.label}-${item.x}`}>
              <line x1={item.x < 200 ? item.x + 46 : item.x - 46} y1={item.y} x2="280" y2="222" stroke="#D7D8E8" strokeWidth="1.2" />
              <rect x={item.x - 40} y={item.y - 17} width="80" height="34" rx="17" fill="#FFFFFF" stroke="#E6E8F2" />
              <circle cx={item.x - 24} cy={item.y} r="4" fill={item.x < 200 ? '#605BFF' : '#0ABB87'} />
              <text x={item.x - 12} y={item.y + 4} fontSize="11" fontWeight="600" fill="#4B5563">{item.label}</text>
            </g>
          ))}

          <g>
            <rect x="72" y="52" width="150" height="46" rx="14" fill="#F7F7FF" stroke="#E8E8F8" />
            <text x="92" y="80" fontSize="13" fontWeight="700" fill="#030229">Brand panorama</text>
          </g>
        </svg>

        <div className="absolute bottom-6 left-6 right-6 grid grid-cols-3 gap-3">
          {METRICS.map((metric) => (
            <div
              key={metric.label}
              className="min-w-0 rounded-[14px] border bg-white/90 px-3 py-3"
              style={{ borderColor: 'var(--color-border-subtle)' }}
            >
              <div className="mb-1 h-1.5 w-8 rounded-full" style={{ background: metric.color }} />
              <p className="truncate text-[10px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--color-text-muted)' }}>
                {metric.label}
              </p>
              <p className="mt-1 text-lg font-semibold leading-none" style={{ color: 'var(--color-text-primary)' }}>
                {metric.value}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
