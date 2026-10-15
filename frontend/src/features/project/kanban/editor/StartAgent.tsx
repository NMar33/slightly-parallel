/*
 * The task window's "start an agent" pill: opens a terminal on the task,
 * or brings forward the terminal already working on it. Moved out of
 * TaskEditor.tsx; it sits in the comeback row (see Resurface.tsx).
 */

import { showTerminal, useTerminalActions, useTerminals } from '../../../../lib/terminal'
import { StateDot } from '../../../terminal/parts'
import { t } from '../../../../i18n/scope/project'

/**
 * Start an agent on this task: a terminal in the project's folder, the
 * agent of Settings › Terminal with the task as its first message — or the
 * terminal already working on it, brought forward.
 */
export function StartAgent({ taskId, project }: { taskId: string; project: string }) {
  const act = useTerminalActions()
  const list = useTerminals().data
  const live = (list?.sessions ?? []).filter((x) => x.task_id === taskId && x.state !== 'ended').slice(-1)[0]
  return (
    <button type="button" disabled={act.opening}
      onClick={() => live ? showTerminal(live.id) : act.open({ kind: 'start', task_id: taskId, project })}
      title={live ? t('Show the terminal working on this task') : t('Open a terminal and start an agent on this task')}
      className="h-24 px-10 rounded-pill border border-border-default text-11 font-mono text-secondary hover:border-brand hover:text-primary inline-flex items-center gap-6">
      {live ? <><StateDot state={live.state} size={6} /> {t('its terminal')}</> : <>{t('▶ start an agent')}</>}
    </button>
  )
}
