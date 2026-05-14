/**
 * FooterCol — one labelled list column inside the footer grid.
 *
 * Moved verbatim from LandingPage.tsx (lines 1541-1572).
 */

interface FooterColProps {
  title: string;
  links: readonly string[];
}

export function FooterCol({ title, links }: FooterColProps) {
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
