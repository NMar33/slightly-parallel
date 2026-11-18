import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import type { AquaSession } from '../model'
import { factsOf, type Facts, type TabInfo } from './facts'
import {
  TAB_STATE_DEFAULT, TAB_STATE_KEY, chatHue, dotInk, intensity, parseTabState, values, warmDots, warmTarget, warmth,
  type Period,
} from './rhythm'
import { RhythmDots, TabStateRow, periodLine, rhythmTip } from './RhythmDots'
import { StripSettingsRows, StripTab } from './Tab'

const p = (start: number, q: Partial<Period> = {}): Period => ({
  start: `2026-11-18T${String(start).padStart(2, '0')}:00:00`, end: `2026-11-18T${String(start + 1).padStart(2, '0')}:00:00`,
  msgs: 0, commits: 0, tasks: 0, tokens: 0, ...q,
})
const facts = (q: Partial<Facts> = {}): Facts => ({ branches: 0, done: 0, all: 0, waited: 0, ctx: null, waiting: false, rhythm: null, chatId: 'cc-a', ...q })
const row = (q: Partial<AquaSession> = {}): AquaSession => ({
  id: 't1', kind: 'shell', label: 'claude', project: 'harbor', cwd: '/h', command: 'claude', agent_id: '', task_id: '',
  created: '', backend: 'tmux', state: 'working', program: 'claude', last_output: 0, ...q,
})

beforeEach(() => localStorage.clear())

describe('the six hours', () => {
  it('weigh messages 1, commits 3, tasks closed 4, tokens 1 per 10k (at most 10); full at 30', () => {
    expect(intensity(p(13))).toBe(0)
    expect(intensity(p(13, { msgs: 12 }))).toBeCloseTo(12 / 30)
    expect(intensity(p(13, { msgs: 3, commits: 2, tasks: 1, tokens: 50_000 }))).toBeCloseTo((3 + 6 + 4 + 5) / 30)
    // a cache rebuild alone fills a third at most
    expect(intensity(p(13, { tokens: 900_000 }))).toBeCloseTo(10 / 30)
    expect(intensity(p(13, { msgs: 40 }))).toBe(1)
  })

  it('are six values oldest first; fewer periods fill from the left with nothing, none known is six empty', () => {
    expect(values(null)).toEqual([0, 0, 0, 0, 0, 0])
    const v = values([p(15, { msgs: 30 }), p(16, { msgs: 15 })])
    expect(v).toEqual([0, 0, 0, 0, 1, 0.5])
    const seven = [8, 9, 10, 11, 12, 13, 14].map((h) => p(h, { msgs: h }))
    expect(values(seven)).toHaveLength(6)
    expect(values(seven)[0]).toBeCloseTo(9 / 30)
  })

  it('come from the server\'s rhythm through the tab\'s facts, with the chat\'s id for the hue', () => {
    const info: TabInfo = { title: '', agent_id: 'cc-a', chat: { name: '', tool: 'claude-code', tasks_done: 0, tasks_all: 0, branches: 0, ctx_pct: null, ctx_size: null, ctx_at: '', rhythm: { period_min: 60, periods: [p(11), p(12, { msgs: 2 })] } } }
    const f = factsOf(row(), info, Date.now())
    expect(f.rhythm?.[1]?.msgs).toBe(2)
    expect(f.chatId).toBe('cc-a')
    // an older server: no rhythm; a shell: the terminal's own id
    expect(factsOf(row(), { ...info, chat: { ...info.chat!, rhythm: undefined } }, 0).rhythm).toBeNull()
    expect(factsOf(row(), undefined, 0).chatId).toBe('t1')
  })

  it('take one hue per chat: a lane colour chosen by its id, the same every time', () => {
    expect(chatHue('cc-4e7a19d2')).toMatch(/^var\(--lane-[1-8]\)$/)
    expect(chatHue('cc-4e7a19d2')).toBe(chatHue('cc-4e7a19d2'))
    const hues = new Set(['cc-a', 'cc-b', 'cc-c', 'cc-d', 'cc-e', 'cx-f', 'cc-g', 'cc-h'].map(chatHue))
    expect(hues.size).toBeGreaterThan(2)
    // more activity, a fuller colour of the same hue
    expect(dotInk('var(--lane-3)', 0, 0, 0)).toBe('color-mix(in srgb, var(--lane-3) 16%, transparent)')
    expect(dotInk('var(--lane-3)', 1, 0, 0)).toBe('color-mix(in srgb, var(--lane-3) 100%, transparent)')
  })
})

describe('the signal', () => {
  it('is calm under 5 min of waiting and up to 70% context', () => {
    expect(warmth(false, 60, null)).toBe(0)
    expect(warmth(true, 4, 70)).toBe(0)
    expect(warmDots(0)).toEqual([0, 0, 0, 0, 0, 0])
  })

  it('warms from the right toward amber, amber at 10 min, red at 20; one gradient', () => {
    expect(warmth(true, 5, null)).toBe(0)
    expect(warmth(true, 7.5, null)).toBeCloseTo(0.5)
    expect(warmth(true, 10, null)).toBe(1)
    expect(warmth(true, 15, null)).toBeCloseTo(1.5)
    expect(warmth(true, 20, null)).toBe(2)
    expect(warmth(true, 90, null)).toBe(2)
    // half warm: the newest three dots, the oldest three calm
    expect(warmDots(0.5)).toEqual([0, 0, 0, 1, 1, 1])
    expect(warmDots(0.25)).toEqual([0, 0, 0, 0, 0.5, 1])
    expect(warmDots(1.7)).toEqual([1, 1, 1, 1, 1, 1])
    // one target for the row: amber, then mixed toward red
    expect(warmTarget(0.6)).toBe('var(--aq-wait)')
    expect(warmTarget(1)).toBe('var(--aq-wait)')
    expect(warmTarget(1.5)).toBe('color-mix(in oklch, var(--aq-down) 50%, var(--aq-wait))')
    expect(warmTarget(2)).toBe('color-mix(in oklch, var(--aq-down) 100%, var(--aq-wait))')
  })

  it('shows past 70% context at once, amber at 85%, red at 95%; the larger of the two wins', () => {
    expect(warmth(false, 0, 71)).toBeGreaterThan(0.4)
    expect(warmth(false, 0, 85)).toBe(1)
    expect(warmth(false, 0, 90)).toBeCloseTo(1.5)
    expect(warmth(false, 0, 95)).toBe(2)
    expect(warmth(true, 12, 80)).toBeCloseTo(1.2)
  })
})

describe('the dots on a tab', () => {
  it('draw six dots in the chat\'s hue and say each hour in the tooltip', () => {
    const f = facts({ rhythm: [p(11), p(12, { msgs: 12, commits: 2 }), p(13, { msgs: 1 }), p(14), p(15, { tasks: 1, tokens: 42_000 }), p(16, { msgs: 30 })] })
    const { container } = render(<RhythmDots f={f} chatId="cc-a" onSelect={() => {}} />)
    const dots = container.querySelectorAll('[data-dot]')
    expect(dots).toHaveLength(6)
    expect(dots[5]!.getAttribute('data-v')).toBe('1.00')
    expect((dots[5] as HTMLElement).style.background).toContain(chatHue('cc-a').slice(4, -1))
    const tip = container.querySelector('[data-tabstate="rhythm"]')!.getAttribute('title')!.split('\n')
    expect(tip).toHaveLength(6)
    expect(tip[1]).toBe('12:00–13:00 · 12 messages, 2 commits')
    expect(tip[0]).toBe('11:00–12:00 · quiet')
    expect(tip[4]).toBe('15:00–16:00 · 1 task closed, 42k tokens')
  })

  it('a waiting chat warms and says so in the tooltip', () => {
    const f = facts({ waiting: true, waited: 25, rhythm: [p(16, { msgs: 3 })] })
    const { container } = render(<RhythmDots f={f} chatId="cc-a" onSelect={() => {}} />)
    const el = container.querySelector('[data-tabstate="rhythm"]')!
    expect(el.getAttribute('data-warm')).toBe('2.00')
    expect([...el.querySelectorAll('[data-dot]')].map((d) => d.getAttribute('data-k'))).toEqual(Array(6).fill('1.00'))
    expect(rhythmTip(f).split('\n').at(-1)).toBe('Waits for your answer 25 min')
    expect(rhythmTip(facts({ ctx: 88 }))).toContain('Context 88%')
    expect(periodLine(p(9, { msgs: 1 }))).toBe('09:00–10:00 · 1 message')
  })
})

describe('the tab state setting', () => {
  const tab = (f: Facts) => (
    <StripTab s={row()} title="hbr" f={f} index={0} on={false} dim={false} alt={false} gapBefore={false} canClose
      tabRef={() => {}} onSelect={() => {}} onClose={() => {}} onRename={() => {}} onMenu={() => {}} />
  )

  it('is rhythm by default; a broken value is the default', () => {
    expect(TAB_STATE_DEFAULT).toBe('rhythm')
    expect(parseTabState(null)).toBe('rhythm')
    expect(parseTabState('nonsense')).toBe('rhythm')
    expect(parseTabState('dots')).toBe('dots')
  })

  it('switches the tab between the six dots, the dotted strip and nothing, and is saved', () => {
    const { container } = render(<>{tab(facts({ done: 2, all: 2 }))}<TabStateRow /></>)
    expect(container.querySelector('[data-tabstate="rhythm"]')).toBeTruthy()
    expect(container.querySelector('[data-strip="c"]')).toBeNull()
    act(() => { fireEvent.click(screen.getByRole('radio', { name: 'dots' })) })
    expect(localStorage.getItem(TAB_STATE_KEY)).toBe('dots')
    expect(container.querySelector('[data-tabstate="rhythm"]')).toBeNull()
    expect(container.querySelector('[data-strip="c"] [data-part="closed"]')?.getAttribute('data-dots')).toBe('5')
    act(() => { fireEvent.click(screen.getByRole('radio', { name: 'switched off' })) })
    expect(container.querySelector('[data-tabstate="rhythm"]')).toBeNull()
    expect(container.querySelector('[data-strip="c"]')).toBeNull()
    expect(screen.getByRole('radio', { name: 'switched off' }).getAttribute('aria-checked')).toBe('true')
  })

  it('shows the dotted strip\'s own settings only with «dots»', () => {
    render(<StripSettingsRows />)
    expect(screen.getByRole('radiogroup', { name: 'Tab state' })).toBeTruthy()
    expect(screen.queryByRole('radiogroup', { name: 'Parts' })).toBeNull()
    act(() => { fireEvent.click(screen.getByRole('radio', { name: 'dots' })) })
    expect(screen.getByRole('radiogroup', { name: 'Parts' })).toBeTruthy()
  })
})
