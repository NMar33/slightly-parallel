/**
 * Press releases — the operator asks from the task, the agent writes.
 *
 * Three parts make the prompt: the focus (this task, this time), the brief
 * (what to write) and the style (the voice, by example). Each part keeps
 * its own named presets on the server, so a different set of style
 * references for a different kind of task is one click. Sending the prompt
 * records a request (sr_…); the request id in the prompt is the agent's
 * permission to post the piece back, and it closes on the first post.
 */

import { getJson, getText, postJson, refused } from '../../../lib/getJson'
import { persistPref, readPref } from '../../../lib/uiPrefs'
import { ago as agoOf } from '../../../utils/format'
import { t } from '../../../i18n/scope/project'

export type Part = 'focus' | 'brief' | 'style'
export const PARTS: Part[] = ['focus', 'brief', 'style']
export const PART_LABEL: Record<Part, string> = { focus: 'focus', brief: t('what to do'), style: 'style examples' }
export const PART_HINT: Record<Part, string> = {
  focus: t('Your notes on this task. They go into the piece as your words.'),
  brief: t('What the agent writes, in which order, and what to attach'),
  style: 'Texts written in the voice you want',
}
export const RELEASE_TYPES = ['article', 'post', 'release'] as const
export type ReleaseType = (typeof RELEASE_TYPES)[number]

export type Preset = { id: string; name: string; text: string }
export type PresetStore = { parts: Record<Part, Preset[]>; builtin: string[] }
export type StoryRequest = {
  id: string; task_id: string; type: string; created_at: string; actor: string
  status: 'open' | 'fulfilled' | 'cancelled'; focus: string; brief_id: string; style_id: string
  note_id: string; agent_id: string; fulfilled_at: string
}

type RequestBody = {
  type: ReleaseType; focus: string; actor: string
  brief_id?: string; brief: string; style_id?: string; style: string
}

/**
 * What the window sends. The brief and the style go as text every time,
 * the preset id beside them for the record: a box the operator emptied
 * sends an empty string, and the server takes that as "none", not as
 * "use the preset". The focus goes whole; the server keeps it whole.
 */
export function requestBody(
  type: ReleaseType, texts: Record<Part, string>, picks: Partial<Record<Part, string>>, actor: string,
): RequestBody {
  return {
    type, focus: texts.focus, actor,
    brief_id: picks.brief, brief: texts.brief,
    style_id: picks.style, style: texts.style,
  }
}
type StoryImage = {
  id: string; note_id: string; task_id: string; title: string; path: string
  width: string; height: string; bytes: string; created_at: string; url: string
}


export function loadPresets(): Promise<PresetStore> {
  return getJson<PresetStore>('/api/story/prompts')
}

export function savePreset(part: Part, name: string, text: string, id?: string): Promise<{ preset: Preset }> {
  return postJson('/api/story/prompts', { part, name, text, id })
}

export function deletePreset(id: string): Promise<{ deleted: string }> {
  return postJson(`/api/story/prompts/${encodeURIComponent(id)}/delete`)
}

export function createRequest(taskId: string, body: RequestBody): Promise<{ request: StoryRequest; prompt: string }> {
  return postJson(`/api/tasks/${encodeURIComponent(taskId)}/story-requests`, body)
}

/** The query key of a task's release requests (the Story section and the release window share it). */
export const requestsKey = (taskId: string) => ['tasks', 'story-requests', taskId] as const

export async function listRequests(taskId: string, signal?: AbortSignal): Promise<StoryRequest[]> {
  const d = await getJson<{ requests?: StoryRequest[] }>(`/api/tasks/${encodeURIComponent(taskId)}/story-requests`, signal).catch(refused(null))
  return d?.requests ?? []
}

export function requestPrompt(id: string): Promise<string> {
  return getText(`/api/story/requests/${encodeURIComponent(id)}/prompt`)
}

export function cancelRequest(id: string): Promise<{ request: StoryRequest }> {
  return postJson(`/api/story/requests/${encodeURIComponent(id)}/cancel`)
}

export async function listImages(taskId: string, signal?: AbortSignal): Promise<StoryImage[]> {
  const d = await getJson<{ images?: StoryImage[] }>(`/api/story/images?task_id=${encodeURIComponent(taskId)}`, signal).catch(refused(null))
  return d?.images ?? []
}

/** A note written under a request carries the request id as its template. */
export function isRequestNote(template: string | undefined): boolean {
  return String(template ?? '').startsWith('sr_')
}

/* Remembered choices: the last preset per part (synced), the focus draft
   per task (this browser only — a draft, like the note drafts). */
const CHOICE_PREF = 'sp-release-presets'
export const FOCUS_DRAFT_KEY = (taskId: string) => `sp-release-draft:${taskId}`

export function readChoices(): Partial<Record<Part, string>> {
  try { return JSON.parse(readPref(CHOICE_PREF) ?? '{}') as Partial<Record<Part, string>> } catch { return {} }
}
export function writeChoices(c: Partial<Record<Part, string>>): void {
  persistPref(CHOICE_PREF, JSON.stringify(c))
}
export function readFocusDraft(taskId: string): string {
  try { return localStorage.getItem(FOCUS_DRAFT_KEY(taskId)) ?? '' } catch { return '' }
}
export function writeFocusDraft(taskId: string, text: string): void {
  try {
    if (text.trim()) localStorage.setItem(FOCUS_DRAFT_KEY(taskId), text)
    else localStorage.removeItem(FOCUS_DRAFT_KEY(taskId))
  } catch { /* private mode */ }
}

export function ago(ts: string): string {
  const ms = Date.now() - Date.parse(ts)
  return Number.isFinite(ms) ? agoOf(ms, 48) : ''
}
