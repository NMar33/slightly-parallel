"""Stage only credential-checked text from a live agent CI run."""

from __future__ import annotations

import argparse
import json
import stat
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fresh_user"))
from common import contains_diagnostic_key  # noqa: E402

MACHINE_TEXT = {".css", ".html", ".js", ".json", ".jsonl", ".log", ".md"}


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        yield from value
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _texts(text: str, suffix: str) -> Iterator[str]:
    yield text
    if suffix == ".json":
        yield from _strings(json.loads(text))
        return
    for line in text.split("\n"):
        if suffix == ".jsonl" and line.strip():
            yield from _strings(json.loads(line))
        elif line.lstrip().startswith(("{", "[", '"')):
            try:
                yield from _strings(json.loads(line))
            except json.JSONDecodeError:
                pass  # logs are allowed to be plain text, including partial JSON lines


def _check_text(name: PurePosixPath, raw: bytes) -> bytes:
    if (contains_diagnostic_key(name.as_posix())
            or any(contains_diagnostic_key(text) for text in _texts(raw.decode("utf-8"), name.suffix))):
        raise ValueError("Provider credential or fragment detected")
    return raw


def stage_artifacts(source: Path, destination: Path) -> int:
    if source.is_symlink() or (source / "logs").is_symlink():
        raise ValueError("Unexpected link in upload inputs")
    files = [source] if source.suffix == ".json" else [source / "report.json", *(source / "logs").glob("*.log")]
    root = source.parent if source.suffix == ".json" else source
    checked = {}
    for path in files:
        if path.is_symlink():
            raise ValueError("Unexpected link in upload inputs")
        if not path.exists():
            continue
        name = path.relative_to(root)
        checked[name] = _check_text(PurePosixPath(name.as_posix()), path.read_bytes())
    destination.mkdir(parents=True)
    for name, raw in checked.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return len(checked)


def stage_machine_archives(source: Path, destination: Path) -> int:
    if source.is_symlink():
        raise ValueError("Unexpected link in upload inputs")
    checked = {}
    for archive in source.glob("sp-machine-*.zip"):
        if archive.is_symlink() or contains_diagnostic_key(archive.name):
            raise ValueError("Unsafe archive name or link")
        files = {}
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                name = PurePosixPath(info.filename)
                if (stat.S_ISLNK(info.external_attr >> 16) or name.is_absolute() or ".." in name.parts
                        or "\\" in info.filename or ":" in info.filename):
                    raise ValueError("Unsafe archive member")
                if info.is_dir() or name.suffix == ".png":
                    continue
                if name.suffix not in MACHINE_TEXT or name in files:
                    raise ValueError("Unexpected or duplicate archive member")
                files[name] = _check_text(name, bundle.read(info))
        checked[archive.name] = files
    destination.mkdir(parents=True)
    for filename, files in checked.items():
        with zipfile.ZipFile(destination / filename, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, raw in files.items():
                bundle.writestr(name.as_posix(), raw)
    return sum(len(files) for files in checked.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--machine", action="store_true", help="repack only audited text members of Machine archives")
    args = parser.parse_args()
    try:
        stage = stage_machine_archives if args.machine else stage_artifacts
        count = stage(args.source, args.destination)
    except (OSError, ValueError, zipfile.BadZipFile):
        print("Agent artifact upload blocked: unsafe or unreadable report or log.", file=sys.stderr)
        return 1
    print(f"Audited {count} text artifact file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
