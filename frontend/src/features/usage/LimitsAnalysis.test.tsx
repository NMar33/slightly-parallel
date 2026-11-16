import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { UsageAnalysis } from './data'
import { LimitsAnalysis, said, type Insight } from './LimitsAnalysis'

const A: UsageAnalysis = {
  window_now: { used: 19, resets_at: '2026-11-10T14:30:00', runs_out_at: null, lasts: true },
  units: { models: [] },
  mix: { total_pct: 400, windows: 4, helpers_n: 44, parts: [{ key: 'over_500k', pct: 160 }, { key: 'helpers', pct: 60 }, { key: 'under_200k', pct: 180 }] },
}
const ITEMS: Insight[] = [
  { id: 'in_1', at: '2026-11-10T09:00:00', kind: 'chat', params: { share: 42, pct: 169, title: 'a chat', agent_id: 'cc-1' }, pinned: true },
  { id: 'in_2', at: '2026-11-10T09:00:00', kind: 'resume', params: { each: 3.9, n: 16, total: 63, ctx: 450000 }, pinned: false },
]

function serve(seen: string[]) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    seen.push(`${init?.method ?? 'GET'} ${String(url)}`)
    return new Response(JSON.stringify({ items: ITEMS, hidden: 0 }), { status: 200, headers: { 'content-type': 'application/json' } })
  }))
}
const draw = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><LimitsAnalysis a={A} range="in the last 7 days" /></MemoryRouter>
  </QueryClientProvider>)
afterEach(() => { vi.unstubAllGlobals() })

describe('LimitsAnalysis', () => {
  it('says the limit now, how many limits were used, and what used them', () => {
    serve([])
    draw()
    expect(screen.getByTestId('analysis-now').textContent).toBe('Now 19% of the 5-hour limit is used. At this rate it will last until the reset at 14:30.')
    expect(screen.getByText('Claude Code used 4 full 5-hour limits in the last 7 days.')).toBeTruthy()
    expect(within(screen.getByTestId('analysis-split')).getByText('Replies in chats under 200,000 tokens')).toBeTruthy()
  })

  it('shows each message with its date and title, and its reason on a click', async () => {
    serve([])
    draw()
    const card = await screen.findByTestId('insight-resume')
    expect(within(card).getByText('Returning to a long chat after a break uses 3.9% of the limit')).toBeTruthy()
    expect(within(card).getByText('10 Nov')).toBeTruthy()
    expect(within(card).queryByText(/start a new chat and paste a short summary/)).toBeNull()
    fireEvent.click(within(card).getByRole('button', { expanded: false }))
    expect(within(card).getByText(/In the last 7 days this happened 16 times, with 450,000 tokens in the chat on average/)).toBeTruthy()
    expect(within(card).getByText(/start a new chat and paste a short summary of the work/)).toBeTruthy()
  })

  it('pins, hides, and clears all but the pinned', async () => {
    const seen: string[] = []
    serve(seen)
    draw()
    const card = await screen.findByTestId('insight-resume')
    fireEvent.click(within(card).getByRole('button', { name: 'Pin' }))
    fireEvent.click(within(card).getByRole('button', { name: 'Hide' }))
    fireEvent.click(screen.getByRole('button', { name: 'Clear all' }))
    await vi.waitFor(() => expect(seen.filter((s) => s.startsWith('POST'))).toEqual([
      'POST /api/usage/insights/in_2/pin', 'POST /api/usage/insights/in_2/hide', 'POST /api/usage/insights/clear']))
  })

  it('compares the models with Opus and prices one action of each kind', () => {
    serve([])
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><LimitsAnalysis range="in the last 7 days" a={{ ...A,
          units: { ...A.units, models: [{ model: 'claude-opus-5-5', pct_per_usd: 0.62 }] },
          prices: [
            { key: 'message', model: 'claude-fable-5-1', each_pct: 4, times: 42, total_pct: 166 },
            { key: 'message', model: 'claude-opus-5-5', each_pct: 0.36, times: 420, total_pct: 150 },
            { key: 'message', model: 'gpt-6.1-sol', each_pct: 0.3, times: 95, total_pct: 28 },
            { key: 'reply_over_500k', each_pct: 0.2, times: 820, total_pct: 160 },
            { key: 'reply_under_100k', each_pct: 0.03, times: 184, total_pct: 6 },
          ] }} /></MemoryRouter>
      </QueryClientProvider>)
    const models = within(screen.getByTestId('analysis-models'))
    expect(models.getByText('fable 5.1').closest('tr')!.textContent).toContain('11 times more')
    expect(models.queryByText(/gpt/)).toBeNull()
    expect(within(screen.getByTestId('analysis-prices')).getByText('A reply in a chat over 500,000 tokens')).toBeTruthy()
  })

  it('writes every kind as plain sentences', () => {
    for (const kind of ['model', 'context', 'resume', 'helpers', 'chat', 'cheap', 'cap']) {
      const s = said({ id: 'x', at: '2026-11-10T09:00:00', kind, params: { k: 11, f: 4, o: 0.36, n: 42, total: 166, start: '2026-11-09T08:00:00', reset: '2026-11-09T13:00:00', fable: true }, pinned: false })
      expect(s.title).not.toMatch(/→|≈|\{/)
      expect(s.detail).not.toMatch(/→|≈|\{/)
    }
  })
})
