/**
 * Round 2 — hiding the columns. The list (left) and the feed (middle) can
 * each be hidden; with the feed hidden, the right column becomes tiles.
 * The state sits in the address (`?hide=list`, `?hide=feed`,
 * `?hide=list,feed`) so a view can be linked and reloaded. Keys: l the
 * list, f the feed (as f flips the feed on Publish; `[` is the app's
 * sidebar) — by the key's place too, so the Russian layout's Д and А work
 * the same; j / k the next and the previous note (with the feed shown);
 * Escape closes the task a tile opened on H's shelves.
 */

import { useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BookOpen, LayoutGrid, PanelLeft } from 'lucide-react'

import { isTypingTarget, letter } from '../../../../lib/typing'
import { t } from '../../../../i18n/scope/notes'

export type Col = 'list' | 'feed'

export function useColumns() {
  const [params, setParams] = useSearchParams()
  const hidden = new Set((params.get('hide') ?? '').split(',').filter((c): c is Col => c === 'list' || c === 'feed'))
  const write = useCallback((next: Set<Col>) => {
    setParams((p) => {
      const q = new URLSearchParams(p)
      if (next.size) q.set('hide', [...next].sort().join(','))
      else q.delete('hide')
      return q
    }, { replace: true })
  }, [setParams])
  const key = [...hidden].sort().join()
  const toggle = useCallback((c: Col) => {
    const next = new Set(key ? (key.split(',') as Col[]) : [])
    if (next.has(c)) next.delete(c)
    else next.add(c)
    write(next)
  }, [key, write])
  const set = useCallback((cols: Col[]) => write(new Set(cols)), [write])
  return { list: !hidden.has('list'), feed: !hidden.has('feed'), toggle, set }
}

export interface PageKeys {
  list?: () => void
  feed?: () => void
  next?: () => void
  prev?: () => void
  escape?: () => void
}

/** The page's own keys, away from any field that takes text. */
export function usePageKeys(keys: PageKeys) {
  const live = useRef(keys)
  useEffect(() => { live.current = keys })
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e)) return
      const k = live.current
      const run = (f?: () => void) => { if (f) { e.preventDefault(); f() } }
      if (e.key === 'Escape') { run(k.escape); return }
      const l = letter(e)
      if (l === 'l') run(k.list)
      else if (l === 'f') run(k.feed)
      else if (l === 'j') run(k.next)
      else if (l === 'k') run(k.prev)
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [])
}

/** A key as drawn in a hint. */
export function Key({ children }: { children: string }) {
  return <kbd className="inline-flex items-center justify-center min-w-[16px] h-16 px-4 rounded-input border border-border-default bg-elevated text-10 font-mono text-secondary">{children}</kbd>
}

/** The keys of the page in one line. */
export function KeysLine() {
  return (
    <span className="inline-flex items-center gap-6 flex-wrap text-11 text-tertiary max-sm:hidden">
      <Key>l</Key>{t('list')}<Key>f</Key>{t('feed / tiles')}<Key>j</Key><Key>k</Key>{t('next, previous note')}
    </span>
  )
}

/**
 * The switch the Entry points page uses for its layouts, here with two
 * independent buttons: the list, and the feed (off = tiles).
 */
export function ColumnSwitch({ list, feed, onList, onFeed }: { list: boolean; feed: boolean; onList: () => void; onFeed: () => void }) {
  const items: Array<[boolean, () => void, typeof PanelLeft, string, string]> = [
    [list, onList, PanelLeft, list ? t('Hide the list') : t('Show the list'), 'l'],
    [feed, onFeed, feed ? BookOpen : LayoutGrid, feed ? t('Hide the feed: tiles') : t('Show the feed'), 'f'],
  ]
  return (
    <div role="group" aria-label={t('Columns')} className="inline-flex items-center gap-2 rounded-pill border border-border-subtle bg-elevated p-2 shrink-0">
      {items.map(([on, click, Icon, label, key]) => (
        <button key={key} type="button" aria-pressed={on} aria-label={label} title={`${label} · ${key}`} onClick={click}
          className={`h-24 w-[28px] inline-flex items-center justify-center rounded-pill transition-colors ${on ? 'bg-brand text-on-brand' : 'text-tertiary hover:text-primary hover:bg-hover'}`}>
          <Icon size={13} aria-hidden />
        </button>
      ))}
    </div>
  )
}
