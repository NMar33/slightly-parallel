import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EntryPointsDesk, LAYOUT_KEY } from './Desk'
import type { Context, Desk, Topic } from './data'
import { linkedChips } from './context'
import { matches } from './data'

const way = (id: string, more: Partial<Topic['ways'][number]> = {}) => ({
  id, name: 'Text console', kind: 'page', url: 'http://localhost:8120', path: '', command: 'npm run dev',
  folder: 'tool/console', note: '', port: 8120, actor: 'operator', updated_at: '2026-11-05T10:00:00', ...more,
})

const FILMS: Topic = {
  id: 'ep_films', project: 'merkhet', name: 'The films and the launch', title: 'с темой «видео и публикация»', state: 'active',
  no_project: false, home: '', what: 'The films of Slightly Parallel and the publishing of v0.1.0.', has_record: true, versions: 2,
  created: '2026-10-16T19:13:00', agent_id: 'cc-c6939458',
  ways: [way('ew_1'), way('ew_2', { name: 'The repository', kind: 'site', url: 'https://github.com/x/y', command: '', folder: '', port: null })],
  stops: [{ id: 'es_1', at: '2026-11-05T18:52:00', author: 'cc-9da6becb', text: 'Live check OK, IndexNow sent.', task_id: '', turn: 12 }],
  stops_n: 1,
  shots: [{ id: 'eh_1', way_id: 'ew_1', caption: 'The console', at: '2026-11-05T18:45:00', author: 'cc-9da6becb', agent_id: 'cc-9da6becb', width: 2, height: 3, src: '/api/entrypoints/shots/eh_1/file' }],
  open_tasks: 1, chats: 2, last_at: '2026-11-05T18:52:00',
}
const THIN: Topic = {
  ...FILMS, id: 'ep_thin', project: '2604-writing-tracker', name: '', title: 'имел ввиду', what: '', has_record: false,
  ways: [], stops: [], stops_n: 0, shots: [], open_tasks: 0, chats: 0, last_at: '2026-10-22T10:00:00', state: 'paused',
}
const CONTEXT: Context = {
  id: 'ep_films',
  chats: [
    { id: 'cc-c6939458', name: 'films', tool: 'claude-code', session_ref: 'aaaa-1111', cwd: '/w/merkhet', first: '2026-10-16T19:13:00', last: '2026-10-16T19:13:00',
      messages: 1, turns: [3], origin: true, did: 'made this entry point', tail: [], commits: 0, live: false, from: null, waiting: false, waiting_text: '', waiting_at: '' },
    { id: 'cc-9da6becb', name: 'wt-seo-guy', tool: 'claude-code', session_ref: 'bbbb-2222', cwd: '/w/site', first: '2026-11-05T18:00:00', last: '2026-11-05T18:52:00',
      messages: 4, turns: [9, 10, 11, 12], origin: false, did: 'Live check OK, IndexNow sent.', commits: 2, live: true, from: { id: 'cc-c6939458', how: 'handoff' },
      tail: [{ who: 'you', at: '2026-11-05T18:50:00', text: 'deploy it', turn: 12, unanswered: true }], waiting: true, waiting_text: 'deploy it', waiting_at: '2026-11-05T18:50:00' },
  ],
  open: [{ id: 'tk_1', title: 'Upload the install film', status: 'todo' }],
  done: [{ id: 'tk_2', title: 'Voice the film', done: '2026-11-01T10:00:00', chat: 'cc-9da6becb', report: 'Voiced, 27 lines.' }],
  decisions: [{ id: 'dc_1', at: '2026-11-01T09:00:00', weight: 'major', title: 'Films stay Unlisted until the release', chat: 'cc-9da6becb' }],
  commits: [{ sha: 'abc1234', at: '2026-11-01T09:30:00', subject: 'voice', chat: 'cc-9da6becb', files: 2, add: 10, del: 3, tasks: ['tk_2'] }],
  commits_n: 1, files: [{ path: 'brand/voice.md', add: 10, del: 3 }], files_n: 1, made: [],
  spend: { tokens: 1200000, dollars: 3.5, by_chat: { 'cc-9da6becb': { tokens: 1200000, dollars: 3.5, turns: 4 } } },
  tasks_n: 2, tasks_truncated: false, briefing: '# The films and the launch\n\nStart in: `cd "/w/merkhet"`\n\n## Ways in\n- Text console: http://localhost:8120\n',
}
const EMPTY_CX: Context = { ...CONTEXT, id: 'ep_thin', chats: [], open: [], done: [], decisions: [], commits: [], commits_n: 0, files: [], files_n: 0, spend: null, tasks_n: 0, briefing: '# имел ввиду\n' }

let posts: Array<{ url: string; body: unknown }> = []

function serve(desk: Desk) {
  posts = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
    if (init?.method === 'POST') {
      posts.push({ url, body: JSON.parse(String(init.body ?? '{}')) })
      return json({ ok: true }, 201)
    }
    if (url.startsWith('/api/entrypoints/desk')) return json(desk)
    if (url.endsWith('/context')) return json(url.includes('ep_thin') ? EMPTY_CX : CONTEXT)
    if (url.endsWith('/ports')) return json({ ways: [{ id: 'ew_1', port: 8120, up: false, why: '' }, { id: 'ew_2', port: null, up: null, why: 'not a local address' }] })
    if (url.startsWith('/api/entrypoints/ep_')) return json({ kept: { message: 'с темой «видео и публикация»', versions: [{ n: 1, at: '2610-16 19:20', how: 'interpreted', note: '', text: '## What\nThe films.\n\n## State\nVoiced.' }], current: { n: 1, at: '2610-16 19:20', how: 'interpreted', note: '', text: '## What\nThe films.\n\n## State\nVoiced.' } } })
    if (url.startsWith('/api/tasks')) return json({ tasks: [{ id: 'tk_9', title: 'Pinned comment', status: 'todo' }] })
    return json({ detail: 'no' }, 404)
  }))
}

function mount(path = '/entrypoints') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}><EntryPointsDesk /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => { try { localStorage.clear() } catch { /* none */ } })
afterEach(() => { vi.unstubAllGlobals() })

describe('Entry points, the desk on the real routes', () => {
  it('lists the topics by project and opens the active one with its ways, feed, tasks and chats', async () => {
    serve({ topics: [THIN, FILMS], projects: ['merkhet', '2604-writing-tracker'] })
    mount()
    const card = await screen.findByTestId('ep-card')
    expect(within(card).getByRole('heading', { name: 'The films and the launch' })).toBeTruthy()
    expect(screen.getAllByTestId('ep-list-item')).toHaveLength(2)
    // A way that is down shows its start command; the site has no up mark.
    await waitFor(() => expect(within(card).getAllByText('down').length).toBe(1))
    expect(within(card).getByText('npm run dev')).toBeTruthy()
    expect(within(card).getAllByText('Live check OK, IndexNow sent.').length).toBeGreaterThan(0)
    expect(await within(card).findByText('Upload the install film')).toBeTruthy()
    // The chats at the bottom, the origin first; your message that waits is said.
    const chats = within(screen.getByTestId('ep-card-chats'))
    expect(chats.getByText('came from here')).toBeTruthy()
    expect(chats.getByText('deploy it')).toBeTruthy()
    expect(within(screen.getByTestId('ep-card-linked')).getByText(/1 task done/)).toBeTruthy()
  })

  it('a thin topic says what is absent instead of empty boxes', async () => {
    serve({ topics: [THIN], projects: ['2604-writing-tracker'] })
    mount()
    const card = await screen.findByTestId('ep-card')
    expect(within(card).getByText('no name yet')).toBeTruthy()
    expect(within(card).getByText('No record written yet.')).toBeTruthy()
    expect(within(card).getByText(/No ways in yet/)).toBeTruthy()
    expect(await within(card).findByText('No chat is linked to this topic yet.')).toBeTruthy()
    expect(await within(card).findByText(/Nothing linked yet/)).toBeTruthy()
  })

  it('no topic at all says how to keep one', async () => {
    serve({ topics: [], projects: [] })
    mount()
    expect(await screen.findByText(/No entry points yet/)).toBeTruthy()
  })

  it('the operator adds a stop, changes the state and renames the topic through the routes', async () => {
    serve({ topics: [FILMS], projects: ['merkhet'] })
    mount()
    const card = await screen.findByTestId('ep-card')
    fireEvent.change(within(card).getByLabelText('Where it stopped, in your words'), { target: { value: 'Uploaded; pinned comment left.' } })
    fireEvent.click(within(card).getByLabelText('Add to the feed'))
    await waitFor(() => expect(posts.some((p) => p.url === '/api/entrypoints/ep_films/stops')).toBe(true))
    expect(posts.find((p) => p.url.endsWith('/stops'))?.body).toEqual({ text: 'Uploaded; pinned comment left.' })
    fireEvent.click(within(card).getByRole('radio', { name: 'paused' }))
    await waitFor(() => expect(posts.some((p) => p.url.endsWith('/state') && (p.body as { state: string }).state === 'paused')).toBe(true))
    fireEvent.click(within(card).getByLabelText('Rename the topic'))
    fireEvent.change(within(card).getByLabelText("The topic's name"), { target: { value: 'Films' } })
    fireEvent.click(within(card).getByText('Save'))
    await waitFor(() => expect(posts.some((p) => p.url.endsWith('/name'))).toBe(true))
  })

  it('a way in is added with labelled fields and sent as the server checks it', async () => {
    serve({ topics: [FILMS], projects: ['merkhet'] })
    mount()
    const card = await screen.findByTestId('ep-card')
    fireEvent.click(within(card).getByText('Add a way in'))
    const form = within(card).getByTestId('ep-way-form')
    fireEvent.change(within(form).getByPlaceholderText('What you call it'), { target: { value: 'Preview' } })
    fireEvent.change(within(form).getByPlaceholderText('http://localhost:8120'), { target: { value: 'http://localhost:8112/hub.html' } })
    fireEvent.change(within(form).getByPlaceholderText('8120'), { target: { value: '8112' } })
    fireEvent.click(within(form).getByText('Add the way in'))
    await waitFor(() => expect(posts.some((p) => p.url.endsWith('/ways'))).toBe(true))
    const sent = posts.find((p) => p.url.endsWith('/ways'))!.body as { way: { port: number; name: string; kind: string } }
    expect(sent.way).toMatchObject({ name: 'Preview', kind: 'page', port: 8112 })
  })

  it('the switch lays the topics out as shelves, kept in this browser, and a tile opens the same card', async () => {
    serve({ topics: [FILMS, THIN], projects: ['merkhet', '2604-writing-tracker'] })
    mount()
    await screen.findByTestId('ep-card')
    fireEvent.click(screen.getByLabelText('Shelves of tiles'))
    expect(await screen.findAllByTestId('ep-shelf')).toHaveLength(2)
    expect(localStorage.getItem(LAYOUT_KEY)).toBe('shelves')
    expect(screen.queryByTestId('ep-card')).toBeNull()
    fireEvent.click(screen.getByText('The films and the launch'))
    expect(await screen.findByTestId('ep-card')).toBeTruthy()
  })

  it('the address picks the layout over the kept one', async () => {
    localStorage.setItem(LAYOUT_KEY, 'list')
    serve({ topics: [FILMS], projects: ['merkhet'] })
    mount('/entrypoints?layout=shelves')
    expect(await screen.findAllByTestId('ep-shelf')).toHaveLength(1)
  })

  it('the briefing as text is the server\'s text', async () => {
    serve({ topics: [FILMS], projects: ['merkhet'] })
    mount()
    const card = await screen.findByTestId('ep-card')
    fireEvent.click(within(card).getByRole('radio', { name: 'as text' }))
    expect((await within(card).findByTestId('ep-briefing-text')).textContent).toBe(CONTEXT.briefing)
  })
})

describe('the pieces', () => {
  it('the find box reads names, ways, ports, stops and captions', () => {
    expect(matches(FILMS, '8120')).toBe(true)
    expect(matches(FILMS, 'indexnow')).toBe(true)
    expect(matches(FILMS, 'console films')).toBe(true)
    expect(matches(FILMS, 'linter')).toBe(false)
  })
  it('a chip says nothing when its kind is empty', () => {
    expect(linkedChips(EMPTY_CX)).toEqual([])
    expect(linkedChips(CONTEXT).map((c) => c.kind)).toEqual(['done', 'decisions', 'commits', 'spent'])
  })
})
