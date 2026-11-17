/**
 * Variant E — Handoff. The page is laid out by what the operator does
 * with a note's content, not by note: texts to paste into another chat,
 * plans to hand to helper agents, actions with his own hands, choices to
 * make. Each packet carries its payload in the middle with the steps
 * before and after it from the note, and names its note. Notes that are
 * only to know (context, reports) sit in a rail and open in place of the
 * lanes. "Copied" is recorded, never shown as "sent".
 */

import { useState, type ReactNode } from 'react'
import { ClipboardCopy, Hand, MessagesSquare, Split, X } from 'lucide-react'

import { CopyButton } from '../../../../components/CopyButton'
import { EmptyState } from '../../../../components/states'
import { t } from '../../../../i18n/scope/notes'
import { BlockView, Gallery, NoteBody, NoteText } from '../blocks'
import { allBlocks, blocksOf, type Block, type Note } from '../model'
import { agoOf, FindBox, KindMark, matches, newestFirst, OpenWords, Outline, ProjectMark, Rule, useOpen } from '../parts'
import { NoteHead } from '../reader'
import { SUPERSEDED_BY } from '../mock'

interface Packet { key: string; note: Note; title: string; before: Block[]; payload: Block[]; after: Block[] }

/** The blocks around one block in its section: text before it, text after it. */
function around(note: Note, target: Block): { title: string; before: Block[]; after: Block[] } {
  for (const s of note.sections) {
    const flat = blocksOf(s.blocks)
    const i = flat.indexOf(target)
    if (i >= 0) {
      return { title: s.title, before: flat.slice(0, i).filter((b) => b.type === 'md'), after: flat.slice(i + 1).filter((b) => b.type === 'md') }
    }
  }
  return { title: '', before: [], after: [] }
}

function packets(notes: Note[]) {
  const chat: Packet[] = []; const agents: Note[] = []; const hands: Packet[] = []; const decide: Packet[] = []
  for (const n of notes) {
    const flat = allBlocks(n).map((x) => x.block)
    if (n.kind === 'plan') { agents.push(n); continue }
    if (n.kind === 'paste') {
      for (const b of flat.filter((x) => x.type === 'copy')) {
        const a = around(n, b)
        chat.push({ key: `${n.id}-${chat.length}`, note: n, title: a.title, before: a.before, payload: [b], after: [...a.after, ...flat.filter((x) => x.type === 'check')] })
      }
      continue
    }
    // One packet per note: its checklists under their section names, its commands once.
    const checks = flat.filter((x) => x.type === 'check')
    if (checks.length && !SUPERSEDED_BY[n.id]) {
      const payload: Block[] = []
      for (const b of checks) {
        const a = around(n, b)
        if (a.title && checks.length > 1) payload.push({ type: 'md', text: `**${a.title}**` })
        payload.push(b)
      }
      if (n.kind === 'actions') payload.push(...flat.filter((x) => x.type === 'copy'))
      const a = around(n, checks[0]!)
      hands.push({ key: `${n.id}-h`, note: n, title: checks.length > 1 ? '' : a.title, before: a.before.slice(-1), payload, after: [] })
    }
    for (const b of flat.filter((x) => x.type === 'choice')) {
      const a = around(n, b)
      decide.push({ key: `${n.id}-d${decide.length}`, note: n, title: a.title, before: [], payload: [b], after: [] })
    }
  }
  return { chat, agents, hands, decide }
}

function Source({ note, onRead }: { note: Note; onRead: (id: string) => void }) {
  return (
    <span className="flex items-center gap-8 flex-wrap min-w-0 text-11 font-mono text-tertiary">
      <KindMark kind={note.kind} />
      <button type="button" onClick={() => onRead(note.id)} className="text-12 font-sans text-primary hover:text-brand text-left">{note.title}</button>
      <ProjectMark code={note.project} />
      <span>{agoOf(note.updated)}</span>
    </span>
  )
}

function PacketCard({ p, onRead, gallery }: { p: Packet; onRead: (id: string) => void; gallery?: boolean }) {
  const g = gallery ? allBlocks(p.note).map((x) => x.block).find((b): b is Extract<Block, { type: 'gallery' }> => b.type === 'gallery') : undefined
  return (
    <article data-note={p.note.id} className="rounded-card border border-border-subtle bg-surface px-16 py-12 flex flex-col gap-10 min-w-0">
      <Source note={p.note} onRead={onRead} />
      {p.title && <h3 className="m-0 text-14 font-semibold text-primary">{p.title}</h3>}
      {p.before.map((b, i) => <div key={i} className="text-tertiary"><BlockView block={b} density="compact" /></div>)}
      {g && <Gallery block={g} size="strip" />}
      {p.payload.map((b, i) => <BlockView key={i} block={b} />)}
      {p.after.length > 0 && <span className="text-10 font-mono uppercase tracking-wide text-tertiary">{t('after')}</span>}
      {p.after.map((b, i) => <BlockView key={i} block={b} density="compact" />)}
    </article>
  )
}

function PlanCard({ note, onRead }: { note: Note; onRead: (id: string) => void }) {
  const copies = allBlocks(note).map((x) => x.block).filter((b): b is Extract<Block, { type: 'copy' }> => b.type === 'copy')
  return (
    <article data-note={note.id} className="rounded-card border border-border-subtle bg-surface px-16 py-12 flex flex-col gap-10 min-w-0">
      <Source note={note} onRead={onRead} />
      <NoteText text={note.lead} density="compact" />
      <div className="grid gap-12 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] min-w-0">
        <div className="min-w-0"><Outline note={note} onGo={() => onRead(note.id)} /></div>
        <div className="flex flex-col gap-8 min-w-0">
          <CopyButton text={note.body} title={t('Copy the whole plan as markdown')} label={t('Copy the whole plan')}
            className="inline-flex items-center justify-center gap-6 h-32 px-12 rounded-input bg-brand text-on-brand text-13 hover:bg-brand-hover" />
          <span className="text-11 text-tertiary">{t('A helper gets the file as written: ids stay ids, the checklist stays markdown.')}</span>
        </div>
      </div>
      {copies.map((b) => <BlockView key={b.id} block={b} density="compact" />)}
    </article>
  )
}

function Lane({ icon, title, count, children }: { icon: ReactNode; title: string; count: number; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-10 min-w-0">
      <Rule aside={<span className="text-11 font-mono text-tertiary">{count}</span>}><span className="inline-flex items-center gap-6">{icon}{title}</span></Rule>
      {count ? children : <EmptyState compact title={t('Nothing here.')} />}
    </section>
  )
}

function RefRow({ note, onRead }: { note: Note; onRead: (id: string) => void }) {
  const open = useOpen(note)
  return (
    <button type="button" onClick={() => onRead(note.id)} className="text-left flex flex-col gap-2 rounded-input px-8 py-6 hover:bg-hover min-w-0">
      <span className="flex items-center gap-8"><KindMark kind={note.kind} /><span className="text-10 font-mono text-tertiary ml-auto">{agoOf(note.updated)}</span></span>
      <span className="text-13 text-primary leading-snug">{note.title}</span>
      <span className="text-12 text-secondary line-clamp-3">{note.lead}</span>
      <OpenWords open={open} done={false} />
    </button>
  )
}

export function Handoff({ notes }: { notes: Note[] }) {
  const [q, setQ] = useState('')
  const [reading, setReading] = useState<string | null>(null)
  const found = notes.filter((n) => matches(n, q)).sort(newestFirst)
  const { chat, agents, hands, decide } = packets(found)
  const refs = found.filter((n) => n.kind === 'context' || n.kind === 'report')
  const note = notes.find((n) => n.id === reading)
  const read = (id: string) => { setReading(id); requestAnimationFrame(() => document.getElementById('handoff-reading')?.scrollIntoView({ behavior: 'smooth' })) }
  return (
    <div className="flex flex-col gap-16 min-w-0">
      <FindBox value={q} onChange={setQ} found={found.length} of={notes.length} className="max-w-[520px]" />
      <div className="grid gap-24 min-w-0 lg:grid-cols-[minmax(0,1fr)_280px] items-start">
        <div className="flex flex-col gap-24 min-w-0">
          {note && (
            <section id="handoff-reading" aria-label={note.title} className="rounded-card border border-brand/40 bg-surface px-24 py-20 max-sm:px-12 flex flex-col gap-16 min-w-0 scroll-mt-[16px]">
              <button type="button" onClick={() => setReading(null)} className="self-end inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-primary"><X size={12} aria-hidden />{t('close')}</button>
              <NoteHead note={note} size="mid" />
              <NoteBody note={note} />
            </section>
          )}
          <Lane icon={<MessagesSquare size={12} aria-hidden />} title={t('Into another chat')} count={chat.length}>
            {chat.map((p) => <PacketCard key={p.key} p={p} onRead={read} />)}
          </Lane>
          <Lane icon={<Split size={12} aria-hidden />} title={t('To helper agents')} count={agents.length}>
            {agents.map((n) => <PlanCard key={n.id} note={n} onRead={read} />)}
          </Lane>
          <Lane icon={<Hand size={12} aria-hidden />} title={t('With your own hands')} count={hands.length}>
            <div className="grid gap-12 xl:grid-cols-2 items-start min-w-0">{hands.map((p) => <PacketCard key={p.key} p={p} onRead={read} />)}</div>
          </Lane>
          <Lane icon={<ClipboardCopy size={12} aria-hidden />} title={t('To decide')} count={decide.length}>
            {decide.map((p, i) => <PacketCard key={p.key} p={p} onRead={read} gallery={i === 0 || decide[i - 1]!.note.id !== p.note.id} />)}
          </Lane>
        </div>
        <aside aria-label={t('To know')} className="flex flex-col gap-6 min-w-0 lg:sticky lg:top-0">
          <Rule aside={<span className="text-11 font-mono text-tertiary">{refs.length}</span>}>{t('To know')}</Rule>
          <p className="m-0 text-11 text-tertiary">{t('Notes to read, not to act on.')}</p>
          {refs.map((n) => <RefRow key={n.id} note={n} onRead={read} />)}
        </aside>
      </div>
    </div>
  )
}
