import { afterEach, describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'

import { useControls } from './parts'

afterEach(() => localStorage.clear())

describe('useControls', () => {
  it('nothing stored: the defaults, not zero', () => {
    const { result } = renderHook(() => useControls())
    expect(result.current.count).toBe(20)
    expect(result.current.weight).toBe(5)
  })

  it('a stored zero is kept: "all" and no weight', () => {
    localStorage.setItem('sp-files-count', '0')
    localStorage.setItem('sp-files-weight', '0')
    const { result } = renderHook(() => useControls())
    expect(result.current.count).toBe(0)
    expect(result.current.weight).toBe(0)
  })
})
