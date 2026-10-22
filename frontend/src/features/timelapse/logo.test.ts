import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

import { useLogo } from './logo'

/** An image that loads only when the test says so. */
const made: FakeImage[] = []
class FakeImage {
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  src = ''
  constructor() { made.push(this) }
}

afterEach(() => { made.length = 0; vi.unstubAllGlobals() })

describe('useLogo', () => {
  it('drops a logo that finishes loading after it was removed', () => {
    vi.stubGlobal('Image', FakeImage)
    const { result, rerender } = renderHook(({ url }) => useLogo(url), { initialProps: { url: 'data:a' } })
    rerender({ url: '' })
    act(() => { made[0]!.onload?.() })
    expect(result.current).toBeNull()
  })

  it('keeps the latest of two logos whatever order they load in', () => {
    vi.stubGlobal('Image', FakeImage)
    const { result, rerender } = renderHook(({ url }) => useLogo(url), { initialProps: { url: 'data:a' } })
    rerender({ url: 'data:b' })
    act(() => { made[1]!.onload?.() })
    act(() => { made[0]!.onload?.() })
    expect((result.current as unknown as FakeImage).src).toBe('data:b')
  })
})
