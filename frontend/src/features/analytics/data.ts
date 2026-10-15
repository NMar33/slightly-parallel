/**
 * Analytics, read (backend analytics.py): the tables, and running a query.
 * Every page — notebook, builder, pipeline — ends in one SQL string here.
 */

import { useQuery } from '@tanstack/react-query'

import { getJson, postJson } from '../../lib/getJson'

interface Column { name: string; type: string; about: string }
interface Table { name: string; about: string; rows: number; columns: Column[] }
export interface Schema { tables: Table[]; examples: Array<{ title: string; sql: string }>; safety?: string[] }
export interface Result { columns: Array<{ name: string; type: string }>; rows: unknown[][]; truncated: boolean; ms: number }

export function useSchema() {
  return useQuery({
    queryKey: ['analytics', 'schema'],
    queryFn: ({ signal }) => getJson<Schema>('/api/analytics/schema', signal),
    staleTime: 60_000,
  })
}

function runSql(sql: string, signal?: AbortSignal): Promise<Result> {
  return postJson<Result>('/api/analytics/query', { sql }, signal)
}

/** A query's result, kept per SQL text; nothing runs for an empty one. */
export function useResult(sql: string) {
  return useQuery({
    queryKey: ['analytics', 'result', sql],
    queryFn: ({ signal }) => runSql(sql, signal),
    enabled: !!sql.trim(),
    retry: false,
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  })
}

/** Each table's clock: what "last 30 days" and "by week" are measured on. */
export const TIME_COLUMN: Record<string, string> = {
  messages: 'sent_at', chats: 'started', tasks: 'created', task_events: 'changed_at',
}

export const isNumeric = (t: string) => /INT|DOUBLE|DECIMAL|FLOAT|REAL|NUMERIC|BIGINT|HUGEINT/i.test(t)
export const isTime = (t: string) => /DATE|TIMESTAMP/i.test(t)
