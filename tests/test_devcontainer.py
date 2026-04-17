"""Unit tests for moot.devcontainer — mock subprocess at the boundary."""
from __future__ import annotations

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


def test_up_streams_then_looks_up_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Success path: no --log-format flag, output not captured, container
    id comes from the post-exit `container_id_or_none()` call."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    lookups: list[Path] = []

    def fake_lookup(ws: Path) -> str | None:
        lookups.append(ws)
        return None if len(lookups) == 1 else "cid_from_lookup"

    monkeypatch.setattr(dc, "container_id_or_none", fake_lookup)

    captured: dict[str, object] = {}

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _fake_run(returncode=0)

    monkeypatch.setattr(dc.subprocess, "run", fake_run)

    result = up(Path("/tmp/workspace"))

    assert result == "cid_from_lookup"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd == [
        "devcontainer", "up",
        "--workspace-folder", "/tmp/workspace",
    ]
    # No --log-format json, no capture_output=True
    assert "--log-format" not in cmd
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert not kwargs.get("capture_output")
    assert len(lookups) == 2


def test_up_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero exit from `devcontainer up` raises DevcontainerError with
    the exit code embedded; stderr/stdout are NOT captured in the message
    (they already streamed to the user's terminal)."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc, "container_id_or_none", lambda _ws: None
    )
    monkeypatch.setattr(
        dc.subprocess, "run",
        lambda *a, **kw: _fake_run(returncode=137),
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "exit code 137" in str(exc.value)


def test_up_prints_build_hint_when_cold(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cold boot: no running container → preamble prints before the CLI call."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    lookups: list[Path] = []

    def fake_lookup(ws: Path) -> str | None:
        lookups.append(ws)
        return None if len(lookups) == 1 else "cidCold"

    monkeypatch.setattr(dc, "container_id_or_none", fake_lookup)
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(returncode=0)
    )

    up(Path("/tmp/workspace"))
    out = capsys.readouterr().out
    assert "Building devcontainer in /tmp/workspace" in out
    assert "1-3 minutes" in out


def test_up_skips_build_hint_when_warm(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Re-up: container already running → preamble suppressed. CLI still runs
    (no code-level short-circuit per D3)."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc, "container_id_or_none", lambda _ws: "cidWarm"
    )
    ran: list[list[str]] = []

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        ran.append(cmd)
        return _fake_run(returncode=0)

    monkeypatch.setattr(dc.subprocess, "run", fake_run)

    result = up(Path("/tmp/workspace"))
    assert result == "cidWarm"
    out = capsys.readouterr().out
    assert "Building devcontainer" not in out
    assert "1-3 minutes" not in out
    assert len(ran) == 1  # CLI still invoked; no short-circuit


def test_up_exit_0_but_no_container_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: if CLI exits 0 but no labelled container is found, raise
    rather than returning an empty string."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(dc, "container_id_or_none", lambda _ws: None)
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(returncode=0)
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "no running container" in str(exc.value).lower()


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
