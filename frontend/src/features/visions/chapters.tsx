import { useEffect, useState, type DragEvent } from 'react'
import { toast } from 'sonner'

import { fail } from '../../lib/getJson'
import { lineDiff } from '../prompts/diff'
import { LABEL } from '../promptlib/taskstyle'
import {
  dateOf, tagCounts, tagsOf,
  type KeptSet, type SetWrites, type Vision, type useSetTags,
} from './data'
import { DRAG_TYPE } from '../kept/tags'
import { monthLong, monthShort } from '../../lib/months'
import { t } from '../../i18n/scope/shell'

/**
 * What the visions, rules and problems pages share when they read a kind of
 * kept entry as chapters: how the entries are grouped, the contents list
 * that follows the reader, the drop of an entry onto a chapter, and the two
 * blocks every section draws — what a version changed, and the words the
 * entry came from. The pages arrange these; they do not redraw them.
 */

export type ChapterMode = 'tag' | 'project' | 'month' | 'set'

export interface Chapter {
  key: string
  title: string
  /** The tag a drop on this chapter adds (tag mode, not "No tag"). */
  tag?: string
  /** The set a drop on this chapter joins (set mode, not "Not in a set"). */
  setId?: string
  full: Vision[]
  refs: Array<{ v: Vision; home: string }>
}


export function monthOf(v: Vision): string {
  const d = dateOf(v.row)
  return Number.isNaN(d.getTime()) ? t('Undated') : `${monthLong(d.getMonth())} ${d.getFullYear()}`
}

export function shortDate(v: Vision): string {
  const d = dateOf(v.row)
  return Number.isNaN(d.getTime()) ? '' : `${d.getDate()} ${monthShort(d.getMonth())}`
}

/** Every word of the query somewhere in the headline, the text, the message or the tags. */
export function matches(v: Vision, q: string): boolean {
  if (!q) return true
  const hay = `${v.row.l1} ${v.l2} ${v.kept?.message ?? ''} ${v.row.tags ?? ''}`.toLowerCase()
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))
}

export function chaptersOf(shown: Vision[], mode: ChapterMode, sets: KeptSet[]): Chapter[] {
  if (mode === 'set') {
    // An entry in several sets is written out in the first and referenced in the rest.
    const byId = new Map(shown.map((v) => [v.row.id, v]))
    const home = new Map<string, string>()
    const out: Chapter[] = sets.map((s) => {
      const c: Chapter = { key: `set:${s.id}`, title: s.name, setId: s.id, full: [], refs: [] }
      for (const id of s.items) {
        const v = byId.get(id)
        if (!v) continue
        const first = home.get(id)
        if (first) c.refs.push({ v, home: first })
        else { c.full.push(v); home.set(id, s.name) }
      }
      return c
    })
    const loose = shown.filter((v) => !home.has(v.row.id))
    if (loose.length) out.push({ key: 'set:', title: t('Not in a set'), full: loose, refs: [] })
    return out
  }
  if (mode === 'tag') {
    const out: Chapter[] = tagCounts(shown).map(([t]) => ({
      key: `tag:${t}`,
      title: t,
      tag: t,
      full: shown.filter((v) => tagsOf(v.row)[0] === t),
      refs: shown
        .filter((v) => { const ts = tagsOf(v.row); return ts.includes(t) && ts[0] !== t })
        .map((v) => ({ v, home: tagsOf(v.row)[0]! })),
    }))
    const bare = shown.filter((v) => tagsOf(v.row).length === 0)
    if (bare.length) out.push({ key: 'tag:', title: t('No tag'), full: bare, refs: [] })
    return out
  }
  const keyOf = mode === 'project' ? (v: Vision) => v.row.project || t('No project') : monthOf
  const out: Chapter[] = []
  for (const v of shown) {
    const k = keyOf(v)
    const hit = out.find((c) => c.title === k)
    if (hit) hit.full.push(v)
    else out.push({ key: `${mode}:${k}`, title: k, full: [v], refs: [] })
  }
  if (mode === 'project') out.sort((a, b) => b.full.length - a.full.length || a.title.localeCompare(b.title))
  return out
}

export const members = (c: Chapter) => [...c.full, ...c.refs.map((r) => r.v)]

/** The colour of a task's status dot next to an entry that names the task. */
export const DOT: Record<string, string> = {
  done: 'bg-status-green',
  'done-archived': 'bg-status-green',
  review: 'bg-status-purple',
  doing: 'bg-brand',
  todo: 'bg-status-amber',
  next: 'bg-status-amber',
}

// The sets panel scrolls to `vision-<id>`; rules and problems keep the same anchor.
export const anchor = (id: string) => `vision-${id}`
export const jump = (id: string) => landOn(document.getElementById(anchor(id)))

/**
 * Scroll an entry or a chapter to the top, smoothly. Records read on the
 * way down (near.ts) make the sections above taller, so the smooth scroll
 * can land short: once the target stops moving it is brought to the top
 * again. The reader taking the wheel cancels that.
 */
export function landOn(el: HTMLElement | null): void {
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  let stop = false
  const cancel = () => { stop = true }
  const events = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const
  for (const e of events) window.addEventListener(e, cancel, { once: true, passive: true })
  const done = () => { for (const e of events) window.removeEventListener(e, cancel) }
  let last = Number.NaN
  let still = 0
  let frames = 0
  const settle = () => {
    if (stop) { done(); return }
    const top = el.getBoundingClientRect().top
    still = top === last ? still + 1 : 0
    last = top
    if (still >= 12) { el.scrollIntoView({ block: 'start' }); done(); return }
    if (++frames < 240) requestAnimationFrame(settle)
    else done()
  }
  requestAnimationFrame(settle)
}

/** The id of the section being read, so the contents list can follow it. */
export function useActiveSection(shown: Vision[], chapters: Chapter[], loading: boolean): string {
  const [active, setActive] = useState('')
  useEffect(() => {
    const els = shown.map((v) => document.getElementById(anchor(v.row.id))).filter(Boolean) as HTMLElement[]
    if (!els.length) return
    const seen = new Map<string, boolean>()
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) seen.set(e.target.id, e.isIntersecting)
      const first = els.find((el) => seen.get(el.id))
      if (first) setActive(first.id.slice('vision-'.length))
    }, { rootMargin: '-15% 0px -65% 0px' })
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [shown, chapters, loading])
  return active
}

/** A drop on a chapter: the entry joins the chapter's set, or takes its tag. */
export function dropOnChapter({
  entries, sets, writes, writeTags, onDone,
}: {
  entries: Vision[]
  sets: KeptSet[]
  writes: SetWrites
  writeTags: ReturnType<typeof useSetTags>
  onDone: () => void
}) {
  return (c: Chapter) => (e: DragEvent) => {
    e.preventDefault()
    onDone()
    const id = e.dataTransfer.getData(DRAG_TYPE) || e.dataTransfer.getData('text/plain')
    const v = entries.find((x) => x.row.id === id)
    if (!v) return
    if (c.setId) {
      const s = sets.find((x) => x.id === c.setId)
      if (!s) return
      if (s.items.includes(id)) { toast(t('Already in {name}', { name: s.name })); return }
      writes.update.mutate(
        { id: s.id, items: [...s.items, id] },
        { onSuccess: () => toast.success(t('Added to {name}', { name: s.name })), onError: fail },
      )
      return
    }
    if (!c.tag) return
    const tags = tagsOf(v.row)
    if (tags.includes(c.tag)) { toast(t('Already in {name}', { name: c.tag })); return }
    const tag = c.tag
    writeTags.mutate({ id, tags: [...tags, tag] }, { onSuccess: () => toast.success(t('Added to {name}', { name: tag })), onError: fail })
  }
}

/** The older version on screen, marked with what the current one changed. */
export function Changes({ from, to, a, b }: { from: string; to: string; a: number; b: number }) {
  const diff = lineDiff(from, to).filter((l) => l.text.trim() || l.type !== 'same')
  return (
    <div className="flex flex-col gap-6">
      <span className="text-11 font-mono text-tertiary">
        v{a} → v{b} · <span className="text-status-red">{t('removed')}</span> · <span className="text-status-green">{t('added')}</span>
      </span>
      <div className="flex flex-col gap-2 text-13 leading-relaxed">
        {diff.map((l, i) => (
          <div key={i}
            className={`whitespace-pre-wrap break-words px-6 rounded-input ${
              l.type === 'add' ? 'bg-status-green/12 text-primary'
                : l.type === 'del' ? 'bg-status-red/10 text-status-red line-through'
                  : 'text-tertiary'
            }`}>
            <span className="font-mono mr-6 select-none" aria-hidden>{l.type === 'add' ? '+' : l.type === 'del' ? '−' : ' '}</span>
            {l.text}
          </div>
        ))}
      </div>
    </div>
  )
}

/** The words the entry came from, verbatim: the operator's message, or the problem's. */
export function Words({ text, label = t('Your words') }: { text: string; label?: string }) {
  const [all, setAll] = useState(false)
  const limit = 360
  const long = text.length > limit
  return (
    <div className="rounded-input border border-border-subtle px-12 py-8 flex flex-col gap-4">
      <span className={LABEL}>{label}</span>
      <div className="text-12 text-secondary leading-relaxed whitespace-pre-wrap break-words">
        {all || !long ? text : `${text.slice(0, limit).trimEnd()}…`}
      </div>
      {long && (
        <button type="button" onClick={() => setAll((x) => !x)} className="self-start text-10 font-mono text-brand hover:underline">
          {all ? 'less' : 'more'}
        </button>
      )}
    </div>
  )
}
