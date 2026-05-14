import type { TFn } from '../lib/types';

/* PRD §4.7.0-a 三读者视角 颜色 / 标签映射 */
export const READER_COLORS: Record<string, { bg: string; text: string }> = {
  operator: { bg: 'rgba(96,91,255,0.10)', text: 'var(--color-accent)' },
  manager:  { bg: 'rgba(245,166,35,0.12)', text: 'var(--color-warning-text)' },
  branding: { bg: 'rgba(10,187,135,0.10)', text: 'var(--color-success-text)' },
};

export function ReaderBadge({ reader, t }: { reader: string | undefined | null; t: TFn }) {
  if (!reader) return null;
  const palette = READER_COLORS[reader] || READER_COLORS.operator;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-medium rounded-full px-1.5 py-0.5"
      style={{ background: palette.bg, color: palette.text }}
      title={t(`reports.reader.${reader}_full`)}
    >
      {t(`reports.reader.${reader}`)}
    </span>
  );
}
