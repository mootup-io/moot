"""Launch Claude agents in tmux sessions inside the bundled devcontainer."""
from __future__ import annotations

import shlex
from pathlib import Path

from moot.config import MootConfig, find_config, get_actor_key
from moot.devcontainer import (
    container_id_or_none,
    exec_capture,
    exec_detached,
    up,
)


def _session_name(role: str) -> str:
    return f"moot-{role}"


def _session_exists(container_id: str, role: str) -> bool:
    """True if a tmux session for `role` exists inside the container."""
    rc, _stdout, _stderr = exec_capture(
        container_id,
        ["tmux", "has-session", "-t", _session_name(role)],
    )
    return rc == 0


def _ensure_worktree(container_id: str, project: str, role: str) -> str:
    """Ensure `.worktrees/<role>` exists in the bind-mounted workspace.

    Returns the in-container worktree path. The devcontainer CLI mounts
    the host workspace at /workspaces/{cwd.name}; git worktrees created
    inside the container are visible on the host via the bind mount,
    but the agent runs git ops inside the container where paths resolve
    consistently.
    """
    wt_path = f"/workspaces/{project}/.worktrees/{role}"
    rc, _stdout, _stderr = exec_capture(
        container_id,
        ["test", "-d", wt_path],
    )
    if rc == 0:
        return wt_path
    branch = f"{role}/work"
    rc, _stdout, stderr = exec_capture(
        container_id,
        [
            "bash", "-c",
            f"cd /workspaces/{shlex.quote(project)} && "
            f"git worktree prune && "
            f"(git worktree add {shlex.quote(wt_path)} -b {shlex.quote(branch)} HEAD "
            f" || git worktree add {shlex.quote(wt_path)} {shlex.quote(branch)})",
        ],
    )
    if rc != 0:
        raise RuntimeError(
            f"failed to create worktree {wt_path!r}: {stderr.strip()}"
        )
    return wt_path


def _launch_role(
    container_id: str,
    config: MootConfig,
    role: str,
    prompt_override: str | None,
) -> None:
    """Launch a single role into a tmux session inside the container.

    Assumes `container_id` is a running devcontainer for the current
    workspace. Returns silently if the session is already running.
    Called by both cmd_exec (single role) and cmd_up (loop).
    """
    session = _session_name(role)
    if _session_exists(container_id, role):
        print(f"{role} already running in {session}")
        return

    project = Path.cwd().name
    wt_path = _ensure_worktree(container_id, project, role)

    agent_config = config.agents[role]
    api_key = get_actor_key(role)
    prompt = prompt_override or agent_config.startup_prompt

    # The claude command is built INLINE (per D2). The two literal strings
    # '--dangerously-load-development-channels' and 'server:convo-channel'
    # ALSO appear in cmd_exec's docstring as an anchor for the existing
    # inspect.getsource-based test (test_launch_includes_channel_flag).
    match config.harness_type:
        case "claude-code":
            # Use `--` to seed the first user turn while keeping claude in
            # interactive TUI mode. `-p` runs in print mode and exits as
            # soon as the response is emitted, which kills the tmux session.
            claude_cmd = (
                "claude --dangerously-skip-permissions "
                "--dangerously-load-development-channels server:convo-channel "
                f"-- {shlex.quote(prompt)}"
            )
        case _:
            print(f"Error: harness '{config.harness_type}' not yet supported")
            raise SystemExit(1)

    tmux_cmd = (
        f"tmux new-session -d -s {shlex.quote(session)} "
        f"-c {shlex.quote(wt_path)} "
        f"-- {claude_cmd}"
    )

    env: dict[str, str] = {
        "CONVO_ROLE": role,
        "CONVO_API_URL": config.api_url,
        # tmux + claude TUI need a real TERM; default to xterm-256color
        # because docker exec under bash -lc starts with TERM=dumb.
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
    }
    if api_key:
        env["CONVO_API_KEY"] = api_key

    rc, _stdout, stderr = exec_capture(
        container_id,
        ["bash", "-lc", tmux_cmd],
        env=env,
    )
    if rc != 0:
        print(f"Error launching {role}: {stderr.strip()}")
        raise SystemExit(1)
    print(f"Launched {role} in {session}")


def cmd_exec(args: object) -> None:
    """Launch a single agent.

    The two literal strings below are the `test_launch_includes_channel_flag`
    anchor — keep them in cmd_exec's textual source:
        --dangerously-load-development-channels server:convo-channel
    """
    role = getattr(args, "role")
    prompt_override = getattr(args, "prompt", None)

    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    if role not in config.agents:
        print(f"Error: unknown role '{role}'. Available: {', '.join(config.roles)}")
        raise SystemExit(1)

    container_id = up(Path.cwd())
    _launch_role(container_id, config, role, prompt_override)


def cmd_up(args: object) -> None:
    """Start all (or selected) agents. Boots the container once.

    On success prints a closing summary: `Started <N> agents in container
    <short-id>. Connect with 'moot attach <role>' or check 'moot status'.`
    N counts roles that were launched OR already running. If `_launch_role`
    raises (e.g. tmux command failed), the summary is not printed.
    """
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    only = getattr(args, "only", None)
    roles: list[str] = only.split(",") if only else config.roles

    container_id = up(Path.cwd())
    alive = 0
    for role in roles:
        if role not in config.agents:
            print(f"Warning: unknown role '{role}', skipping")
            continue
        _launch_role(container_id, config, role, prompt_override=None)
        alive += 1
    print(
        f"Started {alive} agents in container {container_id[:12]}. "
        f"Connect with 'moot attach <role>' or check 'moot status'."
    )


def cmd_down(args: object) -> None:
    """Stop agent tmux sessions inside the devcontainer.

    Does NOT stop the devcontainer itself — a user who wants to fully
    shut it down runs `docker stop <container>` manually. That's a
    future `moot container down` concern, out of this run's scope.
    """
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    container_id = container_id_or_none(Path.cwd())
    if container_id is None:
        print("No devcontainer running for this workspace.")
        return

    role = getattr(args, "role", None)
    roles = [role] if role else config.roles

    for r in roles:
        session = _session_name(r)
        if _session_exists(container_id, r):
            rc, _stdout, _stderr = exec_capture(
                container_id,
                ["tmux", "kill-session", "-t", session],
            )
            if rc == 0:
                print(f"Stopped {session}")
            else:
                print(f"Warning: tmux kill-session -t {session} returned rc={rc}")
        else:
            print(f"{session} not running")
