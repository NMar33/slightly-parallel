import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { OverviewData } from './data'
import { NeedsYou } from './home'

const data = (review: Array<Record<string, unknown>>) =>
  ({ problems: [], review, snapshot: undefined, days: [], latestStandup: new Map() }) as unknown as OverviewData

afterEach(() => { vi.unstubAllGlobals() })

describe('NeedsYou', () => {
  it('asks again for the lens lists only, and shows a task sent back to review after it was accepted', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })))
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const row = { id: 'tk_1', title: 'Ship the thing', project: 'p' }
    const view = (rows: Array<Record<string, unknown>>) => (
      <QueryClientProvider client={qc}><MemoryRouter><NeedsYou data={data(rows)} /></MemoryRouter></QueryClientProvider>
    )
    const { rerender } = render(view([row]))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Accept' })) })
    expect(screen.queryByText('Ship the thing')).toBeNull()
    expect(spy.mock.calls.map((c) => c[0])).toEqual([{ queryKey: ['lens'] }])
    // The server's list drops it, then, days later, it comes back to review.
    rerender(view([]))
    rerender(view([row]))
    expect(screen.getByText('Ship the thing')).toBeInTheDocument()
  })
})
