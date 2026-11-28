import { afterEach, describe, expect, it, vi } from 'vitest'
import { adoptOldKeys, hydratePrefs, isSyncable, readPref } from './uiPrefs'

describe('isSyncable — what reaches the server', () => {
  it('syncs view preferences', () => {
    for (const k of [
      'sp-kanban-view:slightly-parallel', 'sp-lanes-order:slightly-parallel',
      'sp-theme', 'sp-variant-timer', 'sp-task-modal',
      'sp-storyboard-open:slightly-parallel', 'sp-task-timeline:slightly-parallel',
    ]) expect(isSyncable(k), k).toBe(true)
  })
  it('keeps per-browser state local', () => {
    for (const k of [
      'sp-note-draft:tk_x', 'sp-note-edit:nt_x',
      'sp-task-draft:slightly-parallel', 'sp-doc-block-draft:dc_x',
      'pdr.sidebar', 'sp-term-health-day',
      'sp-aqua-active', 'sp-aqua-workspace', 'sp-aqua-ws-tabs', 'sp-aqua-window-side',
    ]) expect(isSyncable(k), k).toBe(false)
  })
})

describe('hydratePrefs — live terminal state stays in the browser', () => {
  afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

  it('a copy the server kept never comes back over the live day, is removed there, and the day is never sent up', async () => {
    localStorage.clear()
    const live = JSON.stringify({ date: '2026-11-18', run: 3 })
    localStorage.setItem('sp-term-health-day', live)
    const posts: unknown[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') { posts.push(JSON.parse(String(init.body))); return new Response('{}') }
      return new Response(JSON.stringify({ prefs: { 'sp-theme': 'dark', 'sp-term-health-day': JSON.stringify({ date: '2026-11-18', run: 95 }) } }),
        { headers: { 'Content-Type': 'application/json' } })
    }))
    await hydratePrefs()
    await new Promise((r) => setTimeout(r, 0))
    expect(localStorage.getItem('sp-term-health-day')).toBe(live)
    expect(localStorage.getItem('sp-theme')).toBe('dark')
    expect(posts).toEqual([{ values: { 'sp-term-health-day': null } }])
  })

  it('ignores stale tab selections and order and keeps the local workspace', async () => {
    localStorage.clear()
    const tabs = JSON.stringify({ 'p:kelp': 'rightmost' })
    const order = JSON.stringify({ 'p:kelp': ['leftmost', 'rightmost'] })
    localStorage.setItem('sp-aqua-active', 'rightmost')
    localStorage.setItem('sp-aqua-workspace', 'p:kelp')
    localStorage.setItem('sp-aqua-ws-tabs', tabs)
    localStorage.setItem('sp-aqua-tab-order', order)
    const posts: unknown[] = []
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') { posts.push(JSON.parse(String(init.body))); return new Response('{}') }
      return new Response(JSON.stringify({ prefs: { 'sp-aqua-active': 'leftmost', 'sp-aqua-ws-tabs': '{}', 'sp-aqua-tab-order': '{}' } }),
        { headers: { 'Content-Type': 'application/json' } })
    }))

    await hydratePrefs()
    expect(localStorage.getItem('sp-aqua-active')).toBe('rightmost')
    expect(localStorage.getItem('sp-aqua-workspace')).toBe('p:kelp')
    expect(localStorage.getItem('sp-aqua-ws-tabs')).toBe(tabs)
    expect(localStorage.getItem('sp-aqua-tab-order')).toBe(order)
    expect(posts).toEqual([{ values: { 'sp-aqua-active': null, 'sp-aqua-ws-tabs': null, 'sp-aqua-tab-order': null } }])
  })

  it('keeps the terminal window layout local when a different profile shared its own', async () => {
    const key = 'sp-aqua-window-layout'
    const local = JSON.stringify({ titleScale: 2, tabsScale: 1.5 })
    const server = JSON.stringify({ titleScale: 1.5, tabsScale: 1 })
    localStorage.setItem(key, local)
    const posts: unknown[] = []
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') { posts.push(JSON.parse(String(init.body))); return new Response('{}') }
      return new Response(JSON.stringify({ prefs: { [key]: server } }), { headers: { 'Content-Type': 'application/json' } })
    }))

    await hydratePrefs()
    expect(localStorage.getItem(key)).toBe(local)
    expect(posts).toEqual([{ values: { [key]: null } }])
  })
})

describe('useKeyedPref', () => {
  it('reads the next key\'s value when the key changes, and writes under the key in use', async () => {
    const { renderHook, act } = await import('@testing-library/react')
    const { useKeyedPref, readJsonPref } = await import('./uiPrefs')
    localStorage.setItem('sp-k:a', JSON.stringify('A'))
    localStorage.setItem('sp-k:b', JSON.stringify('B'))
    const read = (k: string) => readJsonPref<string>(k, '')
    const { result, rerender } = renderHook(({ key }) => useKeyedPref(key, read), { initialProps: { key: 'sp-k:a' } })
    expect(result.current[0]).toBe('A')
    rerender({ key: 'sp-k:b' })
    expect(result.current[0]).toBe('B')
    act(() => result.current[1]('B2'))
    expect(localStorage.getItem('sp-k:b')).toBe('"B2"')
    expect(localStorage.getItem('sp-k:a')).toBe('"A"')
  })
})

describe('keys from before the rename', () => {
  it('readPref answers an sp- key from its merkhet- twin once, and keeps the new name', () => {
    localStorage.clear()
    localStorage.setItem('merkhet-kanban-view:alpha', 'lanes')
    localStorage.setItem('merkhet.chat.size', 'wide')
    expect(readPref('sp-kanban-view:alpha')).toBe('lanes')
    expect(localStorage.getItem('sp-kanban-view:alpha')).toBe('lanes')
    expect(readPref('sp-chat-size')).toBe('wide')  // the dotted spelling from before 2026-09-23
    expect(readPref('sp-nothing')).toBeNull()
    localStorage.setItem('sp-kanban-view:alpha', 'workflow')
    expect(readPref('sp-kanban-view:alpha')).toBe('workflow')  // the new name wins once it holds a value
  })

  it('adoptOldKeys copies every merkhet- key whose sp- twin is absent', () => {
    localStorage.clear()
    localStorage.setItem('merkhet-theme', 'dark')
    localStorage.setItem('merkhet-lang', 'ru')
    localStorage.setItem('sp-lang', 'en')
    adoptOldKeys()
    expect(localStorage.getItem('sp-theme')).toBe('dark')
    expect(localStorage.getItem('sp-lang')).toBe('en')
    expect(localStorage.getItem('merkhet-theme')).toBe('dark')  // the old copy stays
  })
})
