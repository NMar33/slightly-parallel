/**
 * The card picker: folded until opened, one thumbnail per hand, a click
 * names the hand in the script and scrubs the preview to that card.
 */

import { beforeAll, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

import { BookendPicker, endingAt, openingAt } from './BookendPicker'
import { ENDINGS, OPENINGS, PRESETS, type Script } from './script'
import type { Look } from './media'

const look: Look = { face: 'sans', footer: true, bookends: true, highlight: true }

beforeAll(() => {
  // jsdom draws nothing: the thumbnails skip their paint and stay buttons.
  HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as unknown as typeof HTMLCanvasElement.prototype.getContext
})

function mount(s: Script = { ...PRESETS[0], opening: 'sheet', ending: 'recap' }) {
  const onScript = vi.fn()
  const onSeek = vi.fn()
  render(<BookendPicker script={s} look={look} onScript={onScript} onSeek={onSeek} />)
  return { s, onScript, onSeek }
}

describe('the card picker', () => {
  it('starts folded, naming the chosen hands', () => {
    mount()
    const toggle = screen.getByRole('button', { expanded: false })
    expect(toggle).toHaveTextContent('Drawing sheet · Recap')
    expect(screen.queryByRole('radiogroup')).toBeNull()
  })

  it('unfolds to one thumbnail per hand, the chosen ones pressed', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { expanded: false }))
    const [opening, ending] = screen.getAllByRole('radiogroup')
    expect(within(opening).getAllByRole('button')).toHaveLength(OPENINGS.length)
    expect(within(ending).getAllByRole('button')).toHaveLength(ENDINGS.length)
    expect(within(opening).getByRole('button', { pressed: true })).toHaveTextContent('Drawing sheet')
    expect(within(ending).getByRole('button', { pressed: true })).toHaveTextContent('Recap')
  })

  it('a click names the hand and scrubs to its card', () => {
    const { s, onScript, onSeek } = mount()
    fireEvent.click(screen.getByRole('button', { expanded: false }))
    const [opening, ending] = screen.getAllByRole('radiogroup')
    fireEvent.click(within(opening).getByRole('button', { name: /Two stems/ }))
    expect(onScript).toHaveBeenCalledTimes(1)
    expect(onScript.mock.calls[0][0](s).opening).toBe('stems')
    expect(onSeek).toHaveBeenLastCalledWith(openingAt(s))
    fireEvent.click(within(ending).getByRole('button', { name: /Statement/ }))
    expect(onScript.mock.calls[1][0](s).ending).toBe('quote')
    expect(onSeek).toHaveBeenLastCalledWith(endingAt(s))
    expect(endingAt(s)).toBeGreaterThan(openingAt(s))
  })
})
