"""Press releases: presets, the request, the gated story post, images at
the operator's quality, and the note that carries them."""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import create_app


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "data"
    (r / "projects" / "alpha").mkdir(parents=True)
    return r


@pytest.fixture()
def client(root: Path):
    app = create_app(data_root=root, watch=False)
    with TestClient(app) as c:
        yield c


def _task(client: TestClient, title: str = "Collapsable sidebar") -> str:
    r = client.post("/api/tasks", json={
        "created_date": "2609-09", "created_time": "12:00", "project": "alpha",
        "agent_id": "operator", "title": title, "status": "doing", "description": "make it fold",
    })
    assert r.status_code == 201, r.text
    return r.json()["metadata"]["id"]


def _png_bytes(width: int = 40, height: int = 30) -> bytes:
    """A real PNG, from the standard library: one grey-ish RGB rectangle."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    row = b"\x00" + bytes([30, 120, 90]) * width
    raw = zlib.compress(row * height)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def _png(width: int = 40, height: int = 30) -> str:
    return base64.b64encode(_png_bytes(width, height)).decode()


def _request(client: TestClient, tid: str, **extra) -> dict:
    r = client.post(f"/api/tasks/{tid}/story-requests", json={"type": "release", "focus": "the rail", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_presets_have_builtins_and_operator_ones(client: TestClient):
    d = client.get("/api/story/prompts").json()
    assert [p["id"] for p in d["parts"]["brief"]] == ["brief-default"]
    assert [p["id"] for p in d["parts"]["style"]] == ["style-default"]
    assert d["parts"]["focus"] == []
    assert d["types"] == ["article", "post", "release"]

    r = client.post("/api/story/prompts", json={"part": "style", "name": "Clipped", "text": "Rn we don't have a backup system…"})
    assert r.status_code == 200, r.text
    pid = r.json()["preset"]["id"]
    assert pid.startswith("pre_")
    r = client.post("/api/story/prompts", json={"part": "style", "id": pid, "name": "Short", "text": "shorter"})
    assert r.json()["preset"] == {"id": pid, "name": "Short", "text": "shorter"}
    names = [p["name"] for p in client.get("/api/story/prompts").json()["parts"]["style"]]
    assert names == ["My words, three voices", "Short"]

    # Built-ins can be edited, never removed.
    assert client.post("/api/story/prompts/brief-default/delete").status_code == 409
    r = client.post("/api/story/prompts", json={"part": "brief", "id": "brief-default", "name": "Mine", "text": "write it"})
    assert r.status_code == 200
    assert client.post(f"/api/story/prompts/{pid}/delete").json()["deleted"] == pid
    assert client.post("/api/story/prompts", json={"part": "nope", "name": "x", "text": "y"}).status_code == 422
    assert client.post("/api/story/prompts", json={"part": "focus", "name": "", "text": "y"}).status_code == 422


def test_request_builds_the_prompt_and_keeps_it(client: TestClient, root: Path):
    tid = _task(client)
    d = _request(client, tid, style="Write like Slack's launch post.")
    req, prompt = d["request"], d["prompt"]
    assert req["id"].startswith("sr_") and req["status"] == "open" and req["type"] == "release"
    assert req["brief_id"] == "brief-default" and req["style_id"] == "inline"
    assert prompt.startswith(f"{tid} · Collapsable sidebar — press release request {req['id']}")
    for piece in ("FOCUS\nthe rail", "WHAT TO DO", "1.1 What was built", "STYLE EXAMPLES\nWrite like Slack",
                  "MCP tool task_story", req["id"], "(image:1)"):
        assert piece in prompt, piece
    assert (root / "task_story" / tid / f"{req['id']}.prompt.md").read_text(encoding="utf-8") == prompt
    assert client.get(f"/api/story/requests/{req['id']}/prompt").text == prompt
    listed = client.get(f"/api/tasks/{tid}/story-requests").json()
    assert listed["total"] == 1 and listed["requests"][0]["id"] == req["id"]
    # The ask is on the task's timeline.
    ev = client.get(f"/api/tasks/{tid}/events").json()
    assert any(e.get("field") == "story_request" for e in ev.get("events", ev if isinstance(ev, list) else []))


def test_request_refuses_bad_input(client: TestClient):
    tid = _task(client)
    assert client.post(f"/api/tasks/{tid}/story-requests", json={"type": "faq"}).status_code == 422
    assert client.post(f"/api/tasks/{tid}/story-requests", json={"brief_id": "sp_missing"}).status_code == 404
    assert client.post("/api/tasks/tk_nope/story-requests", json={}).status_code == 404


def test_story_needs_an_open_request_on_the_same_task(client: TestClient):
    tid = _task(client)
    other = _task(client, "Another")
    r = client.post(f"/api/tasks/{tid}/story", json={"agent_id": "cc-1", "body": "spam"})
    assert r.status_code == 422 and "request_id" in r.json()["detail"]
    assert client.post(f"/api/tasks/{tid}/story", json={"agent_id": "cc-1", "body": "x", "request_id": "sr_nope"}).status_code == 404
    rid = _request(client, tid)["request"]["id"]
    r = client.post(f"/api/tasks/{other}/story", json={"agent_id": "cc-1", "body": "x", "request_id": rid})
    assert r.status_code == 422 and "belongs to" in r.json()["detail"]
    assert client.post(f"/api/tasks/{tid}/story", json={"agent_id": "", "body": "x", "request_id": rid}).status_code == 422
    assert client.post(f"/api/tasks/{tid}/story", json={"agent_id": "cc-1", "body": "", "request_id": rid}).status_code == 422
    # Cancel closes the door.
    assert client.post(f"/api/story/requests/{rid}/cancel").json()["request"]["status"] == "cancelled"
    r = client.post(f"/api/tasks/{tid}/story", json={"agent_id": "cc-1", "body": "late", "request_id": rid})
    assert r.status_code == 409


def test_story_lands_as_a_note_with_images_and_closes_the_request(client: TestClient, root: Path):
    tid = _task(client)
    rid = _request(client, tid)["request"]["id"]
    body = "# The rail\n\nOne click.\n\n![the rail](image:1)\n\nand ![missing](image:9) stays"
    r = client.post(f"/api/tasks/{tid}/story", json={
        "agent_id": "cc-fe8d67eb", "request_id": rid, "body": body,
        "images": [{"title": "the rail", "data_base64": _png(), "ext": "png"}],
    })
    assert r.status_code == 201, r.text
    d = r.json()
    note, images = d["note"], d["images"]
    assert note["type"] == "release" and note["actor"] == "cc-fe8d67eb" and note["template"] == rid
    # The operator's focus heads the piece, as written.
    assert note["body"].startswith("**From the operator**\n\nthe rail\n\n---\n\n# The rail")
    assert len(images) == 1 and images[0]["id"].startswith("si_") and images[0]["width"] == "40"
    assert f"![the rail]({images[0]['url']})" in note["body"]
    assert "(image:9)" in note["body"]
    # The note is on the task and the wall; the image is served; the request is closed.
    notes = client.get(f"/api/tasks/{tid}/notes").json()["notes"]
    assert [n["id"] for n in notes] == [note["id"]]
    assert client.get("/api/tasks/notes?project=alpha").json()["notes"][0]["actor"] == "cc-fe8d67eb"
    img = client.get(images[0]["url"])
    assert img.status_code == 200 and img.content[:4] == b"\x89PNG"
    assert client.get(f"/api/story/images?note_id={note['id']}").json()["total"] == 1
    req = client.get(f"/api/tasks/{tid}/story-requests").json()["requests"][0]
    assert req["status"] == "fulfilled" and req["note_id"] == note["id"] and req["agent_id"] == "cc-fe8d67eb"
    r = client.post(f"/api/tasks/{tid}/story", json={"agent_id": "cc-1", "body": "again", "request_id": rid})
    assert r.status_code == 409
    # Deleting the note takes its images away.
    path = root / images[0]["path"]
    assert path.exists()
    assert client.post(f"/api/tasks/notes/{note['id']}/delete").status_code == 200
    assert not path.exists()
    assert client.get(images[0]["url"]).status_code == 404


def test_the_prompt_carries_the_size_ask_and_images_are_kept_as_sent(client: TestClient):
    tid = _task(client)
    big = _png(2400, 1200)
    for level, ask in (("original", "any size the page needs"), ("high", "at most 1600px"), ("low", "at most 800px")):
        assert client.post("/api/settings", json={"values": {"story.image_quality": level}}).status_code == 200
        d = _request(client, tid)
        assert ask in d["prompt"], level
        r = client.post(f"/api/tasks/{tid}/story", json={
            "agent_id": "cc-1", "request_id": d["request"]["id"], "body": f"at {level}",
            "images": [{"title": "wide", "data_base64": big, "ext": "png"}],
        })
        assert r.status_code == 201, r.text
        img = r.json()["images"][0]
        assert (img["width"], img["height"]) == ("2400", "1200")
        assert client.get(img["url"]).content == _png_bytes(2400, 1200)
    r = client.post(f"/api/tasks/{tid}/story", json={
        "agent_id": "cc-1", "request_id": _request(client, tid)["request"]["id"], "body": "bad",
        "images": [{"title": "x", "data_base64": "not base64!", "ext": "png"}],
    })
    assert r.status_code == 422
    r = client.post(f"/api/tasks/{tid}/story", json={
        "agent_id": "cc-1", "request_id": _request(client, tid)["request"]["id"], "body": "bad",
        "images": [{"title": "x", "data_base64": _png(), "ext": "bmp"}],
    })
    assert r.status_code == 422


def test_dimensions_from_headers():
    from backend import story_images
    assert story_images.dimensions(_png_bytes(640, 480)) == (640, 480)
    gif = b"GIF89a" + struct.pack("<HH", 12, 34) + b"\x00" * 4
    assert story_images.dimensions(gif) == (12, 34)
    # A minimal JPEG: SOI, an APP0 segment, then a baseline SOF0 with 300x200.
    jpeg = (b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 4) + b"\x00\x00"
            + b"\xff\xc0" + struct.pack(">H", 11) + b"\x08" + struct.pack(">HH", 200, 300) + b"\x03" + b"\x00" * 9)
    assert story_images.dimensions(jpeg) == (300, 200)
    webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8X" + b"\x00" * 8 + (1599).to_bytes(3, "little") + (899).to_bytes(3, "little")
    assert story_images.dimensions(webp) == (1600, 900)
    assert story_images.dimensions(b"not an image") == (0, 0)
    assert story_images.size_ask("medium") == "at most 1200px on the long side (the operator's setting)"
    assert story_images.size_ask("original") == "any size the page needs"
