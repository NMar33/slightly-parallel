/**
 * The small parts every variant draws a note with: the kind mark, the meta
 * line, the open counts, the outline with what each section holds, the
 * find box and the project and kind pills.
 */

import type { ReactNode } from 'react'
import { Search, X } from 'lucide-react'

import { FilterPill } from '../../../components/FilterPill'
import { Input } from '../../../components/primitives/Input'
import { LABEL } from '../../../components/ui'
import { projectColor } from '../../../utils/projectColor'
import { locale, t, tn } from '../../../i18n/scope/notes'
import { anchorOf, IdChip, useOpenIn } from './blocks'
import { openOf, useMarks, useNoteEnv, type Open } from './env'
import { blocksOf, KINDS, type Note, type NoteKind, type Section } from './model'

export const KIND_WORD: Record<NoteKind, string> = {
  context: t('context'), paste: t('to paste'), review: t('review'), plan: t('plan'), report: t('report'), actions: t('actions'),
}
export const KIND_HINT: Record<NoteKind, string> = {
  context: t('what to know when you come back'),
  paste: t('a text for another chat, with the steps around it'),
  review: t('pictures and the choice they ask for'),
  plan: t('a spec for helper agents'),
  report: t('what a helper found and did'),
  actions: t('what only you can do'),
}
const KIND_TONE: Record<NoteKind, string> = {
  context: 'text-secondary', paste: 'text-brand', review: 'text-status-purple', plan: 'text-status-info', report: 'text-status-green', actions: 'text-status-amber',
}

export function KindMark({ kind }: { kind: NoteKind }) {
  return <span className={`text-10 font-mono uppercase tracking-wide shrink-0 ${KIND_TONE[kind]}`} title={KIND_HINT[kind]}>{KIND_WORD[kind]}</span>
}

export function ProjectMark({ code }: { code: string }) {
  return (
    <span className="inline-flex items-center gap-4 text-11 font-mono text-secondary min-w-0">
      <span aria-hidden className="w-6 h-6 rounded-pill shrink-0" style={{ backgroundColor: projectColor(code) }} />
      <span className="truncate">{code}</span>
    </span>
  )
}

/** "16 Nov 11:15". */
export function stampOf(at: string, now = new Date()): string {
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return ''
  const day = d.toLocaleDateString(locale(), d.getFullYear() === now.getFullYear() ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' })
  return `${day} ${at.slice(11, 16)}`
}

/** "today", "3 days ago", "4 months ago". */
export function agoOf(at: string, now = new Date()): string {
  const days = Math.floor((now.getTime() - new Date(at.slice(0, 10)).getTime()) / 86_400_000)
  if (days <= 0) return t('today')
  if (days === 1) return t('yesterday')
  if (days < 45) return tn(days, '{n} day ago', '{n} days ago')
  return tn(Math.round(days / 30), '{n} month ago', '{n} months ago')
}

/** Project, kind, when, version, words, the chat that wrote it. */
export function MetaLine({ note, task = true }: { note: Note; task?: boolean }) {
  const now = useNoteEnv().now()
  return (
    <div className="flex items-center gap-x-10 gap-y-4 flex-wrap text-11 font-mono text-tertiary min-w-0">
      <KindMark kind={note.kind} />
      <ProjectMark code={note.project} />
      <span title={note.updated}>{stampOf(note.updated, now)}</span>
      <span>v{note.versions}</span>
      <span>{tn(note.words, '{n} word', '{n} words')}</span>
      <span title={t('The chat that wrote it')}>{note.chat}</span>
      {task && note.task && <IdChip id={note.task} />}
    </div>
  )
}

/** The links of a note: task, entry point, publish card, and the other ids it names. */
export function LinksLine({ note, max = 99, omit }: { note: Note; max?: number; /** An id already shown above (a task band): left out here. */ omit?: string }) {
  const own = [note.task, note.entrypoint, note.publish].filter((x): x is string => !!x && x !== omit)
  const others = note.refs.filter((r) => !own.includes(r) && r !== omit)
  return (
    <div className="flex flex-wrap gap-4 min-w-0">
      {own.map((id) => <IdChip key={id} id={id} />)}
      {others.slice(0, max).map((id) => <IdChip key={id} id={id} />)}
      {others.length > max && <span className="text-11 font-mono text-tertiary self-center">{max === 0 ? tn(others.length, '{n} more id in the text', '{n} more ids in the text') : t('+{n} more', { n: others.length - max })}</span>}
    </div>
  )
}

/** The open counts as words: "8 of 12 to tick · 1 choice · not copied". */
export function OpenWords({ open, done = true }: { open: Open; done?: boolean }) {
  const parts: Array<[string, string]> = []
  if (open.toAnswer) parts.push([tn(open.toAnswer, '{n} choice waits', '{n} choices wait'), 'text-status-amber'])
  if (open.toTick) parts.push([t('{left} of {all} to tick', { left: open.toTick, all: open.toTick + open.ticked }), 'text-status-amber'])
  if (open.toCopy) parts.push([t('not copied yet'), 'text-brand'])
  if (!parts.length && done) {
    if (open.ticked) parts.push([t('all {n} ticked', { n: open.ticked }), 'text-status-green'])
    if (open.answered) parts.push([tn(open.answered, '{n} choice answered', '{n} choices answered'), 'text-status-green'])
  }
  if (!parts.length) return null
  return (
    <span className="inline-flex items-center gap-8 flex-wrap text-11 font-mono">
      {parts.map(([w, tone]) => <span key={w} className={tone}>{w}</span>)}
    </span>
  )
}

export function useOpen(note: Note): Open { return openOf(note, useMarks()) }

/** One outline line: the section's name and what it holds besides text. */
function OutlineRow({ note, s, i, onGo, current }: { note: Note; s: Section; i: number; onGo?: (anchor: string) => void; current?: string }) {
  const open = useOpenIn(s.blocks)
  const bs = blocksOf(s.blocks)
  const marks: string[] = []
  if (bs.some((b) => b.type === 'copy')) marks.push(t('paste'))
  if (bs.some((b) => b.type === 'gallery')) marks.push(t('pictures'))
  if (bs.some((b) => b.type === 'mermaid')) marks.push(t('diagram'))
  if (bs.some((b) => b.type === 'md' && /\n\|/.test(b.text))) marks.push(t('table'))
  const anchor = anchorOf(note, s)
  const here = current === anchor
  return (
    <li>
      <a href={`#${anchor}`} onClick={(e) => { if (onGo) { e.preventDefault(); onGo(anchor) } }} aria-current={here ? 'location' : undefined}
        className={`flex items-baseline gap-6 rounded-input px-6 py-2 text-12 hover:text-primary hover:bg-hover min-w-0 ${here ? 'text-primary bg-brand-glow' : 'text-secondary'}`}>
        <span className="min-w-0 flex-1">{s.title || (i === 0 ? t('Opening') : '')}</span>
        {open > 0 && <span className="text-10 font-mono text-status-amber shrink-0">{tn(open, '{n} open', '{n} open')}</span>}
        {marks.length > 0 && <span className="text-10 font-mono text-tertiary shrink-0">{marks.join(' · ')}</span>}
      </a>
    </li>
  )
}

/** The sections of a note; `current` (an anchor) marks the one in view. */
export function Outline({ note, onGo, current }: { note: Note; onGo?: (anchor: string) => void; current?: string }) {
  return (
    <ol className="m-0 p-0 list-none flex flex-col gap-1" aria-label={t('Outline')}>
      {note.sections.map((s, i) => <OutlineRow key={s.id} note={note} s={s} i={i} onGo={onGo} current={current} />)}
    </ol>
  )
}

/** Scroll to a section inside the page's own scroller. */
export function goTo(anchor: string) {
  const el = document.getElementById(anchor)
  if (!el) return
  for (let p: HTMLElement | null = el; p; p = p.parentElement) if (p.tagName === 'DETAILS') (p as HTMLDetailsElement).open = true
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

/* ------------------------------------------------------------------- find */

/** Words in the title, the text or the titles of the tasks it names. */
export function matches(note: Note, q: string): boolean {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const hay = `${note.title}\n${note.body}\n${note.project}\n${KIND_WORD[note.kind]}`.toLowerCase()
  return words.every((w) => hay.includes(w))
}

/** Where a word sits in the note: the section and a few words around it. */
export function hitOf(note: Note, q: string): { section: Section; text: string } | null {
  const w = q.trim().toLowerCase().split(/\s+/)[0]
  if (!w) return null
  for (const s of note.sections) {
    const text = blocksOf(s.blocks).map((b) => ('text' in b ? b.text : b.type === 'check' ? b.items.map((i) => i.text).join('\n') : b.type === 'choice' ? `${b.question}\n${b.options.join('\n')}` : '')).join('\n')
    const at = text.toLowerCase().indexOf(w)
    if (at >= 0) return { section: s, text: `${at > 40 ? '…' : ''}${text.slice(Math.max(0, at - 40), at + 90).replace(/\s+/g, ' ')}…` }
  }
  return null
}

export function FindBox({ value, onChange, found, of, className = '' }: { value: string; onChange: (v: string) => void; found: number; of: number; className?: string }) {
  return (
    <div className={`relative min-w-0 ${className}`}>
      <Search size={13} className="absolute left-8 top-1/2 -translate-y-1/2 text-tertiary pointer-events-none" aria-hidden />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={t('Find in notes: words, an id, a project')} aria-label={t('Find in notes')}
        className="pl-24 pr-48 w-full" />
      <span className="absolute right-8 top-1/2 -translate-y-1/2 flex items-center gap-4 text-10 font-mono text-tertiary">
        {value && <span className="tabular">{found}/{of}</span>}
        {value && <button type="button" aria-label={t('Clear')} onClick={() => onChange('')} className="hover:text-primary"><X size={12} aria-hidden /></button>}
      </span>
    </div>
  )
}

export function ProjectPills({ notes, value, onChange }: { notes: Note[]; value: string; onChange: (v: string) => void }) {
  const codes = [...new Set(notes.map((n) => n.project))]
  return (
    <div className="flex items-center gap-4 flex-wrap" role="group" aria-label={t('Projects')}>
      <FilterPill on={value === ''} onClick={() => onChange('')} count={notes.length}>{t('all')}</FilterPill>
      {codes.map((c) => (
        <FilterPill key={c} on={value === c} onClick={() => onChange(value === c ? '' : c)} dot={projectColor(c)} count={notes.filter((n) => n.project === c).length}>{c}</FilterPill>
      ))}
    </div>
  )
}

export function KindPills({ notes, value, onChange }: { notes: Note[]; value: NoteKind | ''; onChange: (v: NoteKind | '') => void }) {
  return (
    <div className="flex items-center gap-4 flex-wrap" role="group" aria-label={t('Kinds')}>
      {KINDS.filter((k) => notes.some((n) => n.kind === k)).map((k) => (
        <FilterPill key={k} on={value === k} title={KIND_HINT[k]} onClick={() => onChange(value === k ? '' : k)} count={notes.filter((n) => n.kind === k).length}>{KIND_WORD[k]}</FilterPill>
      ))}
    </div>
  )
}

export const newestFirst = (a: Note, b: Note) => b.updated.localeCompare(a.updated)

/** A mono label on a rule line, as the finished pages head their groups. */
export function Rule({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center gap-8 min-w-0">
      <span className={LABEL}>{children}</span>
      <span className="flex-1 border-t border-border-subtle" />
      {aside}
    </div>
  )
}
