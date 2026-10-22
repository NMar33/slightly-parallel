import { useMemo } from 'react'
import { DoorOpen } from 'lucide-react'
import { toast } from 'sonner'

import { fail } from '../../lib/getJson'
import { KeptBook, KeptSection, type BookCtx } from '../kept/Book'
import { LABEL } from '../promptlib/taskstyle'
import { jump } from '../visions/chapters'
import { cleanTitle, dateOf, useKept, useSetFields, type Vision } from '../visions/data'
import { ENTRYPOINTS_GUIDE } from '../visions/guides'
import { t } from '../../i18n/scope/system'

/**
 * Entry points — the way into a topic. One record per topic ("the install
 * film", "the launch"), kept from a #entrypoint message; the agent writes
 * its five sections: What, Where, How, State, Next. Open topics stay in a
 * strip under the header with their State line, so coming back to a
 * project starts from where the work stopped. The page is the kept book
 * (features/kept/Book) with those parts.
 */
export function EntryPointsBook({ project }: { project?: string } = {}) {
  const { visions: entries, loading, error, near, complete } = useKept('entrypoint')
  return (
    <KeptBook kind="entrypoint" title={t('Entry points')} icon={DoorOpen} guide={ENTRYPOINTS_GUIDE}
      entries={entries} loading={loading} error={error} near={near} complete={complete}
      empty={t('No entry points yet. Add #entrypoint to a message about a topic to keep one.')}
      modes={[['month', 'month'], ['project', 'project'], ['tag', 'tag']]} defaultMode="project"
      mark={(v) => isOpen(v) && <span role="img" className="h-6 w-6 rounded-pill bg-brand shrink-0 self-center" aria-label={t('open')} />}
      belowGuide={(shown) => <OpenTopics shown={shown} />}
      inProject={project} section={(v, ctx) => <EntrySection v={v} ctx={ctx} />} />
  )
}

export const isOpen = (v: Vision) => (v.row.status ?? 'open') !== 'closed'

/** The topic's title: the operator's `topic` field, else the message's first line. */
export const topicOf = (v: Vision) => (v.row.topic ?? '').trim() || cleanTitle(v.row.l1)

/** One section of the text, by its heading ("State", "Next"), as plain lines. */
export function sectionOf(text: string, name: string): string {
  const re = new RegExp(`^#{1,6}\\s*${name}\\b[^\\n]*\\n([\\s\\S]*?)(?=^#{1,6}\\s|\\Z)`, 'mi')
  const m = re.exec(text.replace(/\r/g, ''))
  if (!m) return ''
  return m[1].split('\n').map((l) => l.replace(/^\s*[-*]\s+/, '').trim()).filter(Boolean).join(' · ')
}

/** The open topics, the newest first, each with where its work stopped. */
function OpenTopics({ shown }: { shown: Vision[] }) {
  const open = useMemo(
    () => shown.filter(isOpen).sort((a, b) => dateOf(b.row).getTime() - dateOf(a.row).getTime()),
    [shown],
  )
  if (!open.length) return null
  return (
    <nav aria-label={t('Open topics')} className="rounded-card border border-brand/40 bg-brand/5 px-12 py-8 flex flex-col gap-6">
      <div className="flex items-center gap-8">
        <span className={`${LABEL} text-brand`}>{t('Open topics')}</span>
        <span className="text-11 font-mono text-tertiary tabular">{open.length}</span>
      </div>
      {open.map((v) => {
        const state = sectionOf(v.kept?.current?.text ?? v.l2 ?? '', 'State')
        return (
          <button key={v.row.id} type="button" onClick={() => jump(v.row.id)}
            className="flex items-baseline gap-8 text-left rounded-input px-6 py-2 hover:bg-surface">
            <span className="text-12 text-primary shrink-0">{topicOf(v)}</span>
            <span className="text-11 text-secondary truncate">{state || t('nothing written yet')}</span>
            <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{v.row.project}</span>
          </button>
        )
      })}
    </nav>
  )
}

function EntrySection({ v, ctx }: { v: Vision; ctx: BookCtx }) {
  const fields = useSetFields('entrypoint')
  const open = isOpen(v)
  const toggle = () => fields.mutate(
    { id: v.row.id, status: open ? 'closed' : 'open' },
    { onSuccess: () => toast.success(open ? t('Closed') : t('Reopened')), onError: fail },
  )
  return (
    <KeptSection v={v} kind="entrypoint" ctx={ctx} headline={topicOf(v)}
      status={
        <span className={`text-11 font-mono shrink-0 ${open ? 'text-brand' : 'text-tertiary'}`}>
          {open ? t('Open') : t('Closed')}
        </span>
      }
      actions={
        <button type="button" onClick={toggle} disabled={fields.isPending}
          className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand disabled:opacity-40">
          {open ? t('Close the topic') : t('Reopen')}
        </button>
      }
      wordsLabel={t('Your words')} />
  )
}
