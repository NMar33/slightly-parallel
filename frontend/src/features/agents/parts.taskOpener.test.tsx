import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'

const errors = vi.hoisted(() => vi.fn())
vi.mock('sonner', async (orig) => ({ ...(await orig<typeof import('sonner')>()), toast: Object.assign(vi.fn(), { error: errors, success: vi.fn() }) }))
// The editor itself is not under test: a stand-in names the task it opened.
vi.mock('../project/kanban/TaskWindow', () => ({
  TaskAddModal: ({ existingTask }: { existingTask: { id: string } }) => <div>editing {existingTask.id}</div>,
}))

import { useTaskOpener } from './parts'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); errors.mockReset() })

function Host({ ids }: { ids: string[] }) {
  const { open, modal } = useTaskOpener('p')
  return <>{ids.map((id) => <button key={id} type="button" onClick={() => open(id)}>{id}</button>)}{modal}</>
}

const answer = (status: number, body: unknown) => ({
  ok: status < 400, status, json: async () => body, text: async () => JSON.stringify(body),
})

describe('useTaskOpener', () => {
  it('says so when the task cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => answer(500, { detail: 'the store is locked' })))
    render(<Host ids={['tk_a']} />)
    await act(async () => { screen.getByText('tk_a').click() })
    expect(errors).toHaveBeenCalledWith('the store is locked')
  })

  it('opens the task clicked last, whichever answers first', async () => {
    const later: Array<() => void> = []
    vi.stubGlobal('fetch', vi.fn((url: string) => new Promise((resolve) => {
      const id = url.split('/').pop()!
      const reply = () => resolve(answer(200, { metadata: { id, title: id, status: 'todo' } }))
      if (id === 'tk_a') later.push(reply); else reply()
    })))
    render(<Host ids={['tk_a', 'tk_b']} />)
    await act(async () => { screen.getByText('tk_a').click(); screen.getByText('tk_b').click() })
    expect(await screen.findByText('editing tk_b')).toBeInTheDocument()
    await act(async () => { later.forEach((f) => f()) })
    expect(screen.getByText('editing tk_b')).toBeInTheDocument()
    expect(screen.queryByText('editing tk_a')).not.toBeInTheDocument()
  })
})
