import { useEffect, useState } from 'react'
import { StickyNote } from 'lucide-react'

import { consumeNote, readNote } from './store'
import { t } from '../../i18n/scope/system'

/**
 * The quick note, offered where it is most likely to be wanted.
 *
 * A thought jotted while looking at something else often turns out to be the
 * description of a task. This hands it over in one press: the note goes into
 * the field, the note is emptied, and a version of what it said is kept — so
 * pressing it by accident costs nothing, which is what makes one press safe.
 */
export function TakeQuickNote({ onTake }: { onTake: (note: string) => void }) {
  const [note, setNote] = useState(readNote)
  const [took, setTook] = useState(false)

  // The note can change while the window is open — in another tab, or in the
  // panel itself — so read it again when focus comes back.
  useEffect(() => {
    const refresh = () => setNote(readNote())
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])

  if (!note.trim() && !took) return null

  const preview = note.trim().split('\n')[0]?.slice(0, 60) ?? ''
  return (
    <button
      type="button"
      disabled={took}
      onClick={() => {
        const taken = consumeNote()
        if (!taken.trim()) return
        onTake(taken.trim())
        setNote('')
        setTook(true)
      }}
      title={took ? t('The note is now in the description') : t('Paste the quick note here and empty it — "{preview}"', { preview: `${preview}${note.trim().length > 60 ? '…' : ''}` })}
      className={`inline-flex items-center gap-4 h-20 px-8 rounded-pill border text-10 font-mono normal-case tracking-normal ${
        took
          ? 'border-status-green/50 text-status-green'
          : 'border-border-default text-tertiary hover:text-brand hover:border-brand'
      }`}
    >
      <StickyNote size={11} aria-hidden />
      {took ? t('note taken') : t('use quick note')}
    </button>
  )
}
