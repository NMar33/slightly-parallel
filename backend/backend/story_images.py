"""Screenshots that come with a press release — measured, never touched.

No image library: a dependency that decodes untrusted bytes is one more
moving part. The operator's ``story.image_quality`` setting is carried in
the prompt instead — the agent is told what size to send — and the server
keeps the bytes as they came. Width and height are read from the file
header with the standard library, so the note still knows the size.
"""

from __future__ import annotations

import base64
import binascii
import struct

LEVELS = ("original", "high", "medium", "low")
QUALITY_BOX = {"high": 1600, "medium": 1200, "low": 800}
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}


def checked_image(item: dict, label: str) -> tuple[str, bytes]:
    """One uploaded image, checked and decoded: ``(ext, bytes)``.

    The evidence and story doors ran the same four checks with wordings
    that had drifted apart; this is the one copy. ``label`` names the slot
    the caller is on ("item 2", "image 1") and prefixes every refusal.
    """
    from fastapi import HTTPException

    from . import limits

    ext = str(item.get("ext") or "png").lower().lstrip(".")
    if ext not in IMAGE_EXTS:
        raise HTTPException(
            status_code=422,
            detail=f"{label}: ext must be one of {', '.join(sorted(IMAGE_EXTS))}",
        )
    try:
        raw = base64.b64decode(str(item.get("data_base64") or ""), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=422, detail=f"{label}: data_base64 is not valid base64"
        )
    if not raw:
        raise HTTPException(status_code=422, detail=f"{label}: image is empty")
    if len(raw) > limits.MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"{label}: image is over {limits.MAX_IMAGE_BYTES // (1024 * 1024)}MB",
        )
    return ext, raw


def size_ask(level: str) -> str:
    """The sentence the prompt carries for the level."""
    box = QUALITY_BOX.get(level)
    if not box:
        return "any size the page needs"
    return f"at most {box}px on the long side (the operator's setting)"


def dimensions(raw: bytes) -> tuple[int, int]:
    """(width, height) from a PNG, GIF, JPEG or WebP header; (0, 0) otherwise."""
    try:
        if raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR":
            w, h = struct.unpack(">II", raw[16:24])
            return int(w), int(h)
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", raw[6:10])
            return int(w), int(h)
        if raw[:2] == b"\xff\xd8":
            return _jpeg(raw)
        if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return _webp(raw)
    except (struct.error, IndexError, ValueError):
        pass
    return 0, 0


def _jpeg(raw: bytes) -> tuple[int, int]:
    i = 2
    n = len(raw)
    while i + 9 < n:
        if raw[i] != 0xFF:
            i += 1
            continue
        marker = raw[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", raw[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", raw[i + 5:i + 9])
            return int(w), int(h)
        i += 2 + length
    return 0, 0


def _webp(raw: bytes) -> tuple[int, int]:
    chunk = raw[12:16]
    if chunk == b"VP8X":
        w = 1 + int.from_bytes(raw[24:27], "little")
        h = 1 + int.from_bytes(raw[27:30], "little")
        return w, h
    if chunk == b"VP8L":
        b0, b1, b2, b3 = raw[21:25]
        w = 1 + (((b1 & 0x3F) << 8) | b0)
        h = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return w, h
    if chunk == b"VP8 ":
        w, h = struct.unpack("<HH", raw[26:30])
        return int(w & 0x3FFF), int(h & 0x3FFF)
    return 0, 0
