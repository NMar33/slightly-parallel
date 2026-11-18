import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ILinkProvider, Terminal } from 'xterm'

import type { ScreenApi } from '../Screen'
import { resetKept } from './data'
import { MessageLayer, type LayerSlot } from './MessageMenu'

/*
 * The record cards over the terminal (tk_b3edbd84): a row of the terminal
 * names a record, its link opens the card, the card reads the record by
 * its page's route and acts by the operator's.
 */

const SHA = '47feacd0f0e1d2c3b4a5968778695a4b3c2d1e0f'

let posts: Array<[string, Record<string, unknown>]>
let gets: string[]
let opened: string[]
let clip: string[]
let terminals: Array<Record<string, unknown>>

function answer(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
}

const DECISION = {
  metadata: { id: 'dc_0badc0de', decision_text: 'x', weight: 'major', created_date: '2611-18', created_time: '10:42:00', project: 'harbor', agent_id: 'cc-676175ea' },
  text: { decision: 'Hashes are checked before they underline', why: 'A hex word is not a commit.', alternatives: ['Underline every hex run — rejected: false links'] },
}
const CARD = { id: 'pu_1a2b3c4d', project: 'harbor', at: '2026-11-18T10:00:00', message: '', text: 'Records open in place in the terminal', context: 'Why it matters: fewer windows',
  tasks: [{ id: 'tk_1' }], notes: [], cores: [], commits: [{ sha: 'a' }], images: [{ url: 'x' }], links: [], files: [], placements: [] }
const CORE = { id: 'cr_00ff00aa', project: 'harbor', name: 'Terminal window', type: 'interface', reason: 'Where the operator works', status: 'view',
  notes: [{ id: 'cn_1', at: '2026-11-17T10:00:00', author: 'operator', text: 'Menus came first', comment: '' }],
  tasks: [{ id: 'tk_a9306fb1', title: 'Message menu', status: 'done', archived_at: '' }] }
const SKILL = { metadata: { id: 'sk_abcdef01', name: 'write-a-note', description: 'Write a note for the operator', status: 'active' },
  skill: { current: { n: 2, skill_md: '---\nname: write-a-note\ndescription: Write a note for the operator\n---\n# Steps\n\nWrite **the note** first.' }, installs: [{ project: 'other', status: 'fresh' }] } }
const AGENT = { agent: { agent_id: 'cc-676175ea', agent_name: 'messages', tool: 'claude-code', session_ref: 'abc-123', project: 'harbor', last_active: '2026-11-18T10:00:00', message_count: 12 } }
const TOPIC = { id: 'ep_12345678', project: 'harbor', name: 'Sandbox', title: 'How do I run the sandbox?', what: 'The sandbox server.', state: 'active',
  stops: [{ id: 's1', at: '2026-11-18T09:00:00', author: 'cc-1', text: 'Started it on 8133', task_id: '', turn: 1 }],
  shots: [{ id: 'sh1', src: '/api/entrypoints/shots/sh1/file', caption: 'Home' }], open_tasks: 1 }
const COMMIT = { sha: SHA, short: SHA.slice(0, 7), project: 'harbor', subject: 'Records open in place', author: 'nick', at: '2026-11-18T10:00:00',
  files: [{ path: 'frontend/a.ts', add: 10, del: 2 }], files_n: 1, add: 10, del: 2, tasks: ['tk_b3edbd84'], agent: 'cc-676175ea' }

beforeEach(() => {
  posts = []; gets = []; opened = []; clip = []; terminals = []
  localStorage.clear()
  resetKept()
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (s: string) => { clip.push(s) } }, configurable: true })
  vi.spyOn(window, 'open').mockImplementation((u?: string | URL) => { opened.push(String(u)); return null })
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const path = String(url)
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body ?? '{}')) as Record<string, unknown>
      posts.push([path, body])
      if (path === '/api/terminal/sessions') return answer({ session: { id: 't-new', label: 'x', project: 'harbor' } })
      return answer({ ok: true })
    }
    gets.push(path)
    if (path === '/api/decisions/dc_0badc0de') return answer(DECISION)
    if (path === '/api/publishing/cards/pu_1a2b3c4d') return answer(CARD)
    if (path === '/api/cores/cr_00ff00aa') return answer(CORE)
    if (path === '/api/skills/sk_abcdef01') return answer(SKILL)
    if (path === '/api/agent/cc-676175ea') return answer(AGENT)
    if (path.startsWith('/api/tasks/mentions/by-agent')) return answer({ agents: { 'cc-676175ea': [{ task_id: 'tk_b3edbd84', title: 'Clickable ids', at: '2026-11-18T10:00' }] } })
    if (path === '/api/terminal/sessions') return answer({ sessions: terminals })
    if (path === '/api/terminal/tabs') return answer({ tabs: {} })
    if (path === '/api/terminal/state') return answer({ enabled: true })
    if (path === '/api/terminal/branch/cc-676175ea') return answer({ command: 'cd /w && claude -r abc-123 --fork-session', project: 'harbor', cwd: '/w', name: 'messages' })
    if (path.startsWith('/api/entrypoints/desk')) return answer({ topics: [TOPIC], projects: ['harbor'] })
    if (path.startsWith('/api/git/commit?repo=harbor&sha=47feacd0')) return answer(path.includes('diff=1') ? { ...COMMIT, diff: 'diff --git a/frontend/a.ts b/frontend/a.ts\n+added line\n-removed line', diff_cut: false } : COMMIT)
    if (path.startsWith('/api/tasks/tk_')) return answer({ metadata: { id: 'tk_b3edbd84', title: 'Clickable ids', status: 'doing', project: 'harbor' } })
    return answer({ detail: 'Not Found' }, 404)
  }))
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); document.body.innerHTML = '' })

interface Rig { slot: LayerSlot; said: string[]; went: string[] }

function rig(project = 'harbor', agentId = ''): Rig {
  const r: Rig = { slot: null as unknown as LayerSlot, said: [], went: [] }
  const api: ScreenApi = { find: () => {}, range: () => {}, copyScreen: () => {}, copyLast: () => {}, rowsAt: async () => null, selection: () => '', ownMenu: () => {},
    editor: () => 'code', openPath: (p) => r.went.push(`path:${p.path}:${p.line}`) }
  function Fake({ slot }: { slot: LayerSlot }) {
    r.slot = slot
    slot.bind(api)
    return <div data-testid="screen" />
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MessageLayer agentId={agentId} project={project} say={(s) => r.said.push(s)} refocus={() => {}} goTo={(sid) => r.went.push(sid)}>
        {(slot) => <Fake slot={slot} />}
      </MessageLayer>
    </QueryClientProvider>,
  )
  return r
}

type Link = { text: string; activate: (e: MouseEvent) => void }

/** One row of a terminal, the layer's link provider on it: the links it gives. */
async function linksOf(r: Rig, text: string): Promise<Link[]> {
  let provider: ILinkProvider | null = null
  const cells = [...text]
  const line = { length: cells.length, getCell: (x: number) => ({ getWidth: () => 1, getChars: () => cells[x] ?? '' }) }
  const term = {
    buffer: { active: { viewportY: 0, getLine: () => line } },
    registerLinkProvider: (p: ILinkProvider) => { provider = p; return { dispose: () => {} } },
    element: document.createElement('div'), rows: 1, cols: cells.length,
  } as unknown as Terminal
  document.body.appendChild(term.element!)
  act(() => r.slot.hooks.terminal?.(term, 'live'))
  return new Promise((res) => provider!.provideLinks(1, (l) => res((l ?? []) as never)))
}

async function open(r: Rig, row: string, id: string): Promise<HTMLElement> {
  const links = await linksOf(r, row)
  const link = links.find((l) => l.text === id)
  expect(link, `${id} is a link in «${row}»`).toBeTruthy()
  act(() => link!.activate(new MouseEvent('mouseup', { clientX: 50, clientY: 5 })))
  return screen.findByRole('dialog')
}

// The preference a core's link sets (persistPref) reaches the server late, in a later test.
const writes = () => posts.filter(([p]) => p !== '/api/prefs')

const button = (card: HTMLElement, name: string | RegExp) => within(card).getByRole('button', { name })

describe('the record cards', () => {
  it('a decision: what was decided, why, the rejected option, weight and day; opens on the Decisions page', async () => {
    const r = rig()
    const card = await open(r, 'Решение dc_0badc0de записано', 'dc_0badc0de')
    expect(card).toHaveAccessibleName('Decision dc_0badc0de')
    await within(card).findByText('Hashes are checked before they underline')
    expect(within(card).getByText('A hex word is not a commit.')).toBeTruthy()
    expect(within(card).getByText('Underline every hex run')).toBeTruthy()
    expect(within(card).getByText('major')).toBeTruthy()
    expect(within(card).getByText(/18\.11\.2026 10:42/)).toBeTruthy()
    fireEvent.click(button(card, 'Open on the Decisions page'))
    expect(opened).toEqual([`${window.location.origin}/decisions#project=harbor&month=2026-11&day=2611-18`])
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(writes()).toEqual([])
  })

  it('a Publish card: the text, the context and how much is attached; Escape closes it', async () => {
    const r = rig()
    const card = await open(r, '#publish → pu_1a2b3c4d', 'pu_1a2b3c4d')
    await within(card).findByText('Records open in place in the terminal')
    expect(within(card).getByText('Why it matters: fewer windows')).toBeTruthy()
    expect(within(card).getByText(/3 attachments/)).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => { void 0 })
    const again = await open(r, '#publish → pu_1a2b3c4d', 'pu_1a2b3c4d')
    fireEvent.click(button(again, 'Open on the Publish page'))
    expect(opened.at(-1)).toBe(`${window.location.origin}/publish#project=harbor`)
  })

  it('a core: its notes and tasks; a note is added by the operator\'s route; it opens on Architecture › cores', async () => {
    const r = rig()
    const card = await open(r, 'ядро cr_00ff00aa', 'cr_00ff00aa')
    await within(card).findByText('Terminal window')
    expect(within(card).getByText('Menus came first')).toBeTruthy()
    expect(within(card).getByRole('button', { name: 'tk_a9306fb1' })).toBeTruthy()
    fireEvent.click(button(card, 'Add a note'))
    fireEvent.change(within(card).getByRole('textbox', { name: 'The note' }), { target: { value: 'Ids open cards now' } })
    fireEvent.click(button(card, 'Save'))
    await waitFor(() => expect(posts).toContainEqual(['/api/cores/cr_00ff00aa/notes', { actor: 'operator', text: 'Ids open cards now' }]))
    await waitFor(() => expect(r.said).toContain('Note added to Terminal window'))
    fireEvent.click(button(card, 'Open in Architecture › cores'))
    expect(opened.at(-1)).toBe(`${window.location.origin}/architecture#project=harbor&core=cr_00ff00aa`)
    expect(localStorage.getItem('sp-architecture-tab-mode')).toBe('cores')
  })

  it('a task id inside a card opens that task\'s menu', async () => {
    const r = rig()
    const card = await open(r, 'ядро cr_00ff00aa', 'cr_00ff00aa')
    fireEvent.click(await within(card).findByRole('button', { name: 'tk_a9306fb1' }))
    await waitFor(() => expect(screen.getByRole('menu')).toHaveAccessibleName('tk_a9306fb1'))
  })

  it('a skill: SKILL.md rendered; installs into the terminal\'s project by the Skills page\'s route', async () => {
    const r = rig()
    const card = await open(r, 'скилл sk_abcdef01', 'sk_abcdef01')
    expect(card).toHaveAccessibleName('Skill sk_abcdef01')
    await within(card).findByRole('heading', { name: 'Steps' })
    expect(within(card).getByText('the note').tagName).toBe('STRONG')
    expect(within(card).getByText('Installed in: other')).toBeTruthy()
    fireEvent.click(button(card, 'Install in harbor'))
    await waitFor(() => expect(posts).toContainEqual(['/api/skills/sk_abcdef01/install', { project: 'harbor', actor: 'operator' }]))
    await waitFor(() => expect(r.said).toContain('write-a-note installed in harbor'))
  })

  it('an entry point: its question, where it stopped and its shots', async () => {
    const r = rig()
    const card = await open(r, 'точка ep_12345678', 'ep_12345678')
    await within(card).findByText('Sandbox')
    expect(within(card).getByText('How do I run the sandbox?')).toBeTruthy()
    expect(within(card).getByText('Started it on 8133')).toBeTruthy()
    expect(within(card).getByRole('img', { name: 'Home' })).toHaveAttribute('src', '/api/entrypoints/shots/sh1/file')
    fireEvent.click(button(card, 'Open on the Entry points page'))
    expect(opened.at(-1)).toBe(`${window.location.origin}/entrypoints?topic=ep_12345678`)
  })

  it('a chat with no terminal open: its tasks; Resume opens it as the left sidebar does', async () => {
    const r = rig()
    const card = await open(r, 'чат cc-676175ea ждёт', 'cc-676175ea')
    await within(card).findByText('messages')
    expect(within(card).getByText('No terminal of this chat is open.')).toBeTruthy()
    await within(card).findByRole('button', { name: 'tk_b3edbd84' })
    expect(within(card).queryByRole('button', { name: 'Go to its tab' })).toBeNull()
    fireEvent.click(button(card, 'Resume'))
    await waitFor(() => expect(posts).toContainEqual(['/api/terminal/sessions', { kind: 'resume', agent: 'cc-676175ea', role: 'chat', actor: 'operator' }]))
    await waitFor(() => expect(r.went).toEqual(['t-new']))
  })

  it('a chat with its terminal open: its state, «Go to its tab»; a branch opens in a window of its own', async () => {
    terminals = [{ id: 't-7', agent_id: 'cc-676175ea', state: 'waiting', kind: 'resume', label: 'messages', project: 'harbor' }]
    const r = rig()
    const card = await open(r, 'чат cc-676175ea ждёт', 'cc-676175ea')
    await within(card).findByText('your turn')
    expect(within(card).queryByRole('button', { name: 'Resume' })).toBeNull()
    fireEvent.click(button(card, 'Go to its tab'))
    expect(r.went).toEqual(['t-7'])
    const again = await open(r, 'чат cc-676175ea ждёт', 'cc-676175ea')
    fireEvent.click(await within(again).findByRole('button', { name: 'Branch into a new window' }))
    await waitFor(() => expect(posts).toContainEqual(['/api/terminal/sessions', { kind: 'shell', project: 'harbor', label: 'messages ⑂', command: 'cd /w && claude -r abc-123 --fork-session', role: 'chat', actor: 'operator' }]))
    await waitFor(() => expect(opened.at(-1)).toMatch(/\/term\?detached=t-new$/))
    expect(gets).toContain('/api/terminal/branch/cc-676175ea')
  })

  it('a commit of the project: subject, files, its Task: line; «Show the changes» reads the diff; copy the hash', async () => {
    const r = rig()
    const card = await open(r, `[master ${SHA.slice(0, 8)}] Records open in place`, SHA.slice(0, 8))
    expect(card).toHaveAccessibleName(/^Commit /)
    await within(card).findByText('Records open in place')
    expect(within(card).getByTestId('commit-files').textContent).toContain('frontend/a.ts+10−2')
    expect(within(card).getByRole('button', { name: 'tk_b3edbd84' })).toBeTruthy()
    fireEvent.click(button(card, 'Show the changes'))
    const diff = await within(card).findByRole('region', { name: 'Changes' })
    await within(diff).findByText('+added line')
    expect(gets).toContain(`/api/git/commit?repo=harbor&sha=${SHA.slice(0, 8)}&diff=1`)
    fireEvent.click(button(card, 'Copy the hash'))
    await waitFor(() => expect(clip).toEqual([SHA]))
    expect(writes()).toEqual([])
  })

  it('a hash that is no commit of the project, and hex that is no hash, are never links; each hash is asked once', async () => {
    const r = rig()
    const row = `d3adbee1 ${SHA.slice(0, 8)} 676175ea-a3c6-4ae1-adcc-5abf2659566a v1.2.3 https://x.io/c/${SHA}`
    expect((await linksOf(r, row)).map((l) => l.text)).toEqual([SHA.slice(0, 8)])
    expect((await linksOf(r, row)).map((l) => l.text)).toEqual([SHA.slice(0, 8)])
    expect(gets.filter((g) => g.startsWith('/api/git/commit'))).toEqual([
      '/api/git/commit?repo=harbor&sha=d3adbee1', `/api/git/commit?repo=harbor&sha=${SHA.slice(0, 8)}`,
    ])
  })

  it('a terminal with no project underlines no hash and asks nothing', async () => {
    const r = rig('')
    expect((await linksOf(r, `x ${SHA.slice(0, 8)} dc_0badc0de`)).map((l) => l.text)).toEqual(['dc_0badc0de'])
    expect(gets.filter((g) => g.startsWith('/api/git/commit'))).toEqual([])
  })

  it('an id the server does not know says so', async () => {
    const r = rig()
    const card = await open(r, 'dc_ffffffff', 'dc_ffffffff')
    await within(card).findByText('No such decision')
  })
})

/* A right click on a link: a terminal of one row, ten pixels a cell, its screen under the pointer. */
function rightClickAt(r: Rig, text: string, want: string): boolean {
  const cells = [...text]
  const line = { length: cells.length, getCell: (x: number) => ({ getWidth: () => 1, getChars: () => cells[x] ?? '' }) }
  const el = document.createElement('div')
  el.className = 'xterm'
  const scr = document.createElement('div')
  scr.className = 'xterm-screen'
  scr.getBoundingClientRect = () => ({ left: 0, top: 0, width: cells.length * 10, height: 20, right: cells.length * 10, bottom: 20, x: 0, y: 0, toJSON: () => ({}) })
  el.appendChild(scr)
  document.body.appendChild(el)
  const term = { buffer: { active: { viewportY: 0, getLine: () => line } }, registerLinkProvider: () => ({ dispose: () => {} }), element: el, rows: 1, cols: cells.length } as unknown as Terminal
  act(() => r.slot.hooks.terminal?.(term, 'live'))
  const ev = new MouseEvent('contextmenu', { clientX: text.indexOf(want) * 10 + 15, clientY: 5 })
  Object.defineProperty(ev, 'target', { value: scr })
  let took = false
  act(() => { took = !!r.slot.hooks.contextMenu?.(ev) })
  return took
}

describe('a right click on a link', () => {
  const ROW = 'see https://example.com/a?b=1. card tk_b3edbd84 in src/app.ts:42 and plain words'

  it('a web address in a shell: copy it as printed, or open it', async () => {
    const r = rig('harbor', '')
    expect(rightClickAt(r, ROW, 'example.com')).toBe(true)
    const menu = await screen.findByRole('menu', { name: 'Link' })
    expect(within(menu).getAllByRole('menuitem').map((b) => b.textContent)).toEqual(['Copy the link', 'Open', 'Terminal menu…'])
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Copy the link' }))
    await waitFor(() => expect(clip).toEqual(['https://example.com/a?b=1']))
    expect(r.said).toEqual(['Link copied'])
    rightClickAt(r, ROW, 'example.com')
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Open' }))
    await waitFor(() => expect(opened).toEqual(['https://example.com/a?b=1']))
  })

  it('a task id: copy the id, copy its page\'s address, open its menu', async () => {
    const r = rig('harbor', '')
    rightClickAt(r, ROW, 'tk_b3edbd84')
    const menu = await screen.findByRole('menu', { name: 'Link' })
    expect(within(menu).getAllByRole('menuitem').map((b) => b.textContent)).toEqual(['Copy the link', 'Copy the page address', 'Open', 'Terminal menu…'])
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Copy the link' }))
    await waitFor(() => expect(clip).toEqual(['tk_b3edbd84']))
    rightClickAt(r, ROW, 'tk_b3edbd84')
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Copy the page address' }))
    await waitFor(() => expect(clip.at(-1)).toBe(`${window.location.origin}/kanban?task=tk_b3edbd84`))
    expect(r.said.at(-1)).toBe('Page address copied')
    rightClickAt(r, ROW, 'tk_b3edbd84')
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Open' }))
    await waitFor(() => expect(screen.getByRole('menu')).toHaveAccessibleName('tk_b3edbd84'))
  })

  it('a decision id: its page address is its project\'s and day\'s', async () => {
    const r = rig('harbor', '')
    rightClickAt(r, 'решение dc_0badc0de', 'dc_0badc0de')
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Copy the page address' }))
    await waitFor(() => expect(clip).toEqual([`${window.location.origin}/decisions#project=harbor&month=2026-11&day=2611-18`]))
  })

  it('a printed path: copy it, open it in the editor', async () => {
    const r = rig('harbor', '')
    rightClickAt(r, ROW, 'app.ts')
    fireEvent.click(within(await screen.findByRole('menu', { name: 'Link' })).getByRole('menuitem', { name: 'Copy the link' }))
    await waitFor(() => expect(clip).toEqual(['src/app.ts:42']))
    rightClickAt(r, ROW, 'app.ts')
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Open' }))
    await waitFor(() => expect(r.went).toEqual(['path:src/app.ts:42']))
  })

  it('no link in a shell: the screen\'s own menu, as before', () => {
    const r = rig('harbor', '')
    expect(rightClickAt(r, ROW, 'plain')).toBe(false)
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('in a chat: the link\'s items first, then the message\'s', async () => {
    const r = rig('harbor', 'cc-676175ea')
    rightClickAt(r, ROW, 'tk_b3edbd84')
    const menu = await screen.findByRole('menu')
    await waitFor(() => expect(menu).toHaveAccessibleName('Message not found in the chat record'))
    expect(within(menu).getAllByRole('menuitem').map((b) => b.textContent)).toEqual(['Copy the link', 'Copy the page address', 'Open', 'Copy', 'Terminal menu…'])
  })
})
