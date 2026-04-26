"""SEC-2-C R8 — devcontainer wrapper script injection tests (legacy moot mirror).

Spawns each script with a malicious CONVO_ROLE and asserts that the
attacker payload never executes (no /tmp/sec2c-pwn marker). Pairs with
the cli-js vitest in mootup-io/moot-cli-js. Plain pytest (no -n auto)
per CLAUDE.md cross-repo exception.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


PWN_MARKER = Path("/tmp/sec2c-pwn")
SCRIPT_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "moot"
    / "templates"
    / "devcontainer"
)
SCRIPTS = ("run-moot-mcp.sh", "run-moot-channel.sh")


def _make_project() -> Path:
    project = Path(tempfile.mkdtemp(prefix="sec2c-"))
    (project / ".moot").mkdir()
    (project / "moot.toml").write_text(
        '[convo]\napi_url = "https://example.test"\nspace_id = "spc_test"\n'
    )
    (project / ".moot" / "actors.json").write_text(
        json.dumps(
            {
                "actors": {
                    "implementation": {
                        "api_key": "convo_key_benign",
                        "actor_id": "agt_benign",
                        "display_name": "BenignImpl",
                    }
                }
            }
        )
    )
    return project


def _probe_cmd(script: Path) -> str:
    # Strip the final `exec python` line so the prelude returns; emit the
    # resolved env for inspection.
    return (
        f"PROBE=$(sed '/^exec python/d' '{script}')\n"
        'eval "$PROBE"\n'
        'echo "POST_KEY=${CONVO_API_KEY:-<unset>}"\n'
    )


@pytest.fixture(autouse=True)
def _clear_pwn_marker():
    if PWN_MARKER.exists():
        PWN_MARKER.unlink()
    yield
    if PWN_MARKER.exists():
        PWN_MARKER.unlink()


@pytest.mark.parametrize("script_name", SCRIPTS)
def test_malicious_role_does_not_execute_shell_code(script_name):
    project = _make_project()
    try:
        env = {
            **os.environ,
            "CONVO_ROLE": f"evil';touch {PWN_MARKER};echo 'pwn",
        }
        subprocess.run(
            ["bash", "-c", _probe_cmd(SCRIPT_DIR / script_name)],
            cwd=project,
            env=env,
            timeout=10,
            capture_output=True,
        )
        assert not PWN_MARKER.exists(), (
            "SEC-2-C invariant violated: malicious CONVO_ROLE created marker file"
        )
    finally:
        for child in project.rglob("*"):
            if child.is_file():
                child.unlink()
        for child in sorted(project.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        project.rmdir()


@pytest.mark.parametrize("script_name", SCRIPTS)
def test_benign_role_resolves_api_key(script_name):
    project = _make_project()
    try:
        env = {**os.environ, "CONVO_ROLE": "implementation"}
        result = subprocess.run(
            ["bash", "-c", _probe_cmd(SCRIPT_DIR / script_name)],
            cwd=project,
            env=env,
            timeout=10,
            capture_output=True,
            text=True,
        )
        assert "POST_KEY=convo_key_benign" in result.stdout, result.stdout + result.stderr
    finally:
        for child in project.rglob("*"):
            if child.is_file():
                child.unlink()
        for child in sorted(project.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        project.rmdir()
