// @vitest-environment jsdom
import { useRef } from 'react'
import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { topDialog, useModalA11y } from './useModalA11y'

function Dialog({ name, onClose }: { name: string; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useModalA11y(ref, onClose)
  return (
    <div ref={ref} role="dialog" aria-label={name}>
      <button type="button">{name} ok</button>
    </div>
  )
}

describe('useModalA11y', () => {
  afterEach(cleanup)

  it('Escape closes only the top dialog, then the one under it', () => {
    const closeEditor = vi.fn()
    const closeRelease = vi.fn()
    const view = render(
      <>
        <Dialog name="editor" onClose={closeEditor} />
        <Dialog name="release" onClose={closeRelease} />
      </>,
    )
    expect(topDialog()?.getAttribute('aria-label')).toBe('release')

    act(() => { fireEvent.keyDown(document, { key: 'Escape' }) })
    expect(closeRelease).toHaveBeenCalledTimes(1)
    expect(closeEditor).not.toHaveBeenCalled()

    // The top one is gone: the editor owns the keys again.
    view.rerender(<Dialog name="editor" onClose={closeEditor} />)
    expect(topDialog()?.getAttribute('aria-label')).toBe('editor')
    act(() => { fireEvent.keyDown(document, { key: 'Escape' }) })
    expect(closeEditor).toHaveBeenCalledTimes(1)
  })

  it('leaves the stack empty when every dialog is gone', () => {
    const view = render(<Dialog name="one" onClose={() => {}} />)
    view.unmount()
    expect(topDialog()).toBeNull()
  })
})
