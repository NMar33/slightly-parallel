"""Provide OpenCode's native ripgrep before running a test on a fresh profile."""

import os
import platform
import shutil
import subprocess
from pathlib import Path


INSTALL = {
    "Linux": (["sudo", "apt-get", "update"], ["sudo", "apt-get", "install", "-y", "ripgrep"]),
    "Darwin": (["brew", "install", "ripgrep"],),
    "Windows": (["choco", "install", "ripgrep", "--yes", "--no-progress"],),
}


def setup(system: str) -> None:
    binary = "rg.exe" if system == "Windows" else "rg"
    executable = shutil.which(binary)
    if executable is None:
        for command in INSTALL[system]:
            subprocess.run(command, check=True)
        executable = shutil.which(binary)
        if executable is None:
            # Package managers need not update the calling process's PATH.
            directory = Path("/usr/bin")
            if system == "Darwin":
                prefix = subprocess.check_output(["brew", "--prefix"], text=True).strip()
                directory = Path(prefix) / "bin"
            elif system == "Windows":
                prefix = os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey")
                directory = Path(prefix) / "bin"
            executable = shutil.which(binary, path=str(directory))
    if executable is None:
        raise SystemExit(f"OpenCode requires {binary}, but the package manager did not provide it.")
    subprocess.run([executable, "--version"], check=True)
    if github_path := os.environ.get("GITHUB_PATH"):
        with Path(github_path).open("a", encoding="utf-8") as handle:
            handle.write(f"{Path(executable).absolute().parent}\n")


if __name__ == "__main__":
    setup(platform.system())
