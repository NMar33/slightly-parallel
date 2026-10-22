import { afterEach, describe, expect, it, vi } from 'vitest'

import { savePrefNow } from './uiPrefs'

describe('savePrefNow', () => {
  afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

  it('writes the local copy only after the server has the value', async () => {
    let release: () => void = () => {}
    const fetch = vi.fn(() => new Promise<Response>((r) => { release = () => r(new Response('{}')) }))
    vi.stubGlobal('fetch', fetch)
    localStorage.setItem('sp-lang', 'en')
    const done = savePrefNow('sp-lang', 'ru')
    expect(JSON.parse(String((fetch.mock.calls[0] as unknown[])[1] && ((fetch.mock.calls[0] as unknown[])[1] as RequestInit).body))).toEqual({ values: { 'sp-lang': 'ru' } })
    expect(localStorage.getItem('sp-lang')).toBe('en')
    release()
    await done
    expect(localStorage.getItem('sp-lang')).toBe('ru')
  })
})
