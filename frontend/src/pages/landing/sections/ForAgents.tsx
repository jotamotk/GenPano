/**
 * ForAgents — MCP / REST positioning section with feature list and code sample.
 *
 * Moved verbatim from LandingPage.tsx (lines 1315-1434).
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Code2, Cpu, FileText, Shield, Sparkles } from 'lucide-react';
import { Eyebrow } from '../components/Eyebrow';
import { track } from '../hooks/useLocale';
import { MAX_W } from '../layout';
import type { SectionProps } from '../types';

export function ForAgents({ t }: SectionProps) {
  const icons: Record<string, ReactNode> = {
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
