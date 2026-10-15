/**
 * LoadingSkeleton — shape-matched pulse placeholders.
 *
 * Rule (aesthetic critic §8): NO spinners for content areas. Skeletons must
 * match the shape of what's coming, not generic bars. We ship four shape
 * variants that cover every P0/P1 view:
 *
 *   • 'kpi'    — 5-tile KPI strip (matches CEO overview hero)
 *   • 'card'   — a single project/decision card
 *   • 'row'    — a table row (32px dense or 28px tree)
 *   • 'chart'  — 320px chart frame with axis stubs
 *   • 'tree'   — indented tree lines (goals tree)
 *
 * The pulse animation is a single CSS keyframe (`skel-pulse`) that respects
 * `prefers-reduced-motion` via the global rule in tokens.css.
 *
 *   <LoadingSkeleton variant="kpi" />
 *   <LoadingSkeleton variant="row" count={8} />
 */

import { CSSProperties } from 'react'
import { t } from '../../i18n/scope/shell'

type SkeletonVariant = 'kpi' | 'card' | 'row' | 'chart' | 'tree' | 'text'

interface LoadingSkeletonProps {
  variant: SkeletonVariant
  count?: number
  className?: string
  /** ARIA label for screen readers; falls back to a variant-specific string. */
  label?: string
}

const defaultLabels: Record<SkeletonVariant, string> = {
  kpi: t('Loading KPI tiles'),
  card: t('Loading cards'),
  row: t('Loading rows'),
  chart: t('Loading chart'),
  tree: t('Loading tree'),
  text: t('Loading text'),
}

// One shared pulse style — keyframe injected below via a <style> tag once.
const bar: CSSProperties = {
  background:
    'linear-gradient(90deg, var(--bg-elevated) 0%, var(--bg-hover) 50%, var(--bg-elevated) 100%)',
  backgroundSize: '200% 100%',
  animation: 'skel-pulse 1.4s var(--ease-out) infinite',
  borderRadius: 'var(--radius-input)',
}

function SkelBar({ w = '100%', h = 12, style }: { w?: string | number; h?: string | number; style?: CSSProperties }) {
  return <div style={{ ...bar, width: w, height: h, ...style }} />
}

function KPISkeleton() {
  return (
    <div className="grid grid-cols-5 gap-16" data-testid="skeleton-kpi">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="rounded-card border border-border-default bg-surface p-16 flex flex-col gap-12 min-h-[96px]">
          <SkelBar w="60%" h={11} />
          <SkelBar w="45%" h={32} />
          <SkelBar w="30%" h={11} />
        </div>
      ))}
    </div>
  )
}

function CardSkeleton({ count }: { count: number }) {
  return (
    <div className="flex flex-col gap-12" data-testid="skeleton-card">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-card border border-border-default bg-surface p-16 flex flex-col gap-12">
          <div className="flex items-center justify-between gap-12">
            <SkelBar w="30%" h={14} />
            <SkelBar w={60} h={20} style={{ borderRadius: 9999 }} />
          </div>
          <SkelBar w="80%" h={12} />
          <SkelBar w="65%" h={12} />
        </div>
      ))}
    </div>
  )
}

function RowSkeleton({ count }: { count: number }) {
  return (
    <div className="flex flex-col divide-y border border-border-default rounded-card overflow-hidden" data-testid="skeleton-row">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="h-32 flex items-center gap-16 px-12 bg-surface" style={{ borderColor: 'var(--border-subtle)' }}>
          <SkelBar w={16} h={16} style={{ borderRadius: 9999 }} />
          <SkelBar w="25%" h={11} />
          <SkelBar w="35%" h={11} />
          <div className="flex-1" />
          <SkelBar w={80} h={11} />
        </div>
      ))}
    </div>
  )
}

function ChartSkeleton() {
  return (
    <div className="rounded-card border border-border-default bg-surface p-16 flex flex-col gap-12" data-testid="skeleton-chart">
      <SkelBar w="40%" h={14} />
      <div className="relative h-[280px] flex items-end gap-8 pt-24 pb-16 pl-24">
        {/* y-axis stub */}
        <div className="absolute left-0 top-24 bottom-16 w-16 flex flex-col justify-between">
          {[0, 1, 2, 3].map((i) => (
            <SkelBar key={i} w={12} h={8} />
          ))}
        </div>
        {/* bars */}
        {[45, 70, 30, 90, 55, 65, 40, 80, 50, 35, 75, 60].map((h, i) => (
          <div key={i} style={{ ...bar, width: 16, height: `${h}%`, borderRadius: 2 }} />
        ))}
      </div>
      {/* x-axis stub */}
      <SkelBar w="90%" h={8} />
    </div>
  )
}

function TreeSkeleton({ count }: { count: number }) {
  // Simulated depth pattern — small→big→small feels like a real tree.
  const depths = [0, 1, 1, 2, 1, 0, 1, 2, 2, 1]
  return (
    <div className="flex flex-col" data-testid="skeleton-tree">
      {Array.from({ length: count }).map((_, i) => {
        const d = depths[i % depths.length]
        return (
          <div key={i} className="h-[28px] flex items-center gap-8" style={{ paddingLeft: 12 + d * 20 }}>
            <SkelBar w={12} h={12} style={{ borderRadius: 3 }} />
            <SkelBar w={`${60 - d * 10}%`} h={10} />
          </div>
        )
      })}
    </div>
  )
}

function TextSkeleton({ count }: { count: number }) {
  const widths = ['100%', '96%', '88%', '92%', '70%']
  return (
    <div className="flex flex-col gap-8" data-testid="skeleton-text">
      {Array.from({ length: count }).map((_, i) => (
        <SkelBar key={i} w={widths[i % widths.length]} h={10} />
      ))}
    </div>
  )
}

export function LoadingSkeleton({ variant, count = 3, className = '', label }: LoadingSkeletonProps) {
  const aria = label ?? defaultLabels[variant]
  let body: JSX.Element
  switch (variant) {
    case 'kpi':   body = <KPISkeleton />; break
    case 'card':  body = <CardSkeleton count={count} />; break
    case 'row':   body = <RowSkeleton count={count} />; break
    case 'chart': body = <ChartSkeleton />; break
    case 'tree':  body = <TreeSkeleton count={count} />; break
    case 'text':  body = <TextSkeleton count={count} />; break
  }
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={aria}
      aria-busy="true"
      className={className}
    >
      {/* Keyframe injected once per page — cheap and self-contained. */}
      <style>{`@keyframes skel-pulse { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }`}</style>
      <span className="sr-only">{aria}</span>
      {body}
    </div>
  )
}
