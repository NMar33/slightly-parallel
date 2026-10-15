import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Confirm } from '../../components/Confirm'
import { Button, toast } from '../../components/primitives'
import { useTerminalActions } from '../../lib/terminal'
import { getJson, postJson } from '../../lib/getJson'
import { TerminalPage } from '../terminal/Deck'
import { OPERATOR_ACTOR, nowStamp } from './types'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { t } from '../../i18n/scope/project'

import { rich } from '../../i18n/rich'
/**
 * TerminalsTab — the project's terminals: the Terminal page with this
 * project only (every terminal opened in its folder, with its state), and
 * the project's snippets under it, each typed and run in the terminal in
 * front. Since 2026-09-27 the terminal is one switch, with no token to type: it is
 * switch, and lives on in tmux (features/terminal).
 */

type SnippetRow = {
  id: string
  project?: string
  label?: string
  command?: string
  position?: string | number
}

export function TerminalsTab({ projectCode }: { projectCode: string }) {
  const terms = useTerminalActions()
  const activeRef = useRef('')
  // ---- Snippets ------------------------------------------------------------
  const qc = useQueryClient()
  const snippetsRead = useQuery({
    queryKey: ['lens', 'snippets', projectCode],
    queryFn: ({ signal }) => getJson<{ snippets?: SnippetRow[] }>(`/api/snippets?project=${encodeURIComponent(projectCode)}`, signal),
  })
  const snippets = Array.isArray(snippetsRead.data?.snippets) ? snippetsRead.data.snippets : []
  const snippetsError = snippetsRead.isError ? (snippetsRead.error as Error).message : null
  const rereadSnippets = () => void qc.invalidateQueries({ queryKey: ['lens', 'snippets', projectCode] })

  const runSnippet = (s: SnippetRow) => {
    const cmd = String(s.command || '')
    if (!cmd) return
    if (!activeRef.current) { toast.info(t('Open a terminal first: the + above the screen.')); return }
    terms.type(activeRef.current, cmd, true).catch((e: Error) => toast.error(t('Nothing was typed: {reason}', { reason: e.message })))
  }

  // Inline add-snippet form (replaces window.prompt dialogs).
  const [addingSnippet, setAddingSnippet] = useState(false)
  const [snippetLabel, setSnippetLabel] = useState('')
  const [snippetCommand, setSnippetCommand] = useState('')
  const [snippetSaving, setSnippetSaving] = useState(false)

  const submitSnippet = async () => {
    const label = snippetLabel.trim()
    const command = snippetCommand.trim()
    if (!label || !command || snippetSaving) return
    setSnippetSaving(true)
    const { dateStr, timeStr } = nowStamp()
    try {
      await postJson('/api/snippets', {
        project: projectCode,
        agent_id: OPERATOR_ACTOR,
        created_date: dateStr,
        created_time: timeStr,
        label,
        command,
        position: '999',
      })
      setAddingSnippet(false)
      setSnippetLabel('')
      setSnippetCommand('')
      rereadSnippets()
    } catch (e) {
      toast.error(t('Couldn\'t save snippet'), { description: String((e as Error)?.message ?? e) })
    } finally {
      setSnippetSaving(false)
    }
  }

  /** The snippet being asked about — components/Confirm is the one way. */
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null)

  const deleteSnippet = async (id: string) => {
    setConfirmingDeleteId(null)
    try {
      await postJson(`/api/snippets/${encodeURIComponent(id)}/delete`, {})
      rereadSnippets()
    } catch (e) {
      toast.error(t('Couldn\'t delete snippet'), { description: String((e as Error)?.message ?? e) })
    }
  }

  return (
    <TerminalPage project={projectCode} below={(active) => {
      activeRef.current = active
      return (
        <div className="flex flex-col gap-8">
      {/* Snippet shortcuts */}
      <div className="pt-4">
        <div className="flex items-baseline gap-8 mb-6">
          <span className={LABEL}>{t('Snippets')}</span>
          <span className="text-11 text-tertiary font-mono">{t('Click to run it in the open terminal')}</span>
          <button
            type="button"
            onClick={() => setAddingSnippet((v) => !v)}
            className="ml-auto text-11 text-brand hover:text-brand-hover font-mono"
          >
            {addingSnippet ? 'cancel' : t('+ new')}
          </button>
        </div>

        {addingSnippet && (
          <form
            onSubmit={(e) => { e.preventDefault(); submitSnippet() }}
            className="flex flex-wrap items-center gap-6 mb-8"
          >
            <input
              autoFocus
              value={snippetLabel}
              onChange={(e) => setSnippetLabel(e.target.value)}
              placeholder={t('Label')}
              aria-label={t('Snippet label')}
              className={`${FIELD} w-[160px]`}
            />
            <input
              value={snippetCommand}
              onChange={(e) => setSnippetCommand(e.target.value)}
              placeholder={t('Command')}
              aria-label={t('Snippet command')}
              className={`${FIELD} flex-1 min-w-[220px]`}
            />
            <Button
              type="submit"
              variant="primary"
              size="sm"
              disabled={!snippetLabel.trim() || !snippetCommand.trim() || snippetSaving}
            >
              {snippetSaving ? 'Saving…' : t('Add')}
            </Button>
          </form>
        )}

        {snippetsError ? (
          <div className="text-11 text-error">
            {t('Couldn\'t load snippets:')} {snippetsError}{' '}
            <button
              type="button"
              onClick={() => rereadSnippets()}
              className="text-brand hover:text-brand-hover underline"
            >
              {t('retry')}
            </button>
          </div>
        ) : snippets.length === 0 ? (
          <div className="text-11 text-tertiary italic">
            {rich(t('No snippets yet — {add}.'), { add: <button type="button" onClick={() => setAddingSnippet(true)} className="text-brand hover:text-brand-hover">{t('add first')}</button> })}
          </div>
        ) : (
          <div className="flex flex-wrap gap-6">
            {snippets.map((s) => (confirmingDeleteId === s.id ? (
              <Confirm
                key={s.id}
                text={t('Delete the snippet “{name}”.', { name: s.label ?? s.id })}
                action={t('Delete')}
                onYes={() => void deleteSnippet(s.id)}
                onNo={() => setConfirmingDeleteId(null)}
              />
            ) : (
              <div
                key={s.id}
                className="group flex items-center gap-2 bg-elevated border border-border-default rounded-input px-2 hover:border-brand"
              >
                <button
                  type="button"
                  onClick={() => runSnippet(s)}
                  className="px-8 py-4 text-12 text-primary font-mono"
                  title={s.command}
                >
                  {s.label}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingDeleteId(s.id)}
                  className="opacity-0 group-hover:opacity-100 text-tertiary hover:text-error px-2 text-11"
                  title={t('Delete snippet')}
                  aria-label={`Delete snippet ${s.label ?? s.id}`}
                >
                  ×
                </button>
              </div>
            )))}
          </div>
        )}
      </div>
        </div>
      )
    }} />
  )
}
