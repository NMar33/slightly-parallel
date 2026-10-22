import { describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { SearchAnswer } from './api'

/** One held answer per search: settled by the test, refused when its signal is aborted. */
const asked: Array<{ q: string; answer: (a: SearchAnswer) => void; refuse: (e: Error) => void }> = []
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  fetchEverything: (q: string, signal: AbortSignal) => new Promise<SearchAnswer>((resolve, reject) => {
    asked.push({ q, answer: resolve, refuse: reject })
    signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
  }),
}))
vi.mock('./stats/Numbers', () => ({ Numbers: () => null }))

import { SearchPage } from './SearchPage'

let go: (to: string) => void = () => {}
function Go() {
  go = useNavigate()
  return null
}

describe('the search page between two words', () => {
  it('keeps saying "searching…" for the second word after the first is dropped', async () => {
    // The page's guide reads the query client (its "remove the examples" button).
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={['/search?q=one']}><Go /><SearchPage /></MemoryRouter></QueryClientProvider>)
    expect(screen.getByText('searching…')).toBeInTheDocument()

    // The second word aborts the first; the first's ending must not end the second's.
    await act(async () => { go('/search?q=two') })
    await act(async () => { await Promise.resolve() })
    expect(asked.map((a) => a.q)).toEqual(['one', 'two'])
    expect(screen.getByText('searching…')).toBeInTheDocument()

    await act(async () => { asked[1]!.answer({ query: 'two', hits: [], counts: {}, total: 0 }) })
    // The answer reaches the page through the query cache, a tick later.
    await waitFor(() => expect(screen.queryByText('searching…')).toBeNull())
  })

  it("does not show the last word's rows under a word whose search failed", async () => {
    asked.length = 0
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={['/search?q=alpha']}><Go /><SearchPage /></MemoryRouter></QueryClientProvider>)
    await act(async () => {
      asked[0]!.answer({ query: 'alpha', total: 1, counts: { task: 1 }, hits: [
        { kind: 'task', id: 'tk_1', title: 'Refund flow for alpha', project: 'p', date: '2610-01', snippet: 'alpha', where: 'title' },
      ] })
    })
    expect(await screen.findAllByText(/Refund flow for/)).not.toHaveLength(0)
    await act(async () => { go('/search?q=beta') })
    await act(async () => { await Promise.resolve() })
    await act(async () => { asked[asked.length - 1]!.refuse(new Error('down')) })
    expect(await screen.findByText('The search failed. Try again.')).toBeInTheDocument()
    expect(screen.queryByText(/Refund flow for/)).toBeNull()
  })

  it('leaves keys typed into another field (the topbar search, the Quick note) alone', async () => {
    asked.length = 0
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={['/search?q=gamma']}><Go /><textarea aria-label="Quick note" /><SearchPage /></MemoryRouter></QueryClientProvider>)
    await act(async () => {
      asked[0]!.answer({ query: 'gamma', total: 1, counts: { task: 1 }, hits: [
        { kind: 'task', id: 'tk_2', title: 'Release notes for gamma', project: 'p', date: '2610-01', snippet: 'gamma', where: 'title' },
      ] })
    })
    expect(await screen.findAllByText(/Release notes for/)).not.toHaveLength(0)
    const press = (target: EventTarget, key: string) => {
      const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
      target.dispatchEvent(e)
      return e.defaultPrevented
    }
    const note = screen.getByLabelText('Quick note')
    note.focus()
    for (const key of ['1', 'Backspace', 'ArrowDown']) expect(press(note, key)).toBe(false)
    expect(document.activeElement).toBe(note)
    // Outside any field the page still owns its keys.
    note.blur()
    expect(press(document.body, '1')).toBe(true)
  })
})
