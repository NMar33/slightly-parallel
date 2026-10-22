import { ExampleSource } from '../example/example'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CopyButton } from '../../components/CopyButton'
import { Markdown } from '../../components/Markdown'
import { LABEL } from '../promptlib/taskstyle'
import { TypeChip } from '../architecture/ledgerParts'
import { GROUPS, groupOf, landedWords, type Landed, type Scan, type TouchedFile } from './data'
import { locale, t } from '../../i18n/scope/system'

export function Lines({ add, del }: { add: number; del: number }) {
  return (
    <span className="font-mono tabular-nums whitespace-nowrap">
      <span className="text-status-green">+{add.toLocaleString(locale())}</span>{' '}
      <span className="text-status-red">−{del.toLocaleString(locale())}</span>
    </span>
  )
}

/** The size of a change as a bar: green added, red deleted, on one scale. */
export function ChangeBar({ add, del, max, width = 120 }: { add: number; del: number; max: number; width?: number }) {
  const scale = (n: number) => (max > 0 ? Math.max(n > 0 ? 2 : 0, Math.round((Math.sqrt(n) / Math.sqrt(max)) * width)) : 0)
  return (
    <span className="inline-flex items-center h-6 rounded-pill overflow-hidden bg-hover" style={{ width }} aria-hidden>
      <span className="h-6 bg-status-green" style={{ width: scale(add) }} />
      <span className="h-6 bg-status-red" style={{ width: Math.min(scale(del), width - scale(add)) }} />
    </span>
  )
}

export function Who({ s, stacked = false }: { s: Scan; stacked?: boolean }) {
  return (
    <span className={stacked ? 'flex flex-col gap-2 min-w-0 items-start' : 'inline-flex items-center gap-6 min-w-0'}>
      <Link to={`/agent/${encodeURIComponent(s.row.agent_id)}`}
        className={`text-secondary hover:text-primary ${stacked ? 'break-words' : 'truncate'}`} title={t('Open the agent')}>
        {s.who}
      </Link>
      {s.who !== s.row.agent_id && (
        <CopyButton
          text={s.row.agent_id}
          title={t('Copy the agent id')}
          label={<>{s.row.agent_id}</>}
          copiedLabel={<>{s.row.agent_id}</>}
          size={9}
          icon={null}
          className="inline-flex flex-row-reverse items-center gap-3 h-16 px-4 rounded-input border border-border-subtle text-10 font-mono text-tertiary hover:text-primary shrink-0"
        />
      )}
    </span>
  )
}

function Dots({ n }: { n: number }) {
  return (
    <span role="img" className="inline-flex gap-2" aria-label={t('Importance {n} of 5', { n })}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={`w-4 h-4 rounded-pill ${i <= n ? 'bg-brand' : 'bg-hover'}`} />
      ))}
    </span>
  )
}

/**
 * A section that can be shut, with its own label as the summary line: the
 * reader still sees what is inside it without opening it.
 */
function Shut({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <details className="flex flex-col gap-4 min-w-0 group">
      <summary className="cursor-pointer list-none marker:content-none inline-flex items-center gap-6 select-none">
        <span aria-hidden className="text-10 font-mono text-tertiary group-open:rotate-90 transition-transform">▶</span>
        {label}
      </summary>
      <div className="pt-6">{children}</div>
    </details>
  )
}

function Touched({ files, ignored, limit = 6, fold = false }: { files: TouchedFile[]; ignored: number; limit?: number; fold?: boolean }) {
  const [all, setAll] = useState(false)
  if (files.length === 0) return null
  const shown = all ? files : files.slice(0, limit)
  const label = <span className={LABEL}>{t('Files')} <span className="normal-case tabular-nums">· {t('{n} important', { n: files.length })}{ignored > 0 ? ` · ${t('{n} not listed', { n: ignored })}` : ''}</span></span>
  const body = (
    <>
      <div className="flex flex-col divide-y divide-border-subtle border-t border-border-subtle">
        {shown.map((f) => (
          <div key={f.path} className="py-6 flex flex-col gap-2 min-w-0">
            <div className="flex items-baseline gap-8 min-w-0 text-11 font-mono">
              <span className="text-primary truncate flex-1 min-w-0" title={f.path}>{f.path}</span>
              <span className="text-tertiary shrink-0">{f.action ? t(f.action) : ''}</span>
              <span className="shrink-0"><Lines add={f.lines_add ?? 0} del={f.lines_del ?? 0} /></span>
              <span className="shrink-0"><Dots n={f.importance ?? 0} /></span>
              {f.test_coverage && (
                <span className={`shrink-0 ${f.test_coverage === 'untested' ? 'text-status-amber' : 'text-tertiary'}`}>{t(f.test_coverage)}</span>
              )}
              {f.security_surface && <span className="shrink-0 text-status-amber">{t('security')}</span>}
            </div>
            {f.why && <p className="text-12 text-secondary leading-relaxed">{f.why}</p>}
          </div>
        ))}
      </div>
      {files.length > limit && (
        <button type="button" onClick={() => setAll((v) => !v)} className="self-start text-11 font-mono text-brand hover:underline">
          {all ? t('Show fewer') : t('Show all {n}', { n: files.length })}
        </button>
      )}
    </>
  )
  if (fold) return <Shut label={label}>{body}</Shut>
  return (
    <section aria-label={t('Files')} className="flex flex-col gap-4 min-w-0">
      {label}
      {body}
    </section>
  )
}

const OP: Record<string, string> = { add: '+', change: '~', remove: '−' }
const OP_WORD: Record<string, string> = { add: t('added'), change: t('changed'), remove: t('removed') }

function LandedList({ landed, fold = false }: { landed: Landed[]; fold?: boolean }) {
  if (landed.length === 0) return null
  const groups = [...GROUPS.map(([g]) => g), 'other']
    .map((g) => ({ g, items: landed.filter((l) => groupOf(l.type) === g) }))
    .filter((x) => x.items.length > 0)
  const label = <span className={LABEL}>{t('Changes')} <span className="normal-case">· {landedWords(landed).join(' · ')}</span></span>
  const body = (
      <div className="flex flex-col gap-8">
        {groups.map(({ g, items }) => (
          <div key={g} className="flex flex-col gap-3 min-w-0">
            <span className="text-10 uppercase tracking-wide font-mono text-tertiary/70">{t(g)}</span>
            {items.map((l) => (
              <div key={l.id} className="flex items-baseline gap-6 min-w-0 text-12">
                <span role="img" className="w-10 shrink-0 font-mono text-tertiary" aria-label={OP_WORD[l.op] ?? l.op}>{OP[l.op] ?? '·'}</span>
                <TypeChip type={l.type} group={groupOf(l.type)} />
                <span className="text-primary shrink-0 max-w-[45%] truncate" title={l.name}>{l.name}</span>
                <span className="text-secondary truncate min-w-0" title={l.note}>{l.note}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
  )
  if (fold) return <Shut label={label}>{body}</Shut>
  return (
    <section aria-label={t('Changes')} className="flex flex-col gap-6 min-w-0">
      {label}
      {body}
    </section>
  )
}

export function LandedChips({ landed, limit = 4 }: { landed: Landed[]; limit?: number }) {
  const words = landedWords(landed)
  if (words.length === 0) return null
  return (
    <span className="inline-flex items-center gap-4 flex-wrap">
      {words.slice(0, limit).map((w) => (
        <span key={w} className="inline-flex items-center h-16 px-6 rounded-pill border border-border-subtle text-10 font-mono text-secondary whitespace-nowrap">{w}</span>
      ))}
      {words.length > limit && <span className="text-10 font-mono text-tertiary">+{words.length - limit}</span>}
    </span>
  )
}

function Deltas({ deltas, limit = 5 }: { deltas: string[]; limit?: number }) {
  const [all, setAll] = useState(false)
  if (deltas.length === 0) return null
  const shown = all ? deltas : deltas.slice(0, limit)
  return (
    <section aria-label={t('What changed')} className="flex flex-col gap-4 min-w-0">
      <span className={LABEL}>{t('What changed')}</span>
      <ul className="flex flex-col gap-3">
        {shown.map((d, i) => (
          <li key={i} className="text-12 text-secondary leading-relaxed pl-10 border-l border-border-subtle [&_p]:m-0 [&_code]:text-11">
            <Markdown text={d} />
          </li>
        ))}
      </ul>
      {deltas.length > limit && (
        <button type="button" onClick={() => setAll((v) => !v)} className="self-start text-11 font-mono text-brand hover:underline">
          {all ? t('Show fewer') : t('Show all {n}', { n: deltas.length })}
        </button>
      )}
    </section>
  )
}

function Proof({ text, open = false }: { text: string; open?: boolean }) {
  if (!text.trim()) return null
  return (
    <details open={open} className="min-w-0">
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>{t('Proof')}</summary>
      <div className="mt-4 text-12 text-secondary leading-relaxed [&_p]:my-2 [&_pre]:overflow-x-auto [&_code]:text-11">
        <Markdown text={text} />
      </div>
    </details>
  )
}

function Waiting({ s }: { s: Scan }) {
  if (s.waiting.length === 0) return null
  return (
    <p className="text-11 font-mono text-status-amber">
      {t('Not written yet: {what}.', { what: s.waiting.join(t(' and ')) })}
    </p>
  )
}

/** Everything a scan holds, in reading order. */
export function ScanBody({ s, proofOpen = false, fold = false }: { s: Scan; proofOpen?: boolean; fold?: boolean }) {
  return (
    <div className="flex flex-col gap-14 min-w-0">
      <ExampleSource kind="scan" project={s.row.project} agentId={s.row.agent_id} date={s.row.created_date} time={s.row.created_time} />
      {s.why && (
        <section aria-label={t('Why')} className="flex flex-col gap-4">
          <span className={LABEL}>{t('Why it changed')}</span>
          <div className="text-13 text-secondary leading-relaxed max-w-[760px] [&_p]:my-2"><Markdown text={s.why} /></div>
        </section>
      )}
      <Deltas deltas={s.deltas} />
      <Touched files={s.touched} ignored={s.ignored} fold={fold} />
      <LandedList landed={s.landed} fold={fold} />
      <Waiting s={s} />
      <Proof text={s.proof} open={proofOpen} />
    </div>
  )
}
