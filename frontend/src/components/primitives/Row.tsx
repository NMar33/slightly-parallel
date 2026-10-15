import { forwardRef, type HTMLAttributes, type ReactNode } from 'react'

/**
 * Row — horizontal flex primitive. `gap` maps to the 8-point token scale.
 *
 *   <Row gap="12" align="center" justify="between">...</Row>
 */

type RowGap = '0' | '4' | '8' | '12' | '16' | '24' | '32'
type RowAlign = 'start' | 'center' | 'end' | 'baseline' | 'stretch'
type RowJustify = 'start' | 'center' | 'end' | 'between' | 'around'

interface RowProps extends HTMLAttributes<HTMLDivElement> {
  gap?: RowGap
  align?: RowAlign
  justify?: RowJustify
  wrap?: boolean
  children?: ReactNode
}

const gapMap: Record<RowGap, string> = {
  '0':  'gap-0',
  '4':  'gap-4',
  '8':  'gap-8',
  '12': 'gap-12',
  '16': 'gap-16',
  '24': 'gap-24',
  '32': 'gap-32',
}
const alignMap: Record<RowAlign, string> = {
  start:    'items-start',
  center:   'items-center',
  end:      'items-end',
  baseline: 'items-baseline',
  stretch:  'items-stretch',
}
const justifyMap: Record<RowJustify, string> = {
  start:   'justify-start',
  center:  'justify-center',
  end:     'justify-end',
  between: 'justify-between',
  around:  'justify-around',
}

export const Row = forwardRef<HTMLDivElement, RowProps>(function Row(
  { gap = '8', align = 'center', justify = 'start', wrap = false, className = '', children, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={`flex ${wrap ? 'flex-wrap' : ''} ${gapMap[gap]} ${alignMap[align]} ${justifyMap[justify]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </div>
  )
})
