import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useSidebarLayout, useUndoDepth } from './store'

afterEach(() => { vi.restoreAllMocks() })

describe('the sidebar store', () => {
  it('removes the storage handler it added once the last reader leaves', () => {
    const add = vi.spyOn(window, 'addEventListener')
    const remove = vi.spyOn(window, 'removeEventListener')
    const storage = (spy: typeof add) => spy.mock.calls.filter((c) => c[0] === 'storage').map((c) => c[1])
    for (let round = 0; round < 2; round += 1) {
      const a = renderHook(() => useSidebarLayout())
      const b = renderHook(() => useUndoDepth())
      a.unmount()
      b.unmount()
    }
    expect(storage(add)).toHaveLength(2)
    expect(storage(remove)).toEqual(storage(add))
  })
})
