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
    expect('title' in update.body).toBe(false)              // unchanged: not sent
    expect('description' in update.body).toBe(false)
    expect('turn' in update.body).toBe(false)
  })
})

describe('what a save sends', () => {
  function open(task: TaskRow, turns: Array<{ n: number; text: string; date?: string; time?: string }>) {
    const posts: Array<{ url: string; body: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        return json(200, {})
      }
      if (url === `/api/tasks/${task.id}`) return json(200, { metadata: task, turns, description: turns.at(-1)?.text ?? '' })
      return json(200, {})
    }))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <TaskAddModal projectCode="p" initialStatus="todo" existingTask={task} onClose={() => {}} onSaved={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    return posts
  }

  it('only the fields that changed, and not the text when it is as it was read', async () => {
    // Before: every field went with every save. `status` among them, which the
    // server reads as the operator's verdict (the agent's report was cleared),
    // and the whole text, logged as an edit each time.
    const task = { id: 'tk_2', title: 'Fix the login', status: 'review', project: 'p', priority: 'med',
                   agent_done_by: 'cc-x', tags: 'ag_bug' } as unknown as TaskRow
    const posts = open(task, [{ n: 1, text: 'the long text' }])
    const title = await screen.findByDisplayValue('Fix the login')
    await waitFor(() => expect(screen.getByDisplayValue('the long text')).toBeInTheDocument())
    fireEvent.change(title, { target: { value: 'Fix the login page' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(posts.some((p) => p.url === '/api/tasks/tk_2/update')).toBe(true))
    const body = posts.find((p) => p.url === '/api/tasks/tk_2/update')!.body
    expect(body).toEqual({ title: 'Fix the login page', actor: 'operator' })
  })

  it('the text, when it changed', async () => {
    const task = { id: 'tk_3', title: 'Keep', status: 'todo', project: 'p' } as unknown as TaskRow
    const posts = open(task, [{ n: 1, text: 'one' }])
    const box = await screen.findByDisplayValue('one')
    fireEvent.change(box, { target: { value: 'one, then two' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save/ }))
    await waitFor(() => expect(posts.some((p) => p.url === '/api/tasks/tk_3/update')).toBe(true))
    const body = posts.find((p) => p.url === '/api/tasks/tk_3/update')!.body
    expect(body.description).toBe('one, then two')
    expect('status' in body).toBe(false)
  })

  it('a task with no priority shows none and keeps none', async () => {
    const task = { id: 'tk_4', title: 'Plain', status: 'todo', project: 'p', priority: '' } as unknown as TaskRow
    open(task, [])
    const select = await screen.findByLabelText('Priority') as HTMLSelectElement
    expect(select.value).toBe('')
  })
})
