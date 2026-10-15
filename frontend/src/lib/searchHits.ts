import { t } from '../i18n/scope/shell'
/**
 * Where a search hit lives, and what its kind is called.
 *
 * The server answers with the kind of every hit — the entity's own name
 * (`task`, `decision`, `scan`, `standup`, `problem`, …) plus `agent` and
 * `chat`. The route for each is the frontend's business, so it is written
 * once, here.
 */

export interface SearchHit {
  kind: string
  id: string
  title: string
  project: string
  date: string
  snippet: string
  where: 'title' | 'text'
  /** How many times the word sits in this row. */
  count?: number
  /** A `turn` hit carries who said it, when, and in which chat. */
  role?: 'user' | 'agent'
  turn?: number
  at?: string
  session_id?: string
  agent_id?: string
  /** A `part` hit carries its row of the map: the kind, and where it lives. */
  map_kind?: string
  where_path?: string
}

/** The page that shows this kind, and the entry brought into view. */
const ROUTE: Record<string, (id: string) => string> = {
  task: (id) => `/kanban?task=${encodeURIComponent(id)}`,
  decision: (id) => `/decisions#${id}`,
  scan: (id) => `/scans#scan=${id}`,
  standup: (id) => `/standups#${id}`,
  problem: (id) => `/problems#${id}`,
  rule: (id) => `/rules#${id}`,
  vision: (id) => `/visions#${id}`,
  skill: (id) => `/skills#${id}`,
  artifact: (id) => `/artifacts#${id}`,
  sprint: (id) => `/sprints#${id}`,
  file: (id) => `/files#${id}`,
  architecture: (id) => `/architecture#${id}`,
  prompt: (id) => `/prompts/${encodeURIComponent(id)}`,
  agent: (id) => `/agent/${encodeURIComponent(id)}`,
  // A row of the program's map. The map is a mode of the architecture page,
  // kept as an operator preference rather than in the address, so the link
  // goes to the page that holds it.
  part: () => '/architecture',
  chat: (id) => `/agent/${encodeURIComponent(id)}#sec=chats`,
}

export function hitHref(hit: SearchHit): string {
  if (hit.kind === 'turn') {
    const agent = hit.agent_id ?? hit.id.split('#')[0]
    return `/agent/${encodeURIComponent(agent)}#sec=chats`
  }
  const route = ROUTE[hit.kind]
  return route ? route(hit.id) : `/search?q=${encodeURIComponent(hit.id)}`
}

const WORD: Record<string, string> = {
  task: t('Tasks'), decision: t('Decisions'), scan: t('Scans'), standup: t('Standups'),
  problem: t('Problems'), rule: t('Rules'), vision: t('Visions'), skill: t('Skills'),
  artifact: t('Artifacts'), sprint: t('Sprints'), file: t('Files'),
  architecture: t('Architecture'), prompt: t('Prompts'),
  agent: t('Agents'), chat: t('Chats'), turn: t('Chats'), part: t('Map parts'),
  note: t('Notes'), idea: t('Ideas'),
  person: t('People'), touch: t('Touches'), event: t('Events'), time_entry: t('Time'),
  snippet: t('Snippets'), goal: t('Goals'), activity: t('Activity'), prompt_run: t('Prompt runs'),
}

export function kindWord(kind: string): string {
  return WORD[kind] ?? kind.replace(/_/g, ' ')
}

