"""Unit tests for moot.launch — mock the devcontainer module boundary."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest


@pytest.fixture
def patch_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    """Install a fake MootConfig + get_actor_key pair.

    Returns the single FakeConfig instance so tests can mutate per-role
    profile fields (model/effort/theme) before invoking the launcher —
    every ``find_config()`` call returns the same instance.
    """
    import moot.launch as launch

    class FakeAgent:
        def __init__(self, role: str) -> None:
            self.role = role
            self.display_name = role.title()
            self.startup_prompt = f"Hello {role}"
            self.harness: str = "claude-code"
            self.model: str | None = None
            self.effort: str | None = None
            self.theme: str | None = None
            self.env: dict[str, str] = {}

    class FakeConfig:
        def __init__(self) -> None:
            self.api_url = "https://mootup.io"
            self.harness_type = "claude-code"
            self.permissions = "dangerously-skip"
            self.permission_mode = "bypassPermissions"
            self.launch_stagger_seconds = 0.0  # tests don't stagger unless set
            self.agents = {"spec": FakeAgent("spec"), "impl": FakeAgent("impl")}
            self.roles = ["spec", "impl"]
            # Arbitrary for this fake — tests that exercise cold-start
            # cascade pin a specific role by monkeypatching if needed.
            self.human_interface = "spec"

    fake_config = FakeConfig()
    monkeypatch.setattr(launch, "find_config", lambda: fake_config)
    # cwd.name is used in _launch_role to compute the in-container
    # workspace path. Use tmp_path itself — its basename is a random slug,
    # fine for tests that don't assert on the project name.
    monkeypatch.chdir(tmp_path)
    return fake_config


def test_cmd_exec_launch_full_flow(
    monkeypatch: pytest.MonkeyPatch, patch_config: object
) -> None:
    """cmd_exec boots the container, creates worktree, fires tmux command."""
    import moot.launch as launch

    # Set per-role profile fields so the full_flow assertions below can
    # verify --model / --effort / pane-border-style wiring end-to-end.
    spec_agent = patch_config.agents["spec"]  # type: ignore[attr-defined]
    spec_agent.model = "opus"
    spec_agent.effort = "high"
    spec_agent.theme = "cyan"

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

    # Find the tmux new-session call (the one with bash -lc ...)
    tmux_indices = [
        i for i, a in enumerate(captured_args) if a[:2] == ["bash", "-lc"]
    ]
    assert tmux_indices, "expected a bash -lc ... call for tmux new-session"
    tmux_call = captured_args[tmux_indices[-1]]
    assert tmux_call[:2] == ["bash", "-lc"], (
        "tmux launch must use `bash -lc` to source ~/.profile and pick up ~/.local/bin"
    )
    last = tmux_indices[-1]
    script = captured_args[last][2]
    # shlex.quote on a hyphenated-identifier returns the identifier unquoted.
    assert "tmux -u new-session -d -s moot-spec" in script
    assert "--dangerously-load-development-channels server:convo-channel" in script
    assert "--dangerously-skip-permissions" not in script
    assert "CONVO_WORKTREE=" in script

    # Per-role env must override via `tmux new-session -e`, NOT docker exec -e,
    # because sessions in a shared server inherit the server's env, not the
    # launching shell's. Without this, cascaded agents run with the first
    # role's CONVO_ROLE and connect to convo as that role.
    assert "-e" in script
    assert "CONVO_ROLE=spec" in script
    assert "CONVO_API_URL=https://mootup.io" in script

    # docker exec env is now global/shared (TERM, LANG, TMUX_TMPDIR) —
    # CONVO_ROLE and CONVO_API_URL go via tmux -e instead.
    env = captured_env[last]
    assert env is not None
    assert "CONVO_ROLE" not in env
    assert "CONVO_API_URL" not in env
    assert env["TERM"] == "xterm-256color"
    assert env["LANG"] == "C.UTF-8"
    assert env["TMUX_TMPDIR"] == "/tmp"

    # API key is NOT passed via env — the MCP wrapper scripts look it up
    # from .moot/actors.json at runtime using CONVO_ROLE, keeping the
    # secret off every command line.
    assert "CONVO_API_KEY" not in env
    assert "CONVO_API_KEY" not in script

    # Agents launch in bypassPermissions mode (sandboxed devcontainer).
    assert "--permission-mode bypassPermissions" in script
    # Per-role profile flags reach the claude invocation + tmux theme.
    assert "--model opus" in script
    assert "--effort high" in script
    assert "pane-border-style fg=cyan" in script
    # pane-border-status must be set BEFORE pane-border-style so the
    # colored border is visible in single-pane sessions (wrong order →
    # silently ignored in some tmux versions).
    assert script.index("pane-border-status") < script.index("pane-border-style")


def test_cmd_exec_per_role_env_and_secret_resolution(
    monkeypatch: pytest.MonkeyPatch, patch_config: object, tmp_path: Path
) -> None:
    """Per-role [agents.<role>].env reaches the pane via tmux -e, with
    ${secret:NAME} resolved from SECRETS_DIR at launch (newline stripped)."""
    import moot.launch as launch

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "llm-proxy-secret").write_text("PROXYSECRET\n")
    monkeypatch.setattr(launch, "SECRETS_DIR", str(secrets_dir))

    spec_agent = patch_config.agents["spec"]  # type: ignore[attr-defined]
    spec_agent.model = "deepseek-v4-pro"
    spec_agent.env = {
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:8090",
        "ANTHROPIC_API_KEY": "${secret:llm-proxy-secret}",
    }

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
        if args[:2] == ["tmux", "has-session"]:
            return (1, "", "")
        if args[0] == "test" and args[1] == "-d":
            return (1, "", "")
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)
    monkeypatch.setattr(launch, "exec_detached", lambda *a, **kw: None)
    monkeypatch.setattr(launch, "container_id_or_none", lambda wd: "cid123")

    launch.cmd_exec(argparse.Namespace(role="spec", prompt=None))

    tmux_indices = [
        i for i, a in enumerate(captured_args) if a[:2] == ["bash", "-lc"]
    ]
    assert tmux_indices
    last = tmux_indices[-1]
    script = captured_args[last][2]
    # Provider binding via tmux -e; secret resolved with trailing newline gone.
    assert "ANTHROPIC_BASE_URL=http://127.0.0.1:8090" in script
    assert "ANTHROPIC_API_KEY=PROXYSECRET" in script
    assert "${secret:" not in script  # reference was resolved, not passed through
    # Per-role env goes through tmux -e (per session), not the shared exec env.
    env = captured_env[last]
    assert env is not None and "ANTHROPIC_API_KEY" not in env


def test_cmd_exec_missing_secret_aborts(
    monkeypatch: pytest.MonkeyPatch, patch_config: object, tmp_path: Path
) -> None:
    """A ${secret:NAME} reference with no matching file aborts the launch."""
    import moot.launch as launch

    monkeypatch.setattr(launch, "SECRETS_DIR", str(tmp_path / "absent-dir"))
    spec_agent = patch_config.agents["spec"]  # type: ignore[attr-defined]
    spec_agent.env = {"ANTHROPIC_API_KEY": "${secret:absent}"}

    monkeypatch.setattr(launch, "up", lambda wd: "cid123")

    def fake_exec_capture(
        container_id: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        if args[:2] == ["tmux", "has-session"]:
            return (1, "", "")
        if args[0] == "test" and args[1] == "-d":
            return (1, "", "")
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)
    monkeypatch.setattr(launch, "exec_detached", lambda *a, **kw: None)
    monkeypatch.setattr(launch, "container_id_or_none", lambda wd: "cid123")

    with pytest.raises(SystemExit):
        launch.cmd_exec(argparse.Namespace(role="spec", prompt=None))


def test_cmd_exec_launch_no_flags_when_unset(
    monkeypatch: pytest.MonkeyPatch, patch_config: object
) -> None:
    """Absent model/effort/theme → no --model, --effort, or pane-border
    calls in the emitted bash script. Lets Claude Code's account default
    model + tmux's default border style apply."""
    import moot.launch as launch

    captured_args: list[list[str]] = []
    monkeypatch.setattr(launch, "up", lambda wd: "cidNoFlags")

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        captured_args.append(args)
        if args[:2] == ["tmux", "has-session"]:
            return (1, "", "")
        if args[0] == "test" and args[1] == "-d":
            return (1, "", "")
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)
    monkeypatch.setattr(launch, "exec_detached", lambda *a, **kw: None)
    monkeypatch.setattr(launch, "container_id_or_none", lambda wd: "cidNoFlags")

    ns = argparse.Namespace(role="spec", prompt=None)
    launch.cmd_exec(ns)

    tmux_indices = [
        i for i, a in enumerate(captured_args) if a[:2] == ["bash", "-lc"]
    ]
    assert tmux_indices, "expected a bash -lc ... call for tmux new-session"
    script = captured_args[tmux_indices[-1]][2]
    assert "--model" not in script
    assert "--effort" not in script
    assert "pane-border-status" not in script
    assert "pane-border-style" not in script


def test_cmd_exec_cursor_harness_errors_cleanly(
    monkeypatch: pytest.MonkeyPatch, patch_config: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """Per-role harness='cursor' errors out with 'not yet supported' — unchanged
    behavior. Regression guard so cursor/aider dispatch doesn't silently break
    when launch.py is edited."""
    import moot.launch as launch

    cursor_agent = patch_config.agents["spec"]  # type: ignore[attr-defined]
    cursor_agent.harness = "cursor"

    monkeypatch.setattr(launch, "up", lambda wd: "cidCursor")
    monkeypatch.setattr(launch, "container_id_or_none", lambda wd: "cidCursor")

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        if args[:3] == ["test", "-s", launch.CREDENTIALS_PATH]:
            return (0, "", "")  # creds present
        if args[:2] == ["tmux", "has-session"]:
            return (1, "", "")  # no existing session
        if args[0] == "test" and args[1] == "-d":
            return (1, "", "")  # worktree absent
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)
    monkeypatch.setattr(launch, "exec_detached", lambda *a, **kw: None)

    ns = argparse.Namespace(role="spec", prompt=None)
    with pytest.raises(SystemExit) as exc:
        launch.cmd_exec(ns)
    assert exc.value.code == 1
    assert "not yet supported" in capsys.readouterr().out


def test_cmd_exec_session_already_running(
    monkeypatch: pytest.MonkeyPatch, patch_config: None, capsys: pytest.CaptureFixture[str]
) -> None:
    import moot.launch as launch

    monkeypatch.setattr(launch, "up", lambda wd: "cid999")

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        if args[0] == "test" and args[1] == "-s":
            return (0, "", "")  # credentials file present → skip auth
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
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """cmd_up calls up() exactly once even when launching multiple roles
    and prints the closing summary naming the container."""
    import moot.launch as launch

    up_calls: list[Path] = []

    def fake_up(wd: Path) -> str:
        up_calls.append(wd)
        return "cidOnceAAAAAA"

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
    out = capsys.readouterr().out
    # 2 roles in FakeConfig (spec, impl), both already running
    assert "Started 2 agents in container cidOnceAAAAA" in out
    assert "moot attach" in out
    assert "moot status" in out


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


def test_cmd_up_cold_start_launches_human_interface_first_then_cascades(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cold start: credentials missing → launch HI role first, poll until creds
    appear, then launch the rest. Order matters — HI is first."""
    import moot.launch as launch

    monkeypatch.setattr(launch, "up", lambda wd: "cidCold")
    monkeypatch.setattr(launch, "exec_detached", lambda *a, **kw: None)
    monkeypatch.setattr(launch, "AUTH_POLL_INTERVAL_S", 0)  # don't actually wait
    monkeypatch.setattr(launch, "AUTH_SETTLE_S", 0)
    monkeypatch.setattr(launch, "DEV_USE_PROMPT_DELAY_S", 0)
    monkeypatch.setattr(launch.time, "sleep", lambda _s: None)

    # Cold-path: first `_credentials_present` check returns missing,
    # then `_first_run_ready` (bash -c) returns missing once, then ready.
    ready_checks = {"n": 0}
    captured_exec_calls: list[list[str]] = []

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        captured_exec_calls.append(args)
        if args[:3] == ["test", "-s", launch.CREDENTIALS_PATH]:
            return (1, "", "")  # cold detection: creds absent
        if args[:2] == ["bash", "-c"] and "settings.json" in args[2]:
            # _first_run_ready probe: fail once, then succeed.
            ready_checks["n"] += 1
            return (1, "", "") if ready_checks["n"] == 1 else (0, "", "")
        if args[:2] == ["tmux", "has-session"]:
            return (1, "", "")  # new session
        if args[0] == "test" and args[1] == "-d":
            return (0, "", "")  # worktree exists
        return (0, "", "")  # worktree add, tmux new-session via bash -lc, etc.

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)

    launched: list[str] = []
    original_launch = launch._launch_role

    def tracking_launch(cid: str, cfg: object, role: str, prompt_override: None) -> None:
        launched.append(role)
        original_launch(cid, cfg, role, prompt_override)

    monkeypatch.setattr(launch, "_launch_role", tracking_launch)

    ns = argparse.Namespace(only=None)
    launch.cmd_up(ns)

    assert launched == ["spec", "impl"], (
        "cold start must launch the human_interface role (spec) first, "
        f"then the rest — got {launched}"
    )
    out = capsys.readouterr().out
    assert "First-time setup" in out
    assert "moot attach spec" in out
    assert "Started 2 agents" in out
    # Enter dispatched to the cascaded siblings (impl), NOT the HI role (spec,
    # which the user dismissed manually during login setup).
    send_keys_calls = [
        a for a in captured_exec_calls if a[:2] == ["tmux", "send-keys"]
    ]
    assert send_keys_calls == [
        ["tmux", "send-keys", "-t", "moot-impl", "Enter"],
    ]


def test_cmd_up_warm_start_launches_all_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Warm start: credentials present → no cascade, no poll, launch all."""
    import moot.launch as launch

    monkeypatch.setattr(launch, "up", lambda wd: "cidWarm")
    monkeypatch.setattr(launch, "exec_detached", lambda *a, **kw: None)

    def never_sleep(_seconds: float) -> None:
        raise AssertionError("warm start must not hit the poll loop")

    monkeypatch.setattr(launch.time, "sleep", never_sleep)

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        if args[:3] == ["test", "-s", launch.CREDENTIALS_PATH]:
            return (0, "", "")  # creds present
        if args[:2] == ["tmux", "has-session"]:
            return (1, "", "")
        if args[0] == "test" and args[1] == "-d":
            return (0, "", "")
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)

    launched: list[str] = []
    monkeypatch.setattr(
        launch,
        "_launch_role",
        lambda cid, cfg, role, prompt_override: launched.append(role),
    )
    # The dev-channels warning is dismissed on warm start too (mock it so it
    # doesn't hit the forbidden time.sleep above).
    dismissed: list[str] = []
    monkeypatch.setattr(
        launch,
        "_auto_dismiss_dev_use_prompt",
        lambda cid, roles: dismissed.extend(roles),
    )

    ns = argparse.Namespace(only=None)
    launch.cmd_up(ns)
    assert launched == ["spec", "impl"]
    assert dismissed == ["spec", "impl"]  # ungated from cold_start
    out = capsys.readouterr().out
    assert "First-time setup" not in out
    assert "Started 2 agents" in out


def test_cmd_up_cold_start_requires_human_interface_in_only(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If --only excludes the HI role on a cold start, error out."""
    import moot.launch as launch

    monkeypatch.setattr(launch, "up", lambda wd: "cidCold")

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        if args[:3] == ["test", "-s", launch.CREDENTIALS_PATH]:
            return (1, "", "")  # missing
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)

    ns = argparse.Namespace(only="impl")  # excludes HI role "spec"
    with pytest.raises(SystemExit) as exc:
        launch.cmd_up(ns)
    assert exc.value.code == 1
    assert "cold start requires the human-interface role" in capsys.readouterr().out


def test_cmd_exec_errors_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`moot exec <role>` refuses to launch when creds aren't warm yet,
    pointing the user at `moot up` which handles cold-start cascade."""
    import moot.launch as launch

    monkeypatch.setattr(launch, "up", lambda wd: "cidCold")

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        if args[:3] == ["test", "-s", launch.CREDENTIALS_PATH]:
            return (1, "", "")
        return (0, "", "")

    monkeypatch.setattr(launch, "exec_capture", fake_exec_capture)
    ns = argparse.Namespace(role="spec", prompt=None)
    with pytest.raises(SystemExit) as exc:
        launch.cmd_exec(ns)
    assert exc.value.code == 1
    assert "claude credentials not yet present" in capsys.readouterr().out


def test_seed_claude_trust_seeds_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Pre-accepts the per-worktree trust + onboarding in ~/.claude.json and
    preserves existing entries (so launched agents skip the trust dialog)."""
    import json

    import moot.launch as launch

    claude_json = tmp_path / "claude.json"
    claude_json.write_text(
        json.dumps(
            {"projects": {"/workspaces/proj": {"hasTrustDialogAccepted": True}}}
        )
    )
    monkeypatch.setattr(launch, "CLAUDE_JSON_PATH", str(claude_json))

    launch._seed_claude_trust("/workspaces/proj/.worktrees/spec")

    data = json.loads(claude_json.read_text())
    wt = data["projects"]["/workspaces/proj/.worktrees/spec"]
    assert wt["hasTrustDialogAccepted"] is True
    assert wt["hasCompletedProjectOnboarding"] is True
    assert data["hasSeenAutoModeEntryWarning"] is True
    # Existing project entry is preserved.
    assert data["projects"]["/workspaces/proj"]["hasTrustDialogAccepted"] is True


def test_seed_claude_trust_is_best_effort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Writes a fresh file when absent; an unwritable path is swallowed."""
    import json

    import moot.launch as launch

    # Unwritable (parent dir missing) → swallowed, no raise.
    monkeypatch.setattr(launch, "CLAUDE_JSON_PATH", str(tmp_path / "missing" / "c.json"))
    launch._seed_claude_trust("/workspaces/proj/.worktrees/spec")

    # Fresh file when the directory exists.
    fresh = tmp_path / "claude.json"
    monkeypatch.setattr(launch, "CLAUDE_JSON_PATH", str(fresh))
    launch._seed_claude_trust("/workspaces/proj/.worktrees/spec")
    data = json.loads(fresh.read_text())
    assert (
        data["projects"]["/workspaces/proj/.worktrees/spec"]["hasTrustDialogAccepted"]
        is True
    )


def test_cmd_up_staggers_cascade_launches(
    monkeypatch: pytest.MonkeyPatch, patch_config: object
) -> None:
    """Successive cascade launches are separated by launch_stagger_seconds to
    avoid storming the convo join_space endpoint."""
    import moot.launch as launch

    patch_config.launch_stagger_seconds = 1.5  # type: ignore[attr-defined]
    monkeypatch.setattr(launch, "up", lambda wd: "cid")
    monkeypatch.setattr(launch, "_credentials_present", lambda cid: True)  # warm
    monkeypatch.setattr(launch, "_launch_role", lambda *a, **k: None)
    monkeypatch.setattr(launch, "_auto_dismiss_dev_use_prompt", lambda *a, **k: None)

    sleeps: list[float] = []
    monkeypatch.setattr(launch.time, "sleep", lambda s: sleeps.append(s))

    launch.cmd_up(argparse.Namespace(only=None))
    # Two roles → exactly one 1.5s gap (before the 2nd launch, not the 1st).
    assert sleeps == [1.5]
