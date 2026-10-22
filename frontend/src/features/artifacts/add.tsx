import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '../../components/primitives'
import { fail } from '../../lib/getJson'
import { FIELD, LABEL, PillGroup } from '../promptlib/taskstyle'
import { KINDS, NEW_ARTIFACT, type Kind, useArtifactWrites } from './data'
import { t } from '../../i18n/scope/system'

/**
 * Add a folder — the operator registers a folder made by hand.
 *
 * The folder must already be under the project in the Slightly Parallel directory;
 * the server checks it and names the problem otherwise. The fields follow
 * the task window: a labelled mono field each, a pill group for the kind.
 */

const NAME_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/

function nameProblem(name: string): string {
  if (!name) return ''
  if (name.length > 64) return t('Up to 64 characters.')
  if (!NAME_RE.test(name)) return t('Lower-case letters, digits and single hyphens.')
  return ''
}

export function AddFolder({ projects, onDone, onCancel }: { projects: string[]; onDone: (id: string) => void; onCancel: () => void }) {
  const writes = useArtifactWrites()
  const [draft, setDraft] = useState({ ...NEW_ARTIFACT, project: projects[0] ?? '' })
  const problem = nameProblem(draft.name)
  const ok = draft.project && draft.name && !problem && draft.description.trim()
  const save = () =>
    writes.register.mutate(
      { project: draft.project, name: draft.name, kind: draft.kind, description: draft.description.trim() },
      { onSuccess: (d) => { toast.success(t('Folder added')); onDone(d.metadata.id) }, onError: fail },
    )
  return (
    <section aria-label={t('Add a folder')} className="flex flex-col gap-12 rounded-card border border-border-subtle bg-surface px-16 py-12 max-w-[720px]">
      <h2 className="text-16 text-primary">{t('Add a folder')}</h2>
      <p className="text-12 text-secondary leading-relaxed">
        {t('A folder you made by hand, under the project in the Slightly Parallel directory: projects/<project>/artifacts/<name>/ with ARTIFACT.md on top.')}
      </p>
      <div className="flex flex-col gap-3">
        <label className={LABEL} htmlFor="artifact-project">{t('Project')}</label>
        <input id="artifact-project" list="artifact-projects" value={draft.project} aria-label={t('Project')}
          onChange={(e) => setDraft((d) => ({ ...d, project: e.target.value.trim() }))} className={FIELD} />
        <datalist id="artifact-projects">{projects.map((p) => <option key={p} value={p} />)}</datalist>
      </div>
      <div className="flex flex-col gap-3">
        <label className={LABEL} htmlFor="artifact-name">{t('Name')}</label>
        <input id="artifact-name" value={draft.name} aria-label={t('Name')} placeholder={t('the folder name')}
          onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value.trim() }))} className={FIELD} />
        {problem && <span className="text-11 text-status-amber">{problem}</span>}
      </div>
      <PillGroup label={t('Kind')} value={draft.kind} onChange={(v) => setDraft((d) => ({ ...d, kind: (v || 'other') as Kind }))}
        options={KINDS.map((k) => [k.kind, k.one])} />
      <div className="flex flex-col gap-3">
        <label className={LABEL} htmlFor="artifact-description">{t('Description')}</label>
        <textarea id="artifact-description" value={draft.description} aria-label={t('Description')} rows={3}
          onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} className={`${FIELD} resize-y`} />
      </div>
      <div className="flex items-center gap-8">
        <Button size="sm" variant="primary" onClick={save} disabled={!ok || writes.register.isPending}>{t('Add')}</Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>{t('Cancel')}</Button>
      </div>
    </section>
  )
}
