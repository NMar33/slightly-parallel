---
id: sp__all01
name: Ship Slightly Parallel v0.1
started_date: 2608-06
ended_date: 2608-08
projects: _all,pdr-framework-dev
time_budget_h: 30
status: closed
confidence_pct: 75
---

## L2 — Theme + intent

Get Slightly Parallel 8-lens dashboard shipped in usable form. Editorial pages for all lenses, mutual tables, POST endpoints, the capture hooks primitive, docs, sidebar navigation. Sellable to corp as v0.1.

## L3 — Goals inside (declared 6, shipped 7 — 1 unplanned bonus)

- SCAN editorial + mutual storage · shipped
- Decisions editorial + drill · shipped
- Goals editorial + tree · shipped
- Standup editorial · shipped
- Activity editorial · shipped
- Vision + Problems (2 new lenses in one turn) · shipped
- Rules lens + Lenses upgrade (bonus — not planned) · shipped
- Lenses page with flip switcher + workflow graph · shipped

## L4 — Retro

**Shipped**: 8 lenses × 4-layer editorial pages, mutual storage, POST endpoints, sidebar polish, the capture hooks + docs, Slightly Parallel branded + LICENSE. The operator can use daily.

**Slipped**: agent-instructions doc (variants exist, winner not picked), Docker (deferred to v0.2), CI (deferred to v0.2), Overview + per-project React pages not fully editorial-parity.

**Calibration diff**: predicted 75%, hit ~90% (bonuses landed). Under-confident again.

**Rules learned**:
- rl__all1ee05 · No parallel subagents sharing mutable files (learned hard way — server.py + App.tsx overwrites)
- rl__all2ff06 · Log every turn, never batch-log

**Next sprint focus**: v0.2 polish — Docker, CI, calibration deep-dive, retros as first-class entity.
