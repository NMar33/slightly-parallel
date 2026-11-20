import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AquaSession, Group } from './model'

// The live terminal is xterm on a socket: here a stub that says which terminal it is and types on request.
// A terminal kept mounted behind the one in front (TermApp KEEP_SCREENS) is a bare mark.
const mounted: string[] = []
/** Times each terminal was made (a mount, not a render): a switch back to a kept one makes none. */
const made: Record<string, number> = {}
vi.mock('../../terminal/Screen', async () => {
  const { useEffect } = await import('react')
  return {
  Screen: ({ sid, visible = true, onInput, onTitle }: { sid: string; visible?: boolean; onInput?: (d: string) => void; onTitle?: (t: string) => void }) => {
    mounted.push(sid)
    useEffect(() => { made[sid] = (made[sid] ?? 0) + 1 }, [sid])
    if (!visible) return <span data-testid="kept" data-sid={sid} />
    return (
      <>
        <button type="button" data-testid="screen" data-sid={sid} onClick={() => onInput?.('a')}>screen {sid}</button>
        <button type="button" data-testid="osc" onClick={() => onTitle?.('hbr-2611-18')}>osc</button>
      </>
    )
  },
  }
})

import { TermApp } from './TermApp'

let n = 0
const row = (p: Partial<AquaSession>): AquaSession => ({
  id: `t${++n}`, kind: 'resume', label: `chat ${n}`, project: 'harbor', cwd: '/w', command: '', agent_id: '', task_id: '',
  created: `2026-11-16T10:${String(n).padStart(2, '0')}`, backend: 'tmux', state: 'working', program: 'claude', last_output: 0, ...p,
})

interface World {
  enabled?: boolean
  sessions: AquaSession[]
  groups?: Group[] | null
  restore?: { needed: number; sessions: Array<{ id: string; label: string }> } | null
  /** The time routes: absent (404) unless given. */
  time?: { running: unknown[]; project: Record<string, number>; total: number; totalAgent?: number; working?: string[] }
  /** GET /api/terminal/tabs: absent (404) unless given. */
  tabs?: Record<string, { title: string; agent_id: string; chat: Record<string, unknown> | null }>
  agentProfile?: Record<string, unknown>
}
let world: World
const posts: Array<[string, unknown]> = []

function answer(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
}

beforeEach(() => {
  n = 0
  mounted.length = 0
  for (const k of Object.keys(made)) delete made[k]
  posts.length = 0
  localStorage.clear()
  Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true })
  Object.defineProperty(window, 'innerHeight', { value: 1000, configurable: true })
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const path = String(url)
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body ?? '{}'))
      posts.push([path, body])
      if (path === '/api/terminal/restore') return answer({ results: [{ id: 'r1', label: 'release-notes', ok: true }, { id: 'r2', label: 'api-limits', ok: false, error: 'the session id is gone' }] })
      if (path === '/api/terminal/groups') {
        const group = { id: 'g9', name: body.name, color: body.color, project: body.project }
        world.groups?.push(group)
        return answer({ group })
      }
      if (path.endsWith('/group')) {
        const session = world.sessions.find((s) => s.id === path.split('/')[4])!
        session.group = body.group
        return answer({ session })
      }
      if (path.endsWith('/capture')) return answer({ text: '$ make test\n41 passed' })
      if (path.endsWith('/wake') && body.shell === true) {
        const id = path.split('/')[4]
        world.sessions = world.sessions.map((s) => s.id === id ? { ...s, state: 'shell' } : s)
      }
      return answer({ ok: true })
    }
    if (path === '/api/terminal/state') {
      return answer({ enabled: world.enabled ?? true, supported: true, token: 'tok', open_shell: true, font_size: 13, scrollback: 1000, editor: '', agent: 'claude', projects: { harbor: '/h', kelp: '/k', lumen: '/l' } })
    }
    if (path === '/api/terminal/sessions') return answer({ sessions: world.sessions, counts: {} })
    if (path === '/api/terminal/tabs') return world.tabs ? answer({ tabs: world.tabs }) : answer({ detail: 'Not Found' }, 404)
    if (path === '/api/terminal/agents') return answer({ agents: { claude: true, codex: true, opencode: false } })
    if (path.startsWith('/api/terminal/resumable')) return answer({ chats: [{ agent_id: 'cc-old', name: 'old chat', tool: 'claude-code' }] })
    if (path.startsWith('/api/terminal/branch/')) return answer({ command: 'cd /h && claude -r ref --fork-session', project: 'harbor', name: 'x' })
    if (path === '/api/agents/codex-current/profile' && world.agentProfile) return answer(world.agentProfile)
    if (path.startsWith('/api/tasks?project=')) return answer({ tasks: [{ id: 'tk_1', title: 'Fix the bill', status: 'todo' }, { id: 'tk_2', title: 'Old', status: 'done' }] })
    if (path === '/api/terminal/groups') return world.groups ? answer({ groups: world.groups }) : answer({ detail: 'Not Found' }, 404)
    if (path === '/api/terminal/restore') return world.restore ? answer(world.restore) : answer({ detail: 'Not Found' }, 404)
    if (path.startsWith('/api/pins') || path.startsWith('/api/carries') || path.startsWith('/api/forks')) return answer({ items: [] })
    if (path.startsWith('/api/sessions')) return answer({ sessions: [] })
    if (world.time && path === '/api/time/running') return answer({ running: world.time.running })
    if (world.time && path === '/api/time/summary') return answer({ today_min: world.time.total })
    if (world.time && path === '/api/time/summary?agent_work=true') return answer({ today_min: world.time.total, today_agent_min: world.time.totalAgent })
    if (world.time && path.startsWith('/api/time/summary?project=')) return answer({ today_min: world.time.project[new URL(path, 'http://x').searchParams.get('project')!] ?? 0 })
    if (world.time && path === '/api/time/auto') return answer({ working: (world.time.working ?? []).map((p) => ({ project: p, entry_id: 'tm_a', task_id: '', top: 100 })), away: [], modes: {}, default_mode: 'remind' })
    return answer({ detail: 'Not Found' }, 404)
  }))
})
afterEach(() => { vi.unstubAllGlobals(); delete (window as unknown as { spWindow?: unknown }).spWindow })

function page(q = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[`/term${q}`]}><TermApp /></MemoryRouter></QueryClientProvider>)
}
const frame = () => screen.getByRole('dialog', { name: /^Window: / })
const at = (side: 'left' | 'right') => {
  const b = frame().querySelector(`[data-toggle="${side}"]`) as HTMLElement
  return parseInt(frame().style.left || '0', 10) + parseInt(b.style.left, 10)
}
const key = (code: string, mods: { alt?: boolean; ctrl?: boolean; shift?: boolean } = {}) =>
  fireEvent.keyDown(window, { code, key: code, altKey: !!mods.alt, ctrlKey: !!mods.ctrl, shiftKey: !!mods.shift })

describe('SP Aqua at /term', () => {
  it('says in one line how to turn the terminal on when it is off', async () => {
    world = { enabled: false, sessions: [] }
    page()
    expect(await screen.findByText('python3 sp.py terminal on')).toBeTruthy()
    expect(screen.queryByRole('tablist')).toBeNull()
  })

  it('at rest: the current workspace as tabs with state dots, the others folded behind +N with a waiting marker, one terminal mounted; the last ones in front stay mounted, hidden', async () => {
    const a = row({ label: 'calendar-overlap' })
    const b = row({ label: 'api-limits', state: 'waiting' })
    const c = row({ project: 'kelp', label: 'release-0.9', state: 'waiting' })
    const z = row({ label: 'dusty', asleep: true, state: 'asleep' })
    world = { sessions: [a, b, c, z] }
    page()
    await screen.findAllByRole('tab')
    const tabs = screen.getByRole('tablist', { name: 'Chats' })
    expect(within(tabs).getAllByRole('tab').map((x) => x.textContent)).toEqual(['calendar-overlap', 'api-limits', 'dusty'])
    expect(within(tabs).getByRole('tab', { name: /api-limits/ }).querySelector('[aria-label="your turn"]')).toBeTruthy()
    const more = screen.getByRole('button', { name: /\+1/ })
    expect(more.querySelector('[aria-label="your turn"]')).toBeTruthy()
    expect(new Set(mounted)).toEqual(new Set([a.id]))
    fireEvent.click(within(tabs).getByRole('tab', { name: /api-limits/ }))
    expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(b.id)
    expect(screen.getAllByTestId('screen')).toHaveLength(1)
    // The tab left stays mounted, hidden, outside .aqua-screen: back to it is no reconnect (tk_74f2d3ba).
    const kept = screen.getByTestId('kept')
    expect(kept.getAttribute('data-sid')).toBe(a.id)
    expect(kept.closest('.aqua-screen')).toBeNull()
    expect(screen.getByTestId('screen').closest('.aqua-screen')).toBeTruthy()
    fireEvent.click(within(tabs).getByRole('tab', { name: /calendar-overlap/ }))
    expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(a.id)
    expect(screen.getByTestId('kept').getAttribute('data-sid')).toBe(b.id)
    expect(made).toEqual({ [a.id]: 1, [b.id]: 1 })
    // a sleeping chat has no terminal: a Wake in its place
    fireEvent.click(within(tabs).getByRole('tab', { name: /dusty/ }))
    expect(screen.queryByTestId('screen')).toBeNull()
    expect(screen.getByText(/dusty is asleep/)).toBeTruthy()
    expect(screen.getByText(/dusty is asleep/).closest('.aqua-screen')).toBeTruthy()
  })

  it('opens first on the workspace of a chat waiting on you, else of the newest terminal', async () => {
    world = { sessions: [row({ project: 'kelp', label: 'release-0.9', state: 'waiting' }), row({ label: 'calendar-overlap' })] }
    const one = page()
    await screen.findAllByRole('tab')
    expect(screen.getAllByRole('tab').map((x) => x.textContent)).toEqual(['release-0.9'])
    one.unmount()
    world = { sessions: [row({ project: 'kelp', label: 'release-0.9' }), row({ label: 'calendar-overlap' })] }
    page()
    await screen.findAllByRole('tab')
    expect(screen.getAllByRole('tab').map((x) => x.textContent)).toEqual(['calendar-overlap'])
  })

  it('does not attach to an ended terminal by itself: it offers to start it again or open a shell in it', async () => {
    const a = row({ label: 'etl-nightly', state: 'ended', asleep: false })
    world = { sessions: [a] }
    page()
    expect(await screen.findByText('etl-nightly ended.')).toBeTruthy()
    expect(screen.queryByTestId('screen')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Start it again' }))
    await waitFor(() => expect(posts.find(([p]) => p === `/api/terminal/sessions/${a.id}/wake`)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: 'Open a shell in it' }))
    expect((await screen.findByTestId('screen')).getAttribute('data-sid')).toBe(a.id)
    expect(posts).toContainEqual([`/api/terminal/sessions/${a.id}/wake`, { actor: 'operator', shell: true }])
  })

  it('goes to another workspace from the folded list', async () => {
    const c = row({ project: 'kelp', label: 'release-0.9' })
    world = { sessions: [row({ label: 'calendar-overlap' }), c] }
    page()
    fireEvent.click(await screen.findByRole('button', { name: /\+1/ }))
    fireEvent.click(within(screen.getByRole('menu', { name: 'The other workspaces, folded' })).getByRole('menuitem', { name: /kelp/ }))
    expect(within(screen.getByRole('tablist', { name: 'Chats' })).getAllByRole('tab').map((x) => x.textContent)).toEqual(['release-0.9'])
    expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(c.id)
  })

  it('counts the keys typed in a terminal and sends the count, never the text', async () => {
    const a = row({})
    world = { sessions: [a] }
    page()
    fireEvent.click(await screen.findByTestId('screen'))
    await waitFor(() => expect(posts.find(([p]) => p === '/api/terminal/typing')).toBeTruthy())
    const [, body] = posts.find(([p]) => p === '/api/terminal/typing')!
    expect(body).toMatchObject({ sid: a.id, keys: 1 })
    expect(JSON.stringify(body)).not.toContain('"a"')
  })

  it('a terminal opened from "+" comes to the front, though the list does not have it yet', async () => {
    const a = row({ label: 'calendar-overlap' })
    world = { sessions: [a] }
    const fresh = row({ kind: 'shell', label: 'harbor', state: 'shell', role: 'shell' } as Partial<AquaSession>)
    const base = (fetch as unknown as { getMockImplementation: () => (u: string, i?: RequestInit) => Promise<Response> }).getMockImplementation()
    vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
      if (String(url) === '/api/terminal/sessions' && init?.method === 'POST') {
        // The server has it from now on; the page's list learns it on its next read.
        world.sessions = [a, fresh]
        return answer({ session: fresh, existing: false }, 201)
      }
      return base(url, init)
    }))
    page()
    expect((await screen.findByTestId('screen')).getAttribute('data-sid')).toBe(a.id)
    fireEvent.click(screen.getByRole('button', { name: 'Choose what to open' }))
    fireEvent.click(screen.getByRole('menuitem', { name: /^Plain terminal/ }))
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(fresh.id))
    const tabs = screen.getByRole('tablist', { name: 'Chats' })
    await waitFor(() => expect(within(tabs).getByRole('tab', { name: /^harbor/ }).getAttribute('aria-selected')).toBe('true'))
  })

  it('the workspaces button goes round: the chat, its workspace, every workspace, the chat', async () => {
    world = { sessions: [row({ label: 'calendar-overlap' })] }
    const { container } = page()
    await screen.findByRole('tablist', { name: 'Chats' })
    const level = () => container.querySelector('[data-level]')?.getAttribute('data-level')
    const button = screen.getByRole('button', { name: 'Workspaces' })
    expect(level()).toBe('chat')
    fireEvent.click(button); expect(level()).toBe('ws')
    fireEvent.click(button); expect(level()).toBe('all')
    fireEvent.click(button); expect(level()).toBe('chat')
  })

  it('reads the inspector chat from resolved tab data and labels its branches', async () => {
    const current = row({ label: 'current terminal', state: 'waiting' })
    const linked = row({ agent_id: 'cc-with-title', label: 'linked terminal' })
    world = {
      sessions: [current, linked],
      tabs: { [current.id]: { title: '', agent_id: 'codex-current', chat: null } },
      agentProfile: {
        tasks: [], parent: null, helpers: [], links: [],
        children: [
          { agent_id: 'cc-named', agent_name: 'Release review', chat_title: 'Review draft' },
          { agent_id: 'cc-with-title', agent_name: 'cc-with-title', chat_title: 'Check keyboard navigation' },
          { agent_id: 'cc-unnamed', agent_name: 'cc-unnamed', chat_title: ' ' },
        ],
      },
    }
    page()
    await screen.findByTestId('screen')
    fireEvent.click(screen.getByRole('button', { name: 'Right sidebar' }))
    const sidebar = within(screen.getByRole('complementary', { name: 'Right sidebar' }))
    fireEvent.click(sidebar.getByRole('button', { name: 'Linked chats and branches' }))
    const titled = await sidebar.findByText('Check keyboard navigation')
    expect(sidebar.getByText('Release review')).toBeVisible()
    expect(sidebar.getByText('cc-unnamed')).toBeVisible()
    expect(titled.title).toBe(linked.agent_id)
    fireEvent.click(within(titled.closest('li')!).getByRole('button', { name: / Open$/ }))
    expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(linked.id)
  })

  it('opens the sidebars with alt+[ and alt+]; in a browser the toggles never move', async () => {
    world = { sessions: [row({ label: 'calendar-overlap' })] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    const start = { l: at('left'), r: at('right') }
    key('BracketLeft', { alt: true })
    expect(screen.getByRole('complementary', { name: 'Left sidebar' })).toBeTruthy()
    expect(within(screen.getByRole('navigation', { name: 'Workspaces' })).getByText('harbor')).toBeTruthy()
    key('BracketRight', { alt: true })
    expect(screen.getByRole('complementary', { name: 'Right sidebar' })).toBeTruthy()
    expect(at('left')).toBe(start.l)
    expect(at('right')).toBe(start.r)
    key('BracketLeft', { alt: true })
    expect(screen.queryByRole('complementary', { name: 'Left sidebar' })).toBeNull()
    expect(at('right')).toBe(start.r)
  })

  it('opens window settings in place of the left sidebar and restores it on close', async () => {
    const sent: unknown[] = []
    ;(window as unknown as { spWindow: unknown }).spWindow = { postMessage: (m: unknown) => sent.push(m) }
    world = { sessions: [row({ label: 'calendar-overlap' })] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    fireEvent.click(screen.getByRole('button', { name: 'Left sidebar' }))
    expect(screen.getByRole('navigation', { name: 'Workspaces' })).toBeTruthy()
    sent.length = 0
    fireEvent.click(screen.getByRole('button', { name: 'Window settings' }))
    expect(screen.queryByRole('navigation', { name: 'Workspaces' })).toBeNull()
    const settings = screen.getByRole('complementary', { name: 'Window settings' })
    expect(within(settings).getByRole('checkbox', { name: 'Instant motion' })).toBeTruthy()
    expect(within(settings).getByText('Keys')).toBeTruthy()
    fireEvent.click(within(settings).getByText('Colour scheme'))
    expect(within(settings).getByRole('radiogroup', { name: 'Colour scheme' })).toBeTruthy()
    key('Escape')
    expect(screen.queryByRole('complementary', { name: 'Window settings' })).toBeNull()
    expect(screen.getByRole('navigation', { name: 'Workspaces' })).toBeTruthy()
    expect(sent.filter((m) => (m as { op: string }).op === 'grow')).toEqual([])
  })

  it('sets the title and tab row heights independently', async () => {
    world = { sessions: [row({ label: 'calendar-overlap' })] }
    const view = page()
    const tabs = await screen.findByRole('tablist', { name: 'Chats' })
    const titleRow = frame().querySelector<HTMLElement>('[data-window-title]')!
    const tabRow = tabs.closest<HTMLElement>('[data-window-tabs]')!
    fireEvent.click(screen.getByRole('button', { name: 'Window settings' }))
    const settings = screen.getByRole('complementary', { name: 'Window settings' })
    fireEvent.change(within(settings).getByLabelText('Title row height'), { target: { value: '2' } })
    expect(titleRow.style.height).toBe('17px')
    expect(tabRow.style.height).toBe('32px')
    fireEvent.change(within(settings).getByLabelText('Tab row height'), { target: { value: '1.5' } })
    expect(tabRow.style.height).toBe('21px')
    view.unmount()
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    expect(frame().querySelector<HTMLElement>('[data-window-title]')?.style.height).toBe('17px')
    expect(frame().querySelector<HTMLElement>('[data-window-tabs]')?.style.height).toBe('21px')
  })

  it('in the app window a sidebar grows the window through the bridge, and close and minimise are there', async () => {
    const sent: unknown[] = []
    ;(window as unknown as { spWindow: unknown }).spWindow = { postMessage: (m: unknown) => sent.push(m) }
    world = { sessions: [row({ label: 'calendar-overlap' })] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    key('BracketLeft', { alt: true })
    expect(sent).toContainEqual({ op: 'grow', left: 236, right: 0 })
    key('BracketLeft', { alt: true })
    expect(sent).toContainEqual({ op: 'grow', left: -236, right: 0 })
    fireEvent.click(screen.getByRole('button', { name: 'Close the window' }))
    expect(sent).toContainEqual({ op: 'close' })
    fireEvent.click(screen.getByRole('button', { name: 'Enter fullscreen' }))
    expect(sent).toContainEqual({ op: 'fullscreen' })
    expect(sent.some((m) => (m as { op: string }).op === 'title')).toBe(true)
  })

  it('a sidebar opened and closed at once leaves the terminal its full width (no stale "the window never answered")', async () => {
    // A window that answers quickly, as on Windows: the resize comes a moment
    // after the message (the main process is another process), well before the
    // next key; four keys take less than the half second the page waits for
    // a window that cannot grow.
    ;(window as unknown as { spWindow: unknown }).spWindow = {
      postMessage: (m: { op: string; left?: number; right?: number }) => {
        if (m.op !== 'grow') return
        setTimeout(() => {
          Object.defineProperty(window, 'innerWidth', { value: window.innerWidth + (m.left ?? 0) + (m.right ?? 0), configurable: true })
          window.dispatchEvent(new Event('resize'))
        }, 5)
      },
    }
    world = { sessions: [row({ label: 'calendar-overlap' })] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    const termW = () => parseInt((frame().querySelector('[data-level]') as HTMLElement).style.width, 10)
    const w0 = termW()
    const answered = () => act(() => new Promise((r) => setTimeout(r, 30)))
    for (const code of ['BracketLeft', 'BracketRight', 'BracketLeft', 'BracketRight']) {
      key(code, { alt: true })
      await answered()
      expect(termW()).toBe(w0)
    }
    expect(window.innerWidth).toBe(1680)
    expect(termW()).toBe(w0)
    await act(() => new Promise((r) => setTimeout(r, 700)))
    expect(termW()).toBe(w0)
  })

  it('a window that cannot grow: the terminal gives up the room for the sidebar itself', async () => {
    ;(window as unknown as { spWindow: unknown }).spWindow = { postMessage: () => {} }
    world = { sessions: [row({ label: 'calendar-overlap' })] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    const termW = () => parseInt((frame().querySelector('[data-level]') as HTMLElement).style.width, 10)
    const w0 = termW()
    key('BracketLeft', { alt: true })
    await act(() => new Promise((r) => setTimeout(r, 700)))
    expect(termW()).toBe(w0 - 236)
    key('BracketLeft', { alt: true })
    await act(() => new Promise((r) => setTimeout(r, 700)))
    expect(termW()).toBe(w0)
  })

  it('has no close or minimise in a browser', async () => {
    world = { sessions: [row({})] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    expect(screen.queryByRole('button', { name: 'Close the window' })).toBeNull()
  })

  it('steps out to the workspace (text tiles, sleeping row, servers), then every workspace, and back with Esc', async () => {
    const k = row({ project: 'kelp', label: 'release-0.9' })
    const a = row({ label: 'calendar-overlap' })
    world = { sessions: [a, row({ label: 'dusty', asleep: true }), row({ label: 'web', role: 'server', kind: 'shell' }), k] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    const body = () => frame().querySelector('[data-level]')!
    key('ArrowUp', { ctrl: true, shift: true })
    expect(body().getAttribute('data-level')).toBe('ws')
    expect(await screen.findByText(/41 passed/)).toBeTruthy()
    expect(within(screen.getByRole('list', { name: 'Asleep' })).getByText('dusty')).toBeTruthy()
    key('ArrowUp', { ctrl: true, shift: true })
    expect(body().getAttribute('data-level')).toBe('all')
    expect(screen.getByRole('region', { name: 'kelp' })).toBeTruthy()
    key('Escape')
    expect(body().getAttribute('data-level')).toBe('ws')
    key('Escape')
    expect(body().getAttribute('data-level')).toBe('chat')
  })

  it('folds the title row with alt+T: a thin row that a click unfolds, the toggles half as wide in the tab strip', async () => {
    world = { sessions: [row({})] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    const toggle = () => frame().querySelector('[data-toggle="left"]') as HTMLElement
    expect(toggle().style.width).toBe('24px')
    expect(toggle().getAttribute('data-in')).toBeNull()
    key('KeyT', { alt: true })
    expect(frame().getAttribute('data-folded')).toBe('true')
    expect(toggle().getAttribute('data-in')).toBe('strip')
    expect(toggle().style.width).toBe('12px')
    fireEvent.click(toggle())
    expect(screen.getByRole('complementary', { name: 'Left sidebar' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Unfold the title row (alt+T)' }))
    expect(frame().getAttribute('data-folded')).toBeNull()
    expect(toggle().style.width).toBe('24px')
  })

  it('without the groups route the tab menu offers no group; with it, a new coloured group from a tab', async () => {
    const a = row({ label: 'calendar-overlap' })
    world = { sessions: [a], groups: null }
    const one = page()
    fireEvent.contextMenu((await screen.findAllByRole('tab'))[0]!)
    expect(screen.queryByRole('menuitem', { name: /New group/ })).toBeNull()
    expect(screen.getByRole('menuitem', { name: 'Detach into its own window' })).toBeTruthy()
    one.unmount()

    world = { sessions: [a], groups: [] }
    page()
    await screen.findAllByRole('tab')
    await waitFor(() => { fireEvent.contextMenu(screen.getAllByRole('tab')[0]!); expect(screen.getByRole('menuitem', { name: /New group/ })).toBeTruthy() })
    fireEvent.click(screen.getByRole('menuitem', { name: /New group/ }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Group name' }), { target: { value: 'Release week' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Colour 6' }))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Make the group' })) })
    await waitFor(() => expect(posts.find(([p]) => p === `/api/terminal/sessions/${a.id}/group`)).toBeTruthy())
    expect(posts.find(([p]) => p === '/api/terminal/groups')![1]).toMatchObject({ name: 'Release week', color: 6, project: 'harbor' })
    expect(posts.find(([p]) => p === `/api/terminal/sessions/${a.id}/group`)![1]).toMatchObject({ group: 'g9' })
    expect(await screen.findByRole('group', { name: 'Release week' })).toBeTruthy()
    expect(localStorage.getItem('sp-aqua-workspace')).not.toBe('g:g9')
  })

  it('collapses a tab group in its project, remembers it on reload and keeps its terminal active', async () => {
    const a = row({ label: 'first' })
    const b = row({ label: 'middle' })
    const c = row({ label: 'last', group: 'g9', state: 'waiting' })
    world = { sessions: [a, b, c], groups: [
      { id: 'g9', name: 'Release', color: 6, project: 'harbor' },
      { id: 'g10', name: 'Other project', color: 2, project: 'kelp' },
    ] }
    const one = page('?ws=harbor')
    const strip = await screen.findByRole('tablist', { name: 'Chats' })
    const group = await within(strip).findByRole('group', { name: 'Release' })
    const tab = await within(strip).findByRole('tab', { name: /first/ })
    fireEvent.contextMenu(tab)
    expect(screen.queryByRole('menuitem', { name: /Other project/ })).toBeNull()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Add to tab group Release' }))
    await waitFor(() => expect(within(strip).getAllByRole('tab').map((el) => el.textContent)).toEqual(['first', 'last', 'middle']))
    fireEvent.click(within(group).getByRole('tab', { name: /last/ }))
    fireEvent.click(within(group).getByRole('button', { name: 'Release' }))
    expect(within(group).queryAllByRole('tab')).toHaveLength(0)
    expect(within(group).getByRole('button', { name: 'Release' }).getAttribute('aria-current')).toBe('true')
    expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(c.id)
    one.unmount()

    page('?ws=harbor')
    const restored = await screen.findByRole('button', { name: 'Release' })
    expect(restored.getAttribute('aria-expanded')).toBe('false')
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(c.id))
    fireEvent.click(restored)
    fireEvent.contextMenu(screen.getByRole('tab', { name: /first/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Remove from tab group' }))
    await waitFor(() => expect(within(screen.getByRole('group', { name: 'Release' })).getAllByRole('tab')).toHaveLength(1))
  })

  it('offers Restore all after a restart and shows each chat\'s result, failures with their reason', async () => {
    world = { sessions: [row({})], restore: { needed: 2, sessions: [{ id: 'r1', label: 'release-notes' }, { id: 'r2', label: 'api-limits' }] } }
    page()
    const run = await screen.findByRole('button', { name: 'Restore all' })
    await act(async () => { fireEvent.click(run) })
    expect(await screen.findByText(/the session id is gone/)).toBeTruthy()
    expect(screen.getByText('Restored')).toBeTruthy()
  })

  it('a detached chat window: that one chat, no strip, its workspace named in the title', async () => {
    const a = row({ label: 'calendar-overlap' })
    world = { sessions: [a, row({ label: 'api-limits' })] }
    page(`?detached=${a.id}`)
    expect(await screen.findByRole('dialog', { name: 'Window: calendar-overlap — from harbor' })).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(a.id))
    expect(screen.queryByRole('tablist', { name: 'Chats' })).toBeNull()
  })

  it('a workspace window shows that workspace and nothing folded', async () => {
    world = { sessions: [row({ label: 'calendar-overlap' }), row({ project: 'kelp', label: 'release-0.9' })] }
    page('?ws=kelp')
    const tabs = await screen.findByRole('tablist', { name: 'Chats' })
    await waitFor(() => expect(within(tabs).getAllByRole('tab').map((x) => x.textContent)).toEqual(['release-0.9']))
    expect(screen.queryByRole('button', { name: /\+1/ })).toBeNull()
  })

  it('changes the fullscreen control when the native window enters and leaves fullscreen', async () => {
    world = { sessions: [row({ label: 'api-limits' })] }
    const sent: unknown[] = []
    let receive: ((value: boolean) => void) | undefined
    ;(window as unknown as { spWindow: unknown }).spWindow = {
      postMessage: (message: unknown) => sent.push(message),
      observeFullscreen: (listener: (value: boolean) => void) => { receive = listener; return () => { receive = undefined } },
    }
    page()
    const enter = await screen.findByRole('button', { name: 'Enter fullscreen' })
    const enterIcon = enter.querySelector('svg')?.innerHTML
    expect(enterIcon).toBeTruthy()
    fireEvent.click(enter)
    expect(sent).toContainEqual({ op: 'fullscreen' })
    expect(screen.getByRole('button', { name: 'Enter fullscreen' })).toBe(enter)
    act(() => receive?.(true))
    const exit = screen.getByRole('button', { name: 'Exit fullscreen' })
    expect(exit.querySelector('svg')?.innerHTML).not.toBe(enterIcon)
    act(() => receive?.(false))
    expect(screen.getByRole('button', { name: 'Enter fullscreen' }).querySelector('svg')?.innerHTML).toBe(enterIcon)
  })

  it('uses the session timer as the model for the project and day timers in the title row', async () => {
    world = { sessions: [row({ label: 'api-limits' })], time: { running: [], project: { harbor: 80 }, total: 185, working: ['harbor'] } }
    const sent: unknown[] = []
    ;(window as unknown as { spWindow: unknown }).spWindow = { postMessage: (m: unknown) => sent.push(m) }
    page()
    const project = await screen.findByRole('button', { name: /Project timer.*harbor.*1:20/ })
    const day = await screen.findByRole('button', { name: /Total timer.*3:05/ })
    const group = project.closest('[data-timer-group]')!
    expect(group.closest('[data-window-title]')).toBeTruthy()
    expect(Array.from(group.children, (item) => item.getAttribute('data-timer-kind'))).toEqual(['session', 'project', 'total'])
    expect(project.textContent).toBe('1:20')
    expect(project.querySelector('[data-project-timer-dot]')).toBeTruthy()
    expect(day.textContent).toBe('Σ3:05')
    expect(project.dataset.timer).toBe('counting')
    fireEvent.click(project)
    expect(sent).toContainEqual({ op: 'open', url: `${window.location.origin}/time` })
  })

  it('draws no project or day timer when the server has no time routes', async () => {
    world = { sessions: [row({ label: 'api-limits' })] }
    page()
    await screen.findAllByRole('tab')
    expect(screen.queryByRole('button', { name: /^(Project|Total) timer/ })).toBeNull()
  })

  it('persists timer order, visibility and work-time sources', async () => {
    world = { sessions: [row({ label: 'api-limits' })], time: { running: [], project: { harbor: 5 }, total: 12, totalAgent: 45 } }
    const view = page()
    await screen.findByRole('button', { name: /Total timer.*0:12/ })
    fireEvent.click(screen.getByRole('button', { name: 'Window settings' }))
    const settings = screen.getByRole('complementary', { name: 'Window settings' })
    fireEvent.click(within(settings).getByText('Timers'))
    fireEvent.click(within(settings).getByRole('button', { name: 'Move Total timer up' }))
    fireEvent.click(within(settings).getByRole('button', { name: 'Move Total timer up' }))
    const group = screen.getByRole('button', { name: /Total timer.*0:12/ }).closest('[data-timer-group]')!
    expect(Array.from(group.children, (item) => item.getAttribute('data-timer-kind'))).toEqual(['total', 'session', 'project'])
    fireEvent.change(within(settings).getByLabelText('Project timer'), { target: { value: 'off' } })
    fireEvent.change(within(settings).getByLabelText('Total timer'), { target: { value: 'agents' } })
    fireEvent.click(within(settings).getByRole('checkbox', { name: 'Session timer' }))
    const day = await screen.findByRole('button', { name: /Total timer.*0:45.*Agent work time/ })
    expect(day.closest('[data-timer-group]')?.children).toHaveLength(1)
    view.unmount()
    page()
    const restored = await screen.findByRole('button', { name: /Total timer.*0:45.*Agent work time/ })
    expect(restored.closest('[data-timer-group]')?.children).toHaveLength(1)
    expect(JSON.parse(localStorage.getItem('sp-aqua-window-layout')!).timerOrder).toEqual(['total', 'session', 'project'])
  })

  it('shows sleep and wake only when the server knows sleep', async () => {
    const a = row({ label: 'calendar-overlap' })
    world = { sessions: [a] }
    const one = page()
    fireEvent.contextMenu((await screen.findAllByRole('tab'))[0]!)
    expect(screen.queryByRole('menuitem', { name: /Sleep/ })).toBeNull()
    one.unmount()
    world = { sessions: [{ ...a, asleep: false }] }
    page()
    fireEvent.contextMenu((await screen.findAllByRole('tab'))[0]!)
    fireEvent.click(screen.getByRole('menuitem', { name: /Sleep/ }))
    await waitFor(() => expect(posts.find(([p]) => p === `/api/terminal/sessions/${a.id}/sleep`)).toBeTruthy())
  })
})

describe('the tab strip of tk_a9306fb1', () => {
  const chat = (p: Record<string, unknown> = {}) => ({ name: '', tool: 'claude-code', tasks_done: 0, tasks_all: 0, branches: 0, ctx_pct: null, ctx_size: null, ctx_at: '', ...p })
  const tabTexts = () => within(screen.getByRole('tablist', { name: 'Chats' })).getAllByRole('tab').map((x) => x.querySelector('[data-tab-title]')?.textContent ?? x.textContent)

  it('a tab is titled with the chat\'s own name: the program\'s title, else the chat\'s name, never the project', async () => {
    const a = row({ label: 'claude' })
    const b = row({ label: 'harbor', kind: 'shell' })
    const c = row({ label: 'claude' })
    world = { sessions: [a, b, c], tabs: {
      [a.id]: { title: 'hbr-2611-17', agent_id: 'cc-a', chat: chat({ name: 'Booking emails' }) },
      [b.id]: { title: '', agent_id: '', chat: null },
      [c.id]: { title: '', agent_id: 'cc-c', chat: chat({ name: 'Pricing page copy' }) },
    } }
    page()
    await waitFor(() => expect(tabTexts()).toEqual(['hbr-2611-17', 'harbor', 'Pricing page copy']))
  })

  it('the title the program sets in the terminal in front (OSC) shows at once; the operator\'s rename wins over it', async () => {
    const a = row({ label: 'claude' })
    world = { sessions: [a], tabs: { [a.id]: { title: '', agent_id: 'cc-a', chat: chat({ name: 'from SP' }) } } }
    page()
    await waitFor(() => expect(tabTexts()).toEqual(['from SP']))
    fireEvent.click(screen.getByTestId('osc'))
    await waitFor(() => expect(tabTexts()).toEqual(['hbr-2611-18']))
    // double click: rename in place; Enter saves and marks the name as the operator's
    fireEvent.doubleClick(within(screen.getByRole('tablist', { name: 'Chats' })).getAllByRole('tab')[0]!)
    const input = screen.getByRole('textbox', { name: 'Name' }) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'my name' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(posts.find(([p, b]) => p === `/api/terminal/sessions/${a.id}/rename` && (b as { label: string }).label === 'my name')).toBeTruthy())
    expect(JSON.parse(localStorage.getItem('sp-term-named') ?? '[]')).toContain(a.id)
  })

  it('held Alt shows each tab\'s facts and a ×; releasing Alt or leaving the window brings the tabs back', async () => {
    const a = row({ label: 'claude', state: 'waiting', last_output: Date.now() / 1000 - 12 * 60 })
    world = { sessions: [a], tabs: { [a.id]: { title: 'hbr', agent_id: 'cc-a', chat: chat({ tasks_done: 1, tasks_all: 2, branches: 3 }) } } }
    const { container } = page()
    await waitFor(() => expect(tabTexts()).toEqual(['hbr']))
    vi.spyOn(document, 'hasFocus').mockReturnValue(true)
    fireEvent.keyDown(window, { key: 'Alt', code: 'AltLeft', altKey: true })
    const facts = await waitFor(() => { const el = container.querySelector('[data-alt="b"]'); expect(el).toBeTruthy(); return el! })
    expect(facts.textContent).toContain('1/2')
    expect(facts.textContent).toContain('3')
    expect(facts.textContent).toMatch(/12 min/)
    expect(screen.getByRole('button', { name: 'Close the tab hbr' })).toBeTruthy()
    fireEvent.keyUp(window, { key: 'Alt', code: 'AltLeft' })
    await waitFor(() => expect(container.querySelector('[data-alt="b"]')).toBeNull())
    fireEvent.keyDown(window, { key: 'Alt', code: 'AltLeft', altKey: true })
    await waitFor(() => expect(container.querySelector('[data-alt="b"]')).toBeTruthy())
    fireEvent.blur(window)
    await waitFor(() => expect(container.querySelector('[data-alt="b"]')).toBeNull())
  })

  it('the strip over each tab draws dots: closed tasks, context, waiting (tab state «dots»)', async () => {
    localStorage.setItem('sp-term-tabstate', 'dots')
    const a = row({ label: 'claude' })
    world = { sessions: [a], tabs: { [a.id]: { title: 'hbr', agent_id: 'cc-a', chat: chat({ tasks_done: 2, tasks_all: 2, ctx_pct: 90 }) } } }
    const { container } = page()
    await waitFor(() => expect(container.querySelector('[data-strip="c"] [data-part="closed"]')?.getAttribute('data-dots')).toBe('5'))
    expect(container.querySelector('[data-part="context"]')?.getAttribute('data-dots')).toBe('5')
    expect(container.querySelector('[data-part="waiting"]')?.getAttribute('data-dots')).toBe('0')
  })

  it('by default each tab draws six dots, the chat\'s last six hours (tk_d2e11125); a waiting chat warms them', async () => {
    const hour = (h: number, msgs: number) => ({ start: `2026-11-18T${h}:00:00`, end: `2026-11-18T${h + 1}:00:00`, msgs, commits: 0, tasks: 0, tokens: 0 })
    const rhythm = { period_min: 60, periods: [11, 12, 13, 14, 15, 16].map((h, i) => hour(h, i * 6)) }
    const a = row({ label: 'claude' })
    const b = row({ label: 'claude', state: 'waiting', last_output: Date.now() / 1000 - 25 * 60 })
    world = { sessions: [a, b], tabs: {
      [a.id]: { title: 'busy', agent_id: 'cc-a', chat: chat({ rhythm }) },
      [b.id]: { title: 'waits', agent_id: 'cc-b', chat: chat({ rhythm }) },
    } }
    const { container } = page()
    const dotsOf = (sid: string) => [...container.querySelectorAll(`[data-tab="${sid}"] [data-tabstate="rhythm"] [data-dot]`)]
    await waitFor(() => expect(dotsOf(a.id).map((d) => d.getAttribute('data-v'))).toEqual(['0.00', '0.20', '0.40', '0.60', '0.80', '1.00']))
    expect(container.querySelector('[data-strip="c"]')).toBeNull()
    expect(container.querySelector(`[data-tab="${a.id}"] [data-tabstate="rhythm"]`)?.getAttribute('data-warm')).toBe('0.00')
    expect(container.querySelector(`[data-tab="${b.id}"] [data-tabstate="rhythm"]`)?.getAttribute('data-warm')).toBe('2.00')
    expect(container.querySelector(`[data-tab="${a.id}"] [data-tabstate="rhythm"]`)?.getAttribute('title')).toContain('16:00–17:00 · 30 messages')
  })

  it('"+": a plain click opens a plain shell in the project (tk_e7649e7c); Ctrl+click opens the list, 1–9 pick, Esc closes', async () => {
    const a = row({ label: 'claude', program: 'codex' })
    world = { sessions: [a], tabs: { [a.id]: { title: 'hbr', agent_id: 'cc-a', chat: chat({ tool: 'codex' }) } } }
    page()
    await waitFor(() => expect(tabTexts()).toEqual(['hbr']))
    const plus = screen.getByRole('button', { name: 'New terminal' })
    fireEvent.click(plus)
    await waitFor(() => expect(posts.filter(([p]) => p === '/api/terminal/sessions')).toHaveLength(1))
    const [, shell] = posts.find(([p]) => p === '/api/terminal/sessions')! as [string, { role: string; project: string; command?: string }]
    expect(shell).toMatchObject({ kind: 'shell', role: 'shell', project: 'harbor' })
    expect(shell.command).toBeUndefined()
    expect(screen.queryByRole('menu', { name: 'Open a new terminal' })).toBeNull()

    fireEvent.click(plus, { ctrlKey: true })
    const menu = screen.getByRole('menu', { name: 'Open a new terminal' })
    expect(within(menu).getByRole('menuitem', { name: /New chat in its own worktree/ }).hasAttribute('disabled')).toBe(true)
    // the installed agents only (the stub: Claude Code and Codex)
    await waitFor(() => expect(within(menu).getAllByRole('menuitem').map((x) => x.getAttribute('data-item')).filter(Boolean))
      .toEqual(['shell', 'agent:claude', 'agent:codex', 'server', 'branch', 'resume', 'task', 'worktree']))
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('menu', { name: 'Open a new terminal' })).toBeNull())

    fireEvent.contextMenu(plus, { ctrlKey: true, button: 2 })
    expect(screen.getByRole('menu', { name: 'Open a new terminal' })).toBeTruthy()
    expect(posts.filter(([p]) => p === '/api/terminal/sessions')).toHaveLength(1)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('menu', { name: 'Open a new terminal' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Choose what to open' }))
    posts.length = 0
    fireEvent.keyDown(window, { key: '3' })
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/sessions' && (b as { command: string }).command === 'codex')).toBeTruthy())
    expect(screen.queryByRole('menu', { name: 'Open a new terminal' })).toBeNull()

    // alt+N opens the list; Ctrl+Shift+T opens a shell at once
    key('KeyN', { alt: true })
    expect(screen.getByRole('menu', { name: 'Open a new terminal' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    posts.length = 0
    key('KeyT', { ctrl: true, shift: true })
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/sessions' && (b as { role: string }).role === 'shell')).toBeTruthy())
  })

  it('the left sidebar: «New terminal» opens a shell, its "⌄" the same list (tk_e7649e7c)', async () => {
    const a = row({ label: 'claude' })
    world = { sessions: [a] }
    page()
    await screen.findByRole('tablist', { name: 'Chats' })
    key('BracketLeft', { alt: true })
    const nav = await screen.findByRole('navigation', { name: 'Workspaces' })
    expect(within(nav).queryByRole('button', { name: /^New chat/ })).toBeNull()
    posts.length = 0
    fireEvent.click(within(nav).getByRole('button', { name: 'New terminal' }))
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/sessions' && (b as { role: string }).role === 'shell' && (b as { project: string }).project === 'harbor')).toBeTruthy())
    fireEvent.click(within(nav).getByRole('button', { name: 'Choose what to open' }))
    const menu = screen.getByRole('menu', { name: 'Open a new terminal' })
    expect(within(menu).getByRole('menuitem', { name: /^Plain terminal/ })).toBeTruthy()
    expect(within(menu).getByRole('menuitem', { name: /^Dev server/ })).toBeTruthy()
  })

  it('every workspace: projects without terminals as quiet tiles, «New terminal» there, and a new workspace (tk_2ac8748d)', async () => {
    world = { sessions: [row({ label: 'calendar-overlap' })], groups: [] }
    const { container } = page()
    await screen.findByRole('tablist', { name: 'Chats' })
    key('ArrowUp', { ctrl: true, shift: true })
    key('ArrowUp', { ctrl: true, shift: true })
    expect(container.querySelector('[data-level]')?.getAttribute('data-level')).toBe('all')
    const idle = [...container.querySelectorAll('section[data-idle]')].map((x) => x.getAttribute('aria-label'))
    expect(idle).toEqual(['kelp', 'lumen'])
    const kelp = screen.getByRole('region', { name: 'kelp' })
    expect(within(kelp).getByText('no terminals')).toBeTruthy()
    posts.length = 0
    fireEvent.click(within(kelp).getByRole('button', { name: 'New terminal' }))
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/sessions' && (b as { role: string }).role === 'shell' && (b as { project: string }).project === 'kelp')).toBeTruthy())
    // a click on the name opens the empty workspace
    fireEvent.click(within(screen.getByRole('region', { name: 'lumen' })).getByRole('button', { name: /lumen/ }))
    await waitFor(() => expect(container.querySelector('[data-level]')?.getAttribute('data-level')).toBe('chat'))
    expect(screen.getByText('No terminal in this workspace.')).toBeTruthy()
    // a new workspace, named on its tile
    key('ArrowUp', { ctrl: true, shift: true }); key('ArrowUp', { ctrl: true, shift: true })
    const tile = screen.getByRole('region', { name: 'New workspace' })
    fireEvent.click(within(tile).getByRole('button', { name: /New workspace/ }))
    fireEvent.change(within(tile).getByRole('textbox', { name: 'Group name' }), { target: { value: 'Launch' } })
    fireEvent.click(within(tile).getByRole('button', { name: 'Make the workspace' }))
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/groups' && (b as { name: string }).name === 'Launch')).toBeTruthy())
  })

  it('the list branches the chat, starts one from a board task, resumes a closed one', async () => {
    const a = row({ label: 'claude' })
    world = { sessions: [a], tabs: { [a.id]: { title: 'hbr', agent_id: 'cc-a', chat: chat() } } }
    page()
    await waitFor(() => expect(tabTexts()).toEqual(['hbr']))
    const open = () => fireEvent.click(screen.getByRole('button', { name: 'Choose what to open' }))
    open()
    posts.length = 0
    fireEvent.click(screen.getByRole('menuitem', { name: /^Branch the current chat/ }))
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/sessions' && (b as { command: string }).command.includes('--fork-session'))).toBeTruthy())
    open()
    fireEvent.click(screen.getByRole('menuitem', { name: /^New chat from a board task/ }))
    expect(screen.queryByRole('menuitem', { name: /tk_2/ })).toBeNull()
    fireEvent.click(await screen.findByRole('menuitem', { name: /tk_1 · Fix the bill/ }))
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/sessions' && (b as { kind: string; task_id: string }).kind === 'start' && (b as { task_id: string }).task_id === 'tk_1')).toBeTruthy())
    open()
    fireEvent.click(screen.getByRole('menuitem', { name: /^Resume a sleeping chat/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /old chat/ }))
    await waitFor(() => expect(posts.find(([p, b]) => p === '/api/terminal/sessions' && (b as { kind: string; agent: string }).kind === 'resume' && (b as { agent: string }).agent === 'cc-old')).toBeTruthy())
  })
})

describe('switching workspaces (tk_f7a924a6)', () => {
  it('a workspace opens on the tab last in front there, also after a reload', async () => {
    const a1 = row({ label: 'a-one' })
    const a2 = row({ label: 'a-two' })
    const b1 = row({ project: 'kelp', label: 'b-one' })
    world = { sessions: [a1, a2, b1] }
    const first = page()
    // it opens on kelp (the newest terminal); harbor first opens on its first tab
    fireEvent.click(await screen.findByRole('button', { name: /\+1/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /harbor/ }))
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(a1.id))
    fireEvent.click(within(screen.getByRole('tablist', { name: 'Chats' })).getByRole('tab', { name: /a-two/ }))
    expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(a2.id)
    // to kelp through the folded "+1", then back to harbor the same way
    fireEvent.click(screen.getByRole('button', { name: /\+1/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /kelp/ }))
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(b1.id))
    fireEvent.click(screen.getByRole('button', { name: /\+1/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /harbor/ }))
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(a2.id))
    // after a reload the remembered tab per workspace still holds
    fireEvent.click(screen.getByRole('button', { name: /\+1/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /kelp/ }))
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(b1.id))
    first.unmount()
    // the window reopens on kelp's tab; harbor still opens on a-two
    page()
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(b1.id))
    fireEvent.click(await screen.findByRole('button', { name: /\+1/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /harbor/ }))
    await waitFor(() => expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(a2.id))
  })

  it('remembers an empty project selected in the sidebar', async () => {
    world = { sessions: [row({ label: 'harbor-one' })] }
    const first = page()
    fireEvent.click(await screen.findByRole('button', { name: 'Left sidebar' }))
    const sidebar = within(screen.getByRole('navigation', { name: 'Workspaces' }))
    fireEvent.click(sidebar.getByRole('button', { name: /projects without terminals/ }))
    fireEvent.click(sidebar.getByRole('button', { name: 'lumen' }))
    expect(screen.getByText('No terminal in this workspace.')).toBeTruthy()
    first.unmount()
    page()
    expect(await screen.findByText('No terminal in this workspace.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Workspaces' })).toHaveTextContent('lumen')
  })
})

describe('health and time in the window (tk_810245f2)', () => {
  it('one small time label in the title row, also when the row is folded; only in the main window', async () => {
    world = { sessions: [row({ label: 'calendar-overlap' })], time: { running: [], project: { harbor: 10 }, total: 20 } }
    const { container, unmount } = page()
    await screen.findByRole('tablist', { name: 'Chats' })
    await waitFor(() => expect(container.querySelector('[data-health-label]')).toBeTruthy())
    key('KeyT', { alt: true })
    await waitFor(() => expect(container.querySelector('[data-folded]')).toBeTruthy())
    expect(container.querySelector('[data-health-label]')).toBeTruthy()
    unmount()
    const a = row({ label: 'solo' })
    world = { sessions: [a], time: { running: [], project: {}, total: 0 } }
    const other = page(`?detached=${a.id}`)
    await screen.findByTestId('screen')
    expect(other.container.querySelector('[data-health-label]')).toBeNull()
  })
})
