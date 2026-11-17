/**
 * The mock notes of the design round. Every note is invented: the long
 * sign-in audit and the navigator message are about a made-up app
 * (Tidepool) and project, with made-up paths, commits and ids; the others
 * follow the shape of work in this repository. Mock only — this file does
 * not ship with the feature.
 */
import auth from './mock/app-auth.md?raw'
import navigator from './mock/app-navigator.md?raw'
import variants from './mock/ep-variants.md?raw'
import spec from './mock/ep-spec.md?raw'
import review from './mock/ep-review.md?raw'
import release from './mock/release-actions.md?raw'
import short from './mock/short.md?raw'
import type { Entity } from '../render/env'
import { parseNote, type Block, type Note, type NoteSource } from './model'

/** The short notes live in one file, each after a `<!-- key -->` line. */
const SHORT: Record<string, string> = Object.fromEntries(
  short.split(/^<!-- (\w+) -->\n/m).slice(1).reduce<Array<[string, string]>>((acc, part, i, all) => {
    if (i % 2 === 0) acc.push([part, all[i + 1] ?? ''])
    return acc
  }, []),
)

export type { Entity }

/** What a chip shows: the live title and status of a task, entry point, decision or publish card. */
export const ENTITIES: Record<string, Entity> = Object.fromEntries(([
  ['tk_fc2d244e', 'Вход: удаление аккаунта, Sign in with Apple, выход', 'todo', '2512-tidepool-app'],
  ['tk_8453174b', 'Вход: код для поддержки, один адрес в двух провайдерах', 'doing', '2512-tidepool-app'],
  ['tk_dfa5fe39', 'Аудит Tidepool перед релизом, затем аудит входа', 'doing', '2512-tidepool-app'],
  ['tk_84803453', 'Убрать синхронизацию записей в облако', 'done', '2512-tidepool-app'],
  ['tk_cb6a3d8e', 'Нужна ли синхронизация в первой версии', 'todo', '2512-tidepool-app'],
  ['tk_e651be1a', 'Сайт: /delete-account, privacy, лендинг, деплой', 'todo', '2512-tidepool-app'],
  ['tk_d4764113', 'Сайт: ссылка на удаление только из privacy', 'doing', '2512-tidepool-app'],
  ['tk_088197f8', 'Починить 5 дефектов аудита', 'doing', '2512-tidepool-app'],
  ['tk_244e12d5', 'Сверить бриф с состоянием кода', 'done', '2512-tidepool-app'],
  ['tk_a54585e7', 'Тесты на эмуляторе и реальных телефонах', 'todo', '2512-tidepool-app'],
  ['tk_75dddb6c', 'Закрытый тест в Google Play: 12 тестеров, 14 дней', 'todo', '2512-tidepool-app'],
  ['tk_03cac607', 'Выложить релиз в tidepool-release', 'todo', '2512-tidepool-app'],
  ['tk_73b03012', 'Хранение ключей подписи и доступ агентов', 'todo', '2512-tidepool-app'],
  ['tk_5ec7c96b', 'Чистка кода после первой версии', 'todo', '2512-tidepool-app'],
  ['tk_d34f8ae2', 'Лента снимков экранов для выбора вариантов', 'doing', '2512-tidepool-app'],
  ['tk_9b20e4f1', 'Перенести навигатор Tidepool в точки входа', 'todo', 'merkhet'],
  ['tk_51b87348', 'Точки входа: круг дизайна и сборка', 'done', 'merkhet'],
  ['tk_6c1f2a90', 'Полки: стрелки снимков с клавиатуры', 'todo', 'merkhet'],
  ['tk_0d8e3b57', 'Тест: два чата пишут одну тему', 'todo', 'merkhet'],
  ['tk_2c7d90a1', 'Выпуск Slightly Parallel на GitHub', 'doing', 'merkhet'],
  ['tk_3e544086', 'Заметки: круг дизайна', 'doing', 'merkhet'],
  ['ep_7a31c0de', 'Точки входа', 'active', 'merkhet'],
  ['ep_1b5e9d40', 'Tidepool: аккаунты и вход', 'active', '2512-tidepool-app'],
  ['ep_c40a7e22', 'Выпуск Slightly Parallel', 'active', 'merkhet'],
  ['ep_5e81b3f6', 'Usage: токены и лимиты', 'paused', 'merkhet'],
  ['dc_4e0a9b12', 'Точки входа: вариант A с полками', 'major', 'merkhet'],
  ['dc_7f2c0a18', 'Лимиты плана не угадывать из токенов', 'normal', 'merkhet'],
  ['pu_5a0e7731', 'Slightly Parallel 1.0 на GitHub', 'draft', 'merkhet'],
] as const).map(([id, title, status, project]) => [id, { id, title, status, project }]))

/** Older notes a newer one replaces: the topic view says which account to trust. */
export const SUPERSEDED_BY: Record<string, string> = { nt_70c2a4e8: 'nt_b3e1a0c4' }

const SOURCES: NoteSource[] = [
  { id: 'nt_b3e1a0c4', project: '2512-tidepool-app', kind: 'context', task: 'tk_fc2d244e', chat: 'cc-5d1e7a20', entrypoint: 'ep_1b5e9d40',
    created: '2026-11-16T10:12:00', updated: '2026-11-16T11:15:00', versions: 2, body: auth },
  { id: 'nt_4f9a2b17', project: 'merkhet', kind: 'paste', task: 'tk_9b20e4f1', chat: 'cc-1fdabd6e', entrypoint: 'ep_7a31c0de',
    created: '2026-11-16T09:40:00', updated: '2026-11-16T09:40:00', versions: 1, body: navigator },
  { id: 'nt_19b0f4ac', project: 'merkhet', kind: 'actions', task: 'tk_2c7d90a1', chat: 'cc-0a8e33d1', entrypoint: 'ep_c40a7e22', publish: 'pu_5a0e7731',
    created: '2026-11-03T18:20:00', updated: '2026-11-14T21:05:00', versions: 4, body: release },
  { id: 'nt_e7d3c1b8', project: 'merkhet', kind: 'report', task: 'tk_51b87348', chat: 'cc-7b2d90e4', entrypoint: 'ep_7a31c0de',
    created: '2026-11-12T16:44:00', updated: '2026-11-12T16:44:00', versions: 1, body: review },
  { id: 'nt_2a6f0e91', project: 'merkhet', kind: 'plan', task: 'tk_51b87348', chat: 'cc-3c6a1f08', entrypoint: 'ep_7a31c0de',
    created: '2026-11-09T11:02:00', updated: '2026-11-10T09:30:00', versions: 3, body: spec },
  { id: 'nt_8c02d5e3', project: 'merkhet', kind: 'review', task: 'tk_51b87348', chat: 'cc-3c6a1f08', entrypoint: 'ep_7a31c0de',
    created: '2026-11-08T15:20:00', updated: '2026-11-08T15:20:00', versions: 1, body: variants },
  { id: 'nt_6d2e8f03', project: 'merkhet', kind: 'context', task: 'tk_3e544086', chat: 'cc-9e4b7a11', entrypoint: 'ep_5e81b3f6',
    created: '2026-11-01T14:30:00', updated: '2026-11-01T14:30:00', versions: 1, body: SHORT.usage ?? '' },
  { id: 'nt_a05c7e66', project: '2603-harbor-lights-video', kind: 'paste', task: '', chat: 'cc-d677db24',
    created: '2026-10-28T12:10:00', updated: '2026-10-28T12:10:00', versions: 1, body: SHORT.shorts ?? '' },
  { id: 'nt_3b8d1f52', project: 'merkhet', kind: 'report', task: '', chat: 'cc-44a1c9e0',
    created: '2026-10-20T19:55:00', updated: '2026-10-20T19:55:00', versions: 2, body: SHORT.tour ?? '' },
  { id: 'nt_70c2a4e8', project: '2512-tidepool-app', kind: 'context', task: 'tk_cb6a3d8e', chat: 'cc-2e90b6d4', entrypoint: 'ep_1b5e9d40',
    created: '2026-07-15T20:00:00', updated: '2026-07-15T20:00:00', versions: 1, body: SHORT.july ?? '' },
]

/** Each note says which newer note replaces it, and which older ones it replaces, as the server's feed does. */
const REPLACES: Record<string, string[]> = {}
for (const [old, by] of Object.entries(SUPERSEDED_BY)) (REPLACES[by] ??= []).push(old)

export const NOTES: Note[] = SOURCES.map((s) => parseNote({ ...s, replacedBy: SUPERSEDED_BY[s.id], replaces: REPLACES[s.id] }))

/** "Now" for the mock: the morning the round was made. */
export const MOCK_NOW = new Date('2026-11-16T12:00:00')

/** Marks already made before the round: one paste note copied, one choice answered. */
export const SEED = {
  copied: { [NOTES.find((n) => n.id === 'nt_a05c7e66')!.sections.flatMap((s) => s.blocks).find((b): b is Extract<Block, { type: 'copy' }> => b.type === 'copy')!.id]: '2026-10-28T12:14:00' },
}
