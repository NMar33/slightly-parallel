import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useLibraryWrites, type Rating, type Scales } from './data'
import { PillGroup } from '../../components/PillGroup'
import { LABEL } from '../../components/ui'
import { t } from '../../i18n/scope/system'

/**
 * The prompt page in the task window's language.
 *
 * The task modal is the one editing surface the operator uses every day, so
 * its idiom is the house style for editing anything: a label in small
 * uppercase mono above a mono input on an elevated ground; enumerated fields
 * as a radiogroup of pills, brand-coloured when chosen, click again to
 * clear; tags as one comma-separated field. The prompt page had grown its
 * own idiom for the same jobs — chip editors, key/value widgets, coloured
 * steps — and two idioms for one job is one too many. These are the task
 * window's parts, rebuilt here rather than imported, because that file is
 * four and a half thousand lines and exports none of them.
 */

// The shared label, and the shared value row, under the names this page's
// importers already use.
export { LABEL } from '../../components/ui'
export { PillGroup } from '../../components/PillGroup'
export const FIELD =
  'bg-elevated text-primary border border-border-default rounded-input px-8 py-4 text-12 font-mono'

// ---------------------------------------------------------------------------
// The assessment of a run, as pill groups; and as chips when not editing
// ---------------------------------------------------------------------------

/**
 * The outcome scale's words. The stored steps keep their first names
 * (below · average · better · one-shot — the API and the ledger hold them);
 * what a person reads is failed · partly · done · one-shot, each with what
 * it means.
 */
const OUTCOME: Record<string, [string, string]> = {
  below: [t('failed'), t("It didn't do what should be done")],
  average: [t('partly'), t('It was done partly: it required a lot of attention or corrections')],
  better: [t('done'), t('It just did what it should do')],
  'one-shot': [t('one-shot'), t('The king of prompts: it lets you do a task in one prompt')],
}

/** The word a step of a scale shows; the outcome scale has words of its own. */
export function stepWord(scale: string, step: string): string {
  return scale === 'task_success' ? OUTCOME[step]?.[0] ?? t(step) : t(step)
}

/** What an outcome step means, for its tooltip; '' for the other scales. */
export function stepHint(scale: string, step: string): string {
  return scale === 'task_success' ? OUTCOME[step]?.[1] ?? '' : ''
}

const HINTS: Record<string, string> = {
  task_success: t('Lets you assess the quality of the prompt'),
  regression: t('Whether anything that worked before stopped working'),
  intervention: t('How much you had to step in during the run'),
}

/** The judgement as the task card would show its value chips: small, mono, tinted only when it matters. */
export function RunChips({ rating }: { rating: Rating | null }) {
  if (!rating) return <span className="text-10 font-mono text-tertiary">{t('unrated')}</span>
  const good = (s: string) => s === 'one-shot' || s === 'better' || s === 'none'
  const bad = (s: string) => s === 'below' || s === 'serious' || s === 'lot'
  const chip = (text: string, s: string) => (
    <span
      key={text}
      className={`px-4 py-1 rounded-input ${
        good(s) ? 'bg-status-green/16 text-status-green'
        : bad(s) ? 'bg-status-red/16 text-status-red'
        : 'bg-elevated text-tertiary'
      }`}
    >
      {text}
    </span>
  )
  return (
    <span className="inline-flex items-center gap-4 text-10 font-mono">
      {rating.task_success && chip(stepWord('task_success', rating.task_success), rating.task_success)}
      {rating.regression && chip(`${t('reg')} ${t(rating.regression)}`, rating.regression)}
      {rating.intervention && chip(`${t('int')} ${t(rating.intervention)}`, rating.intervention)}
      {rating.score != null && <span className="px-4 py-1 rounded-input bg-brand/16 text-brand">{rating.score}/10</span>}
    </span>
  )
}

// ---------------------------------------------------------------------------
// The judgement of a version — the task modal's value rows, verbatim
// ---------------------------------------------------------------------------

/**
 * Under a version's text: Outcome · Regression · Intervention · Score as the
 * same pill rows the task window uses for Impact · Effort · Tokens ·
 * Novelty, then Tags. One judgement per wording, which is how the operator
 * works: rewrite, send, judge. Nothing pops up and nothing submits — a pill
 * saves on click and clears on a second.
 */
export function RatingPills({
  promptId, version, scales, tags, onTags,
}: {
  promptId: string
  version: { n: number; rating?: Rating | null }
  scales: Scales
  tags: string
  onTags: (v: string) => void
}) {
  const { rateVersion } = useLibraryWrites(promptId)
  const r = version.rating
  const set = (fields: Partial<Record<keyof Rating, unknown>>) =>
    rateVersion.mutate(
      { n: version.n, ...fields },
      { onError: (e: Error) => toast.error(e.message) },
    )
  const scoreOpts: Array<[string, string]> = Array.from(
    { length: scales.score[1] - scales.score[0] + 1 },
    (_, i) => [String(i + scales.score[0]), String(i + scales.score[0])],
  )
  return (
    <div className="flex flex-col gap-6">
      <PillGroup labelWidth={92} label={t('Outcome')} hint={HINTS.task_success} value={r?.task_success ?? ''} onChange={(v) => set({ task_success: v || null })} options={scales.task_success.map((s) => [s, stepWord('task_success', s), stepHint('task_success', s)])} />
      <PillGroup labelWidth={92} label={t('Regression')} hint={HINTS.regression} value={r?.regression ?? ''} onChange={(v) => set({ regression: v || null })} options={scales.regression.map((s) => [s, t(s)])} />
      <PillGroup labelWidth={92} label={t('Intervention')} hint={HINTS.intervention} value={r?.intervention ?? ''} onChange={(v) => set({ intervention: v || null })} options={scales.intervention.map((s) => [s, t(s)])} />
      <PillGroup labelWidth={92} label={t('Score')} value={r?.score != null ? String(r.score) : ''} onChange={(v) => set({ score: v ? Number(v) : null })} options={scoreOpts} />
      <div className="flex items-center gap-6">
        <span className={`${LABEL} w-[92px] shrink-0`}>{t('Tags')}</span>
        <TagsField value={tags} onCommit={onTags} />
      </div>
    </div>
  )
}

function TagsField({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const shown = (value ?? '').split(/[\s,]+/).filter(Boolean).join(', ')
  const [draft, setDraft] = useState(shown)
  useEffect(() => setDraft(shown), [shown])
  return (
    <input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => draft !== shown && onCommit(draft.split(/[\s,]+/).filter(Boolean).join(' '))}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      placeholder={t('comma,separated')}
      aria-label={t('Tags')}
      className={`${FIELD} h-24 py-0 min-w-[220px]`}
    />
  )
}
