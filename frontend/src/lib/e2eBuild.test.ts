// @vitest-environment node
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execSync } from 'node:child_process'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildIfStale } from '../../tests/e2e/buildDist'

vi.mock('node:child_process', () => ({ execSync: vi.fn() }))

describe('running tests against a prebuilt frontend snapshot', () => {
  let frontend: string

  beforeEach(() => {
    frontend = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-prebuilt-'))
    fs.mkdirSync(path.join(frontend, 'src'))
    for (const file of ['index.html', 'vite.config.ts', 'src/app.ts']) {
      fs.writeFileSync(path.join(frontend, file), '')
    }
    vi.clearAllMocks()
    vi.stubEnv('SP_E2E_NO_BUILD', '1')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    fs.rmSync(frontend, { recursive: true, force: true })
  })

  function putBuildAt(date: Date): void {
    fs.mkdirSync(path.join(frontend, 'dist'))
    const index = path.join(frontend, 'dist', 'index.html')
    fs.writeFileSync(index, '<html></html>')
    fs.utimesSync(index, date, date)
  }

  it('fails on a missing build before it can start a build', () => {
    expect(() => buildIfStale(frontend)).toThrow(/SP_E2E_NO_BUILD/)
    expect(execSync).not.toHaveBeenCalled()
  })

  it('fails on a stale build before it can start a build', () => {
    putBuildAt(new Date(2000, 0, 1))
    expect(() => buildIfStale(frontend)).toThrow(/SP_E2E_NO_BUILD/)
    expect(execSync).not.toHaveBeenCalled()
  })

  it('uses the ready build without calling npm', () => {
    putBuildAt(new Date(Date.now() + 60_000))
    expect(() => buildIfStale(frontend)).not.toThrow()
    expect(execSync).not.toHaveBeenCalled()
  })
})
