// @vitest-environment node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const topicsPageSource = () =>
  readFileSync(resolve(process.cwd(), 'src/pages/TopicsPage.tsx'), 'utf8');

describe('Topics page minimal monitoring surface', () => {
  it('does not reintroduce metric-heavy columns in the monitoring table', () => {
    const source = topicsPageSource();

    expect(source).toContain('<th>Associated brand</th>');
    expect(source).not.toContain('<th>Engines</th>');
    expect(source).not.toContain('<th>Sentiment</th>');
    expect(source).not.toContain('<th className="text-right">Mention rate</th>');
    expect(source).not.toContain('<th className="text-right">Avg GEO</th>');
    expect(source).not.toContain('Success rate');
    expect(source).not.toContain('Topic x Intent');
  });
});
