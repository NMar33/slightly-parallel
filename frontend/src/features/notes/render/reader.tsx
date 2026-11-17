/**
 * A note as read: the head (title, meta, links, what is open, the version
 * switch and the page's acts on a note) and the body. An earlier version
 * reads in place, its marks shown and not changed.
 */

import { useState } from 'react'

import { Segmented } from '../../../components/Segmented'
import { t } from '../../../i18n/scope/notes'
import { NoteBody, type Density } from './blocks'
import { NoteEnvProvider, useNoteEnv } from './env'
import type { Note } from './model'
import { LinksLine, MetaLine, OpenWords, stampOf, useOpen } from './parts'

export function NoteHead({ note, size = 'big', omit, ver, onVer, older }: {
  note: Note; size?: 'big' | 'mid'; omit?: string
  /** The version shown, and the switch; left out, the switch keeps its own. */
  ver?: string; onVer?: (v: string) => void
  /** The earlier version shown, once read. */
  older?: Note
}) {
  const open = useOpen(note)
  const { HeadTools } = useNoteEnv()
  const [own, setOwn] = useState(String(note.versions))
  const v = ver ?? own
  const setV = onVer ?? setOwn
  const versions = Array.from({ length: note.versions }, (_, i) => String(i + 1))
  return (
    <header className="flex flex-col gap-8 min-w-0">
      <h1 tabIndex={-1} className={`m-0 font-semibold text-primary leading-tight ${size === 'big' ? 'text-24' : 'text-20'}`} style={{ letterSpacing: '-0.015em', outline: 'none' }}>{note.title}</h1>
      <MetaLine note={note} task={false} />
      <LinksLine note={note} max={0} omit={omit} />
      <div className="flex items-center gap-12 flex-wrap">
        <OpenWords open={open} />
        <span className="ml-auto flex items-center gap-8 flex-wrap min-w-0 max-w-full">
          {note.versions > 1 && (
            <Segmented label={t('Version')} shape="pill" value={v} onChange={setV}
              options={versions.map((x) => [x, `v${x}`] as const)} />
          )}
          {HeadTools && <HeadTools note={note} />}
        </span>
      </div>
      {v !== String(note.versions) && (
        <p role="status" className="m-0 text-12 text-status-amber">
          {older
            ? t('This is v{v}, an earlier version: read only, with the ticks and answers as they are now.', { v })
            : t('This is v{v}, an earlier version: ticks and answers show as they were, read only. The text below is the latest in this mock.', { v })}
        </p>
      )}
      <span className="sr-only">{stampOf(note.created)}</span>
    </header>
  )
}

/** The head and the whole body, at reading width; the version switch reads an earlier version in place. */
export function NoteRead({ note, density = 'read', size = 'big', omit }: { note: Note; density?: Density; size?: 'big' | 'mid'; /** An id the page already shows above the note. */ omit?: string }) {
  const env = useNoteEnv()
  const [ver, setVer] = useState(String(note.versions))
  const n = ver === String(note.versions) ? null : Number(ver)
  const older = env.useVersion(note, n)
  const body = n != null && older ? older : note
  return (
    <article data-note={note.id} className="flex flex-col gap-16 min-w-0">
      <NoteHead note={note} size={size} omit={omit} ver={ver} onVer={setVer} older={n != null ? older : undefined} />
      {body === note
        ? <NoteBody note={note} density={density} />
        : <NoteEnvProvider value={{ ...env, readOnly: true }}><NoteBody note={body} density={density} /></NoteEnvProvider>}
    </article>
  )
}
