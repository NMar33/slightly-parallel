import { PageHeader } from '../components/PageHeader'
import { useEffect, useMemo, useState } from 'react'
import { Package, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { Button, Input } from '../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import { useHashState } from '../hooks/useHashState'
import { fail } from '../lib/getJson'
import {
  archivedOf, chaptersOf, matches, notWrittenOf, projectsOf, useArtifactWrites, useArtifacts, artifactTitle,
} from '../features/artifacts/data'
import { AddFolder } from '../features/artifacts/add'
import { NotWritten, Section } from '../features/artifacts/parts'
import { LABEL, PillGroup } from '../features/promptlib/taskstyle'
import { ARTIFACTS_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { t } from '../i18n/scope/pages'

/**
 * Artifacts — the product page, on the real record.
 *
 * One scrolling page: a chapter per kind, a section per artifact with the
 * preview inline, a rail on the left to jump. Archived artifacts sit in a
 * folded chapter at the bottom; kept #artifact messages the agent never
 * answered are reported under them.
 */

/** The sections read before the page shows at all. */
const FIRST_SCREEN = 3

export default function ArtifactsPage() {
  useEffect(() => { document.title = `${t('Artifacts')} — Slightly Parallel` }, [])
  const [hash, setHash] = useHashState()
  const q = (hash.q ?? '').trim()
  const project = hash.project ?? ''
  const { artifacts, loading: listLoading, error, near } = useArtifacts()
  const writes = useArtifactWrites()
  const [archivedOpen, setArchivedOpen] = useState(false)

  const projects = useMemo(() => projectsOf(artifacts), [artifacts])
  const inScope = useMemo(
    () => artifacts.filter((a) => (!project || a.row.project === project) && matches(a, q)),
    [artifacts, project, q],
  )
  const chapters = useMemo(() => chaptersOf(inScope), [inScope])
  const archived = useMemo(() => archivedOf(inScope), [inScope])
  const pending = useMemo(() => notWrittenOf(inScope), [inScope])
  const busy = writes.setStatus.isPending

  // The first sections wait for their folders, as the whole page used to;
  // the rest are read as they come on screen. A request with no folder is
  // read for the words it was kept from.
  const { want } = near
  const firstIds = useMemo(() => chapters.flatMap((c) => c.items).slice(0, FIRST_SCREEN).map((a) => a.row.id), [chapters])
  const pendingIds = useMemo(() => pending.map((a) => a.row.id), [pending])
  useEffect(() => { if (firstIds.length) want(firstIds) }, [firstIds, want])
  useEffect(() => { if (pendingIds.length) want(pendingIds) }, [pendingIds, want])
  const firstPending = !listLoading && artifacts.some((a) => a.pending && firstIds.includes(a.row.id))
  const [opened, setOpened] = useState(false)
  useEffect(() => { if (!listLoading && !firstPending) setOpened(true) }, [listLoading, firstPending])
  const loading = listLoading || (!opened && firstPending)

  const setStatus = (id: string, status: 'active' | 'archived') =>
    writes.setStatus.mutate({ id, status }, {
      onSuccess: () => toast.success(status === 'archived' ? t('Archived.') : t('Restored.')),
      onError: fail,
    })

  const adding = hash.add === '1'

  return (
    <div className="flex flex-col gap-16">
      <PageHeader
        variant="lens" icon={Package} title={t('Artifacts')} count={artifacts.length}
        actions={<>
          <Input value={hash.q ?? ''} onChange={(e) => setHash({ q: e.target.value })} placeholder={t('Find in artifacts')}
            aria-label={t('Find in artifacts')} className="w-[220px] h-24 text-12" />
          <Button size="sm" variant="secondary" iconLeft={<Plus size={12} aria-hidden />} onClick={() => setHash({ add: '1' })}>
            {t('Add a folder')}
          </Button>
        </>}
      />

      <PageGuide id="artifacts" guide={ARTIFACTS_GUIDE} examples={0} />

      {loading && <LoadingSkeleton variant="card" count={3} />}
      {error && <ErrorBanner title={t('Could not read artifacts')} hideDismiss />}

      {!loading && !error && (
        <div className="grid gap-24 lg:grid-cols-[220px_minmax(0,1fr)]">
          <nav aria-label={t('Chapters')} className="flex flex-col gap-12 lg:sticky lg:top-[16px] lg:self-start">
            {projects.length > 1 && (
              <PillGroup label={t('Project')} value={project} onChange={(v) => setHash({ project: v })}
                options={projects.map((p) => [p, p])} />
            )}
            {chapters.map((c) => (
              <div key={c.kind} className="flex flex-col gap-2">
                <span className={`${LABEL} px-8`}>{c.title} <span className="tabular">{c.items.length}</span></span>
                {c.items.map((a) => (
                  <a key={a.row.id} href={`#${a.row.id}`} className="px-8 py-2 text-12 font-mono text-secondary hover:text-primary truncate">
                    {artifactTitle(a)}
                  </a>
                ))}
              </div>
            ))}
            {archived.length > 0 && (
              <button type="button" onClick={() => setArchivedOpen((v) => !v)} className={`${LABEL} px-8 text-left hover:text-primary`}>
                {t('Archived')} <span className="tabular">{archived.length}</span>
              </button>
            )}
            {artifacts.length > 0 && inScope.length === 0 && <p className="px-8 text-12 font-mono text-tertiary">{t('Nothing matches.')}</p>}
            <p className="px-8 text-11 text-tertiary leading-relaxed">{t('Type #artifact in the chat and say what you want. The folder appears here.')}</p>
          </nav>

          <div className="flex flex-col gap-24 min-w-0">
            {adding && (
              <AddFolder projects={projects} onDone={(id) => { setHash({ add: '', q: '' }); setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }), 300) }}
                onCancel={() => setHash({ add: '' })} />
            )}
            {artifacts.length === 0 && !adding && (
              <div className="flex flex-col gap-4 text-13 text-secondary leading-relaxed">
                <p>{t('No artifacts yet. Type #artifact in a message to the agent and say what you want.')}</p>
                <p>{t('The agent follows the make-an-artifact skill on the Skills page.')}</p>
              </div>
            )}
            {chapters.map((c) => (
              <div key={c.kind} className="flex flex-col">
                <div className="flex items-baseline gap-8">
                  <h2 className="text-20 font-semibold text-primary">{c.title}</h2>
                  <span className="text-12 text-tertiary">{c.line}</span>
                </div>
                {c.items.map((a) => (
                  <Section key={a.row.id} a={a} busy={busy} watch={near.watch(a.row.id)}
                    onArchive={() => setStatus(a.row.id, 'archived')} onRestore={() => setStatus(a.row.id, 'active')} />
                ))}
              </div>
            ))}
            {archived.length > 0 && (
              <div className="flex flex-col">
                <button type="button" onClick={() => setArchivedOpen((v) => !v)} className="flex items-baseline gap-8 text-left">
                  <span className={`text-10 text-tertiary transition-transform ${archivedOpen ? 'rotate-90' : ''}`} aria-hidden>▶</span>
                  <h2 className="text-20 font-semibold text-primary">{t('Archived')}</h2>
                  <span className="text-12 text-tertiary tabular">{archived.length}</span>
                </button>
                {archivedOpen && archived.map((a) => (
                  <Section key={a.row.id} a={a} busy={busy} watch={near.watch(a.row.id)}
                    onArchive={() => setStatus(a.row.id, 'archived')} onRestore={() => setStatus(a.row.id, 'active')} />
                ))}
              </div>
            )}
            <NotWritten items={pending} busy={busy} onArchive={(id) => setStatus(id, 'archived')} />
          </div>
        </div>
      )}
    </div>
  )
}
