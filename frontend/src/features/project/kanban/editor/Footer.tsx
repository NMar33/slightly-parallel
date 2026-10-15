/*
 * The task window's bottom row: delete and archive/restore (edit mode),
 * the project line, Cancel, Save and ▶ (save and start the next). Moved
 * out of TaskEditor.tsx; the window owns the save and the asking row.
 */

import { useQuery } from '@tanstack/react-query'
import { Layers } from 'lucide-react'
import { OPERATOR_ACTOR } from '../../types'
import { fail, getJson, postJson } from '../../../../lib/getJson'
import { hMin } from '../../../../utils/format'
import type { ChainMode, TaskRow } from '../model'
import type { Asking } from './types'
import { t } from '../../../../i18n/scope/project'

export function EditorFooter({
  isEdit, existingTask, setAsking, onSaved, homeProject, projects, onClose, save, canSave, saving, chain,
}: {
  isEdit: boolean
  existingTask?: TaskRow | null
  setAsking: (a: Asking) => void
  onSaved: () => void
  homeProject: string
  projects: string[]
  onClose: () => void
  save: (chain?: boolean) => Promise<void>
  canSave: boolean
  saving: boolean
  chain: ChainMode
}) {
  return (
    <div className="flex items-center gap-8 flex-wrap">
      {isEdit && existingTask && (
        <>
          <button
            type="button"
            onClick={() => setAsking({
              text: t('Delete “{title}”. It moves to the .trash folder with its history, links and notes.', { title: existingTask.title ?? existingTask.id }),
              action: t('Delete'),
              run: async () => {
                try {
                  await postJson(`/api/tasks/${encodeURIComponent(existingTask.id)}/delete`, {})
                } catch (e) { fail(e); return }
                onSaved()
              },
            })}
            className="px-8 py-6 rounded-input border border-transparent text-status-red/80 hover:text-status-red hover:border-status-red/40 font-mono text-11"
            title={t('Move to .trash. Move the folder back to restore it.')}
          >{t('delete')}</button>
          <button
            type="button"
            onClick={async () => {
              const verb = existingTask.archived_at ? 'restore' : 'archive'
              try {
                await postJson(`/api/tasks/${encodeURIComponent(existingTask.id)}/${verb}`, { actor: OPERATOR_ACTOR })
              } catch (e) { fail(e); return }
              onSaved()
            }}
            className="px-8 py-6 rounded-input border border-transparent text-tertiary hover:text-primary hover:border-border-default font-mono text-11"
            title={existingTask.archived_at ? t('Bring it back to the board') : t('Hide from the board')}
          >{existingTask.archived_at ? t('restore') : t('archive')}</button>
        </>
      )}
      <span className="text-11 text-tertiary font-mono">
        {t('project ·')} <span className="text-secondary">{homeProject}</span>
        {projects.length > 1 && <span> +{projects.length - 1}</span>}
        {existingTask?.archived_at && <span className="text-status-amber"> {t('· archived')}</span>}
      </span>
      {existingTask && <TaskTime taskId={existingTask.id} />}
      <span className="text-11 text-tertiary font-mono">
        {t('· ⌘/Ctrl+Enter to save')}
      </span>
      <button
        type="button"
        onClick={onClose}
        className="ml-auto px-12 py-6 rounded-input border border-border-default text-secondary font-mono text-12 hover:text-primary"
      >{t('Cancel')}</button>
      <span className="inline-flex items-stretch">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!canSave}
          className={`px-14 py-6 font-mono text-12 font-semibold ${isEdit ? 'rounded-input' : 'rounded-l-input'} ${canSave ? 'bg-brand text-on-brand hover:bg-brand-hover' : 'bg-elevated text-tertiary cursor-not-allowed'}`}
        >
          {saving ? 'Saving…' : t('Save')}
        </button>
        {!isEdit && (
          <button
            type="button"
            onClick={() => void save(true)}
            disabled={!canSave}
            aria-label={chain === 'group'
              ? t('Save and start the next task, grouped with this one')
              : t('Save and start the next task')}
            title={chain === 'group'
              ? t('Save, then open a new task grouped after this one, in the same sprint, lane and column. Change the mode with ⚙.')
              : t('Save, then open a new task in the same sprint, lane and column. Change the mode with ⚙.')}
            className={`px-8 py-6 rounded-r-input border-l font-mono text-12 font-semibold inline-flex items-center gap-2 ${canSave ? 'bg-brand text-on-brand hover:bg-brand-hover border-base/25' : 'bg-elevated text-tertiary cursor-not-allowed border-border-default'}`}
          >
            {chain === 'group' ? <Layers size={11} aria-hidden /> : null}
            ▶
          </button>
        )}
      </span>
    </div>
  )
}

/** Time on this task — the timer's entries that name it, share applied. */
function TaskTime({ taskId }: { taskId: string }) {
  const got = useQuery({
    queryKey: ['time-task', taskId],
    queryFn: ({ signal }) => getJson<{ total_min: number }>(`/api/time/summary?task_id=${encodeURIComponent(taskId)}`, signal),
  }).data
  if (!got || got.total_min <= 0) return null
  return (
    <span className="text-11 text-tertiary font-mono" title={t('Time tracked on this task, by hand and by the timer')}>
      · <span className="text-secondary">{hMin(got.total_min, '0m')}</span> {t('on this')}
    </span>
  )
}
