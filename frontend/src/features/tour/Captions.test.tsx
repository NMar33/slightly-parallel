/**
 * The caption editor: one row per beat that is on, a click on a written
 * caption makes it the shown one, and one voice can be set for the cut.
 */

import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

import { CaptionEditor } from './Captions'
import { LIBRARY, PRESETS, type Beat, type Script } from './script'

const written: Beat['captions'] = [
  { voice: 'xp', title: 'Tasks', text: 'Each card is one task.' },
  { voice: 'sell', title: 'Your work, in one place', text: 'Every task is on one board.' },
  { voice: 'story', title: 'You open the board', text: 'You open Tasks and see every card.' },
  { voice: 'tech', title: 'tasks.csv', text: 'The board reads one CSV file.' },
]

function script(): Script {
  return {
    ...PRESETS[0],
    lead: 2,
    tail: 2,
    beats: [
      { ...LIBRARY[0], id: 'a', hold: 4, on: true, title: 'Tasks', text: 'Each card is one task.', captions: written },
      { ...LIBRARY[1], id: 'b', hold: 4, on: false, title: 'Hidden', text: 'This beat is off.' },
      { ...LIBRARY[2], id: 'c', hold: 4, on: true, title: 'Mine', text: 'Typed by hand.', captions: [] },
    ],
  }
}

function mount(s = script()) {
  const onBeat = vi.fn()
  const onScript = vi.fn()
  const onSeek = vi.fn()
  render(<CaptionEditor script={s} onBeat={onBeat} onScript={onScript} onSeek={onSeek} />)
  return { onBeat, onScript, onSeek }
}

describe('the caption editor', () => {
  it('shows a row for each beat that is on, in order', () => {
    mount()
    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveAccessibleName('Caption for step 1')
    expect(within(rows[1]).getByText('c')).toBeInTheDocument()
  })

  it('marks the shown caption, and "own" when the words match none', () => {
    mount()
    const [first, second] = screen.getAllByRole('listitem')
    expect(within(first).getByRole('button', { name: /^Tasks/ })).toHaveAttribute('aria-pressed', 'true')
    expect(within(first).getByRole('button', { name: /Your work/ })).toHaveAttribute('aria-pressed', 'false')
    expect(within(second).getByText('own')).toBeInTheDocument()
  })

  it('makes a clicked caption the shown one and moves the preview to its beat', () => {
    const { onBeat, onSeek } = mount()
    const first = screen.getAllByRole('listitem')[0]
    fireEvent.click(within(first).getByRole('button', { name: /Your work/ }))
    expect(onBeat).toHaveBeenCalledWith(expect.objectContaining({
      id: 'a', title: 'Your work, in one place', text: 'Every task is on one board.',
    }))
    // Beat a runs from 2 s to 6 s: the preview lands half way.
    expect(onSeek).toHaveBeenCalledWith(4)
  })

  it('edits the shown words directly in the own fields', () => {
    const { onBeat } = mount()
    const second = screen.getAllByRole('listitem')[1]
    fireEvent.change(within(second).getByRole('textbox', { name: 'title' }), { target: { value: 'Mine, again' } })
    expect(onBeat).toHaveBeenCalledWith(expect.objectContaining({ id: 'c', title: 'Mine, again', text: 'Typed by hand.' }))
  })

  it('applies one voice to the whole cut', () => {
    const { onScript } = mount()
    fireEvent.click(within(screen.getByRole('group', { name: 'Voice for all' })).getByRole('button', { name: /Story/ }))
    const change = onScript.mock.calls[0][0] as (s: Script) => Script
    const out = change(script())
    expect(out.voice).toBe('story')
    expect(out.beats[0]).toMatchObject({ title: 'You open the board' })
    expect(out.beats[2]).toMatchObject({ title: 'Mine' })
  })

  it('works when no beat has written captions', () => {
    const s = script()
    s.beats = s.beats.map((b) => ({ ...b, captions: undefined }))
    mount(s)
    expect(screen.queryByRole('group', { name: 'Voice for all' })).toBeNull()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getAllByRole('textbox', { name: 'what to say' })).toHaveLength(2)
  })
})
