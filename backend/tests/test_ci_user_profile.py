"""The actual Docker shell must fail when Node is present."""

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

BASH = shutil.which("bash")


@pytest.mark.skipif(not BASH, reason="the no-Node assertion runs in Bash")
@pytest.mark.parametrize("node_status", [0, 1])
def test_container_proves_node_is_absent(node_status):
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "user-profiles.yml"
    config = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    step = next(step for step in config["jobs"]["no-node"]["steps"]
                if "in a container with no Node" in step.get("name", ""))
    *_, script = shlex.split(step["run"])
    _, assertion = script.split("opencode --version\n", maxsplit=1)
    shell = f"command() {{ return {node_status}; }}\npython() {{ echo profile-ran; }}\n"
    result = subprocess.run([BASH, "-euo", "pipefail", "-c", shell + assertion],
                            capture_output=True, text=True, timeout=10)
    if node_status == 0:
        assert result.returncode == 1
        assert "Node unexpectedly available" in result.stderr
        assert "profile-ran" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "profile-ran" in result.stdout
