"""Opt-in native office checks; never bind the user's LibreOffice profile."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("TURBO_WHISPER_TEST_WRITER") != "1",
    reason="Requires isolated native LibreOffice and its UNO Python",
)
def test_native_writer_range_lifecycle():
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONPATH": str(root / "src")}
    result = subprocess.run(
        [
            os.environ.get("TURBO_WHISPER_UNO_PYTHON", "/usr/bin/python3"),
            str(root / "tools/check_writer.py"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stderr
    assert "closed-document-does-not-retarget" in result.stdout
