"""Boot the shipped dashboard in a Windows Cyrillic home or without Node."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import REPO, WINDOWS, Space, free_port, http, wait_for
from stages import SPAWN, path_without, stop

STARTUP_TIMEOUT_S = 120
WINDOW_TIMEOUT_S = 45


def verify(space: Space, profile: str) -> None:
    release = REPO / "frontend" / "dist" / "index.html"
    if not release.is_file():
        raise SystemExit("this profile needs a public candidate with the compiled frontend committed")
    shutil.copytree(REPO, space.clone, ignore=shutil.ignore_patterns(".git", ".env", "node_modules", ".venv", ".sp"))
    env = space.env()
    if profile == "windows-cyrillic-home":
        home = space.root / "Пользователь"
        env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "AppData" / "Roaming"),
                   LOCALAPPDATA=str(home / "AppData" / "Local"), TEMP=str(home / "Temp"), TMP=str(home / "Temp"))
        for key in ("APPDATA", "LOCALAPPDATA", "TEMP"):
            Path(env[key]).mkdir(parents=True, exist_ok=True)
    if profile == "no-node":
        env["PATH"] = path_without(space, "node", "npm", "npx", "corepack")
        if shutil.which("node", path=env["PATH"]):
            raise SystemExit("the profile still finds Node")
    env["SP_DATA_ROOT"] = str(space.root / "данные" if profile.startswith("windows-") else space.data)
    log_path = space.root / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "sp.py", "run", "--prod"], cwd=space.clone,
                                   env=env, stdout=log, stderr=subprocess.STDOUT, **SPAWN)
        try:
            if not wait_for(space, "/api/health", STARTUP_TIMEOUT_S, alive=lambda: process.poll() is None):
                raise SystemExit(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            health = http(space.url + "/api/health")
            if not health.get("ok") or Path(health["data_root"]) != Path(env["SP_DATA_ROOT"]):
                raise SystemExit(f"unexpected health response: {health}")
            html = http(space.url + "/")
            js = re.search(r'src="(/assets/[^"?]+\.js)"', html) if isinstance(html, str) and 'id="root"' in html else None
            if js is None or not http(space.url + js[1]):
                raise SystemExit("the dashboard did not serve its built JavaScript")
            print("OK: health, configured data path, dashboard HTML and JavaScript")
            if profile == "no-node":
                window = subprocess.run([sys.executable, "sp.py", "window"], cwd=space.clone, env=env,
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=WINDOW_TIMEOUT_S)
                output = window.stdout + window.stderr
                if not window.returncode or "the window needs Node 20+ with npm" not in output or "Traceback" in output:
                    raise SystemExit(f"unexpected terminal window diagnostic: {output[-1600:]}")
                print("OK: the terminal window clearly reports its Node prerequisite")
        finally:
            stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("no-node", "windows-cyrillic-home"))
    args = parser.parse_args()
    if args.profile.startswith("windows-") and not WINDOWS:
        parser.error("this profile requires Windows")
    with tempfile.TemporaryDirectory(prefix="sp-profile-") as folder:
        verify(Space(Path(folder).resolve(), free_port()), args.profile)


if __name__ == "__main__":
    main()
