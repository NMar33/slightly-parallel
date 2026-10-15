/**
 * Backups page — the ladder shows its gaps, and restore costs a typed name.
 *
 * Both are the point of the page rather than decoration: a backup list that
 * only shows what exists cannot show what is missing, and the one control
 * here that destroys data must not be reachable by a mis-click on a column
 * of similar-looking dates.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import BackupsPage from './BackupsPage'

const said = vi.hoisted(() => Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }))
vi.mock('sonner', () => ({ toast: said }))

const DAY = 86_400_000

function archive(name: string, agoDays: number, extra: Record<string, unknown> = {}) {
  return {
    name,
    at: new Date(Date.now() - agoDays * DAY).toISOString(),
    kind: 'auto',
    bytes: 26_214_400,
    label: '',
    files: 736,
    sha256: 'abc123',
    pinned: false,
    reasons: [],
    ...extra,
  }
}

const STATE = {
  data_root: '/data/00-agents',
  backup_root: '/data/00-agents-backups',
  enabled: true,
  every_hours: 6,
  keep: { horizon_days: 90, manual: 10 },
  excluded: ['*.lock'],
  rungs: [
    { name: 'a day', days: 1 },
    { name: '3 days', days: 3 },
    { name: 'a week', days: 7 },
    { name: '2 weeks', days: 14 },
    { name: 'a month', days: 30 },
    { name: '3 months', days: 90 },
  ],
  source: { files: 736, bytes: 32_505_856, mtime: 1 },
  due: false,
  due_reason: 'next in 210 min',
  archives: [
    archive('2609-07-151833__auto', 0, { reasons: ['newest', 'a day'] }),
    archive('2609-05-120000__auto', 2, { reasons: ['3 days'] }),
    archive('2608-30-120000__manual', 8, {
      kind: 'manual',
      reasons: ['manual'],
      label: 'before the migration',
    }),
  ],
  expiring: [],
  total_bytes: 78_643_200,
  count: 3,
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <BackupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BackupsPage', () => {
  let posted: Array<{ url: string; body: unknown }>

  beforeEach(() => {
    posted = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST') {
          posted.push({ url, body: JSON.parse(String(init.body)) })
          return Response.json({
            restored: { files: 736 },
            safety: { name: '2609-07-152000__manual' },
            state: STATE,
          })
        }
        return Response.json(STATE)
      }),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('names every rung, and says which ones nothing has reached yet', async () => {
    renderPage()
    await screen.findByRole('group', { name: '2609-07-151833__auto' })

    // All six ages the operator asked for are listed, filled or not.
    for (const rung of ['a day', '3 days', 'a week', '2 weeks', 'a month', '3 months']) {
      expect(screen.getAllByText(rung).length).toBeGreaterThan(0)
    }
    // Two rungs are filled; the other four must say so out loud. The manual
    // archive fills none of them — a bookmark is not a restore point at an age.
    expect(screen.getAllByText('no backup this old yet')).toHaveLength(4)
  })

  it('restore needs the archive name typed, not just a click', async () => {
    renderPage()
    const row = await screen.findByRole('group', { name: '2609-07-151833__auto' })

    fireEvent.click(within(row).getByRole('button', { name: /Restore$/ }))
    const confirm = await screen.findByRole('button', { name: /Restore this backup/ })
    expect(confirm).toBeDisabled()

    const field = screen.getByLabelText('Type the backup name to confirm')
    fireEvent.change(field, { target: { value: '2609-07-151833__aut' } })
    expect(confirm).toBeDisabled()

    fireEvent.change(field, { target: { value: '2609-07-151833__auto' } })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)

    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0].url).toBe('/api/backup/2609-07-151833__auto/restore')
    expect(posted[0].body).toEqual({ confirm: '2609-07-151833__auto' })
  })

  it('a pinned backup cannot be deleted by accident', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          ...STATE,
          archives: [archive('2609-07-151833__manual', 0, {
            kind: 'manual', pinned: true, reasons: ['pinned'],
          })],
        }),
      ),
    )
    renderPage()
    const row = await screen.findByRole('group', { name: '2609-07-151833__manual' })
    expect(within(row).getByRole('button', { name: /Delete/ })).toBeDisabled()
    expect(within(row).getByRole('button', { name: /Unpin/ })).toBeEnabled()
  })

  it('says the path was copied only when the browser allowed it', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => init?.method === 'POST'
      ? Response.json({ opened: false, path: '/data/00-agents-backups', detail: 'No file manager here' })
      : Response.json(STATE)))
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn(async () => { throw new Error('denied') }) } })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Show in folder/ }))
    await waitFor(() => expect(said).toHaveBeenCalled())
    expect(said.mock.calls[0]![0]).toBe('No file manager here.')
  })
})
