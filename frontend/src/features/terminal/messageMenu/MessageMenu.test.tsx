import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ILinkProvider, Terminal } from 'xterm'

import type { ScreenApi } from '../Screen'
import { resetKept } from './data'
import { MessageLayer, type LayerSlot } from './MessageMenu'

/* The screen as Claude Code draws it, and the chat's record. */
const ROWS = [
  '❯ почини падение теста входа на macOS: имя хоста длинное',
  '',
  '● Тест считал строки в склеенном тексте, а длинное имя хоста',
  '  переносило команду на вторую строку.',
  '',
  '✻ Worked for 42s',
  'nick@host:~$ ls',
]
const TURNS = [
  { n: 7, at: '2026-11-18T10:00:00', user: 'почини падение теста входа на macOS: имя хоста длинное', agent: 'Тест считал строки в склеенном тексте, а длинное имя хоста переносило команду на вторую строку.' },
]

let turnsNow: Array<typeof TURNS[number]> = TURNS
let posts: Array<[string, Record<string, unknown>]>
let gets: string[]
let clip: string[]
let opened: string[]

function answer(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
}

beforeEach(() => {
  posts = []; gets = []; clip = []; opened = []; turnsNow = TURNS
  localStorage.clear()
  resetKept()
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (s: string) => { clip.push(s) } }, configurable: true })
  vi.spyOn(window, 'open').mockImplementation((u?: string | URL) => { opened.push(String(u)); return null })
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const path = String(url)
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body ?? '{}')) as Record<string, unknown>
      posts.push([path, body])
      if (path === '/api/tasks') return answer({ metadata: { id: 'tk_0badc0de', title: 'Длинное имя хоста переносило команду' } }, 201)
      if (path === '/api/terminal/sessions') return answer({ session: { id: 't-branch', label: 'b', project: 'harbor' } })
      return answer({ ok: true })
    }
    gets.push(path)
    if (path.startsWith('/api/sessions?agent_id=')) return answer({ sessions: [{ id: 's1', agent_id: 'cc-1', turns_n: turnsNow.at(-1)!.n }] })
    if (path.startsWith('/api/sessions/turns')) return answer({ turns: { s1: turnsNow } })
    if (path.startsWith('/api/forks')) {
      const marked = posts.some(([p]) => p === '/api/forks')
      return answer({ items: marked ? [{ kind: 'fork', target: 'cc-1#7/reply', agent_id: 'cc-1', turn: 7, side: 'reply', state: '', command: "cd /w && claude -r abc --fork-session 'Take up'" }] : [] })
    }
    if (path.startsWith('/api/pins') || path.startsWith('/api/carries')) return answer({ items: [] })
    if (path.startsWith('/api/tasks/tk_a9306fb1')) return answer({ metadata: { id: 'tk_a9306fb1', title: 'Меню сообщений в терминале', status: 'doing', project: 'harbor' }, description: 'Правый щелчок по сообщению.' })
    if (path.startsWith('/api/notes/feed')) {
      return answer({ notes: [{ id: 'nt_0123abcd', project: 'harbor', kind: 'report', title: 'Как сопоставляется щелчок', task: '', entrypoint: '', chat: '', agent_id: 'cc-1', created: '2026-11-18T10:00:00', updated: '2026-11-18T10:00:00', versions: 1, archived_at: '', replaces: [], replaced_by: '', words: 4, body: '# Как сопоставляется щелчок\n\nПо тексту и по ходу.', images: [] }], marks: { ticks: {}, answers: {}, copied: {} }, entities: {}, projects: ['harbor'] })
    }
    return answer({ detail: 'Not Found' }, 404)
  }))
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

interface Rig { slot: LayerSlot; said: string[]; own: Array<[number, number]>; selection: string; pasted: string[]; bracketed: boolean }

function rig(agentId = 'cc-1', rows: string[] = ROWS, extra: Partial<ScreenApi> = {}): Rig {
  const r: Rig = { slot: null as unknown as LayerSlot, said: [], own: [], selection: '', pasted: [], bracketed: false }
  // The screen: the row under the point is the point's y in rows (the test clicks at y = row).
  const api: ScreenApi = {
    find: () => {}, range: () => {}, copyScreen: () => {}, copyLast: () => {},
    rowsAt: async (_x, y) => (y >= 0 && y < rows.length ? { rows, at: y } : null),
    selection: () => r.selection,
    ownMenu: (x, y) => { r.own.push([x, y]) },
    paste: (text) => { r.pasted.push(text) },
    bracketed: () => r.bracketed,
    ...extra,
  }
  function Fake({ slot }: { slot: LayerSlot }) {
    r.slot = slot
    slot.bind(api)
    return <div data-testid="screen" />
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MessageLayer agentId={agentId} project="harbor" say={(s) => r.said.push(s)} refocus={() => {}}>
        {(slot) => <Fake slot={slot} />}
      </MessageLayer>
    </QueryClientProvider>,
  )
  return r
}

/** A right click on row `row`; true when the layer took it. */
async function rightClick(r: Rig, row: number): Promise<boolean> {
  let took = false
  await act(async () => { took = !!r.slot.hooks.contextMenu?.(new MouseEvent('contextmenu', { clientX: 40, clientY: row })) })
  return took
}

const menu = () => screen.getByRole('menu')
const item = (name: string | RegExp) => within(menu()).getByRole('menuitem', { name })

async function ready() {
  // The record is read before a click can be matched (the turns may come from the turns' own cache).
  await waitFor(() => expect(gets.some((g) => g.startsWith('/api/sessions?agent_id='))).toBe(true))
  for (let i = 0; i < 5; i++) await act(async () => { await new Promise((res) => setTimeout(res, 0)) })
}

describe('the message menu', () => {
  it('a right click on the agent\'s reply opens the list for that reply; Pin pins it through the marks route', async () => {
    const r = rig()
    await ready()
    expect(await rightClick(r, 3)).toBe(true)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 7'))
    for (const name of ['Pin', 'Hand over later', 'Branch into a new window', 'Make a task', 'Copy', 'Terminal menu…']) expect(item(name)).toBeTruthy()
    fireEvent.click(item('Pin'))
    await waitFor(() => expect(posts.find(([p]) => p === '/api/pins')).toBeTruthy())
    expect(posts.find(([p]) => p === '/api/pins')![1]).toMatchObject({ chat_agent: 'cc-1', turn: 7, side: 'reply', session_id: 's1', project: 'harbor', actor: 'operator' })
    expect(r.said).toContain('Message pinned')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('the operator\'s message: carry word for word, then as a summary, and hand over later', async () => {
    const r = rig()
    await ready()
    await rightClick(r, 0)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Your message · 7'))
    fireEvent.click(within(menu()).getByRole('menuitemradio', { name: 'Carry after compaction: word for word' }))
    await waitFor(() => expect(posts.find(([p]) => p === '/api/carries')?.[1]).toMatchObject({ chat_agent: 'cc-1', turn: 7, side: '', level: 'carry' }))
    await rightClick(r, 0)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Your message · 7'))
    fireEvent.click(within(menu()).getByRole('menuitemradio', { name: 'Carry after compaction: as a summary' }))
    await waitFor(() => expect(posts.filter(([p]) => p === '/api/carries').at(-1)?.[1]).toMatchObject({ level: 'brief' }))
    await rightClick(r, 0)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Your message · 7'))
    fireEvent.click(item('Hand over later'))
    await waitFor(() => expect(posts.find(([p]) => p === '/api/forks')?.[1]).toMatchObject({ chat_agent: 'cc-1', turn: 7, side: '' }))
    expect(r.said).toEqual(['After compaction: word for word', 'After compaction: as a summary', 'Will be handed over later'])
  })

  it('a status line is the reply above it; Make a task files the reply as the operator\'s task in todo, once', async () => {
    const r = rig()
    await ready()
    await rightClick(r, 5)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 7'))
    fireEvent.click(item('Make a task'))
    // The card carries the server's title for now (from the message); the chat's agent gives the real one.
    await waitFor(() => expect(r.said).toContain('Task made in todo: tk_0badc0de · Длинное имя хоста переносило команду'))
    const [, body] = posts.find(([p]) => p === '/api/tasks')!
    expect(body).toMatchObject({ project: 'harbor', agent_id: 'operator', actor: 'operator', status: 'todo', title: 'Тест считал строки в склеенном тексте, а длинное имя хоста переносило команду на вторую строку.',
      title_from: 'message', title_source: 'cc-1#7/reply' })
    expect(String(body.description)).toContain('From the chat: cc-1#7/reply')
    await rightClick(r, 3)
    await waitFor(() => expect(item('Task tk_0badc0de')).toBeTruthy())
    fireEvent.click(item('Task tk_0badc0de'))
    await waitFor(() => expect(r.said).toContain('Already a task: tk_0badc0de'))
    expect(posts.filter(([p]) => p === '/api/tasks')).toHaveLength(1)
  })

  it('Branch marks the message to fork, opens a terminal with the server\'s command and shows it in a new window', async () => {
    const r = rig()
    await ready()
    await rightClick(r, 3)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 7'))
    fireEvent.click(item('Branch into a new window'))
    await waitFor(() => expect(r.said).toContain('Branch opened in a new window'))
    expect(posts.map(([p]) => p)).toEqual(['/api/forks', '/api/terminal/sessions', '/api/forks/state'])
    expect(posts[1]![1]).toMatchObject({ kind: 'shell', project: 'harbor', command: "cd /w && claude -r abc --fork-session 'Take up'", role: 'chat', actor: 'operator' })
    expect(posts[2]![1]).toEqual({ target: 'cc-1#7/reply', state: 'started', actor: 'operator' })
    expect(opened[0]).toMatch(/\/term\?detached=t-branch$/)
  })

  it('a row that is no recorded message: Copy only (the line), and it says so', async () => {
    const r = rig()
    await ready()
    await rightClick(r, 6)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Message not found in the chat record'))
    expect(within(menu()).getAllByRole('menuitem').map((b) => b.textContent)).toEqual(['Copy', 'Terminal menu…'])
    fireEvent.click(item('Copy'))
    await waitFor(() => expect(clip).toEqual(['nick@host:~$ ls']))
    expect(r.said).toEqual(['Line copied'])
  })

  it('Copy takes the selection first, else the recorded message whole', async () => {
    const r = rig()
    await ready()
    await rightClick(r, 2)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 7'))
    fireEvent.click(item('Copy'))
    await waitFor(() => expect(clip).toEqual([TURNS[0]!.agent]))
    r.selection = 'склеенном'
    await rightClick(r, 2)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 7'))
    fireEvent.click(item('Copy'))
    await waitFor(() => expect(clip.at(-1)).toBe('склеенном'))
  })

  it('a shell with no chat, and Shift: the right click stays the screen\'s own; «Terminal menu…» opens it', async () => {
    const shell = rig('')
    expect(await rightClick(shell, 3)).toBe(false)
    expect(shell.slot.hooks.mouse?.(new MouseEvent('mousedown', { button: 2 }))).toBe(false)
    document.body.innerHTML = ''
    const r = rig()
    await ready()
    let took = true
    await act(async () => { took = !!r.slot.hooks.contextMenu?.(new MouseEvent('contextmenu', { clientX: 40, clientY: 3, shiftKey: true })) })
    expect(took).toBe(false)
    // The right button never reaches xterm (tmux would draw its own menu).
    expect(r.slot.hooks.mouse?.(new MouseEvent('mousedown', { button: 2 }))).toBe(true)
    await rightClick(r, 3)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 7'))
    fireEvent.click(item('Terminal menu…'))
    expect(r.own).toEqual([[40, 3]])
  })

  it('Escape closes the menu', async () => {
    const r = rig()
    await ready()
    await rightClick(r, 3)
    await waitFor(() => expect(menu()).toBeTruthy())
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
  })
})

/* ids: a fake xterm with one row, its link provider taken as the layer registers it. */
function fakeTerm(text: string): { term: Terminal; links: () => Promise<Array<{ text: string; range: { start: { x: number }; end: { x: number } }; activate: (e: MouseEvent) => void }>> } {
  let provider: ILinkProvider | null = null
  const cells = [...text]
  const line = { length: cells.length, getCell: (x: number) => ({ getWidth: () => 1, getChars: () => cells[x] ?? '' }) }
  const term = {
    buffer: { active: { viewportY: 0, getLine: () => line } },
    registerLinkProvider: (p: ILinkProvider) => { provider = p; return { dispose: () => {} } },
    element: document.createElement('div'),
    rows: 1, cols: cells.length,
  } as unknown as Terminal
  return {
    term,
    links: () => new Promise((res) => provider!.provideLinks(1, (l) => res((l ?? []) as never))),
  }
}

describe('ids in the terminal', () => {
  it('a task id opens its card and moves column through the board route', async () => {
    const r = rig()
    const f = fakeTerm('Готово: tk_a9306fb1, заметка nt_0123abcd')
    document.body.appendChild(f.term.element!)
    act(() => r.slot.hooks.terminal?.(f.term, 'live'))
    const links = await f.links()
    expect(links.map((l) => [l.text, l.range.start.x, l.range.end.x])).toEqual([['tk_a9306fb1', 9, 19], ['nt_0123abcd', 30, 40]])
    act(() => links[0]!.activate(new MouseEvent('mouseup', { clientX: 50, clientY: 5 })))
    const card = await screen.findByRole('dialog', { name: 'Task tk_a9306fb1' })
    await within(card).findByText('Меню сообщений в терминале')
    expect(within(card).getByText('Правый щелчок по сообщению.')).toBeTruthy()
    expect(within(card).getByRole('menuitemradio', { name: 'doing' })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(within(card).getByRole('menuitemradio', { name: 'done' }))
    await waitFor(() => expect(posts).toContainEqual(['/api/tasks/tk_a9306fb1/update', { status: 'done', actor: 'operator' }]))
    await waitFor(() => expect(r.said).toContain('tk_a9306fb1 → done'))
    const columns = within(card).getByRole('combobox', { name: 'Move to column' })
    await waitFor(() => expect(columns).toBeEnabled())
    fireEvent.change(columns, { target: { value: 'review' } })
    await waitFor(() => expect(posts).toContainEqual(['/api/tasks/tk_a9306fb1/update', { status: 'review', actor: 'operator' }]))
  })

  it('a note id opens the note in place; Escape closes it', async () => {
    const r = rig()
    const f = fakeTerm('заметка nt_0123abcd')
    document.body.appendChild(f.term.element!)
    act(() => r.slot.hooks.terminal?.(f.term, 'live'))
    const [link] = await f.links()
    act(() => link!.activate(new MouseEvent('mouseup', { clientX: 50, clientY: 5 })))
    const card = await screen.findByRole('dialog', { name: 'Note nt_0123abcd' })
    await waitFor(() => expect(within(card).getAllByText('Как сопоставляется щелчок').length).toBeGreaterThan(0))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

/* ------------------------------------------------------------ commands (tk_29b870f1) */

/** A reply that tells the operator what to run, and the screen as Claude Code draws it. */
const CMD_MD = [
  'Поставь лимит inotify:',
  '',
  '```',
  "! echo 'fs.inotify.max_user_instances=1024' | sudo tee /etc/sysctl.d/60-inotify.conf && sudo sysctl --system",
  '```',
  '',
  'Потом `git status`, и тесты:',
  '',
  '```bash',
  'cd frontend',
  'npx vitest run',
  '```',
  '',
  'Файл `README.md` не трогай.',
].join('\n')
const CMD_ROWS = [
  '❯ почему падает vite',
  '',
  '● Поставь лимит inotify:',
  '',
  "    ! echo 'fs.inotify.max_user_instances=1024' | sudo tee",
  '    /etc/sysctl.d/60-inotify.conf && sudo sysctl --system',
  '',
  '  Потом git status, и тесты:',
  '',
  '    cd frontend',
  '    npx vitest run',
  '',
  '  Файл README.md не трогай.',
  '',
  '$ ',
]
const ONE = "echo 'fs.inotify.max_user_instances=1024' | sudo tee /etc/sysctl.d/60-inotify.conf && sudo sysctl --system"

const names = () => within(menu()).getAllByRole('menuitem').map((b) => b.textContent)

describe('commands in an agent\'s reply', () => {
  beforeEach(() => { turnsNow = [{ n: 8, at: '2026-11-18T11:00:00', user: 'почему падает vite', agent: CMD_MD }] })

  it('a right click on a wrapped command: its items above the message\'s; each copies what it says', async () => {
    const r = rig('cc-1', CMD_ROWS)
    await ready()
    await rightClick(r, 5)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 8'))
    expect(names().slice(0, 3)).toEqual(['Copy the command', 'Copy for Claude Code', 'Paste into the terminal'])
    expect(names().slice(3)).toContain('Pin')
    fireEvent.click(item('Copy the command'))
    await waitFor(() => expect(clip).toEqual([ONE]))
    expect(r.said).toEqual(['Command copied'])
    await rightClick(r, 4)
    await waitFor(() => expect(item('Copy for Claude Code')).toBeTruthy())
    fireEvent.click(item('Copy for Claude Code'))
    await waitFor(() => expect(clip.at(-1)).toBe(`! ${ONE}`))
    await rightClick(r, 4)
    await waitFor(() => expect(item('Paste into the terminal')).toBeTruthy())
    fireEvent.click(item('Paste into the terminal'))
    await waitFor(() => expect(r.pasted).toEqual([ONE]))
    expect(r.said.at(-1)).toBe('Pasted into the terminal: Enter runs it')
  })

  it('a multi-line block: copied whole; no «for Claude Code»; pasted only where a line break waits for Enter', async () => {
    const r = rig('cc-1', CMD_ROWS)
    await ready()
    await rightClick(r, 10)
    await waitFor(() => expect(item('Copy the command')).toBeTruthy())
    expect(within(menu()).queryByRole('menuitem', { name: 'Copy for Claude Code' })).toBeNull()
    expect(item('Paste into the terminal')).toBeDisabled()
    fireEvent.click(item('Copy the command'))
    await waitFor(() => expect(clip).toEqual(['cd frontend\nnpx vitest run']))
    r.bracketed = true
    await rightClick(r, 9)
    await waitFor(() => expect(item('Paste into the terminal')).toBeEnabled())
    fireEvent.click(item('Paste into the terminal'))
    await waitFor(() => expect(r.pasted).toEqual(['cd frontend\nnpx vitest run']))
  })

  it('an inline command is one; a path, prose and the prompt are not', async () => {
    const r = rig('cc-1', CMD_ROWS)
    await ready()
    await rightClick(r, 7)
    await waitFor(() => expect(item('Copy the command')).toBeTruthy())
    fireEvent.click(item('Copy the command'))
    await waitFor(() => expect(clip).toEqual(['git status']))
    for (const row of [2, 12, 14]) {
      await rightClick(r, row)
      await waitFor(() => expect(menu().getAttribute('data-found')).not.toBe('reading'))
      expect(within(menu()).queryByRole('menuitem', { name: 'Copy the command' }), `row ${row}`).toBeNull()
      fireEvent.keyDown(window, { key: 'Escape' })
    }
  })
})

/** A fake xterm that shows `rows` (10 px a cell), with the events and parts the layer uses. */
function screenTerm(rows: string[]) {
  const element = document.createElement('div')
  element.className = 'xterm'
  const scr = document.createElement('div')
  scr.className = 'xterm-screen'
  element.appendChild(scr)
  const cols = 80
  Object.defineProperty(scr, 'clientHeight', { value: rows.length * 10 })
  scr.getBoundingClientRect = () => ({ top: 0, left: 0, width: cols * 10, height: rows.length * 10, right: cols * 10, bottom: rows.length * 10, x: 0, y: 0, toJSON: () => ({}) })
  const ev = () => () => ({ dispose: () => {} })
  const lineOf = (s: string) => ({ isWrapped: false, length: cols, translateToString: () => s, getCell: (x: number) => ({ getWidth: () => 1, getChars: () => s[x] ?? '' }) })
  const term = {
    element, rows: rows.length, cols,
    buffer: { active: { type: 'normal', viewportY: 0, baseY: 0, cursorY: rows.length - 1, length: rows.length, getLine: (i: number) => (i < rows.length ? lineOf(rows[i]!) : undefined) }, onBufferChange: ev() },
    onScroll: ev(), onResize: ev(), onRender: ev(), onWriteParsed: ev(),
    registerLinkProvider: () => ({ dispose: () => {} }),
  } as unknown as Terminal
  document.body.appendChild(element)
  return { term, scr, at: (row: number, x = 5) => ({ clientX: x, clientY: row * 10 + 5 }) }
}

describe('the copy icon', () => {
  it('a shell: over a `$ ` row a copy icon at its right end; a click copies and says so; elsewhere none', async () => {
    const r = rig('')
    const f = screenTerm(['$ echo hi there', 'hi there', '$ '])
    act(() => r.slot.hooks.terminal?.(f.term, 'live'))
    act(() => { f.term.element!.dispatchEvent(new MouseEvent('mousemove', { ...f.at(0), bubbles: true })) })
    const icon = within(f.scr).getByRole('button', { name: 'Copy the command' })
    expect(icon.style.top).toBe('0px')
    expect(icon.style.right).toBe('4px')
    // A press on it is the page's: xterm and tmux never see it.
    expect(r.slot.hooks.mouse?.(Object.defineProperty(new MouseEvent('mousedown', { button: 0 }), 'target', { value: icon }))).toBe(true)
    fireEvent.click(icon)
    await waitFor(() => expect(clip).toEqual(['echo hi there']))
    expect(r.said).toEqual(['Command copied'])
    await waitFor(() => expect(within(f.scr).getByRole('button', { name: 'Copy the command' })).toHaveTextContent('Copied'))
    // The output row, and the prompt being typed on: no icon.
    for (const row of [1, 2]) {
      act(() => { f.term.element!.dispatchEvent(new MouseEvent('mousemove', { ...f.at(row), bubbles: true })) })
      expect(within(f.scr).queryByRole('button')).toBeNull()
    }
    act(() => { f.term.element!.dispatchEvent(new MouseEvent('mouseleave')) })
    expect(within(f.scr).queryByRole('button')).toBeNull()
  })

  it('a shell: a right click on a command takes the menu (its items only); on other rows it stays the screen\'s', async () => {
    const r = rig('')
    const f = screenTerm(['$ echo hi there', 'hi there', '$ '])
    act(() => r.slot.hooks.terminal?.(f.term, 'live'))
    const on = (row: number, type: string, button = 2) => Object.defineProperty(new MouseEvent(type, { ...f.at(row), button }), 'target', { value: f.scr })
    expect(r.slot.hooks.mouse?.(on(1, 'mousedown'))).toBe(false)
    expect(r.slot.hooks.mouse?.(on(0, 'mousedown'))).toBe(true)
    let took = false
    await act(async () => { took = !!r.slot.hooks.contextMenu?.(on(1, 'contextmenu')) })
    expect(took).toBe(false)
    await act(async () => { took = !!r.slot.hooks.contextMenu?.(on(0, 'contextmenu')) })
    expect(took).toBe(true)
    expect(menu()).toHaveAccessibleName('Command')
    expect(names()).toEqual(['Copy the command', 'Copy for Claude Code', 'Paste into the terminal', 'Terminal menu…'])
    fireEvent.click(item('Copy for Claude Code'))
    await waitFor(() => expect(clip).toEqual(['! echo hi there']))
  })

  it('a chat: the icon over every row of a wrapped command stands on its first row', async () => {
    turnsNow = [{ n: 8, at: '2026-11-18T11:00:00', user: 'почему падает vite', agent: CMD_MD }]
    const r = rig('cc-1', CMD_ROWS)
    await ready()
    const f = screenTerm(CMD_ROWS)
    act(() => r.slot.hooks.terminal?.(f.term, 'live'))
    act(() => { f.term.element!.dispatchEvent(new MouseEvent('mousemove', { ...f.at(5), bubbles: true })) })
    const icon = await within(f.scr).findByRole('button', { name: 'Copy the command' })
    expect(icon.dataset.line).toBe('4')
    fireEvent.click(icon)
    await waitFor(() => expect(clip).toEqual([ONE]))
    act(() => { f.term.element!.dispatchEvent(new MouseEvent('mousemove', { ...f.at(12), bubbles: true })) })
    expect(within(f.scr).queryByRole('button')).toBeNull()
  })
})

describe('collapsing a message (tk_a2bb64a1)', () => {
  it('Collapse on a reply hands the screen its id and says where it shows; Expand and Expand all on a collapsed one', async () => {
    const calls: Array<[string[], boolean]> = []
    const kept = new Set<string>()
    let cleared = 0
    const r = rig('cc-1', ROWS, {
      fold: {
        has: (id) => kept.has(id),
        count: () => kept.size,
        set: async (ids, on) => { calls.push([ids, on]); for (const id of ids) { if (on) kept.add(id); else kept.delete(id) } return 'later' },
        clear: async () => { cleared += 1; kept.clear() },
      },
    })
    await ready()
    await rightClick(r, 3)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Agent\'s reply · 7'))
    expect(item('Collapse to one line').getAttribute('title')).toMatch(/when you scroll up; the live screen at the bottom stays/)
    expect(within(menu()).queryByRole('menuitem', { name: 'Expand all' })).toBeNull()
    fireEvent.click(item('Collapse to one line'))
    await waitFor(() => expect(calls.length).toBe(1))
    expect(calls[0]![1]).toBe(true)
    expect(calls[0]![0][0]).toMatch(/^r/)
    await waitFor(() => expect(r.said).toContain('Collapsed: it shows as one line in the history, once it is above the live screen'))
    // Collapsed now: the same reply offers Expand, and Expand all is there.
    await rightClick(r, 2)
    await waitFor(() => expect(item('Expand')).toBeTruthy())
    fireEvent.click(item('Expand'))
    await waitFor(() => expect(calls.at(-1)).toEqual([calls[0]![0], false]))
    await waitFor(() => expect(r.said).toContain('Expanded'))
    // The operator's message is another id; Collapse all replies takes every reply read.
    await rightClick(r, 0)
    await waitFor(() => expect(menu()).toHaveAccessibleName('Your message · 7'))
    fireEvent.click(item('Collapse all replies'))
    await waitFor(() => expect(calls.at(-1)).toEqual([[calls[0]![0][0]], true]))
    await waitFor(() => expect(r.said).toContain('1 reply collapsed'))
    await rightClick(r, 0)
    await waitFor(() => expect(item('Expand all')).toBeTruthy())
    fireEvent.click(item('Expand all'))
    await waitFor(() => expect(cleared).toBe(1))
    // A row that is no message: no Collapse.
    await rightClick(r, 6)
    await waitFor(() => expect(menu().getAttribute('data-found')).toBe('no'))
    expect(within(menu()).queryByRole('menuitem', { name: 'Collapse to one line' })).toBeNull()
  })
})
