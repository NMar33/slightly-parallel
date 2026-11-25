"""Every chat folder's path comes from one place: backend/backend/chatstore.py
(tk_d1d25a4d, step 1). A path built by hand elsewhere — ``root / "projects" /
p / "chats" / a``, a glob over ``projects/*/chats/*``, a project read off the
folder's depth — is what a later change of the layout would miss.

One hand-built path is allowed: the capture hook's ``_fallback_folder``, which
writes the turn when chatstore itself cannot be loaded."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The places scanned, relative to the repository. Tests are not scanned, nor
# the resolver itself.
SCANNED = ("backend/backend", "scripts", "sp.py")
EXEMPT_FILES = {"backend/backend/chatstore.py"}

# file → the functions in it that may build a chat path by hand. Exactly one
# entry, checked below: a second one is a second resolver.
ALLOWED: dict[str, tuple[str, ...]] = {
    "scripts/hooks/capture.py": ("_fallback_folder",),
}


def _docstrings(tree: ast.AST) -> set[int]:
    """ids of the string constants that are docstrings (the first statement
    of a module, class or function)."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def _is_chats(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "chats"


# Calls that join path parts: a "chats" argument is a chat path built by hand.
PATH_CALLS = {"join", "joinpath", "Path", "PurePath", "PurePosixPath", "PureWindowsPath"}


def _pieces(tree: ast.AST) -> set[int]:
    """ids of the string constants that are pieces of a built string: parts
    of an f-string, operands of a ``+``."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            out |= {id(v) for v in node.values if isinstance(v, ast.Constant)}
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            out |= {id(v) for v in (node.left, node.right) if isinstance(v, ast.Constant)}
    return out


def _path_part(node: ast.AST) -> bool:
    """``<x>.parts[...]`` (or ``parts[...]`` kept in a name) or ``<x>.name``:
    a piece of a path, compared."""
    if isinstance(node, ast.Subscript):
        v = node.value
        return (isinstance(v, ast.Attribute) and v.attr == "parts") or (isinstance(v, ast.Name) and v.id == "parts")
    return isinstance(node, ast.Attribute) and node.attr == "name"


def _attr_chain(node: ast.AST, names: tuple[str, ...]) -> bool:
    """node is ``<x>.names[0].names[1]…`` read from the outside in."""
    for name in names:
        if not (isinstance(node, ast.Attribute) and node.attr == name):
            return False
        node = node.value
    return True


class _Finder(ast.NodeVisitor):
    def __init__(self, docstrings: set[int], pieces: set[int]) -> None:
        self.docstrings = docstrings
        self.pieces = pieces
        self.stack: list[str] = []
        self.found: list[tuple[int, str, str]] = []   # (line, what, enclosing function)

    def _hit(self, node: ast.AST, what: str) -> None:
        self.found.append((getattr(node, "lineno", 0), what, self.stack[-1] if self.stack else ""))

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_Constant(self, node: ast.Constant) -> None:
        v = node.value
        if not isinstance(v, str) or id(node) in self.docstrings:
            return
        # A bare "/chats" is the page's route; as a piece of a built string,
        # or longer ("…/chats"), it is the folder.
        tail = v.endswith("/chats") and (v != "/chats" or id(node) in self.pieces)
        if "/chats/" in v or "chats/*" in v or v.startswith("chats/") or tail:
            self._hit(node, f"string {v!r}")

    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        if name in PATH_CALLS and any(_is_chats(a) for a in node.args):
            self._hit(node, f'{name}(…, "chats", …)')
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        sides = [node.left, *node.comparators]
        if any(_is_chats(x) for x in sides) and any(_path_part(x) for x in sides):
            self._hit(node, 'a path part compared with "chats"')
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Div) and (_is_chats(node.left) or _is_chats(node.right)):
            self._hit(node, '/ "chats"')
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "chats_dir":
            self._hit(node, ".chats_dir")
        if node.attr == "name":
            v = node.value
            if isinstance(v, ast.Subscript) and isinstance(v.value, ast.Attribute) and v.value.attr == "parents" \
                    and isinstance(v.slice, ast.Constant) and v.slice.value == 2:
                self._hit(node, ".parents[2].name")
            if _attr_chain(v, ("parent", "parent", "parent")):
                self._hit(node, ".parent.parent.parent.name")
            elif _attr_chain(v, ("parent", "parent")):
                self._hit(node, ".parent.parent.name")
        self.generic_visit(node)


def violations(source: str) -> list[tuple[int, str, str]]:
    """Every hand-built chat path in ``source``: (line, what, the function it is in)."""
    tree = ast.parse(source)
    finder = _Finder(_docstrings(tree), _pieces(tree))
    finder.visit(tree)
    return finder.found


def _files() -> list[Path]:
    out: list[Path] = []
    for rel in SCANNED:
        p = REPO / rel
        out += [p] if p.is_file() else sorted(p.rglob("*.py"))
    return [f for f in out if f.relative_to(REPO).as_posix() not in EXEMPT_FILES
            and "tests" not in f.relative_to(REPO).parts and "node_modules" not in f.parts]


def test_no_chat_path_is_built_outside_chatstore() -> None:
    bad = []
    for f in _files():
        rel = f.relative_to(REPO).as_posix()
        allowed = ALLOWED.get(rel, ())
        for line, what, func in violations(f.read_text(encoding="utf-8")):
            if func not in allowed:
                bad.append(f"{rel}:{line} {what}" + (f" (in {func})" if func else ""))
    assert not bad, "chat paths built by hand; use backend/backend/chatstore.py:\n" + "\n".join(bad)


def test_the_allow_list_is_the_one_fallback_and_it_exists() -> None:
    assert ALLOWED == {"scripts/hooks/capture.py": ("_fallback_folder",)}, \
        "one hand-built chat path is allowed, the hook's fallback; a second entry is a second resolver"
    tree = ast.parse((REPO / "scripts/hooks/capture.py").read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert "_fallback_folder" in names, "capture._fallback_folder is gone: the allow-list names nothing"


def test_the_guard_sees_each_form() -> None:
    seeded = {
        "string /chats/": 'x = root.glob("projects/*/chats/a/meta.json")\n',
        "string chats/*": 'x = "chats/*"\n',
        "f-string": 'x = root.glob(f"projects/*/chats/{a}/meta.json")\n',
        "div right": 'x = root / "projects" / p / "chats"\n',
        "div left": 'x = "chats" / p\n',
        "chats_dir": "x = pf.chats_dir\n",
        "parents[2]": "x = meta.parents[2].name\n",
        "parent x3": "x = p.parent.parent.parent.name\n",
        "parent x2": "x = folder.parent.parent.name\n",
        "os.path.join": 'x = os.path.join(root, "projects", p, "chats", a)\n',
        "Path(...)": 'x = Path(root, "projects", p, "chats", a)\n',
        "PurePath(...)": 'x = PurePath("projects", p, "chats")\n',
        "joinpath": 'x = root.joinpath("projects", p, "chats", a)\n',
        "concat": 'x = str(root) + "/projects/" + p + "/chats"\n',
        "f-string tail": 'x = f"{root}/projects/{p}/chats"\n',
        "string tail": 'x = "projects/alpha/chats"\n',
        "chats/ head": 'x = "chats/" + a\n',
        "f-string head": 'x = f"chats/{a}/meta.json"\n',
        "parts[2]": 'x = rel.parts[2] == "chats"\n',
        "parts reversed": 'x = "chats" != rel.parts[-2]\n',
        "parts kept": 'parts = rel.parts\nx = len(parts) >= 3 and parts[2] == "chats"\n',
        "name compared": 'x = p.parent.name == "chats"\n',
    }
    for what, src in seeded.items():
        assert violations(src), f"the guard misses: {what}"
    # Not caught: docstrings, the word in other places, a shorter climb.
    clean = ('"""Lives at projects/<p>/chats/<agent>/."""\n'
             'def f():\n    """Reads projects/*/chats/*."""\n    return {"chats": 1}["chats"]\n'
             'x = p.parent.name\ny = p.parents[1].name\nz = "/chats"\n'
             'etag_for(key, store, "tasks", "chats")\narea = "chats" if kind == "chats" else "rest"\n')
    assert violations(clean) == []
    # The function a hit sits in is named, for the allow-list.
    assert violations('def _fallback_folder(r, p, a):\n    return r / "projects" / p / "chats" / a\n')[0][2] \
        == "_fallback_folder"
