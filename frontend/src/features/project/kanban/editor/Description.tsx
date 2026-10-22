/*
 * The task window's description box and its rounds: the quick-note take,
 * "+ next turn" / "back to turn N", the turn reference and the earlier
 * rounds under the box. Moved out of TaskEditor.tsx; the window owns the
 * text and the rounds, this draws them.
 */

import type { Dispatch, SetStateAction } from 'react'
import { TakeQuickNote } from '../../../note/TakeQuickNote'
import { Button } from '../../../../components/primitives'
import { type Turn, turnRef } from '../../../tasks/turns'
import { TurnHistory } from '../parts'
import { LABEL } from '../../../promptlib/taskstyle'
import { t } from '../../../../i18n/scope/project'

export function DescriptionField({
  body, setBody, isEdit, taskId, newTurn, srcTurns, priorTurns, turnNumber, startNextTurn, cancelNextTurn, minHeight,
}: {
  body: string
  setBody: Dispatch<SetStateAction<string>>
  isEdit: boolean
  /** The task being edited; the turn reference is copied under its id. */
  taskId?: string
  newTurn: boolean
  srcTurns: Turn[]
  priorTurns: Turn[]
  turnNumber: number
  startNextTurn: () => void
  cancelNextTurn: () => void
  minHeight: number
}) {
  return (
    <div className="flex flex-col gap-3">
      {/* A row, not a label: the quick-note and turn controls are
          buttons, and interactive content inside a <label> is neither
          valid HTML nor reachable by name for a screen reader. */}
      <div className={`${LABEL} flex items-center gap-8`}>
        <label htmlFor="task-desc">
          {priorTurns.length > 0 ? (
            <>{t('Turn')} {turnNumber} <span className="lowercase text-tertiary/60">{t('— the request now')}</span></>
          ) : (
            <>{t('Description')} <span className="lowercase text-tertiary/60">{t('— optional')}</span></>
          )}
        </label>
        {/* The quick note was written for exactly this moment: a thought
            that turned out to be a task. Taking it empties the note, and
            the note keeps a version of what it handed over. */}
        <TakeQuickNote
          onTake={(note) => setBody((b) => (b.trim() ? `${b.replace(/\s+$/, '')}\n\n${note}` : note))}
        />
        {isEdit && (newTurn ? (
          <Button
            variant="text"
            size="bare"
            onClick={cancelNextTurn}
            className="ml-auto normal-case"
          >
            {t('← back to turn')} {turnNumber - 1}
          </Button>
        ) : srcTurns.some((t) => t.text.trim()) ? (
          <button
            type="button"
            onClick={startNextTurn}
            title={t('Ask for the next step on this task. The current text is kept as an earlier round.')}
            className="ml-auto normal-case text-10 font-mono text-brand hover:underline"
          >
            {t('+ next turn')}
          </button>
        ) : null)}
      </div>
      <textarea
        id="task-desc"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={priorTurns.length > 0 ? t('The next step on this task') : t('Context, links, what done means')}
        className="bg-elevated text-primary border border-border-default rounded-input px-10 py-6 text-13 resize-y"
        style={{ minHeight }}
      />
      {isEdit && taskId && priorTurns.length > 0 && (
        <span className="text-10 font-mono text-tertiary">
          {t('copies as')} {turnRef(String(taskId), turnNumber)}
        </span>
      )}
      <TurnHistory turns={priorTurns} />
    </div>
  )
}
