import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'

// The grown-up reader is heavy and tested on its own; here we only care
// that it is the one being opened, and on which turn.
const readerProps: Record<string, unknown>[] = []
vi.mock('../agents/dossier', () => ({
  ChatReader: (props: Record<string, unknown>) => {
    readerProps.push(props)
    return <div data-testid="chat-reader">reader</div>
  },
}))

import { MentionChat, MentionRow, mentionResume, mentionWho, type Mention } from './mentions'

const AGENT = {
  agent_id: 'cc-c0b0e20f',
  agent_name: 'Отладчик',
  chat_title: '',
  created_date: '2609-10',
  tool: 'claude-code',
  cwd: '/work/slightly-parallel',
  session_ref: 'c0b0e20f-1111-2222-3333-444455556666',
}

const MENTION: Mention = {
  at: '2026-09-14T16:15:00',
  role: 'user',
  agent_id: 'cc-c0b0e20f',
  session_id: 'ses_b4465b20',
  turn: 12,
  excerpt: 'tk_3f49b8bc · Calendar, Milestones, Gantt',
  project: 'slightly-parallel',
  agent: AGENT,
}

let written: string[] = []

beforeEach(() => {
  written = []
  readerProps.length = 0
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn(async (t: string) => { written.push(t) }) },
  })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function wrap(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })
const renderQ = (ui: React.ReactElement) => render(<QueryClientProvider client={qc()}>{ui}</QueryClientProvider>)

describe('MentionRow', () => {
  it('names the agent and keeps the id beside it', () => {
    renderQ(<MentionRow m={MENTION} onOpen={() => {}} />)
    expect(screen.getByText('Отладчик')).toBeInTheDocument()
    expect(screen.getByText('cc-c0b0e20f')).toBeInTheDocument()
    expect(screen.getByText('◆ sent to')).toBeInTheDocument()
    expect(screen.getByText(/turn 12/)).toBeInTheDocument()
  })

  it('copies the name and the id without opening the chat', async () => {
    const onOpen = vi.fn()
    renderQ(<MentionRow m={MENTION} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy Отладчик' }))
    await waitFor(() => expect(written).toEqual(['Отладчик']))
    fireEvent.click(screen.getByRole('button', { name: 'Copy cc-c0b0e20f' }))
    await waitFor(() => expect(written).toEqual(['Отладчик', 'cc-c0b0e20f']))
    expect(onOpen).not.toHaveBeenCalled()
  })

  it('copies the resume command, then says so', async () => {
    renderQ(<MentionRow m={MENTION} onOpen={() => {}} />)
    // Resume opens a terminal; the copy beside it keeps the command.
    expect(screen.getByRole('button', { name: /Resume/ })).toHaveTextContent('Resume')
    const resume = screen.getByRole('button', { name: 'Copy the resume command' })
    fireEvent.click(resume)
    await waitFor(() => expect(written).toEqual([
      'cd "/work/slightly-parallel" && claude -r c0b0e20f-1111-2222-3333-444455556666',
    ]))
  })

  it('opens the chat from the excerpt', () => {
    const onOpen = vi.fn()
    renderQ(<MentionRow m={MENTION} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: /Calendar, Milestones, Gantt/ }))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('offers no resume when the origin was never recorded', () => {
    const bare: Mention = { ...MENTION, agent: null }
    const { rerender } = renderQ(<MentionRow m={bare} onOpen={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Copy the resume command' })).toBeNull()

    const noRef: Mention = { ...MENTION, agent: { ...AGENT, session_ref: '' } }
    rerender(<QueryClientProvider client={qc()}><MentionRow m={noRef} onOpen={() => {}} /></QueryClientProvider>)
    expect(screen.queryByRole('button', { name: 'Copy the resume command' })).toBeNull()

    const unknownTool: Mention = { ...MENTION, agent: { ...AGENT, tool: 'nethack' } }
    rerender(<QueryClientProvider client={qc()}><MentionRow m={unknownTool} onOpen={() => {}} /></QueryClientProvider>)
    expect(screen.queryByRole('button', { name: 'Copy the resume command' })).toBeNull()
  })

  it('falls back to the tool and the id when the server carries no agent', () => {
    renderQ(<MentionRow m={{ ...MENTION, agent: null }} onOpen={() => {}} />)
    expect(screen.getByText('Claude Code')).toBeInTheDocument()
    expect(screen.getByText('cc-c0b0e20f')).toBeInTheDocument()
  })
})

describe('mentionWho / mentionResume', () => {
  it('reads name then id, and the id alone when there is no name', () => {
    expect(mentionWho({ agent_id: 'cc-c0b0e20f', agent: AGENT })).toBe('Отладчик · cc-c0b0e20f')
    expect(mentionWho({ agent_id: 'who-knows' })).toBe('who-knows')
  })

  it('builds the command each tool takes', () => {
    expect(mentionResume(AGENT)).toBe('cd "/work/slightly-parallel" && claude -r c0b0e20f-1111-2222-3333-444455556666')
    expect(mentionResume({ ...AGENT, tool: 'codex', session_ref: 'th_1' })).toBe('cd "/work/slightly-parallel" && codex resume th_1')
    expect(mentionResume({ ...AGENT, tool: 'opencode', session_ref: 'ses_1' })).toBe('cd "/work/slightly-parallel" && opencode --session ses_1')
    expect(mentionResume(null)).toBe('')
  })
})

describe('MentionChat', () => {
  it('opens the reader on the turn that named the task', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        metadata: {
          id: 'ses_b4465b20', created_date: '2609-14', start_time: '16:15',
          end_time: '16:15', duration_min: 1, turns_n: 1, l1: 'a chat',
        },
      }),
    })))
    wrap(<MentionChat mention={MENTION} onClose={() => {}} />)
    await screen.findByTestId('chat-reader')
    const props = readerProps[readerProps.length - 1]!
    expect(props.markTurn).toBe(12)
    expect((props.sessions as { id: string }[])[0]!.id).toBe('ses_b4465b20')
  })

  it('says so when there is no chat id to resume with', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        metadata: {
          id: 'ses_b4465b20', created_date: '2609-14', start_time: '16:15',
          end_time: '16:15', duration_min: 1, turns_n: 1, l1: 'a chat',
        },
      }),
    })))
    wrap(<MentionChat mention={{ ...MENTION, agent: { ...AGENT, session_ref: '' } }} onClose={() => {}} />)
    await screen.findByTestId('chat-reader')
    const props = readerProps[readerProps.length - 1]!
    render(<>{props.extra as React.ReactNode}</>)
    expect(screen.getByText('No chat id recorded.')).toBeInTheDocument()
  })
})
