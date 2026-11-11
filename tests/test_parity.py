"""Run the browser-engine parity check as part of the Python test suite."""

import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data", "deal-lab-data.json")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
@pytest.mark.skipif(not os.path.exists(DATA), reason="no published data file yet")
def test_browser_engine_matches_python_engine():
    result = subprocess.run(["node", os.path.join(ROOT, "tests", "parity.js")],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "parity ok" in result.stdout
