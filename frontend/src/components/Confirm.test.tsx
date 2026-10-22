import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Confirm } from './Confirm'

describe('Confirm', () => {
  it('says what happens and names the act on the button', () => {
    const onYes = vi.fn()
    const onNo = vi.fn()
    render(<Confirm text="Delete this item. It cannot be restored." action="Delete" onYes={onYes} onNo={onNo} />)
    expect(screen.getByRole('group', { name: 'Delete' })).toBeInTheDocument()
    expect(screen.getByText('Delete this item. It cannot be restored.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onNo).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onYes).toHaveBeenCalledTimes(1)
  })

  it('holds the act while it runs; Cancel stays', () => {
    render(<Confirm text="x" action="Remove" busy onYes={() => {}} onNo={() => {}} />)
    expect(screen.getByRole('button', { name: 'Remove' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })
})
