/**
 * The overview's two levels. Level 1, the current workspace: its chats as
 * still text tiles (each terminal's screen, read every few seconds and
 * only while this level shows), the sleeping chats as a row, the servers
 * as a row. Level 2, every workspace: a pool each with its counts,
 * sleeping ones dimmed, waiting chats with an amber edge.
 */

import { ExternalLink, Menu, Moon, Sun } from 'lucide-react'

import { isAsleep, isLive, roleOf, shownOf, tilesOf, waitingIn, type AquaSession, type Workspace } from './model'
import { Dot, SHOWN_WORD, Swatch, Tile, lane } from './parts'
import { t, tn } from '../../../i18n/scope/aqua'

export const TILE_H = 168
export const GAP = 10
export const PAD = 12
/** The level's own header row above the tiles. */
export const HEAD = 26

export function WsLevel({ ws, current, on, cols, onChat, onWake, onSleepWs, onDetach, onMenu, canSleep }: {
  ws: Workspace | undefined; current: string; on: boolean; cols: number
  onChat: (id: string) => void; onWake: (id: string) => void; onSleepWs: (asleep: boolean) => void
  onDetach: () => void; onMenu?: () => void; canSleep: boolean
}) {
  if (!ws) return null
  const tiles = tilesOf(ws)
  const sleeping = ws.sessions.filter((s) => isAsleep(s) && roleOf(s) !== 'server')
  const servers = ws.sessions.filter((s) => roleOf(s) === 'server')
  const ended = ws.sessions.filter((s) => s.state === 'ended' && !isAsleep(s) && roleOf(s) !== 'server')
  const chats = ws.sessions.filter((s) => roleOf(s) !== 'server')
  const allAsleep = chats.length > 0 && chats.every(isAsleep)
  return (
    <div className="h-full flex flex-col min-h-0" style={{ padding: PAD, gap: GAP }} aria-label={ws.name}>
      <div className="flex items-center gap-8 shrink-0" style={{ height: HEAD }}>
        <Swatch w={ws} size={10} />
        <b className="text-14" style={{ color: 'var(--text-primary)' }}>{ws.name}</b>
        <span className="text-11 aq-ink3">{tn(chats.length, '{n} chat', '{n} chats')}{ws.kind === 'group' ? ` · ${t('your group')}` : ''}</span>
        <span className="ml-auto flex items-center gap-4">
          {onMenu && <button type="button" data-nodrag className="aq-btn line" onClick={onMenu}><Menu size={12} />{t('Group…')}</button>}
          <button type="button" data-nodrag className="aq-btn line" onClick={onDetach}><ExternalLink size={12} />{t('Detach the workspace')}</button>
          {canSleep && chats.length > 0 && (
            <button type="button" data-nodrag className="aq-btn line" onClick={() => onSleepWs(!allAsleep)}>
              {allAsleep ? <><Sun size={12} />{t('Wake the workspace')}</> : <><Moon size={12} />{t('Sleep the workspace')}</>}
            </button>
          )}
        </span>
      </div>
      <div className="flex-1 min-h-0 aq-scroll flex flex-col" style={{ gap: GAP }}>
        <div className="grid content-start" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: `${TILE_H}px`, gap: GAP }}>
          {tiles.map((s) => <Tile key={s.id} s={s} on={on} current={s.id === current} onPick={() => onChat(s.id)} />)}
        </div>
        {!tiles.length && <p className="m-0 text-12 aq-ink3">{t('No terminal is awake here.')}</p>}
        {(sleeping.length > 0 || ended.length > 0) && (
          <ul className="m-0 p-0 list-none flex flex-wrap gap-6" aria-label={t('Asleep')}>
            {[...sleeping, ...ended].map((s) => (
              <li key={s.id} className="flex items-center gap-6 h-[26px] pl-8 pr-2 rounded-[6px] text-12" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)' }}>
                <Dot s={s} />
                <button type="button" data-nodrag className="truncate max-w-[200px]" style={{ color: 'var(--text-secondary)' }} onClick={() => onChat(s.id)}>{s.label}</button>
                {isAsleep(s) && <button type="button" data-nodrag className="aq-btn !h-[20px]" onClick={() => onWake(s.id)}><Sun size={11} />{t('Wake')}</button>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="shrink-0 flex items-center gap-6 flex-wrap">
        <span className="aq-label">{t('servers')}</span>
        {servers.map((s) => (
          <button key={s.id} type="button" data-nodrag className="h-[22px] px-8 inline-flex items-center gap-6 text-11 rounded-[6px]" style={{ background: 'var(--bg-hover)', color: 'var(--text-primary)' }} onClick={() => onChat(s.id)}>
            <Dot s={s} />{s.label}
          </button>
        ))}
        {!servers.length && <span className="text-11 aq-ink3">{t('none')}</span>}
      </div>
    </div>
  )
}

export function AllLevel({ workspaces, current, cols, onWs, onChat }: {
  workspaces: Workspace[]; current: string; cols: number; onWs: (id: string) => void; onChat: (id: string) => void
}) {
  const live = workspaces.filter(isLive)
  return (
    <div className="h-full flex flex-col min-h-0" style={{ padding: PAD, gap: GAP }}>
      <div className="flex items-center gap-8 shrink-0" style={{ height: HEAD }}>
        <b className="text-14" style={{ color: 'var(--text-primary)' }}>{t('Every workspace')}</b>
        <span className="text-11 aq-ink3">{t('one per project, and your groups')}</span>
      </div>
      <div className="flex-1 min-h-0 aq-scroll grid gap-12 content-start items-start" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {live.map((w) => {
          const chats = w.sessions.filter((s) => roleOf(s) !== 'server')
          const asleep = chats.length > 0 && chats.every(isAsleep)
          const waiting = waitingIn(w)
          const count = (k: string) => w.sessions.filter((s) => shownOf(s) === k).length
          return (
            <section key={w.id} className="rounded-[12px] p-8 flex flex-col gap-6" aria-label={w.name}
              style={{ background: asleep ? 'var(--bg-surface)' : 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: `inset 3px 0 0 ${lane(w.color)}`, opacity: asleep ? 0.7 : 1 }}>
              <div className="flex items-center gap-6">
                <button type="button" data-nodrag className="flex items-center gap-6 min-w-0" onClick={() => onWs(w.id)}>
                  <Swatch w={w} size={9} />
                  <b className="text-13 truncate" style={{ color: 'var(--text-primary)' }}>{w.name}</b>
                </button>
                {w.kind === 'group' && <span className="aq-chip">{t('group')}</span>}
                {waiting > 0 && <span className="text-11 font-semibold" style={{ color: 'var(--status-amber)' }} title={t('your turn')}>● {waiting}</span>}
                <span className="text-10 aq-ink3 ml-auto">
                  {asleep ? t('asleep') : [
                    tn(chats.length, '{n} chat', '{n} chats'),
                    count('working') ? `${count('working')} ${SHOWN_WORD.working}` : '',
                    count('asleep') ? `${count('asleep')} ${SHOWN_WORD.asleep}` : '',
                  ].filter(Boolean).join(' · ')}
                </span>
              </div>
              <ul className="m-0 p-0 list-none flex flex-col gap-2">
                {w.sessions.map((s: AquaSession) => (
                  <li key={s.id}>
                    <button type="button" data-nodrag onClick={() => onChat(s.id)}
                      className="w-full flex items-center gap-6 rounded-[6px] px-6 h-[24px] text-12 text-left"
                      style={{ background: s.id === current ? 'var(--brand-glow)' : 'var(--bg-surface)', boxShadow: shownOf(s) === 'waiting' ? 'inset 3px 0 0 var(--status-amber)' : undefined, opacity: isAsleep(s) ? 0.6 : 1 }}>
                      <Dot s={s} /><span className="truncate flex-1" style={{ color: 'var(--text-primary)' }}>{s.label}</span>
                      {w.kind === 'group' && <span className="text-10 aq-ink3 shrink-0">{s.project}</span>}
                    </button>
                  </li>
                ))}
                {!w.sessions.length && <li className="text-11 aq-ink3 px-6">{t('empty')}</li>}
              </ul>
            </section>
          )
        })}
      </div>
    </div>
  )
}
