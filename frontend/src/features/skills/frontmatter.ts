import { t } from '../../i18n/scope/system'
/**
 * SKILL.md as fields.
 *
 * The file agents read starts with a `---` block holding the name and the
 * description, then the steps. The page edits those as fields and puts the
 * file back together on save, so the operator never types YAML by hand.
 * Every other line of the block (`allowed-tools:`, `license:`, a `metadata:`
 * map) is kept as it was and written back after the two fields, so a skill
 * taken in from a plugin loses nothing on save.
 * Mirrors backend/skilllib.py: parse() there, this here.
 */

export interface SkillFields {
  name: string
  description: string
  /** The lines of the `---` block that are not name or description, verbatim. */
  extra: string
  /** Everything under the `---` block. */
  body: string
}

/** The longest description the three tools accept (OpenCode's limit, the strictest). */
export const MAX_DESCRIPTION = 1024
/** The longest name, and its shape: lowercase letters, digits and single hyphens (backend NAME_RE). */
const MAX_NAME = 64
const NAME_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/

/** Why a name is refused, in the page's words; empty when it is fine. */
export function nameProblem(name: string): string {
  const v = name.trim()
  if (!v) return t('Type a name.')
  if (v.length > MAX_NAME) return t('Up to {n} characters.', { n: MAX_NAME })
  if (!NAME_RE.test(v)) return 'Lower-case letters, digits and single hyphens. Up to 64 characters.'
  return ''
}

/** Why a description is refused; empty when it is fine. */
export function descriptionProblem(description: string): string {
  return description.length > MAX_DESCRIPTION ? t('Up to {n} characters.', { n: MAX_DESCRIPTION }) : ''
}

export function splitSkillMd(text: string): SkillFields {
  const md = (text ?? '').replace(/\r\n/g, '\n').trim()
  if (!md.startsWith('---\n')) return { name: '', description: '', extra: '', body: md }
  const end = md.indexOf('\n---', 4)
  if (end < 0) return { name: '', description: '', extra: '', body: md }
  const head = md.slice(4, end)
  const body = md.slice(end + 4).replace(/^\n+/, '')
  const [name, rest] = take(head.split('\n'), 'name')
  const [description, extra] = take(rest, 'description')
  return { name, description, extra: extra.join('\n').trim(), body }
}

/** One scalar out of the block's lines, quotes taken off, a folded value joined; the lines that are left. */
function take(lines: string[], key: string): [string, string[]] {
  const at = lines.findIndex((l) => l.startsWith(`${key}:`))
  if (at < 0) return ['', lines]
  let to = at + 1
  while (to < lines.length && /^\s+\S/.test(lines[to]!)) to++
  const parts = [lines[at]!.slice(key.length + 1).trim(), ...lines.slice(at + 1, to).map((l) => l.trim())]
  const value = parts.join(' ').trim()
  const clean = value.replace(/^["'](.*)["']$/s, '$1').replace(/^[>|][-+]?\s*/, '').trim()
  return [clean, [...lines.slice(0, at), ...lines.slice(to)]]
}

/** A value as one YAML line: bare when it reads as a string, quoted when YAML would read something else. */
function scalar(v: string): string {
  const one = v.replace(/\s+/g, ' ').trim()
  return /^[\s"'[\]{}#&*!|>%@`]|: |\s#|:$|^(true|false|null|yes|no|on|off|~)$|^[-+]?\d/i.test(one) ? JSON.stringify(one) : one
}

export function buildSkillMd({ name, description, extra, body }: SkillFields): string {
  const rest = extra.trim()
  return `---\nname: ${scalar(name)}\ndescription: ${scalar(description)}\n${rest ? `${rest}\n` : ''}---\n\n${body.trim()}\n`
}

/** The same skill, whatever the file's spelling: what the page compares to know if there is anything to save. */
export function fieldsEqual(a: SkillFields, b: SkillFields): boolean {
  const one = (v: string) => v.replace(/\s+/g, ' ').trim()
  return one(a.name) === one(b.name) && one(a.description) === one(b.description)
    && a.extra.trim() === b.extra.trim() && a.body.trim() === b.body.trim()
}
