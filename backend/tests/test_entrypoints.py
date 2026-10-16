"""Entry points: #entrypoint in a chat becomes an ep_ record, open; the
agent writes its text through the interpretation route; the operator
closes it; the hook hands out the same id the server mints."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend import keeplib
from backend.db import ViewStore
from backend.docs_md import read_detail
from backend.server import create_app
from tests.conftest import make_chat

AGENT = "cc-abc12345"
TEXT = (
    "## What\nThe install film, the first how-to.\n\n## Where\n- brand/channel/videos/install-voiced.mp4\n\n"
    "## How\nStudio → Install → render MP4.\n\n## State\nVoiced; not uploaded.\n\n## Next\n- upload\n"
)


def _hook():
    path = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "capture.py"
    spec = importlib.util.spec_from_file_location("capture_hook_ep", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["capture_hook_ep"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _kept(data_root: Path) -> ViewStore:
    make_chat(data_root, "ALPHA", AGENT, [
        ("2026-09-01T10:00:00", "one", "a1"),
        ("2026-09-01T10:01:00", "#entrypoint the install film: put the video work and the launch page in", "noted"),
        ("2026-09-01T10:02:00", "three", "a3"),
    ])
    store = ViewStore(data_root=data_root)
    store.rebuild()
    return store


def test_the_tag_makes_an_open_entry_point_the_hook_can_name(data_root: Path) -> None:
    store = _kept(data_root)
    assert len(keeplib.adopt(store)) == 1
    row = store.query_one("SELECT * FROM entrypoints_mutual WHERE source = 'captured'")
    assert row["id"].startswith("ep_") and row["status"] == "open" and row["source_turn"] == 2
    assert row["l1"] == "the install film: put the video work and the launch page in"
    assert _hook().keep_id("entrypoint", "ALPHA", AGENT, 2) == row["id"]
    assert (data_root / "entrypoints.csv").is_file()


def test_the_agent_writes_the_text_in_versions_and_the_operator_closes_it(data_root: Path) -> None:
    _kept(data_root)
    with TestClient(create_app(data_root=data_root, watch=False)) as client:
        listed = client.get("/api/entrypoints?project=ALPHA").json()
        rows = listed.get("entrypoints") or listed.get("items") or []
        assert len(rows) == 1 and rows[0]["status"] == "open"
        eid = rows[0]["id"]

        r = client.post(f"/api/entrypoints/{eid}/interpretation", json={"agent_id": AGENT, "text": TEXT})
        assert r.status_code == 200, r.text
        r = client.post(f"/api/entrypoints/{eid}/interpretation",
                        json={"agent_id": AGENT, "text": TEXT.replace("not uploaded", "uploaded"), "note": "uploaded"})
        assert r.status_code == 200, r.text
        detail = client.get(f"/api/entrypoints/{eid}").json()
        assert detail["metadata"]["versions_n"] == 2
        assert "## State" in detail["kept"]["current"]["text"] and "uploaded" in detail["kept"]["current"]["text"]
        l2, _l3, l4 = read_detail(data_root, detail["metadata"]["md_ref"])
        assert l4.startswith("the install film")

        r = client.post(f"/api/entrypoints/{eid}/update", json={"actor": "operator", "status": "closed", "topic": "The install film"})
        assert r.status_code == 200, r.text
        row = client.get(f"/api/entrypoints/{eid}").json()["metadata"]
        assert row["status"] == "closed" and row["topic"] == "The install film"
        r = client.post(f"/api/entrypoints/{eid}/update", json={"actor": "operator", "status": "resolved"})
        assert r.status_code == 422
        open_only = client.get("/api/entrypoints?project=ALPHA&status=open").json()
        assert not (open_only.get("entrypoints") or open_only.get("items"))
