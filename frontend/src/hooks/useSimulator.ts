/**
 * PANO_A simulator hook — wraps POST /v1/projects/:id/simulator/run.
 *
 * Used by BrandSimulatorPage. The page computes a preview number on
 * the client (`calcDelta`) for instant feedback while the user drags
 * tier sliders; clicking "Run live" fires this mutation to get the
 * authoritative simulated_pano_a from the backend.
 */

import { useMutation } from '@tanstack/react-query'
import { simulatorApi, type SimulatorIn, type SimulatorOut } from '../api/simulator'

export function useRunSimulator(projectId: string | null | undefined) {
  return useMutation<SimulatorOut, Error, SimulatorIn>({
    mutationFn: (payload) =>
      simulatorApi.run(projectId as string, payload),
    onError: (err) => {
      // Best-effort: log; the page falls back to its preview number.
      // eslint-disable-next-line no-console
      console.warn('simulator.run failed:', err)
    },
  })
}
