"""The architecture page: claims with evidence, checked against the folder, kept in versions."""

from __future__ import annotations

import os
import time

from fastapi.testclient import TestClient

from backend import archpage, projectfacts
from backend.csvio import append_row

PAGE = """## 1. What it is
A small tool that renames photos by date. **Kind:** tool. **Standing:** active.

## 2. The live work
One thread: reading dates from video files. No target stated — looked in `README.md`.

## 3. What it does or has produced
1. **Rename photos by their EXIF date** — `rename.py` · where: `rename.py` · seen: ran it on 3 files · made by: person · checked by: automated tests
2. Dry-run report. Where: `report.py`. Made by: agent run.
- A gallery page — `site/index.html`

## 9. What is owed
1. Video files are skipped. Still true on 2026-09-21: checked by running it.
"""


def _project(client: TestClient, tmp_path):
    store = client.app.state.store
    repo = tmp_path / "photos"
    repo.mkdir()
    (repo / "rename.py").write_text("print('x')\n", encoding="utf-8")
    (repo / "README.md").write_text("# photos\n", encoding="utf-8")
    (repo / "old").mkdir()
    (repo / "old" / "v1.py").write_text("x\n", encoding="utf-8")
    past = time.time() - 70 * 86400
    os.utime(repo / "old" / "v1.py", (past, past))
    append_row(store.data_root / "integrations.csv", ("project", "path"), {"project": "ALPHA", "path": str(repo)})
    projectfacts.forget()
    return store, repo


def test_claims_are_parsed_however_they_are_punctuated() -> None:
    secs = {s["title"]: s for s in archpage.parse(PAGE)}
    claims = secs["What it does or has produced"]["claims"]
    assert [c["where"] for c in claims] == ["`rename.py`", "`report.py`", "`site/index.html`"]
    assert claims[0]["seen"] == "ran it on 3 files" and claims[0]["checked_by"] == "automated tests"
    assert claims[1]["made_by"] == "agent run" and "seen" not in claims[1]
    assert secs["What it is"]["claims"] == []            # prose is not a claim
    assert archpage._first_path("`.env.local`") == ".env.local"       # a leading dot is part of the name
    steps = archpage.parse("## 4. How the main thing works\n1. A hook (`capture.py`) appends to `chat.md`.\n")
    assert steps[0]["claims"] == []                        # steps name paths in passing
    made = archpage.parse("## 6. What it is made of\n- Backend · where: `backend` · seen: opened\n")
    assert len(made[0]["claims"]) == 1                    # not the prose section "What it is"


def test_the_page_is_checked_against_the_folder_and_kept_in_versions(client: TestClient, tmp_path) -> None:
    store, repo = _project(client, tmp_path)
    first = client.post("/api/architecture/page", json={"project": "ALPHA", "agent_id": "cc-a", "text": PAGE, "note": "first"})
    assert first.status_code == 201, first.text
    out = first.json()
    assert out["n"] == 1 and out["counts"] == {"claims": 3, "with_path": 3, "missing": 2, "changed_since": 0}
    assert any("report.py" in w for w in out["warnings"]) and any("2 of 3 items do not say how you know" in w for w in out["warnings"])
    # The same text again is the same version; it lives in the project's own folder.
    again = client.post("/api/architecture/page", json={"project": "ALPHA", "agent_id": "cc-a", "text": PAGE})
    assert again.status_code == 200 and again.json()["existing"] is True
    assert (store.data_root / "projects" / "ALPHA" / "architecture" / "v001.md").is_file()

    # A file changed after the page was written marks its claim.
    future = time.time() + 600
    os.utime(repo / "rename.py", (future, future))
    got = client.get("/api/architecture/page?project=ALPHA").json()
    claim = got["page"]["sections"][2]["claims"][0]
    assert claim["path_found"] is True and claim["changed_since"]
    assert got["facts"]["standing"].startswith("active") and got["word_budget"] == archpage.WORD_BUDGET
    old = next(f for f in got["facts"]["top_level"] if f["name"] == "old")
    assert old["files"] == 1

    # The next version is written from the facts, the current page and what to check again.
    mat = client.get("/api/architecture/page/material?project=ALPHA").json()
    assert mat["current_page"]["n"] == 1 and "claim with its evidence" in mat["instructions"]
    assert {c["where"] for c in mat["check_again"]} == {"rename.py", "report.py", "site/index.html"}
    second = client.post("/api/architecture/page", json={"project": "ALPHA", "agent_id": "cc-b",
                                                         "text": PAGE.replace("3 files", "5 files"), "note": "recounted"})
    assert second.json()["n"] == 2
    listed = client.get("/api/architecture/page?project=ALPHA").json()["versions"]
    assert [(v["n"], v["agent_id"], v["note"]) for v in listed] == [(1, "cc-a", "first"), (2, "cc-b", "recounted")]
    assert client.get("/api/architecture/page?project=ALPHA&version=1").json()["page"]["n"] == 1


def test_a_page_with_no_evidence_or_no_shape_is_refused(client: TestClient, tmp_path) -> None:
    _project(client, tmp_path)
    post = lambda text: client.post("/api/architecture/page", json={"project": "ALPHA", "agent_id": "cc-a", "text": text})
    assert "required heading" in post("## 1. What it is\nA tool.\n").json()["detail"]
    bare = "## What it is\nx\n## The live work\nx\n## What it does or has produced\n- renames photos\n## What is owed\n- nothing\n"
    assert "no item carries its evidence" in post(bare).json()["detail"]
    assert post("").status_code == 422
    assert client.get("/api/architecture/page?project=NOPE").status_code == 404
    assert client.get("/api/architecture/page?project=ALPHA").json()["page"] is None


def test_standing_is_computed_not_guessed() -> None:
    now = time.time()
    assert projectfacts.standing(now - 3 * 86400, now).startswith("active")
    assert projectfacts.standing(now - 30 * 86400, now).startswith("paused")
    assert projectfacts.standing(now - 120 * 86400, now).startswith("dormant — last file change")
