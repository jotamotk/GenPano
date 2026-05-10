import { describe, expect, test } from 'vitest'

import { resolveLiveProjectId } from './liveProject'

const FIRST_PROJECT = '11111111-1111-4111-8111-111111111111'
const ACTIVE_PROJECT = '22222222-2222-4222-8222-222222222222'

describe('resolveLiveProjectId', () => {
  test('prefers the active live project over the first project in the list', () => {
    expect(
      resolveLiveProjectId(
        [
          { id: FIRST_PROJECT },
          { id: ACTIVE_PROJECT },
        ],
        { id: ACTIVE_PROJECT },
      ),
    ).toBe(ACTIVE_PROJECT)
  })

  test('falls back to the first live project when the active project is mock-only', () => {
    expect(
      resolveLiveProjectId(
        [{ id: FIRST_PROJECT }],
        { id: 'estee-lauder-demo' },
      ),
    ).toBe(FIRST_PROJECT)
  })
})
