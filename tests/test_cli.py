"""Tests for CLI argument parsing and help text."""
from __future__ import annotations

import subprocess
import sys


def test_cli_help_text() -> None:
    """moot --help produces help text without error."""
    result = subprocess.run(
        [sys.executable, "-m", "moot", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Scaffold and run Convo agent teams" in result.stdout


def test_cli_subcommands_help() -> None:
    """All subcommands produce help text without error."""
    subcommands = [
        "login", "init", "config", "up", "down",
        "exec", "status", "compact", "attach",
    ]
    for cmd in subcommands:
        result = subprocess.run(
            [sys.executable, "-m", "moot", cmd, "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"moot {cmd} --help failed: {result.stderr}"
        assert cmd in result.stdout.lower() or "usage" in result.stdout.lower(), (
            f"moot {cmd} --help missing expected content"
        )


def test_cli_no_command_exits_nonzero() -> None:
    """Running moot with no command exits with code 1."""
    result = subprocess.run(
        [sys.executable, "-m", "moot"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_cli_version_importable() -> None:
    """Package version is importable."""
    from moot import __version__
    assert __version__ == "0.1.0"
