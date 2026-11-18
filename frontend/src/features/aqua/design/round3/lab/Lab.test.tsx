import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AquaDesign } from '../../AquaDesign'
import { SESSIONS } from '../../mock'
import { resetAqua } from '../../store'
import { resetDesk } from '../../round2/desk'
import { resetLab, resetStrip, tickLab } from './live'

const page = (q = '') => render(<MemoryRouter initialEntries={[`/aqua?v=j${q}`]}><AquaDesign /></MemoryRouter>)
const strip = () => screen.getByRole('tablist', { name: 'Chats' })
const tabs = () => within(strip()).getAllByRole('tab')

beforeEach(() => {
  resetAqua(); resetDesk(); resetLab(); resetStrip()
  try { localStorage.clear() } catch { /* private mode */ }
  Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true })
})

describe('J lab: the tabs', () => {
  it('names a tab by the chat\'s own title, not the project', () => {
    page()
    const names = tabs().map((b) => b.textContent)
    expect(names).toContain('hbr-2611-18')
    expect(names.some((n) => n === 'Harbor')).toBe(false)
  })

  it('holding Alt shows the close buttons and the task counts; releasing it hides them', () => {
    page()
    expect(screen.queryByRole('button', { name: 'Close the tab hbr-2611-18' })).toBeNull()
    fireEvent.keyDown(window, { key: 'Alt', altKey: true })
    expect(screen.getByRole('button', { name: 'Close the tab hbr-2611-18' })).toBeTruthy()
    expect(screen.getAllByLabelText('tasks closed: 1 of 5').length).toBeGreaterThan(0)
    fireEvent.keyUp(window, { key: 'Alt' })
    expect(screen.queryByRole('button', { name: 'Close the tab hbr-2611-18' })).toBeNull()
  })

  it('a close in the Alt view removes the tab and selects the next one', () => {
    page()
    const before = tabs().length
    fireEvent.keyDown(window, { key: 'Alt', altKey: true })
    fireEvent.click(screen.getByRole('button', { name: 'Close the tab hbr-2611-18' }))
    fireEvent.keyUp(window, { key: 'Alt' })
    expect(tabs().length).toBe(before - 1)
    expect(tabs().some((b) => b.getAttribute('aria-selected') === 'true')).toBe(true)
  })

  it('Alt view c puts a card under every tab', () => {
    page('&tabs=c')
    fireEvent.keyDown(window, { key: 'Alt', altKey: true })
    expect(document.querySelector('[data-alt="c"]')!.children.length).toBe(tabs().length)
  })

  it('the waiting part of the strip grows as the mock minutes pass', () => {
    page()
    const tab = document.querySelector('[data-lab-tab="cc-b03d55e1"]')!
    const fill = () => (tab.querySelector('[data-strip="a"]')!.lastElementChild!.firstElementChild as HTMLElement).style.width
    const w0 = parseInt(fill(), 10)
    act(() => { for (let i = 0; i < 6; i++) tickLab() })
    expect(parseInt(fill(), 10)).toBeGreaterThan(w0)
  })

  it('the strip settings change the number of parts and the thickness', () => {
    page()
    fireEvent.click(screen.getByRole('button', { name: 'Status strip on the tabs' }))
    const dlg = screen.getByRole('dialog', { name: 'Status strip on the tabs' })
    fireEvent.click(within(within(dlg).getByRole('radiogroup', { name: 'Parts' })).getByRole('radio', { name: '2' }))
    fireEvent.click(within(within(dlg).getByRole('radiogroup', { name: 'Thickness' })).getByRole('radio', { name: '4 px' }))
    const s = document.querySelector('[data-lab-tab] [data-strip="a"]') as HTMLElement
    expect(s.children.length).toBe(2)
    expect(s.style.height).toBe('4px')
  })
})

describe('J lab: the + button', () => {
  it('a plain click opens a new terminal tab at once and selects it', () => {
    page()
    const before = tabs().length
    fireEvent.click(screen.getByRole('button', { name: 'New terminal' }))
    expect(tabs().length).toBe(before + 1)
    expect(tabs().at(-1)!.getAttribute('aria-selected')).toBe('true')
    expect(screen.queryByRole('menu', { name: 'Open a new terminal' })).toBeNull()
  })

  it('Ctrl+click opens the choice instead; a key picks an item', () => {
    page()
    const before = SESSIONS.length
    fireEvent.click(screen.getByRole('button', { name: 'New terminal' }), { ctrlKey: true })
    const menu = screen.getByRole('menu', { name: 'Open a new terminal' })
    expect(within(menu).getByRole('menuitem', { name: /New chat from a board task/ })).toBeTruthy()
    expect(within(menu).getByRole('menuitem', { name: /Plain terminal/ })).toBeTruthy()
    fireEvent.keyDown(window, { key: '3' })
    expect(SESSIONS.length).toBe(before + 1)
    expect(SESSIONS.at(-1)!.name).toMatch(/^bash — /)
    expect(screen.queryByRole('menu', { name: 'Open a new terminal' })).toBeNull()
  })

  it('the ▾ beside it opens the same choice; a sub-list opens in place', () => {
    page('&plusmenu=b')
    fireEvent.click(screen.getByRole('button', { name: 'Choose what to open' }))
    const menu = screen.getByRole('menu', { name: 'Open a new terminal' })
    expect(menu.getAttribute('data-plusmenu')).toBe('b')
    fireEvent.click(within(menu).getByRole('menuitem', { name: /Another agent/ }))
    expect(within(menu).getByRole('menuitem', { name: 'OpenCode' })).toBeTruthy()
  })
})

describe('J lab: switching variants', () => {
  it('takes the variants from the address', () => {
    page('&tabs=b&strip=c&plus=c&plusmenu=b')
    expect(document.querySelector('[data-plus="c"]')).toBeTruthy()
    expect(document.querySelector('[data-strip="c"]')).toBeTruthy()
    const panel = screen.getByRole('region', { name: 'Variants' })
    expect(within(within(panel).getByRole('radiogroup', { name: 'Tabs with Alt' })).getByRole('radio', { checked: true }).textContent).toMatch(/^B/)
  })

  it('a click in the Variants panel switches a variant', () => {
    page()
    expect(document.querySelector('[data-plus="a"]')).toBeTruthy()
    const panel = screen.getByRole('region', { name: 'Variants' })
    fireEvent.click(within(within(panel).getByRole('radiogroup', { name: 'Button +' })).getByRole('radio', { name: /^B/ }))
    expect(document.querySelector('[data-plus="b"]')).toBeTruthy()
    fireEvent.click(within(within(panel).getByRole('radiogroup', { name: 'Strip' })).getByRole('radio', { name: /^B/ }))
    expect(document.querySelector('[data-strip="b"]')).toBeTruthy()
  })
})
