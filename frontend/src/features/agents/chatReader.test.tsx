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

describe('ChatReader, usage on a turn', () => {
  const usage = { new: 1874, output: 512, cache: 108_233, cache_write: 0, thinking: 0, model: 'claude-opus-4-5', messages: 1 }
  const serveTurns = () => vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, status: 200,
    json: async () => ({ turns: { ses_u: [
      { n: 1, at: '09:00', user: 'question 1', agent: 'answer', usage },
      { n: 2, at: '09:05', user: 'question 2', agent: 'answer' },
    ] } }),
  })))
  const mount = (reading?: { size: number; md: boolean; reverse: boolean; work: boolean; usage?: boolean }) => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={qc}><MemoryRouter>
        <ChatReader sessions={[session('ses_u', 2)]} onOpenLens={() => {}} reading={reading} />
      </MemoryRouter></QueryClientProvider>,
    )
  }
  afterEach(() => localStorage.clear())

  it('shows the line on a turn that has usage, and nothing on one that has not', async () => {
    serveTurns()
    mount()
    await screen.findByText('question 1')
    const lines = screen.getAllByTestId('usage-line')
    expect(lines).toHaveLength(1)
    expect(lines[0]!.textContent).toMatch(/^→ 1\.9k ↑ 512 ↓ \(108k\)New 1,874/)
  })

  it('U hides and shows the line, and the chats page\'s saved prefs follow', async () => {
    serveTurns()
    localStorage.setItem('sp-chats', JSON.stringify({ usage: true }))
    mount()
    await screen.findByText('question 1')
    await act(async () => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'u' })) })
    expect(screen.queryByTestId('usage-line')).toBeNull()
    expect(JSON.parse(localStorage.getItem('sp-chats')!).usage).toBe(false)
    await act(async () => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'u' })) })
    expect(screen.getAllByTestId('usage-line')).toHaveLength(1)
  })

  it('builds a line the answer lacks with the turn before it, so a crossed ten of the 5-hour limit shows', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, status: 200,
      json: async () => ({ turns: { ses_lim: [
        { n: 1, at: '09:00', user: 'question 1', agent: 'answer', usage: { ...usage, limit: { five_hour: 69.9 } } },
        { n: 2, at: '09:05', user: 'question 2', agent: 'answer', usage: { ...usage, limit: { five_hour: 70.0 } } },
      ] } }),
    })))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}><MemoryRouter>
        <ChatReader sessions={[session('ses_lim', 2)]} onOpenLens={() => {}} />
      </MemoryRouter></QueryClientProvider>,
    )
    await screen.findByText('question 2')
    const lines = screen.getAllByTestId('usage-line').map((el) => {
      const c = el.cloneNode(true) as HTMLElement
      c.querySelectorAll('.sr-only').forEach((x) => x.remove())
      return c.textContent
    })
    expect(lines).toEqual(['→ 1.9k ↑ 512 ↓ (108k)', '→ 1.9k ↑ 512 ↓ (108k) · 5-hour 70%'])
  })

  it('follows a change made elsewhere on the page', async () => {
    serveTurns()
    mount()
    await screen.findByText('question 1')
    await act(async () => { window.dispatchEvent(new CustomEvent('sp:pref', { detail: { key: 'sp-chat-usage', value: 'off' } })) })
    expect(screen.queryByTestId('usage-line')).toBeNull()
  })

  it('hides it with the reader\'s own switch on the agent page', async () => {
    serveTurns()
    mount()
    await screen.findByText('question 1')
    await act(async () => { screen.getByRole('switch', { name: 'Show the tokens of each reply' }).click() })
    expect(screen.queryByTestId('usage-line')).toBeNull()
    expect(localStorage.getItem('sp-chat-usage')).toBe('off')
  })

  it('follows the host\'s pref when it hands one down, with no switch of its own', async () => {
    serveTurns()
    mount({ size: 12, md: true, reverse: false, work: true, usage: false })
    await screen.findByText('question 1')
    expect(screen.queryByTestId('usage-line')).toBeNull()
    expect(screen.queryByRole('switch', { name: 'Show the tokens of each reply' })).toBeNull()
  })
})
