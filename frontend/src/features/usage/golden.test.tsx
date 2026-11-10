import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import summaryToday from '../../../../testdata/usage/expected/summary.today.json'
import limitsAnswer from '../../../../testdata/usage/expected/limits.json'
import strings from '../../../../testdata/usage/expected/strings.json'

import type { TurnUsage, UsageSummary } from './data'
import { UsageLine, turnLine } from './UsageLine'
import { UsagePage } from './UsagePage'

/**
 * The page against the server's own answers for the golden data root
 * (testdata/usage, written by the server's tests under SP_NOW): what the
 * page shows must be the strings the server lists for it (strings.json).
 */

type Reading = { read_at_text: string; stale: boolean } & Record<'five_hour' | 'seven_day', { pct: string; in: string; resets_text: string; expired_text: string }>

const SUMMARY = summaryToday as unknown as UsageSummary
const S = strings as unknown as {
  now: string
  today: {
    tiles: Record<string, string>
    usual: { shows_ratio: boolean; new_output_ratio: string; cache_ratio: string; share: string }
    limits: Record<string, Reading & { series?: Array<Reading & { name: string; testid: string }> }>
    chats: Array<{ agent_id: string; new_output: string; cache: string }>
    tasks: Array<{ id: string; new_output: string; status: string }>
    coverage: string[]
  }
  lines: Record<string, Record<string, string>>
}

/** The chat's turns as /api/usage/chat answers, when the server's tests wrote them. */
const chatTurns = Object.values(import.meta.glob<{ turns: Record<string, TurnUsage> }>(
  '../../../../testdata/usage/expected/chat.cc-golden.json', { eager: true, import: 'default' }))[0]

beforeAll(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(S.now))
})
afterAll(() => { vi.useRealTimers() })
afterEach(() => { vi.unstubAllGlobals() })

function serve() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url)
    const body = path.startsWith('/api/usage/limits') ? limitsAnswer
      : path.startsWith('/api/usage') ? SUMMARY
        : path.startsWith('/api/snapshot') ? { projects: [{ code: 'GOLD' }, { code: 'SIDE' }] }
          : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
  }))
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}><MemoryRouter initialEntries={['/usage']}>{ui}</MemoryRouter></QueryClientProvider>
}

const tile = (label: string) => screen.getByText(label, { selector: 'div' }).parentElement!

describe('the Usage page on the golden data', () => {
  it('draws the tiles as the server words them', async () => {
    serve()
    render(wrap(<UsagePage />))
    await screen.findByText(S.today.tiles.new_output!)
    expect(within(tile('new + output')).getByText(S.today.tiles.new_output!)).toBeTruthy()
    expect(within(tile('cache')).getByText(S.today.tiles.cache!)).toBeTruthy()
    expect(within(tile('cache share')).getByText(S.today.tiles.share!)).toBeTruthy()
    expect(within(tile('turns')).getByText(S.today.tiles.turns!)).toBeTruthy()
    expect(within(tile('turns')).getByText(S.today.tiles.chats!)).toBeTruthy()
    expect(S.today.usual.shows_ratio).toBe(true)
    expect(within(tile('new + output')).getByText(`${S.today.usual.new_output_ratio}× usual`)).toBeTruthy()
    expect(within(tile('cache')).getByText(`${S.today.usual.cache_ratio}× usual`)).toBeTruthy()
    expect(within(tile('cache share')).getByText(`usual ${S.today.usual.share}`)).toBeTruthy()
    // The helpers' total, apart, in the table's last row.
    const totals = screen.getAllByRole('row').filter((r) => r.textContent?.startsWith('Total'))
    expect(totals[totals.length - 1]!.lastElementChild!.textContent).toBe(S.today.tiles.helpers)
  })

  it('draws the limits in the server\'s words', async () => {
    serve()
    render(wrap(<UsagePage />))
    await screen.findByTestId('limits-codex')
    const groups: Array<[string, Reading & { name?: string }]> = Object.entries(S.today.limits).flatMap(([tool, want]) =>
      want.series ? want.series.map((one): [string, Reading & { name?: string }] => [one.testid, one])
        : [[`limits-${tool}`, want] as [string, Reading]])
    // The golden root has one account per tool (two Claude Code models in it): no series named.
    expect(Object.values(S.today.limits).some((x) => x.series)).toBe(false)
    for (const [testid, want] of groups) {
      const el = screen.getByTestId(testid)
      const row = within(el)
      if (want.name) expect(row.getByText(want.name)).toBeTruthy()
      expect(row.getByText(new RegExp(`^read ${want.read_at_text}`))).toBeTruthy()
      for (const w of ['five_hour', 'seven_day'] as const) {
        const x = want[w]
        if (x.expired_text) {
          expect(row.getByText(x.expired_text)).toBeTruthy()
        } else {
          expect(row.getByText(x.pct)).toBeTruthy()
          expect(row.getByText(x.in ? `resets ${x.resets_text} · in ${x.in}` : `resets ${x.resets_text}`)).toBeTruthy()
        }
      }
      expect(el.className.includes('opacity-60')).toBe(want.stale)
    }
  })

  it('lists the tool rows in order, the chats and the tasks as the server sent them', async () => {
    serve()
    render(wrap(<UsagePage />))
    await screen.findByText(S.today.tiles.new_output!)
    const firsts = screen.getAllByRole('row').map((r) => r.firstElementChild?.textContent ?? '')
    expect(firsts.slice(1, 7)).toEqual(['Claude Code', 'claude-opus-4-5', 'claude-sonnet-4-5', 'claude-haiku-4-5', 'Total Claude Code', 'Codex'])
    for (const c of S.today.chats) {
      // The chat list's link: the analysis at the end of the page links the same chats.
      const link = screen.getAllByRole('link', { name: new RegExp(SUMMARY.chats.find((x) => x.agent_id === c.agent_id)!.title) })
        .find((a) => !a.closest('[data-testid="usage-analysis"]'))!
      expect(link.getAttribute('href')).toBe(`/agent/${c.agent_id}`)
      const cells = link.closest('tr')!.querySelectorAll('td')
      expect([cells[1]!.textContent, cells[2]!.textContent]).toEqual([c.new_output, c.cache])
    }
    const states = screen.getAllByTestId('task-state').map((c) => c.textContent)
    // The kanban's words; a done task with the day it was done.
    expect(states).toEqual(S.today.tasks.map((tk) => ({ doing: 'Doing', todo: 'To do', done: 'done 1 Nov' } as Record<string, string>)[tk.status]))
    for (const note of S.today.coverage) expect(screen.getByText(note)).toBeTruthy()
    expect(screen.getByText(/^2 chats recorded · 1 chat without usage/)).toBeTruthy()
  })

  it('filters by Codex: one chat and its task are left', async () => {
    serve()
    render(wrap(<UsagePage />))
    await screen.findByText(S.today.tiles.new_output!)
    fireEvent.click(screen.getByRole('button', { name: 'Codex' }))
    expect(screen.getAllByRole('link', { name: /./ })
      .filter((a) => a.getAttribute('href')?.startsWith('/agent/') && !a.closest('[data-testid="usage-analysis"]'))).toHaveLength(1)
    expect(screen.getAllByTestId('task-state')).toHaveLength(1)
  })
})

describe('the line under a turn on the golden chat', () => {
  it.skipIf(!chatTurns)('shows the server\'s line, and builds the same one when the answer has none', () => {
    const turns = chatTurns!.turns
    let prev: TurnUsage | null = null
    for (const n of Object.keys(turns).sort((a, b) => Number(a) - Number(b))) {
      const u = turns[n]!
      const want = S.lines['cc-golden']![n]
      expect(u.line).toBe(want)
      const { unmount } = render(<UsageLine usage={u} />)
      const el = screen.getByTestId('usage-line').cloneNode(true) as HTMLElement
      el.querySelectorAll('.sr-only').forEach((x) => x.remove())
      expect(el.textContent).toBe(want)
      unmount()
      expect(turnLine({ ...u, line: undefined }, prev)).toBe(want)
      if (u.limit) prev = u
    }
  })
})
