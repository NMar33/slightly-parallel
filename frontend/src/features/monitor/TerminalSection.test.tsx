/**
 * The terminal's part of the Monitor page: the day in one line, what was
 * found, the buttons for the full log and the report.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TerminalSection, type TermLogSummary } from './TerminalSection'

const hours = Array.from({ length: 24 }, (_, h) => ({ h, frames: h === 14 ? 600 : 0, slow: h === 14 ? 4 : 0, stalls: h === 14 ? 1 : 0, errors: 0, reconnects: 0, findings: 0, p95: 17 }))
const summary: TermLogSummary = {
  day: '2026-11-18', mode: 'light', setting: 'light', full_until: null,
  totals: { frames: 600, slow: 4, stalls: 1, errors: 1, reconnects: 0, findings: 2, in: 40960, out: 120, pastes: 2, keys: 50, wheels: 90, longtasks: 1, fetch_errors: 1, p50: 17, p95: 20, max: 240, page_minutes: 3, self_ms: 12 },
  hours,
  findings: [
    { t: 1_794_970_000_000, kind: 'scroll-stall', sid: 't-1', p: 'alpha', doing: 'scroll', n: 240, what: 'frame' },
    { t: 1_794_969_000_000, kind: 'fetch', sid: 't-1', p: 'alpha', doing: 'scroll', n: 12, what: '/api/terminal/sessions/:id/open no answer' },
  ],
  by_kind: { 'scroll-stall': 1, fetch: 1 }, scroll: { smooth: 90 }, paste: { native: 2 }, mem: { heap: 30e6 },
  server: { tmux: { 'capture-pane': { n: 10, avg: 4, max: 2001, timeouts: 1, slow: 1 } }, writes: { n: 50, max: 3, slow: 0 }, sends: { n: 400, max: 12, slow: 0 } },
  files: { folder: '/data/terminal/log', light_bytes: 3000, full_bytes: 0, full_files: 0 },
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('TerminalSection', () => {
  it('shows the day, what was found, the tmux calls, and turns the full log on for an hour', async () => {
    const posts: unknown[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/terminal/log/mode' && init?.method === 'POST') {
        posts.push(JSON.parse(String(init.body)))
        return new Response(JSON.stringify({ mode: 'full' }), { status: 200 })
      }
      return new Response(JSON.stringify(summary), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><TerminalSection /></QueryClientProvider>)
    await waitFor(() => expect(screen.getByTestId('term-log-health').textContent).toMatch(/600 frames, p95 20 ms, 4 slow · 1 stalls · 1 errors/))
    expect(screen.getByText('Scrolling stalled')).toBeTruthy()
    expect(screen.getByText(/:id\/open no answer/)).toBeTruthy()
    expect(screen.getByText('capture-pane')).toBeTruthy()
    expect(screen.getByRole('link', { name: /download report/i }).getAttribute('href')).toBe('/api/terminal/log/report')
    fireEvent.click(screen.getByRole('button', { name: /turn on the full log for 1 hour/i }))
    await waitFor(() => expect(posts).toEqual([{ mode: 'full', hours: 1 }]))
  })
})
