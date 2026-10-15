import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

import { StandupFocus } from './Focus'

/** Three standups of one project, covering 5, 6 and 7 October, and one of another project. */
const ROWS = [
  { id: 'st_7', created_date: '2610-08', created_time: '10:00', project: 'p', agent_id: 'a1', l1: 'Seventh: scans cover their own chat', for_date: '2610-07' },
  { id: 'st_6', created_date: '2610-07', created_time: '10:00', project: 'p', agent_id: 'a1', l1: 'Sixth: the rename', for_date: '2610-06' },
  { id: 'st_5', created_date: '2610-06', created_time: '10:00', project: 'p', agent_id: 'a1', l1: 'Fifth: an audit', for_date: '2610-05' },
  { id: 'st_x', created_date: '2610-08', created_time: '10:00', project: 'q', agent_id: 'a2', l1: 'Another project', for_date: '2610-07' },
]

const DOCS: Record<string, unknown> = {
  st_7: { text: {
    summary: 'Seventh: scans cover their own chat',
    story: 'A scan now covers only its own chat.',
    deviation: '- The evening scan counted other chats.\n- The wordmark was dark on dark.',
    movement: ['New: a Russian interface (tk_7c30e989)', 'Fixed: the wordmark'],
    decisions: ['Keep the sections · operator, 12:02'],
    forgotten: [],
    detail: '**Needs an answer:** install Codex, or release as tested on Claude Code only.\n**Next:** the map.',
  } },
  st_6: { text: { summary: 'Sixth: the rename', story: '', deviation: '', movement: ['Changed: the name'], decisions: [], forgotten: [], detail: '' } },
  st_5: { text: { summary: 'Fifth: an audit', story: '', deviation: '', movement: [], decisions: [], forgotten: [], detail: '' } },
}

const day = (messages: number, commits: number) => ({
  messages_n: messages, chats_n: 1, agents: [], session_minutes: 0, tasks_created_n: 0, tasks_done_n: 0, tasks_moved_n: 0,
  commits_n: commits, files_n: 0, lines_add: 0, lines_del: 0, tracked_minutes: 0, decisions_n: 0, standup_id: '',
})

vi.mock('../../../lib/getJson', () => ({
  getJson: vi.fn(async (url: string) => {
    const u = new URL(url, 'http://x')
    if (u.pathname === '/api/standups') return { standups: ROWS }
    if (u.pathname === '/api/standups/calendar') return { project: 'p', month: '2026-10', days: { '2610-07': day(47, 20), '2610-06': day(37, 31), '2610-05': day(3, 11) } }
    if (u.pathname === '/api/standups/day') {
      return u.searchParams.get('date') === '2610-07'
        ? { tasks: [{ id: 'tk_7c30e989', title: 'Russian interface', status: 'review', moves: [], agents: [] }], agents: [], created: [] }
        : { tasks: [], agents: [], created: [] }
    }
    const id = u.pathname.split('/').pop() ?? ''
    return DOCS[id] ?? {}
  }),
}))

vi.mock('../../../lib/api', async (orig) => {
  const real = await orig<typeof import('../../../lib/api')>()
  return { ...real, api: { ...real.api, snapshot: async () => ({ agents: [] }) } }
})

function open(props: Partial<React.ComponentProps<typeof StandupFocus>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onPick = vi.fn(), onClose = vi.fn(), onOpenTask = vi.fn()
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <StandupFocus project="p" day="2610-07" onPick={onPick} onClose={onClose} onOpenTask={onOpenTask} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { onPick, onClose, onOpenTask }
}

const counter = () => screen.getByText(/^day \d+ of \d+/)

describe('standup focus', () => {
  beforeEach(() => { localStorage.clear() })

  it('opens full screen on the day, with the project\'s days listed newest first', async () => {
    open()
    const dialog = await screen.findByRole('dialog', { name: /^Focus: 7 October · Seventh/ })
    const list = within(dialog).getByRole('list', { name: 'Days with a standup' })
    const items = await within(list).findAllByRole('button')
    expect(items.map((b) => b.textContent)).toEqual([
      expect.stringContaining('Seventh'), expect.stringContaining('Sixth'), expect.stringContaining('Fifth'),
    ])
    expect(items[0]).toHaveAttribute('aria-current', 'true')
    await waitFor(() => expect(items[0]).toHaveTextContent('47 msg · 20 commits'))
    expect(within(dialog).queryByText('Another project')).toBeNull()
    expect(counter()).toHaveTextContent('day 1 of 3')
  })

  it('reads the day as sections: what needs an answer, what went wrong, what moved with its kinds, decisions, tasks', async () => {
    const { onOpenTask } = open()
    expect(await screen.findByText(/install Codex, or release/)).toBeInTheDocument()
    expect(screen.getByText(/Needs your answer · 1/)).toBeInTheDocument()
    expect(screen.getByText(/What went wrong · 2/)).toBeInTheDocument()
    expect(screen.getByText('The wordmark was dark on dark.')).toBeInTheDocument()
    expect(screen.getByText(/What moved · 2/)).toBeInTheDocument()
    expect(screen.getByText('New')).toBeInTheDocument()
    expect(screen.getByText('Fixed')).toBeInTheDocument()
    expect(screen.getByText('operator, 12:02')).toBeInTheDocument()
    expect(await screen.findByText(/Tasks of the day · 1/)).toBeInTheDocument()
    // "More" keeps the rest of the detail, without the question.
    expect(screen.getByText(/the map\./)).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'tk_7c30e989' })[0]!)
    expect(onOpenTask).toHaveBeenCalledWith('tk_7c30e989')
  })

  it('walks the sections with j and k', async () => {
    open()
    await screen.findByText(/Tasks of the day · 1/)
    await waitFor(() => expect(counter()).toHaveTextContent(/section 1 of 7/))
    fireEvent.keyDown(window, { key: 'j' })
    expect(counter()).toHaveTextContent('section 2 of 7')
    fireEvent.keyDown(window, { key: 'j' })
    fireEvent.keyDown(window, { key: 'k' })
    expect(counter()).toHaveTextContent('section 2 of 7')
  })

  it('moves between days with [ and ], or a click in the list; Esc leaves on the day', async () => {
    const { onPick, onClose } = open({ day: '2610-06' })
    await screen.findByRole('dialog', { name: /Sixth/ })
    fireEvent.keyDown(window, { key: ']' })
    expect(onPick).toHaveBeenLastCalledWith('2610-05')
    fireEvent.keyDown(window, { key: '[' })
    expect(onPick).toHaveBeenLastCalledWith('2610-07')
    fireEvent.click(screen.getByRole('button', { name: /Fifth/ }))
    expect(onPick).toHaveBeenLastCalledWith('2610-05')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledWith('2610-06')
  })

  it('reads every day as one with A, and hides the list with C', async () => {
    open()
    await screen.findByText(/install Codex/)
    fireEvent.keyDown(window, { key: 'a' })
    expect(await screen.findByRole('heading', { name: '6 October' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '5 October' })).toBeInTheDocument()
    expect(screen.getByText('The oldest standup ends here.')).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('sp-standup-focus') ?? 'null')).toBeNull() // written a moment later
    fireEvent.keyDown(window, { key: 'c' })
    expect(screen.queryByRole('list', { name: 'Days with a standup' })).toBeNull()
  })

  it('finds a day by the words of its standup', async () => {
    open()
    const list = await screen.findByRole('list', { name: 'Days with a standup' })
    await within(list).findByRole('button', { name: /Fifth/ })
    fireEvent.change(screen.getByRole('textbox', { name: 'Find a day' }), { target: { value: 'rename' } })
    expect(within(list).getAllByRole('button').map((b) => b.textContent)).toEqual([expect.stringContaining('Sixth')])
  })
})
