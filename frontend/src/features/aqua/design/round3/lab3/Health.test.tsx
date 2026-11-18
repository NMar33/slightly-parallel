import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AquaDesign } from '../../AquaDesign'
import { resetAqua } from '../../store'
import { resetDesk } from '../../round2/desk'
import { resetLab, resetStrip } from '../lab/live'
import {
  AGAIN_MIN, LATER_MIN, breakNow, didIt, finishBreak, dueOf, endBreak, getHealth, later, resetHealth, setHealthSettings, startBreak, tickHealth, zoneOf,
} from './healthModel'

const page = (q = '') => render(<MemoryRouter initialEntries={[`/aqua?v=k${q}`]}><AquaDesign /></MemoryRouter>)
const zone = () => { const h = getHealth(); return zoneOf(h.run, h.s) }

beforeEach(() => {
  try { localStorage.clear() } catch { /* private mode */ }
  resetAqua(); resetDesk(); resetLab(); resetStrip(); resetHealth()
  Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true })
})
afterEach(() => { vi.useRealTimers() })

describe('health: the counter and the zones', () => {
  it('turns yellow at 90 minutes and red at 150, on the minute', () => {
    tickHealth(89); expect(zone()).toBe('green')
    tickHealth(1); expect(zone()).toBe('yellow')
    tickHealth(59); expect(zone()).toBe('yellow')
    tickHealth(1); expect(zone()).toBe('red')
  })

  it('counts the minutes in yellow and in red apart, split exactly at the thresholds', () => {
    const y0 = getHealth().inYellow, r0 = getHealth().inRed
    tickHealth(85); tickHealth(10) // 5 of these 10 are yellow
    expect(getHealth().inYellow - y0).toBe(5)
    tickHealth(60) // 55 more yellow, 5 red
    expect(getHealth().inYellow - y0).toBe(60)
    expect(getHealth().inRed - r0).toBe(5)
  })

  it('a short break pauses the counter; a break of the set length sets it to zero', () => {
    tickHealth(100)
    startBreak(); tickHealth(5); endBreak()
    expect(getHealth().run).toBe(100)
    startBreak(); tickHealth(10); endBreak()
    expect(getHealth().run).toBe(0)
    expect(zone()).toBe('green')
    expect(getHealth().breaks.at(-1)).toMatchObject({ len: 10, reset: true })
  })

  it('the thresholds and the break length follow the settings', () => {
    setHealthSettings({ yellow: 30, red: 40, reset: 3 })
    tickHealth(30); expect(zone()).toBe('yellow')
    tickHealth(10); expect(zone()).toBe('red')
    startBreak(); tickHealth(3); endBreak()
    expect(getHealth().run).toBe(0)
  })

  it('a zone asks at once; «Позже» asks again in 15 minutes, «Сделал» in 30 and logs the action', () => {
    setHealthSettings({ reminders: [] })
    tickHealth(90)
    expect(dueOf(getHealth())).toMatchObject({ kind: 'yellow', act: 'stretch' })
    later()
    expect(dueOf(getHealth())).toBeNull()
    tickHealth(LATER_MIN - 1); expect(dueOf(getHealth())).toBeNull()
    tickHealth(1); expect(dueOf(getHealth())).toMatchObject({ kind: 'yellow' })
    didIt()
    expect(getHealth().done.map((d) => d.act)).toEqual(['stretch'])
    tickHealth(AGAIN_MIN - 1); expect(dueOf(getHealth())).toBeNull()
    tickHealth(1); expect(dueOf(getHealth())).toMatchObject({ kind: 'yellow', act: 'water' })
  })

  it('entering red asks at once even when yellow was put off', () => {
    setHealthSettings({ reminders: [] })
    tickHealth(140); later() // yellow put off till 155
    tickHealth(10)
    expect(dueOf(getHealth())).toMatchObject({ kind: 'red', act: 'walk' })
  })

  it('the pomodoro asks for a break inside the green zone only when on', () => {
    setHealthSettings({ reminders: [] })
    tickHealth(25); expect(dueOf(getHealth())).toBeNull()
    setHealthSettings({ pomo: { on: true, work: 25, rest: 5 } })
    expect(dueOf(getHealth())).toEqual({ kind: 'pomo' })
    didIt() // starts the break
    expect(getHealth().away).not.toBeNull()
    tickHealth(5); endBreak()
    expect(getHealth().pomo).toBe(0)
    expect(getHealth().run).toBe(25)
  })
})

describe('health: reminders on a schedule (tk_caf2b06a)', () => {
  const water = { id: 'w', act: 'water' as const, every: 45, times: 3, pause: 180, on: true }

  it('every 45 min of work; a zone comes before a reminder due at the same time', () => {
    setHealthSettings({ reminders: [water] })
    const due = () => dueOf(getHealth())
    tickHealth(44); expect(due()).toBeNull()
    tickHealth(1); expect(due()).toMatchObject({ kind: 'remind', act: 'water', n: 1 })
    didIt(); tickHealth(45); expect(due()).toMatchObject({ kind: 'yellow' })
    // the zone (yellow at 90) comes first; with it answered the reminder shows
    expect(dueOf({ ...getHealth(), nextAt: Infinity })).toMatchObject({ kind: 'remind', n: 2 })
  })

  it('after the third the long pause, measured in work minutes', () => {
    setHealthSettings({ reminders: [water], yellow: 1000, red: 2000 })
    for (let i = 0; i < 3; i++) { tickHealth(45); expect(dueOf(getHealth())).toMatchObject({ n: i + 1 }); didIt() }
    tickHealth(179); expect(dueOf(getHealth())).toBeNull()
    tickHealth(1); expect(dueOf(getHealth())).toMatchObject({ kind: 'remind', n: 1 })
  })

  it('«Отложить» moves the whole schedule, every reminder, by 15 minutes', () => {
    setHealthSettings({ reminders: [water, { id: 's', act: 'stretch', every: 50, times: 2, pause: 60, on: true }], yellow: 1000, red: 2000 })
    tickHealth(45)
    later()
    tickHealth(14); expect(dueOf(getHealth())).toBeNull() // stretch at 50 moved to 65 too
    tickHealth(1); expect(dueOf(getHealth())).toMatchObject({ act: 'water' })
    didIt(); tickHealth(5); expect(dueOf(getHealth())).toMatchObject({ act: 'stretch' })
  })

  it('«Перерыв» pauses work and project time; «Готово» keeps the note and starts every counter again', () => {
    setHealthSettings({ reminders: [water] })
    tickHealth(100)
    const before = getHealth()
    breakNow()
    tickHealth(7)
    expect(getHealth().day).toBe(before.day)
    expect(getHealth().project).toBe(before.project)
    expect(getHealth().wk).toBe(before.wk)
    finishBreak('  tea and a walk ')
    const h = getHealth()
    expect(h.run).toBe(0)
    expect(h.breaks.at(-1)).toMatchObject({ len: 7, note: 'tea and a walk' })
    tickHealth(44); expect(dueOf(getHealth())).toBeNull()
    tickHealth(1); expect(dueOf(getHealth())).toMatchObject({ kind: 'remind' })
  })
})

describe('health: in J', () => {
  it('d: the popup offers «Сделал», «Перерыв», «Отложить»; Esc postpones; a break shows its window, «Готово» puts the note in the day card', () => {
    setHealthSettings({ yellow: 1000, red: 2000 })
    page('&health=d')
    act(() => { tickHealth(45) })
    const pop = screen.getByRole('dialog', { name: 'Reminder' })
    expect(within(pop).getByRole('button', { name: 'Postpone' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Reminder' })).toBeNull()
    act(() => { tickHealth(15) })
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Reminder' })).getByRole('button', { name: 'Break' }))
    const brk = screen.getByRole('dialog', { name: 'Break' })
    expect(brk.textContent).toContain('Work time and project time are paused.')
    act(() => { tickHealth(12) })
    fireEvent.change(within(brk).getByRole('textbox', { name: 'Note' }), { target: { value: 'walked to the shop' } })
    fireEvent.click(within(brk).getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('dialog', { name: 'Break' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Time without a break: 0:00' }))
    expect(within(screen.getByRole('dialog', { name: 'Time today' })).getByText('walked to the shop')).toBeTruthy()
  })

  it('the fast clock moves the chip from green to yellow to red', () => {
    vi.useFakeTimers()
    page('&health=b&clock=600')
    const chip = () => document.querySelector('[data-health-chip]')!.getAttribute('data-health-chip')
    expect(chip()).toBe('green')
    act(() => { vi.advanceTimersByTime(9000) }) // 90 mock minutes
    expect(chip()).toBe('yellow')
    act(() => { vi.advanceTimersByTime(6000) })
    expect(chip()).toBe('red')
  })

  it('b: the notice offers «Сделал» and «Позже»; «Позже» brings it back 15 minutes later', () => {
    setHealthSettings({ reminders: [] })
    page('&health=b')
    act(() => { tickHealth(90) })
    const toast = screen.getByRole('status')
    expect(toast.getAttribute('data-health-toast')).toBe('yellow')
    fireEvent.click(within(toast).getByRole('button', { name: 'Later' }))
    expect(document.querySelector('[data-health-toast]')).toBeNull()
    act(() => { tickHealth(15) })
    expect(document.querySelector('[data-health-toast]')).toBeTruthy()
    fireEvent.click(within(screen.getByRole('status')).getByRole('button', { name: 'Did it' }))
    expect(document.querySelector('[data-health-toast]')).toBeNull()
    expect(getHealth().done).toHaveLength(1)
  })

  it('a: no chip, no notice; the title row tints and the suggestion shows on hover', () => {
    page('&health=a')
    act(() => { tickHealth(90) })
    expect(document.querySelector('[data-health-chip]')).toBeNull()
    expect(document.querySelector('[data-health-toast]')).toBeNull()
    expect(document.querySelector('[data-health-tint="yellow"]')).toBeTruthy()
    const label = document.querySelector('[data-health-label]')!
    expect(document.querySelector('[data-health-hover]')).toBeNull()
    fireEvent.mouseEnter(label.parentElement!)
    expect(document.querySelector('[data-health-hover]')!.textContent).toContain('stretch')
  })

  it('c: the break card closes with Esc and the red line stays until a break', () => {
    page('&health=c')
    act(() => { tickHealth(150) })
    expect(screen.getByRole('dialog', { name: 'A short break' })).toBeTruthy()
    expect(document.querySelector('[data-health-redline]')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'A short break' })).toBeNull()
    expect(document.querySelector('[data-health-redline]')).toBeTruthy()
    act(() => { startBreak(); tickHealth(10); endBreak() })
    expect(document.querySelector('[data-health-redline]')).toBeNull()
  })

  it('a click on the time opens the day card with the zone minutes; its gear opens the settings', () => {
    page('&health=b')
    act(() => { tickHealth(100) })
    fireEvent.click(screen.getByRole('button', { name: 'Time without a break: 1:40' }))
    const day = screen.getByRole('dialog', { name: 'Time today' })
    expect(within(day).getByText('In the yellow zone').nextElementSibling!.textContent).toBe('30 min')
    fireEvent.click(within(day).getByRole('button', { name: 'Settings' }))
    const set = screen.getByRole('dialog', { name: 'Health and time' })
    fireEvent.change(within(set).getByLabelText('Yellow zone after, min'), { target: { value: '120' } })
    expect(getHealth().s.yellow).toBe(120)
    expect(zone()).toBe('green')
  })

  it('the «Варианты» panel switches the variant and the clock into the address', () => {
    page()
    const panel = screen.getByRole('region', { name: 'Variants' })
    fireEvent.click(within(within(panel).getByRole('radiogroup', { name: 'Health and time' })).getByRole('radio', { name: /^C/ }))
    fireEvent.click(within(within(panel).getByRole('radiogroup', { name: 'Mock clock' })).getByRole('radio', { name: '×600' }))
    expect(within(within(panel).getByRole('radiogroup', { name: 'Health and time' })).getByRole('radio', { name: /^C/ }).getAttribute('aria-checked')).toBe('true')
    expect(within(panel).getByRole('radio', { name: '×600' }).getAttribute('aria-checked')).toBe('true')
    act(() => { tickHealth(150) })
    expect(screen.getByRole('dialog', { name: 'A short break' })).toBeTruthy()
  })
})
