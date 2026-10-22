import { describe, expect, it } from 'vitest'

import { bytes, duration, health, type MonitorNow } from './monitor'

describe('monitor words', () => {
  it('words sizes and spans the way a person reads them', () => {
    expect(bytes(512)).toBe('512 B')
    expect(bytes(1536 * 1024)).toBe('1.5 MB')
    expect(bytes(31 * 1024 ** 3)).toBe('31 GB')
    expect(bytes(null)).toBe('—')
    expect(duration(42)).toBe('42 s')
    expect(duration(90 * 60)).toBe('1 h 30 min')
    expect(duration(3 * 86400)).toBe('3 days')
  })

  it('leads with the worst thing going on', () => {
    const base = { enabled: true, open: [] } as unknown as MonitorNow
    expect(health(base)).toEqual({ word: 'All normal', tone: 'ok' })
    expect(health({ ...base, enabled: false })).toEqual({ word: 'Monitor off', tone: 'off' })
    const open = [
      { severity: 'warning', title: 'CPU busy' },
      { severity: 'critical', title: 'No connection' },
    ] as MonitorNow['open']
    expect(health({ ...base, open })).toEqual({ word: 'No connection', tone: 'critical' })
  })
})
