import { describe, it, expect, beforeEach } from 'vitest'

import {
  MODAL_DESC_PX,
  MODAL_WIDTH_PX,
  doneVisibleLimit,
  linkInfoByTask,
  orderLanes,
  readModalPrefs,
  readStoredView,
  storeModalPrefs,
  storeView,
} from './TasksKanban'
import type { TaskRow } from './TasksKanban'

/**
 * The Done column's visibility rule — the one piece of board logic with
 * real branching. Everything else on the board is interaction.
 */
describe('doneVisibleLimit', () => {
  it('shows everything in "all" mode', () => {
    expect(doneVisibleLimit('all', 5, [2, 3], false)).toBe(Infinity)
  })

  it('honors the operator count in "fixed" mode', () => {
    expect(doneVisibleLimit('fixed', 7, [20, 30], false)).toBe(7)
    // A nonsense count still renders at least one card.
    expect(doneVisibleLimit('fixed', 0, [], false)).toBe(1)
  })

  it('matches the busiest other column, with a floor of 3', () => {
    expect(doneVisibleLimit('match', 5, [2, 9, 4], false)).toBe(9)
    expect(doneVisibleLimit('match', 5, [1, 0], false)).toBe(3)
    // No other columns at all (defensive) — still the floor, never -Infinity.
    expect(doneVisibleLimit('match', 5, [], false)).toBe(3)
  })

  it('expanding overrides every mode', () => {
    expect(doneVisibleLimit('match', 5, [1], true)).toBe(Infinity)
    expect(doneVisibleLimit('fixed', 2, [1], true)).toBe(Infinity)
  })
})


describe('board view memory', () => {
  beforeEach(() => localStorage.clear())

  it('defaults to the 3-column board', () => {
    expect(readStoredView('alpha')).toBe('classic')
  })

  it('remembers each project separately', () => {
    storeView('alpha', 'lanes')
    storeView('beta', 'workflow')
    expect(readStoredView('alpha')).toBe('lanes')
    expect(readStoredView('beta')).toBe('workflow')
  })

  it('gives an unseen project the most recent choice', () => {
    storeView('alpha', 'lanes')
    expect(readStoredView('never-opened')).toBe('lanes')
  })

  it('ignores a corrupted stored value', () => {
    localStorage.setItem('sp-kanban-view:alpha', 'nonsense')
    expect(readStoredView('alpha')).toBe('classic')
  })
})


describe('task-editor window preferences', () => {
  beforeEach(() => localStorage.clear())

  it('starts at the normal window with a short description box', () => {
    expect(readModalPrefs()).toEqual({
      width: 'normal', desc: 's',
      axes: { impact: true, effort: true, tokens: false, novelty: false },
      chain: 'next',
      sections: { evidence: true, links: true, story: true, chat: true, history: true },
      autoNew: false,
      evidenceNew: false,
    })
  })

  it('round-trips a chosen size, axis visibility and the chain mode', () => {
    const axes = { impact: true, effort: false, tokens: true, novelty: true }
    const sections = { evidence: true, links: false, story: true, chat: true, history: false }
    storeModalPrefs({ width: 'wide', desc: 'l', axes, chain: 'group', sections, autoNew: true, evidenceNew: false })
    expect(readModalPrefs()).toEqual({ width: 'wide', desc: 'l', axes, chain: 'group', sections, autoNew: true, evidenceNew: false })
    // An older stored blob has no chain — it reads back as the plain mode.
    storeModalPrefs({ width: 'wide', desc: 'l', axes } as never)
    expect(readModalPrefs().chain).toBe('next')
    expect(MODAL_WIDTH_PX.wide).toBeGreaterThan(MODAL_WIDTH_PX.normal)
    expect(MODAL_DESC_PX.l).toBeGreaterThan(MODAL_DESC_PX.s)
  })

  it('falls back per field when the stored value is junk', () => {
    localStorage.setItem(
      'sp-task-modal',
      JSON.stringify({ width: 'enormous', desc: 'm' }),
    )
    expect(readModalPrefs()).toMatchObject({ width: 'normal', desc: 'm' })
  })

  it('survives an unparseable payload', () => {
    localStorage.setItem('sp-task-modal', 'not json')
    expect(readModalPrefs()).toMatchObject({ width: 'normal', desc: 's' })
  })
})

describe('orderLanes', () => {
  it('alphabetical with unassigned last when nothing is placed', () => {
    expect(orderLanes(['unassigned', 'zed', 'alpha'], [])).toEqual(['alpha', 'zed', 'unassigned'])
  })
  it('placed lanes keep the saved order, newcomers follow alphabetically', () => {
    expect(orderLanes(['a', 'b', 'c', 'unassigned'], ['c', 'a'])).toEqual(['c', 'a', 'b', 'unassigned'])
  })
  it('ignores saved lanes that no longer exist', () => {
    expect(orderLanes(['a', 'b'], ['gone', 'b'])).toEqual(['b', 'a'])
  })
})

describe('linkInfoByTask', () => {
  const L = (from: string, to: string, kind: 'blocks' | 'relates' | 'parent', fromStatus = 'todo', toStatus = 'todo') => ({
    id: `${from}-${to}-${kind}`, from_id: from, to_id: to, kind,
    from: { id: from, title: from.toUpperCase(), status: fromStatus },
    to: { id: to, title: to.toUpperCase(), status: toStatus },
  })
  it('sees blocks from both ends and knows when a blocker is still open', () => {
    const info = linkInfoByTask([L('a', 'b', 'blocks', 'doing'), L('c', 'b', 'blocks', 'done')])
    expect(info.a.blocks.map((x) => x.id)).toEqual(['b'])
    expect(info.b.blockedBy.map((x) => [x.id, x.open])).toEqual([['a', true], ['c', false]])
    expect(info.b.n).toBe(2)
    expect([...info.b.neighbors]).toEqual(['a', 'c'])
  })
  it('counts sub-tasks done on the parent and names the parent on the child', () => {
    const info = linkInfoByTask([L('p', 'x', 'parent', 'todo', 'done'), L('p', 'y', 'parent')])
    expect(info.p.children.filter((c) => c.done).length).toBe(1)
    expect(info.x.parent?.title).toBe('P')
  })
  it('relates is symmetric', () => {
    const info = linkInfoByTask([L('m', 'n', 'relates')])
    expect(info.m.relates[0].id).toBe('n')
    expect(info.n.relates[0].id).toBe('m')
  })
})

describe('local drafts', () => {
  beforeEach(() => localStorage.clear())
  it('round-trips and clears', async () => {
    const { NOTE_DRAFT_KEY, readDraft, writeDraft, clearDraft } = await import('./TasksKanban')
    writeDraft(NOTE_DRAFT_KEY('tk_x'), { type: 'article', template: 'note', body: 'half a thought', at: '10:00' })
    expect(readDraft(NOTE_DRAFT_KEY('tk_x'))).toMatchObject({ body: 'half a thought' })
    clearDraft(NOTE_DRAFT_KEY('tk_x'))
    expect(readDraft(NOTE_DRAFT_KEY('tk_x'))).toBeNull()
  })
  it('survives junk', async () => {
    const { readDraft } = await import('./TasksKanban')
    localStorage.setItem('k', 'not json')
    expect(readDraft('k')).toBeNull()
  })
})

describe('applyTemplate never deletes typed text', () => {
  it('fills an empty box', async () => {
    const { applyTemplate } = await import('./TasksKanban')
    expect(applyTemplate('', '', 'A — \n\nB — ')).toBe('A — \n\nB — ')
  })
  it('swaps an untouched scaffold', async () => {
    const { applyTemplate } = await import('./TasksKanban')
    expect(applyTemplate('A — \n\nB — ', 'A — \n\nB — ', 'Q: \n\nA: ')).toBe('Q: \n\nA: ')
  })
  it('appends below typed text and keeps it', async () => {
    const { applyTemplate } = await import('./TasksKanban')
    expect(applyTemplate('my words', 'A — \n\nB — ', 'Q: \n\nA: ')).toBe('my words\n\nQ: \n\nA: ')
    expect(applyTemplate('my words', '', '')).toBe('my words')
  })
})

describe('sortTasks and ageBucket', () => {
  const T = (id: string, over: Record<string, unknown> = {}) => ({ id, title: id, ...over }) as TaskRow
  it('manual returns the input; others are stable resorts', async () => {
    const { sortTasks } = await import('./TasksKanban')
    const items = [T('a', { priority: 'low' }), T('b', { priority: 'high' }), T('c', { priority: 'high' })]
    expect(sortTasks(items, 'manual')).toBe(items)
    expect(sortTasks(items, 'priority').map((t: TaskRow) => t.id)).toEqual(['b', 'c', 'a']) // tie b/c keeps manual order
  })
  it('oldest uses status_since with creation fallback; quick wins lead', async () => {
    const { sortTasks } = await import('./TasksKanban')
    const items = [
      T('fresh', { created_date: '2608-20', created_time: '01:00', impact: 'high', effort: 'S' }),
      T('stale', { created_date: '2608-10', created_time: '01:00', impact: 'low', effort: 'L' }),
    ]
    const since = { stale: '2026-08-10T01:00:00', fresh: '2026-08-20T01:00:00' }
    expect(sortTasks(items, 'oldest', since).map((t: TaskRow) => t.id)).toEqual(['stale', 'fresh'])
    expect(sortTasks(items, 'quickwins').map((t: TaskRow) => t.id)).toEqual(['fresh', 'stale'])
  })
  it('ageBucket: silent under a day, red past two weeks', async () => {
    const { ageBucket } = await import('./TasksKanban')
    const now = Date.parse('2026-08-20T12:00:00')
    expect(ageBucket('2026-08-20T02:00:00', now)).toBeNull()
    expect(ageBucket('2026-08-18T02:00:00', now)?.days).toBe(2)
    expect(ageBucket('2026-08-01T02:00:00', now)?.color).toBe('var(--status-red)')
    expect(ageBucket(undefined, now)).toBeNull()
  })
})

describe('Today — a lens, not a place', () => {
  it('is true only for the current date, so the lane empties itself', async () => {
    const { isToday, todayISO } = await import('./TasksKanban')
    const today = todayISO(new Date(2026, 7, 22))
    expect(today).toBe('2026-08-22')
    expect(isToday({ id: 'a', today_on: '2026-08-22' } as never, today)).toBe(true)
    expect(isToday({ id: 'a', today_on: '2026-08-21' } as never, today)).toBe(false)
    expect(isToday({ id: 'a' } as never, today)).toBe(false)
  })
  it('stamps the local day, never a UTC-shifted one', async () => {
    const { todayISO } = await import('./TasksKanban')
    expect(todayISO(new Date(2026, 0, 1, 23, 30))).toBe('2026-01-01')
  })
})

describe('Stacks — a queue drawn as one card', () => {
  const t = (id: string, position: number, stack_id?: string, extra: Record<string, unknown> = {}) =>
    ({ id, title: id, status: 'todo', position, stack_id, ...extra }) as never

  it('shows the earliest member and hides the tail behind it', async () => {
    const { foldStacks } = await import('./TasksKanban')
    const items = [t('a', 1, 'st'), t('b', 2, 'st'), t('c', 3, 'st'), t('loose', 4)]
    const out = foldStacks(items)
    expect(out.map((f) => f.task.id)).toEqual(['a', 'loose'])
    expect(out[0]!.behind.map((x) => x.id)).toEqual(['b', 'c'])
    expect(out[0]!.total).toBe(3)
    expect(out[0]!.ordinal).toBe(1)
  })

  it('counts the whole stack even when earlier members left the column', async () => {
    const { foldStacks } = await import('./TasksKanban')
    const all = [t('a', 1, 'st', { status: 'doing' }), t('b', 2, 'st'), t('c', 3, 'st')]
    const inColumn = [all[1]!, all[2]!]        // only b and c are still in To do
    const out = foldStacks(inColumn, all)
    expect(out).toHaveLength(1)
    expect(out[0]!.task.id).toBe('b')
    expect(out[0]!.ordinal).toBe(2)            // b is step 2 of 3, not step 1
    expect(out[0]!.total).toBe(3)
  })

  it('leaves unstacked tasks exactly as they were', async () => {
    const { foldStacks } = await import('./TasksKanban')
    const items = [t('x', 1), t('y', 2)]
    expect(foldStacks(items).map((f) => [f.task.id, f.total])).toEqual([['x', 1], ['y', 1]])
  })
})

/**
 * Writes that can fail: a reorder says how many positions did not land, and
 * a stack with two steps of one name is refused before anything is posted.
 */
describe('writeOrder', () => {
  it('counts the writes that were refused, and posts every one', async () => {
    const { writeOrder } = await import('./TasksKanban')
    const posted: string[] = []
    const post = async (path: string) => {
      posted.push(path)
      if (path.includes('tk_b')) throw new Error("task.position 'x' is not a number")
    }
    const failed = await writeOrder([{ id: 'tk_a', position: 0 }, { id: 'tk_b', position: 1 }, { id: 'tk_c', position: 2 }], post)
    expect(failed).toBe(1)
    expect(posted).toHaveLength(3)
  })

  it('is zero when every write landed', async () => {
    const { writeOrder } = await import('./TasksKanban')
    expect(await writeOrder([{ id: 'tk_a', position: 0 }], async () => ({}))).toBe(0)
  })
})

describe('stepClash', () => {
  it('names the step that repeats the head or another step', async () => {
    const { stepClash } = await import('./TasksKanban')
    expect(stepClash('Write tests', ['Ship', 'write tests '])).toBe('write tests')
    expect(stepClash('Write tests', ['Ship', 'Ship'])).toBe('Ship')
  })

  it('is null when every title is its own, blanks ignored', async () => {
    const { stepClash } = await import('./TasksKanban')
    expect(stepClash('Write tests', ['Ship', '', '  '])).toBeNull()
    expect(stepClash('Write tests', [])).toBeNull()
  })
})
