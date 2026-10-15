"""Scheduling helpers: one call per kind of thing that happens in a month.

Every helper takes the moment it happens and schedules the product's own
write for that moment (engine.Sim.at). Task references in text are written
``{tk:key}`` and resolved when the event runs, so a chat can name a task by
its key before the task's id exists.
"""

from __future__ import annotations

import base64
import zlib
from typing import Any

from engine import CLOCK, Chat, Sim, hhmm, mock_screen, timedelta, yymmdd

OP = "operator"


class World:
    def __init__(self, sim: Sim):
        self.sim = sim

    # -- tasks -------------------------------------------------------------

    def task(self, key: str, when, project: str, title: str, *, status: str = "backlog",
             lane: str = "", priority: str = "med", tags: str = "", impact: str = "",
             effort: str = "", due: str = "", desc: str = "", sprint: str = "",
             agent: str = "", evidence: bool = False, auto: bool = False,
             position: int | None = None, projects: str = "", remember: bool = False,
             novelty: str = "") -> None:
        sim = self.sim

        def run() -> None:
            body: dict[str, Any] = sim.stamp({
                "project": project, "agent_id": agent or OP, "title": title,
                "status": status, "lane": lane, "assignee": lane,
                "description": desc,
            })
            if agent:
                body["tags"] = tags
                r = sim.post("/api/tasks", body, agent=True)
            else:
                body.update({
                    # The board's axes are words: impact low / med / high, effort S / M / L.
                    # The rows below were written on a 1–5 scale; read them onto the words.
                    "priority": priority, "tags": tags,
                    "impact": {"1": "low", "2": "low", "3": "med", "4": "med", "5": "high"}.get(impact, impact),
                    "effort": {"1": "S", "2": "M", "3": "L", "4": "L", "5": "L"}.get(effort, effort),
                    "due_date": due, "sprint_id": sim.ids.get(sprint, "") if sprint else "",
                    "evidence_required": "yes" if evidence else "",
                    "auto_manage": "yes" if auto else "",
                    "position": position if position is not None else sim.rng.randint(1, 60) * 10,
                    "projects": projects, "remember": "yes" if remember else "",
                    "novelty": novelty,
                })
                r = sim.post("/api/tasks", body)
            sim.tasks[key] = r["metadata"]["id"]
            sim.task_rows[key] = {"project": project, "title": title}

        sim.at(when, run)

    def update(self, key: str, when, actor: str = OP, **fields: Any) -> None:
        sim = self.sim

        def run() -> None:
            body = dict(fields)
            if "sprint" in body:
                body["sprint_id"] = sim.ids[body.pop("sprint")]
            body["actor"] = actor
            sim.post(f"/api/tasks/{sim.tasks[key]}/update", body, agent=actor != OP)

        sim.at(when, run)

    def move(self, key: str, when, status: str, actor: str = OP) -> None:
        self.update(key, when, actor=actor, status=status)

    def flow(self, key: str, steps: list[tuple[Any, str]]) -> None:
        for when, status in steps:
            self.move(key, when, status)

    def report(self, key: str, when, agent_id: str, summary: str) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post(f"/api/tasks/{sim.tasks[key]}/report",
                                      {"agent_id": agent_id, "summary": sim.fill(summary)}, agent=True))

    def evidence(self, key: str, when, agent_id: str, items: list[dict]) -> None:
        sim = self.sim

        def run() -> None:
            out = []
            for i, it in enumerate(items):
                it = dict(it)
                if it.get("kind") == "image":
                    raw = mock_screen(it.pop("mock", "cards"), seed=zlib.crc32(key.encode()) % 97 + i)
                    it["data_base64"] = base64.b64encode(raw).decode()
                    it.setdefault("ext", "png")
                if it.get("kind") == "text":
                    it["body"] = sim.fill(it["body"])
                out.append(it)
            sim.post(f"/api/tasks/{sim.tasks[key]}/evidence", {"agent_id": agent_id, "items": out}, agent=True)

        sim.at(when, run)

    def round(self, key: str, when, text: str) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post(f"/api/tasks/{sim.tasks[key]}/turn",
                                      {"text": sim.fill(text), "actor": OP}))

    def link(self, a: str, b: str, kind: str, when) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post(f"/api/tasks/{sim.tasks[a]}/link",
                                      {"to": sim.tasks[b], "kind": kind, "actor": OP}))

    def note(self, key: str, when, ntype: str, body: str, template: str = "note", actor: str = OP) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post(f"/api/tasks/{sim.tasks[key]}/notes",
                                      {"type": ntype, "body": sim.fill(body), "template": template,
                                       "actor": actor}, agent=actor != OP))

    # -- sprints, milestones, calendar, time --------------------------------

    def sprint(self, key: str, when, name: str, theme: str, projects: str, start, end,
               budget: float, confidence: int, declared: int = 0) -> None:
        sim = self.sim

        def run() -> None:
            r = sim.post("/api/sprints", {
                "created_date": yymmdd(CLOCK.now), "agent_id": OP, "name": name, "theme": theme,
                "projects": projects, "started_date": yymmdd(start), "ended_date": yymmdd(end),
                "status": "active", "time_budget_h": budget, "bet_days": (end - start).days + 1,
                "confidence_pct": confidence, "goals_declared_n": declared,
                "l1": name,
            })
            sim.ids[key] = r["metadata"]["id"]

        sim.at(when, run)

    def end_sprint(self, key: str, when, retro: str, points: list[str], shipped: int) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post(f"/api/sprints/{sim.ids[key]}/update", {
            "status": "ended", "goals_shipped_n": shipped, "l2": retro, "l3": points,
            "actor": OP}))

    def milestone(self, key: str, when, project: str, title: str, outcome: str, check: str,
                  target: str, tasks: list[str], status: str = "active", position: int = 0) -> None:
        sim = self.sim

        def run() -> None:
            r = sim.post("/api/milestones", {
                "project": project, "title": title, "outcome": outcome, "check": check,
                "target_date": target, "status": status, "position": position or None,
                "tasks": [sim.tasks[t] for t in tasks], "actor": OP})
            sim.ids[key] = (r.get("milestone") or r.get("metadata") or r)["id"]

        sim.at(when, run)

    def milestone_update(self, key: str, when, **fields: Any) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post(f"/api/milestones/{sim.ids[key]}/update", {**fields, "actor": OP}))

    def calendar(self, when, project: str, kind: str, date: str, title: str, *, time: str = "",
                 end_time: str = "", body: str = "", people: str = "", task: str = "",
                 milestone: str = "", status: str = "open") -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post("/api/calendar/entries", {
            "project": project, "kind": kind, "date": date, "time": time, "end_time": end_time,
            "title": title, "body": body, "people": people,
            "task_id": sim.tasks.get(task, "") if task else "",
            "milestone_id": sim.ids.get(milestone, "") if milestone else "",
            "status": status, "actor": OP}))

    def timer(self, start, minutes: int, project: str, *, task: str = "", sprint: str = "",
              note: str = "", share: int = 100) -> None:
        sim = self.sim
        box: dict[str, str] = {}

        def begin() -> None:
            r = sim.post("/api/time/start", {
                "project": project, "task_id": sim.tasks.get(task, "") if task else "",
                "sprint_id": sim.ids.get(sprint, "") if sprint else "", "note": note,
                "share_pct": share, "actor": OP})
            box["id"] = (r.get("metadata") or r)["id"]

        sim.at(start, begin)
        sim.at(start + timedelta(minutes=minutes),
               lambda: sim.post(f"/api/time/{box['id']}/stop", {}))

    def auto_time(self, start, minutes: int, project: str, *, task: str = "", note: str = "") -> None:
        sim = self.sim
        end = start + timedelta(minutes=minutes)

        def run() -> None:
            sim.post("/api/time-entries", {
                "created_date": yymmdd(start), "created_time": hhmm(start), "project": project,
                "agent_id": OP, "started_at": start.isoformat(), "ended_at": end.isoformat(),
                "paused_at": "", "paused_total_sec": 0, "duration_min": minutes,
                "share_pct": 100, "task_id": sim.tasks.get(task, "") if task else "",
                "note": note, "source": "auto"})

        sim.at(end, run)

    # -- the lenses agents write ---------------------------------------------

    def decision(self, when, project: str, agent_id: str, decision: str, why: str,
                 alternatives: list[str] = (), weight: str = "normal", excerpt: str = "",
                 tags: str = "", source: str = "") -> None:
        sim = self.sim

        def run() -> None:
            body = sim.stamp({"project": project, "agent_id": agent_id,
                              "decision": sim.fill(decision), "why": sim.fill(why),
                              "alternatives": [sim.fill(a) for a in alternatives],
                              "alternatives_n": len(alternatives),
                              "weight": weight, "source": source or ("explicit" if excerpt else "auto")})
            if excerpt:
                body["excerpt"] = sim.fill(excerpt)
            r = sim.post("/api/decisions", body, agent=True)
            if tags:
                sim.post(f"/api/decisions/{r['metadata']['id']}/update", {"tags": tags, "actor": OP})

        sim.at(when, run)

    def scan(self, key: str, when, project: str, agent_id: str, summary: str, why: str,
             deltas: list[str], proof: str, scope: str) -> None:
        sim = self.sim

        def run() -> None:
            m = sim.get(f"/api/scans/material?project={project}&agent_id={agent_id}")
            c = m.get("counters") or {}
            r = sim.post("/api/scans", sim.stamp({
                "project": project, "agent_id": agent_id, "summary": sim.fill(summary),
                "why": sim.fill(why), "deltas": [sim.fill(d) for d in deltas], "proof": sim.fill(proof),
                "files_n": int(c.get("files_n") or 0), "lines_add": int(c.get("lines_add") or 0),
                "lines_del": int(c.get("lines_del") or 0), "decisions_n": int(c.get("decisions_n") or 0),
                "scope": scope}), agent=True)
            sim.ids[key] = r["metadata"]["id"]

        sim.at(when, run)

    def file_entry(self, when, project: str, agent_id: str, scan_key: str, summary: str,
                   narrative: str, per_file: list[str], paths: list[dict], since_first: bool = False) -> None:
        sim = self.sim

        def run() -> None:
            extra = {"commit_from": sim.repos[project].commits[0][0]} if since_first else {}
            sim.post("/api/files", sim.stamp({**extra,
                "project": project, "agent_id": agent_id, "summary": summary,
                "narrative": narrative, "per_file": per_file,
                "trigger_lens": "scan", "trigger_id": sim.ids[scan_key],
                "files_important_n": sum(1 for p in paths if int(p.get("importance", 0)) >= 4),
                "files_ignored_n": 0, "paths": paths}), agent=True)

        sim.at(when, run)

    def arch_form(self, when, project: str, agent_id: str, scan_key: str, changes: list[dict],
                  checked: list[str] | None = None) -> None:
        sim = self.sim
        groups = checked or ["does", "owes", "runs", "stores", "talks", "built with", "faces", "holds"]

        def run() -> None:
            chs = []
            for c in changes:
                c = dict(c)
                if "task" in c and c["task"] in sim.tasks:
                    c["task"] = sim.tasks[c["task"]]
                chs.append(c)
            sim.post("/api/architecture", sim.stamp({
                "project": project, "agent_id": agent_id, "trigger_lens": "scan",
                "trigger_id": sim.ids[scan_key], "checked": groups, "changes": chs}), agent=True)

        sim.at(when, run)

    def arch_page(self, when, project: str, agent_id: str, text: str, note: str) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post("/api/architecture/page", {
            "project": project, "agent_id": agent_id, "text": sim.fill(text), "note": note}, agent=True))

    def map(self, when, project: str, agent_id: str, m: dict, note: str) -> None:
        sim = self.sim
        sim.at(when, lambda: sim.post("/api/map", {
            "project": project, "agent_id": agent_id, "map": m, "note": note}, agent=True))

    def standup(self, when, project: str, agent_id: str, for_day, summary: str,
                movement: list[str], detail: str = "", deviation: list[str] | str = "",
                hours: float = 0, open_n: int = 0, closed_n: int = 0, blockers: int = 0) -> None:
        sim = self.sim
        dev = deviation if isinstance(deviation, str) else "\n".join(f"- {d}" for d in deviation)

        def run() -> None:
            sim.post("/api/standups", sim.stamp({
                "project": project, "agent_id": agent_id, "for_date": yymmdd(for_day),
                "summary": sim.fill(summary), "deviation": sim.fill(dev),
                "movement": [sim.fill(m) for m in movement], "detail": sim.fill(detail),
                "hours_today": hours, "goals_open_n": open_n, "goals_closed_n": closed_n,
                "blockers_n": blockers}), agent=True)

        sim.at(when, run)

    def interpret(self, kind: str, chat: Chat, turn: int, when, text: str, note: str = "",
                  agent_id: str = "") -> None:
        sim = self.sim
        base = {"vision": "visions", "rule": "rules", "problem": "problems"}[kind]

        def run() -> None:
            kid = sim.capture.keep_id(kind, chat.project, chat.agent_id, turn)
            sim.adopt()
            sim.post(f"/api/{base}/{kid}/interpretation",
                     {"text": sim.fill(text), "note": note, "agent_id": agent_id or chat.agent_id},
                     agent=True)

        sim.at(when, run)

    def kept_update(self, kind: str, chat: Chat, turn: int, when, **fields: Any) -> None:
        sim = self.sim
        base = {"vision": "visions", "rule": "rules", "problem": "problems", "skill": "skills",
                "artifact": "artifacts"}[kind]

        def run() -> None:
            kid = sim.capture.keep_id(kind, chat.project, chat.agent_id, turn)
            sim.adopt()
            sim.post(f"/api/{base}/{kid}/update", {**fields, "actor": OP})

        sim.at(when, run)
