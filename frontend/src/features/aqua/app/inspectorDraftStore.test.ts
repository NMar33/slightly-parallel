import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { isSyncable } from '../../../lib/uiPrefs'
import { useInspectorDraft } from './inspectorDraftStore'

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
  vi.restoreAllMocks()
})

it('keeps one local project draft, appends in place, and can undo a clear', async () => {
  const a = renderHook(() => useInspectorDraft('draft-alpha'))
  const b = renderHook(() => useInspectorDraft('draft-beta'))
  act(() => a.result.current.edit('Первая строка\n'))
  await act(async () => { expect(await a.result.current.append('tk_42 — Task\n\nDescription')).toBe(true) })
  const text = 'Первая строка\n\ntk_42 — Task\n\nDescription'
  expect(localStorage.getItem('sp-aqua-draft:draft-alpha')).toBe(text)
  expect(isSyncable('sp-aqua-draft:draft-alpha')).toBe(false)
  expect(b.result.current.state.text).toBe('')
  await act(async () => { await a.result.current.clear() })
  expect(a.result.current.state.text).toBe('')
  await act(async () => { await a.result.current.undoClear() })
  expect(a.result.current.state.text).toBe(text)
  a.unmount()
  expect(renderHook(() => useInspectorDraft('draft-alpha')).result.current.state.text).toBe(text)
})

it('preserves text from both windows if the saved draft changes during a local edit', async () => {
  const project = 'draft-conflict'
  const key = `sp-aqua-draft:${project}`
  localStorage.setItem(key, 'first')
  const draft = renderHook(() => useInspectorDraft(project))
  // Another window wrote before this window was notified. A pending
  // replacement must detect the external change during its locked read.
  localStorage.setItem(key, 'other window')
  act(() => draft.result.current.edit('unsaved local input'))
  expect(draft.result.current.state).toMatchObject({ text: 'unsaved local input', conflict: true })
  expect(localStorage.getItem(key)).toBe('other window')
  expect(sessionStorage.getItem(key)).toBe('unsaved local input')
  await act(async () => { expect(await draft.result.current.append('a task')).toBe(false) })
  await act(async () => { expect(await draft.result.current.keepBoth()).toBe(true) })
  expect(localStorage.getItem(key)).toBe('other window\n\nunsaved local input')
  expect(sessionStorage.getItem(key)).toBeNull()
})
