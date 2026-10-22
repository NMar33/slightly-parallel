/*
 * The task window's Title field, with ⌘/Ctrl+Enter to save (Shift for ▶)
 * and the new-task draft line under it. Moved out of TaskEditor.tsx; the
 * window owns the title, the draft and the save.
 */

import type { RefObject } from 'react'
import { Button } from '../../../../components/primitives'
import { LABEL } from '../../../promptlib/taskstyle'
import { t } from '../../../../i18n/scope/project'

export function TitleField({ titleRef, title, setTitle, onSave, showDraft, draftRestored, onDiscardDraft }: {
  titleRef: RefObject<HTMLInputElement>
  title: string
  setTitle: (v: string) => void
  /** ⌘/Ctrl+Enter; `chain` is true with Shift held. */
  onSave: (chain: boolean) => void
  /** New task with something typed (or a draft restored). */
  showDraft: boolean
  draftRestored: boolean
  onDiscardDraft: () => void
}) {
  return (
    <div className="flex flex-col gap-3">
      <label htmlFor="task-title" className={LABEL}>{t('Title')}</label>
      <input
        id="task-title"
        autoFocus
        ref={titleRef}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) onSave(e.shiftKey)
        }}
        placeholder={t('Title shown on the card')}
        className="bg-elevated text-primary border border-border-default rounded-input px-10 py-6 text-14"
      />
      {showDraft && (
        <div className="text-10 font-mono text-tertiary flex items-center gap-8">
          {draftRestored ? t('Unsaved draft restored') : t('Draft saved in this browser')}
          <Button variant="danger-text" size="bare" onClick={onDiscardDraft}>{t('Discard draft')}</Button>
        </div>
      )}
    </div>
  )
}
