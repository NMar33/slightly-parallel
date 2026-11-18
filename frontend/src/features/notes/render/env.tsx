/**
 * What a drawn note needs from the page around it: the live title and
 * status of an id it names, the operator's marks and the acts that change
 * them, how a picture is drawn, what "now" is, where a note's page is and
 * how an earlier version is read. The Notes page gives the server's; the
 * design round gives its mock. Without a provider a note still draws, with
 * no chips' titles and marks that stay where they are.
 */

import { createContext, useContext, type ComponentType, type ReactNode } from 'react'

import { allBlocks, type Note } from './model'

export interface Entity { id: string; title: string; status: string; project: string }

/** The operator's marks on notes, by item id (`nt_…:k:<hash>`): ticks, answers (the option's index), copies (when). */
export interface Marks {
  ticks: Record<string, boolean>
  answers: Record<string, number>
  copied: Record<string, string>
}

export const NO_MARKS: Marks = { ticks: {}, answers: {}, copied: {} }

export interface NoteEnv {
  entity: (id: string) => Entity | undefined
  marks: Marks
  tick: (item: string, on: boolean) => void
  answer: (item: string, option: number | null) => void
  copied: (item: string) => void
  /** A picture by its src (`ni_…` on the page; `shot:…` in the mock). */
  Picture: ComponentType<{ src: string; alt: string; small?: boolean }>
  /** The address of a picture to open large, or null where it has none (the mock). */
  pictureUrl?: (src: string) => string | null
  now: () => Date
  /** The link to a note on the Notes page. */
  noteHref: (id: string) => string
  /** Marks are shown, not changed (an earlier version). */
  readOnly?: boolean
  /** An earlier version of a note, parsed; undefined while loading or where there are none to read (the mock). */
  useVersion: (note: Note, n: number | null) => Note | undefined
  /** Beside the version switch in a note's head: the page's acts on a note. */
  HeadTools?: ComponentType<{ note: Note }>
}

function Plain({ src, alt }: { src: string; alt: string }) {
  return <span className="block aspect-[16/10] w-full rounded-input border border-border-default bg-elevated text-10 font-mono text-tertiary p-6 truncate" title={alt}>{src}</span>
}

const noop = () => undefined
export const BARE_ENV: NoteEnv = {
  entity: () => undefined, marks: NO_MARKS, tick: noop, answer: noop, copied: noop, Picture: Plain,
  now: () => new Date(), noteHref: (id) => `/notes?note=${id}`, useVersion: () => undefined,
}

const Ctx = createContext<NoteEnv>(BARE_ENV)

export function NoteEnvProvider({ value, children }: { value: NoteEnv; children: ReactNode }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useNoteEnv(): NoteEnv { return useContext(Ctx) }
export function useMarks(): Marks { return useContext(Ctx).marks }

export const isTicked = (m: Marks, id: string, initial: boolean) => m.ticks[id] ?? initial

/** What in a note still waits on the operator: unticked items, unanswered choices, paste blocks not yet copied. */
export interface Open { toTick: number; ticked: number; toAnswer: number; answered: number; toCopy: number; copies: number }

export function openOf(note: Note, m: Marks): Open {
  const o: Open = { toTick: 0, ticked: 0, toAnswer: 0, answered: 0, toCopy: 0, copies: 0 }
  for (const { block: b } of allBlocks(note)) {
    if (b.type === 'check') for (const it of b.items) { if (isTicked(m, it.id, it.done)) o.ticked++; else o.toTick++ }
    if (b.type === 'choice') { if (m.answers[b.id] != null) o.answered++; else o.toAnswer++ }
    if (b.type === 'copy') { o.copies++; if (note.kind === 'paste' && !m.copied[b.id]) o.toCopy++ }
  }
  return o
}

/** Waits on the operator: something to tick, answer, or (a paste note) to copy. */
export const needsYou = (o: Open) => o.toTick + o.toAnswer + o.toCopy > 0
