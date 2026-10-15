import { ProjectFolder } from '../../lib/paths'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { ArchPagePanel } from '../architecture/page/ArchPagePanel'
import { MapPanel } from '../architecture/map/MapPanel'
import { ArchModeSwitch, useArchMode } from '../architecture/page/mode'
import { useLedger } from '../architecture/ledger'
import { OwesStrip } from '../architecture/ledgerParts'
import { ArchViewSwitch, ArchitectureView, useArchView } from '../architecture/views'
import { t, tn } from '../../i18n/scope/project'

/**
 * Architecture tab — the project's page, and its ledger read three ways.
 *
 * The page (the default) says what the project is, as claims with their
 * evidence, over facts Slightly Parallel computed from the folder. The ledger is the
 * log of what each scan changed.
 *
 * Every /scan asks the agent one question — what did you do to the shape?
 * — and the answers are typed changes over a closed vocabulary. The
 * register folds them into the things they speak about (the default: it
 * is the closest thing to "what is this system"); the stream keeps them
 * in the order they happened, silences included; the codebase lays them
 * over the repo. Standing debt and operator actions sit above all three.
 */
export function ArchitectureTab({ projectCode }: { projectCode: string }) {
  return <ProjectFolder project={projectCode}><ArchitectureBody projectCode={projectCode} /></ProjectFolder>
}

function ArchitectureBody({ projectCode }: { projectCode: string }) {
  const { model, loading, error } = useLedger(projectCode)
  const [view, setView] = useArchView()
  const [mode, setMode] = useArchMode()

  const modeSwitch = <ArchModeSwitch value={mode} onChange={setMode} />

  if (mode === 'page' || mode === 'map') {
    return (
      <div className="flex flex-col gap-14 min-w-0">
        <div className="flex items-center gap-10 flex-wrap">
          <h2 className="text-20 font-semibold text-primary leading-none" style={{ letterSpacing: '-0.022em' }}>
            {t('Architecture')}
          </h2>
          <span className="ml-auto">{modeSwitch}</span>
        </div>
        {mode === 'page' ? <ArchPagePanel projectCode={projectCode} /> : <MapPanel projectCode={projectCode} />}
      </div>
    )
  }

  if (error) return <ErrorBanner title={t('The architecture could not be read')} message={error} />
  if (loading || !model) return <LoadingSkeleton variant="row" count={4} />

  return (
    <div className="flex flex-col gap-14 min-w-0">
      <div className="flex items-center gap-10 flex-wrap">
        <h2 className="text-20 font-semibold text-primary leading-none" style={{ letterSpacing: '-0.022em' }}>
          {t('Architecture')}
        </h2>
        <span className="text-12 font-mono text-tertiary">
          {t('{n} standing', { n: model.entities.filter((e) => !e.gone).length })} · {tn(model.totalChanges, '{n} change', '{n} changes')} ·{' '}
          <span style={{ color: model.scans.length && model.answered < model.scans.length ? 'var(--status-amber)' : undefined }}>
            {t('{answered} of {total} scans answered', { answered: model.answered, total: model.scans.length })}
          </span>
        </span>
        <span className="ml-auto flex items-center gap-8">{modeSwitch}<ArchViewSwitch value={view} onChange={setView} /></span>
      </div>

      {model.totalChanges === 0 ? (
        <EmptyState
          title={t('No architecture answers yet')}
          subtitle={t('Appears after the first #scan.')}
        />
      ) : (
        <>
          <OwesStrip rows={model.owes} />
          <ArchitectureView m={model} view={view} />
        </>
      )}
    </div>
  )
}
