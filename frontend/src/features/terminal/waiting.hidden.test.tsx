import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query'
import { createElement } from 'react'

import type { TermSession } from '../../lib/terminal'

const getJson = vi.fn()
vi.mock('../../lib/getJson', async (original) => ({
  ...(await original<typeof import('../../lib/getJson')>()),
  getJson: (...args: unknown[]) => getJson(...args),
}))

import { WaitingNotice } from './waiting'

const s = (id: string, state: TermSession['state']) => ({ id, state, label: id, project: 'p', program: 'claude' }) as TermSession

/** A hidden tab is the one a desktop notification is for: the list has to keep being read there. */
describe('the watcher in a hidden tab', () => {
  const raised: string[] = []
  let state: TermSession['state'] = 'working'

  beforeEach(() => {
    raised.length = 0
    getJson.mockReset()
    state = 'working'
    vi.useFakeTimers()
    class FakeNotification {
      static permission = 'granted'
      static requestPermission = async () => 'granted'
      onclick: (() => void) | null = null
      constructor(title: string) { raised.push(title) }
      close() {}
    }
    vi.stubGlobal('Notification', FakeNotification)
    getJson.mockImplementation(async (path: string) =>
      path === '/api/terminal/state' ? { enabled: true } : { sessions: [s('agent-a', state)], counts: {} })
    // Not in front: react-query's own idea of it, and the document's.
    focusManager.setFocused(false)
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    focusManager.setFocused(undefined)
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    localStorage.clear()
  })

  const mount = async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(createElement(QueryClientProvider, { client: qc }, createElement(WaitingNotice)))
    // The status arrives, then the list it switches on: a render apiece.
    await act(async () => { await vi.advanceTimersByTimeAsync(50) })
    await act(async () => { await vi.advanceTimersByTimeAsync(50) })
    return view
  }
  const lists = () => getJson.mock.calls.filter(([p]) => p === '/api/terminal/sessions').length

  it('keeps reading the list and raises the notification when the switch is on', async () => {
    localStorage.setItem('sp-waiting-notify', '1')
    const view = await mount()
    expect(lists()).toBe(1)
    state = 'waiting'
    await act(async () => { await vi.advanceTimersByTimeAsync(5_100) })
    expect(lists()).toBeGreaterThan(1)
    expect(raised).toEqual(['agent-a is waiting for you'])
    view.unmount()
  })

  it('does not poll a hidden tab when no notification could come of it', async () => {
    const view = await mount()
    expect(lists()).toBe(1)
    state = 'waiting'
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000) })
    expect(lists()).toBe(1)
    expect(raised).toEqual([])
    view.unmount()
  })

  it('still says it when the browser refuses a page its own notification', async () => {
    localStorage.setItem('sp-waiting-notify', '1')
    class Refused {
      static permission = 'granted'
      static requestPermission = async () => 'granted'
      constructor() { throw new TypeError('Illegal constructor') }
    }
    vi.stubGlobal('Notification', Refused)
    const view = await mount()
    state = 'waiting'
    await act(async () => { await vi.advanceTimersByTimeAsync(5_100) })
    expect(view.container.textContent).toContain('agent-a is waiting for you')
    view.unmount()
  })
})
