import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AquaSession } from '../model'
import { factsOf, markNamed, noteOscTitle, tabTitle, type TabInfo } from './facts'
import { STRIP_DEFAULT, dotsOf, parseStrip, partValue, setStrip, shownSlots, useStripSettings } from './strip'
import { agentOf, plusItems, type PlusActions } from './Plus'

const row = (p: Partial<AquaSession> = {}): AquaSession => ({
  id: 't1', kind: 'shell', label: 'claude', project: 'harbor', cwd: '/h', command: 'claude', agent_id: '', task_id: '',
  created: '', backend: 'tmux', state: 'working', program: 'claude', last_output: 0, ...p,
})
const info = (p: Partial<TabInfo> = {}, chat: Partial<NonNullable<TabInfo['chat']>> | null = {}): TabInfo => ({
  title: '', agent_id: 'cc-a',
  chat: chat === null ? null : { name: '', tool: 'claude-code', tasks_done: 0, tasks_all: 0, branches: 0, ctx_pct: null, ctx_size: null, ctx_at: '', ...chat },
  ...p,
})

beforeEach(() => localStorage.clear())

describe('a tab\'s title', () => {
  it('goes: the operator\'s name, the title seen live, tmux\'s title, the chat\'s name, the label; never the project', () => {
    const s = row()
    expect(tabTitle(s, info({}, { name: 'Pricing' }), {}, [])).toBe('Pricing')
    expect(tabTitle(s, info({ title: 'hbr-2611-18' }, { name: 'Pricing' }), {}, [])).toBe('hbr-2611-18')
    expect(tabTitle(s, info({ title: 'hbr-2611-18' }), { t1: 'live' }, [])).toBe('live')
    expect(tabTitle(row({ label: 'mine' }), info({ title: 'x' }), { t1: 'live' }, ['t1'])).toBe('mine')
    // a label that is only the project's code or a made-up word gives way to nothing better: kept
    expect(tabTitle(row({ label: 'harbor' }), undefined, {}, [])).toBe('harbor')
    expect(tabTitle(row({ label: 'release notes' }), info({}, null), {}, [])).toBe('release notes')
  })

  it('remembers the title a program set, and the names the operator gave', () => {
    noteOscTitle('t9', '  hbr-2611-18  ')
    expect(JSON.parse(localStorage.getItem('spw-osc-titles')!)).toEqual({ t9: 'hbr-2611-18' })
    noteOscTitle('t9', '')
    expect(JSON.parse(localStorage.getItem('spw-osc-titles')!)).toEqual({})
    markNamed('t9')
    expect(JSON.parse(localStorage.getItem('sp-term-named')!)).toEqual(['t9'])
  })
})

describe('a tab\'s facts', () => {
  it('waiting minutes count from the last print, only while waiting; context is null when not known', () => {
    const now = 1_800_000_000_000
    const w = factsOf(row({ state: 'waiting', last_output: now / 1000 - 26 * 60 }), info({}, { tasks_done: 1, tasks_all: 3, branches: 2, ctx_pct: 72 }), now)
    expect(w).toEqual({ branches: 2, done: 1, all: 3, waited: 26, ctx: 72, waiting: true, rhythm: null, chatId: 'cc-a' })
    const busy = factsOf(row({ state: 'working', last_output: now / 1000 - 26 * 60 }), undefined, now)
    expect(busy).toEqual({ branches: 0, done: 0, all: 0, waited: 0, ctx: null, waiting: false, rhythm: null, chatId: 't1' })
  })
})

describe('the status strip', () => {
  const f = { branches: 0, done: 1, all: 4, waited: 0, ctx: 50 as number | null, waiting: false }
  it('parts fill and colour: closed green, context grey/amber/red, waiting green to red over 30 min', () => {
    expect(partValue('closed', f)).toEqual({ v: 0.25, color: 'var(--aq-up)' })
    expect(partValue('context', { ...f, ctx: 50 }).color).toBe('var(--aq-ink3)')
    expect(partValue('context', { ...f, ctx: 75 }).color).toBe('var(--aq-wait)')
    expect(partValue('context', { ...f, ctx: 90 }).color).toBe('var(--aq-down)')
    expect(partValue('context', { ...f, ctx: null }).v).toBe(0)
    expect(partValue('waiting', f).v).toBe(0)
    expect(partValue('waiting', { ...f, waiting: true, waited: 30 }).color).toContain('var(--aq-down) 100%')
    expect(dotsOf(0)).toBe(0); expect(dotsOf(0.25)).toBe(1); expect(dotsOf(1)).toBe(5)
  })

  it('settings: parts 1–3 show the right slots, a broken value reads as the defaults, a change persists', () => {
    expect(shownSlots({ ...STRIP_DEFAULT, parts: 2 })).toEqual([0, 2])
    expect(shownSlots({ ...STRIP_DEFAULT, parts: 1 })).toEqual([2])
    expect(parseStrip('{"parts":5}')).toEqual(STRIP_DEFAULT)
    expect(parseStrip('nope')).toEqual(STRIP_DEFAULT)
    expect(parseStrip(JSON.stringify({ parts: 1, px: 4, kinds: ['waiting', 'context', 'closed'], on: false }))).toEqual({ parts: 1, px: 4, kinds: ['waiting', 'context', 'closed'], on: false })
    vi.useFakeTimers()
    setStrip({ px: 3 })
    expect(JSON.parse(localStorage.getItem('sp-term-strip')!).px).toBe(3)
    vi.useRealTimers()
    expect(typeof useStripSettings).toBe('function')
  })
})

describe('the "+" list', () => {
  const act: PlusActions = { agent: vi.fn(), shell: vi.fn(), server: vi.fn(), wake: vi.fn(), resume: vi.fn(), task: vi.fn() }
  const base = { agent: 'claude' as const, project: 'harbor', path: '/h', chatTitle: 'hbr', installed: { claude: true, codex: false, opencode: true }, asleep: [], resumable: [], tasks: [], act }

  it('the agent of a chat: its tool, else the program, else the command, else the default', () => {
    expect(agentOf('codex', 'claude', '', 'claude')).toBe('codex')
    expect(agentOf('claude-code', '', '', 'codex')).toBe('claude')
    expect(agentOf('', '/usr/bin/opencode', '', 'claude')).toBe('opencode')
    expect(agentOf(undefined, 'bash', 'codex --yolo', 'claude')).toBe('codex')
    expect(agentOf(undefined, 'bash', '', 'claude')).toBe('claude')
  })

  it('a plain terminal first, then a chat with each installed agent; open tasks only, the worktree as «soon», branching only when it can (tk_e7649e7c)', () => {
    const items = plusItems({ ...base, tasks: [{ id: 'tk_1', title: 'a', status: 'todo' }, { id: 'tk_2', title: 'b', status: 'done' }],
      asleep: [{ id: 's1', title: 'sleepy' }], resumable: [{ agent_id: 'cc-x', name: 'old', tool: 'claude-code' }] })
    expect(items.map((x) => x.id)).toEqual(['shell', 'agent:claude', 'agent:opencode', 'server', 'branch', 'resume', 'task', 'worktree'])
    expect(items[0]!.hint).toContain('/h')
    expect(items[0]!.hint).toContain('A plain click on + does the same.')
    expect(items[1]!.label).toBe('New chat: Claude Code')
    expect(items[2]!.label).toBe('New chat: OpenCode')
    expect(items[4]!.run).toBeUndefined()
    expect(items[5]!.sub!.map((x) => x.id)).toEqual(['s:s1', 'r:cc-x'])
    expect(items[6]!.sub!.map((x) => x.id)).toEqual(['tk_1'])
    expect(items[7]!.soon).toBe(true)
    items[0]!.run!()
    expect(act.shell).toHaveBeenCalled()
    items[2]!.run!()
    expect(act.agent).toHaveBeenCalledWith('opencode')
    items[5]!.sub![0]!.run(); items[5]!.sub![1]!.run(); items[6]!.sub![0]!.run()
    expect(act.wake).toHaveBeenCalledWith('s1'); expect(act.resume).toHaveBeenCalledWith('cc-x'); expect(act.task).toHaveBeenCalledWith('tk_1')
  })

  it('while the installed agents are not known it offers the given one only', () => {
    const items = plusItems({ ...base, agent: 'codex', installed: null })
    expect(items.filter((x) => x.id.startsWith('agent:')).map((x) => x.id)).toEqual(['agent:codex'])

  })
})
