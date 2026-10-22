/*
 * This computer: start Slightly Parallel at login, and a shortcut that opens
 * it (backend/autostart.py, `sp autostart`, `sp shortcut`). Offered in the
 * Integrate step, switched in Settings › On this computer.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Laptop } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '../../components/primitives'
import { postJson } from '../../lib/getJson'
import { LABEL } from '../promptlib/taskstyle'
import { SETUP_INFO_KEY, useSetupInfo, type ComputerState } from './data'
import { Checkbox } from './parts'
import { t } from '../../i18n/scope/system'

const SHORTCUT_LABEL: Record<ComputerState['system'], string> = {
  linux: 'A shortcut in the applications menu and on the desktop',
  mac: 'A shortcut on the desktop',
  windows: 'A shortcut on the desktop and in the Start menu',
}

/** Why, what it costs, and where to turn it off: the same words in both places. */
function Why({ settings }: { settings: boolean }) {
  return (
    <div className="flex flex-col gap-4 text-12 text-tertiary leading-relaxed max-w-reading">
      <p>{t('Agents write through the server: #scan, #task, the standup, decisions. While it is not running those writes fail; the hooks still record the chats.')}</p>
      <p>{t('Starting at login runs the server in the background, with no window. The shortcut opens this page, and starts the server first when it is not running.')}</p>
      <p>{t('Load: about 300 MB of memory while in use; the processor stays almost idle (under 0.1 %).')}</p>
      {!settings && <p>{t('Turn them off in Settings › On this computer.')}</p>}
    </div>
  )
}

/** In the Integrate step: two boxes, clear by default, applied by Integrate. */
export function IntegrateComputer({ state, autostart, shortcut, onAutostart, onShortcut }: {
  state?: ComputerState
  autostart: boolean
  shortcut: boolean
  onAutostart: (v: boolean) => void
  onShortcut: (v: boolean) => void
}) {
  if (!state || state.sandbox) return null
  return (
    <fieldset className="flex flex-col gap-8">
      <legend className={`${LABEL} mb-4`}>{t('On this computer')}</legend>
      <Checkbox
        checked={state.autostart.on || autostart}
        disabled={state.autostart.on}
        onChange={onAutostart}
        label={<>{t('Start Slightly Parallel when you log in')} {state.autostart.on
          ? <Badge tone="done">{t('on')}</Badge>
          : <span className="text-tertiary">({t('recommended')})</span>}</>}
      />
      <Checkbox
        checked={state.shortcut.on || shortcut}
        disabled={state.shortcut.on}
        onChange={onShortcut}
        label={<>{t(SHORTCUT_LABEL[state.system])} {state.shortcut.on && <Badge tone="done">{t('on')}</Badge>}</>}
      />
      <Why settings={false} />
    </fieldset>
  )
}

/** Settings › On this computer: each switch applies at once. */
export function ComputerCard() {
  const info = useSetupInfo()
  const queryClient = useQueryClient()
  const state = info.data?.computer
  const flip = useMutation({
    mutationFn: (body: Partial<Record<'autostart' | 'shortcut', boolean>>) =>
      postJson<{ computer: ComputerState }>('/api/setup/computer', body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: SETUP_INFO_KEY }),
    onError: (e: Error) => toast.error(e.message),
  })
  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <h2 className="text-16 font-semibold text-primary inline-flex items-center gap-6">
        <Laptop size={16} className="text-brand" aria-hidden /> {t('On this computer')}
      </h2>
      {!state ? null : state.sandbox ? (
        <p className="text-12 text-tertiary">{t('A test server does not change this computer.')}</p>
      ) : (
        <>
          {([
            ['autostart', t('Start Slightly Parallel when you log in')],
            ['shortcut', t(SHORTCUT_LABEL[state.system])],
          ] as const).map(([kind, label]) => (
            <div key={kind} className="flex flex-col gap-2">
              <Checkbox
                checked={state[kind].on}
                disabled={flip.isPending}
                onChange={(v) => flip.mutate({ [kind]: v })}
                label={label}
              />
              {state[kind].on && state[kind].paths.map((p) => (
                <span key={p} className="pl-20 text-11 font-mono text-tertiary break-all">{p}</span>
              ))}
            </div>
          ))}
          <Why settings />
        </>
      )}
    </section>
  )
}
