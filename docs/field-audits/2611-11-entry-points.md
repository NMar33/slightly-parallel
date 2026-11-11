# Entry points — round 1 scout (2026-11-11)

Read only. Sources: both project folders, the three offkey worktrees, `00-agents/`, recorded chats (`chat.md`, non-helper), Claude Code memory for the WT folder, SP `GET /api/tasks|entrypoints|artifacts`, `ss -ltnp`.

## 0. What already exists (read this first)

1. **SP already has `#entrypoint`** (SLIGHTLY-PARALLEL.md l.377): one record per topic, text = What / Where / How / State / Next, ≤400 words, a second `#entrypoint` on the same topic = new version. 9 records exist in all of SP: 1 in WT (`ep_c8021fc2`, the site text console, a very good one), 0 in offkey, 7 in merkhet. **8 of 9 have `topic: null`**, so the list shows the raw message as the title ("имел ввиду", "<pasted_content id=…>", "tk_ad5bc0ca допиши к этой задаче…"). Two have 0 versions (never interpreted). Only `ep_446b4a5a` has a topic: "The films and the launch".
2. **The operator built this by hand before SP**, three times:
   - `00-entrypoints/2605-entrypoints.md` in WT (June): "Main folders", "Mockup EP" = `cd …; python3 -m http.server 8000` + URLs + **screenshots of each page**, plus "auth-flow", "Flow Map", "MVP" topics with pictures.
   - `00-agents/ENTRYPOINT.md` (July): a cross-project log — date · project · started from folder · agent/chat · time · what was done.
   - `00-agents/103-2604-bewrite.md` (July → 11-05, live, 191 lines): "быстрый вход" navigator. Header = **permanent entry points** (folders, run commands, preview ports, checklists, guides); below = dated blocks per chat: Сделано / Дальше / Вход. Plus satellite `103-2604-bewrite-seo.md` (one topic: SEO) and `00-agents/bewrite/2026-07-24-site-development.md` (deep topic file). A memory rule (`feedback_agents_entrypoint_log.md`) makes agents keep it.
   - offkey: `docs/HANDOFF-2026-11-06-library-and-features.md` — a handoff to the next agent: goal, worktrees, what's done, how to continue (commands), "last request of the user".
   So the shape is proven: **permanent things (how to open/run) + per-topic "where it stopped / next"**, with pictures.

## 1. Writing Tracker / Be Write (`103-2604-Writing-Tracker`, SP `2604-writing-tracker`)

Live now: nothing of this project listens (only SP :8123 and the source library :8134, see offkey).

| Name | Kind | How to open | How to start | Live now? | Evidence | Entry point? |
|---|---|---|---|---|---|---|
| getbewrite.com | deployed site (Firebase Hosting) | https://getbewrite.com (pages /writing-habit, /nanowrimo-calculator, /writing-statistics, /words-to-pages, /novel-word-count, /novel-calculator) | deploy by Nick (`firebase deploy`); checks `python3 tool/site/site_live_check.py` | yes (prod updated 11-05) | source `120-app-mvp/hosting/`; `103-2604-bewrite-seo.md` 11-05 "Выкатили всё накопленное с 26.07"; tasks tk_6799668f, tk_e651be1a, tk_659c3b2e (www DNS) | **Yes** — the product's public face; anchor of the SEO topic |
| Site text console ("наша тулза для работы над сайтом") | local web app (Vite+React) | http://127.0.0.1:8120 (keys: `g` overview, `l` journal, `s` site) | `cd 120-app-mvp/tool/console && npm run dev`; data: `python3 tool/console/build_data.py [--fresh] && node tool/console/shots.mjs`; test copy `CONSOLE_STATE=<f> npx vite --port 8122` | down | `ep_c8021fc2`; README in folder; commits 31ea3fe/4ac1a36 11-05; operator 11-05 cc-9da6becb T13: **"напомни, где лежит наша тулза для работы над сайтом"** — the exact use case; T19 asked for the journal "удобно будет потом восстанавливать" | **Yes** (already one; status, URL and start command should be fields, not prose) |
| Site preview | static server | http://localhost:8112/hub.html (`hosting/dev-hub.html`) | `python3 -m http.server 8112` in `120-app-mvp/hosting` | down | header of `103-2604-bewrite.md` | Part of the site EP (a "how to open locally" line), not its own |
| Site dev dashboard | static generated pages | `120-app-mvp/site-dashboard/index.html` (port 8113 in July) | `python3 tool/site/make_dashboard.py` | down; **stale** (built 07-26, "устарел… не знает про /writing-statistics", r1) | `ENTRYPOINT.md` 07-26; seo file 10-31 | Not now — mark stale under the site EP |
| Site analytics | external consoles | getbewrite.goatcounter.com · GSC `sc-domain:getbewrite.com` · Bing Webmaster | pull: `python3 tool/site/pull_analytics.py` (keys in `.env`) → `170-data/raw/…` | external, yes | operator pasted the URLs (cc-2a23af6c "СТЕНДАП 3 … я могу подключить клод код к консоли …"); tasks tk_7b20741a, tk_35227426 | Links inside the SEO EP |
| Site checks | scripts run by hand | — | `python3 tool/site/site_check.py`, `site_live_check.py`, `text_lint.py <f>`, `tool/gate.sh [--release]`, `tool/release_check.py` | n/a | wt-lint-guy / wt-app-dev blocks in `103-2604-bewrite.md` | "How" lines of the site/app EPs, not EPs |
| Review feed (лента проверки) | local web app, cross-project | http://127.0.0.1:8130/ | `python3 serve.py` in `00-agents/feed/`; cards `add_card.py be-write card.json` | down ("работает, пока жива эта сессия") | cc-141a8eed T14–15 (11-04), tk_d34f8ae2 doing; not a git repo; only Be Write cards | **Yes, but it is not this project's** — it lives in `00-agents/`; candidate for a cross-project/home EP |
| Flutter app Be Write | mobile app | APK `120-app-mvp/build/app/outputs/flutter-apk/app-release.apk`; Linux run | `flutter test test/`, e2e `flutter test integration_test/scenarios_test.dart -d linux`; backlog `120-app-mvp/BACKLOG.md` | n/a | navigator header; wt-app-manager/wt-app-dev chats; tasks tk_fc2d244e (auth), tk_75dddb6c (Play test), tk_634c6b09, tk_e79a7f20 | **Yes** — topic "app to the stores" |
| Mockups / design lab | static HTML | http://0.0.0.0:8000/design-lab/, share-*.html | `python3 -m http.server 8000` in `110-mockups/mockups-dev-v01-2604-10` (also `.claude/launch.json`: ports 5173/5174) | down; last touched May–July | `00-entrypoints/2605-entrypoints.md` with screenshots | Was an EP in June; now **stale** (archive EP) |
| ASO dashboard + handbook | static generated HTML | `140-aso/dashboard.html`, `asc.html`, `handbook.html`, `suggestions.html` | `python3 140-aso/tool/build_dashboard.py` (+ `pull.py`, `rank_tracker.py`) | file; data from 08-01, built 11-01 | r1: "Данные снимались один день, 1 августа, с 3 августа никто ничего не…"; data moved to `170-data/` | Maybe — dormant topic "store listings / ASO" |
| Reports per agent chat | md/html docs | `110-mockups/00-<date>-<chat>/response/rN-*.md` (e.g. wt-seo-guy r0–r5, wt-lint-guy r6-text-eda.html) | — | files | navigator: "детальные отчёты живут в …/response/" | Not EPs; they are the "Where" of topics |
| Agent briefs (roles) | docs | `00-agents/briefs/2610-30-wt-seo-guy.md`, wt-editor, wt-lint-guy, wt-app-manager, wt-app-dev | "как мне запустить сео парня?" → `cd …; claude`, `/rename wt-seo-guy`, `#now … Прочитай бриф …` (cc-658e44e3 T26) | — | 5 briefs 10-30…11-04 | Interesting: **"start" for a topic can be "start an agent with this brief"**, not a server |
| Data catalog | folder (own git) | `170-data/CATALOG.md` | — | — | navigator 11-03 | Part of SEO/linter EPs |
| claude.ai artifacts | published pages | https://claude.ai/artifact/DJxzX4AnCzSgqZk9fyzLfv (examples editor, 35 records; cc-fe288d47); https://claude.ai/artifact/A8eFdrDweaoZdSC9xNwNfs (text EDA report = `110-mockups/00-2610-31-wt-lint-guy/response/r6-text-eda.html`; cc-b525fd89) | — | yes (hosted) | operator: "как всегда html … сохраняем куда-то … но могу посмотреть в артефакте" | Links under a topic |
| SP artifact `sostoyanie-opusa` | doc | SP Artifacts page | — | — | ar_95422e62 | No (one-off) |
| DEVLOG.md, PARKING_LOT.md | docs | root / `130-scratchpad/` | — | — | navigator | Project-level "where we are", not a topic |

**Surprise:** the AI-linter (offkey) chats ai-linter, 2.0 … 9.0 (11 chats, the latest 11-10 23:18) are recorded under **this** project, because they were started in the WT folder. Most of the linter's history is in `2604-writing-tracker`, not in `ai-linter-2611-05`.

## 2. AI linter "offkey" (`106-2611-offkey*`, SP `ai-linter-2611-05`)

One repo, **three worktrees**: `106-2611-offkey` (branch `zcode-2.0`, last commit 11-02 — this is the SP project folder and the cwd of the recorded chats), `106-2611-offkey-cc` (`main`, the real line, last commit 11-10 22:46), `106-2611-offkey-merge` (`merge-codex`, 11-10 13:14). Plus pre-history in `103-…/110-mockups/00-2611-02-offkey/` (paper/lit, responses, research pages; touched 11-10).

Live now: `:8134` = source library (`source-library` beside the other projects, `library serve --port 8134`, up since 11-10 13:08). Nothing else.

| Name | Kind | How to open | How to start | Live now? | Evidence | Entry point? |
|---|---|---|---|---|---|---|
| offkey web app ("the linter's own site") | local web app (FastAPI + React `/app/`, tabs #scan, #manual, research pages) | http://127.0.0.1:8765/app/ ; http://127.0.0.1:8765/research-pages/drift.html | `.venv/bin/offkey serve` (in `106-2611-offkey-cc`; ui: `ui/` vite builds to `src/offkey/web/dist`) | down | README "local web app"; cc-c12697a9 T30: operator "вот что я подумал про http://127.0.0.1:8765/app/#scan …"; dist built 11-04 | **Yes** |
| Old variants A/B/C | local web app | http://127.0.0.1:8766/{a,b,c}/ | (old copy) | down; **dead** — "показывает старую копию с двумя нишами" (cc-c12697a9) | cc-47645c73 11-02 | No (dead; history only) |
| Article editor (редактор проспектов) | local web app | http://127.0.0.1:8124/ (`?view=drafts` — 261 saved versions of his text, `?view=article`) | `python3 article-editor/server.py --port 8124` | down | README; codex-e0d50088 11-05; tasks tk_bac9f57e, tk_1f9ee354, tk_be2a25ed | **Yes** — but **which checkout?** `article-editor/state/` (28 MB, untracked, his drafts) exists in all three worktrees, last changed 11-09 / 11-10 / 11-10 |
| EDA gallery (69 infographics) | local web app | http://127.0.0.1:8126/ (`?series=2…5`) | `python3 eda-gallery/server.py` | down | codex-e0d50088: "сделай … 20 инфографик … а я посмотрю, что-то может выберу"; rebuilt 11-10 in -merge | **Yes** (part of the article topic or own) |
| Source library | local web app, **separate project** | http://127.0.0.1:8134/ (cards `?section=articles&id=…`, abridgements `/files/artifacts/…/index.html`) | `cd source-library && ./library serve --port 8134`; CLI `./library search …` | **live** | codex-1266687f T23: "создается это как отдельный проект в <projects folder>. отсюда мы пока будем пользоваться прям напрямую"; T61–63; tasks tk_7c24ec00, tk_6f6a104c | **Yes, cross-project** — used from offkey, belongs to no SP project yet |
| Habr article / MTLD article | docs | `106-2611-offkey-cc/docs/article/article-02.md|.html`, `docs/mtld-article/`, `docs/article/work-02/` | — | files (11-10) | tasks tk_026c1734, tk_c16f65b8, tk_ef4ffc1c; goal "качественная статья на Хабр и опубликованный линтер" (handoff) | **Yes — topic "the article"** |
| Feature cards / audit | docs + status | `docs/features/STATUS.md` (318 signals: 301 drafts, 9 code-checked, 11 source-checked), `docs/feature-audit/` | `pytest` (2 520 passed) | files (11-10) | ai-linter-9.0 T15–16 (last status of the project) | **Yes — topic "verify features against sources"** |
| Linter for a pipeline (agent guide, CLI, MCP) | tool | `docs/agent-guide.md`; `offkey lint text.md --linter devto-sonnet --json`; MCP `offkey mcp` | venv install | n/a | tk_a4457719, tk_77063913 done | Part of the "offkey tool" EP (How) |
| Lab / experiment reports | generated files | `lab/results/*.md|html`, `reports/exp50-ladder.html`, `auc-ladder-dev.html` | `offkey` experiment commands | files, 11-02 | — | No, links |
| Handoff doc | doc | `106-2611-offkey/docs/HANDOFF-2026-11-06-…md` | — | — | cc-2aa87600 T1 opened with it | It *is* a hand-made EP — and it lives in the stale checkout |
| Russian / Habr corpus run | line of work | — | — | — | codex-1266687f; tk_26cc041d doing | Topic |

## 3. Topics he would come back to

Writing Tracker:
- **Site texts and SEO for getbewrite.com** — console :8120, site, analytics, r0–r5. Stopped 11-05: deployed, `/writing-habit` applied; 6 pages have variants waiting for his marking; Request indexing in GSC is his; check Google statuses in 2–3 weeks (~11-20). Next: tk_ddcc0b14, tk_4c17ff8e, tk_e3022f8e, www DNS tk_659c3b2e.
- **App to the stores** — Flutter app, gate, BACKLOG. Stopped 11-04: G1–G4 done, e2e flake open. Next: auth tk_fc2d244e, release build tk_634c6b09, Play closed test tk_75dddb6c, store forms tk_e79a7f20.
- **Review feed for agents' work** (cross-project, `00-agents/feed`) — 11-04 first version, Be Write only, down.
- **Site-monitoring tutorial video** — tk_9bc95f52/tk_9daa4959/tk_3e7f0f35 (overlaps the SP films).
- Dormant: ASO (08-01 data), mockups/design lab (June), monetisation tk_11aea166.

offkey:
- **The Habr article** (+ MTLD article) — editor :8124, gallery :8126, `docs/article`. Next: tk_ef4ffc1c (MTLD pole in the article), editor reviews tk_1f9ee354/tk_be2a25ed.
- **Feature verification against sources** — cards, STATUS.md, library :8134. Stopped 11-10: 11 of 318 source-checked. Next: drafts batch by batch; tk_0b56cce0 (drop 76 weak signals?).
- **The linter tool / web app** — :8765, agent guide, devto-sonnet linter (65/70, 4.7% false alarms).
- **Russian run on Habr** — tk_26cc041d.
- **Source library** — its own project now; tk_7c24ec00 asks whether it joins SP.

## 4. Proposed fields

For him (the card on the page):
- **name** — his word for it ("тулза для сайта", "the films and the launch"), plus a few aliases he might search for.
- **kind** — page/app · site (deployed) · document/folder · topic (a line of work). One EP may hold several "doors".
- **doors** — a list; each: label, URL or path, and for a local app: **start command + cwd + port**, and **live/down** checked by the server (port probe / HTTP HEAD for URLs / file exists for paths). "Open" when live, "Copy start command" when down.
- **state** — where it stopped (dated), one paragraph.
- **next** — items, ideally linked task ids (show their live column).
- **last used** — last chat / commit / file change touching it, computed, plus who (chat title).
- **picture** — a screenshot/thumbnail (he put screenshots in his own June EP file; the feed and console already take shots).
- **status** — active · dormant · stale/dead (archived but kept).

For an agent ("copy to agent" button):
- one text block: What / Where (exact paths, the **worktree/branch**) / How (commands) / State / Next / rules ("don't run X again", "drafts are his, never overwrite") / read-first files (handoff, README, brief) / related tasks, chats, artifacts, entries.
- **project folder and cwd to start in** (`cd …; claude`) and optionally **brief** to start with — the "как мне запустить сео парня" case.

Links: tasks, chats (by title), artifacts (SP and claude.ai), decisions, cores; versions (as `#entrypoint` already does).

## 5. Things that do not fit / surprises

- **Cross-project things**: the review feed (`00-agents/feed`) and the source library (`source-library`, live :8134) belong to no SP project. EP pages per project would miss them.
- **Chats land in the wrong project**: linter chats 2.0–9.0 are under Writing Tracker. Linking EP ↔ chats by project will mislead.
- **Worktrees**: offkey has three checkouts; the SP project points to the stale one (zcode-2.0, 11-02); the live line is `-cc`; the editor's untracked drafts (his own text) exist in all three with different dates. An EP must say *which* checkout, or it sends an agent to the wrong tree (it already happened: cc-2aa87600 T65, "как блядь такая проблема вообще возможна?").
- **Ports collide across projects**: 8124 is also SP's demo/old-build port in merkhet chats; 8120 vs 8112/8113 etc. A port alone is not an identity; the start command + cwd is.
- **Servers die with the chat** ("работает, пока жива эта сессия"); every local door is down right now except :8134. So "how to start" is not optional — it is the main field.
- **Stale vs live**: site-dashboard (07-26), ASO (08-01 data), mockups (June), :8766 variants. Worth keeping as dormant/dead, not deleting — the June EP file is history he made himself.
- **Existing `#entrypoint` records lack titles** (8 of 9 `topic: null`) and two have no text: the list shows message fragments. Whatever we design, the title has to be required or derived.
- **Hand-made navigator (`103-2604-bewrite.md`) is alive and agents are told by memory to update it** — two sources of truth if SP EPs arrive; decide: import, replace, or link.

## 6. Questions for the operator

1. One EP per *topic* (site texts & SEO) with several doors (console, site, analytics), or one per *thing you open* (the console) grouped under topics?
2. Should SP check live/down and offer to start a local server itself, or only show the command to copy?
3. Cross-project things (review feed, source library): a "home" list outside projects, or attached to every project that uses them?
4. `00-agents/103-2604-bewrite.md` and `00-entrypoints/`: import into SP EPs, keep as they are and link, or retire?
5. offkey worktrees: which is the project's folder for SP — `-cc` (main)? And where do your editor drafts live for good?
6. Linter chats recorded under Writing Tracker: move them to offkey, or leave and link?
7. Who writes and refreshes "where it stopped": you with `#entrypoint`, the agent at the end of each chat, or the server from the last chat/tasks on its own?
8. Do you want a screenshot on each EP card (as in your June file)?
