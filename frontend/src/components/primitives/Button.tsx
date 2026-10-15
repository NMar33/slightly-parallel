import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

/**
 * Button — primary / secondary / ghost. Every clickable action in the app
 * uses this OR a Chip. No inline styled <button>.
 *
 *   <Button variant="primary" size="md" onClick={...}>Ship</Button>
 *
 * Accessible: :focus-visible ring (from tokens.css), disabled semantics,
 * keyboard-native.
 */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'text' | 'link' | 'danger-text'
type ButtonSize = 'sm' | 'md' | 'lg' | 'bare'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  iconLeft?: ReactNode
  iconRight?: ReactNode
  loading?: boolean
}

const sizeMap: Record<ButtonSize, string> = {
  sm: 'h-24 px-8 text-12 gap-4',
  md: 'h-32 px-12 text-13 gap-8',
  lg: 'h-48 px-16 text-14 gap-8',
  /** No box of its own — the text variants size themselves. */
  bare: 'gap-4',
}

const variantMap: Record<ButtonVariant, string> = {
  primary:
    'bg-brand text-on-brand border border-brand hover:bg-brand-hover',
  secondary:
    'bg-surface text-primary border border-border-default hover:bg-hover',
  ghost:
    'bg-transparent text-secondary border border-transparent hover:bg-hover hover:text-primary',
  danger:
    'bg-status-red text-on-brand border border-status-red hover:opacity-90',
  /** The mono text action ("copy", "resolve", "show all") — pair with size="bare". */
  text:
    'bg-transparent border-0 text-11 font-mono text-tertiary hover:text-brand',
  /** The brand link that acts ("open the chat →") — pair with size="bare". */
  link:
    'bg-transparent border-0 text-brand hover:underline',
  /** The mono text action whose outcome destroys — pair with size="bare". */
  'danger-text':
    'bg-transparent border-0 text-11 font-mono text-tertiary hover:text-status-red',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    iconLeft,
    iconRight,
    loading = false,
    disabled,
    type = 'button',
    className = '',
    children,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center rounded-input font-medium whitespace-nowrap transition-colors duration-fast ease-out disabled:opacity-50 disabled:cursor-not-allowed ${sizeMap[size]} ${variantMap[variant]} ${className}`.trim()}
      {...rest}
    >
      {iconLeft && <span className="inline-flex shrink-0" aria-hidden="true">{iconLeft}</span>}
      {loading ? <span className="tabular">…</span> : children}
      {iconRight && <span className="inline-flex shrink-0" aria-hidden="true">{iconRight}</span>}
    </button>
  )
})
