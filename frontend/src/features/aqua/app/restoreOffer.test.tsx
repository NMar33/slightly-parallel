import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RestoreOffer } from './restoreOffer'

type W = { spWindow?: unknown }
const posted: unknown[] = []
function inWindow(offer: number | (() => Promise<number>)) {
  (window as unknown as W).spWindow = {
    postMessage: (m: unknown) => { posted.push(m) },
    restoreOffer: typeof offer === 'function' ? offer : () => Promise.resolve(offer),
  }
}

afterEach(() => { delete (window as unknown as W).spWindow; posted.length = 0 })

describe('the main window asks about the windows of last time', () => {
  it('asks with their number; Yes tells the window to open them and the question goes', async () => {
    inWindow(3)
    const refocus = vi.fn()
    render(<RestoreOffer refocus={refocus} />)
    expect(await screen.findByText('Open the 3 windows that were open last time?')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))
    expect(posted).toEqual([{ op: 'restore', open: true }])
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(refocus).toHaveBeenCalled()
  })

  it('one window reads as one; No tells the window to let it go', async () => {
    inWindow(1)
    render(<RestoreOffer />)
    expect(await screen.findByText('Open the window that was open last time?')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'No' }))
    expect(posted).toEqual([{ op: 'restore', open: false }])
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  it('shows nothing when nothing waits, in a browser, or when the window fails to answer', async () => {
    inWindow(0)
    const { unmount } = render(<RestoreOffer />)
    await Promise.resolve()
    expect(screen.queryByRole('alertdialog')).toBeNull()
    unmount()
    delete (window as unknown as W).spWindow
    const b = render(<RestoreOffer />)
    await Promise.resolve()
    expect(screen.queryByRole('alertdialog')).toBeNull()
    b.unmount()
    inWindow(() => Promise.reject(new Error('no main window')))
    render(<RestoreOffer />)
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(posted).toEqual([])
  })
})
