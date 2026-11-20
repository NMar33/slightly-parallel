"""The CI refactoring guard counts unnamed values in runtime policy positions."""

from pathlib import Path
import runpy

import pytest

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "refactoring_budget.py"
python_count = runpy.run_path(str(GUARD))["python_count"]


@pytest.mark.parametrize("source", [
    "X = 7\nsubprocess.run(command, timeout=X)",
    "threading.Timer(9, callback)",
    'getattr(settings, "port", 8123)',
    "range(40)",
])
def test_runtime_numbers_cannot_hide_in_a_placeholder_or_positional_argument(source):
    assert python_count("sample.py", source) == 1


def test_named_settings_keep_their_units_and_count_meanings():
    source = """
REQUEST_TIMEOUT_S = 7
MAX_ATTEMPTS = 40
subprocess.run(command, timeout=REQUEST_TIMEOUT_S)
threading.Timer(REQUEST_TIMEOUT_S, callback)
range(MAX_ATTEMPTS)
"""
    assert python_count("sample.py", source) == 0
