/**
 * Is the operator typing? A page's window-wide keys (digits, arrows,
 * Backspace, Escape, j/k, Enter) stay away from any field that takes
 * text: an input, a textarea, a select, or anything contenteditable —
 * the page's own field, the topbar search and the Quick note alike.
 */
const FIELD = 'input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]'

/** True when `el` (or an element it sits in) takes typed text. */
export function isTypingElement(el: EventTarget | Element | null | undefined): boolean {
  const node = el as HTMLElement | null | undefined
  if (!node || typeof node.closest !== 'function') return false
  return node.isContentEditable === true || node.closest(FIELD) !== null
}

/** True when a key event was aimed at a field that takes typed text. */
export function isTypingTarget(e: { target: EventTarget | null }): boolean {
  return isTypingElement(e.target)
}
