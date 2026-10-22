import { useState } from 'react'

import { LABEL } from '../promptlib/taskstyle'
import { isExample } from '../visions/data'
import { awaitingDraft, hasErrors, isArchived, skillTitle, worstInstall, type Skill } from './data'
import { filesLabel } from './files'
import { t, tn } from '../../i18n/scope/system'

/**
 * Skills v01-01 — the list on the left.
 *
 * Skills grouped by where they stand: drafts, active, archived (folded). A
 * row says how many files the skill carries besides SKILL.md, so a folder
 * with a lot in it is known before it is opened. A kept #skill with no draft
 * is reported under "Not written" (notwritten.tsx), not listed here — unless
 * it was archived, which puts it with the other archived skills so it can be
 * found and restored.
 */

interface Group {
  key: string
  title: string
  skills: Skill[]
  folded?: boolean
}

export function groupsOf(skills: Skill[]): Group[] {
  const written = skills.filter((s) => !awaitingDraft(s) && !isArchived(s))
  return [
    { key: 'draft', title: t('Drafts'), skills: written.filter((s) => (s.row.status ?? 'draft') === 'draft') },
    { key: 'active', title: t('Active'), skills: written.filter((s) => s.row.status === 'active') },
    { key: 'archived', title: t('Archived'), skills: skills.filter(isArchived), folded: true },
  ].filter((g) => g.skills.length > 0)
}

function firstLine(text: string | null | undefined): string {
  return (text ?? '').split(/(?<=\.)\s|\n/)[0] ?? ''
}

function Mark({ s }: { s: Skill }) {
  const worst = worstInstall(s)
  return (
    <span className="flex items-center gap-6 shrink-0">
      {/* A mock that came with Slightly Parallel, marked so it is told apart from your own. */}
      {isExample(s.row) && <span className="text-10 font-mono text-tertiary">{t('Example')}</span>}
      {hasErrors(s) && <span className="text-10 font-mono text-status-red">{t('Errors')}</span>}
      {worst === 'changed' && <span className="text-10 font-mono text-status-amber">{t('Changed on disk')}</span>}
      {(worst === 'stale' || worst === 'missing') && (
        <span className="text-10 font-mono text-status-amber">{worst === 'stale' ? t('Older copy') : t('Copy missing')}</span>
      )}
    </span>
  )
}

function Row({ s, open, onOpen, watch }: { s: Skill; open: boolean; onOpen: () => void; watch?: (el: Element | null) => void }) {
  const uses = s.usage?.recent ?? 0
  const files = filesLabel(Object.keys(s.current?.files ?? {}).length)
  return (
    <button ref={watch} type="button" onClick={onOpen} aria-current={open ? 'true' : undefined}
      className={`w-full text-left rounded-input px-8 py-6 flex flex-col gap-2 border ${
        open ? 'border-brand bg-brand-glow' : 'border-transparent hover:bg-hover'}`}>
      <span className="flex items-baseline gap-8 min-w-0">
        <span className="text-13 font-mono text-primary truncate flex-1 min-w-0">{skillTitle(s)}</span>
        {uses > 0 && (
          <span className="text-10 font-mono text-tertiary tabular shrink-0" title={t('Uses in the last 30 days')}>
            {tn(uses, '{n} use', '{n} uses')}
          </span>
        )}
      </span>
      <span className="flex items-baseline gap-8 min-w-0">
        <span className="text-11 text-tertiary truncate flex-1 min-w-0">
          {awaitingDraft(s) ? t('No draft') : firstLine(s.row.description)}
        </span>
        {files && <span className="text-10 font-mono text-tertiary shrink-0">{files}</span>}
        <Mark s={s} />
      </span>
    </button>
  )
}

export function SkillList({
  skills, openId, onOpen, groups = groupsOf, watch,
}: {
  skills: Skill[]
  openId: string
  onOpen: (id: string) => void
  groups?: (skills: Skill[]) => Group[]
  /** A ref per row, so the page reads the details of the rows on screen (useSkills' `near`). */
  watch?: (id: string) => (el: Element | null) => void
}) {
  const [unfolded, setUnfolded] = useState<Record<string, boolean>>({})
  return (
    <div className="flex flex-col gap-16">
      {groups(skills).map((g) => {
        const folded = g.folded && !unfolded[g.key] && !g.skills.some((s) => s.row.id === openId)
        return (
          <section key={g.key} aria-label={g.title} className="flex flex-col gap-2">
            <button type="button" onClick={() => g.folded && setUnfolded((u) => ({ ...u, [g.key]: !u[g.key] }))}
              className={`flex items-center gap-8 px-8 h-20 text-left ${g.folded ? 'hover:text-primary' : 'cursor-default'}`}>
              {g.folded && <span className={`text-10 text-tertiary transition-transform ${folded ? '' : 'rotate-90'}`} aria-hidden>▶</span>}
              <span className={`${LABEL} flex-1`}>{g.title}</span>
              <span className="text-10 font-mono text-tertiary tabular">{g.skills.length}</span>
            </button>
            {!folded && g.skills.map((s) => (
              <Row key={s.row.id} s={s} open={s.row.id === openId} onOpen={() => onOpen(s.row.id)} watch={watch?.(s.row.id)} />
            ))}
          </section>
        )
      })}
    </div>
  )
}
