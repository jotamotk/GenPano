/**
 * Unit tests for the live-mode UUID gate. Mock projects use synthetic
 * ids like "p-001"; live projects always have UUID ids. The gate keeps
 * mock-only sessions from hitting the backend and getting a 404.
 */
import { describe, it, expect } from 'vitest'
import { isLiveProjectId } from './useReports'

describe('isLiveProjectId', () => {
  it('accepts canonical UUID v4', () => {
    expect(
      isLiveProjectId('123e4567-e89b-12d3-a456-426614174000'),
    ).toBe(true)
  })

  it('accepts uppercase UUID', () => {
    expect(
      isLiveProjectId('123E4567-E89B-12D3-A456-426614174000'),
    ).toBe(true)
  })

  it('rejects mock-style ids', () => {
    expect(isLiveProjectId('p-001')).toBe(false)
    expect(isLiveProjectId('proj-1')).toBe(false)
  })

  it('rejects null / undefined / empty', () => {
    expect(isLiveProjectId(null)).toBe(false)
    expect(isLiveProjectId(undefined)).toBe(false)
    expect(isLiveProjectId('')).toBe(false)
  })

  it('rejects partial UUIDs and wrong-length strings', () => {
    // Missing one segment
    expect(isLiveProjectId('123e4567-e89b-12d3-a456')).toBe(false)
    // Too short
    expect(isLiveProjectId('xxxx')).toBe(false)
    // Right length but contains invalid chars
    expect(
      isLiveProjectId('zzze4567-e89b-12d3-a456-426614174000'),
    ).toBe(false)
  })
})
