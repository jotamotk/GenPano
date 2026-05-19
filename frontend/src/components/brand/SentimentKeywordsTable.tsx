/**
 * SentimentKeywordsTable — tabular rendering of the Top 10 positive or
 * negative keywords for the Sentiment page (Section 5).
 *
 * Replaces the previous Badge-grid layout (Issue #1285) where keyword
 * weight chips used text-[11px] labels the user found illegible. The
 * table uses .t-table styling to match IndustryLeaderboardTable.tsx:
 * text-[13px] body rows with text-[11px] muted headers.
 */
import React from 'react';

export interface SentimentKeyword {
  word: string;
  weight: number;
}

interface SentimentKeywordsTableProps {
  title: string;
  keywords: SentimentKeyword[];
  polarity: 'positive' | 'negative';
  limit?: number;
}

export default function SentimentKeywordsTable({
  title,
  keywords,
  polarity,
  limit = 10,
}: SentimentKeywordsTableProps) {
  const rows = keywords.slice(0, limit);
  const dotColor = polarity === 'positive' ? 'var(--color-chart-7)' : 'var(--color-danger)';
  const wordColorClass =
    polarity === 'positive' ? 'text-[var(--color-chart-7)]' : 'text-[var(--color-danger)]';

  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-themed-primary">{title}</h3>
        <span className="text-[11px] text-themed-muted">Top {limit}</span>
      </div>
      {rows.length === 0 ? (
        <p className="text-themed-muted text-sm py-4 text-center">—</p>
      ) : (
        <table className="t-table w-full text-[13px]">
          <thead>
            <tr className="text-[11px] text-themed-muted">
              <th className="text-left py-1.5 w-8">#</th>
              <th className="text-left py-1.5">关键词</th>
              <th className="text-right py-1.5">权重</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((kw, idx) => (
              <tr key={`${kw.word}-${idx}`}>
                <td className="py-1.5 text-themed-muted tabular-nums">{idx + 1}</td>
                <td className="py-1.5">
                  <span className="inline-flex items-center gap-2">
                    <span
                      className="inline-block w-1.5 h-1.5 rounded-full"
                      style={{ background: dotColor }}
                      aria-hidden="true"
                    />
                    <span className={`font-medium ${wordColorClass}`}>{kw.word}</span>
                  </span>
                </td>
                <td className="py-1.5 text-right tabular-nums text-themed-primary">
                  ×{kw.weight}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
