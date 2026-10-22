import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { ChatReader } from './chatReader'
import type { ProfileSession } from './profile'

beforeAll(() => {
  // jsdom has neither: the reader only needs them to exist.
  vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} unobserve() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.scrollTo = () => {}
})
afterEach(cleanup)

const session = (id: string, turns_n: number): ProfileSession => ({
  id, created_date: '2610-01', start_time: '09:00', end_time: '10:00', duration_min: 60, turns_n, l1: id,
})
const turns = (n: number) => Array.from({ length: n }, (_, i) => ({ n: i + 1, at: '09:00', user: `question ${i + 1}`, agent: 'answer' }))

describe('ChatReader, the whole history', () => {
  it('the newer-chat arrow reaches a chat that sits past the turns drawn so far', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, status: 200, json: async () => ({ turns: { ses_long: turns(200), ses_next: turns(2) } }),
    })))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}><MemoryRouter>
        <ChatReader sessions={[session('ses_long', 200), session('ses_next', 2)]} onOpenLens={() => {}} />
      </MemoryRouter></QueryClientProvider>,
    )
    await screen.findByText('question 1')
    expect(document.querySelector('[data-session="ses_next"]')).toBeNull()
    await act(async () => { screen.getByRole('button', { name: 'Newer chat' }).click() })
    expect(document.querySelector('[data-session="ses_next"]')).not.toBeNull()
  })
})
