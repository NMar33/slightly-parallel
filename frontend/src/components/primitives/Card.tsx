import { forwardRef, type HTMLAttributes, type ReactNode } from 'react'

/**
 * Card — base container. All grouped UI (KPI, project row, decision row, chart
 * frame) composes on Card. Never render a bordered rectangle by hand elsewhere.
 *
 *   <Card padding="md" elevated>...</Card>
 *
 * Padding scale is the 8-point grid; elevated sits on --bg-elevated. A card
 * at rest casts no shadow: only what floats (menus, dialogs) does.
 */

type CardPadding = 'none' | 'sm' | 'md' | 'lg'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padding?: CardPadding
  elevated?: boolean
  interactive?: boolean
  children?: ReactNode
}

const paddingMap: Record<CardPadding, string> = {
  none: '',
  sm:   'p-12',
  md:   'p-16',
  lg:   'p-24',
}

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { padding = 'md', elevated = false, interactive = false, className = '', children, ...rest },
  ref,
) {
  const bg = elevated ? 'bg-elevated' : 'bg-surface'
  const hover = interactive
    ? 'cursor-pointer transition-colors duration-fast ease-out hover:bg-hover'
    : ''
  return (
    <div
      ref={ref}
      className={`rounded-card border border-border-default ${bg} ${paddingMap[padding]} ${hover} ${className}`.trim()}
      {...rest}
    >
      {children}
    </div>
  )
})
