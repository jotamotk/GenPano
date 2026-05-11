import { describe, expect, it } from 'vitest'

import { adaptOverviewToPrimary } from '../../src/adapters/dashboardAdapter'
import type { BrandOverviewOut } from '../../src/api/brandOverview'

const emptyOverview: BrandOverviewOut = {
  project_id: 'project-1',
  brand_id: null,
  brand_name: null,
  industry_id: null,
  period: { from: '2026-05-01', to: '2026-05-11' },
  kpi_cards: [],
  geo_score_30d: [],
  sov_30d: [],
  sentiment_30d: [],
  top_prompts: [],
  same_group_shared_domains: [],
  state: 'empty',
}

describe('dashboard adapter', () => {
  it('does not fabricate Brand #? for an empty unbound overview response', () => {
    expect(adaptOverviewToPrimary(emptyOverview)).toBeNull()
  })
})
