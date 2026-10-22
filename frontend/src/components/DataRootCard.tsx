import { postJson } from '../lib/getJson'
import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button, Input } from './primitives'
import { t } from '../i18n/scope/shell'

/**
 * DataRootCard — the one piece of environment config editable from the UI.
 *
 * Posts to /api/setup/data-root: the server validates the path, persists
 * SCAN_DATA_ROOT to .env, and hot-swaps the running app — every open page
 * shows the new root after the query-cache invalidation below, no restart.
 * Shared by the Setup journey (step 1) and the Settings page.
 */
export function DataRootCard({
  current,
  bare = false,
}: {
  current: string
  /** Render without the card frame (embedded inside another card). */
  bare?: boolean
}) {
  const queryClient = useQueryClient()
  const [path, setPath] = useState(current)
  useEffect(() => setPath(current), [current])

  const change = useMutation({
    mutationFn: async () => {
      return postJson<{ data_root: string }>('/api/setup/data-root', { path: path.trim() })
    },
    onSuccess: (data) => {
      toast.success(t('Data folder changed to {path}', { path: data.data_root }))
      // Every view reads from the new root now.
      void queryClient.invalidateQueries()
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const changed = path.trim() !== '' && path.trim() !== current

  const body = (
    <>
      <p className="text-12 text-secondary leading-relaxed max-w-reading">
        {t('The folder that holds all recorded data: chats, scans, decisions and the other entries of every project. Choose any existing folder; the change applies at once, without a restart. Data in the old folder is not moved. Projects connected with the old path show as stale until you connect them again.')}
      </p>
      <div className="flex gap-8 items-center max-w-[640px]">
        <Input
          value={path}
          onChange={(e) => setPath(e.currentTarget.value)}
          placeholder="/absolute/path/to/data-folder"
          aria-label={t('Data root path')}
          className="font-mono flex-1 min-w-0"
        />
        <Button
          variant="secondary"
          disabled={!changed || change.isPending}
          onClick={() => change.mutate()}
        >
          {change.isPending ? t('Switching…') : t('Change')}
        </Button>
      </div>
      <code className="text-10 text-tertiary">
        SCAN_DATA_ROOT · saved in .env
      </code>
    </>
  )

  if (bare) return <div className="flex flex-col gap-12">{body}</div>
  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <h2 className="text-16 font-semibold text-primary">{t('Data folder')}</h2>
      {body}
    </section>
  )
}
