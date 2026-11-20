/**
 * Variant B — Queue. The page answers "what waits on me": each note with
 * something open shows the open blocks themselves, working (the choice to
 * answer, the items to tick, the text to paste with its steps), with the
 * paragraph before each so it can be acted on without reading the note.
 * Under the queue, every other note as a row that opens in place.
 * A note stays where it was while the operator works through it; the
 * queue is sorted again on the next visit.
 */

import { useState } from 'react'
import { Inbox } from 'lucide-react'

import { Button } from '../../../../components/primitives/Button'
import { EmptyState } from '../../../../components/states'
import { t, tn } from '../../../../i18n/scope/notes'
import { BlockView, NoteBody } from '../blocks'
import { SUPERSEDED_BY } from '../mock'
import type { Block, Note, Section } from '../model'
import { blocksOf } from '../model'
import { agoOf, FindBox, goTo, KindMark, matches, MetaLine, newestFirst, OpenWords, ProjectMark, Rule, useOpen } from '../parts'
import { NoteHead } from '../reader'
import { openOf, needsYou, useMarks } from '../store'

/** The open things of one section: each with the text just before it. */
function openIn(note: Note, s: Section, marks: ReturnType<typeof useMarks>): Array<{ before?: Block; block: Block }> {
  const flat = blocksOf(s.blocks)
  // A paste note's section with the text to paste: the whole section, steps and all.
  if (note.kind === 'paste' && flat.some((b) => b.type === 'copy' && !marks.copied[b.id])) return flat.map((block) => ({ block }))
  const out: Array<{ before?: Block; block: Block }> = []
  flat.forEach((b, i) => {
    const open = (b.type === 'choice' && marks.answers[b.id] == null)
      || (b.type === 'check' && b.items.some((it) => !(marks.ticks[it.id] ?? it.done)))
    if (open) {
      const prev = flat[i - 1]
      out.push({ before: prev?.type === 'md' ? prev : undefined, block: b })
    }
  })
  return out
}

/** The last paragraph of a text block: enough to act on what follows. */
const lastParagraph = (b: Block) => (b.type === 'md' ? b.text.split(/\n\n/).pop() ?? '' : '')

function QueueCard({ note, read, onRead }: { note: Note; read: boolean; onRead: () => void }) {
  const marks = useMarks()
  const open = useOpen(note)
  // What was open when the page opened stays on the card, ticked or not.
  const [sections] = useState(() => note.sections.map((s) => ({ s, items: openIn(note, s, marks) })).filter((x) => x.items.length))
  const settled = !needsYou(open)
  return (
    <article data-note={note.id} className={`rounded-card border bg-surface flex flex-col gap-12 px-16 py-12 min-w-0 ${read ? 'xl:col-span-2' : ''} ${settled ? 'border-status-green/40' : 'border-border-default'}`}>
      <div className="flex flex-col gap-4 min-w-0">
        <div className="flex items-start gap-12 min-w-0">
          <h2 className="m-0 text-16 font-semibold text-primary leading-snug flex-1 min-w-0">{note.title}</h2>
          {settled ? <span className="text-11 font-mono text-status-green shrink-0">{t('done for now')}</span> : <OpenWords open={open} />}
        </div>
        <MetaLine note={note} />
        <p className="m-0 text-13 text-secondary leading-relaxed">{note.lead}</p>
      </div>
      {sections.map(({ s, items }) => (
        <section key={s.id} aria-label={s.title} className="flex flex-col gap-8 min-w-0">
          <Rule aside={<Button variant="text" size="bare" onClick={() => { if (!read) onRead(); requestAnimationFrame(() => goTo(`${note.id}-${s.id}`)) }}>{t('in the note →')}</Button>}>
            {s.title || t('Opening')}
          </Rule>
          {items.map(({ before, block }, i) => (
            <div key={i} className="flex flex-col gap-6 min-w-0">
              {before && <p className="m-0 text-12 text-secondary leading-relaxed">{lastParagraph(before)}</p>}
              <BlockView block={block} density="compact" />
            </div>
          ))}
        </section>
      ))}
      <div className="flex items-center gap-12 border-t border-border-subtle pt-8">
        <Button variant="link" size="bare" className="text-12" onClick={onRead}>{read ? t('Fold the note') : t('Read the whole note')}</Button>
        <span className="text-11 font-mono text-tertiary">{tn(note.sections.length, '{n} section', '{n} sections')} · {tn(note.words, '{n} word', '{n} words')}</span>
      </div>
      {read && <div className="border-t border-border-subtle pt-12"><NoteBody note={note} /></div>}
    </article>
  )
}

function ArchiveRow({ note, read, onRead }: { note: Note; read: boolean; onRead: () => void }) {
  const open = useOpen(note)
  return (
    <div data-note={note.id} className="border-b border-border-subtle min-w-0">
      <button type="button" onClick={onRead} aria-expanded={read}
        className="w-full text-left grid gap-x-12 gap-y-2 py-8 px-4 hover:bg-hover rounded-input min-w-0 grid-cols-1 md:grid-cols-[88px_minmax(0,1fr)_200px]">
        <span className="flex md:flex-col gap-8 md:gap-2"><KindMark kind={note.kind} /><span className="text-10 font-mono text-tertiary">{agoOf(note.updated)}</span></span>
        <span className="flex flex-col gap-2 min-w-0">
          <span className="text-13 text-primary font-medium">{note.title}</span>
          <span className="text-12 text-secondary line-clamp-2">{note.lead}</span>
        </span>
        <span className="flex flex-col gap-2 min-w-0 md:items-end"><ProjectMark code={note.project} /><OpenWords open={open} /></span>
      </button>
      {read && (
        <div className="px-4 pb-16 pt-8 max-w-[760px] flex flex-col gap-12">
          <NoteHead note={note} size="mid" />
          <NoteBody note={note} />
        </div>
      )}
    </div>
  )
}

export function Queue({ notes }: { notes: Note[] }) {
  const marks = useMarks()
  const [q, setQ] = useState('')
  const [read, setRead] = useState<string | null>(null)
  const toggle = (id: string) => setRead((r) => (r === id ? null : id))
  // Who is in the queue is fixed when the page opens: a card does not jump away under the click that settles it.
  // A note a newer one replaces does not ask for anything any more.
  const [queued] = useState(() => new Set(notes.filter((n) => !SUPERSEDED_BY[n.id] && needsYou(openOf(n, marks))).map((n) => n.id)))
  const found = notes.filter((n) => matches(n, q))
  const queue = found.filter((n) => queued.has(n.id)).sort((a, b) => {
    const oa = openOf(a, marks); const ob = openOf(b, marks)
    return (ob.toAnswer - oa.toAnswer) || newestFirst(a, b)
  })
  const rest = found.filter((n) => !queued.has(n.id)).sort(newestFirst)
  const waiting = queue.reduce((s, n) => { const o = openOf(n, marks); return s + o.toAnswer + o.toTick + o.toCopy }, 0)
  return (
    <div className="flex flex-col gap-16 min-w-0">
      <FindBox value={q} onChange={setQ} found={found.length} of={notes.length} className="max-w-[520px]" />
      <section aria-label={t('Waits on you')} className="flex flex-col gap-12 min-w-0">
        <Rule aside={<span className="text-11 font-mono text-status-amber">{tn(waiting, '{n} thing waits', '{n} things wait')}</span>}>
          {t('Waits on you')} · {tn(queue.length, '{n} note', '{n} notes')}
        </Rule>
        {queue.length === 0
          ? <EmptyState icon={<Inbox size={24} />} title={t('Nothing waits on you.')} subtitle={t('A note joins the queue when it has a choice to answer, items to tick or a text to paste.')} />
          : <div className="grid gap-12 min-w-0 xl:grid-cols-2 items-start">{queue.map((n) => <QueueCard key={n.id} note={n} read={read === n.id} onRead={() => toggle(n.id)} />)}</div>}
      </section>
      <section aria-label={t('For reference')} className="flex flex-col gap-4 min-w-0">
        <Rule>{t('For reference')} · {tn(rest.length, '{n} note', '{n} notes')}</Rule>
        {rest.map((n) => <ArchiveRow key={n.id} note={n} read={read === n.id} onRead={() => toggle(n.id)} />)}
        {!rest.length && <EmptyState compact title={t('Nothing here.')} />}
      </section>
    </div>
  )
}
