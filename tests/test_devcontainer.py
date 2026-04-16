"""Unit tests for moot.devcontainer — mock subprocess at the boundary."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from moot.devcontainer import (
    DevcontainerError,
    container_id_or_none,
    ensure_cli,
    exec_capture,
    exec_detached,
    exec_interactive,
    up,
)


# --- ensure_cli ---

def test_ensure_cli_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: None)
    with pytest.raises(DevcontainerError) as exc:
        ensure_cli()
    assert "npm i -g @devcontainers/cli" in str(exc.value)


def test_ensure_cli_present_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    # Should not raise.
    ensure_cli()


# --- up ---

def _fake_run(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_up_parses_container_id(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    payload = json.dumps(
        {"outcome": "success", "containerId": "abc123def", "remoteUser": "node"}
    )
    # Simulate typical text-log noise preceding the JSON result.
    stdout = "building image...\n" + payload + "\n"
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(stdout=stdout)
    )
    assert up(Path("/tmp/workspace")) == "abc123def"


def test_up_error_outcome_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    payload = json.dumps(
        {"outcome": "error", "message": "docker daemon not reachable"}
    )
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(stdout=payload + "\n")
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "docker daemon not reachable" in str(exc.value)


def test_up_empty_stdout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc.subprocess, "run",
        lambda *a, **kw: _fake_run(
            stdout="", stderr="permission denied", returncode=1
        ),
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "permission denied" in str(exc.value)


def test_up_malformed_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc.subprocess, "run",
        lambda *a, **kw: _fake_run(stdout="not json at all\n"),
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "parse" in str(exc.value).lower()


# --- container_id_or_none ---

def test_container_id_or_none_found(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run(stdout="cid9999\n")

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    result = container_id_or_none(Path("/tmp/workspace"))
    assert result == "cid9999"
    assert "docker" in captured["cmd"]
    assert any(
        a.startswith("label=devcontainer.local_folder=") for a in captured["cmd"]
    )


def test_container_id_or_none_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(stdout="")
    )
    assert container_id_or_none(Path("/tmp/workspace")) is None


# --- exec_capture ---

def test_exec_capture_user_node_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run(stdout="hello", stderr="", returncode=0)

    monkeypatch.setattr(dc.subprocess, "run", fake_run)

    rc, stdout, stderr = exec_capture(
        "cid", ["echo", "hi"], env={"FOO": "bar", "BAZ": "qux"}
    )
    assert rc == 0
    assert stdout == "hello"
    cmd = captured["cmd"]
    assert cmd[:5] == ["docker", "exec", "--user", "node", "-e"]
    assert "FOO=bar" in cmd
    assert "BAZ=qux" in cmd
    assert cmd[-3] == "cid"
    assert cmd[-2:] == ["echo", "hi"]


def test_exec_capture_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    exec_capture("cid", ["tmux", "has-session", "-t", "moot-spec"])
    # When env is None, no -e pairs should be emitted.
    assert captured["cmd"] == [
        "docker", "exec", "--user", "node",
        "cid", "tmux", "has-session", "-t", "moot-spec",
    ]


# --- exec_detached ---

def test_exec_detached_uses_d_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["check"] = kwargs.get("check", False)  # type: ignore[assignment]
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    exec_detached("cid", ["bash", "-c", "sleep 1"], env={"X": "y"})
    cmd = captured["cmd"]
    assert cmd[:5] == ["docker", "exec", "-d", "--user", "node"]
    assert "X=y" in cmd
    assert captured["check"] is True


# --- exec_interactive ---

def test_exec_interactive_uses_it_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    exec_interactive("cid", ["tmux", "attach-session", "-t", "moot-spec"])
    cmd = captured["cmd"]
    assert cmd == [
        "docker", "exec", "-it", "--user", "node", "cid",
        "tmux", "attach-session", "-t", "moot-spec",
    ]
