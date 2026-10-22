import { readPref } from '../../lib/uiPrefs'
import { useState } from 'react'
import { Info, X } from 'lucide-react'
import { toast } from 'sonner'

import { CopyButton as SharedCopyButton } from '../../components/CopyButton'
import { Markdown } from '../../components/Markdown'
import { Button } from '../../components/primitives'
import { persistPref, removePref } from '../../lib/uiPrefs'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { useInterpret, useRemoveExamples, visionText, type Kept, type KeptKind, type Turn, type Version, type Vision } from './data'
import type { Guide } from './guides'
import { stamp, whoOf } from './time'
import { Segmented } from '../../components/Segmented'
import { t, tn } from '../../i18n/scope/shell'

export { stamp, whoOf }

/**
 * Parts every vision variant shares: the folded context, the versions of
 * the interpretation, editing, Copy. Editing follows the task window —
 * labelled mono fields on an elevated ground, and a note saying why the
 * wording changed. Variants arrange these; they do not redraw them.
 */

function Clipped({ text, limit, className }: { text: string; limit: number; className?: string }) {
  const [all, setAll] = useState(false)
  const long = text.length > limit
  return (
    <div className={className}>
      <div className="whitespace-pre-wrap break-words">{all || !long ? text : `${text.slice(0, limit).trimEnd()}…`}</div>
      {long && (
        <Button variant="link" size="bare" className="text-10 font-mono" onClick={() => setAll((v) => !v)}>
          {all ? t('less') : t('more')}
        </Button>
      )}
    </div>
  )
}

/** Markdown marks read as noise in a clipped agent reply; the words stay. */
function plain(text: string): string {
  return text.replace(/\*\*|__|`/g, '').replace(/^#{1,6}\s+/gm, '')
}

function TurnBlock({ turn, message }: { turn: Turn; message?: boolean }) {
  return (
    <div className={`flex flex-col gap-4 py-8 ${message ? 'border-l-2 border-brand pl-10' : 'pl-12'}`}>
      <div className="flex items-baseline gap-8">
        <span className={LABEL}>{t('turn {n}', { n: turn.n })}</span>
        <span className="text-10 font-mono text-tertiary">{stamp(turn.at)}</span>
        {message && <span className="text-10 font-mono text-brand">{t('the message')}</span>}
      </div>
      {turn.user && <Clipped text={turn.user} limit={message ? 2000 : 420} className="text-12 text-primary" />}
      {turn.agent && <Clipped text={plain(turn.agent)} limit={message ? 420 : 260} className="text-12 text-tertiary" />}
    </div>
  )
}

/** The turns before and after the message, folded until asked for. */
export function ContextFold({ kept, defaultOpen = false }: { kept: Kept; defaultOpen?: boolean }) {
  // An example, or a rule written from a problem posted by an agent, has no chat to show.
  if (!kept.turn && !kept.before.length && !kept.after.length) return null
  const count = t('{before} before · {after} after', { before: kept.before.length, after: kept.after.length })
  return (
    <details open={defaultOpen} className="group rounded-input border border-border-subtle bg-base">
      <summary className="cursor-pointer select-none list-none px-10 h-24 flex items-center gap-8 hover:bg-hover">
        <span className="text-tertiary text-10 transition-transform group-open:rotate-90">▶</span>
        <span className={LABEL}>{t('context')}</span>
        <span className="text-10 font-mono text-tertiary">{count}</span>
      </summary>
      <div className="px-10 pb-8 flex flex-col divide-y divide-border-subtle">
        {kept.before.map((turn) => <TurnBlock key={turn.n} turn={turn} />)}
        {kept.turn && <TurnBlock turn={kept.turn} message />}
        {kept.after.map((turn) => <TurnBlock key={turn.n} turn={turn} />)}
        {!kept.after.length && (
          <p className="py-8 pl-12 text-11 font-mono text-tertiary">{t('No messages after this one yet.')}</p>
        )}
      </div>
    </details>
  )
}

/** v1 v2 … — the current one last, chosen one in brand. */
export function VersionPills({
  versions, value, onChange,
}: {
  versions: Version[]
  value: number
  onChange: (n: number) => void
}) {
  if (versions.length < 2) return null
  return (
    <Segmented
      label={t('Version')}
      height={20}
      value={String(value)}
      onChange={(v) => onChange(Number(v))}
      options={versions.map((v) => [String(v.n), `v${v.n}`, `${whoOf(v)} · ${stamp(v.at)}${v.note ? ` · ${v.note}` : ''}`] as const)}
    />
  )
}

/** The interpretation as text, rendered. */
export function InterpretationText({ text }: { text: string }) {
  return <div className="text-13 text-primary leading-relaxed"><Markdown text={text} /></div>
}

/** Rewrite the interpretation: a new version, never an overwrite. */
export function InterpretationEditor({
  vision, onDone, kind = 'vision',
}: {
  vision: Vision
  onDone: () => void
  kind?: KeptKind
}) {
  const write = useInterpret(kind)
  const [text, setText] = useState(vision.l2)
  const [note, setNote] = useState('')
  const next = (vision.kept?.versions.length ?? 0) + 1
  const save = () =>
    write.mutate(
      { id: vision.row.id, text, note },
      {
        onSuccess: () => { toast.success(t('Saved as version {n}', { n: next })); onDone() },
        onError: (e) => toast.error(String((e as Error).message)),
      },
    )
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <label className={LABEL} htmlFor={`interp-${vision.row.id}`}>{t('interpretation')}</label>
        <textarea
          id={`interp-${vision.row.id}`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={Math.min(18, Math.max(6, text.split('\n').length + 2))}
          className={`${FIELD} font-sans text-13 leading-relaxed resize-y`}
        />
      </div>
      <div className="flex flex-col gap-3">
        <label className={LABEL} htmlFor={`note-${vision.row.id}`}>{t('why it changed')}</label>
        <input
          id={`note-${vision.row.id}`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={t('Optional')}
          className={FIELD}
        />
      </div>
      <div className="flex items-center gap-8">
        <Button variant="primary" size="sm" onClick={save} disabled={write.isPending || !text.trim() || text.trim() === vision.l2.trim()}>
          {t('Save as v{n}', { n: next })}
        </Button>
        <Button variant="ghost" size="sm" onClick={onDone}>{t('Cancel')}</Button>
      </div>
    </div>
  )
}

/** The chip an example wears in its meta line. */
export function ExampleChip() {
  return (
    <span className="inline-flex items-center h-20 px-6 rounded-pill border border-status-purple/40 bg-status-purple/10 text-status-purple">
      {t('Example')}
    </span>
  )
}

/** Text with #vision, #rule and #problem set in mono, as they are typed. */
function Tagged({ text }: { text: string }) {
  return (
    <>
      {text.split(/(#[a-z]+)/).map((part, i) =>
        part.startsWith('#') ? <code key={i} className="font-mono text-primary">{part}</code> : part)}
    </>
  )
}

// readPref answers null when storage cannot be read.
const readHidden = (key: string): boolean => readPref(key) === 'yes'

/**
 * The top of the visions, rules and problems pages: what the page shows and
 * how to add to it, then "How it works", closed until opened. While the page
 * still holds examples, a line says what they are, with Remove. × closes the
 * guide for good (a synced preference); "About this page" brings it back.
 */
export function PageGuide({ id, guide, examples }: { id: string; guide: Guide; examples: number }) {
  const remove = useRemoveExamples()
  const key = `sp-guide-${id}-hidden`
  const [hidden, setHidden] = useState(() => readHidden(key))
  if (hidden) {
    return (
      <Button variant="text" size="bare" className="self-start" onClick={() => { removePref(key); setHidden(false) }}
        iconLeft={<Info size={12} aria-hidden />}>
        {t('About this page')}
      </Button>
    )
  }
  return (
    <section aria-label={t('About this page')} className="relative rounded-card border border-border-subtle bg-surface pl-16 pr-48 py-12 flex flex-col gap-8">
      <button type="button" aria-label={t('Close')} title={t('Close')}
        onClick={() => { persistPref(key, 'yes'); setHidden(true) }}
        className="absolute top-[10px] right-[10px] p-4 rounded-input text-tertiary hover:text-primary hover:bg-hover">
        <X size={14} aria-hidden />
      </button>
      <div className="flex flex-col gap-2 text-13 text-primary leading-relaxed">
        {guide.intro.map((line) => <p key={line}><Tagged text={line} /></p>)}
      </div>
      <ul className="flex flex-col gap-2 text-12 text-secondary leading-relaxed">
        {guide.parts.map(([name, text]) => (
          <li key={name}><span className="text-primary font-medium">{name}:</span> {text}</li>
        ))}
      </ul>
      <details className="group">
        <summary className="cursor-pointer select-none list-none inline-flex items-center gap-6 text-12 text-brand hover:underline">
          <span className="text-10 transition-transform group-open:rotate-90" aria-hidden>▶</span>
          {t('How it works')}
        </summary>
        <div className="mt-8 flex flex-col gap-8 text-12 text-secondary leading-relaxed">
          <ol className="list-decimal pl-20 flex flex-col gap-2">
            {guide.steps.map((step) => <li key={step}><Tagged text={step} /></li>)}
          </ol>
          {guide.give && (
            <div className="flex flex-col gap-2">
              {guide.giveTitle && <p className="text-primary">{guide.giveTitle}</p>}
              <ul className="list-disc pl-20 flex flex-col gap-2">
                {guide.give.map(([name, text]) => (
                  <li key={text}>{name && <span className="text-primary font-medium">{name}: </span>}{text}</li>
                ))}
              </ul>
            </div>
          )}
          {guide.note && <p>{guide.note}</p>}
        </div>
      </details>
      {examples > 0 && (
        <div className="flex items-center gap-12 flex-wrap border-t border-border-subtle pt-8 text-12">
          <span className="inline-flex items-center h-20 px-6 rounded-pill border border-status-purple/40 bg-status-purple/10 text-11 text-status-purple">{t('Example')}</span>
          <span className="text-secondary">{t('Entries marked Example show how this page looks. They stay on this page.')}</span>
          <Button
            variant="danger-text"
            size="bare"
            className="ml-auto"
            disabled={remove.isPending}
            onClick={() => remove.mutate(undefined, {
              onSuccess: (d) => toast.success(tn(d.removed.length, 'Removed {n} example', 'Removed {n} examples')),
              onError: (e) => toast.error(String((e as Error).message)),
            })}
          >
            {t('Remove all examples')}
          </Button>
        </div>
      )}
    </section>
  )
}

/** Copy the interpretation and the words it came from. */
export function CopyButton({ vision, label = t('Copy') }: { vision: Vision; label?: string }) {
  return (
    <SharedCopyButton
      text={() => visionText(vision)}
      title={`${label}: ${vision.row.l1}`}
      label={<> {label}</>}
      copiedLabel={<> {label}</>}
      size={12}
      tick={false}
      onCopied={() => toast.success(t('Copied'))}
      className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand"
    />
  )
}
