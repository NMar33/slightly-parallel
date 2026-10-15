import { forwardRef, type HTMLAttributes, type ReactNode } from 'react'

/**
 * Badge — small status pill. Semantic tone, not decorative. Every distinct
 * status in the app maps to one Tone value here. If you need a new tone,
 * add it here — do NOT color a badge by hand elsewhere.
 *
 *   <Badge tone="done">done</Badge>
 *
 * Tones (§6.1 status palette; §Vision statuses):
 *   done      → --status-green
 *   active    → --brand
 *   blocked   → --status-red
 *   idle      → --status-neutral (muted)
 *   explicit  → --status-info    (decision source = human)
 *   auto      → --status-amber   (decision source = agent-inferred)
 *   info      → --status-info
 *   warning   → --status-amber
 *   error     → --status-red
 *   neutral   → --status-neutral
 */

export type BadgeTone =
  | 'done'
  | 'active'
  | 'blocked'
  | 'idle'
  | 'explicit'
  | 'auto'
  | 'info'
  | 'warning'
  | 'error'
  | 'neutral'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone
  dot?: boolean
  children?: ReactNode
}

/* text- classes are our extended color names, resolving to CSS vars. Bg is a
   tinted overlay via inline style so we don't blow up the tokens with 10 more
   "-bg" variants — one formula, one place. */
const toneVar: Record<BadgeTone, string> = {
  done:     '--status-green',
  active:   '--brand',
  blocked:  '--status-red',
  idle:     '--status-neutral',
  explicit: '--status-info',
  auto:     '--status-amber',
  info:     '--status-info',
  warning:  '--status-amber',
  error:    '--status-red',
  neutral:  '--status-neutral',
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  { tone = 'neutral', dot = false, className = '', children, style, ...rest },
  ref,
) {
  const v = toneVar[tone]
  const styles: React.CSSProperties = {
    // The ink: the light theme's darker shade of the hue, so the word reads
    // on its own tint (tokens.css, --*-ink); the hue itself in the dark.
    color: `var(${v}-ink, var(${v}))`,
    // Tinted background: layer the semantic color at ~14% over surface.
    // color-mix keeps us inside the token system with zero new hex.
    background: `color-mix(in srgb, var(${v}) 14%, transparent)`,
    ...style,
  }
  return (
    <span
      ref={ref}
      className={`inline-flex items-center gap-4 rounded-pill px-8 py-4 text-11 font-medium tabular whitespace-nowrap ${className}`.trim()}
      style={styles}
      {...rest}
    >
      {dot && (
        <span
          aria-hidden="true"
          className="inline-block w-8 h-8 rounded-pill"
          style={{ background: `var(${v})`, width: 6, height: 6 }}
        />
      )}
      {children}
    </span>
  )
})
