import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

import { TaskAddModal } from './TaskEditor'
import type { TaskRow } from './model'

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

describe('TaskAddModal', () => {
  it('a description it could not read is not overwritten by the empty box', async () => {
    const posts: Array<{ url: string; body: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        return json(200, {})
      }
      if (url === '/api/tasks/tk_1') return json(500, { detail: 'the task file could not be read' })
      return json(200, {})
    }))
    const task = { id: 'tk_1', title: 'Keep me', status: 'todo', project: 'p' } as TaskRow
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <TaskAddModal projectCode="p" initialStatus="todo" existingTask={task} onClose={() => {}} onSaved={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('The description could not be read. Saving keeps it as it is.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(posts.some((p) => p.url === '/api/tasks/tk_1/update')).toBe(true))
    const update = posts.find((p) => p.url === '/api/tasks/tk_1/update')!
    expect(update.body.title).toBe('Keep me')
    expect('description' in update.body).toBe(false)
    expect('turn' in update.body).toBe(false)
  })
})
