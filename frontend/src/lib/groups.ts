/**
 * Agent groups — the operator's name for several lanes that are one piece
 * of work (`agent_group`, set in the agent editor). Wherever agents are
 * listed or picked, a group can stand in for its members; it wears its
 * own colour so it never reads as one more agent.
 */

export const GROUP_COLOR = 'var(--group, var(--status-purple))'

/** A group where an agent id is expected (a filter, a lane). */
export const groupKey = (name: string) => `group:${name}`
export const isGroupKey = (id: string | null | undefined) => !!id && id.startsWith('group:')
export const groupName = (id: string) => (isGroupKey(id) ? id.slice('group:'.length) : '')
