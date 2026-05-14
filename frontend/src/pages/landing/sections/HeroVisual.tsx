/**
 * HeroVisual — flat dashboard-ish preview card next to the hero copy.
 * Intentionally minimal: no browser chrome, no mac dots.
 *
 * Moved verbatim from LandingPage.tsx (lines 721-846).
 */
import { Sparkline } from '../components/Sparkline';

export function HeroVisual() {
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
