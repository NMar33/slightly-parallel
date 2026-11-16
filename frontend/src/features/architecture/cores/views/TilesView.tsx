import { formatStamp } from '../../../../utils/dateUtils'
import type { CoreSummary } from '../data'
import { AgentName, ActivityGrid, TrackingWord, TypeDot, TypeWord } from '../parts'
import type { CoreViewProps } from './types'
import { t, tn } from '../../../../i18n/scope/system'

/** The cores as tiles: type and tracking, why it is kept, the latest note
 *  with who wrote it, the 30-day grid and the counts. */
export function TilesView({ cores, show, onOpen }: CoreViewProps) {
  const inView = cores.filter((c) => c.status === 'view')
  return (
    <div className="grid gap-12" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))' }}>
      {inView.map((c) => <Tile key={c.id} core={c} show={show} onOpen={() => onOpen(c.id)} />)}
    </div>
  )
}

function Tile({ core, show, onOpen }: { core: CoreSummary; show: CoreViewProps['show']; onOpen: () => void }) {
  const last = core.last_note && (show === 'everyone' || core.last_note.approved) ? core.last_note : null
  const first = last?.kind === 'founding'
  const byAgent = !!last && last.author !== 'operator' && !!last.author
  const done = core.tasks_n - core.open_n
  return (
    <button type="button" onClick={onOpen}
      className="text-left flex flex-col gap-12 rounded-card border border-border-subtle bg-surface p-16 min-h-[236px] hover:border-border-strong transition-colors min-w-0">
      <div className="flex items-center gap-8 min-w-0">
        <TypeDot type={core.type} />
        <TypeWord type={core.type} />
        <span className="ml-auto flex items-center gap-8">
          {core.pending_n > 0 && (
            <span className="text-10 font-mono text-brand">{tn(core.pending_n, '{n} to approve', '{n} to approve')}</span>
          )}
          <TrackingWord tracking={core.tracking} />
        </span>
      </div>

      <div className="flex flex-col gap-4 min-w-0">
        <span className="text-16 font-semibold text-primary leading-tight break-words">{core.name}</span>
        {core.reason && <span className="text-12 text-secondary leading-snug line-clamp-2 break-words">{core.reason}</span>}
      </div>

      <div className="flex-1 min-w-0">
        {last ? (
          <div className="flex flex-col gap-4">
            <p className={`m-0 text-12 text-primary leading-snug line-clamp-3 break-words ${byAgent ? 'rounded-input px-8 py-6' : ''}`}
              style={byAgent ? { background: 'var(--brand-glow)' } : undefined}>
              {first ? last.text || last.comment : last.comment || last.text}
            </p>
            <span className="text-10 font-mono text-tertiary">
              {formatStamp(last.at).split(' ')[0]} · {byAgent ? <AgentName id={last.author} /> : t('you')}{first && <> · {t('first note')}</>}
              {byAgent && !last.approved && <span className="text-brand"> · {t('to approve')}</span>}
            </span>
          </div>
        ) : (
          <span className="text-12 text-tertiary">{t('No notes yet.')}</span>
        )}
      </div>

      <div className="flex items-end justify-between gap-12">
        <ActivityGrid grid={core.grid} type={core.type} cell={9} gap={2} />
        <div className="flex flex-col items-end gap-4 text-10 font-mono text-tertiary">
          {core.tasks_n > 0 ? (
            <>
              <span>{tn(core.open_n, '{n} open', '{n} open')} · {tn(core.tasks_n, '{n} task', '{n} tasks')}</span>
              <span className="block w-[96px] h-[4px] rounded-pill bg-elevated overflow-hidden" aria-hidden="true">
                <i className="block h-full bg-status-green" style={{ width: `${Math.round((100 * done) / core.tasks_n)}%` }} />
              </span>
            </>
          ) : <span>{t('no tasks')}</span>}
          <span>{tn(core.notes_n, '{n} note', '{n} notes')}</span>
        </div>
      </div>
    </button>
  )
}
