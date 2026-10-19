import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import QuickNotePanel from './QuickNotePanel'

describe('QuickNotePanel', () => {
  // The button named a `close` it could not see and called window.close():
  // the note stayed open and the last keystrokes waited for the timer.
  it('closes from its close button, with the note written first', () => {
    const onClose = vi.fn()
    const winClose = vi.spyOn(window, 'close').mockImplementation(() => {})
    render(<QuickNotePanel within={createRef<HTMLElement>()} onText={() => {}} onClose={onClose} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'buy milk' } })
    fireEvent.click(screen.getByRole('button', { name: 'close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(winClose).not.toHaveBeenCalled()
    expect(localStorage.getItem('sp-quick-note')).toBe('buy milk')
  })
})
