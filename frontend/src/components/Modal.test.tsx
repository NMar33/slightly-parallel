import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Modal } from './Modal'

describe('Modal', () => {
  it('closes on a click on the backdrop, not on a press inside released outside', () => {
    const onClose = vi.fn()
    render(<Modal label="Edit" onClose={onClose}><textarea aria-label="text" defaultValue="some words" /></Modal>)
    const scrim = screen.getByRole('presentation')
    // A text selection that starts in the dialog and ends on the backdrop.
    fireEvent.mouseDown(screen.getByLabelText('text'))
    fireEvent.click(scrim)
    expect(onClose).not.toHaveBeenCalled()
    // A plain click on the backdrop.
    fireEvent.mouseDown(scrim)
    fireEvent.click(scrim)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
