import { useEffect, useState } from 'react'
import { SPRINTS_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'

import { PageHeader } from '../components/PageHeader'
import { Segmented } from '../components/Segmented'
import { LoadingSkeleton } from '../components/states'
import { RangeSwitch } from '../features/sprints/bands'
import { hm, useDeck } from '../features/sprints/deck'
import { StartBlockAnywhere } from '../features/sprints/parts'
import { fleetTotals } from '../features/sprints/view'
import { persistPref } from '../lib/uiPrefs'
import SprintsMissionPage from './SprintsMissionPage'
import SprintsWeekPage from './SprintsWeekPage'
import { t } from '../i18n/scope/pages'

/**
 * /sprints — one page, two ways of looking at the same blocks.
 *
 * The shell owns everything above the fold: the title, both switches, the
 * fleet totals and starting a block. A view supplies a body and nothing
 * else, so moving between them cannot shift a control or change the range —
 * the top of the page is the same object, whichever view is under it.
 *
 * Mission control is the board: every running block a strip you operate in
 * place. The river is the history: cumulative flow, effectiveness, the
 * numbers. Both the view and the range are remembered.
 */

type View = 'mission' | 'river'
const VIEW_KEY = 'sp-sprints-page-view'
const RANGE_KEY = 'sp-sprints-range'

const BLURB: Record<View, string> = {
  mission: t('Running sprints in every project'),
  river: t('Daily progress'),
}

export default function SprintsPage() {
  const [view, setView] = useState<View>(() => {
    try { return localStorage.getItem(VIEW_KEY) === 'river' ? 'river' : 'mission' } catch { return 'mission' }
  })
  const [range, setRange] = useState<7 | 30>(() => {
    try { return localStorage.getItem(RANGE_KEY) === '30' ? 30 : 7 } catch { return 7 }
  })
  // One read of the deck for whichever view is showing — switching does not
  // refetch, and both views always agree because they share the answer.
  const state = useDeck(range)
  const totals = fleetTotals(state.deck)

  useEffect(() => { document.title = `${t('Sprints')} · ${view === 'river' ? t('progress') : t('running')} — Slightly Parallel` }, [view])

  const pickView = (v: View) => {
    setView(v)
    persistPref(VIEW_KEY, v)
  }
  const pickRange = (v: 7 | 30) => {
    setRange(v)
    persistPref(RANGE_KEY, String(v))
  }

  return (
    <div className="flex flex-col gap-14">
      {/* The header belongs to the page, not to either view */}
      <PageHeader
        variant="tool"
        title={t('Sprints')}
        sub={BLURB[view]}
        below={(
          /* The same five facts, in the same place, in both views */
          <div className="flex items-baseline gap-14 text-11 font-mono flex-wrap">
            <Stat label={t('running')} value={String(totals.running)} tone={totals.running ? 'var(--status-green)' : undefined} />
            <Stat label={t('open work')} value={String(totals.open)} />
            <Stat label={t('planned today')} value={String(totals.today)} />
            <Stat label={t('your hours')} value={hm(totals.human)} />
            <Stat label={t('agent hours')} value={hm(totals.agent)} />
            <span className="text-tertiary">
              {range === 7 ? t('last seven days') : t('last thirty days')}
            </span>
          </div>
        )}
      >
        <Segmented
          label={t('Sprints view')}
          shape="pill"
          value={view}
          onChange={pickView}
          options={[['mission', t('running'), t('Each running sprint with its tasks and timer')],
                    ['river', t('progress'), t('Tasks, effort and lead time per day over the range')]] as const}
        />
        <RangeSwitch value={range} onChange={pickRange} />
        {state.deck && <StartBlockAnywhere deck={state.deck} onStarted={state.refresh} />}
      </PageHeader>
      <PageGuide id="sprints" guide={SPRINTS_GUIDE} examples={0} />

      {!state.deck && !state.err ? (
        <LoadingSkeleton variant="row" count={4} />
      ) : view === 'river' ? (
        <SprintsWeekPage {...state} range={range} />
      ) : (
        <SprintsMissionPage {...state} range={range} />
      )}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <span className="inline-flex items-baseline gap-4">
      <span className="text-tertiary">{label}</span>
      <span className="text-14 font-semibold tabular" style={{ color: tone ?? 'var(--text-primary)' }}>{value}</span>
    </span>
  )
}
