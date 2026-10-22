/**
 * The smart timer's side of the page: what you are working on right now,
 * and a request to ask whether to track it.
 *
 * "Working on" comes in layers — the project page you are on (route), a
 * terminal you are typing in (terminal), a task window open (task); the
 * most specific wins. SmartTimer (features/time) reads it to send the
 * server a beat while you give input; the server decides what counts.
 */

import { useEffect, useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'

import { getJson } from './getJson'

export interface WorkContext { project: string; taskId?: string; title?: string }

const ORDER = ['task', 'terminal', 'route'] as const
type Layer = (typeof ORDER)[number]

const layers = new Map<Layer, WorkContext>()

export function setWork(layer: Layer, ctx: WorkContext | null): void {
  if (ctx && ctx.project) layers.set(layer, ctx)
  else layers.delete(layer)
}

/** The most specific thing you are working on, or null. */
export function currentWork(): WorkContext | null {
  for (const l of ORDER) {
    const got = layers.get(l)
    if (got) return got
  }
  return null
}

/** Hold a layer while the component is mounted (and the context is set). */
export function useWork(layer: Layer, ctx: WorkContext | null): void {
  const project = ctx?.project ?? ''
  const taskId = ctx?.taskId ?? ''
  useEffect(() => {
    if (!project) return
    setWork(layer, { project, taskId })
    return () => setWork(layer, null)
  }, [layer, project, taskId])
}

/* ------------------------------------------------------------ the reminder */

let asking: WorkContext | null = null
const listeners = new Set<() => void>()
const tell = () => listeners.forEach((l) => l())

/** Opening a task or starting an agent: the timer may ask whether to track. */
export function askToTrack(ctx: WorkContext): void {
  if (!ctx.project) return
  asking = ctx
  tell()
}

export function clearAsk(): void {
  asking = null
  tell()
}

export function useAsk(): WorkContext | null {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l) }, () => asking)
}

/* -------------------------------------------------------------- the status */

export type TimeMode = 'remind' | 'auto' | 'manual'

export interface AwayNotice {
  entry_id: string
  project: string
  from: string
  to: string
  sec: number
  /** Away past three hours: still paused, asks what to do. */
  long: boolean
}

export interface TimeAuto {
  idle_sec: number | null
  /** Where idle is read from: gnome, xprintidle, macos, windows, "" (nowhere). */
  idle_source: string
  idle_pause: boolean
  idle_minutes: number
  grace_seconds: number
  default_mode: TimeMode
  modes: Record<string, TimeMode>
  working: Array<{ project: string; entry_id: string; task_id: string; top: number }>
  away: AwayNotice[]
}

export const TIME_AUTO_KEY = ['time-auto'] as const

export function useTimeAuto() {
  return useQuery({
    queryKey: TIME_AUTO_KEY,
    queryFn: ({ signal }) => getJson<TimeAuto>('/api/time/auto', signal),
    refetchInterval: 15_000,
  })
}

export const modeOf = (st: TimeAuto | undefined, project: string): TimeMode =>
  st?.modes[project] ?? st?.default_mode ?? 'remind'
