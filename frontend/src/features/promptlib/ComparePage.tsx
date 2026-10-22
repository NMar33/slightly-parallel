import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink } from 'lucide-react'

import { Input } from '../../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { formatStamp } from '../../utils/dateUtils'
import {
  chatHref, useLibraryWrites, usePrompt, usageWords,
  type Detail, type Send, type Version,
} from './data'
import { TextPane } from './page'
import { VersionDiff, factWords } from './runs'
import { LABEL, PillGroup, RatingPills } from './taskstyle'
import { ChatsWorkbench } from '../chats/ChatsWorkbench'
import { t } from '../../i18n/scope/system'

/**
 * Prompt page v05 — compare, judged per version.
 *
 * What the operator asked for, exactly: no marks, no meta row. A version is
 * its text, Copy and Rewrite, and directly under them the four assessments
 * drawn as the task window's value rows — Task · Regression · Intervention ·
 * Score — then Tags. The judgement belongs to the wording, not to a send:
 * he rewrites, sends, judges, and a wording is rarely sent twice unchanged.
 * The sends stay underneath as evidence — the facts of each, and the door
 * into its conversation — but they are not the thing being rated.
 */
export function PromptCompare() {
  const { id = '' } = useParams<{ id: string }>()
  const detail = usePrompt(id)
  useEffect(() => {
    document.title = detail.data ? `${detail.data.prompt.title} — ${t('compare')} — Slightly Parallel` : `${t('Prompt')} — Slightly Parallel`
  }, [detail.data])

  if (detail.isLoading) return <LoadingSkeleton variant="card" count={3} />
  if (detail.isError || !detail.data) return <ErrorBanner title={t('Could not read that prompt')} hideDismiss />
  return <Compare detail={detail.data} />
}


function Head({ detail }: { detail: Detail }) {
  const { prompt, metrics: m, versions } = detail
  const { update } = useLibraryWrites(prompt.id)
  const [title, setTitle] = useState(prompt.title)
  useEffect(() => setTitle(prompt.title), [prompt.title])
  return (
    <header className="flex flex-col gap-6">
      <Link to="/prompts" className="text-11 text-tertiary hover:text-brand inline-flex items-center gap-4 self-start">
        <ArrowLeft size={11} /> {t('Prompts')}
      </Link>
      <Input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        // A refused rename puts the name back; the write says why.
        onBlur={() => title.trim() && title !== prompt.title && update.mutate({ title }, { onError: () => setTitle(prompt.title) })}
        aria-label={t('Prompt name')}
        className="text-20 font-semibold tracking-tight"
      />
      <div className="flex items-baseline gap-12">
        <span className="text-11 text-tertiary tabular font-mono">{usageWords(m, versions.length).join(' · ')}</span>
        {m.uses > 0 && (
          <Link
            to={`/sessions#prompt=${prompt.id}`}
            className="text-11 font-mono text-brand hover:underline inline-flex items-center gap-4"
            title={t('Chats this prompt was sent in, any version. Each opens at the message.')}
          >
            {t('open chats')} <ExternalLink size={10} />
          </Link>
        )}
      </div>
    </header>
  )
}

/**
 * The prompt, compared and judged. On its own page with the head; inside the
 * table without it, and with the chats folded until asked for — the
 * workbench mounts only when unfolded, so a row that opens costs one
 * request, not a reader's worth.
 */
export function Compare({ detail, head = true, chats = 'open' }: { detail: Detail; head?: boolean; chats?: 'open' | 'collapsed' }) {
  const { versions } = detail
  const [chatsOpen, setChatsOpen] = useState(chats === 'open')
  const last = versions[versions.length - 1]?.n ?? 1
  const [a, setA] = useState<number>(Math.max(1, last - 1))
  const [b, setB] = useState<number>(last)
  const va = versions.find((v) => v.n === a) ?? versions[0]
  const vb = versions.find((v) => v.n === b) ?? versions[versions.length - 1]
  const single = versions.length < 2
  const opts: Array<[string, string]> = versions.map((v) => [String(v.n), `v${v.n}`])

  return (
    <div className="flex flex-col gap-16 max-w-[1200px]">
      {head && <Head detail={detail} />}

      {single ? (
        <Column version={va} detail={detail} isCurrent />
      ) : (
        <>
          <div className="grid gap-16" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>
            <PillGroup label="A" value={String(va.n)} onChange={(v) => v && setA(Number(v))} options={opts} />
            <PillGroup label="B" value={String(vb.n)} onChange={(v) => v && setB(Number(v))} options={opts} />
            <Column version={va} detail={detail} isCurrent={va.n === last} />
            <Column version={vb} detail={detail} isCurrent={vb.n === last} />
          </div>
          <section className="flex flex-col gap-6 border-t border-border-subtle pt-12">
            <span className={LABEL}>{t('What changed, v{a} → v{b}', { a: va.n, b: vb.n })}</span>
            {vb.note && <p className="text-12 text-secondary italic">{vb.note}</p>}
            <VersionDiff before={va} after={vb} limit={60} />
          </section>
        </>
      )}
      {/* The evidence, on the page: every session this prompt was sent in,
          the reader opening on the send's turn, what each turn changed. */}
      {detail.metrics.uses > 0 && (
        <section className="flex flex-col gap-6 border-t border-border-subtle pt-12">
          <button type="button" onClick={() => setChatsOpen((v) => !v)} aria-expanded={chatsOpen}
            className={`${LABEL} inline-flex items-center gap-4 self-start hover:text-primary`}>
            {chatsOpen ? <ChevronDown size={11} aria-hidden /> : <ChevronRight size={11} aria-hidden />}
            {t('Where it was sent')} · {detail.metrics.uses}×
            {!chatsOpen && <span className="normal-case tracking-normal text-tertiary/70 ml-4">{t('click to see the chats it was sent in')}</span>}
          </button>
          {chatsOpen && <ChatsWorkbench fixedPrompt={detail.prompt.id} />}
        </section>
      )}
    </div>
  )
}

function Column({ version, detail, isCurrent }: { version: Version; detail: Detail; isCurrent: boolean }) {
  const { prompt, sends, scales } = detail
  const { update } = useLibraryWrites(prompt.id)
  const runs = useMemo(() => sends.filter((s) => s.version === version.n), [sends, version.n])
  return (
    <div className="flex flex-col gap-10 min-w-0">
      <div className="flex items-baseline gap-8">
        <span className="text-13 font-medium text-primary font-mono">v{version.n}</span>
        <span className="text-11 text-tertiary tabular font-mono">{version.at} · {t('{n} words', { n: version.words })}</span>
      </div>
      <TextPane promptId={prompt.id} version={version} isCurrent={isCurrent} dense />
      <RatingPills
        promptId={prompt.id}
        version={version}
        scales={scales}
        tags={prompt.tags}
        onTags={(tags) => update.mutate({ tags })}
      />
      <Sends runs={runs} />
    </div>
  )
}

/** The sends of this wording — evidence, not the thing being rated. */
function Sends({ runs }: { runs: Send[] }) {
  return (
    <div className="flex flex-col gap-2 border-t border-border-subtle pt-8">
      <span className={LABEL}>{t('Sent')} <span className="tabular">{runs.length}×</span></span>
      {runs.length === 0 && <p className="text-11 text-tertiary italic font-mono">{t('never sent in this wording')}</p>}
      {runs.map((s) => (
        <div key={`${s.session_id}-${s.turn}`} className="flex items-baseline gap-6 text-11 font-mono px-4 py-2">
          <span className="tabular text-primary shrink-0">{formatStamp(s.at)}</span>
          <span className="text-tertiary truncate tabular">{factWords(s.facts).join(' · ')}</span>
          <Link to={chatHref(s)} className="ml-auto text-tertiary hover:text-brand shrink-0 inline-flex items-center gap-4" title={t('Open the chat at this turn')}>
            {t('chat')} <ExternalLink size={10} />
          </Link>
        </div>
      ))}
    </div>
  )
}
