import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react'
import { isTypingElement } from '../../lib/typing'

/**
 * Input — text input primitive.
 *
 *   <Input placeholder="Search…" icon={<SearchIcon/>} shortcut="⌘/" bindShortcut />
 *
 * `bindShortcut`: when true, a global keydown listener on `⌘/` or `Ctrl+/`
 * focuses this input (unless focus is already inside a text field). Set only
 * ONE Input per page with bindShortcut — the topbar search (C13).
 *
 * Cyrillic-safe (composition, IME); Enter/Escape bubble up as native events.
 */

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode
  shortcut?: string
  bindShortcut?: boolean
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { icon, shortcut, bindShortcut = false, invalid = false, className = '', ...rest },
  ref,
) {
  const inner = useRef<HTMLInputElement>(null)
  useImperativeHandle(ref, () => inner.current!, [])

  useEffect(() => {
    if (!bindShortcut) return
    const handler = (e: KeyboardEvent) => {
      const trigger = e.key === '/' && (e.metaKey || e.ctrlKey)
      if (!trigger) return
      if (isTypingElement(document.activeElement)) return
      e.preventDefault()
      inner.current?.focus()
      inner.current?.select()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [bindShortcut])

  const borderCls = invalid
    ? 'border-status-red'
    : 'border-border-default focus-within:border-brand'
  return (
    <div
      className={`inline-flex items-center gap-8 rounded-input border ${borderCls} bg-surface h-32 px-8 text-13 text-primary transition-colors duration-fast ease-out ${className}`.trim()}
    >
      {icon && (
        <span className="inline-flex shrink-0 text-tertiary" aria-hidden="true">
          {icon}
        </span>
      )}
      <input
        ref={inner}
        aria-invalid={invalid || undefined}
        {...rest}
        className="flex-1 min-w-0 bg-transparent outline-none placeholder:text-tertiary text-primary"
      />
      {shortcut && (
        <kbd className="text-11 text-tertiary tabular border border-border-default rounded-input px-4 py-4 font-mono">
          {shortcut}
        </kbd>
      )}
    </div>
  )
})
