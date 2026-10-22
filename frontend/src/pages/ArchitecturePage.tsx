import { PageHeader } from '../components/PageHeader'
import { ProjectFolder } from '../lib/paths'
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Landmark } from 'lucide-react'

import { Input } from '../components/primitives'
import { useHashState } from '../hooks/useHashState'
import { ARCHITECTURE_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/states'
import { OwesStrip, ProjectPicker, useLedgerProject } from '../features/architecture/ledgerParts'
import { ArchViewSwitch, ArchitectureView, useArchView } from '../features/architecture/views'
import { ArchPagePanel } from '../features/architecture/page/ArchPagePanel'
import { MapPanel } from '../features/architecture/map/MapPanel'
import { ArchModeSwitch, useArchMode } from '../features/architecture/page/mode'
import { t, tn } from '../i18n/scope/pages'

/**
 * /architecture — one project's architecture: its page, and its ledger read
 * three ways. The same two parts the project tab carries.
 *
 * The same three views the project tab carries, on a page of their own
 * with the project in the URL, so a reading can be linked. It opens on
 * the project that has a ledger, not the first one alphabetically; the
 * picker says how many changes each project holds. The lens's raw rows
 * are still one drawer away wherever an entry is named — this page is
 * the reading, not the table.
 */
export default function ArchitecturePage() {
  const { codes, project, setProject, model, models, loading, error } = useLedgerProject()
  const [view, setView] = useArchView()
  const [mode, setMode] = useArchMode()
  const [hash, setHash] = useHashState()
  useEffect(() => { document.title = `${t('Architecture')} — Slightly Parallel` }, [])

  const standing = model ? model.entities.filter((e) => !e.gone).length : null
  // The register is the view a find narrows; the stream and the codebase
  // have their own controls, so the box is not offered there.
  const findable = mode === 'ledger' && view === 'register'

  return (
    <ProjectFolder project={project}>
    <div className="flex flex-col gap-16 min-w-0">
      <div className="flex flex-col gap-10">
        <PageHeader
          variant="lens" icon={Landmark} title={t('Architecture')} count={standing ?? ''}
          actions={<>
            {project && (
              <Link to={`/project/${encodeURIComponent(project)}#architecture`} className="text-11 font-mono text-tertiary hover:text-primary">
                {t('Project')} →
              </Link>
            )}
            {findable && (
              <Input value={hash.q ?? ''} onChange={(e) => setHash({ q: e.target.value })}
                placeholder={t('Find a thing')} aria-label={t('Find a thing')} className="w-[220px] h-24 text-12" />
            )}
          </>}
        />
        <div className="flex items-center gap-10 flex-wrap">
          <ProjectPicker codes={codes} project={project} models={models} onPick={setProject} />
          <ArchModeSwitch value={mode} onChange={setMode} />
          {mode === 'ledger' && <ArchViewSwitch value={view} onChange={setView} />}
          {mode === 'ledger' && model && (
            <span className="text-11 font-mono text-tertiary">
              {tn(model.totalChanges, '{n} change', '{n} changes')} · {t('{answered} of {total} scans answered', { answered: model.answered, total: model.scans.length })}
            </span>
          )}
        </div>
      </div>
      <PageGuide id="architecture" guide={ARCHITECTURE_GUIDE} examples={0} />

      {mode === 'page' && project && <ArchPagePanel projectCode={project} />}
      {mode === 'map' && project && <MapPanel projectCode={project} />}

      {mode === 'ledger' && <>
      {error && <ErrorBanner title={t('Could not read the architecture answers')} message={error} hideDismiss />}
      {!error && (loading || !model) && <LoadingSkeleton variant="card" count={2} />}
      {!error && model && (
        model.totalChanges === 0 ? (
          <EmptyState
            title={project ? t('No architecture answers in {project} yet', { project }) : t('No architecture answers in this project yet')}
            subtitle={t('Appears after the first #scan.')}
          />
        ) : (
          <>
            <OwesStrip rows={model.owes} />
            <ArchitectureView m={model} view={view} find={false} />
          </>
        )
      )}
      </>}
    </div>
    </ProjectFolder>
  )
}
