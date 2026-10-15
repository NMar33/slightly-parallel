import { describe, expect, it } from 'vitest'
import { agentLabel, toolOf } from './agentLabel'

describe('agentLabel precedence', () => {
  it('operator rename wins over the chat title', () => {
    expect(
      agentLabel({ agent_id: 'cc-abc12345', agent_name: 'setup build', chat_title: 'branchy' }),
    ).toBe('setup build')
  })
  it('chat title fills in when the operator has not renamed', () => {
    expect(
      agentLabel({ agent_id: 'cc-abc12345', agent_name: 'cc-abc12345', chat_title: 'branchy' }),
    ).toBe('branchy')
  })
  it('falls back to the tool default, then the id', () => {
    expect(agentLabel({ agent_id: 'cc-abc12345', created_date: '2608-14' })).toMatch(/^Claude Code/)
    expect(agentLabel({ agent_id: 'mystery' })).toBe('mystery')
  })
})

describe('resumeCommand', () => {
  it('builds per-tool commands and stays silent when it cannot', async () => {
    const { resumeCommand } = await import('../features/project/AgentDrill')
    expect(resumeCommand('claude-code', '/w/app', 'abc-def')).toBe('cd "/w/app" && claude -r abc-def')
    expect(resumeCommand('codex', '', 'xyz')).toBe('codex resume xyz')
    expect(resumeCommand('opencode', '/w', 's1')).toBe('cd "/w" && opencode --session s1')
    expect(resumeCommand('mystery', '/w', 's1')).toBe('')
    expect(resumeCommand('claude-code', '/w', '')).toBe('')
  })
})

describe('an agent with no id', () => {
  it('reads as nothing rather than breaking the page', () => {
    expect(agentLabel({ agent_id: null as unknown as string })).toBe('')
    expect(toolOf(undefined)).toBe('')
  })
})
