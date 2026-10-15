import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CopyButton } from './CopyButton'

describe('CopyButton', () => {
  let writeText: ReturnType<typeof vi.fn>
  beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  })

  it('copies, says Copied, and keeps the click from the row it sits in', async () => {
    const onRow = vi.fn()
    render(<div onClick={onRow}><CopyButton text="the path" title="Copy path" label="Copy path" /></div>)
    fireEvent.click(screen.getByRole('button', { name: 'Copy path' }))
    await waitFor(() => expect(screen.getByText('Copied')).toBeInTheDocument())
    expect(writeText).toHaveBeenCalledWith('the path')
    expect(onRow).not.toHaveBeenCalled()
  })

  it('takes the text from a function at the click, and an accessible name of its own', async () => {
    const text = vi.fn(() => 'made late')
    render(<CopyButton text={text} title="tooltip" ariaLabel="Copy: the command" />)
    expect(text).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Copy: the command' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('made late'))
  })

  it('moves nothing on the button when the caller says it another way', async () => {
    const onCopied = vi.fn()
    render(<CopyButton text="x" title="Copy" label="Copy" tick={false} onCopied={onCopied} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    await waitFor(() => expect(onCopied).toHaveBeenCalled())
    expect(screen.queryByText('Copied')).not.toBeInTheDocument()
  })
})
