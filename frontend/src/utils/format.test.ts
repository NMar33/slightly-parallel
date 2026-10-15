import { describe, expect, it } from 'vitest'

import { ago, bytes, duration, formatHours, hMin, hm, plural } from './format'

describe('the shared formatters', () => {
  it('bytes: binary units, a decimal only under 10', () => {
    expect([bytes(512), bytes(1200), bytes(48_210), bytes(1536 * 1024), bytes(31 * 1024 ** 3), bytes(null)])
      .toEqual(['512 B', '1.2 KB', '47 KB', '1.5 MB', '31 GB', '—'])
  })
  it('minutes three ways', () => {
    expect([hm(0), hm(45), hm(72)]).toEqual(['0h', '45m', '1.2h'])
    expect([hMin(0), hMin(0, '0m'), hMin(45), hMin(65)]).toEqual(['—', '0m', '45m', '1h 05m'])
    expect([duration(40), duration(720), duration(4800), duration(3 * 86400)]).toEqual(['40 s', '12 min', '1 h 20 min', '3 days'])
  })
  it('hMin never prints sixty minutes: a fraction rounds to the whole minute first', () => {
    expect([hMin(59.6), hMin(119.7), hMin(60.4), hMin(0.3, '0m')]).toEqual(['1h 00m', '2h 00m', '1h 00m', '0m'])
  })
  it('a count with its noun, and how long ago', () => {
    expect([plural(1, 'task'), plural(0, 'task'), plural(3, 'task')]).toEqual(['1 task', '0 tasks', '3 tasks'])
    const min = 60_000
    expect([ago(20_000), ago(12 * min), ago(5 * 60 * min), ago(30 * 60 * min), ago(30 * 60 * min, 48), ago(72 * 60 * min, 48)])
      .toEqual(['just now', '12m ago', '5h ago', '1d ago', '30h ago', '3d ago'])
  })
  it('rounds before it picks the shape: no "19.0", "100.0", "60m", "10.0 KB" or "1024 KB"', () => {
    expect([formatHours(18.96), formatHours(99.96), formatHours(42.5), formatHours(18), formatHours(NaN)])
      .toEqual(['19', '100', '42.5', '18', '0'])
    expect([hm(59.6), hm(59.4)]).toEqual(['1h', '59m'])
    expect([bytes(9.97 * 1024), bytes(1024 * 1024 - 1), bytes(1023)]).toEqual(['10 KB', '1.0 MB', '1023 B'])
  })
})
