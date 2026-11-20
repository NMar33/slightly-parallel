/**
 * The line between two columns (design round 3) is the control that folds the
 * side one. A hairline with a faint grip at rest; under the pointer or the keyboard focus it
 * turns jade and a grip with a chevron shows where the column goes. A click
 * folds the column to nothing and leaves the line at the edge, its grip
 * always drawn, pointing back the way the column comes. Wide screens only:
 * below them the columns stack and a disclosure button stands in (ListBar).
 */

import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from 'lucide-react'

import { t, tn } from '../../../i18n/scope/notes'

export function Divider({ side, open, onToggle, controls, top = 0 }: {
  /** Which column the line folds: the list on its left, the rail on its right. */
  side: 'list' | 'rail'
  open: boolean
  onToggle: () => void
  /** The id of the column it folds. */
  controls: string
  /** Where it sticks: under a sticky toolbar, its height. */
  top?: number
}) {
  const label = side === 'list' ? (open ? t('Hide the list') : t('Show the list')) : (open ? t('Hide the outline') : t('Show the outline'))
  const key = side === 'list' ? 'l' : 'r'
  // The chevron points where the column goes: away on a fold, back on a show.
  const toLeft = side === 'list' ? open : !open
  const Chevron = toLeft ? ChevronLeft : ChevronRight
  return (
    <button type="button" data-divider={side} aria-expanded={open} aria-controls={controls} aria-label={label} title={`${label} · ${key}`}
      onClick={onToggle} style={{ top }}
      className="group/div sticky self-start h-[calc(100vh-120px)] w-full flex justify-center cursor-pointer outline-none">
      <span aria-hidden className={`w-px h-full transition-colors ${open ? 'bg-border-subtle' : 'bg-border-default'} group-hover/div:bg-brand group-focus-visible/div:bg-brand`} />
      <span aria-hidden
        className={`absolute top-[calc(25vh-40px)] left-1/2 -translate-x-1/2 h-32 w-16 rounded-pill border flex items-center justify-center transition-[opacity,colors] bg-elevated
          ${open ? 'opacity-30 border-border-subtle text-tertiary' : 'opacity-100 border-brand/60 text-brand'}
          group-hover/div:opacity-100 group-hover/div:border-brand group-hover/div:text-brand group-focus-visible/div:opacity-100 group-focus-visible/div:border-brand group-focus-visible/div:text-brand group-focus-visible/div:ring-2 group-focus-visible/div:ring-brand/40`}>
        <Chevron size={12} />
      </span>
    </button>
  )
}

/** Below the wide layout: the list folds under a disclosure button instead of a line. */
export function ListBar({ open, onToggle, count, controls }: { open: boolean; onToggle: () => void; count: number; controls: string }) {
  const Icon = open ? ChevronUp : ChevronDown
  return (
    <button type="button" data-listbar aria-expanded={open} aria-controls={controls} onClick={onToggle}
      className="lg:hidden self-start inline-flex items-center gap-6 h-24 px-8 rounded-pill border border-border-subtle bg-elevated text-11 font-mono text-secondary hover:text-primary hover:bg-hover">
      <Icon size={12} aria-hidden />
      {open ? t('Hide the list') : t('Show the list')}
      <span className="text-tertiary">· {tn(count, '{n} note', '{n} notes')}</span>
    </button>
  )
}
