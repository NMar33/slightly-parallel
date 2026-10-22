import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Star, Trash2 } from 'lucide-react'

import { Confirm } from '../../../components/Confirm'
import { useAgentNames } from '../../../lib/useAgentNames'
import { writeClipboard } from '../../../lib/useCopy'
import { Markdown } from '../../../components/Markdown'
import { Button, toast } from '../../../components/primitives'
import { formatStamp } from '../../../utils/dateUtils'
import { fail, getJson, postJson } from '../../../lib/getJson'
import { useModalA11y } from '../useModalA11y'
import {
  EVIDENCE_PROMPTS_KEY, useEvidencePrompts,
  type EvidencePrompt as Prompt, type EvidencePromptStore as PromptStore,
} from './boardData'
import { LABEL } from '../../promptlib/taskstyle'
import {
  ChangeItem, FilesItem, ItemCard, MissingFiles, summarise,
  type EvidenceItem, type WorkFile,
} from './evidenceItems'
import { t } from '../../../i18n/scope/project'

/**
 * Evidence — what the agent showed for this task, and the instructions
 * it was given. The main idea of the whole loop: the proof is read HERE,
 * in the task window, rendered properly — markdown for text, thumbnails
 * with a lightbox for screenshots, a table for the files it touched and a
 * grouped list for what landed (evidenceItems.tsx).
 *
 * Wears the same clothes as the window's other collapsible lines
 * (details/summary, hairline top border) — one language, five sections.
 *
 * The prompt half: which named instruction this task hands to a
 * reporting agent. Prompts are shared and named — edit the text, save it
 * under a name, pick a default; the names sit above the field as
 * scrollable chips because different workflows want different proof.
 * The per-task choice (`evidence_prompt`) is modal state — it saves with
 * the task's Save button like every other field.
 */

/** GET /api/tasks/{id}/evidence (routers/evidence.py `evidence_list`). */
type EvidenceAnswer = {
  task_id: string
  evidence: EvidenceItem[]
  /** Git's account of the task's work (taskwork.task_work). */
  work: { files: WorkFile[]; commits: number; add: number; del: number; sessions: number } | null
  /** Committed files with large changes that no item claims. */
  missing: WorkFile[]
}

export function EvidencePanel({
  taskId,
  promptId,
  onPickPrompt,
}: {
  taskId: string
  /** The task's chosen prompt id ('' = the default prompt). */
  promptId: string
  onPickPrompt: (id: string) => void
}) {
  const nameOf = useAgentNames()
  const qc = useQueryClient()
  // The count belongs on the summary line, so it is read at once, not on opening.
  const evidenceKey = ['tasks', 'evidence', taskId]
  const evidence = useQuery({
    queryKey: evidenceKey,
    queryFn: ({ signal }) => getJson<EvidenceAnswer>(`/api/tasks/${encodeURIComponent(taskId)}/evidence`, signal),
  })
  const items: EvidenceItem[] | null = evidence.data ? (Array.isArray(evidence.data.evidence) ? evidence.data.evidence : [])
    : evidence.isError ? [] : null
  /** Files the task's turns touched that no evidence claims. */
  const missing: WorkFile[] = Array.isArray(evidence.data?.missing) ? evidence.data.missing : []
  /** What is about to be destroyed, asked inline (components/Confirm). */
  const [asking, setAsking] = useState<{ text: string; action: string; run: () => Promise<void> } | null>(null)
  const [busy, setBusy] = useState(false)
  const confirmRow = asking && (
    <Confirm
      text={asking.text}
      action={asking.action}
      busy={busy}
      onNo={() => setAsking(null)}
      onYes={() => {
        setBusy(true)
        void asking.run().finally(() => { setBusy(false); setAsking(null) })
      }}
    />
  )
  // The prompt store is the shared query (kanban/boardData) — the same
  // one the board's copy buttons read, so a save here reaches them too.
  // Fetched only once the section is opened, like the old lazy load.
  const [promptsWanted, setPromptsWanted] = useState(false)
  const { data: store = null } = useEvidencePrompts(promptsWanted)
  const [text, setText] = useState('')
  const [saveName, setSaveName] = useState('')
  const [err, setErr] = useState<string | null>(null)
  /** The open screenshot, by id — so ← → can walk the others. */
  const [lightbox, setLightbox] = useState<string | null>(null)

  // The editor's text primes once, when the store first answers — later
  // refetches must not overwrite what the operator is typing.
  const primed = useRef(false)
  useEffect(() => {
    if (!store || primed.current) return
    primed.current = true
    const first = store.prompts.find((p) => p.id === (promptId || store.default_id)) ?? store.prompts[0]
    setText(first?.text ?? '')
  }, [store, promptId])

  /** Every write answers with the whole new store: show it at once, and
   *  invalidate so every other reader of the key refetches too. */
  const storeChanged = (d: PromptStore) => {
    qc.setQueryData(EVIDENCE_PROMPTS_KEY, d)
    void qc.invalidateQueries({ queryKey: EVIDENCE_PROMPTS_KEY })
  }

  const activeId = promptId || store?.default_id || 'default'
  const active = store?.prompts.find((p) => p.id === activeId)
  const dirty = !!active && text.trim() !== active.text.trim()

  const pick = (p: Prompt) => {
    onPickPrompt(p.id === store?.default_id ? '' : p.id)
    setText(p.text)
  }

  const savePrompt = async (asNew: boolean) => {
    setErr(null)
    const name = asNew ? saveName.trim() : active?.name ?? ''
    if (!name || !text.trim()) { setErr('A prompt needs a name and a text'); return }
    if (!asNew && activeId === 'default') { setErr('The built-in prompt cannot be changed. Save under a new name.'); return }
    let d: PromptStore & { saved?: string }
    try {
      d = await postJson('/api/evidence-prompts', asNew ? { name, text: text.trim() } : { id: activeId, name, text: text.trim() })
    } catch (e) { setErr((e as Error).message); return }
    storeChanged(d)
    setSaveName('')
    if (asNew && d?.saved) onPickPrompt(d.saved)
  }

  const makeDefault = async () => {
    if (!active) return
    const d = await postJson<PromptStore>('/api/evidence-prompts', { id: active.id, name: active.name, text: active.text, make_default: true }).catch((e) => { fail(e); return null })
    if (d) storeChanged(d)
  }

  const removePrompt = (p: Prompt) =>
    setAsking({ text: t('Delete the prompt “{name}”.', { name: p.name }), action: t('Delete'), run: () => reallyRemovePrompt(p) })

  const reallyRemovePrompt = async (p: Prompt) => {
    const d = await postJson<PromptStore>(`/api/evidence-prompts/${encodeURIComponent(p.id)}/delete`, {}).catch((e) => { fail(e); return null })
    if (d) {
      storeChanged(d)
      if (activeId === p.id) { onPickPrompt(''); const def = d.prompts.find((x: Prompt) => x.id === d.default_id); setText(def?.text ?? '') }
    }
  }

  const n = items?.length ?? 0
  const all = items ?? []
  const images = all.filter((it) => it.kind === 'image' && it.url)
  const files = all.filter((it) => it.kind === 'files')
  const changed = all.filter((it) => it.kind === 'change')
  // Anything that is not a screenshot, a file list or a change list reads
  // as a note, so a kind added later still shows up instead of vanishing.
  const texts = all.filter((it) => !['image', 'files', 'change'].includes(it.kind))
  const headline = summarise(all)

  // The lightbox is a gallery: ← → walk the screenshots, Esc closes.
  const shotIndex = images.findIndex((it) => it.id === lightbox)
  const shot = shotIndex >= 0 ? images[shotIndex] : null
  const step = (d: number) => {
    if (images.length === 0) return
    const next = images[(shotIndex + d + images.length) % images.length]
    if (next) setLightbox(next.id)
  }
  /** The image itself onto the clipboard; the link when the browser refuses. */
  const copyShot = async (it: EvidenceItem) => {
    try {
      const res = await fetch(it.url ?? '')
      const blob = await res.blob()
      await navigator.clipboard.write([new ClipboardItem({ [blob.type || 'image/png']: blob })])
      toast.success(t('Screenshot copied'))
    } catch {
      const href = new URL(it.url ?? '', window.location.origin).href
      if (await writeClipboard(href)) toast.success(t('Link copied. This browser cannot copy images.'))
      else toast.error(t('Could not copy the screenshot'))
    }
  }

  /** Drop one item: the row, and the file behind a screenshot. */
  const removeItem = (it: EvidenceItem) => {
    const what = it.title || (it.kind === 'image' ? t('this screenshot') : t('this note'))
    setAsking({ text: t('Remove “{what}” and its file.', { what }), action: t('Remove'), run: () => reallyRemoveItem(it) })
  }

  const reallyRemoveItem = async (it: EvidenceItem) => {
    try {
      await postJson(`/api/tasks/evidence/${encodeURIComponent(it.id)}/delete`, {})
    } catch (e) { fail(e); return }
    const rest = (items ?? []).filter((x) => x.id !== it.id)
    qc.setQueryData<EvidenceAnswer>(evidenceKey, (d) => (d ? { ...d, evidence: rest } : d))
    void qc.invalidateQueries({ queryKey: evidenceKey })
    if (lightbox === it.id) {
      // Stay in the gallery when there is more to see; the neighbour that
      // takes this one's place is the one already under the cursor.
      const nextShots = rest.filter((x) => x.kind === 'image' && x.url)
      const fallback = nextShots[Math.min(shotIndex, nextShots.length - 1)]
      setLightbox(fallback?.id ?? null)
    }
    toast.success(t('Removed'))
  }

  return (
    <details
      className="border-t border-border-subtle pt-8"
      open={n > 0}
      onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) setPromptsWanted(true) }}
    >
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
        {t('Evidence')}{' '}
        <span className="text-tertiary/70">
          — {evidence.isError
            ? t('The evidence could not be read.')
            : n === 0
            ? t('Nothing posted by an agent yet.')
            : `${n} item${n === 1 ? '' : 's'} from ${[...new Set((items ?? []).map((i) => nameOf(i.agent_id)))].join(', ')}`}
        </span>
      </summary>

      <div className="mt-6 flex flex-col gap-10">
        {!shot && confirmRow}
        {/* ---- the proof ------------------------------------------------ */}
        {texts.length > 0 && (
          <div className="flex flex-col gap-6">
            {texts.map((it) => (
              <ItemCard key={it.id} item={it} onRemove={() => void removeItem(it)}>
                <div className="text-12 text-secondary leading-relaxed [&_p]:my-2 [&_pre]:overflow-x-auto">
                  <Markdown text={it.body} />
                </div>
              </ItemCard>
            ))}
          </div>
        )}
        {images.length > 0 && (
          <div className="flex gap-8 flex-wrap">
            {images.map((it) => (
              <figure key={it.id} className="m-0 flex flex-col gap-2" style={{ maxWidth: 260 }}>
                <button type="button" onClick={() => setLightbox(it.id)} title={t('Open full size')} className="rounded-input border border-border-subtle overflow-hidden bg-elevated">
                  <img src={it.url} alt={it.title || t('evidence')} className="block max-h-[140px] w-auto" />
                </button>
                <figcaption className="text-10 font-mono text-tertiary truncate">
                  {it.title || 'screenshot'} · <span title={it.agent_id}>{nameOf(it.agent_id)}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        )}

        {/* ---- what was touched, and what landed: under the proof, folded.
             The proof is what the operator asked for; this is the account
             that rides along. ------------------------------------------- */}
        {(files.length > 0 || changed.length > 0) && (
          <details className="flex flex-col gap-6">
            <summary className="text-10 uppercase tracking-wide font-mono text-tertiary cursor-pointer hover:text-brand">
              {t('Touched and done')} <span className="normal-case text-tertiary/70 tabular-nums">— {headline}</span>
            </summary>
            <div className="mt-6 flex flex-col gap-6">
              {files.map((it) => (
                <FilesItem key={it.id} item={it} onRemove={() => void removeItem(it)} />
              ))}
              {changed.map((it) => (
                <ChangeItem key={it.id} item={it} onRemove={() => void removeItem(it)} />
              ))}
              <MissingFiles missing={missing} />
            </div>
          </details>
        )}

        {/* ---- the instructions ----------------------------------------- */}
        {store && (
          <div className="flex flex-col gap-6">
            <div className="text-10 uppercase tracking-wide font-mono text-tertiary">
              {t('the instructions a reporting agent receives')}
            </div>
            <div className="flex gap-4 overflow-x-auto pb-2" role="tablist" aria-label={t('Saved evidence prompts')}>
              {store.prompts.map((p) => (
                <span key={p.id} className="inline-flex items-center shrink-0">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={p.id === activeId}
                    onClick={() => pick(p)}
                    title={p.text}
                    className={`h-20 px-8 rounded-pill border text-10 font-mono inline-flex items-center gap-4 max-w-[160px] ${
                      p.id === activeId
                        ? 'border-brand bg-brand-glow text-primary'
                        : 'border-border-subtle bg-elevated text-tertiary hover:text-primary'
                    }`}
                  >
                    {p.id === store.default_id && <Star size={9} aria-hidden className="text-brand shrink-0" />}
                    <span className="truncate">{p.name}</span>
                  </button>
                  {p.id !== 'default' && p.id === activeId && (
                    <Button variant="danger-text" size="bare" onClick={() => void removePrompt(p)} title={`Delete “${p.name}”`} className="ml-2">
                      <Trash2 size={10} aria-hidden />
                    </Button>
                  )}
                </span>
              ))}
            </div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              aria-label={t('Evidence prompt text')}
              className="bg-elevated text-primary border border-border-default rounded-input px-10 py-6 text-12 leading-relaxed font-mono"
            />
            <div className="flex items-center gap-8 flex-wrap text-10 font-mono">
              {dirty && activeId !== 'default' && (
                <button type="button" onClick={() => void savePrompt(false)} className="text-brand hover:underline">
                  {t('save “{name}”', { name: active?.name ?? '' })}
                </button>
              )}
              <input
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                placeholder={t('save as…')}
                aria-label={t('New prompt name')}
                className="bg-elevated text-primary border border-border-subtle rounded-input px-8 py-3 text-10 w-[140px]"
              />
              {saveName.trim() && (
                <button type="button" onClick={() => void savePrompt(true)} className="text-brand hover:underline">
                  {t('save new')}
                </button>
              )}
              {active && active.id !== store.default_id && (
                <Button variant="text" size="bare" onClick={() => void makeDefault()}>
                  {t('make default')}
                </Button>
              )}
              <span className="ml-auto text-tertiary">
                {t('this task uses:')} {active?.name ?? t('the default')}
              </span>
            </div>
            {err && <div className="text-10 font-mono" style={{ color: 'var(--status-red)' }}>{err}</div>}
          </div>
        )}
      </div>

      {shot && (
        <Lightbox
          shot={shot}
          index={shotIndex}
          count={images.length}
          nameOf={nameOf}
          confirm={confirmRow}
          onStep={step}
          onCopy={() => void copyShot(shot)}
          onRemove={() => void removeItem(shot)}
          onClose={() => setLightbox(null)}
        />
      )}
    </details>
  )
}

/** The screenshot viewer — its own component so the a11y hook (Escape,
 *  focus trap, focus back to the thumbnail) mounts and unmounts with it. */
function Lightbox({
  shot, index, count, nameOf, confirm, onStep, onCopy, onRemove, onClose,
}: {
  shot: EvidenceItem
  /** Where this shot sits in the gallery, and how many there are. */
  index: number
  count: number
  nameOf: (id: string) => string
  /** The inline destroy question, when one is being asked. */
  confirm: React.ReactNode
  onStep: (d: number) => void
  onCopy: () => void
  onRemove: () => void
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDivElement>(null)
  useModalA11y(dialogRef, onClose)
  // ← → walk the gallery; Escape belongs to the hook.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') { e.preventDefault(); onStep(-1) }
      if (e.key === 'ArrowRight') { e.preventDefault(); onStep(1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onStep])
  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={shot.title || t('Evidence image')}
      className="fixed inset-0 z-modal flex flex-col items-center justify-center gap-12 p-24"
      style={{ background: 'color-mix(in srgb, var(--bg-base) 96%, transparent)' }}
      onClick={onClose}
    >
      <img
        src={shot.url}
        alt={shot.title || t('evidence')}
        onClick={(e) => e.stopPropagation()}
        className="max-w-full max-h-[74vh] rounded-card border border-border-default shadow-lg"
      />
      {/* Everything you can do to the shot, in one bar under it. */}
      <div
        className="flex flex-col items-center gap-6 max-w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline gap-8 flex-wrap justify-center max-w-full">
          <span className="text-12 text-primary">{shot.title || 'screenshot'}</span>
          <span className="text-10 font-mono text-tertiary">
            <span title={shot.agent_id}>{nameOf(shot.agent_id)}</span> · {formatStamp(shot.created_at)}
          </span>
        </div>
        <div className="flex items-center gap-4 flex-wrap justify-center rounded-pill border border-border-subtle bg-surface px-6 py-4">
          {count > 1 && (
            <>
              <Ctl onClick={() => onStep(-1)} title={t('Previous (←)')} label={t('Previous screenshot')}>←</Ctl>
              <span className="text-10 font-mono text-tertiary tabular-nums px-4">
                {index + 1} / {count}
              </span>
              <Ctl onClick={() => onStep(1)} title={t('Next (→)')} label={t('Next screenshot')}>→</Ctl>
              <span className="w-1 h-16 mx-4" style={{ background: 'var(--border-subtle)' }} aria-hidden />
            </>
          )}
          <Ctl onClick={onCopy} title={t('Copy the image to the clipboard')}>{t('copy')}</Ctl>
          <Ctl onClick={() => window.open(shot.url, '_blank', 'noopener')} title={t('Open the file in a new tab')}>{t('open as file')}</Ctl>
          <Ctl onClick={onRemove} title={t('Delete this evidence item')} danger>{t('remove')}</Ctl>
          <span className="w-1 h-16 mx-4" style={{ background: 'var(--border-subtle)' }} aria-hidden />
          <Ctl onClick={onClose} title={t('Close (Esc)')}>{t('close')}</Ctl>
        </div>
        {confirm}
      </div>
    </div>
  )
}

/** One control in the viewer's bar — the same shape for every action. */
function Ctl({
  onClick, title, label, danger, children,
}: {
  onClick: () => void
  title: string
  /** Accessible name when the glyph is not a word (the arrows). */
  label?: string
  danger?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={label ?? undefined}
      className={`h-20 px-8 rounded-pill text-10 font-mono inline-flex items-center hover:bg-hover ${
        danger ? 'text-tertiary hover:text-error' : 'text-tertiary hover:text-primary'
      }`}
    >
      {children}
    </button>
  )
}
