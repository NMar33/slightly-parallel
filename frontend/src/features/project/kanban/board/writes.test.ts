import { afterEach, describe, expect, it, vi } from 'vitest'

import { boardWrites, localStamp } from './writes'
import type { TaskRow } from '../model'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })

describe('localStamp', () => {
  it('stamps local time, as the server stamps an archive', () => {
    vi.stubEnv('TZ', 'Australia/Sydney')
    expect(localStamp(new Date('2026-10-05T21:00:05Z'))).toBe('2026-10-06T08:00:05')
  })
})

describe('boardWrites.setArchived', () => {
  it('stamps the card in local time at once, then asks again', async () => {
    vi.stubEnv('TZ', 'Australia/Sydney')
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-05T21:00:00Z'))
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })))
    let tasks = [{ id: 'tk_1', title: 'a' } as TaskRow]
    const bump = vi.fn()
    const { setArchived } = boardWrites({ setTasks: (u) => { tasks = typeof u === 'function' ? u(tasks) : u }, bump })
    await setArchived(['tk_1'], true)
    expect(tasks[0]!.archived_at).toBe('2026-10-06T08:00:00')
    expect(bump).toHaveBeenCalled()
  })
})
