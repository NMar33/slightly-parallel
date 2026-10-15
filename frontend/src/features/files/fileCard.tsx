import { CopyButton } from '../../components/CopyButton'
import { absolutePath, useProjectFolder } from '../../lib/paths'
import { Link } from 'react-router-dom'

import { type Dossier } from './fleet'
import { fileName, shortPath } from './rows'
import { Importance } from './parts'
import { locale, t, tn } from '../../i18n/scope/system'

/**
 * What one file's ledger says, in one place.
 *
 * Ordered by what it can tell you that nothing else can. The sentences the
 * agents wrote come first — they are the only account of *why* this file is
 * the way it is. Then the files it travels with, which is coupling measured
 * from behaviour rather than read off imports: a file that appears in eight
 * of eight checkpoints alongside this one has never changed alone, and that
 * is a stronger claim about the architecture than any diagram.
 *
 * The panel says what it does not have, too. There is no diff here and no
 * file contents — only what agents recorded when they recorded it.
 */

export function FileCard({
  d, highlight, onClose, dense,
}: {
  d: Dossier
  /** The checkpoint you arrived from, marked in the story. */
  highlight?: string
  onClose?: () => void
  dense?: boolean
}) {
  const full = absolutePath(useProjectFolder(d.project), d.path)
  return (
    <div className="flex flex-col gap-10">
      <header className="flex items-baseline gap-8 flex-wrap">
        <h2 className="text-14 text-primary">{fileName(d.path)}</h2>
        <span className="text-10 font-mono text-tertiary break-all inline-flex items-start gap-3" title={full}>
          {d.path}
          <CopyButton text={full} title={t('Copy path')} size={10} />
        </span>
        {onClose && (
          <button type="button" onClick={onClose} className="ml-auto text-12 font-mono text-tertiary hover:text-primary" aria-label={t('Close')}>×</button>
        )}
      </header>

      <div className="flex items-center gap-10 flex-wrap text-10 font-mono text-tertiary">
        <span>{d.project}</span>
        <span>{d.touches}× {tn(d.checkpoints, 'over {n} scan', 'over {n} scans')}</span>
        <span className="text-status-green">+{d.add.toLocaleString(locale())}</span>
        <span className="text-status-red">−{d.del.toLocaleString(locale())}</span>
        <Importance score={d.score} />
        <span>{d.first} → {d.last}</span>
        {d.rankChurn > 0 && <span>{t('#{n} of {of} by lines changed in {project}', { n: d.rankChurn, of: d.rankOf, project: d.project })}</span>}
        {d.tags.map((t) => (
          <span key={t} className="h-16 px-6 rounded-pill border border-border-subtle" style={{ fontSize: 9 }}>{t}</span>
        ))}
      </div>

      {d.travels.length > 0 && (
        <section className="flex flex-col gap-3">
          <h3 className="text-10 uppercase tracking-wide font-mono text-tertiary">
            {t('changed together')}
            <span className="normal-case tracking-normal text-tertiary/70"> — {t('how often these changed in the same scan')}</span>
          </h3>
          {d.travels.map((t) => (
            <div key={t.path} className="flex items-center gap-8">
              <span className="text-11 text-secondary truncate flex-1" title={t.path}>{shortPath(t.path)}</span>
              <span className="w-[70px] rounded-pill bg-elevated overflow-hidden" style={{ height: 4 }}>
                <span className="block h-full rounded-pill" style={{ width: `${(t.n / t.of) * 100}%`, backgroundColor: t.n === t.of ? 'var(--status-amber)' : 'var(--brand)', opacity: 0.85 }} />
              </span>
              <span className="w-[46px] text-right text-10 font-mono text-tertiary tabular">{t.n}/{t.of}</span>
            </div>
          ))}
          {d.travels[0]?.n === d.travels[0]?.of && (
            <span className="text-10 font-mono text-status-amber">{t('always changes with another file')}</span>
          )}
        </section>
      )}

      <section className="flex flex-col gap-4">
        <h3 className="text-10 uppercase tracking-wide font-mono text-tertiary">
          {t('notes')}
          <span className="normal-case tracking-normal text-tertiary/70"> — {t('newest first')}</span>
        </h3>
        {d.story.filter((s) => s.why).length === 0 && (
          <span className="text-11 text-tertiary italic">{t('No notes for this file.')}</span>
        )}
        {d.story.slice(0, dense ? 4 : 99).map((s) => (
          <div
            key={s.entryId}
            className={`flex flex-col gap-1 pl-10 border-l-2 ${highlight === s.entryId ? '' : 'border-border-subtle'}`}
            style={highlight === s.entryId ? { borderColor: 'var(--brand)' } : undefined}
          >
            <span className="flex items-baseline gap-6 flex-wrap">
              <span className="text-10 font-mono text-tertiary" style={{ fontSize: 9 }}>{s.date} {s.time}</span>
              <span className="text-10 font-mono text-tertiary" style={{ fontSize: 9 }}>{s.agent}</span>
              <span className="text-10 font-mono" style={{ fontSize: 9 }}>
                <span className="text-status-green">+{s.add}</span> <span className="text-status-red">−{s.del}</span>
              </span>
              <span className="text-10 font-mono text-tertiary" style={{ fontSize: 9 }}>{s.action ? t(s.action) : ''}</span>
              {highlight === s.entryId && <span className="text-10 font-mono text-brand" style={{ fontSize: 9 }}>{t('the one you clicked')}</span>}
            </span>
            {s.why && <span className="text-12 text-secondary leading-snug">{s.why}</span>}
            <span className="text-10 font-mono text-tertiary/70" style={{ fontSize: 9 }}>{t('in “{what}”', { what: s.l1.replace(/^\d+ files · /, '') })}</span>
          </div>
        ))}
      </section>

      <section className="flex items-center gap-8 flex-wrap text-10 font-mono text-tertiary">
        <span className="uppercase tracking-wide">{t('touched by')}</span>
        {d.agents.map((a) => (
          <Link key={a.agent} to={`/agent/${a.agent}`} className="hover:text-brand">
            {a.agent}<span className="text-tertiary/70"> ×{a.n}</span>
          </Link>
        ))}
      </section>

      <footer className="flex items-center gap-8 flex-wrap text-10 font-mono text-tertiary" style={{ fontSize: 9 }}>
        <Link to={`/project/${d.project}#files`} className="hover:text-brand">{t('the project’s files →')}</Link>
        <span className="text-tertiary/70">
          {t('What the agents recorded at the time. No diff or file contents.')}
        </span>
      </footer>
    </div>
  )
}
