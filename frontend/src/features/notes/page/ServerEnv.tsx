/**
 * The Notes page's note env: chips from the feed's titles, the operator's
 * marks from the server with each new one shown at once and sent, pictures
 * served by id, an earlier version read on demand, and Archive in a note's
 * head. The task window draws its notes inside the same env.
 */

import { useMemo, useState, type ReactNode } from 'react'
import { Archive, ArchiveRestore } from 'lucide-react'

import { Button } from '../../../components/primitives/Button'
import { fail } from '../../../lib/getJson'
import { t } from '../../../i18n/scope/notes'
import { NoteEnvProvider, type Marks, type NoteEnv } from '../render/env'
import type { Note } from '../render/model'
import { toNote, useNoteVersionText, useNoteWrites, type Feed } from './data'

const IMAGE = /^ni_[0-9a-f]{10}$/

function Picture({ src, alt, small }: { src: string; alt: string; small?: boolean }) {
  if (!IMAGE.test(src)) {
    // Only the note's own pictures are drawn: a path or an address in the text stays text.
    return <span className="block w-full rounded-input border border-dashed border-border-default bg-elevated text-10 font-mono text-tertiary p-6 truncate" title={alt}>{src}</span>
  }
  return (
    <img src={`/api/notes/images/${src}/file`} alt={alt} loading="lazy"
      className={`block w-full rounded-input border border-border-default bg-base object-contain ${small ? 'aspect-[16/10] object-cover' : 'max-h-[70vh]'}`} />
  )
}

function useVersion(note: Note, n: number | null): Note | undefined {
  const got = useNoteVersionText(note.id, n)
  return useMemo(() => (n != null && got.data ? toNote({ ...got.data, id: note.id }, got.data.body) : undefined), [got.data, n, note.id])
}

function HeadTools({ note }: { note: Note }) {
  const { archive } = useNoteWrites()
  const archived = !!note.archivedAt
  return (
    <Button variant="ghost" size="sm" iconLeft={archived ? <ArchiveRestore size={12} aria-hidden /> : <Archive size={12} aria-hidden />}
      disabled={archive.isPending} title={archived ? t('Back among the notes') : t('Out of the feed; kept under Archived')}
      onClick={() => archive.mutate({ id: note.id, archived: !archived }, { onError: fail })}>
      {archived ? t('Restore') : t('Archive')}
    </Button>
  )
}

export function ServerNoteEnv({ feed, children }: { feed: Feed | undefined; children: ReactNode }) {
  const { mark } = useNoteWrites()
  // A mark shows at once; the server's answer replaces it when the notes are read again.
  const [mine, setMine] = useState<Marks>({ ticks: {}, answers: {}, copied: {} })
  const server = feed?.marks
  const marks = useMemo<Marks>(() => {
    const answers = { ...(server?.answers ?? {}), ...mine.answers }
    for (const [k, v] of Object.entries(answers)) if (v < 0) delete answers[k]
    return { ticks: { ...(server?.ticks ?? {}), ...mine.ticks }, answers, copied: { ...(server?.copied ?? {}), ...mine.copied } }
  }, [server, mine])
  const env = useMemo<NoteEnv>(() => ({
    entity: (id) => { const e = feed?.entities[id]; return e ? { id, ...e } : undefined },
    marks,
    tick: (item, on) => {
      setMine((m) => ({ ...m, ticks: { ...m.ticks, [item]: on } }))
      mark.mutate({ item, kind: 'tick', value: on }, { onError: fail })
    },
    answer: (item, option) => {
      setMine((m) => ({ ...m, answers: { ...m.answers, [item]: option ?? -1 } }))
      mark.mutate({ item, kind: 'answer', value: option ?? '' }, { onError: fail })
    },
    copied: (item) => {
      setMine((m) => ({ ...m, copied: { ...m.copied, [item]: new Date().toISOString().slice(0, 19) } }))
      mark.mutate({ item, kind: 'copy', value: true }, { onError: fail })
    },
    Picture,
    pictureUrl: (src) => (IMAGE.test(src) ? `/api/notes/images/${src}/file` : null),
    now: () => new Date(),
    noteHref: (id) => `/notes?note=${id}`,
    useVersion,
    HeadTools,
  }), [feed?.entities, marks, mark])
  return <NoteEnvProvider value={env}>{children}</NoteEnvProvider>
}
