import { ChurnBar, Importance, Spark, Why } from './parts'
import { type Row, fileName, shortPath } from './rows'
import { projectColor } from '../../utils/projectColor'
import { t, tn } from '../../i18n/scope/system'

/**
 * The three readings of file activity that are not the grid: a ranking, the
 * agents' own sentences, and where the weight of the work fell. They take
 * rows and nothing else, so the project tab and the Files page draw the
 * identical thing from the identical data. On the Files page the rows span
 * every project, and each row carries its project as a coloured dot.
 */

/** The project a row is from, as its dot and code; nothing on the project tab. */
function ProjectMark({ row }: { row: Row }) {
  if (!row.project) return null
  return (
    <span className="inline-flex items-center gap-3 text-10 font-mono text-tertiary shrink-0" title={row.project}>
      <span className="h-6 w-6 rounded-pill" style={{ backgroundColor: projectColor(row.project) }} aria-hidden />
      {row.project}
    </span>
  )
}

/* ------------------------------------------------------------------ v02 */

export function Ranking({
  rows, entryIds, scale, open, onOpen,
}: {
  rows: Row[]
  entryIds: string[]
  scale: number
  open: string | null
  onOpen: (p: string | null) => void
}) {
  return (
    <div className="rounded-card border border-border-subtle bg-surface flex flex-col">
      {/* It is a table, so it says what its columns are. The widths below
          match the row exactly — change one and change the other. */}
      <div className="px-12 py-6 flex items-center gap-10 border-b border-border-default text-10 uppercase tracking-wide font-mono text-tertiary">
        <span className="w-[22px]">#</span>
        <span className="min-w-0 flex-1">{t('file · what the agent wrote last')}</span>
        <span className="w-[74px] text-center" title={t('Touches across the scans in this window, oldest on the left')}>
          {t('activity')}
        </span>
        <span className="w-[100px] text-center" title={t('Lines deleted to the left of the line, added to the right')}>
          {t('lines')}
        </span>
        <span className="w-[76px] text-right" title={t('The importance the agent gave its changes to this file')}>
          {t('importance')}
        </span>
        <span className="w-[132px] text-right">{t('touches · size')}</span>
      </div>
      {rows.map((r, i) => (
        <div key={r.key ?? r.path} className="border-b border-border-subtle last:border-b-0">
          <button
            type="button"
            onClick={() => onOpen(open === (r.key ?? r.path) ? null : (r.key ?? r.path))}
            aria-expanded={open === (r.key ?? r.path)}
            className="w-full px-12 py-8 flex items-center gap-10 text-left hover:bg-hover"
          >
            <span className="w-[22px] text-10 font-mono text-tertiary tabular">{i + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-6">
                <span className="text-13 text-primary truncate">{fileName(r.path)}</span>
                <span className="text-10 font-mono text-tertiary truncate" style={{ fontSize: 9 }}>{shortPath(r.path)}</span>
                <ProjectMark row={r} />
              </span>
              <span className="block text-11 text-tertiary truncate">{r.lastWhy || t('no note written')}</span>
            </span>
            <span className="w-[74px] shrink-0 flex justify-center"><Spark row={r} entries={entryIds} /></span>
            <span className="w-[100px] shrink-0"><ChurnBar add={r.lines_add} del={r.lines_del} scale={scale} /></span>
            <span className="w-[76px] shrink-0 flex justify-end"><Importance score={r.semantic_score} /></span>
            <span className="w-[132px] shrink-0 text-10 font-mono text-tertiary text-right">
              {r.total}× · {tn(r.breadth, '{n} scan', '{n} scans')}
              <span className="block">+{r.lines_add} −{r.lines_del}</span>
            </span>
          </button>
          {open === (r.key ?? r.path) && (
            <div className="px-12 pb-10 pl-[44px] flex flex-col gap-6">
              <Why row={r} limit={6} />
              {(r.tags ?? []).length > 0 && (
                <span className="flex items-center gap-4 flex-wrap">
                  {(r.tags ?? []).map((t) => (
                    <span key={t} className="h-16 px-6 rounded-pill border border-border-subtle text-10 font-mono text-tertiary" style={{ fontSize: 9 }}>{t}</span>
                  ))}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ v03 */

export function Story({ rows, scale }: { rows: Row[]; scale: number }) {
  return (
    <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))' }}>
      {rows.map((r) => (
        <article key={r.key ?? r.path} className="rounded-card border border-border-subtle bg-surface p-12 flex flex-col gap-8">
          <header className="flex items-baseline gap-6">
            <h2 className="text-13 text-primary truncate" title={r.path}>{fileName(r.path)}</h2>
            <span className="text-10 font-mono text-tertiary truncate" style={{ fontSize: 9 }}>{shortPath(r.path)}</span>
            <ProjectMark row={r} />
            <span className="ml-auto text-10 font-mono text-tertiary shrink-0">
              {r.breadth}× · +{r.lines_add} −{r.lines_del}
            </span>
          </header>
          <div className="flex items-center gap-10">
            <span className="flex-1"><ChurnBar add={r.lines_add} del={r.lines_del} scale={scale} /></span>
            <Importance score={r.semantic_score} width={54} />
          </div>
          <Why row={r} limit={4} />
          {(r.tags ?? []).length > 0 && (
            <footer className="flex items-center gap-4 flex-wrap">
              {(r.tags ?? []).map((t) => (
                <span key={t} className="h-16 px-6 rounded-pill border border-border-subtle text-10 font-mono text-tertiary" style={{ fontSize: 9 }}>{t}</span>
              ))}
            </footer>
          )}
        </article>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ v04 */

export function Weight({
  rows, open, onOpen, mode = 'lines',
}: {
  rows: Row[]
  open: string | null
  onOpen: (p: string | null) => void
  /** What the shade means: how recently it was touched, or how much the
      agent said the change mattered. Area is always lines changed. */
  mode?: 'lines' | 'importance'
}) {
  const total = Math.max(1, rows.reduce((a, r) => a + r.churn, 0))
  const topScore = Math.max(1, ...rows.map((r) => r.semantic_score ?? 0))
  const shadeOf = (r: Row) => (mode === 'importance' ? (r.semantic_score ?? 0) / topScore : r.recency)
  const picked = rows.find((r) => (r.key ?? r.path) === open) ?? null
  return (
    <div className="grid gap-14" style={{ gridTemplateColumns: picked ? 'minmax(0, 1fr) minmax(320px, 380px)' : '1fr' }}>
      <div className="rounded-card border border-border-subtle bg-surface p-12 flex flex-wrap gap-2 content-start" style={{ minHeight: 320 }}>
        {rows.map((r) => {
          const share = r.churn / total
          const side = Math.max(56, Math.round(Math.sqrt(share) * 460))
          return (
            <button
              key={r.key ?? r.path}
              type="button"
              onClick={() => onOpen(open === (r.key ?? r.path) ? null : (r.key ?? r.path))}
              aria-pressed={open === (r.key ?? r.path)}
              title={`${r.project ? `${r.project} · ` : ''}${r.path}\n+${r.lines_add} / −${r.lines_del} ${tn(r.breadth, 'over {n} scan', 'over {n} scans')} · ${t('importance {n}', { n: r.semantic_score ?? 0 })}${r.lastWhy ? `\n\n${r.lastWhy}` : ''}`}
              className={`rounded-input p-6 flex flex-col justify-between text-left overflow-hidden ${open === (r.key ?? r.path) ? 'outline outline-1 outline-brand' : ''}`}
              style={{
                width: side, height: side,
                backgroundColor: `color-mix(in oklab, var(--brand) ${Math.round(10 + shadeOf(r) * 60)}%, var(--bg-elevated))`,
              }}
            >
              <span className="text-10 font-mono leading-tight break-all" style={{ color: shadeOf(r) > 0.6 ? 'var(--bg-base)' : 'var(--text-secondary)' }}>
                {fileName(r.path)}
              </span>
              {side > 80 && (
                <span className="text-10 font-mono" style={{ fontSize: 9, color: shadeOf(r) > 0.6 ? 'var(--bg-base)' : 'var(--text-tertiary)' }}>
                  {mode === 'importance' ? t('{n} imp', { n: r.semantic_score ?? 0 }) : `+${r.lines_add} −${r.lines_del}`}
                </span>
              )}
            </button>
          )
        })}
      </div>
      {picked && (
        <aside className="rounded-card border border-border-subtle bg-surface p-14 flex flex-col gap-8 h-fit">
          <div className="flex items-baseline gap-6">
            <h2 className="text-14 text-primary break-all">{fileName(picked.path)}</h2>
            <button type="button" onClick={() => onOpen(null)} className="ml-auto text-11 font-mono text-tertiary hover:text-primary" aria-label={t('Close')}>×</button>
          </div>
          <p className="text-10 font-mono text-tertiary break-all">{picked.path}</p>
          <ProjectMark row={picked} />
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-10 font-mono text-tertiary">
            <span>{tn(picked.total, '{n} touch', '{n} touches')}</span>
            <span>{tn(picked.breadth, '{n} scan', '{n} scans')}</span>
            <span className="text-status-green">+{picked.lines_add}</span>
            <span className="text-status-red">−{picked.lines_del}</span>
            <span>{tn(picked.days, '{n} day', '{n} days')}</span>
            <span>{t('{n} importance', { n: picked.semantic_score ?? 0 })}</span>
          </div>
          <Why row={picked} limit={6} />
        </aside>
      )}
      <p className="text-10 font-mono text-tertiary">
        {t('area = lines changed · shade =')} {mode === 'importance' ? t('how much the agent said it mattered') : t('how recently')} · {t('click a file for what the agents said about it')}
      </p>
    </div>
  )
}
