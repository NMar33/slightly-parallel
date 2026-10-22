/**
 * Small pieces the board (../TasksKanban.tsx) and the task window
 * (TaskEditor.tsx) both draw.
 */

import { usePopover } from '../../../hooks/usePopover'
import { Info } from 'lucide-react'

import { toast } from '../../../components/primitives'
import { CopyButton as SharedCopyButton } from '../../../components/CopyButton'
import type { Turn } from '../../tasks/turns'

/**
 * Two steps with one title, written in the same minute by the same hand,
 * fold into one task on the server. The clash is named before anything is
 * posted; null when every title is its own.
 */
export function stepClash(title: string, steps: string[]): string | null {
  const seen = new Set<string>()
  for (const raw of [title, ...steps]) {
    const t = raw.trim().toLowerCase()
    if (!t) continue
    if (seen.has(t)) return raw.trim()
    seen.add(t)
  }
  return null
}

export { PillGroup } from '../../../components/PillGroup'
import { t } from '../../../i18n/scope/project'

export function ValueInfo() {
  const { open, setOpen, rootRef } = usePopover()
  return (
    <span ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        aria-label={t('Why impact and effort')}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="h-20 w-20 inline-flex items-center justify-center rounded-pill text-tertiary hover:text-primary hover:bg-hover transition-colors"
      >
        <Info size={12} aria-hidden />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={t('Impact and effort')}
          className="absolute left-0 bottom-full mb-4 z-40 w-[300px] rounded-card border border-border-default bg-surface shadow-lg p-12 text-12 text-secondary leading-relaxed flex flex-col gap-6"
        >
          <p><strong className="text-primary">{t('Impact')}</strong> {t('— how much this moves the product.')} <strong className="text-primary">{t('Effort')}</strong> {t('— how hard it is to build.')} <strong className="text-primary">{t('Tokens')}</strong> {t('— how much agent budget it uses (a task easy for you can still cost a lot: "make five variants").')} <strong className="text-primary">{t('Novelty')}</strong> {t('— routine, fresh, or a killer feature.')}</p>
          <p>{t('Priority sets the order. These describe the value.')}</p>
          <ul className="list-disc pl-16 flex flex-col gap-2">
            <li><span className="text-status-green">★</span> {t('high impact + S: do first (quick win)')}</li>
            <li>{t('high impact + L: plan it and split it')}</li>
            <li>{t('low impact + S: when time allows')}</li>
            <li>{t('low impact + L: low value')}</li>
            <li>{t('¤ high tokens: run when the budget allows')}</li>
            <li>{t('✦ killer feature')}</li>
          </ul>
          <p className="text-tertiary">{t('All optional. Click a selected pill to clear it. Show or hide axes in the window gear.')}</p>
        </div>
      )}
    </span>
  )
}

/**
 * The rounds already asked — newest first and dimmed, under the box where
 * the next one is written. Read-only: an earlier round is what was said at
 * the time, and the agent's answer to it is already in the chat log.
 */
export function TurnHistory({ turns }: { turns: Turn[] }) {
  if (turns.length === 0) return null
  return (
    <div className="flex flex-col gap-10 mt-2">
      <div className="border-t border-border-default" />
      {[...turns].reverse().map((turn) => (
        <div key={turn.n} className="flex flex-col gap-2 opacity-55">
          <span className="text-10 font-mono text-tertiary">
            {t('turn')} {turn.n}{turn.date ? ` · ${turn.date}${turn.time ? ` ${turn.time}` : ''}` : ''}
          </span>
          <div className="text-12 text-secondary leading-snug whitespace-pre-wrap max-h-[9rem] overflow-auto">
            {turn.text}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Copy-to-clipboard button with a 1.2s confirmation state. */
export function CopyButton({
  text, label, big,
}: {
  text: string
  label: string
  big?: boolean
}) {
  return (
    <SharedCopyButton
      text={text}
      title={t('Copy: {what}', { what: label })}
      onFailed={() => toast.error(t('Could not copy: {what}', { what: label }), {
        description: t('The browser blocked the clipboard.'),
      })}
      className={`shrink-0 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover transition-colors ${
        big ? 'h-20 w-20' : 'h-16 w-16'
      }`}
    />
  )
}
