/**
 * Variant D — Feed. Notes in the order they happened, day by day, the way
 * the Publish feed reads: each note at its latest moment as a card that
 * already shows its opening, its sections, and its open blocks working
 * (bounded: the first items, the first lines), expanding in place to the
 * whole note. The earlier moments of a note (written, each new version,
 * copied) are ledger lines on their days that point to the card.
 */

import { Fragment, useState } from 'react'

import { Button } from '../../../../components/primitives/Button'
import { EmptyState } from '../../../../components/states'
import { locale, t, tn } from '../../../../i18n/scope/notes'
import { Checklist, Choice, CopyBlock, Gallery, NoteBody } from '../blocks'
import { MOCK_NOW } from '../mock'
import { allBlocks, type Block, type Note } from '../model'
import { anchorOf } from '../blocks'
import { FindBox, goTo, KindMark, KindPills, LinksLine, matches, MetaLine, OpenWords, ProjectPills, Rule, useOpen } from '../parts'
import { isTicked, useMarks } from '../store'
import type { NoteKind } from '../model'

type Moment = { at: string; note: Note; what: 'card' | 'written' | 'version' | 'copied'; v?: number }

function momentsOf(notes: Note[], copied: Record<string, string>): Moment[] {
  const out: Moment[] = []
  for (const n of notes) {
    out.push({ at: n.updated, note: n, what: 'card' })
    if (n.versions > 1) out.push({ at: n.created, note: n, what: 'written', v: 1 })
    for (const { block } of allBlocks(n)) if (block.type === 'copy' && copied[block.id]) out.push({ at: copied[block.id]!, note: n, what: 'copied' })
  }
  return out.sort((a, b) => b.at.localeCompare(a.at))
}

const dayWord = (day: string) => {
  const d = new Date(`${day}T12:00:00`)
  const diff = Math.round((new Date(MOCK_NOW.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 86_400_000)
  const date = d.toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'long' })
  return diff === 0 ? `${t('Today')} · ${date}` : diff === 1 ? `${t('Yesterday')} · ${date}` : date
}

/** The open blocks of a note, bounded: what to answer, the first items to tick, the first lines to paste. */
function OpenPreview({ note }: { note: Note }) {
  const m = useMarks()
  const [shown] = useState(() => {
    const picks: Block[] = []
    for (const { block: b } of allBlocks(note)) {
      if (picks.length >= 2) break
      if (b.type === 'choice' && m.answers[b.id] == null) picks.push(b)
      else if (b.type === 'check' && b.items.some((it) => !isTicked(m, it.id, it.done))) picks.push(b)
      else if (b.type === 'copy' && note.kind === 'paste' && !m.copied[b.id]) picks.push(b)
    }
    return picks
  })
  if (!shown.length) return null
  return (
    <div className="flex flex-col gap-8 min-w-0">
      {shown.map((b, i) => b.type === 'choice' ? <Choice key={i} block={b} />
        : b.type === 'check' ? <Checklist key={i} block={b} limit={4} />
          : b.type === 'copy' ? <CopyBlock key={i} block={b} density="compact" lines={6} /> : null)}
    </div>
  )
}

function Card({ note, open: expanded, onToggle }: { note: Note; open: boolean; onToggle: () => void }) {
  const open = useOpen(note)
  const gallery = allBlocks(note).map((x) => x.block).find((b): b is Extract<Block, { type: 'gallery' }> => b.type === 'gallery')
  return (
    <article id={`feed-${note.id}`} data-note={note.id} className="rounded-card border border-border-subtle bg-surface px-16 py-12 flex flex-col gap-10 min-w-0 scroll-mt-[16px]">
      <div className="flex items-start gap-12 min-w-0">
        <h3 className="m-0 text-16 font-semibold text-primary leading-snug flex-1 min-w-0">{note.title}</h3>
        <OpenWords open={open} />
      </div>
      <MetaLine note={note} task={false} />
      <LinksLine note={note} max={4} />
      {expanded ? <NoteBody note={note} /> : (
        <>
          <p className="m-0 text-13 text-secondary leading-relaxed max-w-[760px]">{note.lead}</p>
          <div className="flex flex-wrap gap-4">
            {note.sections.filter((s) => s.title).map((s) => (
              <button key={s.id} type="button" onClick={() => { onToggle(); requestAnimationFrame(() => goTo(anchorOf(note, s))) }}
                className="text-11 px-6 h-20 rounded-pill border border-border-subtle text-secondary hover:text-primary hover:border-border-default">{s.title}</button>
            ))}
          </div>
          {gallery && <div className="max-w-[520px]"><Gallery block={gallery} size="strip" /></div>}
          <OpenPreview note={note} />
        </>
      )}
      <Button variant="link" size="bare" className="self-start text-12" onClick={onToggle}>
        {expanded ? t('Fold') : t('Read the whole note · {n}', { n: tn(note.words, '{n} word', '{n} words') })}
      </Button>
    </article>
  )
}

const LEDGER: Record<Exclude<Moment['what'], 'card'>, string> = {
  written: t('written, v1'), version: t('new version'), copied: t('the text to paste was copied'),
}

export function Feed({ notes }: { notes: Note[] }) {
  const m = useMarks()
  const [q, setQ] = useState('')
  const [project, setProject] = useState('')
  const [kind, setKind] = useState<NoteKind | ''>('')
  const [open, setOpen] = useState<string | null>(null)
  const found = notes.filter((n) => (!project || n.project === project) && (!kind || n.kind === kind) && matches(n, q))
  const moments = momentsOf(found, m.copied)
  const days = [...new Set(moments.map((x) => x.at.slice(0, 10)))]
  return (
    <div className="flex flex-col gap-16 min-w-0 max-w-[920px]">
      <div className="flex flex-col gap-8">
        <FindBox value={q} onChange={setQ} found={found.length} of={notes.length} className="max-w-[520px]" />
        <div className="flex items-center gap-12 flex-wrap">
          <ProjectPills notes={notes} value={project} onChange={setProject} />
          <KindPills notes={notes} value={kind} onChange={setKind} />
        </div>
      </div>
      {!moments.length && <EmptyState compact title={t('Nothing matches.')} />}
      {days.map((day) => (
        <section key={day} aria-label={day} className="flex flex-col gap-10 min-w-0">
          <Rule>{dayWord(day)}</Rule>
          {moments.filter((x) => x.at.startsWith(day)).map((x, i) => (
            <Fragment key={`${x.note.id}-${x.what}-${i}`}>
              {x.what === 'card'
                ? <Card note={x.note} open={open === x.note.id} onToggle={() => setOpen((o) => (o === x.note.id ? null : x.note.id))} />
                : (
                  <p className="m-0 flex items-center gap-8 flex-wrap text-12 text-secondary pl-16 border-l-2 border-border-subtle">
                    <span className="text-11 font-mono text-tertiary">{x.at.slice(11, 16)}</span>
                    <KindMark kind={x.note.kind} />
                    <button type="button" className="text-primary hover:text-brand text-left" onClick={() => document.getElementById(`feed-${x.note.id}`)?.scrollIntoView({ behavior: 'smooth' })}>{x.note.title}</button>
                    <span className="text-tertiary">— {LEDGER[x.what]}</span>
                  </p>
                )}
            </Fragment>
          ))}
        </section>
      ))}
    </div>
  )
}
