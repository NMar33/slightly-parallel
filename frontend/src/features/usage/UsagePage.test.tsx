import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Limits, UsageSummary } from './data'
import { LimitsBlock, UsagePage } from './UsagePage'

const LIMITS: Limits = {
  'claude-code': {
    five_hour: { used: 62.5, resets_at: '2026-11-01T16:40:00', in: '1 h 52 min', span_s: 18000, resets_text: '16:40' },
    seven_day: { used: 31, resets_at: '2026-11-05T09:00:00', in: '3 d 18 h', span_s: 604800, resets_text: 'Thu 09:00' },
    read_at: '2026-11-01T14:02:00', read_at_text: '14:02', stale: false, expired: false, source: 'statusline',
  },
  codex: {
    five_hour: { used: 9, resets_at: '2026-11-01T18:10:00', in: '3 h 22 min', span_s: 18000, resets_text: '18:10' },
    seven_day: { used: null, resets_at: '2026-11-03T06:00:00', in: '1 d 15 h', resets_text: 'Tue 06:00' },
    read_at: '2026-10-31T13:48:00', read_at_text: 'Sat 13:48', stale: false, expired: false, source: 'rollout',
  },
}

const SUMMARY: UsageSummary = {
  range: 'today', days: ['2611-01'], limits: LIMITS,
  usual: { new_output: 2_600_000, cache: 110_000_000, share: 0.97, days_used: 23 },
  totals: { new: 3_660_000, output: 462_000, cache: 212_000_000, cache_write: 1_000_000, share: 0.98, turns: 1204, chats: 41, helpers: { new_output: 1_100_000 } },
  by_tool: [
    { tool: 'codex', new: 460_000, output: 52_000, cache: 14_000_000, share: 0.97, turns: 224, helpers: 0,
      models: [{ model: 'gpt-5-codex', new: 460_000, output: 52_000, cache: 14_000_000, share: 0.97, turns: 224, helpers: 0 }] },
    { tool: 'claude-code', new: 3_200_000, output: 410_000, cache: 198_000_000, share: 0.98, turns: 980, helpers: 1_100_000,
      models: [
        { model: 'claude-opus-4-5', new: 2_900_000, output: 380_000, cache: 190_000_000, share: 0.98, turns: 902, helpers: 1_000_000 },
        { model: 'claude-haiku-4-5', new: 300_000, output: 30_000, cache: 8_100_000, share: 0.96, turns: 78, helpers: 96_000 },
      ] },
  ],
  chats: [
    { agent_id: 'cc-1', title: 'Upload 7: end screen', tool: 'claude-code', model: 'claude-haiku-4-5', models: ['claude-haiku-4-5', 'claude-opus-4-5'], tools: ['claude-code'],
      new_output: 1_200_000, cache: 61_000_000, turns: 88, helpers_n: 2, helpers: { n: 2, new_output: 300_000, cache: 0 }, task_id: 'tk_272c9586' },
    { agent_id: 'cx-2', title: 'Fix the kanban drag', tool: 'codex', model: 'gpt-5-codex', models: ['gpt-5-codex'], tools: ['codex'],
      new_output: 310_000, cache: 9_000_000, turns: 40, helpers_n: 0, task_id: 'tk_272c9586' },
  ],
  chats_total: 41,
  tasks: [
    { id: 'tk_272c9586', title: 'Video: upload 7', new_output: 1_900_000, chats: 3, status: 'doing', done_at: '', project: 'merkhet', tools: ['claude-code'], models: ['claude-opus-4-5'] },
    { id: 'tk_19ab03e2', title: 'Kanban drag fix', new_output: 420_000, chats: 2, status: 'done', done_at: '2026-10-31', project: 'alpha', tools: ['codex'], models: ['gpt-5-codex'] },
  ],
  tasks_total: 2,
  coverage: { chats_recorded: 41, chats_without_usage: 3, chats_from_log: 2, unreadable: ['codex: rollout-2026-11-01.jsonl could not be read'] },
}

const EMPTY: UsageSummary = {
  ...SUMMARY, usual: null, by_tool: [], chats: [], tasks: [],
  totals: { new: 0, output: 0, cache: 0, cache_write: 0, share: null, turns: 0, chats: 0, helpers: null },
  coverage: { chats_recorded: 0, chats_without_usage: 0, unreadable: [] },
}

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/usage']}>
        <Routes>
          <Route path="/usage" element={ui} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function serve(summary: UsageSummary | null, seen: string[] = []) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url)
    seen.push(path)
    const body = path.startsWith('/api/usage/limits') ? { limits: summary?.limits ?? {} }
      : path.startsWith('/api/usage') ? summary
        : path.startsWith('/api/snapshot') ? { projects: [{ code: 'merkhet' }, { code: 'alpha' }] }
          : {}
    if (path.startsWith('/api/usage?') && summary === null) return new Promise<Response>(() => {})
    return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
  }))
}

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

describe('UsagePage', () => {
  it('shows a skeleton while the summary loads', () => {
    serve(null)
    render(wrap(<UsagePage />))
    expect(screen.getByRole('heading', { name: 'Usage' })).toBeTruthy()
    expect(screen.getByLabelText('Loading the usage')).toBeTruthy()
  })

  it('says no usage was recorded, and still shows the limits', async () => {
    serve(EMPTY)
    render(wrap(<UsagePage />))
    expect(await screen.findByText('No usage recorded today.')).toBeTruthy()
    expect(await screen.findByTestId('limits-claude-code')).toBeTruthy()
  })

  it('draws the tiles against the usual day, the table and the two lists', async () => {
    const seen: string[] = []
    serve(SUMMARY, seen)
    render(wrap(<UsagePage />))
    expect(await screen.findByText('4.1M')).toBeTruthy()
    expect(seen.some((p) => p === '/api/usage?project=all&range=today')).toBe(true)
    const ratio = screen.getByText('1.6× usual')
    expect(ratio.getAttribute('style')).toContain('--status-amber-ink')
    expect(screen.getByText('usual 97%')).toBeTruthy()
    expect(screen.getByText('41 chats')).toBeTruthy()
    expect(screen.getByText('usual day: 2.6M new + output')).toBeTruthy()
    // Claude Code first, whatever order the server sent.
    const rows = screen.getAllByRole('row').map((r) => r.textContent ?? '')
    expect(rows.findIndex((r) => r.startsWith('Claude Code'))).toBeLessThan(rows.findIndex((r) => r.startsWith('Codex')))
    expect(screen.getByText(/^41 chats recorded/)).toBeTruthy()
    expect(screen.getByText(/3 chats without usage/)).toBeTruthy()
    expect(screen.getByText(/3 chats without usage · 2 chats from the log/)).toBeTruthy()
    expect(screen.getByText('codex: rollout-2026-11-01.jsonl could not be read')).toBeTruthy()
    // The kanban's word for a status.
    expect(screen.getAllByTestId('task-state').map((c) => c.textContent)).toEqual(['Doing', 'done 31 Oct'])
    // Two of 41 are listed: the rest are counted, not drawn.
    expect(screen.getByText('… 39 more')).toBeTruthy()
  })

  it('gives each tool its own total row, under its models', async () => {
    serve(SUMMARY)
    render(wrap(<UsagePage />))
    const row = await screen.findByTestId('usage-total-claude-code')
    expect(within(row).getByText('Total Claude Code')).toBeTruthy()
    expect(within(row).getAllByRole('cell')).toHaveLength(9)
  })

  const PRICED = { new: 1000, cache: 9000, cache_write: 900, rebuilt: 600, cost_usd: 1234.5, unpriced: 0,
    cost: { new: 0.5, rebuilt: 1000, warm: 200, output: 34, helpers: 0 } }

  it('splits new from rebuilt, adds the input total, and explains them', async () => {
    const tool = { ...SUMMARY.by_tool[0]!, ...PRICED }
    serve({ ...SUMMARY, by_tool: [tool], api_prices: { as_of: '2026-10-06', models: [{ model: 'claude-opus-5-5', input: 4, write_5m: null, write_1h: 8, read: 0.2, output: 20 }] } })
    render(wrap(<UsagePage />))
    const row = await screen.findByTestId(`usage-total-${tool.tool}`)
    expect(within(row).getAllByRole('cell').map((c) => c.textContent).slice(1, 5)).toEqual(['400', '600', '9k', '10k'])
    expect(screen.getByText('What the columns mean')).toBeTruthy()
    const prices = within(screen.getByTestId('usage-prices'))
    expect(prices.getByText('$0.2')).toBeTruthy()
    expect(prices.getByText('—')).toBeTruthy()
    expect(within(screen.getByTestId('usage-written')).getByText('67%')).toBeTruthy()
  })

  it('switches every column to dollars and remembers it', async () => {
    const tool = { ...SUMMARY.by_tool[0]!, ...PRICED }
    serve({ ...SUMMARY, by_tool: [tool] })
    const { unmount } = render(wrap(<UsagePage />))
    await screen.findByTestId(`usage-total-${tool.tool}`)
    fireEvent.click(screen.getByRole('radio', { name: '≈ $' }))
    const cells = within(screen.getByTestId(`usage-total-${tool.tool}`)).getAllByRole('cell').map((c) => c.textContent)
    expect(cells).toHaveLength(10)
    expect(cells.slice(1, 3)).toEqual(['$0.50', '$1,000'])
    expect(cells[9]).toBe('$1,235')
    unmount()
    render(wrap(<UsagePage />))
    expect(within(await screen.findByTestId(`usage-total-${tool.tool}`)).getAllByRole('cell')).toHaveLength(10)
  })

  it('draws dashes for a row with no price', async () => {
    serve({ ...SUMMARY, by_tool: [{ ...SUMMARY.by_tool[0]!, cost_usd: 0, unpriced: 500, cost: { new: 0, rebuilt: 0, warm: 0, output: 0, helpers: 0 } }] })
    render(wrap(<UsagePage />))
    await screen.findByTestId(`usage-total-${SUMMARY.by_tool[0]!.tool}`)
    fireEvent.click(screen.getByRole('radio', { name: '≈ $' }))
    const cells = within(screen.getByTestId(`usage-total-${SUMMARY.by_tool[0]!.tool}`)).getAllByRole('cell')
    expect(cells[1]!.textContent).toBe('—')
    expect(cells[9]!.textContent).toBe('—')
  })

  it('shows the chats, the tasks and the rebuild causes in the same table', async () => {
    serve({ ...SUMMARY,
      chats: [{ ...SUMMARY.chats[0]!, new: 5000, rebuilt: 4000, rebuilds: 7 }],
      by_cause: [{ cause: 'expired', rebuilt: 4000, cost_usd: 2, events: 7, chats: 1 }] })
    render(wrap(<UsagePage />))
    await screen.findByRole('radio', { name: 'chat' })
    fireEvent.click(screen.getByRole('radio', { name: 'chat' }))
    const row = within(screen.getByTestId('usage-slice')).getAllByRole('row')[1]!
    expect(within(row).getByRole('link').getAttribute('href')).toContain('/agent/')
    expect(within(row).getByText('7')).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: 'task' }))
    expect(screen.getByTestId('usage-slice')).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: 'rebuild cause' }))
    const causes = within(screen.getByTestId('usage-causes'))
    expect(causes.getByText('Cache expired')).toBeTruthy()
    expect(causes.getByText('4k')).toBeTruthy()
    expect(screen.getByText('What the causes mean')).toBeTruthy()
  })

  it('shows the ratio only from three days with usage', async () => {
    serve({ ...SUMMARY, usual: { ...SUMMARY.usual!, days_used: 2 } })
    render(wrap(<UsagePage />))
    await screen.findByText('4.1M')
    expect(screen.queryByText(/× usual/)).toBeNull()
  })

  it('filters the two lists by a tool button, says so above them, and clears', async () => {
    serve(SUMMARY)
    render(wrap(<UsagePage />))
    await screen.findByText('Upload 7: end screen')
    const codex = screen.getByRole('button', { name: 'Codex' })
    expect(codex.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(codex)
    expect(codex.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByTestId('usage-filter').textContent).toBe('Showing Codex·Show all')
    expect(screen.queryByText('Upload 7: end screen')).toBeNull()
    expect(screen.getByText('Fix the kanban drag')).toBeTruthy()
    // The task follows its own tools, not the task of a chat the filter kept.
    expect(screen.queryByText('Video: upload 7')).toBeNull()
    expect(screen.getByText('Kanban drag fix')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }))
    expect(screen.getByText('Upload 7: end screen')).toBeTruthy()
  })

  it('a model keeps every chat that used it, not only its last model', async () => {
    serve(SUMMARY)
    render(wrap(<UsagePage />))
    await screen.findByText('Upload 7: end screen')
    fireEvent.click(screen.getByRole('button', { name: 'claude-opus-4-5' }))
    expect(screen.getByTestId('usage-filter').textContent).toBe('Showing Claude Code · claude-opus-4-5·Show all')
    expect(screen.getByText('Upload 7: end screen')).toBeTruthy()
    expect(screen.queryByText('Fix the kanban drag')).toBeNull()
  })

  it('asks again for another range, and a chat is a link to its page', async () => {
    const seen: string[] = []
    serve(SUMMARY, seen)
    render(wrap(<UsagePage />))
    await screen.findByText('Upload 7: end screen')
    fireEvent.click(screen.getByRole('radio', { name: '30 days' }))
    await vi.waitFor(() => expect(seen).toContain('/api/usage?project=all&range=30d'))
    const link = screen.getByRole('link', { name: /Upload 7: end screen/ })
    expect(link.getAttribute('href')).toBe('/agent/cc-1')
    fireEvent.click(link)
    expect((await screen.findByTestId('where')).textContent).toBe('/agent/cc-1')
  })

  it('heads the tiles with the range of the answer drawn, dimmed while the next loads', async () => {
    let release: (() => void) | null = null
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const path = String(url)
      if (path.includes('range=7d')) await new Promise<void>((r) => { release = r })
      const body = path.startsWith('/api/usage/limits') ? { limits: LIMITS }
        : path.startsWith('/api/usage') ? { ...SUMMARY, range: path.includes('range=7d') ? '7d' : 'today' } : {}
      return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
    }))
    render(wrap(<UsagePage />))
    await screen.findByText('4.1M')
    fireEvent.click(screen.getByRole('radio', { name: '7 days' }))
    await vi.waitFor(() => expect(document.querySelector('[aria-busy="true"]')).not.toBeNull())
    expect(screen.getByText(/^Today · /)).toBeTruthy()
    release!()
    expect(await screen.findByText('Last 7 days')).toBeTruthy()
    expect(document.querySelector('[aria-busy="true"]')).toBeNull()
  })

  it('says the limits could not be read instead of "no limits yet"', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const path = String(url)
      if (path.startsWith('/api/usage/limits')) return new Response('boom', { status: 500 })
      return new Response(JSON.stringify(path.startsWith('/api/usage') ? SUMMARY : {}), { status: 200, headers: { 'content-type': 'application/json' } })
    }))
    render(wrap(<UsagePage />))
    expect(await screen.findByText('Could not read the plan limits.')).toBeTruthy()
    expect(screen.queryByText(/No limits from Claude Code yet/)).toBeNull()
  })
})

describe('LimitsBlock', () => {
  const now = new Date('2026-11-01T14:48:00')

  it('draws two bars per tool with the server\'s words and the even-pace mark', () => {
    render(<LimitsBlock limits={LIMITS} now={now} />)
    const cc = within(screen.getByTestId('limits-claude-code'))
    expect(cc.getByText('62%')).toBeTruthy()
    expect(cc.getByText('resets 16:40 · in 1 h 52 min')).toBeTruthy()
    expect(cc.getByText('resets Thu 09:00 · in 3 d 18 h')).toBeTruthy()
    expect(cc.getByText('read 14:02, from the open chat')).toBeTruthy()
    expect(cc.getAllByTitle(/^Even pace: \d+% of the window has passed$/)).toHaveLength(2)
    expect(cc.getAllByRole('img')[0]!.getAttribute('aria-label'))
      .toBe('5-hour limit 62%, Even pace: 63% of the window has passed, resets 16:40 · in 1 h 52 min')
  })

  it('draws a dash for a window the tool gave no number for, and no mark without its length', () => {
    render(<LimitsBlock limits={LIMITS} now={now} />)
    const cx = within(screen.getByTestId('limits-codex'))
    expect(cx.getByText('—')).toBeTruthy()
    expect(cx.getByText('read Sat 13:48')).toBeTruthy()
    // The 5-hour window says its length; the weekly one does not, and Codex's is not assumed.
    expect(cx.getAllByTitle(/^Even pace/)).toHaveLength(1)
  })

  it('dims a stale reading and says why', () => {
    render(<LimitsBlock limits={{ 'claude-code': { ...LIMITS['claude-code']!, stale: true } }} now={now} />)
    const row = screen.getByTestId('limits-claude-code')
    expect(row.className).toContain('opacity-60')
    expect(screen.getByText('Claude Code sends its limits only while a chat is open. Last reading 14:02.')).toBeTruthy()
  })

  it('draws an empty bar after a reset with no reading since', () => {
    const late = new Date('2026-11-01T17:00:00')
    render(<LimitsBlock limits={{ 'claude-code': LIMITS['claude-code']! }} now={late} />)
    expect(screen.getByText('Reset at 16:40. No reading since.')).toBeTruthy()
  })

  it('draws one group per account when Claude Code reports several, newest first', () => {
    const cc = LIMITS['claude-code']!
    const second = {
      ...cc, account: 'bbbbbbbbbbbb', model: 'claude-fable-5-1', session: 'fable123',
      five_hour: { ...cc.five_hour!, used: 4, resets_text: '18:30', in: '3 h 42 min' },
      seven_day: { ...cc.seven_day!, used: 60 }, read_at_text: '14:40',
    }
    const first = { ...cc, account: '2403ec81aa11', model: 'claude-opus-5-5', session: 'opus1234', stale: true }
    const limits: Limits = { 'claude-code': { ...second, series: [second, first], accounts_n: 2, models_n: 2 } }
    render(<LimitsBlock limits={limits} now={now} />)
    const groups = within(screen.getByTestId('limits-claude-code')).getAllByTestId(/^limits-claude-code-/)
    expect(groups.map((g) => g.getAttribute('data-testid'))).toEqual(['limits-claude-code-bbbbbbbbbbbb', 'limits-claude-code-2403ec81aa11'])
    const [b, a] = groups.map((g) => within(g))
    expect(b!.getByText('Claude Code · account bbbbbbbb')).toBeTruthy()
    expect(b!.getByText('4%')).toBeTruthy()
    expect(b!.getByText('resets 18:30 · in 3 h 42 min')).toBeTruthy()
    expect(a!.getByText('Claude Code · account 2403ec81')).toBeTruthy()
    expect(a!.getByText('62%')).toBeTruthy()
    expect(groups[1]!.className).toContain('opacity-60')
    expect(groups[0]!.className).not.toContain('opacity-60')
    expect(screen.queryByText(/fable|opus/)).toBeNull()
  })

  it('draws one account as before: the tool\'s name alone, whatever the models', () => {
    const cc = LIMITS['claude-code']!
    const one = { ...cc, account: '2403ec81aa11', model: 'claude-opus-5-5' }
    render(<LimitsBlock limits={{ 'claude-code': { ...cc, series: [one], accounts_n: 1, models_n: 2 } }} now={now} />)
    expect(screen.getByTestId('limits-claude-code').className).not.toContain('gap-10')
    expect(screen.getByText('Claude Code')).toBeTruthy()
    expect(screen.queryByText(/account/)).toBeNull()
  })

  it('says when Claude Code has sent no limits yet', () => {
    render(<LimitsBlock limits={{}} now={now} />)
    expect(screen.getByText('No limits from Claude Code yet. They appear after the first reply in a chat, on Pro and Max plans.')).toBeTruthy()
  })
})

describe('the Codex row before its first reading', () => {
  const now = new Date('2026-11-01T14:48:00')
  const poll = { found: true, enabled: true, every_hours: 6, last_attempt: '', last_success: '', next_attempt: '', cause: '', failures: 0 }

  it('says Codex is here and how often it is read, and the cause when it could not be', () => {
    render(<LimitsBlock limits={{ 'claude-code': LIMITS['claude-code']! }} now={now} codexPoll={{ ...poll, cause: 'not signed in' }} />)
    const row = within(screen.getByTestId('limits-codex-empty'))
    expect(row.getByText('Codex is on this machine. Its limits are read every 6 hours. Could not read them: not signed in.')).toBeTruthy()
    expect(row.queryByRole('button', { name: 'Read now' })).toBeNull()
  })

  it('is not drawn once Codex has a reading, nor without Codex on the machine', () => {
    render(<LimitsBlock limits={LIMITS} now={now} codexPoll={poll} />)
    expect(screen.queryByTestId('limits-codex-empty')).toBeNull()
    render(<LimitsBlock limits={{}} now={now} codexPoll={{ ...poll, found: false }} />)
    expect(screen.queryByTestId('limits-codex-empty')).toBeNull()
  })

  it('keeps a stale reading drawn, with why the last try failed and the way to ask now', () => {
    const asked = vi.fn(async () => undefined)
    render(<LimitsBlock limits={{ codex: { ...LIMITS.codex!, stale: true } }} now={now} codexPoll={{ ...poll, cause: 'dns error' }} onRefresh={asked} />)
    expect(screen.getByTestId('limits-codex')).toBeTruthy()
    const read = within(screen.getByTestId('limits-codex-read'))
    expect(read.getByText('Could not read them: dns error.')).toBeTruthy()
    fireEvent.click(read.getByRole('button', { name: 'Read now' }))
    expect(asked).toHaveBeenCalledOnce()
  })

  it('adds nothing under a fresh reading', () => {
    render(<LimitsBlock limits={{ codex: { ...LIMITS.codex!, stale: false } }} now={now} codexPoll={{ ...poll, cause: 'dns error' }} />)
    expect(screen.queryByTestId('limits-codex-read')).toBeNull()
  })

  it('names an app-server reading as such', () => {
    render(<LimitsBlock limits={{ codex: { ...LIMITS.codex!, source: 'app-server' } }} now={now} />)
    expect(within(screen.getByTestId('limits-codex')).getByText(/from app-server/)).toBeTruthy()
  })

  it('asks the server for a fresh reading once when the page opens without one', async () => {
    const seen: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url)
      seen.push(`${init?.method ?? 'GET'} ${path}`)
      const body = path.startsWith('/api/usage/limits/refresh') ? { refreshed: true }
        : path.startsWith('/api/usage/limits') ? { limits: { 'claude-code': LIMITS['claude-code'] }, codex_poll: poll }
          : path.startsWith('/api/usage') ? SUMMARY
            : path.startsWith('/api/snapshot') ? { projects: [{ code: 'merkhet' }] }
              : {}
      return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
    }))
    render(wrap(<UsagePage />))
    expect(await screen.findByTestId('limits-codex-empty')).toBeTruthy()
    await vi.waitFor(() => expect(seen.filter((s) => s.startsWith('POST /api/usage/limits/refresh'))).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: 'Read now' }))
    await vi.waitFor(() => expect(seen.filter((s) => s.startsWith('POST /api/usage/limits/refresh'))).toHaveLength(2))
  })
})
