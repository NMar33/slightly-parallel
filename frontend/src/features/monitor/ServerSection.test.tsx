/**
 * The server section of the Monitor page: the four numbers, the slow paths, the log, and the copy.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ServerSection } from './ServerSection'

const answer = {
  summary: {
    started_at: 1_790_000_000, uptime_s: 4_000, data_root: '/data', log_file: '/x/sp.log', log_file_bytes: 2048,
    view_age_ms: 3_000, load_errors: [], rss_mb: 160, threads: 29, records_n: 3, since: 1_790_000_000,
    requests: { n: 2, slow_n: 1, by_path: [
      { path: 'GET /api/sessions/turns', n: 1, p50_ms: 700, max_ms: 700, total_ms: 700, errors: 0 },
      { path: 'GET /api/health', n: 1, p50_ms: 3, max_ms: 3, total_ms: 3, errors: 0 },
    ] },
    rebuilds: { n: 2, p50_ms: 300, max_ms: 500, last_ms: 300 },
    errors_n: 0, warnings_n: 1, slow_request_ms: 300,
  },
  records: [
    { ts: 1_790_000_001, level: 'INFO', logger: 'sp.server', msg: 'req', method: 'GET', path: '/api/health', status: 200, ms: 3 },
    { ts: 1_790_000_002, level: 'WARNING', logger: 'sp.server', msg: 'req', method: 'GET', path: '/api/sessions/turns', status: 200, ms: 700, why: 'slow' },
    { ts: 1_790_000_003, level: 'INFO', logger: 'sp.db', msg: 'views rebuilt: projects=4', ms: 300 },
  ],
}

afterEach(() => { vi.restoreAllMocks() })

describe('ServerSection', () => {
  it('shows the numbers, the slow paths and the log, and copies the text', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.startsWith('/api/logs/text')) return new Response('# Slightly Parallel health\nplain', { status: 200 })
      if (url.startsWith('/api/logs')) return new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } })
      return new Response('{}', { status: 200 })
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchInterval: false } } })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><ServerSection /></MemoryRouter>
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getByText('well')).toBeTruthy())
    expect(screen.getByText('every file read')).toBeTruthy()
    expect(screen.getByText('GET /api/sessions/turns')).toBeTruthy()
    expect(screen.getByText(/GET \/api\/sessions\/turns → 200 in 700 ms/)).toBeTruthy()
    expect(screen.getByText(/views rebuilt: projects=4 \(300 ms\)/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /copy the whole page/i })).toBeTruthy()
  })
})
