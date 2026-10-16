/*
 * The pieces the Setup page is built of: a numbered step, a detected
 * fact, a labelled field, a checkbox, a write's result, a confirm window,
 * a shell command to copy, and an adapter's trust badge.
 */
import { useState } from 'react'
import { CheckCircle2, CircleAlert, CircleX, Trash2, Unplug } from 'lucide-react'

import { CopyButton } from '../../components/CopyButton'
import { Modal } from '../../components/Modal'
import { Badge, Button, Input } from '../../components/primitives'
import { LABEL } from '../promptlib/taskstyle'
import { TOOL_KEYS, TOOL_NAMES, type IntegrateResult, type Integration, type ToolKey } from './data'
import { IMPORTABLE, ImportSessions } from '../capture/ImportSessions'
import { t, tn } from '../../i18n/scope/system'

/**
 * StepCard — one numbered step of the Setup journey. `done` renders a green
 * check next to the number; `undefined` means the step has no done-state.
 */
export function StepCard({
  n,
  title,
  done,
  badge,
  children,
}: {
  n: number
  title: string
  done?: boolean
  badge?: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <div className="flex items-center gap-12">
        <span
          aria-hidden
          className={`inline-flex items-center justify-center w-24 h-24 rounded-pill text-12 font-semibold shrink-0 ${
            done
              ? 'bg-status-green text-on-brand'
              : 'bg-elevated text-secondary border border-border-default'
          }`}
        >
          {done ? <CheckCircle2 size={14} /> : n}
        </span>
        <h2 className="text-16 font-semibold text-primary">{title}</h2>
        {badge && (
          <Badge tone={done ? 'done' : 'neutral'} className="ml-auto">
            {badge}
          </Badge>
        )}
      </div>
      {children}
    </section>
  )
}

/* ------------------------------------------------------------------------- */

export function DetectedRow({ label, value, warn }: { label: string; value: string; warn?: string }) {
  return (
    <div className="flex gap-12 min-w-0">
      <span className="text-tertiary w-[120px] shrink-0">{label}</span>
      <span className="truncate" title={value}>{value}</span>
      {warn && <span className="text-error shrink-0">{warn}</span>}
    </div>
  )
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <label className="flex flex-col gap-4 max-w-reading">
      <span className={LABEL}>
        {label}
      </span>
      {children}
      <span className="text-12 text-tertiary">{hint}</span>
    </label>
  )
}

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: React.ReactNode
}) {
  return (
    <label className="flex items-start gap-8 text-13 text-secondary cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.currentTarget.checked)}
        className="mt-2 accent-[var(--brand)]"
      />
      <span>{label}</span>
    </label>
  )
}

export function ResultPanel({
  result,
  title,
  success = false,
}: {
  result: IntegrateResult
  title: string
  success?: boolean
}) {
  return (
    <div
      className={`rounded-input border p-12 flex flex-col gap-8 ${
        success ? 'border-status-green' : 'border-border-default'
      }`}
      role="status"
    >
      <div className="text-13 font-medium text-primary">{title}</div>
      {result.results.map((r) => (
        <div key={r.file} className="flex flex-col gap-4">
          <div className="flex items-center gap-8 text-12 font-mono">
            <Badge tone={r.action === 'unchanged' ? 'neutral' : 'done'}>
              {r.action}
            </Badge>
            <span className="text-secondary truncate" title={r.file}>{r.file}</span>
          </div>
          <pre className="text-11 font-mono text-tertiary bg-elevated rounded-input p-8 overflow-x-auto whitespace-pre-wrap max-h-[200px]">
            {r.content}
          </pre>
        </div>
      ))}
    </div>
  )
}

/**
 * ConfirmDialog — a small modal for the two removal verbs. `typeToConfirm`
 * requires the project code to be typed for the destructive one.
 */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  danger,
  typeToConfirm,
  pending,
  onConfirm,
  onClose,
}: {
  title: string
  body: React.ReactNode
  confirmLabel: string
  danger?: boolean
  typeToConfirm?: string
  pending: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  const [typed, setTyped] = useState('')
  const ready = !typeToConfirm || typed.trim() === typeToConfirm
  return (
    <Modal label={title} onClose={onClose} width="w-[440px]">
      <div className="flex flex-col gap-12">
        <h2 className="text-14 font-semibold text-primary">{title}</h2>
        <p className="text-13 text-secondary leading-relaxed max-w-reading">{body}</p>
        {typeToConfirm && (
          <Input
            value={typed}
            onChange={(e) => setTyped(e.currentTarget.value)}
            placeholder={t('type {code} to confirm', { code: typeToConfirm })}
            aria-label={t('Type the project code to confirm')}
            className="font-mono"
          />
        )}
        <div className="flex items-center gap-8 justify-end">
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>
            {t('Cancel')}
          </Button>
          <Button
            variant={danger ? 'danger' : 'primary'}
            size="sm"
            type="button"
            disabled={!ready || pending}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/**
 * CopyCommand — one shell command as a row: mono text, muted note, and a
 * one-click copy of exactly the text shown.
 */
export function CopyCommand({ cmd, note }: { cmd: string; note?: string }) {
  return (
    <div className="flex items-center gap-8 bg-elevated rounded-input px-12 py-6 min-w-0 group">
      <code className="text-12 font-mono text-secondary whitespace-nowrap overflow-x-auto">
        {cmd}
      </code>
      {note && (
        <span className="text-11 text-tertiary truncate hidden sm:inline">
          · {note}
        </span>
      )}
      <CopyButton
        text={cmd}
        title={t('Copy command')}
        ariaLabel={t('Copy: {cmd}', { cmd })}
        size={12}
        className="ml-auto shrink-0 h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover transition-colors duration-fast"
      />
    </div>
  )
}


/**
 * AdapterBadge — self-updating trust label. An adapter is "experimental"
 * until its first real captured agent appears in the data, then the badge
 * flips to verified on its own.
 */
export function AdapterBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <Badge tone="done">{t('capture verified')}</Badge>
  ) : (
    <Badge tone="warning" title={t('Changes to capture verified after the first recorded message')}>
      {t('experimental')}
    </Badge>
  )
}

/** One integrated project: its folder, what is in place there, and its verbs. */
/**
 * Which tools record this project's chats, and which tools this computer
 * has that do not: those lose their chats without a word, so each gets a
 * line and a Connect button.
 */
function ToolsLine({ project, tools, installed, lost, importable, ignored, onConnect, onIgnore }: {
  project: string
  tools: Record<ToolKey, boolean>
  installed?: Record<ToolKey, boolean>
  lost?: Partial<Record<ToolKey, number>>
  importable?: Partial<Record<ToolKey, number>>
  ignored?: ToolKey[]
  onConnect: (tool: ToolKey) => void
  onIgnore: (tool: ToolKey) => void
}) {
  const wired = TOOL_KEYS.filter((k) => tools[k])
  const off = new Set(ignored ?? [])
  // A tool to speak of: it ran here and nothing was recorded, or it is on
  // this computer and the project does not record it. Unless the operator
  // said it is not needed.
  const missing = TOOL_KEYS.filter((k) => !off.has(k) && ((lost?.[k] ?? 0) > 0 || (!tools[k] && installed?.[k])))
  // Sessions from before the tool was connected: no longer a warning, still not recorded.
  const earlier = IMPORTABLE.filter((k) => !missing.includes(k) && (importable?.[k] ?? 0) > 0)
  return (
    <div className="basis-full flex flex-col gap-4">
      <div className="flex items-center gap-6 flex-wrap text-11">
        <span className="text-tertiary">{t('Records')}</span>
        {wired.length
          ? wired.map((k) => <Badge key={k} tone="done">{TOOL_NAMES[k]}</Badge>)
          : <span className="text-status-amber">{t('no tool: no chat is recorded')}</span>}
      </div>
      {missing.map((k) => {
        const n = lost?.[k] ?? 0
        const tool = TOOL_NAMES[k]
        const said = n > 0
          ? tools[k]
            ? (k === 'codex'
              ? t('{tool} ran here {n} times in the last week and nothing was recorded. Codex runs the hooks of a project only once you trust them: start codex in this folder and accept.', { tool, n })
              : t('{tool} ran here {n} times in the last week and nothing was recorded: its hooks did not run.', { tool, n }))
            : t('{tool} ran here {n} times in the last week and nothing was recorded: it is not connected.', { tool, n })
          : t('{tool} is on this computer, but its chats in this project are not recorded.', { tool })
        return (
          <div key={k} className="flex items-center gap-8 flex-wrap text-12 text-status-amber" role="status">
            <CircleAlert size={12} aria-hidden />
            <span className="min-w-0">{said}</span>
            {!tools[k] && (
              <Button variant="secondary" size="sm" onClick={() => onConnect(k)}>
                {t('Connect {tool}', { tool })}
              </Button>
            )}
            <ImportSessions project={project} tool={k} n={importable?.[k] ?? 0} />
            <Button variant="text" size="sm" onClick={() => onIgnore(k)}
              title={t('Stop asking about {tool} in this project', { tool })}>
              {t('Not needed')}
            </Button>
          </div>
        )
      })}
      {earlier.map((k) => (
        <div key={k} className="flex items-center gap-8 flex-wrap text-12 text-secondary">
          <span className="min-w-0">{tn(importable?.[k] ?? 0, '{n} {tool} session from before it was connected was not recorded.', '{n} {tool} sessions from before it was connected were not recorded.', { tool: TOOL_NAMES[k] })}</span>
          <ImportSessions project={project} tool={k} n={importable?.[k] ?? 0} />
        </div>
      ))}
    </div>
  )
}

export function IntegrationRow({
  it,
  installed,
  onRefresh,
  onConnect,
  onIgnore,
  onDisconnect,
  onDelete,
}: {
  it: Integration
  installed?: Record<ToolKey, boolean>
  onRefresh: () => void
  onConnect: (tool: ToolKey) => void
  onIgnore: (tool: ToolKey) => void
  onDisconnect: () => void
  onDelete: () => void
}) {
  const status =
    it.status === 'fresh' ? (
      <span className="inline-flex items-center gap-4 text-status-green text-12">
        <CheckCircle2 size={14} aria-hidden /> {t('fresh')}
      </span>
    ) : it.status === 'stale' ? (
      <span className="inline-flex items-center gap-4 text-status-amber text-12">
        <CircleAlert size={14} aria-hidden /> {t('stale contract path')}
      </span>
    ) : (
      <span className="inline-flex items-center gap-4 text-error text-12">
        <CircleX size={14} aria-hidden /> {t('block missing')}
      </span>
    )
  const fact = (ok: boolean, yes: string, no: string, noTone: 'amber' | 'muted') => (
    <span
      className={`inline-flex items-center gap-4 text-11 font-mono ${
        ok ? 'text-status-green' : noTone === 'amber' ? 'text-status-amber' : 'text-tertiary'
      }`}
    >
      {ok ? <CheckCircle2 size={12} aria-hidden /> : <CircleAlert size={12} aria-hidden />}
      {ok ? yes : no}
    </span>
  )
  return (
    <li className="rounded-card border border-border-subtle bg-surface px-16 py-12 flex items-center gap-12 min-w-0 flex-wrap">
      <span className="font-mono text-13 text-primary shrink-0">{it.project}</span>
      <span className="font-mono text-12 text-tertiary truncate" title={it.path}>
        {it.path}
      </span>
      <span className="ml-auto shrink-0 flex items-center gap-10">
        <span title={t("The capture hooks are in this folder's .claude/settings.local.json. Start the agent here.")}>
          {fact(it.hooks, t('hooks'), t('hooks missing'), 'amber')}
        </span>
        <span title={t('Optional. With git, scans list commits, line counts and diffs. Without it, they list the files each turn changed.')}>
          {fact(it.git, 'git', t('no git · files only'), 'muted')}
        </span>
        {status}
      </span>
      {it.status !== 'fresh' && (
        <Button variant="secondary" size="sm" onClick={onRefresh}>
          {t('Re-integrate')}
        </Button>
      )}
      {it.tools && installed && (
        <ToolsLine project={it.project} tools={it.tools} installed={installed} lost={it.lost} importable={it.importable}
          ignored={it.ignored} onConnect={onConnect} onIgnore={onIgnore} />
      )}
      <span className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={onDisconnect}
          title={t('Stop recording and remove what Setup wrote; the data is kept')}
          aria-label={t('Disconnect {project}', { project: it.project })}
          className="h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover"
        >
          <Unplug size={14} aria-hidden />
        </button>
        <button
          type="button"
          onClick={onDelete}
          title={t("Move all of this project's data to .trash/")}
          aria-label={t('Delete data for {project}', { project: it.project })}
          className="h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-error hover:bg-hover"
        >
          <Trash2 size={14} aria-hidden />
        </button>
      </span>
    </li>
  )
}
