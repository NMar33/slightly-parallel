import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PillRow } from './PillRow'

const OPTIONS = [['a', 'Alpha'], ['b', 'Beta', 'the second']] as const

describe('PillRow', () => {
  it('is a named radiogroup whose pills are radios, the value checked', () => {
    render(<PillRow label="Pick one" value="b" onChange={() => {}} options={[...OPTIONS]} />)
    expect(screen.getByRole('radiogroup', { name: 'Pick one' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Alpha' })).toHaveAttribute('aria-checked', 'false')
    const beta = screen.getByRole('radio', { name: 'Beta' })
    expect(beta).toHaveAttribute('aria-checked', 'true')
    expect(beta).toHaveAttribute('title', 'the second')
  })

  it('picks the pill that is clicked', () => {
    const onChange = vi.fn()
    render(<PillRow label="Pick one" value="" onChange={onChange} options={[...OPTIONS]} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Alpha' }))
    expect(onChange).toHaveBeenCalledWith('a')
  })

  it('clears on a second click only when clearable', () => {
    const onChange = vi.fn()
    const { rerender } = render(<PillRow label="Pick one" value="a" onChange={onChange} options={[...OPTIONS]} clearable />)
    fireEvent.click(screen.getByRole('radio', { name: 'Alpha' }))
    expect(onChange).toHaveBeenLastCalledWith('')
    rerender(<PillRow label="Pick one" value="a" onChange={onChange} options={[...OPTIONS]} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Alpha' }))
    expect(onChange).toHaveBeenLastCalledWith('a')
  })
})
