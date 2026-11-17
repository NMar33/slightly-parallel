import { describe, expect, it } from 'vitest'

import {
  chordOf, deriveWorkspaces, detachUrl, foldTabs, isLive, laneOf, nextWaiting, parseView, placeSide, resolveWs, roleOf, seatBoth,
  cycleLevel, shownOf, stepIn, stepOut, tabsOf, tilesOf, wsIdOf, type AquaSession, type Group,
} from './model'

let n = 0
const row = (p: Partial<AquaSession>): AquaSession => ({
  id: `t${++n}`, kind: 'shell', label: 'x', project: 'harbor', cwd: '/w', command: '', agent_id: '', task_id: '',
  created: `2026-11-16T10:${String(n).padStart(2, '0')}`, backend: 'tmux', state: 'shell', program: '', last_output: 0, ...p,
})

describe('a terminal row read without the new fields', () => {
  it('is a chat when it carries an agent or a command, a shell otherwise, a server only when the server says so', () => {
    expect(roleOf(row({ kind: 'resume', agent_id: 'cc-1' }))).toBe('chat')
    expect(roleOf(row({ kind: 'shell', command: 'claude' }))).toBe('chat')
    expect(roleOf(row({ kind: 'shell' }))).toBe('shell')
    expect(roleOf(row({ kind: 'shell', role: 'server' }))).toBe('server')
  })

  it('shows asleep from either the flag or the state, and ended over the rest', () => {
    expect(shownOf(row({ asleep: true, state: 'waiting' }))).toBe('asleep')
    expect(shownOf(row({ state: 'asleep' }))).toBe('asleep')
    expect(shownOf(row({ state: 'ended' }))).toBe('ended')
    expect(shownOf(row({ state: 'running' }))).toBe('working')
    expect(shownOf(row({ state: 'shell' }))).toBe('idle')
  })
})

describe('the workspaces', () => {
  const groups: Group[] = [{ id: 'g1', name: 'Release week', color: 6 }]

  it('one per project, registered or named by a terminal, and one per group; a chat lives in exactly one', () => {
    const a = row({ project: 'harbor' })
    const b = row({ project: 'kelp', group: 'g1' })
    const c = row({ project: 'otter' })
    const ws = deriveWorkspaces([a, b, c], ['harbor', 'kelp', 'lumen'], groups)
    expect(ws.map((w) => w.id)).toEqual(['p:harbor', 'p:kelp', 'p:lumen', 'p:otter', 'g:g1'])
    expect(ws.find((w) => w.id === 'g:g1')!.sessions).toEqual([b])
    expect(ws.find((w) => w.id === 'p:kelp')!.sessions).toEqual([])
    expect(ws.flatMap((w) => w.sessions)).toHaveLength(3)
    expect(ws.find((w) => w.id === 'g:g1')!.color).toBe(6)
  })

  it('puts a chat whose group is unknown (no groups route, or a removed group) back in its project', () => {
    const b = row({ project: 'kelp', group: 'g9' })
    expect(wsIdOf(b, null)).toBe('p:kelp')
    expect(wsIdOf(b, groups)).toBe('p:kelp')
    expect(deriveWorkspaces([b], [], null).map((w) => w.id)).toEqual(['p:kelp'])
  })

  it('gives a project the same lane every time', () => {
    expect(laneOf('harbor')).toBe(laneOf('harbor'))
    expect(laneOf('harbor')).toBeGreaterThanOrEqual(1)
    expect(laneOf('harbor')).toBeLessThanOrEqual(8)
  })

  it('counts an empty group as live, an empty project not', () => {
    const ws = deriveWorkspaces([], ['harbor'], groups)
    expect(ws.filter(isLive).map((w) => w.id)).toEqual(['g:g1'])
  })
})

describe('the tab strip', () => {
  it('opens the current workspace, servers after the chats, and folds the others behind +N with a waiting marker', () => {
    const srv = row({ project: 'harbor', role: 'server' })
    const a = row({ project: 'harbor', kind: 'resume', agent_id: 'cc-a' })
    const b = row({ project: 'kelp', state: 'waiting', kind: 'resume', agent_id: 'cc-b' })
    const c = row({ project: 'otter' })
    const ws = deriveWorkspaces([srv, a, b, c], ['harbor', 'lumen'], null)
    const f = foldTabs(ws, 'p:harbor')
    expect(f.tabs.map((s) => s.id)).toEqual([a.id, srv.id])
    expect(f.folded.map((x) => [x.ws.id, x.count, x.waiting])).toEqual([['p:kelp', 1, 1], ['p:otter', 1, 0]])
    expect(f.anyWaiting).toBe(true)
    expect(foldTabs(ws, 'p:kelp').anyWaiting).toBe(false)
  })

  it('leaves out the terminals another window holds', () => {
    const a = row({ project: 'harbor' })
    const b = row({ project: 'harbor' })
    const ws = deriveWorkspaces([a, b], [], null)
    expect(tabsOf(ws[0], (id) => id === a.id).map((s) => s.id)).toEqual([b.id])
  })

  it('tiles only the awake chats and shells; sleeping, ended and servers have rows of their own', () => {
    const a = row({}), z = row({ asleep: true }), e = row({ state: 'ended' }), s = row({ role: 'server' })
    const ws = deriveWorkspaces([a, z, e, s], [], null)
    expect(tilesOf(ws[0]).map((x) => x.id)).toEqual([a.id])
  })

  it('goes to the next chat waiting on you, across the workspaces, round again at the end', () => {
    const a = row({ project: 'harbor', state: 'waiting' })
    const b = row({ project: 'kelp', state: 'waiting' })
    const c = row({ project: 'kelp', state: 'working' })
    const ws = deriveWorkspaces([a, b, c], [], null)
    expect(nextWaiting(ws, c.id)).toBe(a.id)
    expect(nextWaiting(ws, a.id)).toBe(b.id)
    expect(nextWaiting(ws, b.id)).toBe(a.id)
    expect(nextWaiting(deriveWorkspaces([c], [], null), c.id)).toBeUndefined()
  })
})

describe('the overview levels', () => {
  it('steps out to the workspace, then every workspace, and in again to the terminal', () => {
    expect(stepOut('chat', false)).toBe('ws')
    expect(stepOut('ws', false)).toBe('all')
    expect(stepOut('all', false)).toBe('all')
    expect(stepIn('all')).toBe('ws')
    // the button goes round: chat → workspace → every workspace → chat
    expect(['chat', 'ws', 'all'].map((l) => cycleLevel(l as 'chat' | 'ws' | 'all', false))).toEqual(['ws', 'all', 'chat'])
    expect(['chat', 'ws'].map((l) => cycleLevel(l as 'chat' | 'ws', true))).toEqual(['ws', 'chat'])
    expect(stepIn('ws')).toBe('chat')
    expect(stepIn('chat')).toBe('chat')
  })

  it('stops at the workspace in a window of one workspace', () => {
    expect(stepOut('ws', true)).toBe('ws')
  })
})

describe('the address', () => {
  it('reads a detached chat and a workspace window', () => {
    expect(parseView('?detached=t1')).toEqual({ detached: 't1', ws: '' })
    expect(parseView('?ws=harbor')).toEqual({ detached: '', ws: 'harbor' })
  })

  it('takes ?ws= as a group when one has that id, else a project', () => {
    const ws = deriveWorkspaces([], ['harbor'], [{ id: 'g1', name: 'G', color: 1 }])
    expect(resolveWs('g1', ws)).toBe('g:g1')
    expect(resolveWs('harbor', ws)).toBe('p:harbor')
    expect(resolveWs('p:x', ws)).toBe('p:x')
  })

  it('builds the address of a detached window', () => {
    expect(detachUrl('chat', 't 1')).toMatch(/\/term\?detached=t%201$/)
    expect(detachUrl('ws', 'g:g1')).toMatch(/\/term\?ws=g1$/)
  })
})

describe('where a sidebar opens in a browser page', () => {
  const none = { left: null, right: null }
  it('on its own side when there is room, on the other when not, and slides only when neither has room', () => {
    expect(placeSide(400, 1000, 1680, none, 'left')).toEqual({ pick: 'left', slide: 0 })
    expect(placeSide(668, 1000, 1680, none, 'right').pick).toBe('left')
    expect(placeSide(400, 1000, 1680, { left: 'left', right: null }, 'right')).toEqual({ pick: 'right', slide: -60 })
    expect(seatBoth(400, 1000, 1680)).toEqual({ left: 'right', right: 'left' })
    expect(seatBoth(100, 1000, 1200)).toBeNull()
  })
})

describe('chords', () => {
  it('reads the physical key, so a Russian layout keeps the shortcuts', () => {
    expect(chordOf({ ctrlKey: true, metaKey: false, altKey: false, shiftKey: true, code: 'ArrowUp', key: 'ArrowUp' })).toBe('mod+shift+ArrowUp')
    expect(chordOf({ ctrlKey: false, metaKey: false, altKey: true, shiftKey: false, code: 'BracketLeft', key: 'х' })).toBe('alt+BracketLeft')
  })
})
