// @vitest-environment node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const topicsPageSource = () =>
  readFileSync(resolve(process.cwd(), 'src/pages/TopicsPage.tsx'), 'utf8');

describe('Topics page drilldown monitoring surface', () => {
  it('keeps the user-facing evidence columns and avoids admin execution-table leakage', () => {
    const source = topicsPageSource();

    expect(source).toContain('<th>Associated brand</th>');
    expect(source).toContain('<th className="text-right">Visibility</th>');
    expect(source).toContain('<th>Sentiment</th>');
    expect(source).toContain('<th className="text-right">Citation Coverage</th>');
    expect(source).toContain('<th className="text-right">Citations</th>');
    expect(source).not.toContain('<th>Engines</th>');
    expect(source).not.toContain('<th className="text-right">Mention rate</th>');
    expect(source).not.toContain('<th className="text-right">Avg GEO</th>');
    expect(source).not.toContain('Topic x Intent');
    expect(source).not.toContain('QueryActivityCard');
    expect(source).not.toContain('Query activity');
    expect(source).not.toContain('Query executions');
  });
});
