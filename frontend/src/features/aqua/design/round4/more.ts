/**
 * What a later version lays over K's parts without changing K. A version
 * after K (round5/L) renders K inside this context and adds: a look for the
 * tab's state, rows at the top of the «Варианты» panel, switches it hides,
 * its own compare features, and its lines in «Скопировать выбор».
 * Without a provider every part is as it was in K.
 */

import { createContext, useContext, type ReactNode } from 'react'

import type { Session } from '../mock'
import type { AquaState } from '../store'
import type { Facts, LabKey } from '../round3/lab/live'
import type { Feature } from './compareState'

/** What a tab draws instead of the status strip, and instead of its state dot when `dot` is set. */
export interface TabDecor { strip: ReactNode; dot?: ReactNode }
export interface TabDecorArgs { c: Session; st: AquaState; f: Facts; waiting: boolean; alt: boolean }

export interface More {
  /** The version key in the copied address (`v=l`). */
  v: string
  /** The head line of the copied text. */
  head: string
  /** Replaces the strip (and maybe the dot) on every tab. */
  tabDecor?: (a: TabDecorArgs) => TabDecor
  /** «Варианты» switches this version leaves out (the panel and the copied text). */
  hide?: LabKey[]
  /** Rows at the top of the «Варианты» list. */
  rows?: ReactNode
  /** The letters after the folded panel's name. */
  summary?: string
  /** The feature «Сравнить» opens first. */
  first?: Feature
  /** The features the compare view lists, in order. */
  features?: readonly Feature[]
  /** Compare features of this version: the tab's word, the line under it, the tiles. */
  compare?: Partial<Record<Feature, { word: string; line: string; body: ReactNode }>>
  /** Lines of the copied text right after the head line. */
  lines?: string[]
  /** Address parameters the copied address carries. */
  params?: Record<string, string>
}

export const MoreContext = createContext<More | null>(null)
export const useMore = () => useContext(MoreContext)
