import { useEffect, useRef, useState } from 'react'
import { AgentName } from '../components/AgentName'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useHashState } from '../hooks/useHashState'
import { persistPref, readPref } from '../lib/uiPrefs'
import { entryText } from '../lib/entryText'

import { lensApi, qk, type FilePathRecord, type LensRow, type SessionTurn } from '../lib/api'
import { CopyButton } from '../components/CopyButton'
import { Modal } from '../components/Modal'
import { Badge } from '../components/primitives'
import { LoadingSkeleton, ErrorBanner } from '../components/states'
import type { LensConfig } from './config'
import { Markdown } from '../components/Markdown'
import { toBadgeTone } from './badgeTone'
import { t } from '../i18n/scope/shell'

/**
 * Detail view for a selected entry: metadata header, then the entry's text
 * under the names its lens gives it (a decision's Why and Alternatives, a
 * scan's Deltas and Proof — lib/entryText).
 *
 * Three presentations:
 * - drawer   — right-hand side panel; the list stays visible (variant set).
 * - reading  — centered overlay, wider measure, larger type (variant set).
 * - embedded — plain block filling its parent; used by lens LAYOUTS that
 *              dock the detail in a fixed pane (split / console / focus).
 */
export function LensDrawer({
  lens,
  id,
  presentation = 'drawer',
  onClose,
  header = true,
}: {
  lens: LensConfig
  id: string
  presentation?: 'drawer' | 'reading' | 'embedded'
  onClose: () => void
  /** Hosts that draw their own title bar (the checkpoint popup) hide ours. */
  header?: boolean
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: qk.lensDetail(lens.base, id),
    queryFn: ({ signal }) => lensApi.detail(lens.base, id, signal),
  })

  // Focus management: move focus in on open, restore on close, Esc closes.
  // Embedded panes are persistent surfaces — they must not steal focus from
  // the list on every selection change.
  // The latest onClose, read at the key press: a host that passes a new
  // function each render must not move focus back and forth each render.
  const closeRef = useRef(onClose)
  useEffect(() => { closeRef.current = onClose }, [onClose])
  const embedded = presentation === 'embedded'
  useEffect(() => {
    // The reading presentation dialogs through <Modal>, which brings its
    // own Escape / focus handling.
    if (embedded || presentation === 'reading') return
    const previous = document.activeElement as HTMLElement | null
    panelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeRef.current()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [embedded, presentation])

  const row = data?.metadata
  const reading = presentation === 'reading'

  const body = (
    <aside
      ref={panelRef}
      tabIndex={-1}
      role={embedded ? 'region' : reading ? undefined : 'dialog'}
      aria-label={reading ? undefined : t('{lens} detail', { lens: lens.title })}
      className={
        reading
          ? 'outline-none'
          : embedded
            ? 'w-full h-full min-h-0 bg-surface rounded-card border border-border-subtle overflow-y-auto outline-none'
            : 'w-[420px] max-w-[90vw] shrink-0 border-l border-border-subtle bg-surface overflow-y-auto outline-none'
      }
    >
      {header && (
      <div className="sticky top-0 bg-surface border-b border-border-subtle px-16 py-12 flex items-center gap-8">
        <span className="text-11 font-mono text-tertiary truncate">{id}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('Close detail')}
          className="ml-auto h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover transition-colors duration-fast"
        >
          <X size={14} aria-hidden />
        </button>
      </div>
      )}

      <div className="px-16 py-16 flex flex-col gap-16">
        {isLoading && <LoadingSkeleton variant="text" count={4} />}
        {isError && (
          <ErrorBanner
            title={t('Could not load the detail')}
            onRetry={() => void refetch()}
            hideDismiss
          />
        )}

        {row && (() => {
          // Legacy rows (per-project overlays) carry their prose inline
          // rather than in a detail doc — surface it as the summary.
          const held = entryText(data)
          const summary = held.text || String(row.rationale ?? '') || ''
          return (
          <>
            <header className="flex flex-col gap-8">
              <h2
                className={`${reading ? 'text-20' : 'text-14'} font-semibold text-primary leading-snug`}
              >
                {lens.l1(row)}
              </h2>
              <div className="flex flex-wrap gap-4">
                {(lens.badges?.(row) ?? []).map((b, i) => (
                  <Badge key={`${b.label}-${i}`} tone={toBadgeTone(b.tone)}>
                    {b.label}
                  </Badge>
                ))}
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-12 gap-y-4 text-12">
                {metaPairs(row).map(([k, v]) => (
                  <MetaRow key={k} label={k} value={v} />
                ))}
              </dl>
            </header>

            {summary && (
              <Section title={held.parts.text.label}>
                <Markdown text={summary} />
              </Section>
            )}

            {data.paths && data.paths.length > 0 && (
              <PathsTable
                paths={data.paths}
                range={{
                  from: data.commit_from,
                  to: data.commit_to,
                  dirty: data.dirty,
                  status: data.git_status,
                  basis: data.range_basis,
                }}
              />
            )}

            {data.turns && data.turns.length > 0 ? (
              <ChatHistory turns={data.turns} />
            ) : (
              held.list.length > 0 && (
                <Section title={held.parts.list.label}>
                  <ul className="flex flex-col gap-4 list-disc pl-16">
                    {held.list.map((item, i) => (
                      <li key={i} className="text-13 text-secondary leading-relaxed">
                        <Markdown text={item} />
                      </li>
                    ))}
                  </ul>
                </Section>
              )
            )}

            {held.long && (
              <Section title={held.parts.long.label}>
                <pre className="text-12 font-mono text-secondary bg-elevated rounded-input p-12 overflow-x-auto whitespace-pre-wrap">
                  {held.long}
                </pre>
              </Section>
            )}
          </>
          )
        })()}
      </div>
    </aside>
  )

  if (!reading) return body
  return (
    <Modal label={t('{lens} detail', { lens: lens.title })} onClose={onClose} width="w-[720px]" padding="p-0" top>
      {body}
    </Modal>
  )
}

/**
 * The file entry's per-path judgment: what git knew (action, ±lines) beside
 * what only the agent knew (importance, blast radius, coverage, why).
 */
function PathsTable({
  paths,
  range,
}: {
  paths: FilePathRecord[]
  range: { from?: string; to?: string; dirty?: boolean; status?: string; basis?: string }
}) {
  const short = (sha?: string) => (sha ? sha.slice(0, 8) : '')
  const basisNote =
    range.basis === 'head'
      ? t('since the last commit')
      : range.basis === 'empty-tree'
        ? t('repo has no commits — every file counted as new')
        : range.basis === 'previous-entry'
          ? t('since the previous entry')
          : ''
  return (
    <Section title={t('Paths')}>
      {range.status === 'not-a-repo' || range.status === 'no-path' ? (
        <p className="text-11 font-mono text-tertiary mb-6">
          git:{' '}
          {range.status === 'not-a-repo'
            ? t('registered path is not a repository')
            : t('project path not registered on Setup')}{' '}
          — {t("line counts are the agent's")}
        </p>
      ) : (
        (range.from || range.to) && (
          <p className="text-11 font-mono text-tertiary mb-6">
            git {short(range.from) || '—'} → {short(range.to) || t('working tree')}
            {basisNote ? ` · ${basisNote}` : ''}
            {range.dirty ? ` · ${t('uncommitted work included')}` : ''}
          </p>
        )
      )}
      <ul className="flex flex-col gap-6">
        {paths.map((p) => (
          <li
            key={p.path}
            className="rounded-input border border-border-subtle bg-base px-10 py-6"
          >
            <div className="flex items-baseline gap-8 flex-wrap">
              <span className="text-12 font-mono text-primary break-all">{p.path}</span>
              <span className="text-11 font-mono tabular text-tertiary">
                {p.action ?? 'modified'}
                {p.lines_add != null || p.lines_del != null
                  ? ` · +${p.lines_add ?? 0}/−${p.lines_del ?? 0}`
                  : ''}
              </span>
              <span className="ml-auto flex gap-4">
                {p.importance != null && (
                  <Badge tone={p.importance >= 4 ? 'warning' : 'neutral'}>
                    {t('imp {n}', { n: p.importance })}
                  </Badge>
                )}
                {p.blast_radius != null && <Badge tone="neutral">{t('blast {n}', { n: p.blast_radius })}</Badge>}
                {p.test_coverage && (
                  <Badge tone={p.test_coverage === 'untested' ? 'error' : 'neutral'}>
                    {p.test_coverage}
                  </Badge>
                )}
                {p.security_surface && <Badge tone="warning">{t('security')}</Badge>}
              </span>
            </div>
            {p.why && (
              <p className="text-12 text-secondary leading-relaxed mt-4">{p.why}</p>
            )}
          </li>
        ))}
      </ul>
    </Section>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-8">
      <h3 className="text-11 uppercase tracking-wider text-tertiary font-medium">
        {title}
      </h3>
      {children}
    </section>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-tertiary">{t(label)}</dt>
      <dd className="text-secondary font-mono truncate" title={value}>
        {/* An agent is shown by name; the id stays in the title. */}
        {label === 'agent' ? <AgentName id={value} /> : value}
      </dd>
    </>
  )
}

function metaPairs(row: LensRow): Array<[string, string]> {
  const out: Array<[string, string]> = []
  const push = (label: string, v: unknown) => {
    if (v != null && v !== '') out.push([label, String(v)])
  }
  push('project', row.project)
  push('agent', row.agent_id)
  push('date', row.created_date)
  push('time', row.created_time)
  return out
}

/* ---------------------------------------------------------------------------
 * ChatHistory — a chat renders its turns as a conversation: the user's
 * text clipped to a chosen preview length, the agent's reply folded behind
 * a spoiler, and a per-turn copy of the full exchange.
 * ------------------------------------------------------------------------- */

const PREVIEW_KEY = 'sp-chats-preview'
const PREVIEW_CHOICES = [100, 300, 0] as const // 0 = full text

function readPreview(): number {
  const raw = Number(readPref(PREVIEW_KEY))
  return (PREVIEW_CHOICES as readonly number[]).includes(raw) ? raw : 100
}

function clip(text: string, limit: number): string {
  if (limit === 0 || text.length <= limit) return text
  return text.slice(0, limit).trimEnd() + '…'
}

/**
 * A `turn=N` in the hash marks one turn — the one a prompt page sent you
 * to — and scrolls it into view. The prompt lives in the user half of that
 * turn, so that is what gets the ring: reworded sends are still that whole
 * message, so there is nothing to underline more finely.
 */
function ChatHistory({ turns }: { turns: SessionTurn[] }) {
  const [hash] = useHashState()
  const marked = Number(hash.turn ?? 0) || 0
  const [preview, setPreview] = useState(readPreview)
  const pick = (n: number) => {
    setPreview(n)
    try {
      persistPref(PREVIEW_KEY, String(n))
    } catch {
      /* private mode — the choice just won't persist */
    }
  }
  return (
    <section className="flex flex-col gap-8">
      <div className="flex items-center gap-8">
        <h3 className="text-11 uppercase tracking-wider text-tertiary font-medium">
          {t('Chat history')}
        </h3>
        <div
          role="radiogroup"
          aria-label={t('Preview length')}
          className="ml-auto inline-flex rounded-input border border-border-subtle overflow-hidden"
        >
          {PREVIEW_CHOICES.map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={preview === n}
              onClick={() => pick(n)}
              className={`px-8 h-24 text-11 transition-colors duration-fast ease-out ${
                preview === n
                  ? 'bg-hover text-primary'
                  : 'text-tertiary hover:text-secondary'
              }`}
            >
              {n === 0 ? t('full') : n}
            </button>
          ))}
        </div>
      </div>
      {/* Newest first — the recent exchange is what the operator came for. */}
      <ol className="flex flex-col gap-8">
        {[...turns].reverse().map((turn) => (
          <TurnItem key={turn.n} turn={turn} preview={preview} marked={turn.n === marked} />
        ))}
      </ol>
    </section>
  )
}

function TurnItem({
  turn, preview, marked = false,
}: { turn: SessionTurn; preview: number; marked?: boolean }) {
  const ref = useRef<HTMLLIElement | null>(null)
  useEffect(() => {
    if (marked) ref.current?.scrollIntoView({ block: 'center' })
  }, [marked])
  return (
    <li
      ref={ref}
      id={`turn-${turn.n}`}
      className={`rounded-input border px-12 py-8 ${
        marked
          ? 'border-brand bg-brand-glow ring-2 ring-brand/30'
          : 'border-border-subtle bg-base'
      }`}
    >
      <div className="flex items-start gap-8">
        <span className="text-10 font-mono tabular text-tertiary shrink-0 mt-2">
          {turn.at}
        </span>
        <div className="min-w-0 flex-1">
          {!turn.user ? (
            <p className="text-13 text-tertiary">{t('(no user message)')}</p>
          ) : preview === 0 ? (
            <Markdown text={turn.user} />
          ) : (
            <p className="text-13 text-primary leading-relaxed whitespace-pre-wrap">
              {clip(turn.user, preview)}
            </p>
          )}
        </div>
        <CopyButton
          text={`User: ${turn.user}\nAgent: ${turn.agent}`}
          title={t('Copy this exchange')}
          ariaLabel={t('Copy turn {n}', { n: turn.n })}
          size={12}
          className="shrink-0 h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover transition-colors duration-fast"
        />
      </div>
      {turn.agent && (
        <details className="mt-4 pl-[44px]">
          <summary className="text-11 text-tertiary cursor-pointer select-none hover:text-secondary">
            {t('agent reply')}
          </summary>
          <div className="mt-4">
            <Markdown text={turn.agent} />
          </div>
        </details>
      )}
    </li>
  )
}
