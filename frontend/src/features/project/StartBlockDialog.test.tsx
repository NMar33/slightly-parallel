import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { EditBlockDialog } from './StartBlockDialog'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const sprint = { id: 'sp_1', name: 'Payments', bet_days: 7, budget_h: 10, tasks_total: 2 }

function mount(detail: () => Promise<unknown>) {
  const posted: Array<{ url: string; body: unknown }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      posted.push({ url, body: JSON.parse(String(init.body)) })
      return { ok: true, status: 200, json: async () => ({}) }
    }
    const body = await detail()
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) }
  }))
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={qc}><EditBlockDialog sprint={sprint} onClose={() => {}} onSaved={() => {}} /></QueryClientProvider>)
  return posted
}

describe('EditBlockDialog', () => {
  it('does not save before the goals and notes are read, which would erase them', () => {
    mount(() => new Promise(() => {}))
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('saves the goals it read back with the change', async () => {
    const posted = mount(async () => ({ l2: 'the bet', l3: ['ship refunds'], l4: 'notes' }))
    const save = screen.getByRole('button', { name: 'Save' })
    await waitFor(() => expect(save).toBeEnabled())
    fireEvent.click(save)
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]!.body).toMatchObject({ l2: 'the bet', l3: ['ship refunds'], l4: 'notes' })
  })
})
