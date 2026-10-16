/*
 * Step 2 of Setup: the form that integrates a project folder, the list of
 * integrated projects, the projects with data but no integration, and the
 * two removal verbs (disconnect, delete data).
 */
import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button, Input } from '../../components/primitives'
import { postJson } from '../../lib/getJson'
import { LABEL } from '../promptlib/taskstyle'
import { postIgnore, postIntegrate, SETUP_INFO_KEY, type IntegrateResult, type Integration, type SetupInfo, type ToolKey } from './data'
import { AdapterBadge, Checkbox, ConfirmDialog, Field, IntegrationRow, ResultPanel, StepCard } from './parts'
import { t, tn } from '../../i18n/scope/system'

import { rich } from '../../i18n/rich'
/** What the form says: the project, its folder, and which files to write. */
interface IntegrateForm {
  code: string
  dir: string
  notes: string
  writeAgents: boolean
  writeBridge: boolean
  writeHooks: boolean
  writeOpencode: boolean
  writeCodex: boolean
  writeCursor: boolean
}

const bodyOf = (f: IntegrateForm, dryRun: boolean) => ({
  project_code: f.code,
  project_dir: f.dir,
  notes: f.notes,
  write_agents: f.writeAgents,
  write_claude_bridge: f.writeBridge,
  write_claude_hooks: f.writeHooks,
  write_opencode_plugin: f.writeOpencode,
  write_codex_hooks: f.writeCodex,
  write_cursor_hooks: f.writeCursor,
  dry_run: dryRun,
})

/**
 * The form's state and its two writes. Each write is sent the form it is
 * for, so Re-integrate on a row sends that row's project and folder, not
 * whatever the fields held before the click.
 */
function useIntegrate() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<IntegrateForm>({
    code: '', dir: '', notes: '',
    // Every tool ticked: a stray file is cheaper than a lost chat. Unticking is the user's call.
    writeAgents: true, writeBridge: true, writeHooks: true, writeOpencode: true, writeCodex: true, writeCursor: true,
  })
  const set = <K extends keyof IntegrateForm>(k: K) => (v: IntegrateForm[K]) => setForm((f) => ({ ...f, [k]: v }))
  const [preview, setPreview] = useState<IntegrateResult | null>(null)
  const [applied, setApplied] = useState<IntegrateResult | null>(null)

  const codeValid = useMemo(() => /^[a-z0-9][a-z0-9_-]{0,63}$/.test(form.code), [form.code])
  const ready = codeValid && form.dir.trim().length > 1
    && (form.writeAgents || form.writeBridge || form.writeHooks || form.writeOpencode || form.writeCodex || form.writeCursor)

  const previewMut = useMutation({
    mutationFn: (f: IntegrateForm) => postIntegrate(bodyOf(f, true)),
    onSuccess: (r) => {
      setPreview(r)
      setApplied(null)
    },
  })
  const applyMut = useMutation({
    mutationFn: (f: IntegrateForm) => postIntegrate(bodyOf(f, false)),
    onSuccess: (r) => {
      setApplied(r)
      setPreview(null)
      void queryClient.invalidateQueries({ queryKey: SETUP_INFO_KEY })
      void queryClient.invalidateQueries({ queryKey: ['snapshot'] })
    },
  })
  /** Integrate a row again: the tools it already records stay, and the one
   *  asked for (Connect) is added — nothing else, whatever the form ticks.
   *  A row that records no tool yet takes the form's boxes. */
  const reintegrate = (it: Integration, add?: ToolKey) => {
    const any = it.tools && Object.values(it.tools).some(Boolean)
    const has = (k: ToolKey, fromForm: boolean) => (it.tools && any ? Boolean(it.tools[k]) : fromForm) || add === k
    const next = {
      ...form, code: it.project, dir: it.path,
      writeHooks: has('claude', form.writeHooks),
      writeCodex: has('codex', form.writeCodex),
      writeOpencode: has('opencode', form.writeOpencode),
      writeCursor: has('cursor', form.writeCursor),
    }
    setForm(next)
    applyMut.mutate(next)
  }
  return { form, set, codeValid, ready, preview, applied, previewMut, applyMut, reintegrate }
}

/** Disconnect and delete-data: which project is being asked about, and the write. */
function useRemovals() {
  const queryClient = useQueryClient()
  const [disconnecting, setDisconnecting] = useState<Integration | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const refreshAll = () => {
    void queryClient.invalidateQueries()
  }
  const disconnectMut = useMutation({
    mutationFn: (it: { project: string; path: string }) =>
      postJson<{ forgotten: string }>('/api/setup/forget', {
        project_code: it.project,
        path: it.path,
      }),
    onSuccess: (r) => {
      toast.success(t('Disconnected {path}. Its data is kept.', { path: r.forgotten }))
      setDisconnecting(null)
      refreshAll()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const deleteMut = useMutation({
    mutationFn: (code: string) =>
      postJson<{ project: string; trash: string; moved: Record<string, number> }>(
        '/api/setup/delete-data',
        { project_code: code, confirm: code },
      ),
    onSuccess: (r) => {
      const n = Object.values(r.moved).reduce((a, b) => a + b, 0)
      toast.success(tn(n, 'Moved {n} entry for {project} to {trash}', 'Moved {n} entries for {project} to {trash}', { project: r.project, trash: r.trash }))
      setDeleting(null)
      refreshAll()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  return { disconnecting, setDisconnecting, deleting, setDeleting, disconnectMut, deleteMut }
}

export function IntegrateStep({ info }: { info: SetupInfo }) {
  const { form, set, codeValid, ready, preview, applied, previewMut, applyMut, reintegrate } = useIntegrate()
  const { disconnecting, setDisconnecting, deleting, setDeleting, disconnectMut, deleteMut } = useRemovals()
  const queryClient = useQueryClient()
  const ignore = (project: string, tool: ToolKey) => postIgnore(project, tool)
    .then(() => {
      void queryClient.invalidateQueries({ queryKey: SETUP_INFO_KEY })
      void queryClient.invalidateQueries({ queryKey: ['capture', 'health'] })
    })
    .catch(() => toast.error(t('Could not save that')))
  const dataOnly = useMemo(() => {
    const registered = new Set(info.integrations.map((i) => i.project))
    return info.data_projects.filter((d) => !registered.has(d.code))
  }, [info])
  const { code, dir, notes, writeAgents, writeBridge, writeHooks, writeOpencode, writeCodex, writeCursor } = form

  return (
    <StepCard
      n={2}
      title={t('Integrate your projects')}
      done={info.integrations.length > 0}
    >
      <p className="text-13 text-secondary leading-relaxed max-w-reading">
        {rich(t('Give each project a short code and its folder. Setup writes the files ticked below into that folder: a section of `AGENTS.md`, a line in `CLAUDE.md`, the capture hooks and the MCP entry. Integrating again updates them in place.'))}
      </p>

      <Field label={t('Project code')} hint={t("the project's name in the dashboard: lowercase letters, digits, - and _")}>
        <Input
          value={code}
          onChange={(e) => set('code')(e.currentTarget.value)}
          placeholder="my-app"
          aria-label={t('Project code')}
        />
        {code && !codeValid && (
          <p className="text-12 text-error mt-4">
            {t('Lowercase letters, digits, "-" and "_" only.')}
          </p>
        )}
      </Field>

      <Field
        label={t('Project folder')}
        hint={t('absolute path of the folder you start the agent in; the hooks work only there')}
      >
        <Input
          value={dir}
          onChange={(e) => set('dir')(e.currentTarget.value)}
          placeholder="/home/you/projects/my-app"
          aria-label={t('Project folder')}
          className="font-mono"
        />
      </Field>

      <Field
        label={t('Project notes')}
        hint={t('optional line added to the AGENTS.md section, such as a routine')}
      >
        <Input
          value={notes}
          onChange={(e) => set('notes')(e.currentTarget.value)}
          placeholder="run #scan before every commit"
          aria-label={t('Project notes')}
        />
      </Field>

      <p className="text-12 text-tertiary leading-relaxed max-w-reading">
        {t('Git is optional. In a repository, file entries get their line counts and diffs from git; without one, the agent counts them.')}
      </p>

      <fieldset className="flex flex-col gap-8">
        <legend className={`${LABEL} mb-4`}>
          {t('Files to write')}
        </legend>
        <Checkbox
          checked={writeAgents}
          onChange={set('writeAgents')}
          label={t('AGENTS.md: the Slightly Parallel section (read by Codex, OpenCode, Cursor and Gemini CLI)')}
        />
        <Checkbox
          checked={writeBridge}
          onChange={set('writeBridge')}
          label={t('CLAUDE.md: a line that points Claude Code to AGENTS.md')}
        />
        <Checkbox
          checked={writeHooks}
          onChange={set('writeHooks')}
          label={t('Claude Code hooks: record every chat (.claude/settings.local.json)')}
        />
        <Checkbox
          checked={writeOpencode}
          onChange={set('writeOpencode')}
          label={
            <>
              {t('OpenCode plugin: records OpenCode chats')}
              (<code>.opencode/plugin/slightly-parallel.js</code>){' '}
              <AdapterBadge verified={info.adapters.opencode_verified} />
            </>
          }
        />
        <Checkbox
          checked={writeCodex}
          onChange={set('writeCodex')}
          label={
            <>
              {t('Codex hooks: record Codex chats')}
              (<code>.codex/hooks.json</code>; {t('Codex must trust the folder')}){' '}
              <AdapterBadge verified={info.adapters.codex_verified} />
            </>
          }
        />
        <Checkbox
          checked={writeCursor}
          onChange={set('writeCursor')}
          label={
            <>
              {t('Cursor hooks: record Cursor chats')}
              (<code>.cursor/hooks.json</code>, <code>.cursor/mcp.json</code>){' '}
              <AdapterBadge verified={info.adapters.cursor_verified} />
            </>
          }
        />
      </fieldset>

      <div className="flex items-center gap-8">
        <Button
          variant="secondary"
          disabled={!ready || previewMut.isPending}
          onClick={() => previewMut.mutate(form)}
        >
          {t('Preview')}
        </Button>
        <Button
          variant="primary"
          disabled={!ready || applyMut.isPending}
          onClick={() => applyMut.mutate(form)}
        >
          {t('Integrate')}
        </Button>
        {(previewMut.error || applyMut.error) && (
          <span className="text-12 text-error">
            {String((previewMut.error ?? applyMut.error as Error).message)}
          </span>
        )}
      </div>

      {preview && <ResultPanel result={preview} title={t('Preview, nothing written yet')} />}
      {applied && <ResultPanel result={applied} title={t('Integrated')} success />}

      {info.integrations.length > 0 && (
        <div className="flex flex-col gap-4 pt-8 border-t border-border-subtle">
          <h3 className={LABEL}>
            {t('Integrated projects')}
          </h3>
          <ul className="flex flex-col gap-4">
            {info.integrations.map((it) => (
              <IntegrationRow
                key={`${it.project}:${it.path}`}
                it={it}
                // The example project is played, not worked in: no tool warnings on it.
                installed={it.project === info.example?.project ? undefined : info.tools_installed}
                onRefresh={() => reintegrate(it)}
                onConnect={(tool) => reintegrate(it, tool)}
                onIgnore={(tool) => void ignore(it.project, tool)}
                onDisconnect={() => setDisconnecting(it)}
                onDelete={() => setDeleting(it.project)}
              />
            ))}
          </ul>
        </div>
      )}

      {dataOnly.length > 0 && (
        <div className="flex flex-col gap-4 pt-8 border-t border-border-subtle">
          <h3 className={LABEL}>
            {t('Data without an integration')}
          </h3>
          <p className="text-12 text-tertiary">
            {t('Projects that have data but no integration: disconnected, imported, or test leftovers. They still show in the dashboard until the data is deleted.')}
          </p>
          <ul className="flex flex-col gap-4">
            {dataOnly.map((d) => (
              <li
                key={d.code}
                className="rounded-card border border-border-subtle bg-surface px-16 py-10 flex items-center gap-12"
              >
                <span className="font-mono text-13 text-primary">{d.code}</span>
                <span className="text-11 font-mono text-tertiary">
                  {tn(d.chats, '{n} chat', '{n} chats')} · {tn(d.rows, '{n} row', '{n} rows')}
                </span>
                <span className="ml-auto">
                  <Button variant="ghost" size="sm" onClick={() => setDeleting(d.code)}>
                    <Trash2 size={13} aria-hidden /> {t('Delete data…')}
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {disconnecting && (
        <ConfirmDialog
          title={t('Disconnect {project}', { project: disconnecting.project })}
          body={
            <>
              {rich(t("Stops recording this project. Removes it from this list, and removes the capture hooks, the OpenCode plugin, the `AGENTS.md` section and the `CLAUDE.md` line from {path}. The rest of the folder is untouched. The project's data is kept; Delete data removes it."), { path: <code className="break-all">{disconnecting.path}</code> })}
            </>
          }
          confirmLabel={t('Disconnect')}
          pending={disconnectMut.isPending}
          onConfirm={() => disconnectMut.mutate(disconnecting)}
          onClose={() => setDisconnecting(null)}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title={t('Delete all data for {project}', { project: deleting })}
          body={
            <>
              {t("Moves the project's chats and all its records (scans, decisions, tasks, time entries, …) into")} <code>.trash/</code>{' '}
              {t('in the data folder. To restore them, move the folder back. A sprint shared with other projects is kept, without this project.')}
            </>
          }
          confirmLabel={t('Delete data')}
          danger
          typeToConfirm={deleting}
          pending={deleteMut.isPending}
          onConfirm={() => deleteMut.mutate(deleting)}
          onClose={() => setDeleting(null)}
        />
      )}
    </StepCard>
  )
}
