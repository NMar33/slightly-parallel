import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AquaDesign } from '../AquaDesign'
import { SESSIONS } from '../mock'
import { resetAqua } from '../store'
import { resetDesk } from '../round2/desk'
import { getLab, labWith, resetLab, resetStrip, type Facts } from '../round3/lab/live'
import { resetLab2 } from '../round3/lab2/store'
import { resetHealth } from '../round3/lab3/healthModel'
import { picksText, picksUrl, type Picks } from '../round4/CopyPicks'
import { CTX_CHAT, MOMENTS, MOMENT_FACTS, WAIT_CHAT, signal, tickContext, type Moment, type TabState } from './tabStateModel'
import { activity, freshMood, getMood, moodOf, resetMood, values, warmDots, warmth } from './mood'

const page = (q: string) => render(<MemoryRouter initialEntries={[`/aqua${q}`]}><AquaDesign /></MemoryRouter>)
const variants = () => screen.getByRole('region', { name: 'Variants' })
const tile = (name: string) => screen.getByRole('region', { name })
const tabOf = (id: string) => document.querySelector(`.aq [data-lab-tab="${id}"]`)!
const s = (id: string) => SESSIONS.find((x) => x.id === id)!

beforeEach(() => {
  resetAqua(); resetDesk(); resetLab(); resetStrip(); resetLab2(); resetHealth(); resetMood()
  try { localStorage.clear() } catch { /* private mode */ }
  Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true })
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}')))
})
afterEach(() => { vi.unstubAllGlobals() })

/** The facts of a chat at a frozen moment. */
const at = (m: Moment, id: string): Facts => labWith(MOMENT_FACTS[m]).facts[id]!

describe('the round bar', () => {
  it('opens L by default and shows L and K up front, the earlier versions folded', () => {
    page('')
    expect(document.querySelector('.aq[data-v="l"]')).toBeTruthy()
    const bar = screen.getByRole('tablist', { name: 'Variant' })
    expect(within(bar).getAllByRole('tab').map((b) => b.textContent)).toEqual(['L · K + tab state', 'K · J + variants 18.11'])
    fireEvent.click(screen.getByRole('button', { name: /Early versions/ }))
    expect(within(bar).getAllByRole('tab')).toHaveLength(12)
  })
})

describe('each variant at the three frozen moments', () => {
  // [variant, moment, chat] → [kind, level]
  const cases: Array<[TabState, Moment, string, string | null, string | null]> = [
    ['a', 'calm', WAIT_CHAT, null, null], ['a', 'calm', CTX_CHAT, null, null],
    ['a', 'wait', WAIT_CHAT, 'wait', 'red'], ['a', 'ctx', CTX_CHAT, 'ctx', 'amber'],
    ['b', 'calm', WAIT_CHAT, 'wait', 'green'], ['b', 'wait', WAIT_CHAT, 'wait', 'red'], ['b', 'ctx', CTX_CHAT, null, null],
    ['c', 'calm', WAIT_CHAT, 'wait', 'green'], ['c', 'calm', CTX_CHAT, null, null],
    ['c', 'wait', WAIT_CHAT, 'wait', 'red'], ['c', 'ctx', CTX_CHAT, 'ctx', 'amber'],
    ['d', 'calm', WAIT_CHAT, 'wait', 'green'], ['d', 'calm', CTX_CHAT, null, null],
    ['d', 'wait', WAIT_CHAT, 'wait', 'red'], ['d', 'ctx', CTX_CHAT, 'ctx', 'amber'],
    ['now', 'wait', WAIT_CHAT, null, null], ['e', 'ctx', CTX_CHAT, null, null], ['f', 'wait', WAIT_CHAT, null, null],
  ]
  it.each(cases)('%s at %s on %s: %s %s', (look, m, id, kind, level) => {
    const sig = signal(look, at(m, id), s(id).state === 'waiting')
    expect([sig.kind, sig.level]).toEqual([kind, level])
  })

  it('b marks context over 70% on the dot, and fills the ring with the wait', () => {
    expect(signal('b', at('ctx', CTX_CHAT), false).notch).toBe('amber')
    expect(signal('b', at('calm', CTX_CHAT), false).notch).toBeNull()
    expect(signal('b', at('wait', WAIT_CHAT), true).fill).toBeCloseTo(25 / 30)
  })
})

describe('L live', () => {
  it('a: nothing over a calm tab, a line once the jump makes a chat wait 25 min', () => {
    page('?v=l&tabstate=a')
    act(() => { fireEvent.click(within(variants()).getByRole('button', { name: 'all calm' })) })
    expect(tabOf(WAIT_CHAT).querySelector('[data-tabstate="a"]')!.getAttribute('data-kind')).toBe('none')
    expect(document.querySelector('.aq [data-strip]')).toBeNull()
    act(() => { fireEvent.click(within(variants()).getByRole('button', { name: 'waits 25 min' })) })
    expect(tabOf(WAIT_CHAT).querySelector('[data-tabstate="a"]')!.getAttribute('data-level')).toBe('red')
    act(() => { fireEvent.click(within(variants()).getByRole('button', { name: 'context 80%' })) })
    expect(tabOf(CTX_CHAT).querySelector('[data-tabstate="a"]')!.getAttribute('data-level')).toBe('amber')
  })

  it('keeps the dots as «as now», shows them in e only while Alt is held, a ring in b', () => {
    page('?v=l&tabstate=now')
    expect(tabOf(CTX_CHAT).querySelector('[data-strip="c"]')).toBeTruthy()
    act(() => { fireEvent.click(within(variants()).getByRole('radio', { name: /only with Alt/ })) })
    expect(document.querySelector('.aq [data-strip]')).toBeNull()
    fireEvent.keyDown(window, { key: 'Alt', altKey: true })
    expect(tabOf(CTX_CHAT).querySelector('[data-strip="c"]')).toBeTruthy()
    expect(document.querySelector('[data-alt="a"]')).toBeTruthy()
    fireEvent.keyUp(window, { key: 'Alt' })
    act(() => { fireEvent.click(within(variants()).getByRole('radio', { name: /ring on the dot/ })) })
    expect(tabOf(WAIT_CHAT).querySelector('[data-tabstate="b"] svg')).toBeTruthy()
  })

  it('grows the context of working chats and compacts at 96%', () => {
    const before = getLab().facts[CTX_CHAT]!.ctx
    tickContext()
    expect(getLab().facts[CTX_CHAT]!.ctx).toBe(before + 1)
    expect(getLab().facts[WAIT_CHAT]!.ctx).toBe(s(WAIT_CHAT).ctx)
    for (let i = 0; i < 40; i++) tickContext()
    expect(getLab().facts[CTX_CHAT]!.ctx).toBeLessThan(50)
  })

  it('has the switch with its hint in the Variants panel, and no Strip row', () => {
    page('?v=l&tabstate=a')
    const panel = variants()
    expect(within(panel).getByRole('radiogroup', { name: 'Tab state' }).querySelectorAll('[role="radio"]')).toHaveLength(7)
    expect(within(panel).getByText('Wait a minute, or press a button below')).toBeTruthy()
    expect(within(panel).queryByRole('radiogroup', { name: 'Strip' })).toBeNull()
  })
})

describe('f · six dots', () => {
  it('is the default, pattern 1, six dots on every tab', () => {
    page('?v=l')
    expect(tabOf(CTX_CHAT).querySelector('[data-tabstate="f"]')!.getAttribute('data-pattern')).toBe('1')
    expect(document.querySelector('.aq [data-strip]')).toBeNull()
  })

  it('gives every chat its own row: the rhythm of six hours differs between chats', () => {
    const m = freshMood()
    const row = (id: string) => moodOf(m, s(id)).hours.map(activity).map((x) => x.toFixed(2)).join()
    const rows = ['cc-4e7a19d2', 'cc-b03d55e1', 'cc-c37d2e86', 'cx-0d4b8e37', 'cc-5a0f7e19', 'cx-91c2f0a7'].map(row)
    expect(new Set(rows).size).toBe(6)
  })

  it('stays cool when calm and warms from the right: amber past 5 min, red at 20', () => {
    const m = moodOf(freshMood(), s(WAIT_CHAT))
    expect(warmth(at('calm', WAIT_CHAT), true, m)).toBe(0)
    expect(warmDots(0)).toEqual([0, 0, 0, 0, 0, 0])
    const u = warmth({ ...at('calm', WAIT_CHAT), waited: 8 }, true, m)
    expect(u).toBeGreaterThan(0)
    expect(u).toBeLessThan(1)
    const d = warmDots(u)
    expect(d[5]).toBeGreaterThan(0)
    expect(d[0]).toBe(0)
    expect(warmth(at('wait', WAIT_CHAT), true, m)).toBeGreaterThan(1.9)
    expect(warmth(at('ctx', CTX_CHAT), false, moodOf(freshMood(), s(CTX_CHAT)))).toBeGreaterThan(0)
    expect(warmth(at('calm', CTX_CHAT), false, { ...m, checkFailed: true })).toBe(1.5)
  })

  it('pattern 3 shows six properties; 1 and 2 the six hours', () => {
    const m = moodOf(freshMood(), s(CTX_CHAT))
    const f = at('ctx', CTX_CHAT)
    expect(values('1', m, f, false)).toEqual(values('2', m, f, false))
    expect(values('3', m, f, false)[1]).toBeCloseTo(0.8)
  })

  it('draws six dots in the pattern picked, and «+3 commits» changes the newest one', () => {
    page('?v=l&tabstate=f&pattern=1')
    const dots = () => tabOf(CTX_CHAT).querySelectorAll('[data-tabstate="f"] [data-dot]')
    expect(dots()).toHaveLength(6)
    const before = moodOf(getMood(), s(CTX_CHAT)).hours[5]!.commits
    act(() => { fireEvent.click(within(variants()).getByRole('button', { name: '+3 commits' })) })
    expect(moodOf(getMood(), s(CTX_CHAT)).hours[5]!.commits).toBe(before + 3)
    act(() => { fireEvent.click(within(variants()).getByRole('radio', { name: /constellation/ })) })
    expect(tabOf(CTX_CHAT).querySelector('[data-tabstate="f"]')!.getAttribute('data-pattern')).toBe('2')
    act(() => { fireEvent.click(within(variants()).getByRole('button', { name: 'check failed' })) })
    expect(tabOf(CTX_CHAT).querySelector('[data-tabstate="f"]')!.getAttribute('data-warm')).toBe('1.50')
  })
})

describe('the compare view of the tab state', () => {
  it('opens from «Compare» first, with a tile per variant and per pattern of f', () => {
    page('?v=l')
    fireEvent.click(within(variants()).getByRole('button', { name: /^Compare$/ }))
    const view = screen.getByRole('dialog', { name: 'Compare variants' })
    expect(view.getAttribute('data-compare')).toBe('tabstate')
    expect(within(within(view).getByRole('tablist', { name: 'Feature' })).getAllByRole('tab').map((b) => b.textContent)).toEqual(['Tab state', 'Tabs with Alt', 'Button +', 'Message menu', 'Colour schemes', 'Health and time'])
    const tiles = Array.from(document.querySelectorAll('[data-tile]'))
    expect(tiles).toHaveLength(9)
    for (const x of tiles) expect(x.querySelector('[inert]')?.childElementCount).toBeGreaterThan(0)
  })

  it('freezes every variant at the three moments, whatever the live pick', () => {
    page('?v=l&tabstate=now&compare=tabstate')
    const row = (v: string, m: Moment) => tile(v).querySelector(`[data-moment="${m}"] [data-closeup]`)!
    for (const m of MOMENTS) expect(tile('As now').querySelector(`[data-moment="${m}"]`)).toBeTruthy()
    expect(row('A · only when it matters', 'calm').querySelector('[data-tabstate="a"]')!.getAttribute('data-kind')).toBe('none')
    expect(row('A · only when it matters', 'wait').querySelector('[data-tabstate="a"]')!.getAttribute('data-level')).toBe('red')
    expect(row('A · only when it matters', 'ctx').querySelector('[data-tabstate="a"]')!.getAttribute('data-level')).toBe('amber')
    expect(row('B · ring on the dot', 'ctx').querySelector('[data-tabstate="b"]')!.getAttribute('data-notch')).toBe('amber')
    expect(row('C · tab background', 'wait').querySelector('[data-tabstate="c"]')!.getAttribute('data-level')).toBe('red')
    expect(row('D · one line below', 'ctx').querySelector('[data-tabstate="d"]')!.getAttribute('data-kind')).toBe('ctx')
    expect(row('E · only with Alt', 'wait').querySelector('[data-strip]')).toBeNull()
    expect(tile('E · only with Alt').querySelector('[data-alt-held] [data-strip="c"]')).toBeTruthy()
    expect(row('As now', 'calm').querySelector('[data-strip="c"]')).toBeTruthy()
    // f: each pattern on three chats, calm and warm
    const warm = tile('F2 · constellation').querySelectorAll('[data-warm-closeup] [data-tabstate="f"]')
    expect(warm).toHaveLength(3)
    for (const x of Array.from(warm)) expect(Number(x.getAttribute('data-warm'))).toBeGreaterThan(0)
    expect(tile('F3 · six properties').querySelector('[data-tabstate="f"]')!.getAttribute('data-pattern')).toBe('3')
  })

  it('«Choose this variant» switches the live pick and «Open live» goes to the window', () => {
    page('?v=l&tabstate=a&compare=tabstate')
    expect(within(tile('A · only when it matters')).getByText('chosen')).toBeTruthy()
    fireEvent.click(within(tile('D · one line below')).getByRole('button', { name: 'Choose this variant' }))
    expect(within(tile('D · one line below')).getByText('chosen')).toBeTruthy()
    fireEvent.click(within(tile('F3 · six properties')).getByRole('button', { name: 'Open live' }))
    expect(screen.queryByRole('dialog', { name: 'Compare variants' })).toBeNull()
    expect(tabOf(CTX_CHAT).querySelector('[data-tabstate="f"]')!.getAttribute('data-pattern')).toBe('3')
  })
})

describe('«Copy the picks» in L', () => {
  const PICKS: Picks = { lab: { tabs: 'b', strip: 'a', plus: 'c', plusmenu: 'a' }, menu: 'a', scheme: 'tokyo-night', scope: 'window', health: 'd', clock: 60 }

  it('K\'s text is as it was', () => {
    const url = picksUrl('http://x', '/aqua', new URLSearchParams('v=k'), PICKS)
    expect(picksText(PICKS, url).split('\n')[0]).toBe('Picks in mockup K (/aqua?v=k):')
    expect(picksText(PICKS, url)).toContain('Strip: a — segments')
  })

  it('copies the tab state line, without the Strip line, with the address of L', async () => {
    const write = vi.fn(async (_: string) => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: write }, configurable: true })
    page('?v=l&tabstate=f&pattern=2')
    await act(async () => { fireEvent.click(within(variants()).getByRole('button', { name: 'Copy the picks' })) })
    const lines = (write.mock.calls[0]![0]).split('\n')
    expect(lines[0]).toBe('Picks in mockup L (/aqua?v=l):')
    expect(lines[1]).toBe('Tab state: f — six dots, pattern f2 — constellation')
    expect(lines.some((x) => x.startsWith('Strip:'))).toBe(false)
    expect(lines.at(-1)).toMatch(/\/aqua\?v=l&/)
    expect(lines.at(-1)).toContain('tabstate=f&pattern=2')
    expect(lines.at(-1)).not.toContain('strip=')
  })
})
