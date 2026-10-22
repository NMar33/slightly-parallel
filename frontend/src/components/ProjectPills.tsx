import type { ReactNode } from 'react'

import { projectColor } from '../utils/projectColor'
import { filterPill } from './FilterPill'
import { LABEL } from './ui'
import { t } from '../i18n/scope/shell'

/**
 * The one project picker: a row of outlined pills, the project on show in
 * jade, each with how many it holds when the page counts. "all" drops the
 * filter when the page offers it. A project's colour shows only as a dot.
 *
 * Visions, Rules and Problems drew this first (KeptProjectPills); the day
 * books, the calendar, statistics, tasks, milestones and architecture draw
 * it too.
 */
export interface ProjectPillOption {
  code: string
  /** How many the project holds, shown after the name. */
  count?: number
  /** The word on the pill, when it is not the code (a saved board's name). */
  text?: ReactNode
  /** A tooltip. */
  hint?: string
  /** Drawn quieter: the project has nothing here yet. */
  dim?: boolean
  /** No colour dot (a saved board is not one project). */
  noDot?: boolean
}

/** The pill's classes, for a row that adds a pill of its own. */
const projectPill = filterPill

export function ProjectPills({
  projects, value, onPick, all, label = 'project', dots = false, clearable = false, className = '',
}: {
  projects: Array<string | ProjectPillOption>
  /** The project on show; '' for all of them. */
  value: string
  onPick: (code: string) => void
  /** Offer "all" (value ''), with the total when given. */
  all?: { count?: number; text?: string }
  /** The small label before the pills; false for none. */
  label?: string | false
  /** A colour dot on each project pill. */
  dots?: boolean
  /** Clicking the pill that is on goes back to all. */
  clearable?: boolean
  className?: string
}) {
  const options = projects.map((p) => (typeof p === 'string' ? { code: p } : p))
  if (options.length === 0) return null
  return (
    <div role="radiogroup" aria-label={label || t('Project')} className={`inline-flex items-center gap-4 flex-wrap min-w-0 ${className}`}>
      {label && <span className={`${LABEL} mr-2`}>{label}</span>}
      {all && (
        <button type="button" role="radio" aria-checked={!value} onClick={() => onPick('')} className={projectPill(!value)}>
          {all.text ?? 'all'}{all.count != null && <span className="opacity-60">{all.count}</span>}
        </button>
      )}
      {options.map((o) => {
        const on = value === o.code
        return (
          <button key={o.code} type="button" role="radio" aria-checked={on} title={o.hint}
            onClick={() => onPick(on && clearable ? '' : o.code)}
            className={`${projectPill(on)} ${o.dim && !on ? 'opacity-60' : ''}`}>
            {dots && !o.noDot && <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: projectColor(o.code) }} aria-hidden />}
            {o.text ?? o.code}
            {o.count != null && <span className="opacity-60 tabular-nums">{o.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
