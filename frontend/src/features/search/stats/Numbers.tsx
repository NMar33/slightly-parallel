import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { kindWord } from '../../../lib/searchHits'
import { fetchOverview } from './api'
import { Block, DayBand, Distribution, NearTable, RankTable, RoleSplit, Stat } from './parts'
import {
  countOf, dayBars, daysWith, distribution, medianBucket, nearWords, num, pct, ranked,
} from './rollups'
import { t, tn } from '../../../i18n/scope/system'

/**
 * What is in here, in numbers.
 *
 * The search page shows this while nothing is searched, and again for a
 * word once one is. Every figure comes from `/api/search/overview`, which
 * the server counted when it built the index, so showing this costs a
 * lookup.
 */

const WORDS_SHOWN = 30
const NEAR_SHOWN = 30

function kindLabel(kind: string): string {
  return t(kindWord(kind))
}

export function Numbers({ query, showDays = false }: { query: string; showDays?: boolean }): JSX.Element | null {
  const [, setParams] = useSearchParams()
  const q = query.trim()
  const allQuery = useQuery({
    queryKey: ['search-overview', ''],
    queryFn: ({ signal }) => fetchOverview('', signal),
  })
  // The word's numbers: the previous word's stay up while the next one is
  // counted, and are never shown under a word whose read failed.
  const wordQuery = useQuery({
    queryKey: ['search-overview', q],
    queryFn: ({ signal }) => fetchOverview(q, signal),
    enabled: !!q,
    placeholderData: keepPreviousData,
  })
  const all = allQuery.data ?? null
  const word = q && !wordQuery.isError ? wordQuery.data ?? null : null

  const shown = word ?? all
  if (allQuery.isError) return <p className="text-13 text-status-red">{t('The numbers could not be read.')}</p>
  if (q && wordQuery.isError) return <p className="text-13 text-status-red">{t('The numbers for “{q}” could not be read.', { q })}</p>
  if (!shown) return null

  const rows = shown.rows
  const bars = dayBars(all?.days ?? [], word?.days ?? [])
  const words = ranked(shown.words.map((w) => [w.word, w.n] as [string, number]), WORDS_SHOWN)
  const near = nearWords(word?.near ?? [], NEAR_SHOWN)
  const kinds = ranked(shown.kinds, 12)
  const projects = ranked(shown.projects, 6)
  const chats = ranked(shown.chats, 12)
  const buckets = distribution(shown.turn_lengths)
  const turns = countOf(shown.kinds, 'turn')
  const user = countOf(shown.roles, 'user')
  const agent = countOf(shown.roles, 'agent')
  const median = medianBucket(shown.turn_lengths)
  const carried = daysWith(bars)
  const pick = (w: string) => setParams({ q: w })

  return (
    <div className="flex flex-col gap-24 min-w-0">
      <div className="grid grid-cols-2 gap-10 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label={t('Rows')} value={num(rows)} note={q ? t('of {n}', { n: num(all?.rows ?? 0) }) : t('entries, map parts, chat turns')} />
        <Stat label={t('Chat turns')} value={num(turns)} note={t('{pct} of the rows', { pct: pct(turns, rows) })} />
        <Stat
          label={t('Words said')}
          value={num(shown.words_said)}
          note={turns ? t('{n} a turn', { n: num(Math.round(shown.words_said / turns)) }) : t('in chat turns')}
        />
        <Stat label={t('Days')} value={num(q ? carried : bars.length)} note={q ? t('of {n}', { n: num(bars.length) }) : t('first to last')} />
        <Stat label={t('Kinds')} value={num(shown.kinds.length)} note={kinds[0] ? t('most are {kind}', { kind: kindLabel(kinds[0].label).toLowerCase() }) : ''} />
        <Stat label={t('Median turn')} value={median || '—'} note={t('words in a turn')} />
      </div>

      {showDays && (
        <Block
          title={q ? t('Days “{q}” was said on', { q }) : t('Days')}
          note={q ? t('{a} of {b}', { a: num(carried), b: num(bars.length) }) : tn(bars.length, '{n} day', '{n} days', { n: num(bars.length) })}
        >
          <DayBand bars={bars} word={q} />
        </Block>
      )}

      <div className="grid grid-cols-1 gap-24 min-w-0 lg:grid-cols-3">
        <div className="flex flex-col gap-24 min-w-0">
          {q ? (
            <Block title={t('Words used with “{q}”', { q })} note={near.length ? t('{a} of {b}', { a: num(near.length), b: num(word?.near?.length ?? 0) }) : ''}>
              {near.length > 0 ? (
                <>
                  <NearTable rows={near} onPick={pick} />
                  <p className="text-11 text-tertiary">
                    {t('Rows is the number of matches that contain the word. Lift is how much more often it appears with “{q}” than elsewhere.', { q })}
                  </p>
                </>
              ) : (
                <p className="text-12 text-secondary">{t('No other word appears with this one often enough to rank.')}</p>
              )}
            </Block>
          ) : (
            <Block title={t('Words')} note={t('top {a} of {b}', { a: num(words.length), b: num(all?.words.length ?? 0) })}>
              <RankTable rows={words} what="word" unit="said" onPick={pick} />
              <p className="text-11 text-tertiary">
                {t('Number of times each word is used. Common English words are not counted. Click a word to search it.')}
              </p>
            </Block>
          )}
        </div>

        <div className="flex flex-col gap-24 min-w-0">
          <Block title={t('Kinds')} note={`${num(shown.kinds.length)}`}>
            <RankTable rows={kinds} what="kind" format={kindLabel} />
          </Block>
          <Block title={t('Projects')} note={`${num(shown.projects.length)}`}>
            <RankTable rows={projects} what="project" />
          </Block>
        </div>

        <div className="flex flex-col gap-24 min-w-0">
          <Block title={t('Words in a turn')} note={median ? t('middle {m}', { m: median }) : ''}>
            <Distribution buckets={buckets} />
            <p className="text-11 text-tertiary">{t('Length of a chat turn, in words. The marked row contains the middle value.')}</p>
          </Block>

          <Block title={t('Who said it')} note={tn(user + agent, '{n} turn', '{n} turns', { n: num(user + agent) })}>
            <RoleSplit user={user} agent={agent} />
          </Block>

          <Block title={t('Chats')} note={t('top {n} by turns', { n: num(chats.length) })}>
            <RankTable rows={chats} what="chat" unit="turns" />
          </Block>
        </div>
      </div>
    </div>
  )
}
