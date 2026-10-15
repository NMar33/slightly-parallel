"""AGENT-README.md is a briefing an agent acts on — every path and route it
cites must exist, or the briefing lies. This test keeps it honest."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend.server import create_app

REPO = Path(__file__).resolve().parents[2]
README = REPO / "AGENT-README.md"

# Repo-relative paths in backticks: files or dirs that must exist.
_PATH_RE = re.compile(r"`((?:backend|frontend|scripts|docs|fixtures|prompts|templates)/[^`\s]+|[A-Za-z0-9_.-]+\.(?:md|sh|py|example))`")
# API routes in backticks or curl lines.
_ROUTE_RE = re.compile(r"(?<![\w/])(/api/[a-z0-9\-/{}<>_*]+)")


_GENERATED = {"AGENTS.md", "CLAUDE.md"}


def _cited_paths(text: str) -> set[str]:
    out = set()
    for m in _PATH_RE.finditer(text):
        p = m.group(1).rstrip("/")
        # `<lens>.csv`, `*.md` and glob-ish mentions are illustrative, not paths.
        if any(ch in p for ch in "<>*{}") or p.endswith((".csv", ".json", ".toml")):
            continue
        # Written by Setup into a project and git-ignored here: named, never shipped.
        if p in _GENERATED:
            continue
        out.add(p)
    return out


def _exists(p: str) -> bool:
    if (REPO / p).exists():
        return True
    # Bare file names (`db.py`) are cited inside a folder listing; accept
    # them when a file of that name lives anywhere under the repo's code.
    if "/" not in p:
        return any(
            hit.is_file() and "node_modules" not in hit.parts and ".venv" not in hit.parts
            for hit in REPO.rglob(p)
        )
    return False


def _cited_routes(text: str) -> set[str]:
    return {m.group(1).rstrip("/.,;)") for m in _ROUTE_RE.finditer(text)}


def test_agent_readme_cites_only_existing_paths() -> None:
    text = README.read_text(encoding="utf-8")
    missing = sorted(p for p in _cited_paths(text) if not _exists(p))
    assert not missing, f"AGENT-README.md cites paths that do not exist: {missing}"


def test_agent_readme_cites_only_registered_routes(tmp_path: Path) -> None:
    text = README.read_text(encoding="utf-8")
    app = create_app(data_root=tmp_path / "data", watch=False)
    with TestClient(app) as c:
        registered = {p for p in c.get("/openapi.json").json()["paths"] if p.startswith("/api/")}

    def matches(cited: str) -> bool:
        # `/api/<lens>` and `/api/time/*` style mentions are families; check
        # that at least one registered route sits under the concrete prefix.
        concrete = re.split(r"[<{*]", cited)[0].rstrip("/")
        if cited in registered:
            return True
        return any(r == concrete or r.startswith(concrete + "/") for r in registered)

    unknown = sorted(c for c in _cited_routes(text) if not matches(c))
    assert not unknown, f"AGENT-README.md cites unregistered routes: {unknown}"


def test_agent_readme_names_the_capture_tell() -> None:
    text = README.read_text(encoding="utf-8")
    assert "your agent_id is" in text
    assert "SLIGHTLY-PARALLEL.md" in text and "#scan" in text


def test_both_readmes_teach_the_current_write_path() -> None:
    """Cold readers believe these two files. They once taught numbered levels
    and HTTP writes by agents, and pages written from them described the
    product as it had been."""
    from backend.mcp import TOOLS

    for name in ("README.md", "AGENT-README.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert "MCP" in text and "write_entry" in text, name
        assert not re.search(r"\bL[1-4]\b|level contract|pyramid|(?<![\w#])/scan\b", text, re.I), name
    agent = README.read_text(encoding="utf-8")
    # A tool named in backticks with a tool-like name must be a real tool.
    cited = set(re.findall(r"`((?:scan|standup|architecture)_(?:material|page|postpone)|write_entry|task_[a-z_]+)`", agent))
    assert cited and cited <= set(TOOLS), sorted(cited - set(TOOLS))
    for skill in re.findall(r"`((?:make|keep|log|write|daily|task)-[a-z-]+)`", agent + (REPO / "README.md").read_text(encoding="utf-8")):
        assert (REPO / "templates" / "skills" / skill / "SKILL.md").is_file(), skill
