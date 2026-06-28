"""Unit tests for moot.devcontainer — the in-devcontainer local exec layer."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from moot.devcontainer import (
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


# --- container discovery (presume in-devcontainer; no docker reflection) ---

def test_container_id_or_none_returns_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import moot.devcontainer as dc

    def _boom(*_a: object, **_kw: object) -> object:
        raise AssertionError("must not shell out to docker to find the container")

    monkeypatch.setattr(dc.subprocess, "run", _boom)
    monkeypatch.setattr(dc.socket, "gethostname", lambda: "23c9e3b97f7c")
    assert container_id_or_none(Path("/workspaces/repo")) == "23c9e3b97f7c"


def test_up_reports_current_container(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc

    def _boom(*_a: object, **_kw: object) -> object:
        raise AssertionError("up() must not shell out (no devcontainer management)")

    monkeypatch.setattr(dc.subprocess, "run", _boom)
    monkeypatch.setattr(dc.socket, "gethostname", lambda: "23c9e3b97f7c")
    assert up(Path("/workspaces/repo")) == "23c9e3b97f7c"


def test_up_falls_back_when_hostname_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.socket, "gethostname", lambda: "")
    assert up(Path("/workspaces/repo")) == "devcontainer"


# --- exec_capture (local) ---

def test_exec_capture_runs_locally_with_layered_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import moot.devcontainer as dc
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return _fake_run(stdout="hello", returncode=0)

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    monkeypatch.setenv("PATH", "/usr/bin")  # part of the os.environ baseline

    rc, stdout, _stderr = exec_capture(
        "ignored-cid", ["echo", "hi"], env={"FOO": "bar"}
    )
    assert (rc, stdout) == (0, "hello")
    # Command runs directly — no `docker exec` wrapper.
    assert captured["args"] == ["echo", "hi"]
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["FOO"] == "bar"        # layered override present
    assert env["PATH"] == "/usr/bin"  # base environment inherited


def test_exec_capture_no_env_inherits_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import moot.devcontainer as dc
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    exec_capture("ignored-cid", ["tmux", "has-session", "-t", "moot-spec"])
    assert captured["args"] == ["tmux", "has-session", "-t", "moot-spec"]
    assert isinstance(captured["env"], dict)  # always the process environment


# --- exec_detached (local, fire-and-forget) ---

def test_exec_detached_spawns_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import moot.devcontainer as dc
    captured: dict[str, object] = {}

    def fake_popen(args: list[str], **kwargs: object) -> object:
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return object()  # stand-in Popen handle; never awaited

    monkeypatch.setattr(dc.subprocess, "Popen", fake_popen)
    exec_detached(
        "ignored-cid", ["bash", "-lc", "tmux new-session -d"], env={"X": "y"}
    )
    assert captured["args"] == ["bash", "-lc", "tmux new-session -d"]
    env = captured["env"]
    assert isinstance(env, dict) and env["X"] == "y"


# --- exec_interactive (local, stdio inherited) ---

def test_exec_interactive_pins_term_and_lang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin TERM=xterm-256color + LANG=C.UTF-8 in the child environment because
    exotic host TERM values often have no terminfo entry in the container."""
    import moot.devcontainer as dc
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    monkeypatch.setenv("TERM", "xterm-24bits")  # exotic host TERM
    monkeypatch.delenv("COLORTERM", raising=False)

    exec_interactive("ignored-cid", ["tmux", "attach-session", "-t", "moot-spec"])
    assert captured["args"] == ["tmux", "attach-session", "-t", "moot-spec"]
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["TERM"] == "xterm-256color"  # overrides the exotic host TERM
    assert env["LANG"] == "C.UTF-8"


def test_exec_interactive_passes_colorterm_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import moot.devcontainer as dc
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["env"] = kwargs.get("env")
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    monkeypatch.setenv("COLORTERM", "truecolor")
    exec_interactive("ignored-cid", ["tmux", "attach-session", "-t", "moot-spec"])
    env = captured["env"]
    assert isinstance(env, dict) and env["COLORTERM"] == "truecolor"
