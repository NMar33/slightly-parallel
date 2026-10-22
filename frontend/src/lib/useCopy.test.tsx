import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { COPIED_MS, useCopy, writeClipboard } from './useCopy'

describe('useCopy', () => {
  let writeText: ReturnType<typeof vi.fn>
  beforeEach(() => {
    vi.useFakeTimers()
    writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  })
  afterEach(() => { vi.useRealTimers() })

  it('writes the text, shows the tick, and takes it back after 1.2 s', async () => {
    const onCopied = vi.fn()
    const { result } = renderHook(() => useCopy({ onCopied }))
    await act(async () => { expect(await result.current.copy('hello')).toBe(true) })
    expect(writeText).toHaveBeenCalledWith('hello')
    expect(result.current.copied).toBe(true)
    expect(onCopied).toHaveBeenCalledTimes(1)
    act(() => { vi.advanceTimersByTime(COPIED_MS) })
    expect(result.current.copied).toBe(false)
  })

  it('says so when the browser refuses', async () => {
    writeText.mockRejectedValue(new Error('denied'))
    const onFailed = vi.fn()
    const { result } = renderHook(() => useCopy({ onFailed }))
    await act(async () => { expect(await result.current.copy('x')).toBe(false) })
    expect(result.current.copied).toBe(false)
    expect(onFailed).toHaveBeenCalledTimes(1)
  })

  it('answers false with no clipboard at all', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    expect(await writeClipboard('x')).toBe(false)
  })

  it('a control gone before the clipboard answers leaves no timer behind', async () => {
    let answer: () => void = () => {}
    writeText.mockReturnValue(new Promise<void>((r) => { answer = r }))
    const onCopied = vi.fn()
    const { result, unmount } = renderHook(() => useCopy({ onCopied }))
    const pending = result.current.copy('late')
    unmount()
    await act(async () => { answer(); await pending })
    expect(vi.getTimerCount()).toBe(0)
    expect(onCopied).not.toHaveBeenCalled()
  })
})
