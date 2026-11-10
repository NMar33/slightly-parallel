"""One chat, one identity, however its folder is spelled; two chats in one
folder, two identities, told apart by real process trees.

The hook names a chat's breadcrumb by the folder the tool reports; the MCP
server asks /api/whoami with its own ``os.getcwd()``. The two spellings
differed (drive-letter case on Windows, /var against /private/var on macOS,
NFD against NFC, a trailing separator, a link) and each difference was a
404: "no captured session", and the agent wrote nothing (round 5). A chat in
a subfolder is found by the tool process it shares with the MCP server.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app
from tests.conftest import symlink_or_need

HOOKS = Path(__file__).resolve().parents[2] / "scripts" / "hooks"
BACKEND = Path(__file__).resolve().parents[1]


def _capture():
    sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location("cc_identity", HOOKS / "claude-code-capture.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def world(tmp_path: Path):
    root = tmp_path / "data"
    (root / "projects" / "alpha").mkdir(parents=True)
    with TestClient(create_app(data_root=root, watch=False)) as c:
        yield c, root, tmp_path


def _who(c: TestClient, cwd: str, pids: str = "") -> tuple[int, dict]:
    r = c.get("/api/whoami", params={"cwd": cwd, **({"pids": pids} if pids else {})})
    return r.status_code, r.json()


def test_a_folder_spelled_another_way_is_the_same_chat(world) -> None:
    c, root, tmp = world
    cc = _capture()
    work = tmp / "Café work"
    work.mkdir()
    cc.write_breadcrumb(str(root), "alpha", "sess-one", str(work))
    nfd = unicodedata.normalize("NFD", str(work))
    for spelling in (str(work), str(work) + os.sep, nfd):
        status, got = _who(c, spelling)
        assert status == 200 and got["session_id"] == "sess-one", (spelling, got)
    # A link to the folder: macOS's /var is a link to /private/var.
    link = tmp / "link"
    symlink_or_need(link, work)
    status, got = _who(c, str(link))
    assert status == 200 and got["session_id"] == "sess-one", got


@pytest.mark.skipif(sys.platform != "win32", reason="drive letters are a Windows spelling")
def test_windows_the_drive_letter_case_is_the_same_chat(world) -> None:
    c, root, tmp = world
    cc = _capture()
    work = tmp / "proj"
    work.mkdir()
    cc.write_breadcrumb(str(root), "alpha", "sess-drive", str(work)[0].lower() + str(work)[1:])
    status, got = _who(c, str(work)[0].upper() + str(work)[1:])
    assert status == 200 and got["session_id"] == "sess-drive", got


# A stand-in for a tool: it runs the hook as a child (the breadcrumb, with
# the processes above the hook), then an MCP server as a child, which prints
# the processes above it. Each tool is a real process tree.
TOOL = r'''
import json, subprocess, sys
root, cwd, session, hooks, backend = sys.argv[1:6]
hook = (
    "import sys, importlib.util; sys.path.insert(0, %r); "
    "s = importlib.util.spec_from_file_location('h', %r); m = importlib.util.module_from_spec(s); "
    "s.loader.exec_module(m); m.write_breadcrumb(%r, 'alpha', %r, %r)"
) % (hooks, hooks + "/claude-code-capture.py", root, session, cwd)
subprocess.run([sys.executable, "-c", hook], check=True, cwd=cwd)
mcp = "import sys; sys.path.insert(0, %r); from backend.hookshared import ancestors; print(','.join(map(str, ancestors())))" % backend
print(subprocess.run([sys.executable, "-c", mcp], check=True, cwd=cwd, capture_output=True, text=True).stdout.strip())
'''


def _tool(root: Path, cwd: Path, session: str, tmp: Path) -> str:
    script = tmp / "tool.py"
    script.write_text(TOOL, encoding="utf-8")
    out = subprocess.run([sys.executable, str(script), str(root), str(cwd), session, str(HOOKS), str(BACKEND)],
                         check=True, capture_output=True, text=True, timeout=60)
    return out.stdout.strip().splitlines()[-1]


def test_two_chats_in_one_folder_each_find_their_own_by_real_processes(world) -> None:
    c, root, tmp = world
    work = tmp / "shared"
    work.mkdir()
    pids_a = _tool(root, work, "sess-a", tmp)
    pids_b = _tool(root, work, "sess-b", tmp)
    for pids, want in ((pids_a, "sess-a"), (pids_b, "sess-b")):
        status, got = _who(c, str(work), pids)
        assert status == 200 and got["session_id"] == want, (want, got)
        assert got["identity_source"] == "process", got
    # Without its processes the newest chat in the folder answers, as a guess.
    status, got = _who(c, str(work))
    assert status == 200 and got["identity_source"] == "folder"


def test_a_chat_in_a_subfolder_is_found_by_its_tool_process_only(world) -> None:
    c, root, tmp = world
    top = tmp / "repo"
    sub = top / "frontend"
    sub.mkdir(parents=True)
    pids = _tool(root, sub, "sess-sub", tmp)   # the hook reports the subfolder
    status, got = _who(c, str(top), pids)      # the MCP server started at the top
    assert status == 200 and got["session_id"] == "sess-sub" and got["identity_source"] == "process", got
    # A client that shares no process with that chat is not given it.
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        status, _ = _who(c, str(top), str(other.pid))
    finally:
        other.kill()
        other.wait()
    assert status == 404
    status, _ = _who(c, str(top))
    assert status == 404
