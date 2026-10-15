import { Numbers } from './stats/Numbers'
import { SEARCH_GUIDE } from '../visions/guides'
import { PageGuide } from '../visions/parts'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Card } from '../../components/primitives/Card'
import { PageHeader } from '../../components/PageHeader'
import { fetchEverything, FETCH_LIMIT, type SearchAnswer } from './api'
import {
  applyClauses,
  buildFacets,
  buildResults,
  narrowingChain,
  popClause,
  toggleClause,
  type Clause,
  type FacetGroup,
} from './filter'
import {
  ChatHeading,
  ClauseLine,
  EntryRow,
  FacetRail,
  TurnRow,
} from './parts'
import { t, tn } from '../../i18n/scope/system'
import { isTypingElement, isTypingTarget } from '../../lib/typing'

/**
 * /search — the filter line.
 *
 * One word, then a chip per narrowing, and a counted rail beside the
 * results. Every facet carries its count, so the operator reads what a cut
 * would buy before making it, and the match count falls as clauses are
 * pushed. The page fetches the query once at the ceiling and does all the
 * narrowing in the browser.
 *
 * Keys: `/` the line · `⇥` the rail · `↑↓` walk · `1`–`9` toggle · `⌫` pop
 * the last clause · `↵` open · `⎋` back to the bare word. Every one of them
 * has a mouse path too.
 */

const KEYS = t('/ field · Tab rail · ↑↓ move · 1-9 pick · Backspace drop · Enter open · Esc clear')

export function SearchPage({ variant }: { variant?: string }): JSX.Element {
  const [params, setParams] = useSearchParams()
  const q = params.get('q')?.trim() ?? ''

  const [word, setWord] = useState(q)
  const [clauses, setClauses] = useState<Clause[]>([])

  const inputRef = useRef<HTMLInputElement>(null)
  const railEls = useRef(new Map<string, HTMLButtonElement>())
  const rowEls = useRef(new Map<string, HTMLAnchorElement>())

  useEffect(() => {
    document.title = q ? `${q} — ${t('the filter line')} — Slightly Parallel` : `${t('The filter line')} — Slightly Parallel`
  }, [q])
  useEffect(() => {
    setWord(q)
    setClauses([])
  }, [q])

  // The previous word's rows stay up while the next one is asked; a word
  // replaced by the next is dropped, and its answer ends nothing.
  const search = useQuery({
    queryKey: ['search', q],
    queryFn: ({ signal }) => fetchEverything(q, signal),
    enabled: !!q,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const data: SearchAnswer | null = q && !search.isError ? search.data ?? null : null
  const loading = !!q && search.isFetching && (search.isPlaceholderData || !search.data)
  const error = q && search.isError ? 'The search failed. Try again.' : null

  const hits = useMemo(() => data?.hits ?? [], [data])
  const facets = useMemo(() => buildFacets(hits, clauses), [hits, clauses])
  const kept = useMemo(() => applyClauses(hits, clauses), [hits, clauses])
  const results = useMemo(() => buildResults(kept), [kept])
  const chain = useMemo(() => narrowingChain(hits, clauses), [hits, clauses])

  const railKeys = useMemo(
    () => facets.flatMap((f) => f.values.map((v) => `${f.group}:${v.value}`)),
    [facets],
  )
  const rowKeys = useMemo(() => results.rows.map((h) => `${h.kind}:${h.id}`), [results])

  const registerButton = useCallback((el: HTMLButtonElement | null, key: string) => {
    if (el) railEls.current.set(key, el)
    else railEls.current.delete(key)
  }, [])
  const registerRow = useCallback((el: HTMLAnchorElement | null, key: string) => {
    if (el) rowEls.current.set(key, el)
    else rowEls.current.delete(key)
  }, [])

  const toggle = useCallback((clause: Clause) => {
    setClauses((cs) => toggleClause(cs, clause))
  }, [])

  /* ---- the keyboard. Every action here also has a button or a link. ---- */
  useEffect(() => {
    const focusRail = (i: number) => {
      const key = railKeys[Math.max(0, Math.min(i, railKeys.length - 1))]
      railEls.current.get(key)?.focus()
    }
    const focusRow = (i: number) => {
      const key = rowKeys[Math.max(0, Math.min(i, rowKeys.length - 1))]
      rowEls.current.get(key)?.focus()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const el = document.activeElement as HTMLElement | null
      const inInput = el === inputRef.current
      // Typing anywhere else (the topbar search, the Quick note) keeps every key.
      if (!inInput && (isTypingTarget(e) || isTypingElement(el))) return

      if (e.key === 'Escape') {
        setClauses([])
        el?.blur()
        return
      }
      if (e.key === '/' && !inInput) {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
        return
      }
      if (e.key === 'Tab' && !e.shiftKey && (inInput || el === document.body) && railKeys.length) {
        e.preventDefault()
        focusRail(0)
        return
      }
      if (inInput) {
        if (e.key === 'Backspace' && inputRef.current?.value === '' && clauses.length) {
          e.preventDefault()
          setClauses(popClause)
        }
        return
      }
      if (e.key === 'Backspace') {
        e.preventDefault()
        setClauses(popClause)
        return
      }

      const facetKey = el?.getAttribute('data-facet') ?? null
      if (/^[1-9]$/.test(e.key)) {
        const group = (facetKey?.split(':')[0] as FacetGroup | undefined) ?? facets[0]?.group
        const facet = facets.find((f) => f.group === group)
        const value = facet?.values[Number(e.key) - 1]
        if (facet && value) {
          e.preventDefault()
          toggle({ group: facet.group, value: value.value })
        }
        return
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        const step = e.key === 'ArrowDown' ? 1 : -1
        if (facetKey) {
          e.preventDefault()
          focusRail(railKeys.indexOf(facetKey) + step)
          return
        }
        const rowKey = rowKeys.find((k) => rowEls.current.get(k) === el)
        if (rowKey) {
          e.preventDefault()
          focusRow(rowKeys.indexOf(rowKey) + step)
        } else if (rowKeys.length) {
          e.preventDefault()
          focusRow(0)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [railKeys, rowKeys, facets, clauses.length, toggle])

  const onLineKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      setParams(word.trim() ? { q: word.trim() } : {})
    }
  }

  const matches = kept.length
  const capped = data != null && data.total > hits.length
  const turns = results.rows.length - results.entries.length
  // With no clause the chain is one number, which the title already says;
  // the line spends itself on what the word is in instead.
  const countLine = !q
    ? t('no word yet')
    : clauses.length > 0
      ? `${chain.join(' → ')} ${tn(matches, 'match', 'matches')}`
      : t('{rows} rows · {entries} entries · {turns} turns in {chats} chats', { rows: matches, entries: results.entries.length, turns, chats: results.chats.length })

  return (
    <div className="flex flex-col gap-16 min-w-0">
      <PageHeader
        variant="tool"
        title={t('Search')}
        sub={q ? (loading ? t('searching…') : tn(matches, '{n} match', '{n} matches')) : variant}
      />
      <PageGuide id="search" guide={SEARCH_GUIDE} examples={0} />

      <ClauseLine
        word={word}
        clauses={clauses}
        inputRef={inputRef}
        onWord={setWord}
        onSubmit={() => setParams(word.trim() ? { q: word.trim() } : {})}
        onDrop={toggle}
        onKeyDown={onLineKey}
      />

      <div className="flex flex-wrap items-baseline justify-between gap-8 text-11 text-tertiary">
        <span className="font-mono tabular">
          {countLine}
          {capped ? ` · ${t('the first {n} of {total}', { n: FETCH_LIMIT, total: data?.total ?? 0 })}` : ''}
        </span>
        <span className="font-mono">{KEYS}</span>
      </div>

      {error && (
        <Card padding="md" className="border-status-red">
          <p className="text-13 text-status-red">{error}</p>
        </Card>
      )}

      {!q && (
        <>
          <p className="text-13 text-secondary max-w-reading">
            {t('Type a word to search entries, map parts and chat turns.')}
          </p>
          <Numbers query="" />
        </>
      )}

      {q && data && hits.length === 0 && !loading && (
        <Card padding="lg">
          <p className="text-13 text-secondary">{t('No match for “{q}”.', { q })}</p>
        </Card>
      )}

      {q && hits.length > 0 && (
        <div className="grid grid-cols-1 gap-16 min-w-0 lg:grid-cols-[240px_minmax(0,1fr)]">
          <aside className="min-w-0">
            <FacetRail facets={facets} registerButton={registerButton} onToggle={toggle} />
          </aside>

          <div className="flex flex-col gap-16 min-w-0">
            {matches === 0 && (
              <Card padding="lg">
                <p className="text-13 text-secondary">
                  {t('No matches. Remove a filter to see more.')}
                </p>
              </Card>
            )}

            {results.entries.length > 0 && (
              <section className="flex flex-col gap-8 min-w-0">
                <h2 className="text-11 uppercase tracking-wide text-tertiary">
                  {t('Entries')} · {results.entries.length}
                </h2>
                <ul role="list" className="grid gap-8 min-w-0 xl:grid-cols-2">
                  {results.entries.map((h) => (
                    <li key={`${h.kind}:${h.id}`} className="min-w-0">
                      <EntryRow
                        hit={h}
                        word={q}
                        ref={(el) => registerRow(el, `${h.kind}:${h.id}`)}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {results.chats.length > 0 && (
              <section className="flex flex-col gap-8 min-w-0">
                <h2 className="text-11 uppercase tracking-wide text-tertiary">
                  {t('Chats')} · {results.chats.length} · {tn(results.rows.length - results.entries.length, '{n} turn', '{n} turns')}
                </h2>
                <ul role="list" className="flex flex-col gap-16 min-w-0">
                  {results.chats.map((chat) => (
                    <li key={chat.agentId} className="flex flex-col gap-4 min-w-0">
                      <ChatHeading chat={chat} word={q} />
                      <ul role="list" className="flex flex-col gap-4 min-w-0">
                        {chat.turns.map((t) => (
                          <li key={t.id} className="min-w-0">
                            <TurnRow
                              hit={t}
                              word={q}
                              ref={(el) => registerRow(el, `${t.kind}:${t.id}`)}
                            />
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>
      )}

      {q && matches > 0 && (
        <details className="flex flex-col gap-8 min-w-0">
          <summary className="cursor-pointer text-11 uppercase tracking-wide text-tertiary hover:text-primary">
            {t('The numbers for “{q}”', { q })}
          </summary>
          <div className="pt-16">
            <Numbers query={q} />
          </div>
        </details>
      )}
    </div>
  )
}