import { afterEach, describe, expect, it, vi } from 'vitest'

import { boardDrops } from './drops'
import type { TaskRow } from '../model'

afterEach(() => { vi.unstubAllGlobals() })

function board(tasks: TaskRow[]) {
  let cur = tasks
  const posts: Array<{ id: string; body: Record<string, unknown> }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const id = decodeURIComponent(/\/api\/tasks\/([^/]+)\/update/.exec(String(url))?.[1] ?? '')
    posts.push({ id, body: JSON.parse(String(init?.body)) })
    return new Response('{}', { status: 200 })
  }))
  const drops = boardDrops({
    tasks: cur,
    setTasks: (u) => { cur = typeof u === 'function' ? u(cur) : u },
    columnKeyOf: (t) => String(t.status),
    today: '2026-10-25',
    sorts: {},
    setPendingDrop: () => {},
    setArchived: async () => {},
    moveSelection: async () => {},
    setRefreshTick: () => {},
  })
  return { drops, posts, tasks: () => cur }
}

const row = (id: string, position: string | undefined, status = 'todo'): TaskRow =>
  ({ id, title: id, status, position } as unknown as TaskRow)

describe('a dropped card lands where it was put, in whole positions', () => {
  it('takes the whole number in the middle of a gap', async () => {
    const { drops, posts } = board([row('a', '10'), row('b', '20'), row('x', '50', 'doing')])
    await drops.handleDrop('x', 'todo', undefined, 'b')
    expect(posts.at(-1)!.body.position).toBe('15')
  })

  it('numbers the column again when every card sits at 999 (the editor\'s default)', async () => {
    // Before: (999 + 999) / 2 = 999 → 999.5, which the server rounds to 1000:
    // the card went below every 999 instead of between the first two.
    const { drops, posts, tasks } = board([row('a', '999'), row('b', '999'), row('c', '999'), row('x', '5', 'doing')])
    await drops.handleDrop('x', 'todo', undefined, 'b')
    const positions = Object.fromEntries(tasks().map((t) => [t.id, Number(t.position)]))
    expect(positions).toEqual({ a: 10, x: 20, b: 30, c: 40 })
    expect(posts.every((p) => Number.isInteger(p.body.position === undefined ? 0 : Number(p.body.position)))).toBe(true)
    expect(posts.map((p) => p.id).sort()).toEqual(['a', 'b', 'c', 'x'])
  })

  it('counts a card with no position as last, as the server sorts it', async () => {
    // Before: an agent's card has no position, read as 0; dropping before it
    // wrote 0.5 → 1, which sorted ahead of every position-less card.
    const { drops, tasks } = board([row('a', '10'), row('agent', undefined), row('x', '5', 'doing')])
    await drops.handleDrop('x', 'todo', undefined, 'agent')
    const positions = Object.fromEntries(tasks().map((t) => [t.id, Number(t.position)]))
    expect(positions.x).toBeGreaterThan(positions.a!)
    expect(positions.agent).toBeGreaterThan(positions.x!)
    expect(Object.values(positions).every(Number.isInteger)).toBe(true)
  })
})
