"""The map of a program: every part as a row of one kind, and what connects
to what. For projects that are programs.

The architecture page (archpage.py) says what a project is in prose, for
any kind of project. The map is the table: a closed list of row kinds
(runtime, entry, surface, api, module, service, store, external, config,
build, deploy, test …), one template per kind of program saying which
kinds must be answered, one column set, and relations between rows with a
closed list of verbs. Trials on four repositories of four kinds (a web
service, a mobile app, research code, a command-line tool) gave maps with
every path found, every kind and verb in the vocabulary and every relation
naming a real row; the few faults were rows under the wrong kind, and
those became rules in the contract part.

Two layers, as everywhere: ``detect`` reads what a program can read with
no model (languages, manifests, build and CI files, compose services, test
folders, environment variables, ports); the agent's rows are checked here
against the vocabulary, the template and the folder. Versions live under
``projects/<project>/map/vNNN.json``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from . import folderwalk, frontmatter, gitwork, versioned
from .db import ViewStore
from .file_entries import project_path
from .date_utils import now_iso

PART = "47-map.md"
KINDS = ("runtime", "framework", "library", "entry", "surface", "api", "module", "service", "store",
         "data-in", "data-out", "external", "config", "build", "deploy", "test", "auth", "job", "model", "step")
VERBS = ("starts", "serves", "calls", "reads", "writes", "uses", "feeds", "builds", "deploys-to", "tests", "triggers")
TEMPLATES: dict[str, tuple[str, ...]] = {
    "web-service": ("runtime", "framework", "entry", "surface", "api", "module", "service", "store", "external",
                    "config", "build", "deploy", "test", "auth", "job"),
    "app": ("runtime", "framework", "entry", "surface", "module", "store", "external", "config", "build", "deploy", "test", "auth"),
    "tool": ("runtime", "entry", "surface", "module", "data-in", "data-out", "config", "build", "test", "external"),
    "library": ("runtime", "api", "module", "build", "test", "external"),
    "pipeline": ("runtime", "framework", "entry", "step", "data-in", "store", "data-out", "job", "config", "test", "external"),
    "research": ("runtime", "framework", "entry", "data-in", "model", "step", "data-out", "store", "external", "test"),
    "site": ("framework", "entry", "build", "deploy", "surface", "data-in"),
}
ROWS_MAX = 50
RELATIONS_MAX = 30
KIND_MAX = {"module": 10, "library": 6, "entry": 5, "surface": 6}
WHAT_WORDS = 12
NOTE_WORDS = 20
ROW_COLUMNS = ("kind", "name", "what", "where", "version", "evidence", "note")

def _git_facts(root: Path) -> dict[str, Any] | None:
    if not gitwork.git(root, "rev-parse", "--git-dir"):
        return None
    return {
        "commits": gitwork.git(root, "rev-list", "--count", "HEAD"),
        "last_commit": gitwork.git(root, "log", "-1", "--date=short", "--format=%ad %s"),
        "remote": (gitwork.git(root, "remote", "-v") or "").splitlines()[:1],
        "recent_subjects": (gitwork.git(root, "log", "-25", "--date=short", "--format=%ad %s") or "").splitlines(),
    }


def parse_manifest(p: Path) -> dict[str, Any]:
    """What one manifest declares: its name, version, dependencies, scripts."""
    name, t = p.name, folderwalk.read_text(p, 60_000)
    out = {"file": str(p), "declares": {}}
    try:
        if name == "package.json":
            d = json.loads(t); out["declares"] = {"name": d.get("name"), "version": d.get("version"), "scripts": list((d.get("scripts") or {}).keys())[:20],
                "dependencies": sorted((d.get("dependencies") or {}).keys())[:60], "devDependencies": sorted((d.get("devDependencies") or {}).keys())[:40], "engines": d.get("engines")}
        elif name == "pyproject.toml":
            deps = re.findall(r'^\s*"([A-Za-z0-9_.\-\[\]]+)', t.split("dependencies")[1], re.M)[:60] if "dependencies" in t else []
            out["declares"] = {"name": (re.search(r'^name\s*=\s*"([^"]+)"', t, re.M) or [None, None])[1], "requires_python": (re.search(r'requires-python\s*=\s*"([^"]+)"', t) or [None, None])[1],
                               "dependencies": deps, "scripts": re.findall(r"^\[project\.scripts\]\n((?:.+\n)+)", t, re.M)[:1]}
        elif name == "requirements.txt":
            out["declares"] = {"dependencies": [l.split("==")[0].split(">=")[0].strip() for l in t.splitlines() if l.strip() and not l.startswith("#")][:60]}
        elif name == "pubspec.yaml":
            out["declares"] = {"name": (re.search(r"^name:\s*(\S+)", t, re.M) or [None, None])[1], "version": (re.search(r"^version:\s*(\S+)", t, re.M) or [None, None])[1],
                               "sdk": (re.search(r"sdk:\s*['\"]?([^'\"\n]+)", t) or [None, None])[1], "dependencies": re.findall(r"^  ([a-z_0-9]+):", t.split("dev_dependencies")[0], re.M)[:60]}
        elif name == "go.mod":
            out["declares"] = {"module": (re.search(r"^module\s+(\S+)", t, re.M) or [None, None])[1], "go": (re.search(r"^go\s+(\S+)", t, re.M) or [None, None])[1], "requires": re.findall(r"^\s+(\S+) v", t, re.M)[:40]}
        elif name == "Cargo.toml":
            out["declares"] = {"name": (re.search(r'^name\s*=\s*"([^"]+)"', t, re.M) or [None, None])[1], "dependencies": re.findall(r"^([A-Za-z0-9_\-]+)\s*=", t.split("[dependencies]")[1] if "[dependencies]" in t else "", re.M)[:40]}
        elif name.startswith(("docker-compose", "compose")):
            out["declares"] = {"services": re.findall(r"^  ([A-Za-z0-9_\-]+):\s*$", t.split("\nservices:")[1] if "\nservices:" in t else t, re.M)[:20]}
        elif name == "Dockerfile":
            out["declares"] = {"from": re.findall(r"^FROM\s+(\S+)", t, re.M), "expose": re.findall(r"^EXPOSE\s+(\d+)", t, re.M), "cmd": re.findall(r"^(?:CMD|ENTRYPOINT)\s+(.+)$", t, re.M)[-1:]}
        elif name == "Makefile":
            out["declares"] = {"targets": re.findall(r"^([A-Za-z0-9_\-]+):", t, re.M)[:30]}
        elif name == ".env.example":
            out["declares"] = {"variables": re.findall(r"^([A-Z][A-Z0-9_]+)=", t, re.M)}
        else:
            out["declares"] = {"first_lines": [l for l in t.splitlines()[:12] if l.strip()]}
    except Exception as e:
        out["declares"] = {"parse_error": str(e)[:80]}
    return out


def detect(root: Path) -> dict[str, Any]:
    """What a program can read from a repository with no model — from one
    walk (folderwalk.py), the same walk the architecture page reads."""
    seen = folderwalk.walk(root, read_files=True)
    return {
        "folder": str(root),
        "files": seen.files,
        "languages": seen.languages.most_common(8),
        "top_level_folders": [(k, int(v["files"])) for k, v in
                              sorted(seen.by_top.items(), key=lambda kv: -kv[1]["files"])[:25]],
        "manifests": [parse_manifest(p) for p in seen.manifests[:25]],
        "build_and_ci_files": seen.build_files(),
        "test_folders": seen.test_folders[:15],
        "env_variables_read_by_code": [v for v, _ in seen.env_vars.most_common(40)],
        "ports_named_in_code": [p for p, _ in seen.ports.most_common(8)],
        "nested_repositories": seen.nested,
        "git": _git_facts(root),
    }


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


KIND = "map"


def folder(store: ViewStore, project: str) -> Path:
    return versioned.folder(store, project, KIND)


def versions(store: ViewStore, project: str) -> list[dict[str, Any]]:
    def read(text: str) -> dict[str, Any]:
        doc = json.loads(text)
        m = doc.get("map") or {}
        return {"at": doc.get("at", ""), "agent_id": doc.get("agent_id", ""), "note": doc.get("note", ""),
                "template": m.get("template", ""), "rows_n": len(m.get("rows") or []), "shape": doc.get("shape", ""), "_map": m}

    return versioned.versions(store, project, KIND, read)


def _key(row: dict[str, Any]) -> str:
    return f"{row.get('kind', '')}:{str(row.get('name', '')).strip().lower()}"


def diff(new: dict[str, Any], old: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """Rows that came and went between two versions, by kind and name."""
    if not old:
        return {"added": [], "removed": []}
    a = {_key(r): r for r in new.get("rows") or []}
    b = {_key(r): r for r in old.get("rows") or []}
    return {"added": [a[k] for k in a if k not in b], "removed": [b[k] for k in b if k not in a]}


def current(store: ViewStore, project: str) -> dict[str, Any] | None:
    all_ = versions(store, project)
    if not all_:
        return None
    last = all_[-1]
    prev = all_[-2]["_map"] if len(all_) > 1 else None
    problems = check(store, project, last["_map"])
    return {**{k: v for k, v in last.items() if k != "_map"}, "map": last["_map"],
            "changes": diff(last["_map"], prev), "problems": problems, "by_kind": _by_kind(last["_map"])}


def _by_kind(m: dict[str, Any]) -> dict[str, int]:
    return dict(Counter(str(r.get("kind") or "") for r in m.get("rows") or []))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check(store: ViewStore, project: str, m: dict[str, Any]) -> list[str]:
    """What is wrong with a map, as sentences an agent can act on. Empty
    when the map is sound. Shape faults are refused before this runs."""
    root = project_path(store, project)
    rows = m.get("rows") or []
    names = {str(r.get("name") or "") for r in rows}
    out: list[str] = []
    template = str(m.get("template") or "")
    if template not in TEMPLATES:
        out.append(f"template must be one of {', '.join(TEMPLATES)}")
    else:
        answered = {str(r.get("kind") or "") for r in rows}
        for kind in TEMPLATES[template]:
            if kind not in answered:
                out.append(f"the {template} template asks for a `{kind}` row: add one, or one row `name: none` with what you searched")
    counts = Counter(str(r.get("kind") or "") for r in rows)
    for kind, cap in KIND_MAX.items():
        if counts.get(kind, 0) > cap:
            out.append(f"{counts[kind]} `{kind}` rows against at most {cap}: keep the ones a lead must know")
    for r in rows:
        kind, name = str(r.get("kind") or ""), str(r.get("name") or "")
        if kind not in KINDS:
            out.append(f"“{name}”: kind `{kind}` is not one of {', '.join(KINDS)}")
        if not name or not str(r.get("what") or "").strip():
            out.append(f"a row lacks `name` or `what`: {json.dumps(r)[:80]}")
        if len(str(r.get("what") or "").split()) > WHAT_WORDS:
            out.append(f"“{name}”: `what` is over {WHAT_WORDS} words")
        if len(str(r.get("note") or "").split()) > NOTE_WORDS:
            out.append(f"“{name}”: `note` is over {NOTE_WORDS} words")
        if not str(r.get("evidence") or "").strip():
            out.append(f"“{name}”: no `evidence` — computed, opened <file>, ran <command>, or per <file>, not checked")
        where = str(r.get("where") or "").strip()
        if not where:
            out.append(f"“{name}”: no `where`")
        elif root is not None and not re.match(r"^[a-z]+://", where):
            target = (root / where.split(":")[0]).resolve()
            # Inside the folder, not merely a name that starts the same way.
            if not target.is_relative_to(root.resolve()) or not target.exists():
                out.append(f"“{name}”: where `{where}` is not in the project folder")
    for rel in m.get("relations") or []:
        if str(rel.get("verb") or "") not in VERBS:
            out.append(f"relation {rel.get('from')} → {rel.get('to')}: verb `{rel.get('verb')}` is not one of {', '.join(VERBS)}")
        for end in ("from", "to"):
            if str(rel.get(end) or "") not in names:
                out.append(f"relation names “{rel.get(end)}”, which is not a row")
    return out


def write(store: ViewStore, project: str, agent_id: str, m: Any, note: str = "") -> dict[str, Any]:
    if not isinstance(m, dict) or not isinstance(m.get("rows"), list):
        raise ValueError("map is an object {template, rows: [...], relations: [...], notes: {...}}")
    if len(m["rows"]) > ROWS_MAX:
        raise ValueError(f"{len(m['rows'])} rows against at most {ROWS_MAX}: keep the ones a lead must know")
    if m.get("relations") not in (None, "") and not isinstance(m.get("relations"), list):
        raise ValueError("relations is a list of {from, verb, to}")
    if m.get("notes") not in (None, "") and not isinstance(m.get("notes"), dict):
        raise ValueError("notes is an object {shape, main_path, runs_on, not_found, not_read}")
    if len(m.get("relations") or []) > RELATIONS_MAX:
        raise ValueError(f"{len(m['relations'])} relations against at most {RELATIONS_MAX}")
    clean = {
        "template": str(m.get("template") or ""),
        "rows": [{k: str(r.get(k) or "").strip() for k in ROW_COLUMNS if r.get(k)} for r in m["rows"] if isinstance(r, dict)],
        "relations": [{k: str(r.get(k) or "").strip() for k in ("from", "verb", "to")} for r in (m.get("relations") or []) if isinstance(r, dict)],
        "notes": {k: str(v or "").strip() for k, v in (m.get("notes") or {}).items() if isinstance(k, str)} if isinstance(m.get("notes"), dict) else {},
    }
    problems = check(store, project, clean)
    hard = [p for p in problems if "not one of" in p or "lacks `name`" in p or "template must be" in p]
    if hard:
        raise ValueError("; ".join(hard[:6]))
    # The shape it was written against: what `architecture_status` compares.
    shape = shape_print(facts(store, project))
    with versioned.numbering(store, project, KIND):
        prior = versions(store, project)
        if prior and prior[-1]["_map"] == clean:
            return {"n": prior[-1]["n"], "existing": True, "warnings": problems[:30], "by_kind": _by_kind(clean)}
        n = versioned.next_number(prior)
        at = now_iso()
        doc = {"n": n, "at": at, "agent_id": agent_id, "note": versioned.note_of(note), "map": clean,
               "shape": shape}
        versioned.write(store, project, KIND, n, "json", json.dumps(doc, ensure_ascii=False, indent=1))
    return {"n": n, "existing": False, "at": at, "warnings": problems[:30], "by_kind": _by_kind(clean),
            "changes": {k: len(v) for k, v in diff(clean, prior[-1]["_map"] if prior else None).items()}}


def instructions(repo_root: Path) -> str:
    try:
        return frontmatter.body_of((repo_root / "prompts" / "contract" / PART).read_text(encoding="utf-8")).strip()
    except OSError:
        return ""


_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def facts(store: ViewStore, project: str) -> dict[str, Any]:
    root = project_path(store, project)
    if root is None:
        return {"note": "No folder is registered for this project (Setup)."}
    key = f"{store.data_root}|{project}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 120:
        return hit[1]
    out = detect(root)
    _cache[key] = (time.time(), out)
    return out


def shape_print(f: dict[str, Any]) -> str:
    """The program's shape in 12 hex: what a map row could change with — its
    languages, top folders, manifests and what they declare, build and test
    files, variables, ports, nested repositories. Not counts, not git: a
    commit that adds a line is not a new shape. '' with no folder."""
    if not f or "folder" not in f:
        return ""
    shape = {
        "languages": sorted(str(x[0]) for x in f.get("languages") or []),
        "top": sorted(str(x[0]) for x in f.get("top_level_folders") or []),
        "manifests": sorted(json.dumps({"file": Path(str(m.get("file") or "")).name,
                                        "declares": {k: v for k, v in (m.get("declares") or {}).items()
                                                     if k in ("name", "dependencies", "devDependencies", "scripts")}},
                                       sort_keys=True, default=str) for m in f.get("manifests") or []),
        "build": sorted(str(x) for x in f.get("build_and_ci_files") or []),
        "tests": sorted(str(x) for x in f.get("test_folders") or []),
        "env": sorted(str(x) for x in f.get("env_variables_read_by_code") or []),
        "ports": sorted(str(x) for x in f.get("ports_named_in_code") or []),
        "nested": sorted(str(x) for x in f.get("nested_repositories") or []),
    }
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()[:12]


def fingerprint(store: ViewStore) -> str:
    """For ETags: a map version is a file, so no view moves when one lands."""
    return versioned.fingerprint(store, KIND)


def forget() -> None:
    """Drop the computed facts — the data root changed, or a test moved on."""
    _cache.clear()
