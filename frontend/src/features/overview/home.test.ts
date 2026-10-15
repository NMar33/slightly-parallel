import { describe, expect, it } from 'vitest'

import { startedToday } from './home'

describe('startedToday', () => {
  it('reads a terminal made just after local midnight as today', () => {
    const now = new Date(2026, 9, 12, 0, 40)
    expect(startedToday('2026-10-12T00:30:00', now)).toBe('2026-10-12T00:30:00')
  })
  it('leaves a terminal from yesterday without a start', () => {
    const now = new Date(2026, 9, 12, 23, 50)
    expect(startedToday('2026-10-11T23:55:00', now)).toBe('')
  })
})
