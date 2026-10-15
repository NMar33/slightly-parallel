import { describe, expect, it } from 'vitest'
import { adoptOldKeys, isSyncable, readPref } from './uiPrefs'

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
      'pdr.sidebar',
    ]) expect(isSyncable(k), k).toBe(false)
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
