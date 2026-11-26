"""The one table of MCP tool arguments (backend/mcp_args.py, tk_0b8a32d2).

The served schemas, the translator and the CI stand all read it; these tests
hold the served schemas to it, so no copy can drift."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from backend import mcp, mcp_args


def _tools_from(client) -> dict:
    schema = client.get("/api/schema").json()
    tr = mcp.Translator.__new__(mcp.Translator)
    tr.schema = schema
    tr.lenses = {l["name"]: l for l in schema["lenses"]}
    tr.vocab = schema.get("vocabularies", {})
    return {t["name"]: t for t in tr.tool_defs()}


def test_the_table_names_every_tool_served() -> None:
    assert set(mcp_args.TOOL_ARGS) == set(mcp.TOOLS)
    assert mcp_args.PROJECT_TOOLS <= set(mcp_args.TOOL_ARGS)


def test_every_served_schema_takes_exactly_the_tables_arguments(client) -> None:
    tools = _tools_from(client)
    for name, tool in tools.items():
        props = set(tool["inputSchema"].get("properties") or {})
        assert props == set(mcp_args.accepts(name)), name
        assert set(tool["inputSchema"].get("required") or []) <= props, name


def test_project_is_in_the_schema_of_the_project_tools_and_of_no_other(client) -> None:
    tools = _tools_from(client)
    with_project = {n for n, t in tools.items() if "project" in (t["inputSchema"].get("properties") or {})}
    assert with_project == set(mcp_args.PROJECT_TOOLS)
    for name in mcp_args.PROJECT_TOOLS:
        assert "project" in mcp_args.accepts(name)
    assert mcp_args.accepts("no_such_tool") == frozenset()


def test_no_tool_takes_a_stamped_name_and_each_is_refused_as_stamped(monkeypatch) -> None:
    import pytest

    assert not any(mcp_args.STAMPED & args for args in mcp_args.TOOL_ARGS.values())
    tr = mcp.Translator.__new__(mcp.Translator)
    tr.schema, tr.vocab = {}, {}
    tr.lenses = {"decision": {"base": "decisions", "mutable": ["status"], "fields": {"decision": {}},
                              "text_fields": ["decision"]}}
    for key in sorted(mcp_args.STAMPED):
        for args in ({"lens": "decision", "fields": {"decision": "x", key: "operator"}},
                     {"lens": "decision", "fields": {"decision": "x"}, key: "operator"}):
            with pytest.raises(mcp.ApiError, match=f"^{key} is stamped by Slightly Parallel; leave it out$"):
                tr.call("write_entry", args)
        with pytest.raises(mcp.ApiError, match=f"^{key} is stamped"):
            tr.call("update_entry", {"lens": "decision", "id": "dc_x", "changes": {key: "operator"}})


def test_the_table_is_standard_library_only() -> None:
    """The CI stand loads the file by path, without the backend's packages."""
    tree = ast.parse(Path(mcp_args.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module == "__future__", ast.dump(node)
        assert not isinstance(node, ast.Import), ast.dump(node)


_CALL_RE = re.compile(r"\b([a-z][a-z0-9_]*) \{([^`{}]*)\}")


def _named_args(inner: str) -> set[str]:
    """`a, b?, c: "x"` → {a, b, c}; an ellipsis names nothing."""
    out = set()
    for part in inner.split(","):
        key = part.split(":")[0].strip().rstrip("?")
        if re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            out.add(key)
    return out


def test_every_call_the_agent_texts_and_descriptions_show_uses_the_tables_arguments(client) -> None:
    """A skill, a contract part or a tool description that shows a call with
    an argument the tool does not take sends the agent into a refusal."""
    root = Path(__file__).resolve().parents[2]
    texts = {p.name: p.read_text(encoding="utf-8") for p in
             [*sorted((root / "templates" / "skills").glob("*/SKILL.md")),
              *sorted((root / "prompts" / "contract").glob("*.md"))]}
    texts |= {f"tool {n}": t["description"] for n, t in _tools_from(client).items()}
    # The contract as agents read it, and the docs.
    texts |= {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
              for p in [root / "SLIGHTLY-PARALLEL.md", *sorted((root / "docs").rglob("*.md"))]}
    # Every text the hooks and the server hand an agent (notices, «next»
    # hints, refusals): the string constants of their code.
    for path in [*sorted((root / "scripts" / "hooks").glob("*.py")), *sorted((root / "backend" / "backend").rglob("*.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        texts[path.relative_to(root).as_posix()] = "\n".join(
            n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str))
    seen, wrong, read_in = 0, [], set()
    for where, text in texts.items():
        for name, inner in _CALL_RE.findall(text):
            if name in mcp_args.TOOL_ARGS:
                seen += 1
                read_in.add(where.split("/")[0])
                extra = _named_args(inner) - mcp_args.accepts(name)
                if extra:
                    wrong.append((where, name, sorted(extra)))
    assert seen > 40 and not wrong, wrong
    # The scan reaches each kind of text: hooks and server code, docs, the contract.
    assert {"scripts", "backend", "docs", "SLIGHTLY-PARALLEL.md"} <= read_in, read_in


def test_the_contract_and_write_entry_name_the_one_place_of_project(client) -> None:
    root = Path(__file__).resolve().parents[2]
    shape = mcp_args.project_shape("task", "<code>")
    place = "put `project` next to lens, never inside `fields`"
    contract = (root / "SLIGHTLY-PARALLEL.md").read_text(encoding="utf-8")
    for text in ((root / "prompts" / "contract" / "30-entry.md").read_text(encoding="utf-8"),
                 contract, _tools_from(client)["write_entry"]["description"]):
        assert shape in text and place in text
    assert "Do not send project" not in contract
