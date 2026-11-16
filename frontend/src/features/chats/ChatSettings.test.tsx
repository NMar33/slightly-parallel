import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ChatSettings } from './ChatSettings'
import type { ChatsPrefs } from './prefs'

const PREFS: ChatsPrefs = { width: 'even', list: 12, chat: 12, order: 'oldest', md: true, work: true, usage: true }

describe('ChatSettings', () => {
  it('has a row for usage on a turn with its second line', () => {
    const onChange = vi.fn()
    render(<ChatSettings prefs={PREFS} onChange={onChange} />)
    expect(screen.getByText('Usage on a turn')).toBeTruthy()
    expect(screen.getByText('Tokens of each reply. Hover the numbers for the detail.')).toBeTruthy()
    const hides = screen.getAllByRole('button', { name: 'hide' })
    fireEvent.click(hides[hides.length - 1]!)
    expect(onChange).toHaveBeenCalledWith({ ...PREFS, usage: false })
  })
})
