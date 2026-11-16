import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { TurnUsage } from './data'
import { UsageLine, turnLine, usageDetail } from './UsageLine'

const TURN: TurnUsage = {
  new: 1874, output: 512, cache: 108_233, cache_write: 1622, thinking: 210, model: 'claude-opus-4-5',
  messages: 1, helpers: null, rebuild: null, limit: null, ttl: '1h', line: '→ 1.9k ↑ 512 ↓ (108k)',
}

/** The text a reader sees: the line without its hidden description. */
function visible(el: HTMLElement): string {
  const copy = el.cloneNode(true) as HTMLElement
  copy.querySelectorAll('.sr-only').forEach((n) => n.remove())
  return copy.textContent ?? ''
}

describe('UsageLine', () => {
  it('shows new + output and the cache in brackets', () => {
    render(<UsageLine usage={TURN} at="14:02:11" turn={38} />)
    const line = screen.getByTestId('usage-line')
    expect(line.firstChild?.textContent).toBe('→ 1.9k ↑ 512 ↓')
    expect(visible(line)).toBe('→ 1.9k ↑ 512 ↓ (108k)')
    expect(line.className).toContain('text-secondary')
  })

  it('can be reached by keyboard, with the full account as its description', () => {
    render(<UsageLine usage={TURN} at="14:02:11" turn={38} />)
    const line = screen.getByTestId('usage-line')
    expect(line.tabIndex).toBe(0)
    const desc = document.getElementById(line.getAttribute('aria-describedby')!)
    expect(desc?.textContent).toContain('New 1,874, read for the first time')
    expect(desc?.className).toContain('sr-only')
  })

  it('keeps only the leading part under 320px: the rest is its own span', () => {
    render(<UsageLine usage={TURN} />)
    const rest = screen.getByTestId('usage-line').querySelector('span.hidden')
    expect(rest?.textContent).toBe(' (108k)')
    expect(rest?.className).toContain('min-[320px]:inline')
  })

  it('draws nothing for a turn with no usage recorded', () => {
    const { container } = render(<UsageLine usage={undefined} />)
    expect(container.textContent).toBe('')
  })

  it('is amber on a cache rebuild and names the cause in the tooltip', () => {
    render(<UsageLine usage={{ ...TURN, line: undefined, new: 40_488, cache: 0, rebuild: { cause: 'cache expired: 7 min since the last turn', kind: 'expired' } }} />)
    const line = screen.getByTestId('usage-line')
    expect(visible(line)).toBe('→ 40k ↑ 512 ↓ (0) · cache expired')
    expect(line.style.color).toBe('var(--status-amber-ink)')
    expect(line.getAttribute('title')).toContain('Cache rebuilt: cache expired: 7 min since the last turn')
  })

  it('adds the helpers apart, outside the leading number', () => {
    render(<UsageLine usage={{ ...TURN, line: undefined, helpers: { n: 2, new_output: 300_412 } }} />)
    expect(visible(screen.getByTestId('usage-line'))).toBe('→ 1.9k ↑ 512 ↓ (108k) + helpers 300k')
  })

  it('builds the server\'s line when the answer has none: the 5-hour limit when it passed a ten', () => {
    const prev = { ...TURN, limit: { five_hour: 69.9 } }
    expect(turnLine({ ...TURN, limit: { five_hour: 70.0 } }, prev)).toBe('→ 1.9k ↑ 512 ↓ (108k) · 5-hour 70%')
    expect(turnLine({ ...TURN, limit: { five_hour: 79.6 } }, { ...TURN, limit: { five_hour: 70.0 } })).toBe('→ 1.9k ↑ 512 ↓ (108k)')
    expect(turnLine({ ...TURN, rebuild: { cause: 'x', kind: 'model' } })).toBe('→ 1.9k ↑ 512 ↓ (108k) · model changed')
    expect(turnLine({ ...TURN, rebuild: { cause: 'x', kind: 'unknown' } })).toBe('→ 1.9k ↑ 512 ↓ (108k) · cache rebuilt')
  })

  it('gives the full account in the tooltip', () => {
    const tip = usageDetail({ ...TURN, helpers: { n: 2, new_output: 300_412 }, limit: { five_hour: 62 } }, '14:02:11', 38)
    expect(tip.split('\n')).toEqual([
      'New 1,874, read for the first time',
      '  of which cache written 1,622 · kept 1 h',
      'Output 512',
      '  of which thinking 210',
      'Cache 108,233, read again from cache',
      'Cache share 98%',
      'Model claude-opus-4-5',
      '2 helpers · 300,412 new + output',
      '5-hour 62% at this turn',
      '14:02:11 · turn 38 · 1 API message',
    ])
  })
})
