import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const { copied } = vi.hoisted(() => ({ copied: vi.fn(async () => true) }))
vi.mock('../../lib/useCopy', async (orig) => ({ ...(await orig<object>()), copyText: copied }))

import { PromptsTable } from './Table'

const prompt = {
  id: 'pm_1', created_date: '2609-28', created_time: '10:05', project: 'p', agent_id: 'cc-a', title: 'plan before code',
  tags: '', status: 'active', source: 'captured', versions_n: 1, marks: {}, preview: 'Before writing code: say what you will change.',
  chars: 46, words: 8, current_rating: null, current_version: 1, made: { commits: 1, files: 1, add: 1, del: 0, tasks: 0 },
  metrics: { uses: 2, reuses: 1, first_used: '2026-09-28T10:05:00', sessions: 2, turns: 4, minutes: 10, projects: ['p'], tasks: [], last_used: '2026-09-29T10:05:00', by_version: { 1: 1 }, by_day: { '2609-28': 1 } },
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); copied.mockClear(); window.location.hash = '' })

describe('PromptsTable keys', () => {
  it('c copies the open prompt, but Ctrl+C is left to the browser', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = url.includes('candidates') ? { candidates: [], min_sends: 2 }
        : url.startsWith('/api/prompt-library') ? { prompts: [prompt], adopted: [], counts: {}, mark_names: [] } : {}
      return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) }
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><PromptsTable /></MemoryRouter></QueryClientProvider>)
    expect((await screen.findAllByText('plan before code')).length).toBeGreaterThan(0)
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true })
    fireEvent.keyDown(window, { key: 'c', metaKey: true })
    expect(copied).not.toHaveBeenCalled()
    fireEvent.keyDown(window, { key: 'c' })
    expect(copied).toHaveBeenCalledWith(prompt.preview)
  })

  it('Enter on a focused link or button is left to that control', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = url.includes('candidates') ? { candidates: [], min_sends: 2 }
        : url.startsWith('/api/prompt-library') ? { prompts: [prompt], adopted: [], counts: {}, mark_names: [] } : {}
      return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) }
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><MemoryRouter><button type="button">elsewhere</button><a href="#x">a link</a><PromptsTable /></MemoryRouter></QueryClientProvider>)
    expect((await screen.findAllByText('plan before code')).length).toBeGreaterThan(0)
    const press = (target: EventTarget) => {
      const e = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
      target.dispatchEvent(e)
      return e.defaultPrevented
    }
    expect(press(screen.getByText('elsewhere'))).toBe(false)
    expect(press(screen.getByText('a link'))).toBe(false)
    expect(press(document.body)).toBe(true)
  })
})
