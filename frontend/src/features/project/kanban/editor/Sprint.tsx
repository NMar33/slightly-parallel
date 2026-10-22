/*
 * The task window's sprint choice: useSprintChoice holds the picked
 * block, the pinned default and the running / ended blocks; SprintPicker
 * draws them as chips. Moved out of TaskEditor.tsx — the window calls the
 * hook where its state used to sit, so the hook order is unchanged.
 */

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pin } from 'lucide-react'
import { Button } from '../../../../components/primitives'
import { getJson } from '../../../../lib/getJson'
import { useSprintBoard, type SprintsAnswer } from '../../../tasks/data'
import { readPinnedSprint, writePinnedSprint } from '../model'
import { LABEL } from '../../../promptlib/taskstyle'
import type { SprintChip } from './types'
import { useKeyedPref } from '../../../../lib/uiPrefs'
import { t } from '../../../../i18n/scope/project'

export function useSprintChoice(homeProject: string, isExisting: boolean, initialSprint: string) {
  // The pin is per project: ticking another home project reads its own.
  const [pinnedSprint, setPinnedSprint] = useKeyedPref(homeProject, readPinnedSprint, writePinnedSprint)
  const [sprintId, setSprintId] = useState(initialSprint)
  const togglePin = (id: string) => {
    const next = pinnedSprint === id ? '' : id
    setPinnedSprint(next)
    // Pinning while writing a new task is a statement of intent: use it.
    if (next && !isExisting) setSprintId(next)
  }
  // The running blocks (three at most) come as chips; "more" reveals the
  // settled past so old work can still be filed where it belonged.
  // The same read the project's Sprints and Timer tabs use; on a failure
  // there are none and the row hides itself.
  const board = useSprintBoard(homeProject)
  const activeSprints = useMemo<SprintChip[]>(() => (board.data ?? []).map((x) => ({ id: x.id, name: x.name })), [board.data])
  const [wantEnded, setWantEnded] = useState(false)
  const ended = useQuery({
    queryKey: ['sprints', 'ended', homeProject],
    queryFn: ({ signal }) => getJson<SprintsAnswer>(`/api/sprints?project=${encodeURIComponent(homeProject)}&status=ended&limit=100`, signal),
    enabled: wantEnded,
    select: (d) => (Array.isArray(d?.sprints) ? d.sprints : []).map((x): SprintChip => ({ id: x.id, name: x.name })),
  })
  // Null until asked for and answered: "more…" stays until then.
  const endedSprints: SprintChip[] | null = !wantEnded ? null : ended.data ?? (ended.isError ? [] : null)
  const endedFailed = wantEnded && ended.isError
  const loadEnded = () => setWantEnded(true)
  return { sprintId, setSprintId, pinnedSprint, togglePin, activeSprints, endedSprints, endedFailed, loadEnded }
}

/** Sprint: the running blocks as chips, the settled past on demand. */
export function SprintPicker({ homeProject, isExisting, sprint }: {
  homeProject: string
  isExisting: boolean
  sprint: ReturnType<typeof useSprintChoice>
}) {
  const { sprintId, setSprintId, pinnedSprint, togglePin, activeSprints, endedSprints, endedFailed, loadEnded } = sprint
  return (
    <div className="flex items-center gap-6 flex-wrap">
      <span
        className={`${LABEL} w-[52px] cursor-help`}
        title={`The block of work this task belongs to. A pinned block is the default for new tasks in ${homeProject}.`}
      >
        {t('Sprint')}
      </span>
      <button
        type="button"
        onClick={() => setSprintId('')}
        aria-pressed={sprintId === ''}
        className={`h-24 px-10 rounded-pill border text-11 font-mono ${sprintId === '' ? 'border-brand bg-brand text-on-brand' : 'border-border-default text-tertiary hover:border-brand'}`}
      >
        {t('none')}
      </button>
      {activeSprints.map((sp) => {
        const on = sprintId === sp.id
        const pinned = pinnedSprint === sp.id
        return (
          <span
            key={sp.id}
            className={`h-24 pl-10 pr-4 rounded-pill border text-11 font-mono inline-flex items-center gap-4 ${on ? 'border-brand bg-brand text-on-brand' : pinned ? 'border-brand/50 text-secondary' : 'border-border-default text-secondary hover:border-brand'}`}
          >
            <button type="button" onClick={() => setSprintId(on ? '' : sp.id)} aria-pressed={on}>
              {sp.name}
            </button>
            <button
              type="button"
              onClick={() => togglePin(sp.id)}
              aria-pressed={pinned}
              aria-label={pinned ? `Unpin ${sp.name} as the default block` : `Pin ${sp.name} as the default block for new tasks`}
              title={pinned
                ? t('Pinned. New tasks in {project} start in {sprint}. Click to unpin.', { project: homeProject, sprint: sp.name })
                : t('Pin {sprint} as the default for new tasks in {project}', { project: homeProject, sprint: sp.name })}
              className={`leading-none px-2 ${pinned ? (on ? 'opacity-100' : 'text-brand') : 'opacity-45 hover:opacity-100'}`}
            >
              <Pin size={10} aria-hidden style={pinned ? { fill: 'currentColor' } : undefined} />
            </button>
          </span>
        )
      })}
      {sprintId && !activeSprints.some((sp) => sp.id === sprintId) && !(endedSprints ?? []).some((sp) => sp.id === sprintId) && (
        <span className="h-24 px-10 rounded-pill border border-brand bg-brand text-on-brand text-11 font-mono inline-flex items-center" title={t('An ended block, or one from another project. Still assigned.')}>
          {sprintId}
        </span>
      )}
      {!isExisting && pinnedSprint && sprintId === pinnedSprint && (
        <span className="basis-full text-10 font-mono text-tertiary pl-[58px] inline-flex items-center gap-4">
          <Pin size={9} aria-hidden style={{ fill: 'currentColor' }} />
          {t('New tasks in')} {homeProject} {t('start in this sprint.')}
        </span>
      )}
      {endedSprints === null ? (
        <Button variant="text" size="bare" onClick={loadEnded} title={t('Show ended blocks too')}>
          {t('more…')}
        </Button>
      ) : (
        endedSprints.map((sp) => (
          <button
            key={sp.id}
            type="button"
            onClick={() => setSprintId(sprintId === sp.id ? '' : sp.id)}
            aria-pressed={sprintId === sp.id}
            title={t('An ended block. Assigning adds the task to its history.')}
            className={`h-24 px-10 rounded-pill border text-11 font-mono opacity-70 ${sprintId === sp.id ? 'border-brand bg-brand text-on-brand opacity-100' : 'border-border-subtle text-tertiary hover:border-border-strong line-through decoration-1'}`}
          >
            {sp.name}
          </button>
        ))
      )}
      {endedFailed && <span className="text-10 font-mono text-tertiary">{t('The ended blocks could not be read.')}</span>}
    </div>
  )
}
