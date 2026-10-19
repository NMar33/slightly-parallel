import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, SlidersHorizontal } from 'lucide-react'
import { toast } from 'sonner'

import { DataRootCard } from '../components/DataRootCard'
import { WithContents } from '../components/WithContents'
import { AppearanceCard } from '../features/settings/AppearanceCard'
import { SidebarCard } from '../features/settings/SidebarCard'
import { PromptsCard } from '../features/settings/PromptsCard'
import { ComputerCard } from '../features/setup/Computer'
import { Button, Input } from '../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import {
  SETTINGS_QUERY_KEY,
  fetchSettings,
  saveSettings,
  type SettingSpec,
} from '../lib/settings'
import { PageHeader } from '../components/PageHeader'
import { LanguagePicker } from '../components/LanguagePicker'
import { t } from '../i18n/scope/pages'

/**
 * SettingsPage — every tunable in the system, rendered generically from the
 * server's schema. Adding a setting on the backend makes it appear here
 * with its label, description, bounds, and default; no frontend change.
 */
export default function SettingsPage() {
  useEffect(() => {
    document.title = `${t('Settings')} — Slightly Parallel`
  }, [])

  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchSettings(signal),
  })

  // Draft edits keyed by setting key; empty = no unsaved changes.
  const [draft, setDraft] = useState<Record<string, number | boolean | string>>({})

  const specs = useMemo(
    () => (query.data ? query.data.groups.flatMap((g) => g.settings) : []),
    [query.data],
  )
  const dirty = Object.keys(draft).filter(
    (k) => draft[k] !== specs.find((s) => s.key === k)?.value,
  )

  const save = useMutation({
    mutationFn: () =>
      saveSettings(Object.fromEntries(dirty.map((k) => [k, draft[k]]))),
    onSuccess: () => {
      setDraft({})
      void queryClient.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
      toast.success(t('Settings saved.'))
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const valueOf = (s: SettingSpec) => draft[s.key] ?? s.value

  return (
    <div className="flex flex-col gap-24 min-w-0">
      <PageHeader
        icon={SlidersHorizontal}
        title={t('Settings')}
        tagline={t('The numbered settings are saved when you click Save. The cards below them apply at once.')}
      />

      {query.isLoading && !query.data && <LoadingSkeleton variant="card" count={2} />}
      {query.isError && (
        <ErrorBanner
          title={t('Could not load settings')}
          onRetry={() => void query.refetch()}
          hideDismiss
        />
      )}

      {query.data && (
        <WithContents
          label={t('On this page')}
          items={[
            { id: 'language', text: t('Language') },
            { id: 'computer', text: t('On this computer') },
            ...query.data.groups.map((g) => ({
              id: groupAnchor(g.name),
              text: t(g.name),
              note: String(g.settings.length),
            })),
            { id: 'appearance', text: t('Appearance') },
            { id: 'sidebar', text: t('Sidebar') },
            { id: 'prompts', text: t('Agent prompts') },
            { id: 'data-root', text: t('Data folder') },
            { id: 'environment', text: t('Environment') },
          ]}
        >
          <section id="language" className="rounded-card border border-border-subtle bg-surface p-24 flex items-center justify-between gap-16 flex-wrap scroll-mt-16">
            <div className="flex flex-col gap-2">
              <h2 className="text-16 font-semibold text-primary">{t('Language')}</h2>
              <p className="text-12 text-tertiary">{t('The page reloads in the language you pick.')}</p>
            </div>
            <LanguagePicker />
          </section>
          <div id="computer" className="scroll-mt-16"><ComputerCard /></div>
          {query.data.groups.map((group) => (
            <section
              key={group.name}
              id={groupAnchor(group.name)}
              className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-16 scroll-mt-16"
            >
              <h2 className="text-16 font-semibold text-primary">{t(group.name)}</h2>
              {group.settings.map((s) => (
                <SettingRow
                  key={s.key}
                  spec={s}
                  value={valueOf(s)}
                  onChange={(v) => setDraft((d) => ({ ...d, [s.key]: v }))}
                />
              ))}
            </section>
          ))}

          <div id="appearance" className="scroll-mt-16"><AppearanceCard /></div>

          <div id="sidebar" className="scroll-mt-16"><SidebarCard /></div>

          <div id="prompts" className="scroll-mt-16"><PromptsCard /></div>

          <div id="data-root" className="scroll-mt-16">
            <DataRootCard current={dataRootValue(query.data.environment)} />
          </div>

          <section id="environment" className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-8 scroll-mt-16">
            <h2 className="text-16 font-semibold text-primary">
              {t('Environment')}{' '}
              <span className="text-11 font-normal text-tertiary">
                {t('read-only · set in .env, restart to apply')}
              </span>
            </h2>
            {query.data.environment
              .filter((e) => e.key !== 'SCAN_DATA_ROOT')
              .map((e) => (
                <div key={e.key} className="flex gap-12 text-12 min-w-0 items-baseline">
                  <span className="text-tertiary w-[140px] shrink-0">{t(e.label)}</span>
                  <span className="font-mono text-secondary truncate" title={e.value}>
                    {e.value}
                  </span>
                  <code className="ml-auto text-10 text-tertiary shrink-0">{e.key}</code>
                </div>
              ))}
          </section>

          <div className="flex items-center gap-8 sticky bottom-0 bg-base py-12 border-t border-border-subtle">
            <Button
              variant="primary"
              disabled={dirty.length === 0 || save.isPending}
              onClick={() => save.mutate()}
            >
              {t('Save')}{dirty.length > 0 ? ` (${dirty.length})` : ''}
            </Button>
            <Button
              variant="ghost"
              disabled={dirty.length === 0}
              onClick={() => setDraft({})}
            >
              {t('Discard changes')}
            </Button>
            <span className="ml-auto text-11 font-mono text-tertiary truncate">
              {query.data.file}
            </span>
          </div>
        </WithContents>
      )}
    </div>
  )
}

/** A unit after a number: its own dictionary entry ("unit:tasks"), since the
 *  same English word as a heading takes another Russian form. */
function unitText(unit: string): string {
  const key = `unit:${unit}`
  const text = t(key)
  return text === key ? unit : text
}

/** A group's heading is its anchor: "Agent signals" → "agent-signals". */
function groupAnchor(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

function SettingRow({
  spec,
  value,
  onChange,
}: {
  spec: SettingSpec
  value: number | boolean | string
  onChange: (v: number | boolean | string) => void
}) {
  const isDefault = value === spec.default
  return (
    <div className="flex gap-16 items-start">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-8">
          <span className="text-13 font-medium text-primary">{t(spec.label)}</span>
          <code className="text-10 text-tertiary">{spec.key}</code>
          {!isDefault && (
            <button
              type="button"
              className="inline-flex items-center gap-4 text-11 text-brand hover:underline"
              onClick={() => onChange(spec.default)}
              title={t('Reset to default ({value})', { value: String(spec.default) })}
            >
              <RotateCcw size={11} aria-hidden /> {t('default: {value}', { value: String(spec.default) })}
            </button>
          )}
        </div>
        <p className="text-12 text-tertiary leading-relaxed mt-2 max-w-reading">
          {t(spec.description)}
        </p>
      </div>
      <div className="shrink-0 w-[140px] flex items-center justify-end gap-8">
        {spec.type === 'choice' && spec.free ? (
          <>
            <Input
              type="text"
              list={`opts-${spec.key}`}
              value={String(value)}
              onChange={(e) => onChange(e.currentTarget.value.trim())}
              aria-label={t(spec.label)}
              title={t('Pick one, or type a model name')}
              className="font-mono"
            />
            <datalist id={`opts-${spec.key}`}>
              {spec.options.map((o) => <option key={o} value={o} />)}
            </datalist>
          </>
        ) : spec.type === 'choice' ? (
          <select
            value={String(value)}
            onChange={(e) => onChange(e.currentTarget.value)}
            aria-label={t(spec.label)}
            className="h-32 px-8 rounded-input border border-border-default bg-surface text-13 text-primary font-mono"
          >
            {spec.options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : spec.type === 'text' ? (
          <Input
            type="text"
            value={String(value)}
            onChange={(e) => onChange(e.currentTarget.value)}
            aria-label={t(spec.label)}
            className="font-mono"
          />
        ) : spec.type === 'bool' ? (
          <label className="inline-flex items-center gap-8 cursor-pointer text-13 text-secondary">
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => onChange(e.currentTarget.checked)}
              className="accent-[var(--brand)]"
              aria-label={t(spec.label)}
            />
            {value ? t('on') : t('off')}
          </label>
        ) : (
          <>
            <Input
              type="number"
              value={String(value)}
              min={spec.minimum ?? undefined}
              max={spec.maximum ?? undefined}
              onChange={(e) => {
                const n = Number(e.currentTarget.value)
                if (Number.isFinite(n)) onChange(Math.trunc(n))
              }}
              aria-label={t(spec.label)}
              className="text-right font-mono"
            />
            {spec.unit && (
              <span className="text-11 text-tertiary w-[36px]">{unitText(spec.unit)}</span>
            )}
          </>
        )}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Data folder — rendered by the shared DataRootCard (also used on Setup).
 * ------------------------------------------------------------------------- */

function dataRootValue(
  environment: Array<{ key: string; value: string }>,
): string {
  return environment.find((e) => e.key === 'SCAN_DATA_ROOT')?.value ?? ''
}
