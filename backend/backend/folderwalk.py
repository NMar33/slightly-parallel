"""One walk over a project folder, for everything that reads one.

The architecture page asks how alive a folder is; the map asks what the
program is written in. Each used to walk the same folder itself, with its
own skip list, and the two answered with different file counts of one
project. One walk now, read two ways: the cheap facts every caller needs,
and — only when a caller asks for it — what the text of the files says.

Nothing here writes. A folder that cannot be read is skipped, never raised.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SKIP = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".dart_tool", ".idea", ".gradle", "Pods", ".mypy_cache", ".pytest_cache",
    ".next", "target",
})
MAX_FILES = 200_000
NESTED_MAX = 12
NESTED_DEPTH = 4
READ_BYTES = 120_000
READ_DEPTH = 6
MANIFEST_DEPTH = 3

LANGUAGES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".mjs": "JavaScript", ".dart": "Dart", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".kt": "Kotlin", ".swift": "Swift", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".ipynb": "Jupyter notebook", ".sh": "Shell", ".sql": "SQL",
    ".html": "HTML", ".css": "CSS", ".md": "Markdown", ".tex": "TeX", ".r": "R", ".jl": "Julia",
}
TEXT_EXT = frozenset({
    ".py", ".ts", ".tsx", ".js", ".mjs", ".dart", ".go", ".rs", ".sh", ".yml", ".yaml",
    ".toml", ".json", ".env", ".cfg", ".ini", ".rb", ".php", ".kt", ".swift", ".java",
})
ENV_RE = re.compile(
    r"""(?:os\.environ(?:\.get)?\(?\[?\s*["']([A-Z][A-Z0-9_]{2,})["']"""
    r"""|process\.env\.([A-Z][A-Z0-9_]{2,})"""
    r"""|getenv\(\s*["']([A-Z][A-Z0-9_]{2,})["']"""
    r"""|\$\{?([A-Z][A-Z0-9_]{2,})\}?\b)""")
PORT_RE = re.compile(r"""(?:port\s*[=:]\s*|localhost:|127\.0\.0\.1:|0\.0\.0\.0:|:)(\d{4,5})\b""")
# Names a machine gives itself, not the program's own configuration.
ENV_IGNORED = frozenset({"PATH", "HOME", "USER", "PWD", "SHELL", "TERM", "LANG", "TMPDIR", "NODE_ENV"})
MANIFESTS = frozenset({
    "package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile",
    "environment.yml", "pubspec.yaml", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "build.gradle.kts", "Gemfile", "composer.json", "Package.swift", "CMakeLists.txt", "Makefile",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "Procfile", "fly.toml", "vercel.json", "netlify.toml", "codemagic.yaml", "app.json",
    "mkdocs.yml", "_config.yml", "hugo.toml", "next.config.js", "vite.config.ts", "vite.config.js",
    "tsconfig.json", ".env.example", "Taskfile.yml",
})
BUILD_GLOBS = (
    ".github/workflows/*", "*/.github/workflows/*", ".gitlab-ci.yml", "codemagic.yaml",
    "*/codemagic.yaml", "fastlane/*", "*/fastlane/*", "Dockerfile", "docker-compose*.yml",
    "Makefile", ".circleci/config.yml", "bitrise.yml",
)


@dataclass
class Folder:
    """What one walk saw. Paths are relative to the folder."""

    root: Path
    files: int = 0
    last_change: float = 0.0
    #: top-level folder name → {files, bytes, last}
    by_top: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(lambda: {"files": 0, "bytes": 0, "last": 0.0}))
    #: '.py' → how many
    suffixes: Counter = field(default_factory=Counter)
    #: 'Python' → how many
    languages: Counter = field(default_factory=Counter)
    #: (mtime, path), newest first
    newest: list[tuple[float, str]] = field(default_factory=list)
    #: folders holding a repository of their own
    nested: list[str] = field(default_factory=list)
    manifests: list[Path] = field(default_factory=list)
    test_folders: list[str] = field(default_factory=list)
    #: only when the walk was asked to read the text
    env_vars: Counter = field(default_factory=Counter)
    ports: Counter = field(default_factory=Counter)

    def build_files(self) -> list[str]:
        """The build and CI files, by name, wherever they sit."""
        return sorted({str(p.relative_to(self.root)) for g in BUILD_GLOBS for p in self.root.glob(g)})


def read_text(path: Path, limit: int = READ_BYTES) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def walk(root: Path, *, read_files: bool = False) -> Folder:
    """Walk ``root`` once. ``read_files`` also reads the text of source files
    for the names and ports the code carries, which costs a read per file."""
    out = Folder(root=root)
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        rel = here.relative_to(root)
        depth = len(rel.parts)
        if ".git" in dirnames and rel.parts and depth <= NESTED_DEPTH and len(out.nested) < NESTED_MAX:
            out.nested.append(str(rel))
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        if rel.parts and depth <= MANIFEST_DEPTH and any(w in here.name.lower() for w in ("test", "spec", "e2e")):
            out.test_folders.append(str(rel))
        top = rel.parts[0] if rel.parts else "(top level)"
        for name in filenames:
            path = here / name
            try:
                st = path.stat()
            except OSError:
                continue
            out.files += 1
            rec = out.by_top[top]
            rec["files"] += 1
            rec["bytes"] += st.st_size
            rec["last"] = max(rec["last"], st.st_mtime)
            out.last_change = max(out.last_change, st.st_mtime)
            suffix = path.suffix.lower()
            out.suffixes[suffix or "(none)"] += 1
            if suffix in LANGUAGES:
                out.languages[LANGUAGES[suffix]] += 1
            out.newest.append((st.st_mtime, str(path.relative_to(root))))
            if name in MANIFESTS and depth <= MANIFEST_DEPTH:
                out.manifests.append(path)
            if read_files and suffix in TEXT_EXT and depth <= READ_DEPTH:
                text = read_text(path)
                for m in ENV_RE.finditer(text):
                    found = next(g for g in m.groups() if g)
                    if found not in ENV_IGNORED:
                        out.env_vars[found] += 1
                for m in PORT_RE.finditer(text):
                    out.ports[m.group(1)] += 1
        if out.files > MAX_FILES:
            break
    out.newest.sort(reverse=True)
    return out
