import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '../../components/primitives'
import { fail } from '../../lib/getJson'
import { LABEL } from '../promptlib/taskstyle'
import { stamp } from '../visions/time'
import { ALL_PROJECTS, type FoundSkill, type SkillWrites, type UsageSummary } from './data'
import { t, tn } from '../../i18n/scope/system'

/**
 * Skills v01-01 — "Not in Slightly Parallel": skill folders on this machine Slightly Parallel
 * does not keep, and names agents ran that have no folder here. A folder can
 * be taken in with one click; the folder on disk is left as it is. With
 * plugins the list runs long, so it shows the first rows and folds the rest.
 */

/** How many rows show before "Show all". */
const FOLD_AT = 8

interface Entry {
  name: string
  description: string
  uses: number
  lastUsed: string
  where: FoundSkill['where']
  clash: boolean
  path: string
}

function entriesOf(found: FoundSkill[], usage: UsageSummary | undefined): Entry[] {
  const out: Entry[] = found.map((f) => ({
    name: f.name,
    description: f.description,
    uses: f.uses,
    lastUsed: usage?.unknown.find((u) => u.name === f.name)?.last_used ?? '',
    where: f.where,
    clash: f.clash,
    path: f.where[0]?.path ?? '',
  }))
  const held = new Set(out.map((e) => e.name))
  for (const u of usage?.unknown ?? []) {
    // Ran in a session, but no folder Slightly Parallel can read — a plugin skill.
    if (!held.has(u.name)) {
      out.push({ name: u.name, description: '', uses: u.uses, lastUsed: u.last_used, where: [], clash: false, path: '' })
    }
  }
  return out.sort((a, b) => b.uses - a.uses || a.name.localeCompare(b.name))
}

function whereLine(e: Entry): string {
  if (!e.where.length) return t('From a plugin')
  const names = e.where.map((w) => (w.project === ALL_PROJECTS ? t('All projects') : w.project))
  return e.where.length > 1 ? `${tn(e.where.length, '{n} copy', '{n} copies')} · ${names.join(', ')}` : names[0]
}

export function FoundSkills({
  found, usage, writes, onOpen,
}: {
  found: FoundSkill[]
  usage: UsageSummary | undefined
  writes: SkillWrites
  onOpen: (id: string) => void
}) {
  const entries = entriesOf(found, usage)
  const [all, setAll] = useState(false)
  if (!entries.length) return null
  const list = all ? entries : entries.slice(0, FOLD_AT)

  const takeIn = (e: Entry) =>
    writes.takeIn.mutate({ path: e.path }, {
      onSuccess: (d) => {
        toast.success(t('Added {name} to the skills', { name: e.name }))
        if (d.skipped.length) toast.message(t('Not copied: {list}', { list: d.skipped.join(', ') }))
        onOpen(d.metadata.id)
      },
      onError: fail,
    })

  return (
    <section aria-label={t('Not in Slightly Parallel')} className="flex flex-col gap-4 border-t border-border-subtle pt-12">
      <div className="px-8 flex flex-col gap-2">
        <span className={LABEL}>{t('Not in Slightly Parallel')}</span>
        <span className="text-11 text-tertiary leading-relaxed">
          {t('Skill folders on this machine, and skills agents used in the last {n} days.', { n: usage?.days ?? 30 })}
        </span>
      </div>
      {list.map((e) => (
        <div key={`${e.name}-${e.path}`} className="px-8 py-6 flex flex-col gap-2 rounded-input hover:bg-hover">
          <span className="flex items-baseline gap-8 min-w-0">
            <span className="text-12 font-mono text-secondary truncate flex-1 min-w-0" title={e.description || e.name}>
              {e.name}
            </span>
            {e.uses > 0 && (
              <span className="text-10 font-mono text-tertiary tabular shrink-0" title={e.lastUsed ? t('Last used {date}', { date: stamp(e.lastUsed) }) : undefined}>
                {tn(e.uses, '{n} use', '{n} uses')}
              </span>
            )}
          </span>
          <span className="flex items-baseline gap-8 min-w-0">
            <span className="text-10 font-mono text-tertiary truncate flex-1 min-w-0" title={e.path}>{whereLine(e)}</span>
            {e.path && !e.clash && (
              <Button variant="link" size="bare" className="text-10 font-mono shrink-0"
                onClick={() => takeIn(e)} disabled={writes.takeIn.isPending}>
                {t('Take in')}
              </Button>
            )}
          </span>
          {e.clash && <span className="text-10 font-mono text-status-amber">{t('A skill here already has this name.')}</span>}
        </div>
      ))}
      {entries.length > FOLD_AT && (
        <Button variant="link" size="bare" className="self-start px-8 text-11 font-mono" onClick={() => setAll((v) => !v)}>
          {all ? t('Show fewer') : t('Show all {n}', { n: entries.length })}
        </Button>
      )}
    </section>
  )
}
