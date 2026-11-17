/**
 * A note as read — moved to the shared module (../render/reader). The
 * design round's head carries a mock "Attach to a Publish card" (MockHeadTools).
 */

import { Paperclip } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '../../../components/primitives/Button'
import { t } from '../../../i18n/scope/notes'
import type { Note } from '../render/model'
import { IdChip } from './blocks'

export { NoteHead, NoteRead } from '../render/reader'

export function MockHeadTools({ note }: { note: Note }) {
  return note.publish
    ? <span className="inline-flex items-center gap-4 flex-wrap min-w-0 max-w-full text-11 font-mono text-tertiary"><Paperclip size={12} aria-hidden />{t('attached to')} <IdChip id={note.publish} /></span>
    : <Button variant="ghost" size="sm" iconLeft={<Paperclip size={12} aria-hidden />} onClick={() => toast.success(t('Mock: the card picker opens here.'))}>{t('Attach to a Publish card')}</Button>
}
