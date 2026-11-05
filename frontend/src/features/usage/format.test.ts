import { describe, expect, it } from 'vitest'

import shared from '../../../../testdata/usage/format-table.json'

import { exactTokens, formatTokens, pct, ratioTenths, sharePct, tenthsText } from './format'

/**
 * One table for Python and TypeScript: testdata/usage/format-table.json,
 * which the server's tests loop over too. `span_min` is the server's alone:
 * the page shows its "in …" as given and never recomputes it.
 */
interface Table {
  tokens: Array<[number, string]>
  pct: Array<[number | null, string]>
  ratio: Array<[[number, number], string]>
  span_min?: Array<[number, string]>
}

const TABLE = shared as unknown as Table

const ratioText = (v: number, u: number) => {
  const q = ratioTenths(v, u)
  return q == null ? '—' : tenthsText(q)
}

describe('the format table the server shares', () => {
  it('is read from testdata/usage/format-table.json', () => {
    expect(TABLE.tokens.length).toBeGreaterThan(10)
  })

  it.each(TABLE.tokens)('tokens %s → %s', (n, shown) => {
    expect(formatTokens(n)).toBe(shown)
  })

  it.each(TABLE.pct)('percent %s → %s', (x, shown) => {
    expect(pct(x)).toBe(shown)
  })

  it.each(TABLE.ratio)('ratio %j → %s', ([v, u], shown) => {
    expect(ratioText(v, u)).toBe(shown)
  })
})

describe('formatTokens', () => {
  it('draws a dash for a number the tool did not give', () => {
    expect(formatTokens(null)).toBe('—')
    expect(formatTokens(undefined)).toBe('—')
    expect(formatTokens(Number.NaN)).toBe('—')
  })

  it('rounds a fraction as Python does, a tie to even', () => {
    expect(formatTokens(512.5)).toBe('512')
    expect(formatTokens(513.5)).toBe('514')
  })

  it('keeps the exact count for tooltips, grouped by thousands', () => {
    expect(exactTokens(108_233)).toBe('108,233')
    expect(sharePct(0.976)).toBe('98%')
    expect(sharePct(null)).toBe('—')
  })
})
