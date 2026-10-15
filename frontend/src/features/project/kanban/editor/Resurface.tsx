/*
 * The task window's comeback row: the important star, "start an agent",
 * and "↩ Back" — the comeback date, the column it returns to, and the
 * repeat. Moved out of TaskEditor.tsx; the window owns the values.
 */

import type { Dispatch, SetStateAction } from 'react'
import { STAR_COLOR } from '../../../../lib/marks'
import { LABEL } from '../../../promptlib/taskstyle'
import { StartAgent } from './StartAgent'
import { PillRow } from '../../../../components/PillRow'
import { isoDay } from '../../../../utils/dateUtils'
import { t } from '../../../../i18n/scope/project'

/** The local date n days from today, YYYY-MM-DD (the date input's own form). */
const inDays = (n: number) => {
  const d = new Date(); d.setDate(d.getDate() + n)
  return isoDay(d)
}

/** The quick comeback offsets, in days. */
const BACK = [['1w', 7], ['2w', 14], ['1m', 30]] as const
const BACK_OPTIONS: Array<readonly ['never' | (typeof BACK)[number][0], string]> =
  [['never', 'never'], ...BACK.map(([k]) => [k, k] as const)]

/** Bring it back: the comeback date, where to, and repeat — and the star. */
export function ResurfaceRow({
  remember, setRemember, agentTaskId, projectCode, resurfaceOn, setResurfaceOn, resurfaceTo, setResurfaceTo, setResurfaceEvery, resurfaceEvery,
}: {
  remember: boolean
  setRemember: Dispatch<SetStateAction<boolean>>
  /** The task being edited — "start an agent" shows only for one. */
  agentTaskId?: string
  projectCode: string
  resurfaceOn: string
  setResurfaceOn: (v: string) => void
  resurfaceTo: string
  setResurfaceTo: (v: string) => void
  resurfaceEvery: string
  setResurfaceEvery: (v: string) => void
}) {
  return (
    <div className="flex items-center gap-6 flex-wrap">
      <button
        type="button"
        onClick={() => setRemember((v) => !v)}
        aria-pressed={remember}
        title={t('Mark as important')}
        className={`h-24 px-10 rounded-pill border text-11 font-mono ${remember ? '' : 'border-border-default text-tertiary hover:text-primary'}`}
        style={remember ? { color: STAR_COLOR, borderColor: STAR_COLOR, backgroundColor: `color-mix(in srgb, ${STAR_COLOR} 10%, transparent)` } : undefined}
      >
        {remember ? '★' : '☆'} {t('important')}
      </button>
      {agentTaskId && <StartAgent taskId={agentTaskId} project={projectCode} />}
      <span className="w-px h-16 bg-border-subtle mx-2" aria-hidden />
      <span className={`${LABEL} w-[52px]`} title={t('On this date the task moves back to the selected column.')}>{t('↩ Back')}</span>
      <PillRow
        label={t('Bring back')}
        value={!resurfaceOn ? 'never' : (BACK.find(([, n]) => resurfaceOn === inDays(n))?.[0] ?? '')}
        onChange={(v) => {
          const n = BACK.find(([k]) => k === v)?.[1]
          if (n == null) { setResurfaceOn(''); setResurfaceEvery('') } else setResurfaceOn(inDays(n))
        }}
        options={BACK_OPTIONS}
        gap={6}
      />
      <input type="date" value={resurfaceOn} onChange={(e) => setResurfaceOn(e.target.value)} aria-label={t('Comeback date')}
        className="h-24 px-6 rounded-input border border-border-default bg-elevated text-11 font-mono text-secondary" />
      {resurfaceOn && (
        <>
          <span className="text-11 text-tertiary">→</span>
          <PillRow
            label={t('Back to')}
            value={resurfaceTo === 'todo' || resurfaceTo === 'review' ? resurfaceTo : ''}
            onChange={setResurfaceTo}
            options={[['todo', t('To do')], ['review', t('Review')]]}
            gap={6}
          />
          <label className="inline-flex items-center gap-4 text-11 font-mono text-tertiary" title={t('When the task is done, it returns again after this many days')}>
            <input type="checkbox" checked={!!resurfaceEvery} onChange={(e) => setResurfaceEvery(e.target.checked ? String(Math.max(1, Math.round((Date.parse(resurfaceOn) - Date.now()) / 86400e3))) : '')} className="accent-[var(--brand)]" />
            {t('repeat')}
          </label>
        </>
      )}
    </div>
  )
}
