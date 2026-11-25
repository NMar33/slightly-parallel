/**
 * One reading of a comma-separated project list: a task's `projects`, and an
 * agent's or a chat's (the projects that list it, origin first).
 *
 * The twin of the server's `entitylib.project_codes` / `project_lists`: spaces
 * anywhere are dropped, blanks skipped, case kept, each code once. One table,
 * testdata/project_codes/table.json, holds both to the same answers.
 */

export function projectCodes(value: string | readonly string[] | null | undefined): string[] {
  const text = Array.isArray(value) ? value.map(String).join(',') : String(value ?? '')
  const out: string[] = []
  for (const part of text.replace(/ /g, '').split(',')) {
    if (part && !out.includes(part)) out.push(part)
  }
  return out
}

/** Whether the list names `code`, as a whole code: `seo` never reads `seo-fight`. */
export function projectLists(value: string | readonly string[] | null | undefined, code: string): boolean {
  return Boolean(code) && projectCodes(value).includes(code)
}

/** A row's projects: its `projects` when the server sent them, else its own `project`. */
export function rowProjects(row: { project?: string | null; projects?: string | null }): string {
  return row.projects || row.project || ''
}

/** Whether a project's list shows this row: its own, or one of the projects that list it. */
export function listedIn(row: { project?: string | null; projects?: string | null }, code: string): boolean {
  return projectLists(rowProjects(row), code)
}
