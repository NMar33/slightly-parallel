import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'

import { ThemeProvider, useTheme } from './ThemeProvider'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear() })

describe('ThemeProvider', () => {
  it('going back to the system theme clears the server copy too', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }))
    vi.stubGlobal('fetch', fetch)
    localStorage.setItem('sp-theme', 'dark')
    let setMode: (m: 'system' | 'light' | 'dark') => void = () => {}
    function Probe() { setMode = useTheme().setMode; return null }
    render(<ThemeProvider><Probe /></ThemeProvider>)
    act(() => setMode('system'))
    await act(async () => { vi.advanceTimersByTime(500) })
    expect(localStorage.getItem('sp-theme')).toBeNull()
    const sent = fetch.mock.calls.map((c) => JSON.parse(String((c as unknown[])[1] && ((c as unknown[])[1] as RequestInit).body)))
    expect(sent).toContainEqual({ values: { 'sp-theme': null } })
  })
})
