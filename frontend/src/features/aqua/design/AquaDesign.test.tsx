import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AquaDesign, VARIANTS } from './AquaDesign'
import { MESSAGES, SESSIONS } from './mock'
import { Messages } from './parts'
import { getAqua, projectAsleep, reboot, resetAqua, restoreAll, setProjectAsleep } from './store'

const page = (q: string) => render(<MemoryRouter initialEntries={[`/aqua?${q}`]}><AquaDesign /></MemoryRouter>)

beforeEach(() => { resetAqua() })
afterEach(() => { vi.useRealTimers() })

describe('the SP Aqua design round', () => {
  it.each(VARIANTS.map((v) => v.key))('draws variant %s with the session terminal and the variant switch', (k) => {
    page(`v=${k}`)
    expect(screen.getByRole('tablist', { name: 'Variant' })).toBeTruthy()
    expect(document.querySelector(`.aq[data-v="${k}"]`)).toBeTruthy()
    expect(screen.getAllByText(/auto mode on/).length).toBeGreaterThan(0)
  })

  it('opens the command palette with Ctrl+K and goes to a chat found by a few letters', () => {
    page('v=a')
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const box = screen.getByRole('dialog', { name: 'Command palette' })
    fireEvent.change(within(box).getByRole('textbox'), { target: { value: 'release-0.9' } })
    fireEvent.keyDown(within(box).getByRole('textbox'), { key: 'Enter' })
    expect(getAqua().active).toBe('cc-2a6e0d93')
  })

  it('puts a whole project to sleep, its chats and its servers, and wakes it again', () => {
    setProjectAsleep('harbor', true)
    expect(projectAsleep(getAqua(), 'harbor')).toBe(true)
    expect(getAqua().up.ew_h1).toBe(false)
    setProjectAsleep('harbor', false)
    expect(getAqua().asleep['cc-4e7a19d2']).toBe(false)
    expect(getAqua().up.ew_h1).toBe(true)
  })

  it('pins, makes a task and queues a fork from a message with its keys', () => {
    render(<Messages sessionId="cc-4e7a19d2" />)
    const row = screen.getByRole('listitem', { name: MESSAGES.find((m) => m.id === 'm5')!.text })
    fireEvent.keyDown(row, { key: 'p' })
    fireEvent.keyDown(row, { key: 't' })
    fireEvent.keyDown(row, { key: 'f' })
    const st = getAqua()
    expect(st.pinned.m5).toBe(true)
    expect(st.tasked.m5).toMatch(/^tk_[0-9a-f]{8}$/)
    expect(st.forkLater.m5).toBe(true)
  })

  it('restores after a reboot: every chat that was awake comes back, the one whose id is gone fails', () => {
    vi.useFakeTimers()
    reboot()
    expect(SESSIONS.every((s) => getAqua().asleep[s.id])).toBe(true)
    act(() => { restoreAll() })
    act(() => { vi.advanceTimersByTime(10_000) })
    const st = getAqua()
    expect(st.asleep['cc-4e7a19d2']).toBe(false)
    expect(st.restore!['cx-3c8f1b52']).toBe('fail')
    expect(st.asleep['cc-8b1e6f04']).toBe(true)
  })

  it('shows a detached terminal as a window of its own and a placeholder in its place', () => {
    page('v=a')
    fireEvent.click(screen.getAllByRole('button', { name: 'Detach' })[0]!)
    expect(screen.getByRole('dialog', { name: /Detached window/ })).toBeTruthy()
    expect(screen.getByText('In its own window')).toBeTruthy()
  })
})
