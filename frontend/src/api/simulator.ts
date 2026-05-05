/**
 * PANO_A simulator API (Phase E.3).
 *
 *   POST /v1/projects/:id/simulator/run
 *     body: { brand_id, delta_by_tier: {"1": N, "2": N, ...},
 *             confidence_override?: 0.5..1.0 }
 *     resp: { current_pano_a, simulated_pano_a, delta,
 *             delta_breakdown: {visibility, sov, sentiment, citation_authority},
 *             base_price_equivalent_cny, confidence }
 */

import { apiClient } from '../lib/apiClient'

export interface SimulatorIn {
  brand_id: number
  delta_by_tier: Record<string, number>
  confidence_override?: number | null
}

export interface SimulatorBreakdown {
  visibility: number
  sov: number
  sentiment: number
  citation_authority: number
}

export interface SimulatorOut {
  current_pano_a: number
  simulated_pano_a: number
  delta: number
  delta_breakdown: SimulatorBreakdown
  base_price_equivalent_cny: number
  confidence: number
}

export const simulatorApi = {
  run(projectId: string, payload: SimulatorIn): Promise<SimulatorOut> {
    return apiClient.post<SimulatorOut>(
      `/v1/projects/${projectId}/simulator/run`,
      payload,
    )
  },
}
