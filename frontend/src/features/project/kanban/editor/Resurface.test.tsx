import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'

import { ResurfaceRow } from './Resurface'

beforeEach(() => {
  // A morning east of UTC: the UTC date is still yesterday.
  vi.stubEnv('TZ', 'Australia/Sydney')
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-05T21:00:00Z')) // 08:00 on 6 Oct in Sydney
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllEnvs() })

describe('ResurfaceRow', () => {
  it('a week from now is seven local days on, not counted from the UTC date', () => {
    const setOn = vi.fn()
    render(
      <ResurfaceRow remember={false} setRemember={() => {}} projectCode="p"
        resurfaceOn="" setResurfaceOn={setOn} resurfaceTo="todo" setResurfaceTo={() => {}}
        resurfaceEvery="" setResurfaceEvery={() => {}} />,
    )
    fireEvent.click(screen.getByRole('radio', { name: '1w' }))
    expect(setOn).toHaveBeenCalledWith('2026-10-13')
  })
})
