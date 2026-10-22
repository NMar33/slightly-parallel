import { useEffect, useRef, type RefObject } from 'react'

/**
 * Accessibility behavior for modal dialogs:
 *   - initial focus moves inside the dialog (respects an autoFocus element)
 *   - Tab / Shift+Tab wrap within the dialog (simple focus trap)
 *   - Escape closes
 *   - focus is restored to the previously focused element on unmount
 *
 * One dialog at a time: dialogs register on a stack, and only the top one
 * handles keys. Two open windows (the task editor with the release window
 * over it) used to both answer Escape, closing both at once.
 *
 * The dialog element itself should carry role="dialog" and aria-modal="true".
 */
const stack: HTMLElement[] = []

/** The dialog that owns the keyboard right now (tests read it). */
export function topDialog(): HTMLElement | null {
  return stack[stack.length - 1] ?? null
}

export function useModalA11y(
  dialogRef: RefObject<HTMLElement | null>,
  onClose: () => void,
) {
  // Keep the latest onClose without re-running the effect (parents typically
  // pass a fresh inline closure every render).
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    stack.push(dialog)
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null

    const getFocusable = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input, select, summary, [tabindex]:not([tabindex="-1"])',
        ),
      )

    // Initial focus — skip if something inside is already focused (autoFocus).
    if (!dialog.contains(document.activeElement)) {
      const first = getFocusable()[0]
      if (first) {
        first.focus()
      } else {
        dialog.tabIndex = -1
        dialog.focus()
      }
    }

    const onKeyDown = (e: KeyboardEvent) => {
      if (topDialog() !== dialog) return
      if (e.key === 'Escape') {
        e.stopImmediatePropagation()
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab') return
      const focusable = getFocusable()
      if (focusable.length === 0) {
        e.preventDefault()
        return
      }
      const first = focusable[0]!
      const last = focusable[focusable.length - 1]!
      const active = document.activeElement
      if (e.shiftKey) {
        if (active === first || !dialog.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else if (active === last || !dialog.contains(active)) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      const at = stack.lastIndexOf(dialog)
      if (at >= 0) stack.splice(at, 1)
      previouslyFocused?.focus()
    }
    // The ref is stable: the dialog is set up once, for the life of the hook.
  }, [dialogRef])
}
