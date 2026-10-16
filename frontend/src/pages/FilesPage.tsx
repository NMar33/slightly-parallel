import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { PageHeader } from '../components/PageHeader'
import { FILES_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { projectColor } from '../utils/projectColor'
import { FilesTab } from '../features/project/FilesTab'
import type { Payload } from '../features/files/rows'
import { getJson } from '../lib/getJson'
import { t, tn, locale } from '../i18n/scope/pages'

/**
 * /files — every project's file activity, drawn exactly as a project's
 * Files tab draws its own: the grid, the ranking, the story and the
 * weight, the same orderings, with a row of project chips to narrow it.
 * The header counts the whole; the tab reads the same payload (one query
 * key), so the two never disagree.
 */
export default function FilesPage() {
  const blurb = t('every project · the same views as a project\'s Files tab')
  useEffect(() => { document.title = `${t('Files')} — Slightly Parallel` }, [])
  const heat = useQuery({
    queryKey: ['lens', 'files', 'heatmap', ''],
    queryFn: ({ signal }) => getJson<Payload>('/api/files/heatmap?limit_files=500', signal),
  })
  const data = heat.data
  const projects = data ? [...new Set(data.entries.map((e) => e.project ?? ''))].filter(Boolean).sort() : []
  const churn = data ? data.files.reduce((a, f) => a + f.lines_add + f.lines_del, 0) : 0

  return (
    <div className="flex flex-col gap-14 min-w-0">
      <PageHeader
        variant="tool"
        title={t('Files')}
        sub={blurb}
        below={data ? (
          <div className="flex items-baseline gap-14 text-11 font-mono text-tertiary flex-wrap">
            <span>{tn(projects.length, '{n} project', '{n} projects')}</span>
            <span>{tn(data.files.length, '{n} file', '{n} files')}</span>
            <span>{tn(data.entries.length, '{n} scan', '{n} scans')}</span>
            <span>{t('{n} lines changed', { n: churn.toLocaleString(locale()) })}</span>
            {projects.map((p) => (
              <span key={p} className="inline-flex items-center gap-3">
                <span className="h-6 w-6 rounded-pill" style={{ backgroundColor: projectColor(p) }} aria-hidden />
                {p}
              </span>
            ))}
          </div>
        ) : undefined}
      />
      <PageGuide id="files" guide={FILES_GUIDE} examples={0} />
      <FilesTab />
    </div>
  )
}
