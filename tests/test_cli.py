"""Tests for CLI argument parsing and help text."""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path


def test_cli_help_text() -> None:
    """moot --help produces help text without error."""
    result = subprocess.run(
        [sys.executable, "-m", "moot", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Scaffold and run Moot agent teams" in result.stdout


def test_cli_version_flag() -> None:
    """moot --version prints 'moot <version>' and exits 0."""
    from moot import __version__
    result = subprocess.run(
        [sys.executable, "-m", "moot", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # argparse writes `%(prog)s <version>` — prog is "moot".
    # argparse may write to stdout or stderr depending on Python version.
    combined = result.stdout + result.stderr
    assert f"moot {__version__}" in combined


def test_cli_help_no_convo_branding() -> None:
    """User-facing help text does not contain 'Convo' (the old brand)."""
    result = subprocess.run(
        [sys.executable, "-m", "moot", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Convo" not in result.stdout, (
        f"Expected 'Convo' to be absent from --help; got:\n{result.stdout}"
    )


def test_version_consistency() -> None:
    """__version__ in package matches pyproject.toml [project].version."""
    from moot import __version__

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    assert data["project"]["version"] == __version__, (
        f"pyproject.toml version ({data['project']['version']}) does not "
        f"match moot.__version__ ({__version__})"
    )


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
