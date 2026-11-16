"""Libraries never import a router.

A router (backend/routers/*) answers HTTP: it reads the request, calls the
libraries and shapes the answer. A library (every other module under
backend/backend, server.py aside — it assembles the app) does the work and
may be called from a router, a hook, a thread or another library. When a
library reached into a router, the import cycle was dodged with an import
inside a function, and a change to an endpoint quietly changed #now, #done,
#undo or the smart timer. Fifteen such imports were moved out (the "Layers"
commits); this keeps the count at none. The allow-list is empty on purpose.

server.py counts as a router here: it imports every one, so a library that
imports it imports them all.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "backend"
ASSEMBLES_THE_APP = {"server.py"}
ALLOWED: set[tuple[str, str]] = set()


def _is_router(target: list[str]) -> bool:
    """``backend.routers…`` or ``backend.server``, as dotted parts."""
    return target[:2] in (["backend", "routers"], ["backend", "server"])


def _router_imports(path: Path, package: list[str]) -> list[tuple[int, str]]:
    """(line, what) for every import of a router in one library — top level
    or inside a function, absolute or relative, or by importlib/__import__.
    ``package`` is the library's own package as dotted parts (["backend"])."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            base = package[: len(package) - (node.level - 1)] if node.level else []
            target = base + (node.module.split(".") if node.module else [])
            names = [a.name for a in node.names]
            if _is_router(target) or any(_is_router(target + [n]) for n in names):
                out.append((node.lineno, f"from {'.' * node.level}{node.module or ''} import {', '.join(names)}"))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if _is_router(a.name.split(".")):
                    out.append((node.lineno, f"import {a.name}"))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
            arg = node.args[0] if node.args else None
            if (name in ("import_module", "__import__") and isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str) and ("routers" in arg.value or arg.value.endswith("server"))):
                out.append((node.lineno, f"{name}({arg.value!r})"))
    return out


def _libraries() -> list[tuple[Path, list[str]]]:
    """Every library module under backend/backend, with its package."""
    out = []
    for p in sorted(PACKAGE.rglob("*.py")):
        rel = p.relative_to(PACKAGE)
        if rel.parts[0] == "routers" or (len(rel.parts) == 1 and rel.name in ASSEMBLES_THE_APP):
            continue
        out.append((p, ["backend", *rel.parts[:-1]]))
    return out


def test_no_library_imports_a_router() -> None:
    found = [
        f"{p.relative_to(PACKAGE)}:{line}: {what}"
        for p, package in _libraries()
        for line, what in _router_imports(p, package)
        if (str(p.relative_to(PACKAGE)), what) not in ALLOWED
    ]
    assert found == [], "a library imports a router (move the code it needs into a library):\n" + "\n".join(found)


def test_importing_every_library_loads_no_router() -> None:
    """The same, at run time: import all the libraries in a fresh interpreter
    and no router module is loaded on the way."""
    import subprocess

    names = ["backend." + ".".join(p.relative_to(PACKAGE).with_suffix("").parts) for p, _ in _libraries()]
    code = ("import importlib, sys\n"
            f"for n in {names!r}: importlib.import_module(n)\n"
            "print(sorted(m for m in sys.modules if m.startswith('backend.routers') or m == 'backend.server'))")
    done = subprocess.run([sys.executable, "-c", code], cwd=PACKAGE.parent, capture_output=True,
                          text=True, encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]", done.stdout


def test_the_check_sees_every_spelling(tmp_path: Path) -> None:
    sample = tmp_path / "lib.py"
    sample.write_text(
        "from .routers.deps import a\n"                 # 1
        "from . import routers\n"                       # 2
        "import backend.routers.lenses\n"               # 3
        "def f():\n    from .routers import setup\n"    # 5
        "from backend import routers\n"                 # 6
        "from . import server\n"                        # 7
        "import importlib\nimportlib.import_module('backend.routers.x')\n"   # 9
        "__import__('backend.server')\n"                # 10
        "from .viewrows import attach_agent\n"          # fine
        "from backend import viewrows\n", encoding="utf-8")
    assert sorted(line for line, _ in _router_imports(sample, ["backend"])) == [1, 2, 3, 5, 6, 7, 9, 10]
    # One package down, `..routers` is the routers package; `.routers` is not.
    nested = tmp_path / "deep.py"
    nested.write_text("from ..routers.deps import a\nfrom .routers import b\n", encoding="utf-8")
    assert [line for line, _ in _router_imports(nested, ["backend", "sub"])] == [1]


def test_the_refusals_libraries_raise_keep_their_sentences() -> None:
    """integration_text and story_images refuse with ValueError (answered as
    422 with the sentence); the sentences are the ones the routes gave."""
    import base64

    import pytest

    from backend import integration_text as it
    from backend import limits, story_images
    with pytest.raises(ValueError, match=r"^\.claude/settings\.local\.json: `hooks\.Stop` is not a list$"):
        it._upsert_hooks('{"hooks": {"Stop": {}}}', "python3 x.py")
    with pytest.raises(ValueError, match=r"^not valid JSON: "):
        it._upsert_json_key("{oops", "mcpServers", "sp", {})
    with pytest.raises(ValueError, match=r"^the file is not a JSON object$"):
        it._upsert_json_key("[1]", "mcpServers", "sp", {})
    big = base64.b64encode(b"x" * (limits.MAX_IMAGE_BYTES + 1)).decode()
    with pytest.raises(ValueError, match=rf"^image 1: image is over {limits.MAX_IMAGE_BYTES // (1024 * 1024)}MB$"):
        story_images.checked_image({"ext": "png", "data_base64": big}, "image 1")
