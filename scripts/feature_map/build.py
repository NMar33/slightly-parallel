#!/usr/bin/env python3
"""Feature map of Slightly Parallel — a repeatable infographic (tk_f6d3dcd9).

Run from the repository root:

    backend/.venv/bin/python scripts/feature_map/build.py

Options: --data-root PATH (default: ../00-agents-dashboard beside the
repository's parent), --no-png (JSON, HTML and changes only), --today
YYYY-MM-DD (count windows end there).

What it does:

1. EXTRACTS the features from the program: the command table and kept tags
   of the capture hook (scripts/hooks/capture.py), the contract's command
   table (SLIGHTLY-PARALLEL.md §2), the sp-help skill's table (groups, what,
   where), the MCP tools with their fields and required names
   (backend mcp.Translator.tool_defs over routers/schema_api.build_schema),
   the lenses with agent_write / agent_update / mutable fields, the task
   fields an agent may not set (routers/tasks_extra._OPERATOR_FIELDS), the
   operator-only acts (every operator_only(...) call in the routers), the
   skills (templates/skills and ~/.claude/skills), and the pages
   (frontend App.tsx routes, sidebar catalog, guide, Russian labels).
   What only a person can say lives in manual.yaml beside this file; each
   item is checked against the extraction and a mismatch is a warning.
2. COUNTS from the data root, read only (csv module; nothing is written
   there): every ledger by who wrote it (operator / program / agent) over
   all time, 30 and 7 days; the commands the operator typed in chats
   (helper chats left out); where tasks came from and what agents added.
3. WRITES notes/feature-map/out/: feature-map.json (the model),
   feature-map-YYMMDD.json (the dated copy), changes.md (against the
   previous run's JSON), feature-map.html (variant A: rows) and
   feature-map-b.html (variant B: cards), the flow sheets
   feature-map-flow-{a,b,c}.html (flow.py: river, star, metro — how a
   message becomes a record, 30-day volumes), and a PNG per sheet at 2x through
   Playwright from frontend/ (the render script is copied there for the run
   and deleted after), each also kept as a dated copy.
4. DRAWS the system maps (sysmap.py, layout in sysmap.yaml):
   feature-map-sys-metro.html (lines = processes and loops, stations =
   commands and records) and feature-map-sys-flow.html (sectors and the
   flows between them, like an economy's circular flow), each with a dated
   HTML copy and a PNG; a command of the program with no metro station is a
   warning.
5. DRAWS the command scene (scene.py, layout hand-kept there):
   feature-map-scene.html — terminal, hook, server, the task, the browser,
   the agent, AGENTS.md and skills, repository and CI on one sheet; each
   command one row from where it is typed to where it is seen.
6. DRAWS the series (series.py, texts hand-kept there): feature-map-series.html,
   five sheets — s1 the program as a cut through the earth (surface, SP
   layer, key mechanisms / cores, foundation; commands as drill shafts),
   s2-s5 a panel per command (tasks; your words; structure and rhythm; marks
   and service): what is typed and kept, what the program does, what the
   agent writes and how much, whether it can change it later, the record,
   where it is seen. A command of the program with no panel is a warning.
"""

from __future__ import annotations

import argparse
import hashlib
import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "notes" / "feature-map" / "out"
FRONTEND = REPO / "frontend"
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(HERE))
csv.field_size_limit(sys.maxsize)

WARNINGS: list[str] = []


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 1. Extraction from the program
# ---------------------------------------------------------------------------

def load_capture():
    """The capture hook as a module: its command table and tag patterns."""
    path = REPO / "scripts" / "hooks" / "capture.py"
    spec = importlib.util.spec_from_file_location("sp_capture_fm", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def extract_hook(cap) -> dict:
    keep = re.search(r"#\(([a-z|]+)\)", cap._KEEP_TAG_RE.pattern).group(1).split("|")
    anytag = re.search(r"#\(\?:([a-z|]+)\)", cap._ANY_TAG_RE.pattern).group(1).split("|")
    commands = {k: {"skill": v[0], "start": v[1]} for k, v in cap._COMMANDS.items()}
    src = (REPO / "scripts" / "hooks" / "capture.py").read_text(encoding="utf-8")
    notices = sorted(set(re.findall(r"\[slightly-parallel\] (#?[a-z][a-z-]*)", src)))
    return {"commands": commands, "kept_tags": keep, "harvested_tags": anytag,
            "evidence": True, "notices": notices}


def extract_contract() -> dict:
    text = (REPO / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    sec = text.split("## 2. Commands", 1)[1].split("## 3.", 1)[0]
    rows = {}
    for m in re.finditer(r"^\| `#([^`]+)` \| (.+?) \|$", sec, re.M):
        cmd = m.group(1).split(" <")[0].split(" {")[0].strip()
        rows[cmd] = m.group(2).strip()
    return {"commands": rows}


def parse_frontmatter(p: Path) -> dict:
    t = p.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---", t, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip().strip('"')
    return out


def extract_help(skills_dir: Path) -> dict:
    p = skills_dir / "sp-help" / "SKILL.md"
    if not p.exists():
        warn("sp-help skill not found: groups and 'where seen' come from manual.yaml only")
        return {}
    group = ""
    rows = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        g = re.match(r"^\*\*(.+?)\*\*", line)
        if g and not line.startswith("**Slightly"):
            group = g.group(1).split(" — ")[0]
        m = re.match(r"^\| `#([^`]+)`(.*?)\| (.+?) \|(?: (.+?) \|)?$", line)
        if m:
            base = m.group(1).split(" <")[0].strip()
            extras = re.findall(r"`-([a-z-]+)`", m.group(2))
            prefix = base.rsplit("-", 1)[0]
            row = {"group": group, "what": m.group(3).strip(), "where": (m.group(4) or "").strip()}
            for key in [base] + [f"{prefix}-{x}" for x in extras]:
                rows[key] = row
    return rows


def extract_backend() -> dict:
    from backend.routers.schema_api import build_schema
    from backend import mcp
    from backend.entitylib import OPERATOR_ONLY, AGENT_CREATE_REFUSED
    from backend.routers import tasks_extra
    from backend.tasklib import AGENT_TAGS
    from backend.keeplib import KINDS as KEPT
    from backend.marklib import KINDS as MARK_KINDS, MESSAGE_KINDS
    from backend.actors import HOUSE_ACTORS

    schema = build_schema()

    class _Api:  # the translator reads the schema the server would serve
        def get(self, _path):
            return schema

    tr = mcp.Translator(_Api(), str(REPO))
    tools = []
    for d in tr.tool_defs():
        props = (d.get("inputSchema") or {}).get("properties") or {}
        tools.append({"name": d["name"], "summary": mcp.TOOLS.get(d["name"], ""),
                      "fields": sorted(props), "required": (d.get("inputSchema") or {}).get("required", [])})
    lenses = []
    for l in schema["lenses"]:
        lenses.append({"name": l["name"], "base": l["base"], "agent_write": l["agent_write"],
                       "agent_update": l.get("agent_update", l["agent_write"]),
                       "text_fields": l["text_fields"], "mutable": l["mutable"],
                       "fields": sorted(l["fields"]), "when": l["when_to_use"]})
    # Operator-only acts: every operator_only(..., "what") call in the routers.
    acts = []
    for f in sorted((REPO / "backend" / "backend" / "routers").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"operator_only\((?:[^()]|\([^()]*\))*?,\s*\"([^\"]+)\"", src):
            if re.fullmatch(r"[a-z_]+", m.group(1)) or any(a["what"] == m.group(1) for a in acts):
                continue
            acts.append({"what": m.group(1), "file": f"routers/{f.name}"})
    return {
        "tools": tools,
        "lenses": lenses,
        "stamped": schema["stamped_by_server"],
        "vocab": schema["vocabularies"],
        "operator_only_lenses": {k: v for k, v in OPERATOR_ONLY.items()},
        "agent_create_refused": dict(AGENT_CREATE_REFUSED),
        "task_operator_fields": sorted(tasks_extra._OPERATOR_FIELDS),
        "task_mutable_fields": sorted(tasks_extra._MUTABLE_FIELDS),
        "agent_tags": list(AGENT_TAGS),
        "kept_kinds": list(KEPT),
        "mark_kinds": list(MARK_KINDS) + list(MESSAGE_KINDS),
        "house_actors": [a for a in HOUSE_ACTORS if a],
        "operator_only_acts": acts,
    }


def extract_skills(skills_dir: Path) -> list[dict]:
    out = {}
    for base, where in ((REPO / "templates" / "skills", "repo"), (skills_dir, "installed")):
        for p in sorted(base.glob("*/SKILL.md")):
            fm = parse_frontmatter(p)
            name = fm.get("name") or p.parent.name
            row = out.setdefault(name, {"name": name, "description": fm.get("description", ""),
                                        "repo": False, "installed": False, "sha": ""})
            if where == "repo" or not row["sha"]:
                row["sha"] = hashlib.sha1(p.read_bytes()).hexdigest()[:12]
            row[where] = True
    return sorted(out.values(), key=lambda r: r["name"])


def extract_pages() -> list[dict]:
    src = FRONTEND / "src"
    app = (src / "App.tsx").read_text(encoding="utf-8")
    routes = re.findall(r'<Route path="([^"]+)" element=\{<(\w+)', app)
    ru = {}
    for j in sorted((src / "i18n" / "ru").glob("*.json")):
        try:
            ru.update(json.loads(j.read_text(encoding="utf-8")))
        except ValueError:
            pass
    labels = {}
    cat = (src / "features" / "sidebar" / "catalog.ts").read_text(encoding="utf-8")
    for m in re.finditer(r"key: '([^']+)'.*?label: t\('([^']+)'\)", cat):
        labels[m.group(1)] = m.group(2)
    heads = (src / "lenses" / "heads.ts").read_text(encoding="utf-8")
    for m in re.finditer(r"base: '([^']+)', title: t\('([^']+)'\)", heads):
        labels.setdefault("/" + m.group(1), m.group(2))
    labels.setdefault("/chats", labels.get("/sessions", "Chats"))
    guide = (src / "features" / "guide" / "pages.ts").read_text(encoding="utf-8")
    gmap = {}
    for block in re.split(r"\n  \{\n", guide)[1:]:
        r = re.search(r"route: '([^']+)'", block)
        if not r:
            continue
        title = re.search(r"title: t\('([^']+)'\)", block)
        cmds = re.search(r"commands: \[([^\]]*)\]", block) or re.search(r"command: ('[^']+')", block)
        gmap[r.group(1)] = {"title": title.group(1) if title else "",
                            "commands": re.findall(r"'#([^']+)'", cmds.group(1)) if cmds else []}
    pages = []
    for path, comp in routes:
        label = labels.get(path) or gmap.get(path, {}).get("title") or ""
        pages.append({"route": path, "component": comp, "label": label,
                      "label_ru": ru.get(label, label), "commands": gmap.get(path, {}).get("commands", []),
                      "in_sidebar": path in labels})
    return pages


# ---------------------------------------------------------------------------
# 2. Counts from the data root (read only)
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def parse_day(v: str) -> date | None:
    v = (v or "").strip()
    m = re.match(r"^(\d{2})(\d{2})-(\d{2})$", v)
    try:
        if m:
            return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if re.match(r"^\d{4}-\d{2}-\d{2}", v):
            return date.fromisoformat(v[:10])
    except ValueError:
        return None
    return None


SERVER_ACTORS = {"stack", "resurface", "server", "auto", "system", "hook"}


def who_of(v: str) -> str:
    v = (v or "").strip()
    if v in ("", "operator"):
        return "o"
    if v in SERVER_ACTORS:
        return "s"
    return "a"


# key, csv, Russian name, who rule. Rules: kept (the operator's tagged
# message kept by the server), tag (marks: a tag or a button, both the
# operator's), s / o (one writer), col:<name> (classify that column),
# time (source auto is the program's timer).
LEDGERS = [
    ("tasks", "tasks.csv", "Задачи", "col:agent_id"),
    ("visions", "visions.csv", "Видения", "kept"),
    ("rules", "rules.csv", "Правила", "kept"),
    ("problems", "problems.csv", "Проблемы", "kept"),
    ("entrypoints", "entrypoints.csv", "Точки входа", "kept"),
    ("publish", "publish.csv", "Публикации", "kept"),
    ("prompts", "prompts.csv", "Промпты", "kept"),
    ("skills", "skills.csv", "Скиллы", "kept"),
    ("artifacts", "artifacts.csv", "Артефакты", "kept"),
    ("decisions", "decisions.csv", "Решения", "col:agent_id"),
    ("scans", "scans.csv", "Сканы", "col:agent_id"),
    ("files", "files.csv", "Файловые записи", "col:agent_id"),
    ("architecture", "architecture.csv", "Формы архитектуры", "col:agent_id"),
    ("standups", "standups.csv", "Стендапы", "col:agent_id"),
    ("notes", "notes.csv", "Заметки", "col:agent_id"),
    ("task_evidence", "task_evidence.csv", "Доказательства", "col:agent_id"),
    ("marks", "marks.csv", "Звёзды и закрепы", "tag"),
    ("done", "done.csv", "#done применён", "s"),
    ("now", "now.csv", "#now учтён", "s"),
    ("cores", "cores.csv", "Ядра", "col:actor"),
    ("core_notes", "core_notes.csv", "Заметки ядер", "col:author"),
    ("core_links", "core_links.csv", "Связи ядер", "col:actor"),
    ("entrypoint_ways", "entrypoint_ways.csv", "Способы входа", "col:actor"),
    ("entrypoint_stops", "entrypoint_stops.csv", "Где остановились", "col:author"),
    ("entrypoint_shots", "entrypoint_shots.csv", "Скриншоты тем", "col:author"),
    ("publish_attachments", "publish_attachments.csv", "Вложения публикаций", "col:actor"),
    ("undo", "undo.csv", "Запросы #undo", "s"),
    ("commit_links", "commit_links.csv", "Привязки коммитов", "col:actor"),
    ("story_requests", "story_requests.csv", "Запросы Story", "col:actor"),
    ("doc_versions", "doc_versions.csv", "Версии документов", "col:agent_id"),
    ("sprints", "sprints.csv", "Спринты", "o"),
    ("time_entries", "time_entries.csv", "Записи времени", "time"),
]
DATE_COLS = ("created_date", "created_at", "marked_at", "at")


def helper_chats(root: Path) -> set[str]:
    """Agent ids of helper chats: their "user" messages are written by the
    agent that started the helper, not by the operator."""
    out = set()
    for m in root.glob("projects/*/chats/*/meta.json"):
        try:
            meta = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("helper") or meta.get("helper_of"):
            out.add(m.parent.name)
    return out


def ledger_counts(root: Path, today: date) -> list[dict]:
    d7, d30 = today - timedelta(days=7), today - timedelta(days=30)
    helpers = helper_chats(root)
    out = []
    for key, fname, ru, rule in LEDGERS:
        path = root / fname
        if not path.exists():
            warn(f"ledger {fname} is not in the data root")
            continue
        rows = read_csv(path)
        c = {"key": key, "csv": fname, "ru": ru, "total": 0, "d30": 0, "d7": 0,
             "by": {"o": 0, "s": 0, "a": 0}, "by30": {"o": 0, "s": 0, "a": 0},
             "kept_from_helper": 0, "kept_from_helper30": 0, "archived": 0, "archived_from_helper": 0}
        dcol = next((k for k in DATE_COLS if rows and k in rows[0]), None)
        for r in rows:
            if (r.get("source") or "") == "demo":
                continue
            if rule == "kept":
                w = "o" if (r.get("source") or "") == "captured" else who_of(r.get("agent_id", ""))
            elif rule == "tag":
                w = "o"
            elif rule in ("s", "o"):
                w = rule
            elif rule == "time":
                w = "s" if (r.get("source") or "") == "auto" else "o"
            else:
                w = who_of(r.get(rule.split(":", 1)[1], ""))
            day = parse_day(r.get(dcol, "")) if dcol else None
            if (r.get("removed_at") or "").strip() or (r.get("off_at") or "").strip():
                continue
            if (r.get("archived_at") or "").strip() or (r.get("status") or "") == "archived":
                c["archived"] += 1
                c["archived_from_helper"] += (rule == "kept" and (r.get("source") or "") == "captured"
                                              and r.get("agent_id") in helpers)
                continue
            from_helper = rule == "kept" and (r.get("source") or "") == "captured" and r.get("agent_id") in helpers
            c["total"] += 1
            c["by"][w] += 1
            c["kept_from_helper"] += from_helper
            if day and day > d30:
                c["d30"] += 1
                c["by30"][w] += 1
                c["kept_from_helper30"] += from_helper
            if day and day > d7:
                c["d7"] += 1
        out.append(c)
    return out


def mark_kinds_count(root: Path, today: date, kinds: list[str]) -> dict:
    """Live marks of the given kinds (marks.csv holds stars, pins, carries, forks)."""
    d7, d30 = today - timedelta(days=7), today - timedelta(days=30)
    c = {"total": 0, "d30": 0, "d7": 0, "by": {"o": 0, "s": 0, "a": 0}}
    for r in read_csv(root / "marks.csv"):
        if r.get("kind") not in kinds or (r.get("removed_at") or "").strip():
            continue
        day = parse_day(r.get("marked_at", ""))
        c["total"] += 1
        c["by"]["o"] += 1
        c["d30"] += bool(day and day > d30)
        c["d7"] += bool(day and day > d7)
    return c


def task_origins(root: Path, today: date) -> dict:
    d7, d30 = today - timedelta(days=7), today - timedelta(days=30)
    tasks = read_csv(root / "tasks.csv")
    events = read_csv(root / "task_events.csv")
    ev = defaultdict(list)
    for e in events:
        ev[e["task_id"]].append(e)
    evidence = Counter(r["task_id"] for r in read_csv(root / "task_evidence.csv"))
    noted = Counter(r.get("task_id") for r in read_csv(root / "notes.csv") if r.get("task_id"))
    origins = Counter()
    origins30 = Counter()
    origins7 = Counter()
    server_wrote = 0
    parts = Counter()
    archived = sum(1 for t in tasks if (t.get("archived_at") or "").strip())
    tasks = [t for t in tasks if not (t.get("archived_at") or "").strip()]
    for t in tasks:
        tid = t["id"]
        es = ev.get(tid, [])
        origin = None
        for e in es:
            if e["field"] in ("started", "filed"):
                m = re.search(r"#(now(?:-[a-z-]+)?)", e["new_value"])
                if m:
                    origin = "#" + m.group(1)
                    if "agent wrote no card" in e["new_value"] or "written by the server" in e["new_value"]:
                        server_wrote += 1
                    break
        if origin is None:
            origin = "#task (агент)" if who_of(t.get("agent_id", "")) == "a" else "доска (вручную)"
        if origin.startswith("#now-"):
            origin = "#now-<колонка>"
        day = parse_day(t.get("created_date", ""))
        origins[origin] += 1
        if day and day > d30:
            origins30[origin] += 1
        if day and day > d7:
            origins7[origin] += 1
        ag = [e for e in es if who_of(e.get("actor", "")) == "a"]
        if origin == "#task (агент)" or any(e["field"] == "description" for e in ag):
            parts["описание от агента"] += 1
        if (t.get("agent_done_note") or "").strip() or any(e["field"] == "agent_report" for e in ag):
            parts["отчёт агента"] += 1
        if any(e["field"] == "comment" for e in ag):
            parts["комментарий агента"] += 1
        if evidence.get(tid):
            parts["доказательства"] += 1
        if noted.get(tid):
            parts["заметка агента"] += 1
        if any(e["field"] == "done_in_chat" for e in es):
            parts["закрыта #done"] += 1
        if any(e["field"] == "status" and who_of(e.get("actor", "")) == "a" for e in es):
            parts["статус менял агент"] += 1
    return {"total": len(tasks), "archived": archived, "origins": dict(origins.most_common()), "origins30": dict(origins30),
            "origins7": dict(origins7), "server_wrote_card": server_wrote, "parts": dict(parts.most_common())}


TURN_RE = re.compile(r"^## Turn (\d+) · (\S+)\n\*\*User\*\*: (.*?)(?=^\*\*Agent\*\*:|^## Turn |\Z)", re.M | re.S)


def typed_commands(root: Path, cap, today: date) -> dict:
    d7, d30 = today - timedelta(days=7), today - timedelta(days=30)
    shared = cap.shared
    total, d30n, d7n, helper30 = Counter(), Counter(), Counter(), Counter()
    msgs = {"all": 0, "d30": 0, "d7": 0, "with_command": 0, "with_command30": 0}
    chats = helpers = 0
    for chat in sorted(root.glob("projects/*/chats/*/chat.md")):
        meta = {}
        try:
            meta = json.loads((chat.parent / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        is_helper = bool(meta.get("helper") or meta.get("helper_of"))
        helpers += is_helper
        chats += not is_helper
        text = chat.read_text(encoding="utf-8", errors="replace")
        for m in TURN_RE.finditer(text):
            day = parse_day(m.group(2))
            said = m.group(3)
            heard = shared.command_text(said)
            found = set()
            for rx in (cap._COMMAND_RE, cap._KEEP_TAG_RE):
                for mm in rx.finditer(heard):
                    found.add(" ".join(mm.group(1).lower().split()))
            if cap._EVIDENCE_RE.search(heard):
                found.add("evidence")
            if re.search(r"(?<![\w#])#mute(?![\w-])", said, re.I):
                found.add("mute")
            recent = bool(day and day > d30)
            if is_helper:
                for f in found:
                    helper30[f] += recent
                continue
            msgs["all"] += 1
            msgs["d30"] += recent
            msgs["d7"] += bool(day and day > d7)
            if found:
                msgs["with_command"] += 1
                msgs["with_command30"] += recent
            for f in found:
                total[f] += 1
                if recent:
                    d30n[f] += 1
                if day and day > d7:
                    d7n[f] += 1
    return {"chats": chats, "helper_chats_skipped": helpers, "messages": msgs,
            "total": dict(total.most_common()), "d30": dict(d30n), "d7": dict(d7n),
            "helper_d30": {k: v for k, v in helper30.most_common() if v}}


def flow_counts(root: Path, today: date) -> dict:
    """What the flow sheets need beyond the ledgers, last 30 days: the agents'
    replies, token rows, commits tied to a chat stretch, notes on a task,
    kept messages interpreted, core links by kind, backups on disk."""
    d30 = today - timedelta(days=30)

    def recent(v: str) -> bool:
        day = parse_day((v or "")[:10])
        return bool(day and day > d30)

    out = {"replies": 0, "usage_rows": 0, "commits": 0, "notes_on_task": 0,
           "interpreted": 0, "core_links": {}, "backups": 0}
    shas = set()
    for chat in root.glob("projects/*/chats/*"):
        try:
            meta = json.loads((chat / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        helper = bool(meta.get("helper") or meta.get("helper_of"))
        for name, key in (("turns.jsonl", "start"), ("usage.jsonl", "at"), ("work.jsonl", "at")):
            p = chat / name
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if not recent(str(j.get(key) or "")):
                    continue
                if name == "turns.jsonl" and not helper:
                    out["replies"] += 1
                elif name == "usage.jsonl":
                    out["usage_rows"] += 1
                elif name == "work.jsonl":
                    shas.update(c for c in (j.get("commits") or []) if isinstance(c, str))
    out["commits"] = len(shas)
    for r in read_csv(root / "notes.csv"):
        if (r.get("task_id") or "").strip() and not (r.get("archived_at") or "").strip() \
                and recent(r.get("created_date", "")):
            out["notes_on_task"] += 1
    ver = re.compile(r"^## Version \d+ · (\d{4}-\d{2}) .*interpreted", re.M)
    for p in (root / "kept_versions").glob("*.md"):
        for m in ver.finditer(p.read_text(encoding="utf-8", errors="replace")):
            out["interpreted"] += recent(m.group(1))
    kinds = Counter()
    for r in read_csv(root / "core_links.csv"):
        if recent(r.get("at", "")) and not (r.get("removed_at") or "").strip():
            kinds[r.get("kind", "")] += 1
    out["core_links"] = dict(kinds)
    broot = Path(os.environ.get("SP_BACKUP_ROOT", "").strip() or (root.parent / f"{root.name}-backups"))
    if broot.is_dir():
        cut = datetime.combine(d30, datetime.min.time()).timestamp()
        out["backups"] = sum(1 for p in broot.glob("*.tar.gz") if p.stat().st_mtime > cut)
    return out


# ---------------------------------------------------------------------------
# 3. The model, checks, changes
# ---------------------------------------------------------------------------

def load_manual() -> dict:
    import yaml
    return yaml.safe_load((HERE / "manual.yaml").read_text(encoding="utf-8"))


def build_model(root: Path, today: date, skills_dir: Path) -> dict:
    cap = load_capture()
    hook = extract_hook(cap)
    contract = extract_contract()
    helpt = extract_help(skills_dir)
    be = extract_backend()
    skills = extract_skills(skills_dir)
    pages = extract_pages()
    manual = load_manual()

    code_cmds = set(hook["commands"]) | set(hook["kept_tags"]) | {"evidence"}
    tool_names = {t["name"] for t in be["tools"]}
    skill_names = {s["name"] for s in skills}
    routes = {p["route"]: p for p in pages}
    named = set()
    ledgers = ledger_counts(root, today)
    lmap = {l["key"]: l for l in ledgers}
    typed = typed_commands(root, cap, today)
    tasks = task_origins(root, today)

    # Every name a field may legitimately carry.
    known_fields = set()
    for l in be["lenses"]:
        known_fields |= set(l["fields"]) | set(l["text_fields"])
    for _k, fname, _ru, _r in LEDGERS:
        p = root / fname
        if p.exists():
            with open(p, encoding="utf-8", newline="") as fh:
                known_fields |= set(next(csv.reader(fh), []))
    known_fields |= {r["field"] for r in read_csv(root / "task_events.csv")}

    cards = []
    for item in manual["commands"]:
        for c in item["cmds"]:
            if c in named:
                warn(f"manual.yaml names #{c} twice")
            named.add(c)
            if c not in code_cmds:
                warn(f"manual.yaml: #{c} is not a command of the capture hook any more")
        for t in item.get("tools") or []:
            if t not in tool_names:
                warn(f"manual.yaml #{item['id']}: tool {t} is not served by the MCP server")
        if item.get("skill") and item["skill"] not in skill_names:
            warn(f"manual.yaml #{item['id']}: skill {item['skill']} not found")
        if item.get("page") and item["page"] not in routes:
            warn(f"manual.yaml #{item['id']}: page {item['page']} is not a route of App.tsx")
        if item.get("record") and item["record"] not in lmap:
            warn(f"manual.yaml #{item['id']}: ledger {item['record']} not counted")
        for f, _o in item.get("fields") or []:
            if re.fullmatch(r"[a-z_]+", f) and f not in known_fields:
                warn(f"manual.yaml #{item['id']}: field {f} is in no lens, ledger or task event")
        lens = next((l for l in be["lenses"] if l["base"].replace("-", "_") == (item.get("record") or "")
                     or l["name"] + "s" == (item.get("record") or "")), None)
        for f, o in item.get("fields") or []:
            if o == "o" and lens and lens["agent_update"] and f in lens["mutable"]:
                warn(f"manual.yaml #{item['id']}: field {f} is marked the operator's, but an agent may change it (lens {lens['name']})")
            if item.get("record") == "tasks" and o == "a" and f in be["task_operator_fields"]:
                warn(f"manual.yaml #{item['id']}: task field {f} is marked the agent's, but the server refuses it to agents")
        hook_skill = {hook["commands"].get(c, {}).get("skill") for c in item["cmds"]} - {"", None}
        if item.get("skill") and hook_skill and item["skill"] not in hook_skill:
            warn(f"manual.yaml #{item['id']}: skill {item['skill']} but the hook names {sorted(hook_skill)}")
        typed_n = {k: sum(typed[k].get(c, 0) for c in item["cmds"]) for k in ("total", "d30", "d7")}
        h = next((helpt[c] for c in item["cmds"] if c in helpt), {})
        rec = lmap.get(item.get("record") or "")
        if rec and item.get("record_kinds"):
            rec = mark_kinds_count(root, today, item["record_kinds"])
        page = routes.get(item.get("page") or "")
        cards.append({
            **item,
            "group_ru": manual["groups"].get(item["group"], item["group"]),
            "contract": next((contract["commands"][c] for c in item["cmds"] if c in contract["commands"]), ""),
            "help_what": h.get("what", ""), "help_where": h.get("where", ""), "help_group": h.get("group", ""),
            "hook_start": next((hook["commands"][c]["start"] for c in item["cmds"] if c in hook["commands"]), ""),
            "kept_by_server": any(c in hook["kept_tags"] or c in hook["harvested_tags"] for c in item["cmds"]),
            "page_ru": page["label_ru"] if page else "",
            "typed": typed_n,
            "record_counts": {k: rec[k] for k in ("total", "d30", "d7", "by")} if rec else None,
        })
    for c in sorted(code_cmds - named):
        warn(f"the hook has #{c}, manual.yaml has no item for it")
    for c in sorted(set(contract["commands"]) - code_cmds - {"problem solved"}):
        warn(f"the contract lists #{c}, the hook has no such command")
    for t in sorted(tool_names):
        if not any(t in (i.get("tools") or []) for i in manual["commands"] + manual["agent_own"]):
            pass  # readers and helpers need no card; listed in the inventory
    for b in manual["agent_own"]:
        for t in b.get("tools") or []:
            if t not in tool_names:
                warn(f"manual.yaml agent_own: tool {t} is not served")
    for s in skills:
        if s["repo"] and not s["installed"]:
            warn(f"skill {s['name']} is in templates/skills but not installed in {skills_dir}")
        if s["installed"] and not s["repo"] and s["name"] != "synced":
            warn(f"skill {s['name']} is installed but not in templates/skills")

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "today": today.isoformat(),
        "data_root": str(root),
        "commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True).stdout.strip(),
        "groups": manual["groups"],
        "cards": cards,
        "agent_own": manual["agent_own"],
        "server_own": manual["server_own"],
        "hook": hook,
        "contract_commands": contract["commands"],
        "tools": be["tools"],
        "lenses": be["lenses"],
        "stamped": be["stamped"],
        "operator": {
            "task_fields": be["task_operator_fields"],
            "task_mutable": be["task_mutable_fields"],
            "agent_tags": be["agent_tags"],
            "lenses": be["operator_only_lenses"],
            "agent_create_refused": be["agent_create_refused"],
            "acts": be["operator_only_acts"],
        },
        "kept_kinds": be["kept_kinds"],
        "mark_kinds": be["mark_kinds"],
        "skills": skills,
        "pages": pages,
        "counts": {"ledgers": ledgers, "typed": typed, "tasks": tasks, "flow": flow_counts(root, today)},
        "warnings": WARNINGS,
    }


def changes_md(prev: dict | None, cur: dict) -> str:
    lines = [f"# Изменения карты: {cur['today']}", ""]
    if not prev:
        lines.append("Первый запуск: сравнивать не с чем.")
        return "\n".join(lines) + "\n"
    lines.append(f"Сравнение с запуском {prev.get('generated_at')} (коммит {prev.get('commit')}) → "
                 f"{cur['generated_at']} (коммит {cur['commit']}).")

    def diff(name, a, b):
        add, rem = sorted(set(b) - set(a)), sorted(set(a) - set(b))
        if add or rem:
            lines.append(f"\n## {name}")
            lines.extend([f"- добавлено: {x}" for x in add] + [f"- убрано: {x}" for x in rem])

    def cmds(m):
        return [c for card in m.get("cards", []) for c in card["cmds"]] + list(m.get("hook", {}).get("commands", {}))

    diff("Команды", cmds(prev), cmds(cur))
    diff("MCP-инструменты", [t["name"] for t in prev.get("tools", [])], [t["name"] for t in cur["tools"]])
    diff("Линзы", [l["name"] for l in prev.get("lenses", [])], [l["name"] for l in cur["lenses"]])
    diff("Страницы", [p["route"] for p in prev.get("pages", [])], [p["route"] for p in cur["pages"]])
    diff("Скиллы", [s["name"] for s in prev.get("skills", [])], [s["name"] for s in cur["skills"]])
    diff("Поля MCP-инструментов", [f"{t['name']}.{f}" + ("*" if f in t.get("required", []) else "") for t in prev.get("tools", []) for f in t.get("fields", [])],
         [f"{t['name']}.{f}" + ("*" if f in t.get("required", []) else "") for t in cur["tools"] for f in t["fields"]])
    diff("Права линз (создаёт / меняет агент; изменяемые поля)",
         [f"{l['name']}: {l['agent_write']}/{l['agent_update']}; {','.join(l['mutable'])}" for l in prev.get("lenses", [])],
         [f"{l['name']}: {l['agent_write']}/{l['agent_update']}; {','.join(l['mutable'])}" for l in cur["lenses"]])
    diff("Таблица команд хука (скилл, с чего начать)",
         [f"{k}: {v.get('skill')} · {v.get('start')}" for k, v in prev.get("hook", {}).get("commands", {}).items()],
         [f"{k}: {v.get('skill')} · {v.get('start')}" for k, v in cur["hook"]["commands"].items()])
    ps = {x["name"]: x.get("sha") for x in prev.get("skills", [])}
    changed = [x["name"] for x in cur["skills"] if x["name"] in ps and ps[x["name"]] and ps[x["name"]] != x.get("sha")]
    if changed:
        lines.extend(["", "## Изменился текст скилла", ""] + [f"- {n}" for n in changed])
    diff("Поля задачи только оператора", prev.get("operator", {}).get("task_fields", []), cur["operator"]["task_fields"])
    pl = {l["key"]: l for l in prev.get("counts", {}).get("ledgers", [])}
    rows = []
    for l in cur["counts"]["ledgers"]:
        p = pl.get(l["key"])
        if p and p["total"] != l["total"]:
            rows.append(f"| {l['ru']} | {p['total']} | {l['total']} | {l['total'] - p['total']:+d} |")
    if rows:
        lines += ["", "## Записи", "", "| Вид | было | стало | Δ |", "|---|---|---|---|"] + rows
    pt, ct = prev.get("counts", {}).get("typed", {}).get("total", {}), cur["counts"]["typed"]["total"]
    rows = [f"| #{k} | {pt.get(k, 0)} | {v} | {v - pt.get(k, 0):+d} |" for k, v in ct.items() if v != pt.get(k, 0)]
    if rows:
        lines += ["", "## Набранные команды (всего)", "", "| Команда | было | стало | Δ |", "|---|---|---|---|"] + rows
    po = prev.get("counts", {}).get("tasks", {}).get("origins", {})
    rows = [f"| {k} | {po.get(k, 0)} | {v} |" for k, v in cur["counts"]["tasks"]["origins"].items() if v != po.get(k, 0)]
    if rows:
        lines += ["", "## Откуда задачи", "", "| Источник | было | стало |", "|---|---|---|"] + rows
    neww = sorted(set(cur["warnings"]) - set(prev.get("warnings", [])))
    if neww:
        lines += ["", "## Новые предупреждения", ""] + [f"- {w}" for w in neww]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 4. Render
# ---------------------------------------------------------------------------

def render_pngs(htmls: list[tuple[Path, str]], stamp: str) -> list[dict]:
    script = FRONTEND / ".feature-map-render.mjs"
    shutil.copy(HERE / "render.mjs", script)
    try:
        args = ["node", str(script)] + [f"{h}::{OUT / prefix}" for h, prefix in htmls]
        res = subprocess.run(args, cwd=FRONTEND, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise RuntimeError(res.stderr[-2000:])
        shots = json.loads(res.stdout.strip().splitlines()[-1])
    finally:
        script.unlink(missing_ok=True)
    for s in shots:
        p = Path(s["file"])
        dated = p.with_name(p.stem + f"-{stamp}.png")
        shutil.copy(p, dated)
        s["dated"] = str(dated)
    return shots


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-root", default=os.environ.get("SP_FEATURE_MAP_DATA") or str(REPO.parents[1] / "00-agents-dashboard"))
    ap.add_argument("--skills", default=str(Path.home() / ".claude" / "skills"))
    ap.add_argument("--today", default="")
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    root = Path(a.data_root)
    today = date.fromisoformat(a.today) if a.today else date.today()
    model = build_model(root, today, Path(a.skills))
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = today.strftime("%y%m%d")
    jpath = OUT / "feature-map.json"
    prev = None
    if jpath.exists():
        try:
            prev = json.loads(jpath.read_text(encoding="utf-8"))
        except ValueError:
            prev = None
    # changes.md compares with the last run, same day or not; the dated
    # copies keep the last run of each day.
    text = json.dumps(model, ensure_ascii=False, indent=1)
    jpath.write_text(text, encoding="utf-8")
    (OUT / f"feature-map-{stamp}.json").write_text(text, encoding="utf-8")
    (OUT / "changes.md").write_text(changes_md(prev, model), encoding="utf-8")

    import page
    htmls = []
    for variant, name in (("a", "feature-map.html"), ("b", "feature-map-b.html")):
        p = OUT / name
        p.write_text(page.render(model, variant), encoding="utf-8")
        htmls.append((p, f"feature-map-{variant}"))
    import flow
    for letter, variant in (("a", "river"), ("b", "star"), ("c", "metro")):
        p = OUT / f"feature-map-flow-{letter}.html"
        p.write_text(flow.render(model, variant), encoding="utf-8")
        htmls.append((p, f"feature-map-flow-{letter}"))
    import sysmap
    for cmd in sysmap.missing_commands(model):
        warn(f"sysmap: command #{cmd} exists in the program but has no metro station (add it to sysmap.yaml)")
    for kind in ("metro", "flow"):
        p = OUT / f"feature-map-sys-{kind}.html"
        text = sysmap.render(model, kind)
        p.write_text(text, encoding="utf-8")
        p.with_name(f"feature-map-sys-{kind}-{stamp}.html").write_text(text, encoding="utf-8")
        htmls.append((p, f"feature-map-sys-{kind}"))
    import scene
    for cmd in scene.missing_commands(model):
        warn(f"scene: command #{cmd} exists in the program but is not drawn (add it to scene.py ROWS)")
    p = OUT / "feature-map-scene.html"
    text = scene.render(model)
    p.write_text(text, encoding="utf-8")
    p.with_name(f"feature-map-scene-{stamp}.html").write_text(text, encoding="utf-8")
    htmls.append((p, "feature-map-scene"))
    import series
    for cmd in series.missing_commands(model):
        warn(f"series: command #{cmd} exists in the program but has no panel on sheets 2-5 (add it to series.py FAMILIES)")
    p = OUT / "feature-map-series.html"
    text = series.render(model)
    p.write_text(text, encoding="utf-8")
    p.with_name(f"feature-map-series-{stamp}.html").write_text(text, encoding="utf-8")
    htmls.append((p, "feature-map-series"))
    shots = [] if a.no_png else render_pngs(htmls, stamp)
    took = time.time() - t0
    for s in shots:
        print(f"{s['file']}  {s['width']}x{s['height']} css px")
    print(f"{len(model['cards'])} command cards, {len(model['tools'])} tools, {len(model['lenses'])} lenses, "
          f"{len(model['pages'])} pages, {len(model['skills'])} skills; {len(WARNINGS)} warnings; {took:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
