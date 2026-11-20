/**
 * The tile view (design round 2, kept by K). With the feed hidden, notes stand as tiles on
 * shelves, the way the Entry points page shows topics: the picture (the
 * note's first screenshot, or its outline when it has none), the title,
 * the first paragraph, what is open, the project and the task. A tile
 * opens the note back in the reading layout.
 */

import type { ReactNode } from 'react'

import { LABEL } from '../../../components/ui'
import { t, tn } from '../../../i18n/scope/notes'
import { IdChip } from './blocks'
import { useNoteEnv } from './env'
import { allBlocks, type Block, type Note } from './model'
import { agoOf, KindMark, OpenWords, ProjectMark, useOpen } from './parts'

/** The picture of a tile: the note's first screenshot, when it has one. */
function Face({ note }: { note: Note }) {
  const { Picture } = useNoteEnv()
  const gallery = allBlocks(note).map((x) => x.block).find((b): b is Extract<Block, { type: 'gallery' }> => b.type === 'gallery')
  if (gallery?.shots[0]) {
    return (
      <span className="relative block">
        <Picture src={gallery.shots[0].src} alt={gallery.shots[0].caption} />
        {gallery.shots.length > 1 && (
          <span className="absolute right-6 bottom-6 rounded-pill bg-elevated border border-border-subtle px-6 text-10 font-mono text-secondary">
            {tn(gallery.shots.length, '{n} picture', '{n} pictures')}
          </span>
        )}
      </span>
    )
  }
  // No picture: no face. The tile leads with what is open instead (drawn below the title).
  return null
}

export function NoteTile({ note, onOpen, current = false, extra, hideTask = false }: { note: Note; onOpen: () => void; current?: boolean; extra?: ReactNode; /** The shelf heading names the task already. */ hideTask?: boolean }) {
  const open = useOpen(note)
  const env = useNoteEnv()
  const replaced = note.replacedBy
  return (
    <div data-testid="note-tile" data-note={note.id}
      className={`rounded-input bg-elevated p-10 flex flex-col gap-8 min-w-0 has-[button:focus-visible]:ring-2 has-[button:focus-visible]:ring-brand ${current ? 'ring-2 ring-brand bg-brand-glow/30' : ''} ${replaced ? 'opacity-70' : ''}`}>
      {/* The tile draws the focus (its ring), not the button inside it. */}
      <button type="button" onClick={onOpen} aria-label={t('Read: {title}', { title: note.title })} className="flex flex-col gap-8 text-left min-w-0" style={{ outline: 'none' }}>
        <Face note={note} />
        <span className="flex items-center gap-8 min-w-0">
          <KindMark kind={note.kind} />
          <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{agoOf(note.updated, env.now())}</span>
        </span>
        <span className="text-13 font-semibold text-primary leading-snug break-words">{note.title}</span>
        <span className="text-12 text-secondary leading-snug line-clamp-3">{note.lead}</span>
        <span className="text-10 font-mono text-tertiary">
          {note.sections.some((x) => x.title) && `${tn(note.sections.filter((x) => x.title).length, '{n} section', '{n} sections')} · `}{tn(note.words, '{n} word', '{n} words')}
        </span>
      </button>
      {replaced && <span className="text-11 text-status-amber">{t('Replaced by {id}', { id: replaced })}</span>}
      <OpenWords open={open} done={false} />
      {extra}
      <div className="mt-auto flex items-center gap-8 flex-wrap min-w-0">
        <ProjectMark code={note.project} />
        {note.task && !hideTask && <span className="text-10 font-mono text-tertiary" title={env.entity(note.task)?.title}>{note.task}</span>}
      </div>
    </div>
  )
}

export interface Shelf { key: string; head: ReactNode; items: ReactNode[]; /** Drawn across the shelf after its tiles: what a tile opened. */ after?: ReactNode }

/** Shelves as on the Entry points page: a heading on a rule, tiles in a grid that fills the width. */
export function Shelves({ shelves, label }: { shelves: Shelf[]; label: string }) {
  return (
    <div data-testid="note-shelves" aria-label={label} role="region" className="flex flex-col gap-20 min-w-0">
      {shelves.map((s) => (
        <section key={s.key} aria-label={s.key} className="flex flex-col gap-10 min-w-0">
          {s.head}
          <div className="grid gap-12 min-w-0 grid-cols-1 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]" style={{ gridAutoFlow: 'dense' }}>
            {s.items}
            {s.after && <div className="min-w-0" style={{ gridColumn: '1 / -1' }}>{s.after}</div>}
          </div>
        </section>
      ))}
    </div>
  )
}

/** A shelf's heading: a word or a chip on a rule, and how many. */
export function ShelfHead({ children, count, tone = '' }: { children: ReactNode; count: number; tone?: string }) {
  return (
    <h2 className="m-0 flex items-center gap-8 min-w-0 text-12">
      <span className={`${LABEL} ${tone}`}>{children}</span>
      <span className="text-11 font-mono text-tertiary tabular shrink-0">{tn(count, '{n} note', '{n} notes')}</span>
      <span className="flex-1 border-t border-border-subtle" />
    </h2>
  )
}

/** A task as a shelf heading: its chip with the live title and status. */
export function TaskHead({ id, count, waiting }: { id: string; count: number; waiting: number }) {
  return (
    <h2 className="m-0 flex items-center gap-8 min-w-0 text-12 flex-wrap">
      {id ? <IdChip id={id} /> : <span className={LABEL}>{t('No task')}</span>}
      <span className="text-11 font-mono text-tertiary tabular shrink-0">{tn(count, '{n} note', '{n} notes')}</span>
      {waiting > 0 && <span className="text-11 font-mono text-status-amber shrink-0">{tn(waiting, '{n} waits on an answer', '{n} wait on an answer')}</span>}
      <span className="flex-1 border-t border-border-subtle min-w-[24px]" />
    </h2>
  )
}
