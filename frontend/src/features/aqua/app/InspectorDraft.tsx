import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from '../../../components/primitives'
import { copyText } from '../../../lib/useCopy'
import { t } from '../../../i18n/scope/aqua'
import { TaskAddModal } from '../../project/kanban/TaskWindow'
import { saveNativeDraft } from './bridge'
import { useInspectorDraft } from './inspectorDraftStore'

export { useInspectorDraft } from './inspectorDraftStore'

export function InspectorDraft({ project, draft }: { project: string; draft: ReturnType<typeof useInspectorDraft> }) {
  const editor = useRef<HTMLTextAreaElement>(null)
  const [newTask, setNewTask] = useState<{ title: string; description: string } | null>(null)
  const [exporting, setExporting] = useState(false)
  const query = useQueryClient()
  const { text, conflict, unavailable, undo } = draft.state

  if (!project) return <p className="p-12 text-12 aq-ink3">{t('Open a project to use its draft.')}</p>

  function selectionOrText() {
    const el = editor.current
    return el && el.selectionEnd > el.selectionStart ? text.slice(el.selectionStart, el.selectionEnd) : text
  }

  function createTask() {
    const [first, ...rest] = selectionOrText().trim().split(/\r?\n/)
    if (!first) return
    setNewTask({ title: first.replace(/^#{1,6}\s+/, '').trim(), description: rest.join('\n').trim() })
  }

  async function saveAs() {
    setExporting(true)
    try {
      const name = `${project.replace(/[^\p{L}\p{N}._-]/gu, '-').replace(/^\.+/, '').slice(0, 80) || 'project'}-draft`
      const native = saveNativeDraft(name, text)
      if (native) {
        await native
      } else {
        const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
        const link = document.createElement('a')
        link.href = url
        link.download = `${name}.md`
        document.body.append(link)
        link.click()
        link.remove()
        setTimeout(() => URL.revokeObjectURL(url), 4000)
      }
    } catch {
      toast.error(t('Could not save the Markdown file.'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div data-inspector-edit className="flex min-h-0 flex-1 flex-col gap-8 p-8">
      {unavailable && <p role="status" className="m-0 text-12">{t('The draft could not be saved locally.')}</p>}
      {conflict && (
        <div role="status" className="flex flex-wrap gap-4 text-12">
          <p className="m-0 basis-full">{t('This draft changed in another window.')}</p>
          <button type="button" className="aq-btn line" onClick={() => void draft.keepBoth()}>{t('Keep both texts')}</button>
          <button type="button" className="aq-btn" onClick={() => void draft.useSaved()}>{t('Use saved text')}</button>
        </div>
      )}
      <textarea ref={editor} aria-label={t('Project draft')} value={text} onChange={(event) => draft.edit(event.target.value)}
        className="w-full min-h-0 flex-1 resize-none rounded-md border border-border-default bg-surface p-8 font-mono text-12 leading-relaxed text-primary focus:border-border-strong focus:outline-none" spellCheck={false} />
      <div className="flex shrink-0 flex-wrap items-center gap-4">
        <button type="button" className="aq-btn line" disabled={!text.trim()} onClick={() => void copyText(selectionOrText())}>{t('Copy')}</button>
        <button type="button" className="aq-btn line" disabled={exporting || !text} onClick={() => void saveAs()}>{t('Save as Markdown')}</button>
        <button type="button" className="aq-btn line" disabled={!text.trim()} onClick={createTask}>{t('Create task')}</button>
        {undo === null
          ? <button type="button" className="aq-btn" disabled={conflict || !text} onClick={() => void draft.clear()}>{t('Clear draft')}</button>
          : <button type="button" className="aq-btn" onClick={() => void draft.undoClear()}>{t('Undo clear')}</button>}
      </div>
      {newTask && createPortal(
        <div data-inspector-edit>
          <TaskAddModal projectCode={project} initialTitle={newTask.title} initialDescription={newTask.description} initialStatus="todo"
            onClose={() => setNewTask(null)}
            onSaved={(result) => {
              void query.invalidateQueries({ queryKey: ['tasks'] })
              if (!result?.keepOpen && !result?.existing) setNewTask(null)
            }} />
        </div>,
        document.body,
      )}
    </div>
  )
}
