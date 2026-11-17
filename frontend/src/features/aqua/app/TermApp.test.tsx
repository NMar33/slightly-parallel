import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AquaSession } from './model'

// The live terminal is xterm on a socket: here a stub that says which terminal it is and types on request.
const mounted: string[] = []
vi.mock('../../terminal/Screen', () => ({
  Screen: ({ sid, onInput }: { sid: string; onInput?: (d: string) => void }) => {
    mounted.push(sid)
    return <button type="button" data-testid="screen" data-sid={sid} onClick={() => onInput?.('a')}>screen {sid}</button>
  },
}))

import { TermApp } from './TermApp'

let n = 0
const row = (p: Partial<AquaSession>): AquaSession => ({
  id: `t${++n}`, kind: 'resume', label: `chat ${n}`, project: 'harbor', cwd: '/w', command: '', agent_id: '', task_id: '',
  created: `2026-11-16T10:${String(n).padStart(2, '0')}`, backend: 'tmux', state: 'working', program: 'claude', last_output: 0, ...p,
})

interface World {
  enabled?: boolean
  sessions: AquaSession[]
  groups?: Array<{ id: string; name: string; color: number }> | null
  restore?: { needed: number; sessions: Array<{ id: string; label: string }> } | null
}
let world: World
const posts: Array<[string, unknown]> = []

function answer(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
}

beforeEach(() => {
  n = 0
  mounted.length = 0
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
      if (path === '/api/terminal/groups') return answer({ group: { id: 'g9', name: body.name, color: body.color } })
      if (path.endsWith('/capture')) return answer({ text: '$ make test\n41 passed' })
      return answer({ ok: true })
    }
    if (path === '/api/terminal/state') {
      return answer({ enabled: world.enabled ?? true, supported: true, token: 'tok', font_size: 13, scrollback: 1000, editor: '', agent: 'claude', projects: { harbor: '/h', kelp: '/k', lumen: '/l' } })
    }
    if (path === '/api/terminal/sessions') return answer({ sessions: world.sessions, counts: {} })
    if (path === '/api/terminal/groups') return world.groups ? answer({ groups: world.groups }) : answer({ detail: 'Not Found' }, 404)
    if (path === '/api/terminal/restore') return world.restore ? answer(world.restore) : answer({ detail: 'Not Found' }, 404)
    if (path.startsWith('/api/pins') || path.startsWith('/api/carries') || path.startsWith('/api/forks')) return answer({ items: [] })
    if (path.startsWith('/api/sessions')) return answer({ sessions: [] })
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

  it('at rest: the current workspace as tabs with state dots, the others folded behind +N with a waiting marker, one terminal mounted', async () => {
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
    // a sleeping chat has no terminal: a Wake in its place
    fireEvent.click(within(tabs).getByRole('tab', { name: /dusty/ }))
    expect(screen.queryByTestId('screen')).toBeNull()
    expect(screen.getByText(/dusty is asleep/)).toBeTruthy()
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
    expect(screen.getByTestId('screen').getAttribute('data-sid')).toBe(a.id)
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
    fireEvent.click(screen.getByRole('button', { name: 'New terminal (alt+N)' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Shell' }))
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
    expect(posts.find(([p]) => p === '/api/terminal/groups')![1]).toMatchObject({ name: 'Release week', color: 6 })
    expect(posts.find(([p]) => p === `/api/terminal/sessions/${a.id}/group`)![1]).toMatchObject({ group: 'g9' })
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
