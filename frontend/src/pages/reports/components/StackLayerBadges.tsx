export function StackLayerBadges({ layers }: { layers: number[] | undefined | null }) {
  if (!layers || layers.length === 0) return null;
  return (
    <span className="inline-flex items-center gap-0.5">
      {[1, 2, 3].map((n) => {
        const active = layers.includes(n);
        return (
          <span
            key={n}
            className="inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-bold tabular-nums"
            style={{
              background: active ? 'var(--color-accent-subtle)' : 'var(--color-bg-subtle)',
              color: active ? 'var(--color-accent)' : 'var(--color-text-faint)',
            }}
            title={`L${n} ${['Observation', 'Explanation', 'Direction'][n - 1]}`}
          >
            L{n}
          </span>
        );
      })}
    </span>
  );
}
