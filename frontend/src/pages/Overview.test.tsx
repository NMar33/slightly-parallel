/**
 * Overview tests — the home page on an injected snapshot.
 *
 * Uses a fetcher prop for the snapshot; the other reads (problems, tasks in
 * review, standups, a year of sessions, terminals) go through a stubbed
 * global fetch. Cyrillic content included throughout.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { fireEvent, render, screen, within, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Overview, type SnapshotResponse } from './Overview'
import { formatYYMMDD } from '../utils/dateUtils'

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchInterval: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const fixture: SnapshotResponse = {
  view_mtime: 1_700_000_000,
  kpi: {
    projects: 2,
    agents: 7,
    open_tasks: 5,
    tasks_done_7d: 3,
    decisions_7d: 4,
    est_hours_30d: 42.5,
  },
  projects: [
    {
      code: 'WT',
      name: 'BeWrite',
      l1_headline: 'Shipped draft split view',
      open_tasks: 4,
      tasks_total: 9,
      tasks_done_7d: 2,
      decisions_7d: 2,
      est_hours_30d: 18,
      active_agents: 3,
      last_activity: '2608-06',
    },
    {
      code: 'МО',
      name: 'матолимп',
      l1_headline: 'рекогниция первого раунда',
      open_tasks: 1,
      tasks_total: 5,
      tasks_done_7d: 1,
      decisions_7d: 1,
      est_hours_30d: 6,
      active_agents: 1,
      last_activity: '2608-05',
    },
  ],
  recent_activity: [
    {
      id: 'a1',
      agent_id: 'agent-01',
      activity_type: 'session',
      duration_min: 45,
      files_touched: '',
      related_goal_id: null,
      created_date: '2608-06',
      summary: 'refactored draft splitter',
      project: 'WT',
    },
    {
      id: 'a2',
      agent_id: 'agent-02',
      activity_type: 'session',
      duration_min: 20,
      files_touched: '',
      related_goal_id: null,
      created_date: '2608-05',
      summary: 'подготовка задач',
      project: 'МО',
    },
  ],
  open_tasks: [
    { id: 'tk_1', project: 'WT', title: 'Wire the split view', status: 'doing', priority: 'high', sprint_id: '', created_date: '2608-05', agent_id: 'operator' },
    { id: 'tk_2', project: 'МО', title: 'рекогниция раунда', status: 'todo', priority: 'med', sprint_id: '', created_date: '2608-04', agent_id: 'operator' },
  ],
  recent_decisions: [
    {
      id: 'd1',
      decision_text: 'Adopt jade accent',
      rationale: 'distinctive',
      source: 'explicit',
      agent_id: 'agent-01',
      related_goal_id: null,
      tags: '',
      created_date: '2608-06',
      project: 'WT',
    },
  ],
  agents: [],
}

const today = formatYYMMDD(new Date())
const daysAgo = (n: number) => { const d = new Date(); d.setDate(d.getDate() - n); return formatYYMMDD(d) }
const session = (over: Record<string, unknown>) => ({
  id: `ses_${Math.random()}`, project: 'WT', agent_id: 'agent-01', created_date: today, start_time: '09:00', end_time: '11:00',
  agent_min: 90, turns_n: 4, tasks: 1, l1: 'refactored draft splitter → done', produced: { decisions: 1 }, git: { commits: 3, add: 120, del: 10 },
  ...over,
})
const SESSIONS = [
  session({}),
  session({ id: 'ses_old', project: 'МО', created_date: daysAgo(3), agent_min: 60, git: { commits: 1, add: 5, del: 0 }, l1: 'подготовка задач' }),
]

let calls: Array<{ url: string; method: string; body: unknown }> = []

function stubFetches() {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url)
    calls.push({ url: path, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = init?.method === 'POST'
      ? (path.endsWith('/api/tasks') ? { metadata: { id: 'tk_new' } } : { ok: true })
      : path.includes('/api/problems')
        ? { total: 1, problems: [{ id: 'pb_1', l1: 'CSV lock contention', severity: 'high', status: 'open', created_date: '2608-05', project: 'WT' }] }
        : path.includes('/api/tasks')
          ? { total: 1, tasks: [{ id: 'tk_9', title: 'Review the cutover plan', status: 'review', project: 'WT', created_date: '2608-05' }] }
          : path.includes('/api/standups')
            ? { total: 1, standups: [{ id: 'su_1', project: 'МО', agent_id: 'agent-02', created_date: today, created_time: '08:00', for_date: daysAgo(1), l1: 'Раунд разобран, задачи на доске' }] }
            : path.includes('/api/sessions')
              ? { total: SESSIONS.length, sessions: SESSIONS }
              : path.includes('/api/terminal/state')
                ? { enabled: false, forced: false, token: '', tmux: false, tmux_version: '', keep: 'plain', launch: 'run', agent: 'claude', font_size: 13, scrollback: 1000, editor: '', projects: {} }
                : { total: 0, sessions: [], counts: {} }
    return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  }))
}

describe('Overview', () => {
  beforeEach(() => {
    stubFetches()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders skeleton while loading', () => {
    let resolve!: (v: SnapshotResponse) => void
    const pending = new Promise<SnapshotResponse>((r) => {
      resolve = r
    })
    renderWithClient(<Overview fetcher={() => pending} />)
    expect(screen.getByTestId('overview-skeleton')).toBeInTheDocument()
    resolve(fixture)
  })

  it('says on top who works and what waits', async () => {
    renderWithClient(<Overview fetcher={async () => fixture} />)
    expect(await screen.findByRole('heading', { level: 1, name: /No agent is working · 2 things wait for you/ })).toBeInTheDocument()
  })

  it('draws the day: agent time, and the counts against a usual working day', async () => {
    renderWithClient(<Overview fetcher={async () => fixture} />)
    const day = await screen.findByTestId('home-day')
    expect(within(day).getByText('Agents worked today')).toBeInTheDocument()
    expect(within(day).getByRole('img', { name: /Agent time through the day/ })).toBeInTheDocument()
    expect(within(day).getByText('commits').parentElement!.textContent).toContain('3')
    expect(within(day).getByText(/the mean of 1 day with agent time/)).toBeInTheDocument()
  })

  it('lists a project per row with its agent time, Cyrillic-safe, linking to the project', async () => {
    renderWithClient(<Overview fetcher={async () => fixture} />)
    const fleet = await screen.findByTestId('fleet-cards')
    expect(within(fleet).getByText('WT')).toBeInTheDocument()
    expect(within(fleet).getByText('МО').closest('a')!.getAttribute('href')).toBe(`/project/${encodeURIComponent('МО')}`)
    expect(within(fleet).getByText('Раунд разобран, задачи на доске')).toBeInTheDocument()
    expect(within(fleet).getByText('1h 30m')).toBeInTheDocument()
  })

  it('Needs you ranks urgent problems above review tasks, and Accept moves the task to done', async () => {
    renderWithClient(<Overview fetcher={async () => fixture} />)
    const needs = await screen.findByTestId('needs-you')
    await waitFor(() => expect(within(needs).getByText('Review the cutover plan')).toBeInTheDocument())
    const rows = within(needs).getAllByRole('listitem')
    expect(rows[0]!.textContent).toContain('CSV lock contention')
    expect(rows[1]!.textContent).toContain('Review the cutover plan')
    expect(within(needs).getByText('Review the cutover plan').closest('a')!.getAttribute('href')).toBe('/project/WT#tasks&task=tk_9')
    fireEvent.click(within(rows[1]!).getByRole('button', { name: 'Accept' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/api/tasks/tk_9/update'))).toBe(true))
    expect(calls.find((c) => c.url.endsWith('/api/tasks/tk_9/update'))!.body).toMatchObject({ status: 'done', actor: 'operator' })
  })

  it('the box on top writes a task on the chosen project', async () => {
    renderWithClient(<Overview fetcher={async () => fixture} />)
    const box = await screen.findByRole('textbox', { name: 'Start an agent on a task' })
    fireEvent.change(box, { target: { value: 'Сделать раунд' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start an agent' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/api/tasks'))).toBe(true))
    expect(calls.find((c) => c.url.endsWith('/api/tasks'))!.body).toMatchObject({ title: 'Сделать раунд', status: 'doing', project: 'WT' })
  })

  it('shows the latest standup of each project', async () => {
    renderWithClient(<Overview fetcher={async () => fixture} />)
    const section = await screen.findByRole('region', { name: 'What happened' })
    expect(within(section).getByText('Раунд разобран, задачи на доске')).toBeInTheDocument()
  })

  it('renders empty state when no projects', async () => {
    const empty: SnapshotResponse = {
      ...fixture,
      kpi: { ...fixture.kpi, projects: 0 },
      projects: [],
      recent_activity: [],
      open_tasks: [],
      recent_decisions: [],
    }
    renderWithClient(<Overview fetcher={async () => empty} />)
    expect(await screen.findByTestId('overview-empty')).toBeInTheDocument()
    expect(screen.getByText(/No projects yet/)).toBeInTheDocument()
  })

  it('renders error state on fetch failure', async () => {
    renderWithClient(
      <Overview
        fetcher={async () => {
          throw new Error('boom')
        }}
      />,
    )
    await waitFor(() =>
      expect(screen.getByTestId('overview-error')).toBeInTheDocument(),
    )
    expect(screen.getByText('boom')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })
})
