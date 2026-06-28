"""Unit tests for moot.devcontainer — mock subprocess at the boundary."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from moot.devcontainer import (
    DevcontainerError,
    container_id_or_none,
    exec_capture,
    exec_detached,
    exec_interactive,
    up,
)


def _fake_run(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# --- up (in-container rediscovery only; never manages the devcontainer) ---

def test_up_returns_running_container_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """up() resolves the running container via container_id_or_none and never
    shells out (the python launcher runs inside the container; the host JS CLI
    is what boots the devcontainer)."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc, "container_id_or_none", lambda _ws: "cid_running")

    def _boom(*_a: object, **_kw: object) -> object:
        raise AssertionError("up() must not invoke subprocess (no devcontainer up)")

    monkeypatch.setattr(dc.subprocess, "run", _boom)

    assert up(Path("/workspaces/repo")) == "cid_running"


def test_up_no_container_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """No running container → DevcontainerError pointing at the host `moot up`."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc, "container_id_or_none", lambda _ws: None)
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/workspaces/repo"))
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

def test_exec_interactive_pins_term_and_lang_to_container_safe_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Always pin TERM=xterm-256color + LANG=C.UTF-8 because host TERM
    values (e.g. xterm-24bits, xterm-kitty, alacritty) often have no
    terminfo entry inside the container — tmux then refuses to start
    with 'missing or unsuitable terminal'."""
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    monkeypatch.setenv("TERM", "xterm-24bits")  # exotic host TERM
    monkeypatch.delenv("COLORTERM", raising=False)

    exec_interactive("cid", ["tmux", "attach-session", "-t", "moot-spec"])
    cmd = captured["cmd"]
    assert cmd[:5] == ["docker", "exec", "-it", "--user", "node"]
    assert "TERM=xterm-256color" in cmd
    assert "TERM=xterm-24bits" not in cmd
    assert "LANG=C.UTF-8" in cmd
    # No COLORTERM arg when the host didn't set one.
    assert not any(e.startswith("COLORTERM=") for e in cmd)
    assert cmd[-4:] == ["tmux", "attach-session", "-t", "moot-spec"]


def test_exec_interactive_passes_colorterm_when_host_exports_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COLORTERM is safe to pass through — it's just a capability flag,
    not a terminfo lookup key."""
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    monkeypatch.setenv("COLORTERM", "truecolor")

    exec_interactive("cid", ["tmux", "attach-session", "-t", "moot-spec"])
    assert "COLORTERM=truecolor" in captured["cmd"]
