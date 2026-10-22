/**
 * The parts the filter line is drawn from: the marked word, the clause
 * line, the counted rail, and the two kinds of result row.
 *
 * Every one of them is a plain function of what it is given. The state —
 * the query, the clauses, the focused row — lives in the page.
 */

import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import { Chip } from '../../components/primitives/Chip'
import { hitHref, kindWord, type SearchHit } from '../../lib/searchHits'
import {
  GROUP_TITLE,
  markParts,
  type ChatBlock,
  type Clause,
  type Facet,
  type FacetGroup,
} from './filter'
import { t, tn } from '../../i18n/scope/system'

/** The text with every occurrence of the word marked. */
function Marked({ text, word }: { text: string; word: string }): JSX.Element {
  return (
    <>
      {markParts(text, word).map((part, i) =>
        part.hit ? (
          <mark key={i} className="rounded-input bg-brand-glow px-2 text-brand">
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  )
}

/**
 * What a kind is called here.
 *
 * `kindWord` gives a chat and a chat turn the same word, which two rows of
 * one rail cannot share, so a turn says what it is.
 */
function kindLabel(kind: string): string {
  if (kind === 'turn') return t('Chat turns')
  return t(kindWord(kind))
}

/** How a clause reads on its chip. */
function clauseLabel(clause: Clause): string {
  if (clause.group === 'kind') return t('kind: {v}', { v: kindLabel(clause.value).toLowerCase() })
  if (clause.group === 'where') return t('word in: {v}', { v: clause.value })
  if (clause.group === 'role') return t('said by: {v}', { v: clause.value === 'user' ? t('the operator') : t('the agent') })
  return `${clause.group}: ${clause.value}`
}

/** How a facet value reads in the rail. */
function facetLabel(group: FacetGroup, value: string): string {
  if (group === 'kind') return kindLabel(value)
  if (group === 'role') return value === 'user' ? t('The operator') : t('The agent')
  return value
}

/* ------------------------------------------------------------------ line */

export function ClauseLine({
  word,
  clauses,
  inputRef,
  onWord,
  onSubmit,
  onDrop,
  onKeyDown,
}: {
  word: string
  clauses: Clause[]
  inputRef: React.RefObject<HTMLInputElement>
  onWord: (w: string) => void
  onSubmit: () => void
  onDrop: (clause: Clause) => void
  onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void
}): JSX.Element {
  return (
    <form
      className="flex items-center gap-8 flex-wrap rounded-card border border-border-default focus-within:border-brand bg-surface px-12 py-12"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <span className="text-11 uppercase tracking-wide text-tertiary">{t('find')}</span>
      <input
        ref={inputRef}
        value={word}
        onChange={(e) => onWord(e.target.value)}
        onKeyDown={onKeyDown}
        aria-label={t('The word to find')}
        placeholder={t('a word')}
        className="min-w-[160px] flex-1 bg-transparent font-mono text-14 text-primary placeholder:text-tertiary outline-none"
      />
      {clauses.map((c) => (
        <Chip
          key={`${c.group}:${c.value}`}
          active
          onClick={() => onDrop(c)}
          onRemove={() => onDrop(c)}
          title={t('Remove this filter')}
        >
          {clauseLabel(c)}
        </Chip>
      ))}
    </form>
  )
}

/* ------------------------------------------------------------------ rail */

export function FacetRail({
  facets,
  registerButton,
  onToggle,
}: {
  facets: Facet[]
  registerButton: (el: HTMLButtonElement | null, key: string) => void
  onToggle: (clause: Clause) => void
}): JSX.Element {
  return (
    <nav aria-label={t('Filter the matches')} className="flex flex-col gap-16">
      {facets.map((facet) => (
        <section key={facet.group} data-group={facet.group} className="flex flex-col gap-4">
          <h2 className="flex items-baseline justify-between gap-8 text-11 uppercase tracking-wide text-tertiary">
            <span>{GROUP_TITLE[facet.group]}</span>
            <span className="font-mono tabular normal-case">{t('of {n}', { n: facet.base })}</span>
          </h2>
          <ul role="list" className="flex flex-col">
            {facet.values.map((v, i) => (
              <li key={v.value}>
                <button
                  ref={(el) => registerButton(el, `${facet.group}:${v.value}`)}
                  type="button"
                  aria-pressed={v.active}
                  data-facet={`${facet.group}:${v.value}`}
                  onClick={() => onToggle({ group: facet.group, value: v.value })}
                  className={`flex w-full items-baseline gap-8 rounded-input px-8 py-4 text-left text-12 transition-colors duration-fast ease-out focus:outline-none focus-visible:ring-2 focus-visible:ring-brand ${
                    v.active ? 'bg-brand-glow text-brand' : 'text-secondary hover:bg-hover hover:text-primary'
                  }`}
                >
                  <span className="w-12 shrink-0 font-mono text-11 text-tertiary tabular">
                    {i < 9 ? i + 1 : ''}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{facetLabel(facet.group, v.value)}</span>
                  <span className="font-mono text-11 tabular">{v.count}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  )
}

/* ----------------------------------------------------------------- rows */

const ROW_BASE =
  'block rounded-input border border-border-default bg-surface px-12 py-12 min-w-0 transition-colors duration-fast ease-out hover:bg-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand'

export const EntryRow = forwardRef<HTMLAnchorElement, { hit: SearchHit; word: string }>(
  function EntryRow({ hit, word }, ref) {
    return (
      <Link ref={ref} to={hitHref(hit)} className={ROW_BASE}>
        <div className="text-13 text-primary">
          <Marked text={hit.title || hit.id} word={word} />
        </div>
        {hit.where === 'text' && hit.snippet && (
          <div className="mt-4 text-12 text-secondary line-clamp-2">
            <Marked text={hit.snippet} word={word} />
          </div>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-8 text-11 text-tertiary">
          <span className="text-secondary">{kindLabel(hit.kind)}</span>
          <span className="font-mono">{hit.id}</span>
          {hit.map_kind && <span className="font-mono">{hit.map_kind}</span>}
          {hit.where_path && <span className="font-mono">{hit.where_path}</span>}
          {hit.date && <span className="font-mono tabular">{hit.date}</span>}
          {hit.project && <span className="font-mono">{hit.project}</span>}
          <span className="font-mono">{hit.where === 'title' ? 'in the title' : 'in the text'}</span>
          {(hit.count ?? 1) > 1 && <span className="font-mono tabular">{hit.count}×</span>}
        </div>
      </Link>
    )
  },
)

export const TurnRow = forwardRef<HTMLAnchorElement, { hit: SearchHit; word: string }>(
  function TurnRow({ hit, word }, ref) {
    return (
      <Link ref={ref} to={hitHref(hit)} className={`${ROW_BASE} border-l-2 border-l-border-strong`}>
        <div className="flex flex-wrap items-baseline gap-8 text-11 text-tertiary">
          <span className={hit.role === 'user' ? 'text-brand' : 'text-secondary'}>
            {hit.role === 'user' ? t('Operator') : t('Agent')}
          </span>
          <span className="font-mono tabular">{t('turn {n}', { n: hit.turn ?? '' })}</span>
          {hit.at && <span className="font-mono tabular">{hit.at}</span>}
          {hit.agent_id && <span className="font-mono">{hit.agent_id}</span>}
          {(hit.count ?? 1) > 1 && <span className="font-mono tabular">{hit.count}×</span>}
        </div>
        <div className="mt-4 text-12 text-secondary line-clamp-3">
          <Marked text={hit.snippet || hit.title} word={word} />
        </div>
      </Link>
    )
  },
)

export function ChatHeading({ chat, word }: { chat: ChatBlock; word: string }): JSX.Element {
  return (
    <div className="flex flex-wrap items-baseline gap-8 pt-4 text-12">
      <Link
        to={`/agent/${encodeURIComponent(chat.agentId)}#sec=chats`}
        className="text-primary hover:text-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-input"
      >
        <Marked text={chat.title} word={word} />
      </Link>
      <span className="font-mono text-11 text-tertiary">{chat.agentId}</span>
      {chat.date && <span className="font-mono text-11 text-tertiary tabular">{chat.date}</span>}
      <span className="font-mono text-11 text-tertiary tabular">
        {tn(chat.turns.length, '{n} turn', '{n} turns')} · {chat.occurrences}×
      </span>
    </div>
  )
}
