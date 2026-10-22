import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { LensDrawer } from './LensDrawer'
import { LENSES } from './config'

function mount(detail: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }), json: async () => detail, text: async () => JSON.stringify(detail),
  })))
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <LensDrawer lens={LENSES.decisions} id="dc_1" presentation="embedded" onClose={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('LensDrawer', () => {
  it('labels an entry by what it holds', async () => {
    mount({
      metadata: { id: 'dc_1', decision_text: 'Chose Redis', created_date: '2609-20' },
      l2: 'Workers share counters.', l3: ['LRU — rejected: undercounts'], l4: 'user: two workers',
      text: { decision: 'Chose Redis', why: 'Workers share counters.', alternatives: ['LRU — rejected: undercounts'], excerpt: 'user: two workers' },
    })
    expect(await screen.findByText('Why')).toBeInTheDocument()
    expect(screen.getByText('Alternatives')).toBeInTheDocument()
    expect(screen.getByText('Excerpt')).toBeInTheDocument()
    expect(screen.queryByText('Summary')).not.toBeInTheDocument()
    expect(screen.queryByText('Raw')).not.toBeInTheDocument()
  })

  it('still reads an answer that has only the slots', async () => {
    mount({ metadata: { id: 'dc_1', decision_text: 'Older' }, l2: 'a paragraph', l3: [], l4: '' })
    expect(await screen.findByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('a paragraph')).toBeInTheDocument()
  })

  it('keeps focus where it is when the host re-renders with a new onClose', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ metadata: { id: 'dc_1', decision_text: 'x' }, l2: '', l3: [], l4: '' }), text: async () => '',
    })))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const closed = vi.fn()
    const tree = (onClose: () => void) => (
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <button type="button">outside</button>
          <LensDrawer lens={LENSES.decisions} id="dc_1" onClose={onClose} />
        </MemoryRouter>
      </QueryClientProvider>
    )
    const { rerender } = render(tree(() => closed('first')))
    const outside = screen.getByText('outside')
    outside.focus()
    rerender(tree(() => closed('second')))
    expect(document.activeElement).toBe(outside)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(closed).toHaveBeenCalledWith('second')
  })
})
