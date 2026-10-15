/**
 * Runs — the rating steps save on click, the facts stay grey, the rollup
 * counts rather than averages, and every run opens its own turn in the chat.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import { RunCard, RollupBars, factWords } from './runs'
import type { Scales, Send, VersionRollup } from './data'

const SCALES: Scales = {
  task_success: ['below', 'average', 'better', 'one-shot'],
  regression: ['none', 'some', 'serious'],
  intervention: ['none', 'little', 'lot'],
  score: [1, 10],
}

const SEND: Send = {
  at: '2026-09-07T16:56:51', project: 'slightly-parallel', agent_id: 'cc-1',
  session_id: 'ses_abc', turn: 7, words: 124, head: 'Feature for the prompt',
  version: 1, exact: true,
  facts: {
    turns_after: 7, follow_ups: 7, minutes: 56, reply_words: 244,
    produced: { scans: 2 }, task_moved: [{ task_id: 'tk_1', from: 'doing', to: 'review' }],
    session_turns: 11,
  },
  rating: null,
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('runs', () => {
  let posted: Array<{ url: string; body: Record<string, unknown> }>
  beforeEach(() => {
    posted = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      posted.push({ url, body: JSON.parse(String(init?.body ?? '{}')) })
      return Response.json({})
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('the facts read as a sentence and the task move is named', () => {
    expect(factWords(SEND.facts)).toEqual([
      '7 follow-ups', '11 turns', '56 min of agent work', '244-word reply', '2 scans',
    ])
    wrap(<RunCard promptId="pm_x" send={SEND} scales={SCALES} open onToggle={() => {}} />)
    expect(screen.getByText('tk_1 doing → review')).toBeInTheDocument()
  })

  it('clicking a step saves it against the run, and the chat link carries the turn', async () => {
    wrap(<RunCard promptId="pm_x" send={SEND} scales={SCALES} open onToggle={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'task: one-shot' }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0].url).toBe('/api/prompt-library/pm_x/runs/ses_abc/7')
    expect(posted[0].body).toEqual({ task_success: 'one-shot' })

    fireEvent.click(screen.getByRole('button', { name: 'score 8' }))
    await waitFor(() => expect(posted).toHaveLength(2))
    expect(posted[1].body).toEqual({ score: 8 })

    expect(screen.getByRole('link', { name: /open chat/ })).toHaveAttribute(
      'href', '/sessions#sel=ses_abc&turn=7',
    )
  })

  it('a chosen step clicked again clears it', async () => {
    const rated = { ...SEND, rating: { task_success: 'better', regression: '', intervention: '', score: 7, note: '', rated_at: '' } }
    wrap(<RunCard promptId="pm_x" send={rated} scales={SCALES} open onToggle={() => {}} />)
    const on = screen.getByRole('button', { name: 'task: better' })
    expect(on).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(on)
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0].body).toEqual({ task_success: null })
  })

  it('the rollup shows counts per step, never an average', () => {
    const r: VersionRollup = {
      sends: 5, rated: 4,
      dist: {
        task_success: { below: 0, average: 1, better: 0, 'one-shot': 3 },
        regression: { none: 3, some: 1, serious: 0 },
        intervention: { none: 2, little: 2, lot: 0 },
      },
      score_median: 8, follow_ups_median: 1,
    }
    wrap(<RollupBars rollup={r} scales={SCALES} />)
    expect(screen.getByText(/5 sends · 4 rated · median 8\/10/)).toBeInTheDocument()
    expect(screen.getByText('1 average · 3 one-shot')).toBeInTheDocument()
    expect(screen.getByText('3 none · 1 some')).toBeInTheDocument()
    expect(screen.queryByText(/7\.\d/)).toBeNull()
  })
})
