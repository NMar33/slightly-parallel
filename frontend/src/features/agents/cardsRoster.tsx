import { useMemo, useState } from 'react'

import { GROUP_COLOR } from '../../lib/groups'
import { fmtLines, fmtMinutes, groupProfiles, toolOfProfile, type AgentProfile } from './profile'

import { t } from '../../i18n/scope/views'
/**
 * The cards roster's toolbar and ordering — sort, tool and group filters,
 * "keep groups together" — shared by every cards-shaped page so they
 * differ only in what a click on a card does.
 */

type CardsSort = 'recent' | 'time' | 'output' | 'tasks' | 'name'

const SORTS: Array<[CardsSort, string]> = [
  ['recent', t('most recent')],
  ['time', t('most time')],
  ['output', t('most output')],
  ['tasks', t('most tasks done')],
  ['name', t('by name')],
]

function sortBy(k: CardsSort) {
  return (a: AgentProfile, b: AgentProfile): number => {
    switch (k) {
      case 'recent': return (Date.parse(b.agent.last_active) || 0) - (Date.parse(a.agent.last_active) || 0)
      case 'time': return b.totals.minutes - a.totals.minutes
      case 'output': return (b.totals.lines_add + b.totals.features_n * 200) - (a.totals.lines_add + a.totals.features_n * 200)
      case 'tasks': return b.totals.tasks_done_n - a.totals.tasks_done_n || b.totals.tasks_handed_n - a.totals.tasks_handed_n
      case 'name': return a.agent.agent_name.localeCompare(b.agent.agent_name)
    }
  }
}

export function useCardsRoster(profiles: AgentProfile[]) {
  const [sort, setSort] = useState<CardsSort>('recent')
  const [tool, setTool] = useState<string>('')
  const [group, setGroup] = useState<string>('')
  const [grouped, setGrouped] = useState(true)
  const tools = useMemo(() => [...new Set(profiles.map(toolOfProfile).filter(Boolean))], [profiles])
  const groups = useMemo(() => [...new Set(profiles.map((p) => p.agent.agent_group).filter(Boolean))] as string[], [profiles])
  const sections = useMemo(() => {
    const list = profiles
      .filter((p) => !tool || toolOfProfile(p) === tool)
      .filter((p) => !group || p.agent.agent_group === group)
      .sort(sortBy(sort))
    return grouped ? groupProfiles(list) : [{ name: '', members: list }]
  }, [profiles, tool, group, sort, grouped])
  /** Every shown profile in display order — for prev/next. */
  const ordered = useMemo(() => sections.flatMap((s) => s.members), [sections])

  const toolbar = (
    <div className="flex items-center gap-8 flex-wrap text-11">
      <span className="font-mono text-tertiary uppercase tracking-wide">{t('sort')}</span>
      {SORTS.map(([k, label]) => (
        <button key={k} type="button" onClick={() => setSort(k)} aria-pressed={sort === k}
          className={`rounded-pill border px-8 py-2 ${sort === k ? 'border-brand text-brand' : 'border-border-subtle text-secondary hover:text-primary'}`}>
          {label}
        </button>
      ))}
      {tools.length > 1 && (
        <>
          <span className="font-mono text-tertiary uppercase tracking-wide ml-8">{t('tool')}</span>
          {tools.map((it) => (
            <button key={it} type="button" onClick={() => setTool((v) => (v === it ? '' : it))} aria-pressed={tool === it}
              className={`rounded-pill border px-8 py-2 ${tool === it ? 'border-brand text-brand' : 'border-border-subtle text-secondary hover:text-primary'}`}>
              {it}
            </button>
          ))}
        </>
      )}
      {groups.length > 0 && (
        <>
          <span className="font-mono text-tertiary uppercase tracking-wide ml-8">{t('group')}</span>
          {groups.map((g) => (
            <button key={g} type="button" onClick={() => setGroup((v) => (v === g ? '' : g))} aria-pressed={group === g}
              className="rounded-pill border px-8 py-2"
              style={{ borderColor: GROUP_COLOR, color: group === g ? 'var(--bg-surface)' : GROUP_COLOR, backgroundColor: group === g ? GROUP_COLOR : 'transparent' }}>
              ⌂ {g}
            </button>
          ))}
          <label className="inline-flex items-center gap-4 text-secondary ml-8">
            <input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.currentTarget.checked)} /> {t('keep groups together')}
          </label>
        </>
      )}
    </div>
  )

  return { sort, tool, group, grouped, sections, ordered, toolbar }
}

/** The heading above a group of cards. */
export function GroupHeading({ name, members }: { name: string; members: AgentProfile[] }) {
  if (!name) return null
  return (
    <h2 className="text-12 font-mono text-secondary flex items-center gap-8">
      <span className="font-semibold" style={{ color: GROUP_COLOR }}>⌂ {name}</span>
      <span className="text-tertiary">{members.length} {t('agents ·')}{' '}{fmtMinutes(members.reduce((s, p) => s + p.totals.minutes, 0))} · {fmtLines(members.reduce((s, p) => s + p.totals.lines_add, 0), members.reduce((s, p) => s + p.totals.lines_del, 0))}</span>
      <span className="flex-1 border-t border-border-subtle" />
    </h2>
  )
}
