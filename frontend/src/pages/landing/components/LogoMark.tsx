/**
 * LogoMark — gradient G square used in masthead/footer.
 *
 * Moved verbatim from LandingPage.tsx (lines 467-484).
 */

interface LogoMarkProps {
  size?: number;
}

export function LogoMark({ size = 32 }: LogoMarkProps) {
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
