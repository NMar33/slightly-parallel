import { describe, it, expect } from 'vitest'

import { formatClock, formatDuration, liveElapsed, type TimeEntry } from './TimeTracker'

const START = '2026-08-16T10:00:00'
const NOW = Date.parse('2026-08-16T11:00:00')

const entry = (over: Partial<TimeEntry> = {}): TimeEntry => ({
  id: 'tm_1',
  project: 'alpha',
  started_at: START,
  status: 'running',
  ...over,
})

describe('formatDuration', () => {
  it('renders minutes and hours at stable width', () => {
    expect(formatDuration(0)).toBe('0m')
    expect(formatDuration(59)).toBe('0m')
    expect(formatDuration(720)).toBe('12m')
    expect(formatDuration(3600)).toBe('1h 00m')
    expect(formatDuration(3600 * 2 + 240)).toBe('2h 04m')
  })
})

describe('formatClock', () => {
  it('shows seconds so a running timer visibly moves', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(5)).toBe('0:05')
    expect(formatClock(754)).toBe('12:34')
  })

  it('adds an hours field with zero-padded minutes', () => {
    expect(formatClock(3600)).toBe('1:00:00')
    expect(formatClock(3873)).toBe('1:04:33')
  })
})

describe('liveElapsed', () => {
  it('counts wall time while running', () => {
    expect(liveElapsed(entry(), NOW)).toBe(3600)
  })

  it('subtracts banked pause time', () => {
    expect(liveElapsed(entry({ paused_total_sec: 900 }), NOW)).toBe(2700)
  })

  it('freezes while paused, however late the clock is read', () => {
    const e = entry({ status: 'paused', paused_at: '2026-08-16T10:30:00' })
    expect(liveElapsed(e, NOW)).toBe(1800)
    expect(liveElapsed(e, NOW + 5 * 3600_000)).toBe(1800)
  })

  it('uses the frozen duration once stopped', () => {
    const e = entry({ status: 'done', duration_min: 20, ended_at: '2026-08-16T10:20:00' })
    expect(liveElapsed(e, NOW + 99_000_000)).toBe(1200)
  })

  it('falls back to the server value when timestamps are unusable', () => {
    expect(liveElapsed(entry({ started_at: 'nonsense', elapsed_sec: 42 }), NOW)).toBe(42)
  })
})

describe('liveElapsed on finished entries', () => {
  it('measures start→end even when the row carries no status', async () => {
    const { liveElapsed } = await import('./TimeTracker')
    const e = { id: 'x', project: 'p', started_at: '2026-08-21T07:00:00', ended_at: '2026-08-21T07:30:00' }
    // "now" is hours later — a finished entry must not keep growing.
    expect(liveElapsed(e, Date.parse('2026-08-21T11:30:00'))).toBe(30 * 60)
  })
  it('subtracts banked pauses from a finished span', async () => {
    const { liveElapsed } = await import('./TimeTracker')
    const e = { id: 'x', project: 'p', started_at: '2026-08-21T07:00:00', ended_at: '2026-08-21T08:00:00', paused_total_sec: 600 }
    expect(liveElapsed(e, 0)).toBe(50 * 60)
  })
})
