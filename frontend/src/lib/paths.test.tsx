import { describe, expect, it } from 'vitest'
import { absolutePath, looksLikePath } from './paths'

const FOLDER = '/home/user/projects/app'

describe('a copied path', () => {
  it('is joined to the project folder', () => {
    expect(absolutePath(FOLDER, 'backend/backend/db.py')).toBe(`${FOLDER}/backend/backend/db.py`)
    expect(absolutePath(`${FOLDER}/`, './run.sh')).toBe(`${FOLDER}/run.sh`)
    expect(absolutePath(FOLDER, 'backend/db.py:ViewStore')).toBe(`${FOLDER}/backend/db.py:ViewStore`)
  })
  it('leaves alone what is already absolute, a home path, a URL or prose', () => {
    expect(absolutePath(FOLDER, '/etc/hosts')).toBe('/etc/hosts')
    expect(absolutePath(FOLDER, '~/.claude/skills')).toBe('~/.claude/skills')
    expect(absolutePath(FOLDER, 'https://example.com/x')).toBe('https://example.com/x')
    expect(absolutePath(FOLDER, 'the kanban card')).toBe('the kanban card')
  })
  it('is unchanged while the folder is unknown', () => {
    expect(absolutePath(undefined, 'run.sh')).toBe('run.sh')
  })
  it('knows a path from prose', () => {
    expect(looksLikePath('backend/db.py')).toBe(true)
    expect(looksLikePath('run.sh')).toBe(true)
    expect(looksLikePath('Open this first')).toBe(false)
  })
})
