import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, PlugZap } from 'lucide-react'

import { DataRootCard } from '../components/DataRootCard'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import { api, qk } from '../lib/api'
import { PageHeader } from '../components/PageHeader'
import { CodexCard } from '../features/setup/CodexCard'
import { IntegrateStep } from '../features/setup/IntegrateStep'
import { SETUP_INFO_KEY, useSetupInfo } from '../features/setup/data'
import { CopyCommand, DetectedRow, StepCard } from '../features/setup/parts'
import { rich } from '../i18n/rich'
import { t } from '../i18n/scope/pages'

/**
 * SetupPage — the entry point. Everything a fresh clone needs to go from
 * the example project to an observed fleet lives on this page, as a numbered journey:
 *
 *   1. choose the data root (inline editor, hot-swaps live)
 *   2. integrate projects (server writes the AGENTS.md block; previews,
 *      tracks freshness)
 *   3. start an agent — nothing to configure on the agent side
 *   4. optionally enable the embedded terminal (shell-only, by design)
 *   5. optionally run it supervised (sp.sh — auto-restart)
 */
export default function SetupPage() {
  useEffect(() => {
    document.title = `${t('Setup')} — Slightly Parallel`
  }, [])

  const queryClient = useQueryClient()
  const info = useSetupInfo()
  const snapshot = useQuery({
    queryKey: qk.snapshot(),
    queryFn: ({ signal }) => api.snapshot(signal),
  })
  const terminalEnabled = snapshot.data?.capabilities?.terminal_enabled ?? false

  return (
    <div className="flex flex-col gap-24 min-w-0">
      <PageHeader
        icon={PlugZap}
        title={t('Setup')}
        tagline={t('Choose where the records are kept, then integrate the projects you want recorded.')}
      />

      {info.isLoading && !info.data && <LoadingSkeleton variant="card" count={2} />}
      {info.isError && (
        <ErrorBanner
          title={t('Could not load setup info')}
          onRetry={() => void info.refetch()}
          hideDismiss
        />
      )}

      {info.data && (
        <>
          <section className="rounded-card border border-border-subtle bg-surface p-16 text-12 font-mono text-secondary flex flex-col gap-4">
            <DetectedRow label={t('Slightly Parallel folder')} value={info.data.app_root} />
            <DetectedRow
              label={t('Contract')}
              value={info.data.contract_path}
              warn={!info.data.contract_exists ? t('file missing') : undefined}
            />
            <DetectedRow label="API" value={info.data.api_url} />
            <DetectedRow label={t('Data folder')} value={info.data.data_root} />
          </section>

          <StepCard
            n={1}
            title={t('Choose where Slightly Parallel keeps its records')}
            done
          >
            {info.data.example.present && (
              <p className="text-13 text-secondary leading-relaxed max-w-reading">
                {rich(t('The folder holds the **example project** {project}: a month of work, to see how each page fills. Hide it from the sidebar, or in Settings › Example project.', { project: info.data.example.project }))}
              </p>
            )}
            <DataRootCard current={info.data.data_root} bare />
          </StepCard>

          <IntegrateStep info={info.data} />

          <CodexCard
            status={info.data.codex}
            verified={info.data.adapters.codex_verified}
            onChanged={() =>
              void queryClient.invalidateQueries({ queryKey: SETUP_INFO_KEY })
            }
          />

          <StepCard n={3} title={t('Start an agent')}>
            <p className="text-13 text-secondary leading-relaxed flex items-start gap-8 max-w-reading">
              <CircleAlert size={15} className="text-status-amber shrink-0 mt-2" aria-hidden />
              <span>{rich(t('Open a **new** agent session. Coding tools read their hook configuration when a session starts, so capture begins with the next session you open.'))}</span>
            </p>
            <p className="text-13 text-secondary leading-relaxed max-w-reading">
              {rich(t('Nothing to configure on the agent side. In an integrated project the hooks record every message as written, and the agent reads `AGENTS.md` to learn how to write entries:'))}
            </p>
            <ul className="text-13 text-secondary leading-relaxed list-disc pl-20 flex flex-col gap-2">
              <li>{rich(t('Start it **in the integrated folder**. Its first answer includes `[slightly-parallel] project … · your agent_id is …`, which shows capture is on. If the line is missing, the agent was started outside the integrated folder or in a subfolder of it.'))}</li>
              <li>{t('Chats and hours are counted from the recorded messages, at no cost in tokens.')}</li>
              <li>{rich(t('The agent posts a **scan** when you type `#scan`, offers a **standup** when a new day starts, and logs **decisions** as they happen.'))}</li>
              <li>{rich(t('It writes decisions, problems, architecture and the rest through the Slightly Parallel MCP tools. The Guide shows each page\'s **agent prompt**: the exact text the agent receives.'))}</li>
            </ul>
            <p className="text-13 text-tertiary">
              {t('The full contract:')}{' '}
              <Link to="/guide" className="text-brand hover:underline">
                {t('Guide')}
              </Link>
              {', '}<code>SLIGHTLY-PARALLEL.md</code>{' '}{t('at the repository root.')}
            </p>
          </StepCard>

          <StepCard
            n={4}
            title={t('Optional: enable the embedded terminal')}
            done={terminalEnabled ? true : undefined}
            badge={terminalEnabled ? t('enabled') : t('disabled')}
          >
            <p className="text-13 text-secondary leading-relaxed max-w-reading">
              {t("Terminals are real shells on this computer, opened in each project's folder: the ` key on any page, Resume and Start an agent. They run commands on your machine, so they stay off until you switch them on, in Settings › Terminal or from your shell:")}
            </p>
            <div className="flex flex-col gap-4">
              <CopyCommand cmd={`cd "${info.data.app_root}"`} note={t('run once per shell')} />
              <CopyCommand cmd="./sp.sh terminal on" note={t('switches it on in the running server')} />
              <CopyCommand cmd="./sp.sh terminal off" />
            </div>
            <p className="text-13 text-tertiary">
              {rich(t('There is no token to paste: the server hands it only to its own pages. `SP_ENABLE_TERMINAL=1` in `.env` keeps the terminal on whatever the setting says.'))}
            </p>
          </StepCard>

          <StepCard n={5} title={t('Optional: keep it running')}>
            <p className="text-13 text-secondary leading-relaxed max-w-reading">
              {rich(t('`./run.sh` runs in the foreground and stops when its terminal closes. `./sp.sh` runs the servers in the background and restarts them within seconds if they crash.'))}
            </p>
            <div className="flex flex-col gap-4">
              <CopyCommand cmd={`cd "${info.data.app_root}"`} note={t('run once per shell')} />
              <CopyCommand cmd="./sp.sh up" note={t('in the background; the app on :8123')} />
              <CopyCommand cmd="./sp.sh up --dev" note={t('the same, with the development servers (hot reload)')} />
              <CopyCommand cmd="./sp.sh status" note={t('supervisor, health and terminal state')} />
              <CopyCommand cmd="./sp.sh logs" note={t('follow the server log')} />
              <CopyCommand cmd="./sp.sh restart" />
              <CopyCommand cmd="./sp.sh down" note={t('stop everything')} />
            </div>
            <p className="text-13 text-tertiary">
              {rich(t('State and the log are kept in `.sp/` in the Slightly Parallel folder, ignored by git.'))}
            </p>
          </StepCard>
        </>
      )}
    </div>
  )
}
