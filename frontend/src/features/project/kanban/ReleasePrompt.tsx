import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Newspaper, Plus, X } from 'lucide-react'

import { Confirm } from '../../../components/Confirm'
import { Button, IconButton, toast } from '../../../components/primitives'
import { Modal } from '../../../components/Modal'
import { OPERATOR_ACTOR } from '../types'
import { type TaskRow } from './model'
import { copyText, writeClipboard } from '../../../lib/useCopy'
import { LABEL } from '../../promptlib/taskstyle'
import {
  PARTS, PART_HINT, PART_LABEL, RELEASE_TYPES, ago, cancelRequest, createRequest, deletePreset, listRequests,
  loadPresets, readChoices, readFocusDraft, requestBody, requestPrompt, savePreset, writeChoices, writeFocusDraft,
  type Part, type Preset, type PresetStore, type ReleaseType, type StoryRequest,
} from './release'
import { t } from '../../../i18n/scope/project'

/**
 * The release button and its window.
 *
 * The window is the task window's sibling: the same frame, the same
 * labelled mono fields. Three parts, each with a strip of named presets
 * above its text; the type of note the piece becomes; "Copy prompt"
 * records the request and puts the prompt on the clipboard, ready to be
 * pasted to the agent. Earlier requests of the task sit at the foot, so a
 * lost prompt can be copied again and a stale one cancelled.
 */
export function ReleaseButton({
  task, size = 16, className = '', onOpen,
}: {
  task: TaskRow
  size?: number
  className?: string
  /** When given, the parent owns the window (a card re-renders under the
   *  board's polling; state that lives in it would close the window). */
  onOpen?: () => void
}) {
  const [open, setOpen] = useState(false)
  const reported = !!task.agent_done_by
  return (
    <>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); if (onOpen) onOpen(); else setOpen(true) }}
        aria-label={t('Press release')}
        title={reported ? t('Reported done. Ask the agent for a press release.') : t('Ask the agent for a press release')}
        className={`shrink-0 inline-flex items-center justify-center rounded-input transition-colors ${
          reported ? 'text-brand hover:bg-brand/12' : 'text-tertiary hover:text-primary hover:bg-hover'
        } ${className}`}
        style={{ width: size, height: size }}
      >
        <Newspaper size={Math.max(11, size - 4)} aria-hidden />
      </button>
      {open && !onOpen && createPortal(<ReleasePromptModal task={task} onClose={() => setOpen(false)} />, document.body)}
    </>
  )
}

type Texts = Record<Part, string>
type Picks = Partial<Record<Part, string>>

export function ReleasePromptModal({ task, onClose }: { task: TaskRow; onClose: () => void }) {
  const taskId = String(task.id ?? '')
  const [store, setStore] = useState<PresetStore | null>(null)
  const [type, setType] = useState<ReleaseType>('release')
  const [picks, setPicks] = useState<Picks>(() => readChoices())
  const [texts, setTexts] = useState<Texts>({ focus: readFocusDraft(taskId), brief: '', style: '' })
  const [requests, setRequests] = useState<StoryRequest[]>([])
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    loadPresets().then((s) => {
      if (cancelled) return
      setStore(s)
      // The remembered preset per part, or the first one, fills the text.
      setTexts((t) => {
        const next = { ...t }
        for (const part of PARTS) {
          if (part === 'focus' && next.focus.trim()) continue
          const list = s.parts[part] ?? []
          const chosen = list.find((p) => p.id === picks[part]) ?? (part === 'focus' ? undefined : list[0])
          if (chosen) next[part] = chosen.text
        }
        return next
      })
      setPicks((p) => {
        const next = { ...p }
        for (const part of PARTS) {
          const list = s.parts[part] ?? []
          if (!list.some((x) => x.id === next[part])) next[part] = part === 'focus' ? undefined : list[0]?.id
        }
        return next
      })
    }).catch(() => toast.error(t('Couldn\'t load the presets')))
    return () => { cancelled = true }
    // Seeds the texts once, when the presets first arrive; `picks` is the remembered one then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  // The task's requests, read again after each one this window sends.
  useEffect(() => {
    const stop = new AbortController()
    listRequests(taskId, stop.signal)
      .then((r) => { if (!stop.signal.aborted) setRequests(r) })
      .catch(() => { /* the list stays as it was; sending a request does not need it */ })
    return () => stop.abort()
  }, [taskId, tick])
  useEffect(() => { writeFocusDraft(taskId, texts.focus) }, [taskId, texts.focus])

  const setText = (part: Part, value: string) => setTexts((t) => ({ ...t, [part]: value }))
  const pick = (part: Part, p: Preset) => {
    setText(part, p.text)
    const next = { ...picks, [part]: p.id }
    setPicks(next)
    writeChoices(next)
  }
  const edited = (part: Part): boolean => {
    const chosen = store?.parts[part]?.find((p) => p.id === picks[part])
    return chosen ? chosen.text.trim() !== texts[part].trim() : texts[part].trim().length > 0
  }
  const refresh = async () => { try { setStore(await loadPresets()) } catch { /* shown already */ } }

  const send = async () => {
    if (!texts.brief.trim()) { toast.error(t('The brief is empty. Write what the agent should do.')); return }
    setBusy(true)
    try {
      const d = await createRequest(taskId, requestBody(type, texts, picks, OPERATOR_ACTOR))
      // One toast says both: the request is recorded, and whether the prompt was copied.
      const ok = await writeClipboard(d.prompt)
      setTick((t) => t + 1)
      // The focus was written for this request; the next one starts clean.
      setText('focus', '')
      // A second "Copy prompt" would record a second request; "copy again" on the request does not.
      if (ok) toast.success(t('Prompt copied. Paste it to the agent. Request {id}', { id: d.request.id }))
      else toast.warning(t('Request {id} recorded, but the browser blocked the clipboard. Use "copy again" on the request.', { id: d.request.id }))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal tone="window" labelledBy="release-modal-title" onClose={onClose} isolateKeys
      width="w-full" maxWidth={820} padding="p-14" className="flex flex-col gap-10">
        <div className="flex items-baseline gap-8 min-w-0">
          <span id="release-modal-title" className="text-16 font-semibold text-primary inline-flex items-center gap-6">
            <Newspaper size={15} className="text-brand" aria-hidden /> {t('Press release')}
          </span>
          <span className="text-11 text-tertiary font-mono">{taskId}</span>
          <span className="text-12 text-secondary truncate">{task.title}</span>
          <IconButton label={t('Close')} onClick={onClose} className="ml-auto text-16">×</IconButton>
        </div>

        <div className="flex items-center gap-8 flex-wrap">
          <span className={LABEL}>{t('lands as')}</span>
          <div role="radiogroup" aria-label={t('Note type')} className="flex items-center gap-4">
            {RELEASE_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                role="radio"
                aria-checked={type === t}
                onClick={() => setType(t)}
                className={`px-8 h-20 rounded-input border text-11 font-mono ${type === t ? 'border-brand text-brand bg-brand/8' : 'border-border-default text-tertiary hover:text-primary'}`}
              >
                {t}
              </button>
            ))}
          </div>
          <span className="text-11 text-tertiary">{t('The release is saved as a note on the task, on the Storyboard, with the agent\'s screenshots')}</span>
        </div>

        {PARTS.map((part) => (
          <PartField
            key={part}
            part={part}
            presets={store?.parts[part] ?? []}
            builtin={store?.builtin ?? []}
            picked={picks[part]}
            edited={edited(part)}
            value={texts[part]}
            onChange={(v) => setText(part, v)}
            onPick={(p) => pick(part, p)}
            onSaved={async (p) => { await refresh(); pick(part, p) }}
            onDeleted={async (id) => {
              await refresh()
              if (picks[part] === id) { const next = { ...picks, [part]: undefined }; setPicks(next); writeChoices(next) }
            }}
          />
        ))}

        <div className="flex items-center gap-8 border-t border-border-subtle pt-8 text-11 font-mono flex-wrap">
          <RequestsLine requests={requests} onChanged={() => setTick((t) => t + 1)} />
          <span className="ml-auto text-tertiary">{t('The agent posts one piece per request, under the request id')}</span>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void send()}
            disabled={busy || !store}
            iconLeft={<Check size={12} aria-hidden />}
          >
            {t('Copy prompt')}
          </Button>
        </div>
    </Modal>
  )
}

const ROWS: Record<Part, number> = { focus: 4, brief: 9, style: 9 }

function PartField({
  part, presets, builtin, picked, edited, value, onChange, onPick, onSaved, onDeleted,
}: {
  part: Part
  presets: Preset[]
  builtin: string[]
  picked?: string
  edited: boolean
  value: string
  onChange: (v: string) => void
  onPick: (p: Preset) => void
  onSaved: (p: Preset) => void
  onDeleted: (id: string) => void
}) {
  const [naming, setNaming] = useState<null | { name: string }>(null)
  const current = useMemo(() => presets.find((p) => p.id === picked), [presets, picked])

  const saveNew = async () => {
    const name = naming?.name.trim()
    if (!name) return
    try {
      const d = await savePreset(part, name, value)
      setNaming(null)
      onSaved(d.preset)
      toast.success(t('Saved "{name}"', { name }))
    } catch (e) { toast.error((e as Error).message) }
  }
  const updateCurrent = async () => {
    if (!current) return
    try {
      const d = await savePreset(part, current.name, value, current.id)
      onSaved(d.preset)
      toast.success(t('"{name}" updated', { name: current.name }))
    } catch (e) { toast.error((e as Error).message) }
  }
  const [removing, setRemoving] = useState<Preset | null>(null)
  const [busy, setBusy] = useState(false)
  const remove = async (p: Preset) => {
    setBusy(true)
    try { await deletePreset(p.id); onDeleted(p.id) } catch (e) { toast.error((e as Error).message) }
    setBusy(false)
    setRemoving(null)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-8 min-w-0">
        <span className={`${LABEL} shrink-0`}>{PART_LABEL[part]}</span>
        <span className="text-11 text-tertiary truncate">{PART_HINT[part]}</span>
        {edited && current && (
          <Button variant="link" size="bare" onClick={() => void updateCurrent()} className="ml-auto shrink-0 text-11 font-mono" title={t('Write the text back into "{name}"', { name: current.name })}>
            {t('update "{name}"', { name: current.name })}
          </Button>
        )}
      </div>
      {removing && (
        <Confirm text={t('Remove the preset "{name}".', { name: removing.name })} action={t('Remove')} busy={busy}
          onYes={() => void remove(removing)} onNo={() => setRemoving(null)} />
      )}
      <div className="flex items-center gap-4 overflow-x-auto pb-2" role="group" aria-label={`${PART_LABEL[part]} presets`}>
        {presets.map((p) => {
          const on = p.id === picked
          const locked = builtin.includes(p.id)
          return (
            <span key={p.id} className="group/preset inline-flex items-center shrink-0">
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onPick(p)}
                title={p.text.slice(0, 200)}
                className={`h-20 px-8 rounded-input border text-11 font-mono whitespace-nowrap ${
                  on ? 'border-brand text-brand bg-brand/8' : 'border-border-default text-tertiary hover:text-primary'
                }`}
              >
                {p.name}{on && edited ? ' ·' : ''}
              </button>
              {!locked && (
                <button
                  type="button"
                  onClick={() => setRemoving(p)}
                  aria-label={`Remove preset ${p.name}`}
                  className="w-14 h-20 inline-flex items-center justify-center text-tertiary opacity-0 group-hover/preset:opacity-100 hover:text-error"
                >
                  <X size={10} aria-hidden />
                </button>
              )}
            </span>
          )
        })}
        {naming ? (
          <form className="inline-flex items-center gap-4 shrink-0" onSubmit={(e) => { e.preventDefault(); void saveNew() }}>
            <input
              autoFocus
              value={naming.name}
              onChange={(e) => setNaming({ name: e.target.value })}
              onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setNaming(null) } }}
              placeholder={t('name…')}
              maxLength={60}
              aria-label={`Name for the new ${PART_LABEL[part]} preset`}
              className="h-20 w-[140px] px-6 rounded-input border border-brand bg-elevated text-11 font-mono text-primary"
            />
            <Button type="submit" variant="link" size="bare" className="text-11 font-mono">{t('save')}</Button>
            <Button variant="text" size="bare" onClick={() => setNaming(null)}>{t('cancel')}</Button>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setNaming({ name: '' })}
            disabled={!value.trim()}
            title={t('Keep the text below as a named preset')}
            className="h-20 px-6 rounded-input border border-dashed border-border-default text-11 font-mono text-tertiary hover:text-primary inline-flex items-center gap-4 shrink-0 disabled:opacity-40"
          >
            <Plus size={10} aria-hidden /> {t('save as')}
          </button>
        )}
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={ROWS[part]}
        aria-label={PART_LABEL[part]}
        placeholder={part === 'focus' ? t('Notes about this task, or what to focus on.') : ''}
        className="bg-elevated text-primary border border-border-default rounded-input px-8 py-4 text-12 leading-relaxed w-full resize-y font-mono"
      />
    </div>
  )
}

function RequestsLine({ requests, onChanged }: { requests: StoryRequest[]; onChanged: () => void }) {
  if (requests.length === 0) return <span className="text-tertiary">{t('No request on this task yet')}</span>
  const open = requests.filter((r) => r.status === 'open')
  const done = requests.filter((r) => r.status === 'fulfilled')
  const recopy = async (r: StoryRequest) => {
    try { await copyText(await requestPrompt(r.id), t('Prompt {id} copied again', { id: r.id })) } catch (e) { toast.error((e as Error).message) }
  }
  const cancel = async (r: StoryRequest) => {
    try { await cancelRequest(r.id); onChanged() } catch (e) { toast.error((e as Error).message) }
  }
  return (
    <span className="inline-flex items-center gap-8 flex-wrap">
      {open.map((r) => (
        <span key={r.id} className="inline-flex items-center gap-6">
          <span className="text-status-amber">{r.id} {t('· waiting ·')} {ago(r.created_at)}</span>
          <Button variant="link" size="bare" onClick={() => void recopy(r)}>{t('copy again')}</Button>
          <Button variant="danger-text" size="bare" onClick={() => void cancel(r)}>{t('cancel')}</Button>
        </span>
      ))}
      {done.length > 0 && <span className="text-tertiary">{done.length} {t('written')}</span>}
    </span>
  )
}
