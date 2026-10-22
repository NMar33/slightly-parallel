"""A rebuild builds again only the tables whose files moved — and never misses one."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from backend.db import ViewStore
from backend.server import create_app


def _store(tmp_path: Path) -> ViewStore:
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        for title in ("one", "two"):
            c.post("/api/tasks", json={"created_date": "2609-01", "created_time": "10:00", "project": "alpha",
                                       "agent_id": "operator", "title": title, "status": "todo"})
    return ViewStore(root)


def test_only_changed_tables_are_built_again(tmp_path: Path) -> None:
    st = _store(tmp_path)
    st.rebuild()
    assert st._built == {}, "nothing moved, nothing built"
    (st.data_root / "tasks.csv").touch()
    st.rebuild()
    assert list(st._built) == ["tasks_mutual"]
    assert len(st.query("SELECT id FROM tasks_mutual")) == 2


def test_a_same_size_edit_in_the_same_second_is_seen(tmp_path: Path) -> None:
    st = _store(tmp_path)
    p = st.data_root / "tasks.csv"
    text = p.read_text(encoding="utf-8")
    before = p.stat()
    # Rewritten the way the writers do (a new file renamed over), same size, same time.
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text.replace(",one,", ",uno,"), encoding="utf-8")
    os.utime(tmp, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(tmp, p)
    st.rebuild()
    assert {r["title"] for r in st.query("SELECT title FROM tasks_mutual")} == {"uno", "two"}


def test_a_broken_file_keeps_saying_so(tmp_path: Path) -> None:
    st = _store(tmp_path)
    (st.data_root / "goals.csv").write_bytes(b"\x00\xff\xfegarbage header\ng_1,x\n")
    st.rebuild()
    first = [e for e in st.load_errors if "goals.csv" in e["file"]]
    assert first, st.load_errors
    st.rebuild()          # not built again — its error is still reported
    assert [e for e in st.load_errors if "goals.csv" in e["file"]] == first
    assert len(st.query("SELECT id FROM tasks_mutual")) == 2


def test_readers_see_whole_builds(tmp_path: Path) -> None:
    """Tables and the views over them keep answering across swaps."""
    st = _store(tmp_path)
    for _ in range(3):
        (st.data_root / "tasks.csv").touch()
        st.rebuild()
        assert st.query("SELECT COUNT(*) AS n FROM time_blocks")[0]["n"] >= 0
        assert st.query("SELECT COUNT(*) AS n FROM scans_mutual")[0]["n"] == 0
