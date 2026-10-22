import { describe, expect, it } from 'vitest'

import { currentWork, modeOf, setWork } from './timer'

describe('what you are working on', () => {
  it('is the most specific layer: a task, then a terminal, then the page', () => {
    setWork('route', { project: 'alpha' })
    expect(currentWork()).toEqual({ project: 'alpha' })
    setWork('terminal', { project: 'beta', taskId: 'tk_t' })
    setWork('task', { project: 'alpha', taskId: 'tk_1' })
    expect(currentWork()?.taskId).toBe('tk_1')
    setWork('task', null)
    expect(currentWork()?.project).toBe('beta')
    setWork('terminal', null)
    setWork('route', null)
    expect(currentWork()).toBeNull()
  })
  it('a project with no mode of its own takes the default', () => {
    const st = { modes: { alpha: 'auto' }, default_mode: 'remind' } as never
    expect([modeOf(st, 'alpha'), modeOf(st, 'beta')]).toEqual(['auto', 'remind'])
  })
})
