import React from 'react';

type FilterPillProps = {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  style?: React.CSSProperties;
};

export default function FilterPill({ active, onClick, children, style }: FilterPillProps) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-pill text-xs font-medium transition-colors ${
        active ? 'text-themed-accent' : 'text-themed-muted'
      }`}
      style={active
        ? { background: 'var(--color-accent-bg-light)', ...(style || {}) }
        : { background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', ...(style || {}) }}
    >
      {children}
    </button>
  );
}
