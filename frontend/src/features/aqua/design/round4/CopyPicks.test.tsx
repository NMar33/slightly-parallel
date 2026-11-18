import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AquaDesign } from '../AquaDesign'
import { getAqua, resetAqua } from '../store'
import { resetDesk } from '../round2/desk'
import { resetLab, resetStrip } from '../round3/lab/live'
import { getLab2, resetLab2 } from '../round3/lab2/store'
import { resetHealth } from '../round3/lab3/healthModel'
import { picksText, picksUrl, type Picks } from './CopyPicks'

const page = (q: string) => render(<MemoryRouter initialEntries={[`/aqua${q}`]}><AquaDesign /></MemoryRouter>)
const variants = () => screen.getByRole('region', { name: 'Variants' })
const schemePanel = () => screen.getByRole('region', { name: 'Scheme and message menu' })
const tile = (name: string) => screen.getByRole('region', { name })

const PICKS: Picks = { lab: { tabs: 'b', strip: 'a', plus: 'c', plusmenu: 'a' }, menu: 'a', scheme: 'tokyo-night', scope: 'window', health: 'd', clock: 60 }

let fetchSpy: ReturnType<typeof vi.fn>
beforeEach(() => {
  resetAqua(); resetDesk(); resetLab(); resetStrip(); resetLab2(); resetHealth()
  try { localStorage.clear() } catch { /* private mode */ }
  Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true })
  fetchSpy = vi.fn(async () => new Response('{}'))
  vi.stubGlobal('fetch', fetchSpy)
})
afterEach(() => { vi.unstubAllGlobals() })

function clipboard(writeText: (s: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn(writeText) }, configurable: true })
  return navigator.clipboard.writeText as ReturnType<typeof vi.fn>
}

describe('the copied text', () => {
  it('has a head line, one line per switch and the address that reopens the state', () => {
    const url = picksUrl('http://127.0.0.1:8123', '/aqua', new URLSearchParams('v=k&compare=tabs&work=30'), PICKS)
    expect(picksText(PICKS, url)).toBe([
      'Picks in mockup K (/aqua?v=k):',
      'Tabs with Alt: b — facts',
      'Strip: a — segments',
      'Button +: c — pill',
      'Menu +: a — list',
      'Message menu: a — round',
      'Scheme: Tokyo Night, whole window',
      'Health and time: d — popup, mock clock ×60',
      'http://127.0.0.1:8123/aqua?v=k&work=30&tabs=b&strip=a&plus=c&plusmenu=a&msgmenu=a&scheme=tokyo-night&scope=window&health=d&clock=60',
    ].join('\n'))
  })
})

describe('«Copy the picks»', () => {
  it('copies the current picks from the Variants panel and says so', async () => {
    const write = clipboard(async () => {})
    page('?v=k&tabs=b&plus=c&health=d&clock=60&scheme=tokyo-night&scope=window')
    await act(async () => { fireEvent.click(within(variants()).getByRole('button', { name: 'Copy the picks' })) })
    const text = write.mock.calls[0]![0] as string
    expect(text.split('\n')).toEqual(expect.arrayContaining([
      'Tabs with Alt: b — facts', 'Button +: c — pill', 'Scheme: Tokyo Night, whole window', 'Health and time: d — popup, mock clock ×60',
    ]))
    expect(text.split('\n').at(-1)).toMatch(/\/aqua\?v=k&tabs=b&plus=c&health=d&clock=60&scheme=tokyo-night&scope=window&strip=a&plusmenu=a&msgmenu=a$/)
    expect(getAqua().flash?.text).toBe('Copied')
    expect(document.querySelector('[data-copy-box]')).toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('copies the same text from the Scheme panel', async () => {
    const write = clipboard(async () => {})
    page('?v=k&strip=c')
    await act(async () => { fireEvent.click(within(variants()).getByRole('button', { name: 'Copy the picks' })) })
    await act(async () => { fireEvent.click(within(schemePanel()).getByRole('button', { name: 'Copy the picks' })) })
    expect(write.mock.calls[1]![0]).toBe(write.mock.calls[0]![0])
    expect(write.mock.calls[0]![0]).toContain('Strip: c — dots')
  })

  it('shows the text selected in a box when the browser refuses the clipboard', async () => {
    clipboard(async () => { throw new Error('denied') })
    page('?v=k')
    await act(async () => { fireEvent.click(within(variants()).getByRole('button', { name: 'Copy the picks' })) })
    const box = within(variants()).getByRole('textbox', { name: 'Picks' }) as HTMLTextAreaElement
    expect(box.value.startsWith('Picks in mockup K (/aqua?v=k):\nTabs with Alt: a — inline')).toBe(true)
    expect(document.activeElement).toBe(box)
    expect([box.selectionStart, box.selectionEnd]).toEqual([0, box.value.length])
    fireEvent.click(within(variants()).getByRole('button', { name: 'Close' }))
    expect(document.querySelector('[data-copy-box]')).toBeNull()
  })
})

describe('«Choose this variant» in the compare view', () => {
  it('switches the live pick, stays in the view and marks the tile', () => {
    page('?v=k&compare=tabs')
    expect(within(tile('A · inline')).getByText('chosen')).toBeTruthy()
    fireEvent.click(within(tile('C · cards')).getByRole('button', { name: 'Choose this variant' }))
    expect(screen.getByRole('dialog', { name: 'Compare variants' })).toBeTruthy()
    expect(within(tile('C · cards')).getByText('chosen')).toBeTruthy()
    expect(within(tile('A · inline')).getByRole('button', { name: 'Choose this variant' })).toBeTruthy()
    // the Variants panel follows
    expect(within(variants()).getByRole('radiogroup', { name: 'Tabs with Alt' }).querySelector('[aria-checked="true"]')?.textContent).toContain('C')
    // «Without Alt» is no variant
    expect(within(tile('Without Alt')).queryByRole('button', { name: 'Choose this variant' })).toBeNull()
  })

  it('picks a scheme, a message menu and a health look the same way', () => {
    page('?v=k&compare=scheme')
    fireEvent.click(within(tile('Nord')).getByRole('button', { name: 'Choose this variant' }))
    expect(getLab2().scheme).toBe('nord')
    expect(within(tile('Nord · now')).getByText('chosen')).toBeTruthy()
    act(() => { fireEvent.click(screen.getByRole('tab', { name: 'Message menu' })) })
    fireEvent.click(within(tile('C · bar')).getByRole('button', { name: 'Choose this variant' }))
    expect(getLab2().menu).toBe('c')
    act(() => { fireEvent.click(screen.getByRole('tab', { name: 'Health and time' })) })
    fireEvent.click(within(tile('D · Red zone')).getByRole('button', { name: 'Choose this variant' }))
    expect(within(tile('D · Green zone')).getByText('chosen')).toBeTruthy()
    expect(within(variants()).getByRole('radiogroup', { name: 'Health and time' }).querySelector('[aria-checked="true"]')?.textContent).toContain('D')
    expect(screen.getByRole('dialog', { name: 'Compare variants' })).toBeTruthy()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
