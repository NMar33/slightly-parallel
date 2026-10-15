import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

/**
 * IconButton — the one square icon action: 24×24, rounded-input, tertiary
 * ink that wakes on hover. `label` is both the accessible name and the
 * tooltip. `danger` for the ones that destroy; `active` for a toggle that
 * is on.
 */
interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string
  danger?: boolean
  active?: boolean
  size?: 16 | 20 | 24
  children: ReactNode
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, danger = false, active = false, size = 24, type = 'button', className = '', children, ...rest },
  ref,
) {
  const box = size === 16 ? 'w-16 h-16' : size === 20 ? 'w-20 h-20' : 'w-24 h-24'
  return (
    <button
      ref={ref}
      type={type}
      title={label}
      aria-label={label}
      aria-pressed={active || undefined}
      className={`${box} inline-flex items-center justify-center rounded-input shrink-0 transition-colors duration-fast ease-out disabled:opacity-40 ${
        active ? 'bg-brand-glow text-brand' : `text-tertiary hover:bg-hover ${danger ? 'hover:text-status-red' : 'hover:text-primary'}`
      } ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
})
