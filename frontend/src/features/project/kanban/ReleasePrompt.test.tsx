import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { toast } from '../../../components/primitives'
import { ReleasePromptModal } from './ReleasePrompt'
import { FOCUS_DRAFT_KEY } from './release'
import type { TaskRow } from './model'

const task = { id: 'tk_1', title: 'Ship it', project: 'alpha', status: 'done' } as unknown as TaskRow

const presets = {
  parts: {
    focus: [],
    brief: [{ id: 'b1', name: 'Default', text: 'Write it up' }],
    style: [{ id: 's1', name: 'Plain', text: 'plain voice' }],
  },
  builtin: ['b1', 's1'],
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('the release window', () => {
  const posted: unknown[] = []
  beforeEach(() => {
    localStorage.clear()
    posted.length = 0
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/story/prompts') return json(200, presets)
      if (url.endsWith('/story-requests') && init?.method === 'POST') {
        posted.push(JSON.parse(String(init.body)))
        return json(201, { request: { id: 'sr_1', status: 'open', created_at: new Date().toISOString() }, prompt: 'THE PROMPT' })
      }
      if (url.endsWith('/story-requests')) return json(200, { requests: [] })
      return json(404, { detail: `unexpected ${url}` })
    }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('sends an emptied style as an empty string and clears the focus draft once the request is recorded', async () => {
    localStorage.setItem(FOCUS_DRAFT_KEY('tk_1'), 'notes for this one')
    render(<ReleasePromptModal task={task} onClose={() => {}} />)

    const style = await screen.findByLabelText('style examples') as HTMLTextAreaElement
    await waitFor(() => expect(style.value).toBe('plain voice'))
    const focus = screen.getByLabelText('focus') as HTMLTextAreaElement
    expect(focus.value).toBe('notes for this one')

    fireEvent.change(style, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /Copy prompt/ }))

    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]).toMatchObject({ type: 'release', focus: 'notes for this one', brief: 'Write it up', style: '', actor: 'operator' })
    await waitFor(() => expect(focus.value).toBe(''))
    expect(localStorage.getItem(FOCUS_DRAFT_KEY('tk_1'))).toBeNull()
  })

  it('refuses an empty brief without a request', async () => {
    render(<ReleasePromptModal task={task} onClose={() => {}} />)
    const brief = await screen.findByLabelText('what to do') as HTMLTextAreaElement
    await waitFor(() => expect(brief.value).toBe('Write it up'))
    fireEvent.change(brief, { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: /Copy prompt/ }))
    await new Promise((r) => setTimeout(r, 20))
    expect(posted).toHaveLength(0)
  })

  it('warns when the browser blocks the clipboard: the request is recorded, the prompt is not copied', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
    const warning = vi.spyOn(toast, 'warning')
    const success = vi.spyOn(toast, 'success')
    render(<ReleasePromptModal task={task} onClose={() => {}} />)
    const brief = await screen.findByLabelText('what to do') as HTMLTextAreaElement
    await waitFor(() => expect(brief.value).toBe('Write it up'))
    fireEvent.click(screen.getByRole('button', { name: /Copy prompt/ }))
    await waitFor(() => expect(warning).toHaveBeenCalledTimes(1))
    expect(String(warning.mock.calls[0]![0])).toMatch(/sr_1 recorded, but the browser blocked the clipboard/)
    expect(success).not.toHaveBeenCalled()
    warning.mockRestore()
    success.mockRestore()
  })
})
