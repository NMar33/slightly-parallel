import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { SIDEBAR_PREF, useSidebarCollapsed } from './useSidebarCollapsed'

function press(target: EventTarget, key = '[', init: KeyboardEventInit = {}) {
  target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init }))
}

describe('useSidebarCollapsed', () => {
  beforeEach(() => localStorage.clear())

  it('starts expanded and remembers a collapse', () => {
    const { result } = renderHook(() => useSidebarCollapsed())
    expect(result.current[0]).toBe(false)
    act(() => result.current[1]())
    expect(result.current[0]).toBe(true)
    expect(localStorage.getItem(SIDEBAR_PREF)).toBe('1')
    const again = renderHook(() => useSidebarCollapsed())
    expect(again.result.current[0]).toBe(true)
  })

  it('flips on [ but not with a modifier or inside a field', () => {
    const { result } = renderHook(() => useSidebarCollapsed())
    act(() => press(document.body))
    expect(result.current[0]).toBe(true)
    act(() => press(document.body, '[', { ctrlKey: true }))
    expect(result.current[0]).toBe(true)
    const input = document.createElement('input')
    document.body.appendChild(input)
    act(() => press(input))
    expect(result.current[0]).toBe(true)
    input.remove()
    act(() => press(document.body, ']'))
    expect(result.current[0]).toBe(true)
  })
})
