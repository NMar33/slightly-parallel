import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'

import { MonthFeed } from './MonthFeed'
import { monthKey, monthLabel } from './data'

// Every month answers at once, with no work in it.
vi.mock('../../lib/getJson', () => ({
  getJson: vi.fn(async (url: string) => {
    const u = new URL(url, 'http://x')
    return { project: u.searchParams.get('project'), month: u.searchParams.get('month'), days: {} }
  }),
}))

// The sentinel is always in view: the feed grows as far as it may.
class SeenObserver {
  constructor(private cb: IntersectionObserverCallback) {}
  observe() { this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver) }
  disconnect() {}
  unobserve() {}
  takeRecords() { return [] }
}

describe('the day book feed', () => {
  beforeEach(() => {
    ;(globalThis as { IntersectionObserver: unknown }).IntersectionObserver = SeenObserver
  })

  it('goes on loading older months after a switch back to a project already in the cache', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const older = monthKey(new Date(), -1)
    const feed = (project: string) => (
      <QueryClientProvider client={qc}>
        <MonthFeed project={project} earliest={older} anchor={monthKey()} active=""
          keep={() => false} renderDay={() => null} />
      </QueryClientProvider>
    )
    const { rerender } = render(feed('alpha'))
    expect(await screen.findByText(/Nothing older/)).toBeInTheDocument()
    rerender(feed('beta'))
    expect(await screen.findByText(/Nothing older/)).toBeInTheDocument()
    // Back to the first project: its months answer from the cache.
    rerender(feed('alpha'))
    expect(await screen.findByText(/Nothing older/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: monthLabel(older) })).toBeInTheDocument()
  })
})
