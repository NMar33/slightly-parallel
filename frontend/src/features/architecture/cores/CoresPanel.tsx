import { useMemo, useState } from 'react'

import { Modal } from '../../../components/Modal'
import { Segmented } from '../../../components/Segmented'
import { Button, Input, toast } from '../../../components/primitives'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../../components/states'
import { useHashState } from '../../../hooks/useHashState'
import { formatStamp } from '../../../utils/dateUtils'
import { FIELD } from '../../promptlib/taskstyle'
import { CorePage } from './CorePage'
import { CORE_TYPES, useCoreWrites, useCores } from './data'
import { TypeDot, typeHint, typeWord } from './parts'
import { MapView } from './views/MapView'
import { RoadmapView } from './views/RoadmapView'
import { TilesView } from './views/TilesView'
import type { CoreViewName } from './views/types'
import { persistPref, readPref } from '../../../lib/uiPrefs'
import { t, tn } from '../../../i18n/scope/system'

/**
 * Architecture › cores: the program's core elements the operator keeps in
 * view, as tiles. One tile: the name, its type in colour, why it is kept,
 * the last note, the 30-day grid, the linked tasks and the tracking state.
 * A click opens the core (CorePage) in place; the hash carries which one.
 * Under the tiles, the cores taken out of view, with their stories kept.
 */
export function CoresPanel({ projectCode }: { projectCode: string }) {
  const [hash, setHash] = useHashState()
  if (hash.core) return <CorePage projectCode={projectCode} coreId={hash.core} onBack={() => setHash({ core: '' })} />
  return <CoreTiles projectCode={projectCode} onOpen={(id) => setHash({ core: id })} />
}

type Show = 'everyone' | 'operator'

const VIEW_KEY = 'sp-cores-view'
const VIEWS: Array<readonly [CoreViewName, string, string]> = [
  ['tiles', t('Tiles'), t('Each core as a tile')],
  ['roadmap', t('Roadmap'), t('How each core changed, day by day, with standups and releases')],
  ['map', t('Map'), t('The cores over the map of the program')],
]

function useCoreView(): [CoreViewName, (v: CoreViewName) => void] {
  const [view, setView] = useState<CoreViewName>(() => {
    const kept = readPref(VIEW_KEY) === 'lanes' ? 'roadmap' : readPref(VIEW_KEY)
    return VIEWS.some(([v]) => v === kept) ? (kept as CoreViewName) : 'tiles'
  })
  return [view, (v) => { setView(v); persistPref(VIEW_KEY, v) }]
}

function CoreTiles({ projectCode, onOpen }: { projectCode: string; onOpen: (id: string) => void }) {
  const { data, isLoading, isError, error, refetch } = useCores(projectCode)
  const [show, setShow] = useState<Show>('everyone')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [adding, setAdding] = useState(false)
  const [view, setView] = useCoreView()

  const cores = useMemo(() => data?.cores ?? [], [data])
  const shown = useMemo(() => cores.filter((c) => !typeFilter || c.type === typeFilter), [cores, typeFilter])
  const inView = useMemo(() => shown.filter((c) => c.status === 'view'), [shown])
  const out = useMemo(() => cores.filter((c) => c.status !== 'view'), [cores])
  const typesPresent = useMemo(() => CORE_TYPES.filter((ty) => cores.some((c) => c.type === ty && c.status === 'view')), [cores])

  if (isError) return <ErrorBanner title={t('Could not load the cores.')} message={error instanceof Error ? error.message : String(error)} onRetry={() => void refetch()} hideDismiss />
  if (isLoading || !data) return <LoadingSkeleton variant="card" count={2} />

  const props = { projectCode, cores: shown, show, onOpen }
  return (
    <div className="flex flex-col gap-14 min-w-0">
      <div className="flex items-center gap-10 flex-wrap text-11 font-mono text-tertiary">
        <Segmented label={t('View')} shape="pill" value={view} onChange={setView} options={VIEWS} />
        <span className="text-12 text-primary">{tn(inView.length, '{n} core in view', '{n} cores in view')}</span>
        <span>·</span>
        <span>{tn(inView.filter((c) => c.tracking.on).length, '{n} tracked', '{n} tracked')}</span>
        {inView.some((c) => c.pending_n > 0) && (
          <span className="text-brand">· {tn(inView.reduce((n, c) => n + c.pending_n, 0), '{n} note awaiting approval', '{n} notes awaiting approval')}</span>
        )}
        <span className="ml-auto flex items-center gap-10 flex-wrap">
          <Segmented label={t('Whose notes')} shape="pill" value={show} onChange={setShow}
            options={[['everyone', t('everyone'), t('Show the latest note by anyone')], ['operator', t('operator'), t('Show the latest note you wrote or approved')]]} />
          <Button size="sm" onClick={() => setAdding(true)}>{t('New core')}</Button>
        </span>
      </div>

      {typesPresent.length > 1 && (
        <div className="flex items-center gap-12 flex-wrap text-11 font-mono text-tertiary">
          <span className="uppercase tracking-wider text-10">{t('types')}</span>
          {typesPresent.map((ty) => (
            <button key={ty} type="button" onClick={() => setTypeFilter(typeFilter === ty ? '' : ty)}
              title={typeHint(ty)}
              className={`inline-flex items-center gap-6 rounded-pill px-6 py-2 ${typeFilter === ty ? 'bg-elevated text-primary' : 'hover:text-primary'}`}>
              <TypeDot type={ty} />{typeWord(ty)}
            </button>
          ))}
        </div>
      )}

      {cores.length === 0 ? (
        <EmptyState title={t('No cores yet.')}
          subtitle={t('Add a core here, or type #core-new and a description in a chat with an agent. Your message becomes its first note.')} />
      ) : inView.length === 0 && view !== 'map' ? (
        <EmptyState title={t('No core of this type in view.')} />
      ) : view === 'roadmap' ? <RoadmapView {...props} />
        : view === 'map' ? <MapView {...props} />
          : <TilesView {...props} />}

      {out.length > 0 && view !== 'roadmap' && (
        <div className="flex items-center gap-12 flex-wrap border-t border-dashed border-border-subtle pt-10 text-12 text-secondary">
          <span className="text-10 font-mono uppercase tracking-wider text-tertiary">{t('out of view')}</span>
          {out.map((c) => (
            <button key={c.id} type="button" onClick={() => onOpen(c.id)} className="inline-flex items-center gap-6 hover:text-primary">
              <TypeDot type={c.type} size={8} />{c.name}
              <span className="text-10 font-mono text-tertiary">· {t('removed {date}', { date: formatStamp(c.off_at).split(' ')[0] ?? '' })}</span>
            </button>
          ))}
          <span className="ml-auto text-10 font-mono text-tertiary">{t('Notes and links are kept when a core is removed from view.')}</span>
        </div>
      )}

      {adding && <NewCoreModal projectCode={projectCode} onClose={() => setAdding(false)} onMade={onOpen} />}
    </div>
  )
}

function NewCoreModal({ projectCode, onClose, onMade }: { projectCode: string; onClose: () => void; onMade: (id: string) => void }) {
  const writes = useCoreWrites(projectCode)
  const [name, setName] = useState('')
  const [type, setType] = useState<string>('capability')
  const [reason, setReason] = useState('')
  const [text, setText] = useState('')
  const [anchors, setAnchors] = useState('')
  const busy = writes.create.isPending
  const submit = async () => {
    if (!name.trim()) return
    try {
      const got = await writes.create.mutateAsync({
        name: name.trim(), type, reason: reason.trim(), text: text.trim(),
        anchors: anchors.split(/[\n,]/).map((s) => s.trim()).filter(Boolean),
      })
      if (got.existing) toast.success(t('This core is already in view.'))
      onClose()
      onMade(got.core.id)
    } catch (e) {
      toast.error(t('Could not create the core.'), { description: e instanceof Error ? e.message : String(e) })
    }
  }
  return (
    <Modal labelledBy="new-core-title" onClose={onClose} width="w-[560px]">
      <div className="flex flex-col gap-12">
        <h3 id="new-core-title" className="text-16 font-semibold text-primary m-0">{t('New core')}</h3>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('name')}
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} autoFocus placeholder={t('Core name')} />
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
          <span className="text-10">{typeHint(type)}</span>
        </div>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('why it is kept in view')}
          <Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} placeholder={t('Why this core is kept in view')} />
        </label>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('first note')}
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} className={`${FIELD} w-full font-sans`} />
        </label>
        <label className="flex flex-col gap-4 text-11 font-mono text-tertiary">
          {t('files this core is in')}
          <textarea value={anchors} onChange={(e) => setAnchors(e.target.value)} rows={2} className={`${FIELD} w-full`} placeholder={t('File path or file:symbol, one per line')} />
        </label>
        <div className="flex justify-end gap-8">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>{t('Cancel')}</Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !name.trim()}>{t('Keep in view')}</Button>
        </div>
      </div>
    </Modal>
  )
}
