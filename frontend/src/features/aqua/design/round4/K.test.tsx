import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AquaDesign } from '../AquaDesign'
import { resetAqua } from '../store'
import { resetDesk } from '../round2/desk'
import { resetLab, resetStrip } from '../round3/lab/live'
import { SCHEMES } from '../round3/lab2/schemes'
import { getLab2, resetLab2 } from '../round3/lab2/store'
import { getHealth, resetHealth } from '../round3/lab3/health'
import { FEATURES } from './compareState'

const page = (q: string) => render(<MemoryRouter initialEntries={[`/aqua${q}`]}><AquaDesign /></MemoryRouter>)
const tiles = () => Array.from(document.querySelectorAll('[data-tile]'))
const tile = (name: string) => screen.getByRole('region', { name })

beforeEach(() => {
  resetAqua(); resetDesk(); resetLab(); resetStrip(); resetLab2(); resetHealth()
  try { localStorage.clear() } catch { /* private mode */ }
  Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true })
})

describe('the round bar', () => {
  it('opens K by default and shows K and J up front, the earlier versions folded', () => {
    page('')
    expect(document.querySelector('.aq[data-v="k"]')).toBeTruthy()
    const bar = screen.getByRole('tablist', { name: 'Variant' })
    expect(within(bar).getAllByRole('tab').map((b) => b.textContent)).toEqual(['K · J + variants 18.11', 'J · Zoom, refined'])
    fireEvent.click(screen.getByRole('button', { name: /Early versions/ }))
    expect(within(bar).getAllByRole('tab')).toHaveLength(11)
  })

  it('unfolds the earlier versions when one of them is open', () => {
    page('?v=c')
    expect(within(screen.getByRole('tablist', { name: 'Variant' })).getByRole('tab', { name: 'C · Spine' })).toBeTruthy()
  })
})

describe('J is as it was before the labs of 18.11', () => {
  it('has no lab panels, no status strip and names a tab by the chat', () => {
    page('?v=j')
    expect(screen.queryByRole('region', { name: 'Variants' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Scheme and message menu' })).toBeNull()
    expect(document.querySelector('[data-strip]')).toBeNull()
    expect(document.querySelector('[data-health-chip]')).toBeNull()
    const names = within(screen.getByRole('tablist', { name: 'Chats' })).getAllByRole('tab').map((b) => b.textContent)
    expect(names).toContain('calendar-overlap')
  })
})

describe('K', () => {
  it('has the labs: the Variants and Scheme panels, the strip, the + and the health chip', () => {
    page('?v=k')
    expect(screen.getByRole('region', { name: 'Variants' })).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Scheme and message menu' })).toBeTruthy()
    expect(document.querySelector('[data-strip]')).toBeTruthy()
    expect(document.querySelector('[data-plus]')).toBeTruthy()
    expect(document.querySelector('[data-health-chip]')).toBeTruthy()
  })

  it('says under each switch how to see it live', () => {
    page('?v=k')
    const panel = screen.getByRole('region', { name: 'Variants' })
    expect(within(panel).getByText('Hold Alt')).toBeTruthy()
    expect(within(panel).getByText('Ctrl+click on +')).toBeTruthy()
    expect(within(panel).getByText('Speed up the clock, or jump to a zone below')).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Scheme and message menu' })).getByText('Right click on a message')).toBeTruthy()
  })
})

describe('K: the compare view', () => {
  it('opens from «Compare» in the Variants panel and closes with Esc', () => {
    page('?v=k')
    fireEvent.click(within(screen.getByRole('region', { name: 'Variants' })).getByRole('button', { name: /^Compare$/ }))
    expect(screen.getByRole('dialog', { name: 'Compare variants' }).getAttribute('data-compare')).toBe('tabs')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Compare variants' })).toBeNull()
  })

  const count: Record<string, number> = { tabs: 4, strip: 3, plus: 5, msgmenu: 3, scheme: SCHEMES.length, health: 13 }
  it.each(FEATURES)('draws every tile of %s', (f) => {
    page(`?v=k&compare=${f}`)
    expect(tiles()).toHaveLength(count[f]!)
    for (const t of tiles()) expect(t.querySelector('[inert]')?.childElementCount).toBeGreaterThan(0)
  })

  it('freezes each variant where it differs', () => {
    page('?v=k&compare=tabs')
    expect(tile('C · cards').querySelector('[data-alt="c"]')).toBeTruthy()
    expect(tile('B · facts').querySelector('[data-alt="b"]')).toBeTruthy()
    act(() => { fireEvent.click(screen.getByRole('tab', { name: 'Button +' })) })
    expect(tile('Menu A · list').querySelector('[data-plusmenu="a"]')).toBeTruthy()
    expect(tile('Menu B · cards').querySelector('[data-plusmenu="b"]')).toBeTruthy()
    act(() => { fireEvent.click(screen.getByRole('tab', { name: 'Message menu' })) })
    expect(tile('A · round').querySelector('.lab-radial')).toBeTruthy()
    expect(tile('B · list').querySelector('.lab-list')).toBeTruthy()
    expect(tile('C · bar').querySelector('.lab-edge')).toBeTruthy()
    act(() => { fireEvent.click(screen.getByRole('tab', { name: 'Health and time' })) })
    expect(tile('C · Red zone').querySelector('[data-health-card="red"]')).toBeTruthy()
    expect(tile('D · Yellow zone').querySelector('[data-health-popup="yellow"]')).toBeTruthy()
    expect(tile('B · Green zone').querySelector('[data-health-toast]')).toBeNull()
    expect(tile('Break').querySelector('[data-health-break]')).toBeTruthy()
  })

  it('«Open live» switches the mockup to the variant and closes the view', () => {
    page('?v=k&compare=tabs')
    fireEvent.click(within(tile('C · cards')).getByRole('button', { name: 'Open live' }))
    expect(screen.queryByRole('dialog', { name: 'Compare variants' })).toBeNull()
    fireEvent.keyDown(window, { key: 'Alt', altKey: true })
    expect(document.querySelector('[data-alt="c"]')).toBeTruthy()
    fireEvent.keyUp(window, { key: 'Alt' })

    fireEvent.click(within(screen.getByRole('region', { name: 'Scheme and message menu' })).getByRole('button', { name: 'Compare the schemes' }))
    fireEvent.click(within(tile('Nord')).getByRole('button', { name: 'Open live' }))
    expect(getLab2().scheme).toBe('nord')

    fireEvent.click(within(screen.getByRole('region', { name: 'Scheme and message menu' })).getByRole('button', { name: 'compare' }))
    fireEvent.click(within(tile('B · list')).getByRole('button', { name: 'Open live' }))
    expect(getLab2().menu).toBe('b')

    fireEvent.click(within(screen.getByRole('region', { name: 'Variants' })).getAllByRole('button', { name: 'compare' }).at(-1)!)
    fireEvent.click(within(tile('D · Red zone')).getByRole('button', { name: 'Open live' }))
    expect(document.querySelector('[data-health-popup="red"]')).toBeTruthy()
    expect(getHealth().run).toBeGreaterThanOrEqual(getHealth().s.red)
  })
})
