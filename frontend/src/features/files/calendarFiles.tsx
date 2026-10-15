import { useState, type ReactNode } from 'react'

import { Modal } from '../../components/Modal'
import { type Data, headline } from './calendars'
import { FileCard } from './fileCard'
import { type FleetEntry, fileDossier, pathsOf } from './fleet'
import { shortPath } from './rows'
import { Importance } from './parts'
import { locale, t, tn } from '../../i18n/scope/system'

/**
 * The days list with the files made answerable: click a path and the ledger
 * tells you everything it has about it, in a reading modal.
 */

type Tone = (project: string) => string

export function CalendarFiles({ data, toneOf }: { data: Data; toneOf: Tone }) {
  const [openEntry, setOpenEntry] = useState<string | null>(null)
  const [file, setFile] = useState<{ path: string; entryId: string } | null>(null)

  const days = (() => {
    const map = new Map<string, FleetEntry[]>()
    for (const e of data.entries) {
      const list = map.get(e.date) ?? []
      list.push(e)
      map.set(e.date, list)
    }
    for (const l of map.values()) l.sort((a, b) => a.time.localeCompare(b.time))
    return [...map.entries()].sort(([a], [b]) => (a < b ? 1 : -1))
  })()
  const peak = Math.max(1, ...days.map(([, es]) => es.reduce((a, e) => a + e.paths_n, 0)))
  const dossier = file ? fileDossier(data, file.path) : null

  const feed = (
    <div className="flex flex-col gap-8">
      {days.map(([date, es]) => {
        const paths = es.reduce((a, e) => a + e.paths_n, 0)
        const lines = es.reduce((a, e) => a + pathsOf(data, e.id).reduce((x, p) => x + p.add + p.del, 0), 0)
        return (
          <div key={date} className="rounded-card border border-border-subtle bg-surface px-14 py-10 flex flex-col gap-6">
            <div className="flex items-baseline gap-10">
              <span className="text-13 font-semibold text-primary">{date}</span>
              <span className="text-10 font-mono text-tertiary">
                {tn(es.length, '{n} scan', '{n} scans')} · {tn(paths, '{n} file', '{n} files')} · {tn(lines, '{n} line', '{n} lines', { n: lines.toLocaleString(locale()) })}
              </span>
              <span className="ml-auto flex-1 max-w-[380px] flex items-center gap-2" aria-hidden>
                {es.map((e) => (
                  <span
                    key={e.id}
                    className="rounded-pill"
                    style={{ height: 8, width: `${Math.max(4, (e.paths_n / peak) * 100)}%`, backgroundColor: 'color-mix(in oklab, var(--brand) 55%, var(--bg-elevated))' }}
                    title={`${e.project} · ${tn(e.paths_n, '{n} file', '{n} files')}`}
                  />
                ))}
              </span>
            </div>

            <div className="flex flex-col gap-2">
              {es.map((e) => (
                <div key={e.id} className="flex flex-col gap-3">
                  <button
                    type="button"
                    onClick={() => setOpenEntry(openEntry === e.id ? null : e.id)}
                    aria-expanded={openEntry === e.id}
                    className="flex items-baseline gap-6 text-left hover:bg-hover rounded-input px-6 py-2"
                  >
                    <span className="h-6 w-6 rounded-pill shrink-0" style={{ backgroundColor: toneOf(e.project) }} aria-hidden />
                    <span className="text-10 font-mono text-tertiary shrink-0" style={{ fontSize: 9 }}>{e.time}</span>
                    <span className="text-12 text-secondary truncate">{headline(e)}</span>
                    <span className="ml-auto text-10 font-mono text-tertiary shrink-0" style={{ fontSize: 9 }}>
                      {e.project} · {e.paths_n}
                    </span>
                  </button>

                  {openEntry === e.id && (
                    <div className="pl-12 flex flex-col gap-3 border-l border-border-subtle">
                      {pathsOf(data, e.id).map((p) => {
                        const on = file?.path === p.path && file.entryId === e.id
                        return (
                          <div key={p.path} className="flex flex-col gap-1">
                            <button
                              type="button"
                              onClick={() => setFile(on ? null : { path: p.path, entryId: e.id })}
                              aria-pressed={on}
                              title={t('Everything recorded about this file')}
                              className={`flex items-baseline gap-6 text-left rounded-input px-4 py-1 ${on ? 'bg-elevated' : 'hover:bg-hover'}`}
                            >
                              <span className={`text-11 ${on ? 'text-primary' : 'text-secondary'}`}>{shortPath(p.path)}</span>
                              <span className="text-10 font-mono" style={{ fontSize: 9 }}>
                                <span className="text-status-green">+{p.add}</span> <span className="text-status-red">−{p.del}</span>
                              </span>
                              <Importance score={p.score} width={26} />
                            </button>
                            {p.why && <span className="text-10 text-tertiary leading-snug pl-4">{p.why}</span>}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )

  return (
    <>
      {feed}
      {dossier && (
        <FileModal path={file?.path ?? ''} onClose={() => setFile(null)}>
          <FileCard d={dossier} highlight={file?.entryId} onClose={() => setFile(null)} />
        </FileModal>
      )}
    </>
  )
}

/** The reading modal: Escape closes, focus stays inside while it is open. */
function FileModal({ path, onClose, children }: { path: string; onClose: () => void; children: ReactNode }) {
  return (
    <Modal label={t('About {path}', { path })} onClose={onClose} width="w-[720px]">
      {children}
    </Modal>
  )
}
