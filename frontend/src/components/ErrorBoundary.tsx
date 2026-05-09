/**
 * Catches uncaught render errors and shows a copyable diagnostic page.
 *
 * Render-time exceptions (bad data, undefined refs) used to crash silently in
 * production — the browser would whitewash and there was no way to copy the
 * stack for a bug report. This boundary wraps the whole app at `main.tsx` so
 * users always have something to send to support.
 *
 * Errors thrown inside event handlers / async callbacks are NOT caught here
 * (React's contract). Those go through `showApiError` instead.
 */
import React from 'react'

interface Props {
  children: React.ReactNode
}

interface State {
  error: Error | null
  info: React.ErrorInfo | null
  copied: boolean
}

function buildCopyText(error: Error, info: React.ErrorInfo | null): string {
  const lines = [
    `[ui_crash] ${error.name}: ${error.message}`,
    `time: ${new Date().toISOString()}`,
    `path: ${typeof window !== 'undefined' ? window.location.pathname + window.location.search : '-'}`,
    `user_agent: ${typeof navigator !== 'undefined' ? navigator.userAgent : '-'}`,
  ]
  if (error.stack) {
    lines.push('stack:')
    lines.push(error.stack)
  }
  if (info?.componentStack) {
    lines.push('component_stack:')
    lines.push(info.componentStack)
  }
  return lines.join('\n')
}

async function clipboardWrite(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand && document.execCommand('copy')
    document.body.removeChild(ta)
    return Boolean(ok)
  } catch {
    return false
  }
}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null, info: null, copied: false }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    this.setState({ info })
    // Surface to the console with the full stack so devtools captures it.
    console.error('[ErrorBoundary] ', error, info?.componentStack)
  }

  handleCopy = async () => {
    const { error, info } = this.state
    if (!error) return
    const ok = await clipboardWrite(buildCopyText(error, info))
    if (ok) {
      this.setState({ copied: true })
      setTimeout(() => this.setState({ copied: false }), 1500)
    }
  }

  handleReload = () => {
    if (typeof window !== 'undefined') window.location.reload()
  }

  render() {
    const { error, info, copied } = this.state
    if (!error) return this.props.children
    const copyText = buildCopyText(error, info)
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          background: 'var(--color-bg, #0b0d12)',
          color: 'var(--color-text-primary, #e6e8ec)',
        }}
      >
        <div
          style={{
            maxWidth: 720,
            width: '100%',
            padding: '1.5rem',
            background: 'var(--color-bg-card, #14171f)',
            border: '1px solid var(--color-danger, #dc2626)',
            borderRadius: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
            <span
              style={{
                fontFamily: 'monospace',
                fontSize: 12,
                padding: '2px 6px',
                borderRadius: 4,
                background: 'rgba(220,38,38,0.12)',
                color: 'var(--color-danger, #dc2626)',
              }}
            >
              ui_crash
            </span>
            <h1 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>
              {error.name}: {error.message}
            </h1>
          </div>
          <p style={{ marginTop: 12, opacity: 0.75, fontSize: 13 }}>
            页面渲染失败。请复制下方诊断信息发送至支持团队，便于排查问题。
          </p>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={this.handleCopy}
              style={{
                fontSize: 12,
                padding: '6px 10px',
                borderRadius: 6,
                border: '1px solid var(--color-border-subtle, #2a2f3a)',
                background: 'transparent',
                color: 'inherit',
                cursor: 'pointer',
              }}
            >
              {copied ? '已复制' : '复制诊断信息'}
            </button>
            <button
              type="button"
              onClick={this.handleReload}
              style={{
                fontSize: 12,
                padding: '6px 10px',
                borderRadius: 6,
                border: '1px solid var(--color-border-subtle, #2a2f3a)',
                background: 'transparent',
                color: 'inherit',
                cursor: 'pointer',
              }}
            >
              重新加载
            </button>
          </div>
          <details style={{ marginTop: 16 }}>
            <summary style={{ cursor: 'pointer', fontSize: 12, opacity: 0.75 }}>
              展开完整堆栈
            </summary>
            <pre
              style={{
                marginTop: 8,
                fontSize: 11,
                fontFamily: 'monospace',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                padding: 12,
                borderRadius: 6,
                background: 'rgba(0,0,0,0.3)',
                maxHeight: 320,
                overflow: 'auto',
                userSelect: 'text',
              }}
            >
              {copyText}
            </pre>
          </details>
        </div>
      </div>
    )
  }
}
