import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

import type { TaskRow } from '../../project/kanban/model'
import { InspectorTasks } from './InspectorTasks'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear() })

it('moves only the chosen board field and adds the latest task round to the draft', async () => {
  const task: TaskRow = { id: 'tk_one', title: 'First card', status: 'todo', assignee: 'Old lane' }
  const posts: unknown[] = []
  const onAppend = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(false)
  localStorage.setItem('sp-lanes:sample', JSON.stringify(['New lane']))
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/tasks/tk_one/update' && init?.method === 'POST') {
      const patch = JSON.parse(String(init.body))
      posts.push(patch)
      Object.assign(task, patch)
      return Response.json({})
    }
    if (url === '/api/tasks/tk_one') {
      return Response.json({ metadata: task, turns: [
        { n: 1, text: 'Original instructions' },
        { n: 2, text: 'Current instructions' },
      ] })
    }
    return Response.json(url.startsWith('/api/tasks?') ? { tasks: [task] } : {})
  }))

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}>
    <InspectorTasks project="sample" agent="" onAppend={onAppend} />
  </QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: /^First card/ }))
  expect(await screen.findByText('Original instructions')).toBeInTheDocument()
  expect(screen.getByText('Current instructions')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('combobox', { name: 'Lane' }), { target: { value: 'New lane' } })
  await waitFor(() => {
    expect(screen.getByRole('combobox', { name: 'Lane' })).toHaveValue('New lane')
    expect(screen.getByRole('combobox', { name: 'Column' })).toBeEnabled()
  })
  expect(posts).toEqual([{ actor: 'operator', assignee: 'New lane', lane: 'New lane' }])
  fireEvent.change(screen.getByRole('combobox', { name: 'Column' }), { target: { value: 'done' } })
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Column' })).toHaveValue('done'))
  expect(posts.at(-1)).toEqual({ actor: 'operator', status: 'done' })

  const append = screen.getByRole('button', { name: 'Add to draft' })
  fireEvent.click(append)
  await waitFor(() => {
    expect(onAppend).toHaveBeenCalledWith('tk_one.2 · First card\nCurrent instructions')
    expect(append).toBeEnabled()
  })
  fireEvent.click(append)
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not add to draft.')
})

it('sorts project tasks by their last mention and can limit the list to the active chat', async () => {
  const older = { id: 'tk_old', title: 'Older card', created_date: '2611-13', status: 'done' }
  const newer = { id: 'tk_new', title: 'Newer card', created_date: '2611-19', status: 'todo' }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.startsWith('/api/tasks/mentions/summary?')) {
      return Response.json({ mentions: { [older.id]: { last_at: '2026-11-19T00:00:00' } } })
    }
    if (url.startsWith('/api/tasks/mentions/by-agent?')) {
      return Response.json({ agents: { one: [{ task_id: newer.id, at: '2026-11-19T01:00:00' }] } })
    }
    return Response.json(url.startsWith('/api/tasks?') ? { tasks: [older, newer] } : {})
  }))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={queryClient}>
    <InspectorTasks project="sample" agent="one" onAppend={() => {}} />
  </QueryClientProvider>)
  await screen.findByRole('button', { name: /^Older card/ })
  expect(screen.getAllByRole('button')[0]).toHaveTextContent('Newer card')
  fireEvent.change(screen.getByRole('combobox', { name: 'Sort tasks' }), { target: { value: 'mentioned' } })
  await waitFor(() => expect(screen.getAllByRole('button')[0]).toHaveTextContent('Older card'))
  fireEvent.change(screen.getByRole('combobox', { name: 'Task scope' }), { target: { value: 'chat' } })
  await screen.findByRole('button', { name: /^Newer card/ })
  expect(screen.queryByRole('button', { name: /^Older card/ })).toBeNull()
})
