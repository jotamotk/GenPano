/**
 * SentimentSamplesTable — sortable, expandable table rendering of
 * Response samples on the Sentiment page (Section 6).
 *
 * Replaces the card list (Issue #1285) where engine/topic/time metadata
 * rendered at text-[10px], which the user found illegible. The table
 * uses .t-table styling (text-[13px] body / text-[11px] muted headers)
 * matching IndustryLeaderboardTable.tsx.
 *
 * Behaviour:
 *  - Header click toggles sort key/direction. Default sort is by time desc.
 *  - Row click toggles a detail row with the full response text (or
 *    fallback message + snippet + responseApiNeed) using colSpan={5}.
 *  - The Inspect button is removed; click-target is the whole row.
 *  - Polarity badge / engine / topic / time / summary are the visible columns.
 */
import React, { useMemo, useState } from 'react';
import { Badge } from '../ui';
import type { SentimentSampleRow } from '../../adapters/chartAdapters';

interface SentimentSamplesTableProps {
  rows: SentimentSampleRow[];
  expandedKey: string | null;
  onExpandedKeyChange: (key: string | null) => void;
  responseApiNeed: string;
}

type SortKey = 'polarity' | 'topic' | 'engine' | 'time' | 'summary';
type SortDir = 'asc' | 'desc';

const COLUMNS: { key: SortKey; label: string; align: 'left' | 'right'; width?: string }[] = [
  { key: 'polarity', label: '极性', align: 'left', width: 'w-20' },
  { key: 'topic', label: '主题', align: 'left' },
  { key: 'engine', label: '引擎', align: 'left', width: 'w-24' },
  { key: 'time', label: '时间', align: 'left', width: 'w-28' },
  { key: 'summary', label: '摘要', align: 'left' },
];

function rowKey(item: SentimentSampleRow, idx: number): string {
  return `${item.queryId ?? 'query'}-${item.mentionId ?? item.responseId ?? idx}`;
}

function compareRows(a: SentimentSampleRow, b: SentimentSampleRow, key: SortKey, dir: SortDir): number {
  const av = (a[key] ?? '') as string;
  const bv = (b[key] ?? '') as string;
  const cmp = String(av).localeCompare(String(bv));
  return dir === 'asc' ? cmp : -cmp;
}

function polarityBadgeVariant(polarity: SentimentSampleRow['polarity']): 'green' | 'red' | 'default' {
  if (polarity === 'positive') return 'green';
  if (polarity === 'negative') return 'red';
  return 'default';
}

export default function SentimentSamplesTable({
  rows,
  expandedKey,
  onExpandedKeyChange,
  responseApiNeed,
}: SentimentSamplesTableProps) {
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: 'time', dir: 'desc' });

  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => compareRows(a, b, sort.key, sort.dir));
  }, [rows, sort.key, sort.dir]);

  const handleHeaderClick = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: key === 'time' ? 'desc' : 'asc' },
    );
  };

  const sortIndicator = (key: SortKey) => {
    if (sort.key !== key) return null;
    return <span className="ml-1 text-themed-muted">{sort.dir === 'asc' ? '▲' : '▼'}</span>;
  };

  return (
    <table className="t-table w-full text-[13px]">
      <thead>
        <tr className="text-[11px] text-themed-muted">
          {COLUMNS.map((col) => (
            <th
              key={col.key}
              className={`py-1.5 ${col.align === 'right' ? 'text-right' : 'text-left'} ${col.width ?? ''}`.trim()}
            >
              <button
                type="button"
                onClick={() => handleHeaderClick(col.key)}
                aria-label={`Sort by ${col.label}`}
                className="inline-flex items-center hover:text-themed-primary transition-colors"
              >
                {col.label}
                {sortIndicator(col.key)}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedRows.map((item, idx) => {
          const key = rowKey(item, idx);
          const expanded = expandedKey === key;
          return (
            <React.Fragment key={key}>
              <tr
                role="button"
                tabIndex={0}
                onClick={() => onExpandedKeyChange(expanded ? null : key)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onExpandedKeyChange(expanded ? null : key);
                  }
                }}
                aria-expanded={expanded}
                aria-label={`Inspect full response for ${item.summary}`}
                className="cursor-pointer"
              >
                <td className="py-1.5">
                  <Badge variant={polarityBadgeVariant(item.polarity)} size="sm">
                    {item.label}
                  </Badge>
                </td>
                <td className="py-1.5 text-themed-primary">{item.topic}</td>
                <td className="py-1.5 text-themed-muted">{item.engine}</td>
                <td className="py-1.5 text-themed-muted tabular-nums">{item.time}</td>
                <td className="py-1.5 text-themed-primary">
                  <span className="line-clamp-2">{item.summary}</span>
                </td>
              </tr>
              {expanded && (
                <tr aria-label={`Full response inspection for ${item.summary}`}>
                  <td colSpan={COLUMNS.length} className="py-3 bg-themed-subtle">
                    <div className="rounded-card bg-themed-card border border-themed-subtle p-3">
                      <p className="text-xs font-semibold text-themed-primary">
                        Full response inspection
                      </p>
                      <p className="text-[11px] text-themed-muted mt-1">
                        query_id: {item.queryId ?? 'pending'} · response_id:{' '}
                        {item.responseId ?? 'pending'} · mention_id:{' '}
                        {item.mentionId ?? 'pending'}
                      </p>
                      {item.responseText ? (
                        <p className="text-sm text-themed-primary leading-relaxed mt-2 whitespace-pre-wrap">
                          {item.responseText}
                        </p>
                      ) : (
                        <div className="mt-2 space-y-2">
                          <p className="text-sm text-themed-primary leading-relaxed">
                            Full response text is not available from the current API payload.
                          </p>
                          {item.snippet && (
                            <p className="text-xs text-themed-muted leading-relaxed">
                              Current snippet: {item.snippet}
                            </p>
                          )}
                          <p className="text-[11px] text-themed-muted">{responseApiNeed}</p>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
