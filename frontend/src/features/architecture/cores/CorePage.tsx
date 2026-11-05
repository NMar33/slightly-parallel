import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { Confirm } from '../../../components/Confirm'
import { Modal } from '../../../components/Modal'
import { Segmented } from '../../../components/Segmented'
import { Switch } from '../../../components/Switch'
import { Badge, Button, Input, toast } from '../../../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../../../components/states'
import { formatStamp } from '../../../utils/dateUtils'
import { TaskAddModal } from '../../project/kanban/TaskWindow'
import type { TaskRow } from '../../project/kanban/model'
import { fetchTask } from '../../tasks/data'
import { fail as failRead } from '../../../lib/getJson'
import { CORE_TYPES, coreColor, shownNote, useCore, useCoreWrites, type CoreDetail } from './data'
import { TrackingWord, TypeDot, typeHint, typeWord } from './parts'
import { GraphBody } from './bodies/GraphBody'
import { t } from '../../../i18n/scope/system'

/**
 * One core, as facing pages: the story on the left (the founding note,
 * then every note, newest first, the operator's on paper and the agents'
 * tinted with their approval), the evidence on the right (the linked tasks
 * with status, the 30-day grid, the files the tasks touched, the anchors,
 * what else is connected, and the commits near its anchors, apart). The
 * header band carries the type, the position (the latest note), tracking
 * with its expiry, whose notes to show, and the way out of view.
 */
export function CorePage({ projectCode, coreId, onBack }: { projectCode: string; coreId: string; onBack: () => void }) {
  const { data, isLoading, isError, error, refetch } = useCore(coreId)
  if (isError) return <ErrorBanner title={t('Could not load the core.')} message={error instanceof Error ? error.message : String(error)} onRetry={() => void refetch()} hideDismiss />
  if (isLoading || !data) return <LoadingSkeleton variant="card" count={2} />
  return <CoreBody key={coreId} projectCode={projectCode} core={data} onBack={onBack} />
}

type Show = 'everyone' | 'operator'

function CoreBody({ projectCode, core, onBack }: { projectCode: string; core: CoreDetail; onBack: () => void }) {
  const writes = useCoreWrites(projectCode, core.id)
  const [show, setShow] = useState<Show>('everyone')
  const [editing, setEditing] = useState(false)
  const [asking, setAsking] = useState<null | 'off'>(null)
  // The task window, in place: a new task for this core, or a linked one opened.
  const [taskWindow, setTaskWindow] = useState<null | 'new' | TaskRow>(null)
  const qc = useQueryClient()
  const openTask = (id: string) => fetchTask(id).then((it) => { if (it) setTaskWindow(it) }, failRead)
  const taskSaved = () => {
    setTaskWindow(null)
    void qc.invalidateQueries({ queryKey: ['core', core.id] })
    void qc.invalidateQueries({ queryKey: ['cores', projectCode] })
  }

  const position = shownNote(core.notes, show === 'operator')
  const bodyProps = { projectCode, core, show, onOpenTask: (id: string) => void openTask(id), onNewTask: () => setTaskWindow('new') }
  const color = coreColor(core.type)
  const off = core.status !== 'view'
  const busy = writes.tracking.isPending || writes.update.isPending

  const fail = (e: unknown, title: string) => toast.error(title, { description: e instanceof Error ? e.message : String(e) })

  return (
    <div className="flex flex-col gap-16 min-w-0">
      {/* the band */}
      <div className="flex rounded-card border border-border-subtle bg-surface overflow-hidden">
        <div className="w-[8px] shrink-0" style={{ background: color }} />
        <div className="flex-1 flex flex-col gap-10 p-16 min-w-0">
          <div className="flex items-center gap-8 text-11 font-mono text-tertiary flex-wrap">
            <Button variant="text" size="bare" onClick={onBack}>← {t('cores')}</Button>
            <span>/</span>
            <span style={{ color }}>{typeWord(core.type)}</span>
            <span>·</span>
            <span>{core.id}</span>
            {off && <Badge tone="idle">{t('out of view since {date}', { date: formatStamp(core.off_at).split(' ')[0] ?? '' })}</Badge>}
            <span className="ml-auto flex items-center gap-8 flex-wrap">
              <Segmented label={t('Whose notes')} shape="pill" value={show} onChange={setShow}
                options={[['everyone', t('everyone'), t('Show every note')], ['operator', t('operator'), t('Show the notes you wrote or approved')]]} />
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>{t('Edit')}</Button>
              {off
                ? <Button variant="ghost" size="sm" disabled={busy} onClick={() => writes.update.mutate({ status: 'view' }, { onError: (e) => fail(e, t('Could not restore the core.')) })}>{t('Restore to view')}</Button>
                : <Button variant="ghost" size="sm" disabled={busy} onClick={() => setAsking('off')}>{t('Remove from view')}</Button>}
            </span>
          </div>
          <div className="flex items-start justify-between gap-16 flex-wrap">
            <div className="flex flex-col gap-6 min-w-0 max-w-[760px]">
              <h2 className="text-24 font-semibold text-primary leading-tight m-0 flex items-center gap-10" style={{ letterSpacing: '-0.015em' }}>
                <TypeDot type={core.type} size={14} />{core.name}
              </h2>
              {core.reason && <p className="text-12 text-secondary m-0">{core.reason}</p>}
              <p className="text-13 text-primary m-0">
                <span className="text-10 font-mono text-tertiary uppercase tracking-wider mr-8">{t('latest note')} · {position ? formatStamp(position.at).split(' ')[0] : '—'}</span>
                {position ? (position.comment || position.text) : t('No notes yet.')}
              </p>
            </div>
            <TrackingControls core={core} busy={busy} onSet={(input) => writes.tracking.mutate(input, { onError: (e) => fail(e, t('Could not change tracking.')) })} />
          </div>
        </div>
      </div>

      <GraphBody {...bodyProps} />

      {taskWindow && (
        <TaskAddModal projectCode={projectCode} initialStatus="todo" initialCores={[core.id]}
          existingTask={taskWindow === 'new' ? null : taskWindow}
          onClose={() => setTaskWindow(null)} onSaved={(o) => { if (!o?.keepOpen) taskSaved() }} />
      )}
      {editing && <EditModal core={core} busy={writes.update.isPending} onClose={() => setEditing(false)}
        onSave={(input) => writes.update.mutate(input, { onSuccess: () => setEditing(false), onError: (e) => fail(e, t('Could not save the core.')) })} />}
      {asking === 'off' && (
        <Modal label={t('Remove from view')} onClose={() => setAsking(null)} width="w-[440px]">
          <Confirm text={t('The core is removed from the tiles. Its notes and links are kept. Restore it from the list below the tiles.')}
            action={t('Remove')} busy={writes.update.isPending}
            onNo={() => setAsking(null)}
            onYes={() => writes.update.mutate({ status: 'off' }, { onSuccess: () => setAsking(null), onError: (e) => fail(e, t('Could not remove the core.')) })} />
        </Modal>
      )}
    </div>
  )
}

/** Tracking: the switch, and while on, the end — a day, a week, a date, or none. */
function TrackingControls({ core, busy, onSet }: { core: CoreDetail; busy: boolean; onSet: (input: { on: boolean; span?: 'day' | 'week'; until?: string }) => void }) {
  const tr = core.tracking
  const [picking, setPicking] = useState(false)
  const [until, setUntil] = useState('')
  const off = core.status !== 'view'
  return (
    <div className="flex flex-col items-end gap-6 text-11 font-mono">
      <div className="flex items-center gap-10">
        <Switch on={tr.on} disabled={busy || off} label={t('Tracking')} text={tr.on ? t('tracking on') : t('tracking off')}
          title={t('On: agents may add one-line notes and link tasks when finished work changes this core. Off: notes come from you only, here or with #core-note.')}
          onChange={(next) => { if (next) setPicking(true); else onSet({ on: false }) }} />
        {tr.on && <TrackingWord tracking={tr} />}
        {tr.expired && <span className="text-tertiary">{t('expired {date}', { date: tr.until })}</span>}
      </div>
      {picking && (
        <div className="flex items-center gap-6 flex-wrap justify-end">
          <span className="text-tertiary">{t('Track for')}</span>
          <Button size="sm" variant="ghost" onClick={() => { onSet({ on: true, span: 'day' }); setPicking(false) }}>{t('a day')}</Button>
          <Button size="sm" variant="ghost" onClick={() => { onSet({ on: true, span: 'week' }); setPicking(false) }}>{t('a week')}</Button>
          <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} className="h-24 text-11 w-[150px]" aria-label={t('until')} />
          {until && <Button size="sm" variant="ghost" onClick={() => { onSet({ on: true, until }); setPicking(false) }}>{t('Until {date}', { date: until })}</Button>}
          <Button size="sm" variant="ghost" onClick={() => { onSet({ on: true }); setPicking(false) }}>{t('No expiry')}</Button>
          <Button size="sm" variant="text" onClick={() => setPicking(false)}>{t('Cancel')}</Button>
        </div>
      )}
      {!picking && tr.on && (
        <span className="text-10 text-tertiary">{t('Agents may add one-line notes and link tasks when they finish work.')}</span>
      )}
    </div>
  )
}

function EditModal({ core, busy, onClose, onSave }: {
  core: CoreDetail; busy: boolean; onClose: () => void
  onSave: (input: { name?: string; type?: string; reason?: string }) => void
}) {
  const [name, setName] = useState(core.name)
  const [type, setType] = useState(core.type)
  const [reason, setReason] = useState(core.reason)
  return (
    <Modal labelledBy="edit-core-title" onClose={onClose} width="w-[520px]">
      <div className="flex flex-col gap-12">
        <h3 id="edit-core-title" className="text-16 font-semibold text-primary m-0">{t('Edit the core')}</h3>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('name')}
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} autoFocus />
        </label>
        <div className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('type')}
          <div className="flex flex-wrap gap-6">
            {CORE_TYPES.map((ty) => (
              <button key={ty} type="button" onClick={() => setType(ty)} title={typeHint(ty)}
                className={`inline-flex items-center gap-6 rounded-pill border px-8 py-3 text-11 ${type === ty ? 'border-border-strong bg-elevated text-primary' : 'border-border-subtle text-secondary hover:text-primary'}`}>
                <TypeDot type={ty} />{typeWord(ty)}
              </button>
            ))}
          </div>
        </div>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('why it is kept in view')}
          <Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} />
        </label>
        <div className="flex justify-end gap-8">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>{t('Cancel')}</Button>
          <Button size="sm" disabled={busy || !name.trim()} onClick={() => onSave({ name: name.trim(), type, reason: reason.trim() })}>{t('Save')}</Button>
        </div>
      </div>
    </Modal>
  )
}
