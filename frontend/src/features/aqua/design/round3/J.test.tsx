import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AquaDesign } from '../AquaDesign'
import { resetAqua } from '../store'
import { moveWin, resetDesk } from '../round2/desk'
import { placeSide, seatBoth } from './J'

const page = () => render(<MemoryRouter initialEntries={['/aqua?v=j']}><AquaDesign /></MemoryRouter>)
const frame = () => screen.getByRole('dialog', { name: 'Window: SP Aqua' })
/** A toggle's place on the screen: the window's left plus the toggle's left inside it. */
const at = (side: 'left' | 'right') => {
  const b = frame().querySelector(`[data-toggle="${side}"]`) as HTMLElement
  return parseInt(frame().style.left, 10) + parseInt(b.style.left, 10)
}

beforeEach(() => { resetAqua(); resetDesk(); Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true }) })

describe('J: the sidebar toggles never move', () => {
  it.each([
    ['left, then right', ['left', 'right']],
    ['right, then left', ['right', 'left']],
    ['left on and off', ['left', 'left']],
    ['right, left, right off, left off', ['right', 'left', 'right', 'left']],
  ])('%s', (_, order) => {
    page()
    const start = { l: at('left'), r: at('right') }
    for (const side of order) {
      fireEvent.click(frame().querySelector(`[data-toggle="${side}"]`)!)
      expect(at('left')).toBe(start.l)
      expect(at('right')).toBe(start.r)
    }
  })

  it('at the right screen edge both sidebars open on the left and the toggles stay', () => {
    page()
    act(() => { moveWin('main', 1680 - 1012, 96) })
    const start = { l: at('left'), r: at('right') }
    fireEvent.click(frame().querySelector('[data-toggle="right"]')!)
    fireEvent.click(frame().querySelector('[data-toggle="left"]')!)
    expect(at('left')).toBe(start.l)
    expect(at('right')).toBe(start.r)
    expect(screen.getByRole('complementary', { name: 'Right sidebar' })).toBeTruthy()
  })

  it('in the middle of the screen, left then right: no room for both on their own sides, they are seated again and nothing moves', () => {
    page()
    act(() => { moveWin('main', 400, 96) })
    const start = { l: at('left'), r: at('right') }
    fireEvent.click(frame().querySelector('[data-toggle="left"]')!)
    fireEvent.click(frame().querySelector('[data-toggle="right"]')!)
    expect(at('left')).toBe(start.l)
    expect(at('right')).toBe(start.r)
    expect(parseInt(frame().style.left, 10)).toBe(400 - 340)
  })

  it('places a sidebar on the other side only when its own side has no room, and slides only when neither has', () => {
    const none = { left: null, right: null }
    expect(placeSide(400, 1000, 1680, none, 'left')).toEqual({ pick: 'left', slide: 0 })
    expect(placeSide(668, 1000, 1680, none, 'right').pick).toBe('left')
    // the left one already open on the left: the right one has no room on either side, so the window slides
    expect(placeSide(400, 1000, 1680, { left: 'left', right: null }, 'right')).toEqual({ pick: 'right', slide: -60 })
    // …so both are seated again instead: the left one goes right, the right one left, nothing moves
    expect(seatBoth(400, 1000, 1680)).toEqual({ left: 'right', right: 'left' })
    expect(seatBoth(100, 1000, 1200)).toBeNull()
  })

  it('folds the title row: the close button goes, the toggles become dots at the same places, alt+T brings it back', () => {
    page()
    const l = at('left')
    fireEvent.keyDown(window, { key: 't', altKey: true })
    expect(frame().getAttribute('data-folded')).toBe('true')
    expect(screen.queryByRole('button', { name: 'Fold the title row (alt+T)' })).toBeNull()
    expect(at('left')).toBe(l + 8)
    fireEvent.keyDown(window, { key: 't', altKey: true })
    expect(frame().getAttribute('data-folded')).toBeNull()
  })
})
