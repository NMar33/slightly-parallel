import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { AquaDesign } from '../../AquaDesign'
import { resetAqua } from '../../store'
import { resetDesk } from '../../round2/desk'
import { blocksOf, type ScreenLine } from '../../term'
import { SCHEMES, contrast, ratios } from './schemes'
import { resetLab2, setMenu } from './store'

const page = (q = '') => render(<MemoryRouter initialEntries={[`/aqua?v=k${q}`]}><AquaDesign /></MemoryRouter>)
const desk = () => document.querySelector('[data-scheme]') as HTMLElement
const varOf = (name: string) => desk().style.getPropertyValue(name)
const blocks = (who: 'you' | 'agent') => [...document.querySelectorAll(`.lab-block[data-who="${who}"]`)] as HTMLElement[]

beforeEach(() => { resetAqua(); resetDesk(); resetLab2(); Object.defineProperty(window, 'innerWidth', { value: 1680, configurable: true }) })

describe('colour schemes', () => {
  it('the contrast is the WCAG ratio', () => {
    expect(contrast('#000000', '#FFFFFF')).toBeCloseTo(21, 5)
    expect(contrast('#777777', '#FFFFFF')).toBeCloseTo(4.48, 2)
  })

  it('every scheme has 16 colours and readable text; the ones made for SP reach AA everywhere', () => {
    for (const s of SCHEMES) {
      expect(s.ansi).toHaveLength(16)
      expect(ratios(s).text).toBeGreaterThanOrEqual(4)
    }
    for (const s of SCHEMES.filter((x) => x.sp && x.id !== 'sp-now')) {
      const r = ratios(s)
      expect(r.text).toBeGreaterThanOrEqual(7)
      expect(r.dim).toBeGreaterThanOrEqual(4.5)
      expect(r.colours).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('a click in the picker recolours the terminal, and "the whole window" the window too', () => {
    page()
    const picker = screen.getByRole('radiogroup', { name: 'Scheme' })
    fireEvent.click(within(picker).getByRole('radio', { name: /^Nord/ }))
    expect(desk().dataset.scheme).toBe('nord')
    expect(varOf('--aq-term-bg')).toBe('#2E3440')
    expect(varOf('--ansi-2')).toBe('#A3BE8C')
    expect(varOf('--bg-base')).toBe('')
    fireEvent.click(screen.getByRole('radio', { name: 'whole window' }))
    expect(varOf('--bg-base')).toBe('#2E3440')
    expect(varOf('--aq-panel')).not.toBe('')
    // the picker prints the contrast of text on background
    expect(within(picker).getByRole('radio', { name: /^Nord/ }).textContent).toContain('9.2 AAA')
  })

  it('the address picks the scheme and the menu', () => {
    page('&scheme=dracula&msgmenu=b&scope=window')
    expect(desk().dataset.scheme).toBe('dracula')
    expect(varOf('--aq-term-fg')).toBe('#F8F8F2')
    expect(desk().dataset.scope).toBe('window')
    expect(screen.getByRole('radio', { name: 'b · list' }).getAttribute('aria-checked')).toBe('true')
  })

  it('the output carries ANSI colours: passes green, the failure red', () => {
    page()
    const term = document.querySelector('.aq-term[data-lab]')!
    expect(term.querySelectorAll('.a-f2').length).toBeGreaterThan(0)
    expect(term.querySelectorAll('.a-f1').length).toBeGreaterThan(0)
    expect(term.textContent).not.toContain('\x1b')
  })
})

describe('message blocks', () => {
  it('group the operator\'s messages and the agent\'s replies', () => {
    const lines: ScreenLine[] = [
      { k: 'you', text: 'one' }, { k: 'say', text: 'two' }, { k: 'tool', name: 'Read', arg: 'a.ts' }, { k: 'compact', text: 'c' }, { k: 'you', text: 'three' },
    ]
    const b = blocksOf(lines, 's')
    expect(b.map((x) => x.block?.who ?? null)).toEqual(['you', 'agent', null, 'you'])
    expect(b[1]!.block!.text).toBe('two')
    expect(b[1]!.to).toBe(3)
  })
})

describe('the message menu', () => {
  it('a · round: a right click opens the ring; Pin pins, and carry offers word for word', () => {
    page('&msgmenu=a')
    const b = blocks('you')[0]!
    fireEvent.contextMenu(b, { clientX: 300, clientY: 300 })
    const menu = screen.getByRole('menu', { name: 'Your message' })
    expect(menu.className).toContain('lab-radial')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Pin' }))
    expect(b.dataset.pinned).toBe('true')
    expect(screen.getByRole('status').textContent).toBe('Message pinned')
    fireEvent.contextMenu(b, { clientX: 300, clientY: 300 })
    const again = screen.getByRole('menu', { name: 'Your message' })
    fireEvent.click(within(again).getByRole('menuitem', { name: 'Carry after compaction' }))
    fireEvent.click(within(again).getByRole('menuitem', { name: 'Carry after compaction: word for word' }))
    expect(within(b).getByLabelText('Marks').textContent).toContain('word for word')
  })

  it('b · list: Branch into a new window says so; Make a task puts the task on the block', () => {
    page('&msgmenu=b')
    const b = blocks('agent')[0]!
    fireEvent.contextMenu(b, { clientX: 200, clientY: 200 })
    const menu = screen.getByRole('menu', { name: 'Agent\'s reply' })
    expect(menu.className).toContain('lab-list')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Branch into a new window' }))
    expect(screen.getByRole('status').textContent).toBe('Branch opened in a new window')
    fireEvent.contextMenu(b, { clientX: 200, clientY: 200 })
    fireEvent.click(within(screen.getByRole('menu')).getByRole('menuitem', { name: 'Make a task' }))
    expect(within(b).getByLabelText('Marks').textContent).toMatch(/tk_[0-9a-f]{8}/)
  })

  it('c · bar: pointing at a message shows its buttons; Hand over later marks it', () => {
    page('&msgmenu=c')
    const b = blocks('you')[0]!
    fireEvent.contextMenu(b)
    expect(screen.queryByRole('menu')).toBeNull()
    fireEvent.mouseEnter(b)
    const bar = within(b).getByRole('toolbar')
    fireEvent.click(within(bar).getByRole('button', { name: 'Hand over later' }))
    expect(within(b).getByLabelText('Marks').textContent).toContain('later')
  })

  it.each(['a', 'b', 'c'] as const)('%s: a click on a task id opens the task menu; a column changes the chip', (v) => {
    page()
    act(() => setMenu(v))
    const chip = [...document.querySelectorAll('.aq-term .task')].find((x) => x.textContent === 'tk_93d0a5f7') as HTMLElement
    expect(chip.dataset.column).toBe('todo')
    fireEvent.click(chip, { clientX: 300, clientY: 300 })
    const menu = screen.getByRole('menu', { name: 'tk_93d0a5f7' })
    const done = within(menu).queryByRole('menuitemradio', { name: 'done' }) ?? within(menu).getByRole('menuitem', { name: 'done' })
    fireEvent.click(done)
    const after = [...document.querySelectorAll('.aq-term .task')].find((x) => x.textContent === 'tk_93d0a5f7') as HTMLElement
    expect(after.dataset.column).toBe('done')
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('Escape closes an open menu', () => {
    page('&msgmenu=b')
    fireEvent.contextMenu(blocks('you')[0]!, { clientX: 200, clientY: 200 })
    expect(screen.getByRole('menu')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()
  })
})
