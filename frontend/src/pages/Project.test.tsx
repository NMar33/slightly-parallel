/**
 * C8 — Per-Project Page tests.
 *
 * Coverage:
 *   1. Page renders header (name + code + L1 headline) from injected fetcher
 *   2. Tabs by role, Overview active by default; the task numbers render
 *   3. Tab switching — clicking a tab reveals corresponding tabpanel content
 *   4. Page shows error state on fetcher rejection
 *   5. Chats tab and Agents tab fetch their own data
 *   6. Cyrillic strings render (project name, headline)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import ProjectPage, { type ProjectPayload } from './Project'
import { setTabShown } from '../features/project/tabs'

// ---------------------------------------------------------------------------
// Fixture factory
// ---------------------------------------------------------------------------

function makePayload(overrides: Partial<ProjectPayload> = {}): ProjectPayload {
  const base: ProjectPayload = {
    code: 'WT',
    name: 'WriteTogether · матолимп',
    color: '#4FB39A',
    l1_headline: 'Онбординг агентов запущен; калибровка растёт.',
    summary: { open_tasks: 2, tasks_total: 5, tasks_done_7d: 1, decisions_7d: 1, est_hours_30d: 3 },
    decisions: [
      {
        id: 'd1',
        decision_text: 'Adopt jade accent',
        rationale: 'Distinctive vs Linear/Vercel',
        source: 'explicit',
        agent_id: 'a1',
        related_goal_id: null,
        tags: ['design', 'accent'],
        created_date: '2607-28',
      },
    ],
    activity: [
      {
        id: 'act1',
        agent_id: 'a1',
        activity_type: 'complete',
        duration_min: 45,
        files_touched: ['src/foo.ts', 'src/bar.ts'],
        related_goal_id: 'g1',
        created_date: '2608-02',
      },
      {
        id: 'act2',
        agent_id: 'a2',
        activity_type: 'blocked',
        duration_min: 20,
        files_touched: [],
        related_goal_id: 'g2',
        created_date: '2608-03',
      },
      {
        id: 'act3',
        agent_id: 'a1',
        activity_type: 'work',
        duration_min: 90,
        files_touched: ['src/foo.ts'],
        related_goal_id: 'g1',
        created_date: '2608-04',
      },
    ],
    agents: [
      {
        id: 'a1',
        agent_name: 'writer',
        l1_headline: 'Написал рекогниция prototype v1',
        parent_agent_id: null,
        created_date: '2607-20',
        last_active: '2608-04',
        message_count: 42,
        files_touched: ['src/foo.ts', 'src/bar.ts'],
      },
      {
        id: 'a2',
        agent_name: 'reviewer',
        l1_headline: null,
        parent_agent_id: 'a1',
        created_date: '2607-25',
        last_active: '2608-03',
        message_count: 12,
        files_touched: [],
      },
    ],
  }
  return { ...base, ...overrides }
}

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------

function renderPage(
  payload: ProjectPayload | (() => Promise<ProjectPayload>) | Error = makePayload(),
  code = 'WT',
) {
  const fetcher = vi.fn(async () => {
    if (payload instanceof Error) throw payload
    if (typeof payload === 'function') return payload()
    return payload
  })
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const utils = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/project/${code}`]}>
        <Routes>
          <Route path="/project/:code" element={<ProjectPage fetcher={fetcher} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...utils, fetcher }
}

beforeEach(() => {
  // Reset hash so tab reading defaults each test
  if (typeof window !== 'undefined') {
    window.history.replaceState(null, '', '/')
  }
})

// ---------------------------------------------------------------------------
// Page rendering
// ---------------------------------------------------------------------------

describe('ProjectPage — rendering', () => {
  it('renders header + Cyrillic project name after fetch resolves', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: /WriteTogether/ })).toBeTruthy(),
    )
    // Cyrillic subtitle intact
    expect(screen.getByText(/Онбординг агентов/)).toBeTruthy()
  })

  it('shows tabs by role and marks Overview active by default', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Overview' })).toBeTruthy(),
    )
    const overview = screen.getByRole('tab', { name: 'Overview' })
    expect(overview.getAttribute('aria-selected')).toBe('true')
    // Overview, Agents, Tasks, Sprints, Terminals, Decisions, Chats, Files,
    // Architecture, Timer — Terminals hides itself while the terminal is off.
    const labels = screen.getAllByRole('tab').map((t) => t.textContent)
    // The snapshot fetch is not stubbed here, so terminals default to on.
    expect(labels).toEqual(['Overview', 'Agents', 'Tasks', 'Sprints', 'Calendar', 'Terminals', 'Decisions', 'Chats', 'Files', 'Architecture', 'Timer'])
    // The overview's numbers come from the summary the backend sums.
    expect(screen.getByText('Open tasks')).toBeTruthy()
    expect(screen.getByText('of 5')).toBeTruthy()
    expect(screen.getByText('Done this week')).toBeTruthy()
  })

  it('a tab turned off in Settings leaves the strip; its link says so and can turn it on', async () => {
    setTabShown('files', false)
    window.history.replaceState(null, '', '/#files')
    try {
      renderPage()
      expect(await screen.findByText('The Files tab is turned off.')).toBeTruthy()
      expect(screen.queryByRole('tab', { name: 'Files' })).toBeNull()
      expect(screen.getByRole('tab', { name: 'Overview' }).getAttribute('aria-selected')).toBe('true')
      fireEvent.click(screen.getByRole('button', { name: 'Turn it on' }))
      await waitFor(() => expect(screen.getByRole('tab', { name: 'Files' }).getAttribute('aria-selected')).toBe('true'))
      expect(screen.queryByText('The Files tab is turned off.')).toBeNull()
    } finally {
      localStorage.removeItem('sp-project-tabs')
    }
  })

  it('the Tabs menu at the end of the strip turns a tab on in place', async () => {
    try {
      renderPage()
      fireEvent.click(await screen.findByRole('button', { name: /Tabs/ }))
      expect(screen.queryByRole('tab', { name: 'Visions' })).toBeNull()
      fireEvent.click(screen.getByRole('checkbox', { name: 'Visions' }))
      expect(await screen.findByRole('tab', { name: 'Visions' })).toBeTruthy()
      expect((screen.getByRole('checkbox', { name: 'Overview' }) as HTMLInputElement).disabled).toBe(true)
    } finally {
      localStorage.removeItem('sp-project-tabs')
    }
  })

  it('switches tabpanel when a different tab is clicked', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Decisions' })).toBeTruthy(),
    )
    fireEvent.click(screen.getByRole('tab', { name: 'Decisions' }))
    // Decision text is now visible — once the tab's own chunk is in
    // (every tab but Overview is loaded when it is opened).
    expect(await screen.findByText('Adopt jade accent', {}, { timeout: 10_000 })).toBeTruthy()
    // Overview mini-stat headings no longer in DOM
    expect(screen.queryByText('Agent timeline')).toBeNull()
  })

  it('renders error state and retry button when fetcher rejects', async () => {
    renderPage(new Error('boom'))
    await waitFor(() =>
      expect(screen.getByText(/Could not load project/)).toBeTruthy(),
    )
    expect(screen.getByRole('button', { name: /Retry/ })).toBeTruthy()
  })

  it('chats tab renders the chats workbench, Cyrillic intact', async () => {
    // The tab fetches /api/sessions itself — same source as the lens page.
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url)
      if (path.includes('/api/sessions')) {
        return new Response(
          JSON.stringify({
            total: 1,
            sessions: [{
              id: 'ses_test0001',
              // The tab is this project's: the chat must be of it.
              project: 'WT',
              agent_id: 'cc-абвгд123',
              created_date: '2608-14',
              start_time: '10:00',
              end_time: '10:45',
              duration_min: 45,
              turns_n: 3,
              l1: 'Сессия: рекогниция интеграций',
            }],
          }),
          { headers: { 'Content-Type': 'application/json' } },
        )
      }
      if (path.includes('/api/settings')) {
        return new Response(
          JSON.stringify({ groups: [], environment: [], file: '' }),
          { headers: { 'Content-Type': 'application/json' } },
        )
      }
      return new Response(JSON.stringify({}), {
        headers: { 'Content-Type': 'application/json' },
      })
    }))
    try {
      renderPage()
      await waitFor(() =>
        expect(screen.getByRole('tab', { name: 'Chats' })).toBeTruthy(),
      )
      fireEvent.click(screen.getByRole('tab', { name: 'Chats' }))
      // The same workbench /chats renders: the list carries the headline,
      // and the turn count appears in the totals line and the reader's header.
      expect(
        await screen.findByText('Сессия: рекогниция интеграций', {}, { timeout: 10_000 }),
      ).toBeTruthy()
      expect(screen.getAllByText(/3 turns/).length).toBeGreaterThan(0)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('agents tab is the cards + stage, fed by /api/agents/profiles', async () => {
    const profile = (id: string, name: string) => ({
      agent: { agent_id: id, agent_name: name, project: 'WT', created_date: '2608-20', last_active: '2026-08-21T10:00:00', message_count: 3, files_touched: [] },
      origin: { tool: 'claude-code', cwd: '/w', session_ref: '', capture: '', chat_path: '' },
      totals: { sessions_n: 1, minutes: 5, turns: 3, days_active: 1, scans_n: 0, files_n: 0, lines_add: 0, lines_del: 0, file_entries_n: 0, decisions_n: 0, architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0, rules_n: 0, standups_n: 0, tasks_n: 0, tasks_handed_n: 0, tasks_done_n: 0, links_n: 0 },
      by_day: [], by_hour: new Array(24).fill(0), architecture_kinds: {}, sessions: [], scans: [], files: [], decisions: [],
      architecture: [], problems: [], rules: [], tasks: [], links: [], parent: null, children: [], group: { name: '', members: [] },
    })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).includes('/api/agents/profiles')) {
        return { ok: true, json: async () => ({ total: 2, profiles: [profile('a1', 'писатель'), profile('a2', 'reviewer')] }) }
      }
      // Everything else behaves as it did without a stub: no network.
      throw new Error('no network in tests')
    }))
    try {
      renderPage()
      await waitFor(() =>
        expect(screen.getByRole('tab', { name: 'Agents' })).toBeTruthy(),
      )
      fireEvent.click(screen.getByRole('tab', { name: 'Agents' }))
      // One card per agent; the Cyrillic name renders as the card's title.
      await waitFor(() => expect(screen.getByRole('article', { name: 'писатель' })).toBeTruthy())
      expect(screen.getByRole('article', { name: 'reviewer' })).toBeTruthy()
      // Clicking a card lifts it onto the stage.
      fireEvent.click(screen.getByRole('article', { name: 'reviewer' }))
      expect(screen.getByRole('dialog')).toBeTruthy()
      expect(window.location.hash).toBe('#agents&agent=a2&sec=chats')
    } finally {
      vi.unstubAllGlobals()
      window.location.hash = ''
    }
  })
})
