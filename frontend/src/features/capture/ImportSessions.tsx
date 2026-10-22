/**
 * Import sessions nothing recorded, from the tool's own log
 * (backend sessionimport.py). A button that opens what an import would
 * write — one row per session — and imports on the operator's word.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Modal } from '../../components/Modal'
import { Button } from '../../components/primitives'
import { getJson, postJson } from '../../lib/getJson'
import { SETUP_INFO_KEY, TOOL_NAMES, type ToolKey } from '../setup/data'
import { t, tn } from '../../i18n/scope/system'

interface PreviewRow { session: string; agent_id: string; turns: number; started: string; ended: string; first: string }

/** The tools whose own logs can be read. */
export const IMPORTABLE: ToolKey[] = ['claude', 'codex']

export function ImportSessions({ project, tool, n }: { project: string; tool: ToolKey; n: number }) {
  const [open, setOpen] = useState(false)
  if (!IMPORTABLE.includes(tool) || n <= 0) return null
  return (
    <>
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        {tn(n, 'Import {n} session', 'Import {n} sessions')}
      </Button>
      {open && <ImportDialog project={project} tool={tool} onClose={() => setOpen(false)} />}
    </>
  )
}

function ImportDialog({ project, tool, onClose }: { project: string; tool: ToolKey; onClose: () => void }) {
  const queryClient = useQueryClient()
  const preview = useQuery({
    queryKey: ['capture', 'import', project, tool],
    queryFn: ({ signal }) => getJson<{ sessions: PreviewRow[] }>(
      `/api/capture/import?project=${encodeURIComponent(project)}&tool=${tool}`, signal),
  })
  const run = useMutation({
    mutationFn: () => postJson<{ imported: unknown[]; skipped: unknown[] }>('/api/capture/import', { project, tool }),
    onSuccess: (r) => {
      toast.success(tn(r.imported.length, 'Imported {n} session', 'Imported {n} sessions'))
      void queryClient.invalidateQueries({ queryKey: ['capture'] })
      void queryClient.invalidateQueries({ queryKey: SETUP_INFO_KEY })
      void queryClient.invalidateQueries({ queryKey: ['snapshot'] })
      onClose()
    },
    onError: () => toast.error(t('Could not import them')),
  })
  const rows = preview.data?.sessions ?? []
  const title = t('Import {tool} sessions into {project}', { tool: TOOL_NAMES[tool], project })
  return (
    <Modal label={title} onClose={onClose} width="w-[640px]">
      <div className="flex flex-col gap-12">
        <h2 className="text-14 font-semibold text-primary">{title}</h2>
        <p className="text-13 text-secondary leading-relaxed max-w-reading">
          {t('These sessions ran in the project folder and nothing recorded them. They are read from the tool\'s own log and written as chats, with the times the messages were written. A command in them (#task, #done …) is not carried out.')}
        </p>
        {preview.isLoading && <p className="text-12 text-tertiary">{t('Reading the log…')}</p>}
        {preview.isError && <p className="text-12 text-error">{t('Could not read the log.')}</p>}
        {preview.data && rows.length === 0 && (
          <p className="text-12 text-tertiary">{t('Nothing to import: each session is recorded already, or still going on.')}</p>
        )}
        {rows.length > 0 && (
          <ul className="flex flex-col gap-6 max-h-[320px] overflow-auto">
            {rows.map((r) => (
              <li key={r.session} className="rounded-input border border-border-subtle px-10 py-6 flex flex-col gap-2 min-w-0">
                <span className="text-11 font-mono text-tertiary">
                  {r.agent_id} · {r.started.replace('T', ' ').slice(0, 16)} · {tn(r.turns, '{n} message', '{n} messages')}
                </span>
                <span className="text-12 text-secondary truncate" title={r.first}>{r.first}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-11 text-tertiary">
          {t('The logs are the tools\' own formats and change between versions: check a chat after the import.')}
        </p>
        <div className="flex items-center gap-8 justify-end">
          <Button variant="ghost" size="sm" type="button" onClick={onClose}>{t('Cancel')}</Button>
          <Button variant="primary" size="sm" disabled={!rows.length || run.isPending} onClick={() => run.mutate()}>
            {tn(rows.length, 'Import {n} session', 'Import {n} sessions')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
