import { useEffect, useMemo } from 'react'

import { PageHeader } from '../components/PageHeader'
import { EmptyState, LoadingSkeleton } from '../components/states'
import { FILES_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { projectColor } from '../utils/projectColor'
import { useControls } from '../features/files/parts'
import { byProject, useFleet } from '../features/files/fleet'
import { CalendarFiles } from '../features/files/calendarFiles'
import { t, tn, locale } from '../i18n/scope/pages'

/**
 * /files — the lens page: every project's checkpoints, newest day first.
 *
 * The project tab answers "what happened to this codebase". This answers
 * what no single project can: what shipped anywhere, on which day, in which
 * repo — and clicking any path opens that file's whole account of itself.
 * The page draws its own header, then its guide.
 */
export default function FilesPage() {
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <FilesFleet />
    </div>
  )
}

function FilesFleet() {
  const { data, err } = useFleet()
  const { weight } = useControls()
  const blurb = t('days · click a file to open its details')

  useEffect(() => { document.title = `${t('Files')} · ${blurb.split(' · ')[0]} — Slightly Parallel` }, [blurb])

  const projects = useMemo(() => (data ? byProject(data, weight) : []), [data, weight])
  // A project's colour is its own everywhere (projectColor), drawn as a dot.
  const toneOf = projectColor

  if (err) return <p className="text-12 text-error">{t('The file activity could not be read: {error}', { error: err })}</p>
  if (!data) return <LoadingSkeleton variant="row" count={5} />

  const totalChurn = projects.reduce((a, p) => a + p.churn, 0)

  return (
    <div className="flex flex-col gap-14">
      <PageHeader
        variant="tool"
        title={t('Files')}
        sub={blurb}
        below={(
          <div className="flex items-baseline gap-14 text-11 font-mono text-tertiary flex-wrap">
            <span>{tn(projects.length, '{n} project', '{n} projects')}</span>
            <span>{tn(data.files.length, '{n} file', '{n} files')}</span>
            <span>{tn(data.entries.length, '{n} scan', '{n} scans')}</span>
            <span>{t('{n} lines changed', { n: totalChurn.toLocaleString(locale()) })}</span>
            {projects.map((p) => (
              <span key={p.project} className="inline-flex items-center gap-3">
                <span className="h-6 w-6 rounded-pill" style={{ backgroundColor: toneOf(p.project) }} aria-hidden />
                {p.project}
              </span>
            ))}
          </div>
        )}
      />
      <PageGuide id="files" guide={FILES_GUIDE} examples={0} />

      {data.entries.length === 0 ? (
        <EmptyState title={t('No file entries yet')} subtitle={t('An agent posts one with each scan.')} />
      ) : (
        <CalendarFiles data={data} toneOf={toneOf} />
      )}
    </div>
  )
}
