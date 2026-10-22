import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import { ThenSteps } from './ThenSteps'

function Harness({ steps }: { steps: string[] }) {
  const [thenSteps, setThenSteps] = useState(steps)
  return <ThenSteps title="first" thenSteps={thenSteps} setThenSteps={setThenSteps} />
}

describe('the "then" steps of a new task', () => {
  it('removing a middle step leaves the others in their own fields', () => {
    render(<Harness steps={['alpha', 'beta', 'gamma']} />)
    const gamma = screen.getByDisplayValue('gamma')
    gamma.focus()
    fireEvent.click(screen.getByRole('button', { name: 'Remove step 3' }))
    expect(screen.queryByDisplayValue('beta')).toBeNull()
    // The same field, not the removed step's field re-used for this text —
    // so the keyboard is still where it was.
    expect(screen.getByDisplayValue('gamma')).toBe(gamma)
    expect(document.activeElement).toBe(gamma)
  })

  it('Backspace on an empty step removes it and goes back to the one above', () => {
    render(<Harness steps={['alpha', '', 'gamma']} />)
    const empty = screen.getByLabelText('Step 3 of the stack')
    empty.focus()
    fireEvent.keyDown(empty, { key: 'Backspace' })
    expect(screen.getAllByRole('textbox').map((el) => (el as HTMLInputElement).value)).toEqual(['alpha', 'gamma'])
    expect(document.activeElement).toBe(screen.getByDisplayValue('alpha'))
  })
})
