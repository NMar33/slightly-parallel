import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, renderHook, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { ThinkBadge } from './parts'
import { TaskCard } from './board/Card'
import { EditorHeader } from './editor/Header'
import { useBoardColumns } from './board/useBoardColumns'
import type { TaskRow } from './model'

/**
 * The operator's «think» mark on the card, in the task window and as a
 * board filter. Only the operator removes it: the badge's ×.
 */

afterEach(() => { localStorage.clear(); vi.unstubAllGlobals() })

function wrap() {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })))
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

const marked = { id: 'tk_think01', title: 'Pricing model', status: 'todo', project: 'alpha',
  think_at: '2026-11-26T10:00:00', think_by: 'operator' } as TaskRow
const plain = { id: 'tk_plain01', title: 'Export bug', status: 'todo', project: 'alpha' } as TaskRow

describe('ThinkBadge', () => {
  it('says think, and its × clears without opening the card', () => {
    const onClear = vi.fn()
    const outer = vi.fn()
    render(<div onClick={outer}><ThinkBadge at="2026-11-26T10:00:00" onClear={onClear} /></div>)
    expect(screen.getByText('think')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Remove the think mark' }))
    expect(onClear).toHaveBeenCalledTimes(1)
    expect(outer).not.toHaveBeenCalled()
  })

  it('has no × when nothing can clear it', () => {
    render(<ThinkBadge at="2026-11-26T10:00:00" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('the card', () => {
  it('shows the badge on a marked task and the × calls onThinkOff with the task', () => {
    const onThinkOff = vi.fn()
    const onEdit = vi.fn()
    render(<TaskCard task={marked} onThinkOff={onThinkOff} onEdit={onEdit} />, { wrapper: wrap() })
    expect(screen.getByText('think')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Remove the think mark' }))
    expect(onThinkOff).toHaveBeenCalledWith(marked)
    expect(onEdit).not.toHaveBeenCalled()
  })

  it('shows nothing on a task without the mark', () => {
    render(<TaskCard task={plain} onThinkOff={vi.fn()} />, { wrapper: wrap() })
    expect(screen.queryByText('think')).toBeNull()
  })
})

describe('the task window', () => {
  const base = { isEdit: true, existingTask: marked, tuning: false, setTuning: vi.fn(), onClose: vi.fn() }

  it('shows the badge beside the id, and the × removes it', () => {
    const onThinkOff = vi.fn()
    render(<EditorHeader {...base} thinkAt={marked.think_at} onThinkOff={onThinkOff} />, { wrapper: wrap() })
    expect(screen.getByText('think')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Remove the think mark' }))
    expect(onThinkOff).toHaveBeenCalledTimes(1)
  })

  it('shows no badge once the mark is off', () => {
    render(<EditorHeader {...base} thinkAt="" onThinkOff={vi.fn()} />, { wrapper: wrap() })
    expect(screen.queryByText('think')).toBeNull()
  })
})

describe('the board filter', () => {
  it('keeps only the marked tasks when on', () => {
    const props = {
      boardKey: 'think', tasks: [marked, plain], todayTasks: [] as TaskRow[], today: '2026-11-26', statusSince: {},
      sprintFilter: null, onlyRemembered: false, onlyToday: false,
    }
    const wrapper = wrap()
    const all = renderHook(() => useBoardColumns(props), { wrapper })
    expect(Object.values(all.result.current.tasksByStatus).flat().map((t) => t.id).sort()).toEqual(['tk_plain01', 'tk_think01'])
    const only = renderHook(() => useBoardColumns({ ...props, onlyThink: true }), { wrapper })
    expect(Object.values(only.result.current.tasksByStatus).flat().map((t) => t.id)).toEqual(['tk_think01'])
  })
})
