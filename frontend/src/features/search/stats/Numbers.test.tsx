import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { Numbers } from './Numbers'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const overview = { rows: 1234, kinds: [['turn', 1000]], days: [['2026-10-01', 3]], projects: [], turn_lengths: [], words_said: 10, chats: [], roles: [], words: [] }

function mount(query: string) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('?q=')) return { ok: false, status: 500, text: async (): Promise<string> => '{"detail":"index busy"}' }
    return { ok: true, status: 200, json: async () => overview, text: async (): Promise<string> => JSON.stringify(overview) }
  }))
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={qc}><MemoryRouter><Numbers query={query} /></MemoryRouter></QueryClientProvider>)
}

describe('Numbers', () => {
  it('shows the whole index with no word', async () => {
    mount('')
    expect(await screen.findByText('1,234')).toBeInTheDocument()
  })

  it("says a word's numbers failed instead of showing the whole index under the word", async () => {
    mount('refund')
    expect(await screen.findByText('The numbers for “refund” could not be read.')).toBeInTheDocument()
    expect(screen.queryByText('1,234')).not.toBeInTheDocument()
  })
})
