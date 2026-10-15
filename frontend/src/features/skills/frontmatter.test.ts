import { describe, expect, it } from 'vitest'

import { buildSkillMd, descriptionProblem, fieldsEqual, nameProblem, splitSkillMd } from './frontmatter'

describe('SKILL.md as fields', () => {
  it('reads the two fields and the steps', () => {
    const f = splitSkillMd('---\nname: cut-a-release\ndescription: Use when a release is cut.\n---\n\n1. Tag.\n2. Push.\n')
    expect(f).toEqual({ name: 'cut-a-release', description: 'Use when a release is cut.', extra: '', body: '1. Tag.\n2. Push.' })
  })

  it('keeps every other line of the block and writes it back', () => {
    const md = '---\nname: shot\ndescription: "Use when: a screenshot is asked for."\nallowed-tools: Bash(node:*)\nmetadata:\n  author: dana\n---\n\nRun it.\n'
    const f = splitSkillMd(md)
    expect(f.name).toBe('shot')
    expect(f.description).toBe('Use when: a screenshot is asked for.')
    expect(f.extra).toBe('allowed-tools: Bash(node:*)\nmetadata:\n  author: dana')
    const out = buildSkillMd(f)
    expect(out).toContain('allowed-tools: Bash(node:*)')
    expect(out).toContain('metadata:\n  author: dana')
    // A value with ": " is quoted again, so YAML reads it as one string.
    expect(out).toContain('description: "Use when: a screenshot is asked for."')
    expect(splitSkillMd(out)).toEqual(f)
  })

  it('joins a folded description and keeps the lines around it', () => {
    const md = '---\nlicense: MIT\ndescription: >\n  One line\n  and another.\nname: two-lines\n---\nBody.\n'
    const f = splitSkillMd(md)
    expect(f.description).toBe('One line and another.')
    expect(f.name).toBe('two-lines')
    expect(f.extra).toBe('license: MIT')
    expect(buildSkillMd(f)).toBe('---\nname: two-lines\ndescription: One line and another.\nlicense: MIT\n---\n\nBody.\n')
  })

  it('is not "changed" until a field is', () => {
    const md = '---\nname: x\ndescription:   spaced   out \n---\n\nBody.\n\n'
    const f = splitSkillMd(md)
    expect(fieldsEqual(f, splitSkillMd(buildSkillMd(f)))).toBe(true)
    expect(fieldsEqual(f, { ...f, body: 'Body.' })).toBe(true)
    expect(fieldsEqual(f, { ...f, name: 'y' })).toBe(false)
    expect(fieldsEqual(f, { ...f, extra: 'license: MIT' })).toBe(false)
  })

  it('checks the name and the description the way the server does', () => {
    expect(nameProblem('cut-a-release')).toBe('')
    expect(nameProblem('')).toBe('Type a name.')
    expect(nameProblem('Cut Release')).toMatch(/Lower-case/)
    expect(nameProblem('a--b')).toMatch(/single hyphens/)
    expect(nameProblem('-a')).toMatch(/single hyphens/)
    expect(nameProblem('a'.repeat(65))).toBe('Up to 64 characters.')
    expect(descriptionProblem('x'.repeat(1024))).toBe('')
    expect(descriptionProblem('x'.repeat(1025))).toBe('Up to 1024 characters.')
  })

  it('takes a file with no block as steps only', () => {
    expect(splitSkillMd('Just steps.')).toEqual({ name: '', description: '', extra: '', body: 'Just steps.' })
  })
})
