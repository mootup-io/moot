"""Unit tests for moot.launch — mock the devcontainer module boundary."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest


@pytest.fixture
def patch_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Install a fake MootConfig + get_actor_key pair."""
    import moot.launch as launch

    class FakeAgent:
        def __init__(self, role: str) -> None:
            self.role = role
            self.display_name = role.title()
            self.startup_prompt = f"Hello {role}"

    class FakeConfig:
        def __init__(self) -> None:
            self.api_url = "https://mootup.io"
            self.harness_type = "claude-code"
            self.permissions = "dangerously-skip"
            self.agents = {"spec": FakeAgent("spec"), "impl": FakeAgent("impl")}
            self.roles = ["spec", "impl"]

    monkeypatch.setattr(launch, "find_config", lambda: FakeConfig())
    monkeypatch.setattr(launch, "get_actor_key", lambda role: f"convo_key_{role}")
    # cwd.name is used in _launch_role to compute the in-container
    # workspace path. Use tmp_path itself — its basename is a random slug,
    # fine for tests that don't assert on the project name.
    monkeypatch.chdir(tmp_path)


def test_cmd_exec_launch_full_flow(
    monkeypatch: pytest.MonkeyPatch, patch_config: None
) -> None:
    """cmd_exec boots the container, creates worktree, fires tmux command."""
    import moot.launch as launch

    captured_args: list[list[str]] = []
    captured_env: list[dict[str, str] | None] = []
    monkeypatch.setattr(launch, "up", lambda wd: "cid123")

    def fake_exec_capture(
        container_id: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        captured_args.append(args)
        captured_env.append(env)
        # First call: tmux has-session → nonexistent (rc=1)
        # Second call: test -d .worktrees/spec → nonexistent (rc=1)
        # Third call: git worktree add → rc=0
        # Fourth call: bash -c 'tmux new-session ...' → rc=0
        if args[:2] == ["tmux", "has-session"]:
            return (1, "", "")
        if args[0] == "test" and args[1] == "-d":
            return (1, "", "")
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)
    monkeypatch.setattr(launch, "exec_detached", lambda *a, **kw: None)
    monkeypatch.setattr(launch, "container_id_or_none", lambda wd: "cid123")

    ns = argparse.Namespace(role="spec", prompt=None)
    launch.cmd_exec(ns)

    # Find the tmux new-session call (the one with bash -c ...)
    tmux_indices = [
        i for i, a in enumerate(captured_args) if a[:2] == ["bash", "-c"]
    ]
    assert tmux_indices, "expected a bash -c ... call for tmux new-session"
    last = tmux_indices[-1]
    script = captured_args[last][2]
    # shlex.quote on a hyphenated-identifier returns the identifier unquoted.
    assert "tmux new-session -d -s moot-spec" in script
    assert "--dangerously-load-development-channels server:convo-channel" in script
    assert "--dangerously-skip-permissions" in script

    # Env dict must include CONVO_API_KEY via docker exec -e (not on cmdline)
    env = captured_env[last]
    assert env is not None
    assert env["CONVO_ROLE"] == "spec"
    assert env["CONVO_API_KEY"] == "convo_key_spec"
    assert env["CONVO_API_URL"] == "https://mootup.io"

    # The API key must NOT appear on the bash command line.
    assert "convo_key_spec" not in script


def test_cmd_exec_session_already_running(
    monkeypatch: pytest.MonkeyPatch, patch_config: None, capsys: pytest.CaptureFixture[str]
) -> None:
    import moot.launch as launch

    monkeypatch.setattr(launch, "up", lambda wd: "cid999")

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        if args[:2] == ["tmux", "has-session"]:
            return (0, "", "")  # session exists
        raise AssertionError(f"unexpected call once session exists: {args}")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)

    ns = argparse.Namespace(role="spec", prompt=None)
    launch.cmd_exec(ns)
    out = capsys.readouterr().out
    assert "already running" in out


def test_cmd_exec_unknown_role(
    patch_config: None, capsys: pytest.CaptureFixture[str]
) -> None:
    import moot.launch as launch

    ns = argparse.Namespace(role="gremlin", prompt=None)
    with pytest.raises(SystemExit) as exc:
        launch.cmd_exec(ns)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "unknown role 'gremlin'" in out


def test_cmd_exec_no_moot_toml(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import moot.launch as launch

    monkeypatch.setattr(launch, "find_config", lambda: None)
    ns = argparse.Namespace(role="spec", prompt=None)
    with pytest.raises(SystemExit) as exc:
        launch.cmd_exec(ns)
    assert exc.value.code == 1
    assert "no moot.toml" in capsys.readouterr().out


def test_cmd_up_boots_once(
    monkeypatch: pytest.MonkeyPatch, patch_config: None
) -> None:
    """cmd_up calls up() exactly once even when launching multiple roles."""
    import moot.launch as launch

    up_calls: list[Path] = []

    def fake_up(wd: Path) -> str:
        up_calls.append(wd)
        return "cidOnce"

    monkeypatch.setattr(launch, "up", fake_up)

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        if args[:2] == ["tmux", "has-session"]:
            return (0, "", "")  # session always "exists" → short-circuit
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)

    ns = argparse.Namespace(only=None)
    launch.cmd_up(ns)
    assert len(up_calls) == 1


def test_cmd_down_stops_tmux_sessions(
    monkeypatch: pytest.MonkeyPatch, patch_config: None
) -> None:
    import moot.launch as launch

    monkeypatch.setattr(launch, "container_id_or_none", lambda wd: "cidDown")
    calls: list[list[str]] = []

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        calls.append(args)
        if args[:2] == ["tmux", "has-session"]:
            return (0, "", "")  # session exists
        if args[:2] == ["tmux", "kill-session"]:
            return (0, "", "")
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)

    ns = argparse.Namespace(role="spec")
    launch.cmd_down(ns)
    kill = [c for c in calls if c[:2] == ["tmux", "kill-session"]]
    assert kill == [["tmux", "kill-session", "-t", "moot-spec"]]
