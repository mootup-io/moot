from __future__ import annotations

import subprocess
from pathlib import Path

from moot.config import find_config, load_agent_keys


def _ensure_worktree(role: str) -> Path:
    """Create git worktree for role if it doesn't exist."""
    wt_path = Path(f".worktrees/{role}")
    if wt_path.exists():
        return wt_path
    subprocess.run(
        ["git", "worktree", "add", str(wt_path), "main"],
        check=True,
        capture_output=True,
    )
    return wt_path


def _session_name(role: str) -> str:
    return f"moot-{role}"


def _session_exists(role: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", _session_name(role)],
        capture_output=True,
    )
    return result.returncode == 0


def cmd_exec(args: object) -> None:
    """Launch a single agent."""
    role = getattr(args, "role")
    prompt_override = getattr(args, "prompt", None)

    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    if role not in config.agents:
        print(f"Error: unknown role '{role}'. Available: {', '.join(config.roles)}")
        raise SystemExit(1)

    session = _session_name(role)
    if _session_exists(role):
        print(f"Session {session} already running")
        return

    worktree = _ensure_worktree(role)
    agent_config = config.agents[role]
    keys = load_agent_keys()
    api_key = keys.get(role, "")

    prompt = prompt_override or agent_config.startup_prompt

    # Create tmux session
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, "-c", str(worktree)],
        check=True,
    )

    # Set environment in the session
    for var, val in [
        ("CONVO_ROLE", role),
        ("CONVO_API_KEY", api_key),
        ("CONVO_API_URL", config.api_url),
    ]:
        if val:
            subprocess.run(
                ["tmux", "send-keys", "-t", session, f"export {var}={val}", "Enter"],
            )

    # Launch Claude Code
    match config.harness_type:
        case "claude-code":
            cmd = f"claude --dangerously-skip-permissions --dangerously-load-development-channels server:convo-channel -p '{prompt}'"
        case _:
            print(f"Error: harness '{config.harness_type}' not yet supported")
            raise SystemExit(1)

    subprocess.run(["tmux", "send-keys", "-t", session, cmd, "Enter"])
    print(f"Launched {role} in {session} (worktree: {worktree})")


def cmd_up(args: object) -> None:
    """Start all (or selected) agents."""
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    only = getattr(args, "only", None)
    roles = only.split(",") if only else config.roles

    for role in roles:
        if role not in config.agents:
            print(f"Warning: unknown role '{role}', skipping")
            continue
        # Reuse exec logic
        class FakeArgs:
            pass
        fake = FakeArgs()
        fake.role = role  # type: ignore[attr-defined]
        fake.prompt = None  # type: ignore[attr-defined]
        cmd_exec(fake)


def cmd_down(args: object) -> None:
    """Stop agents by killing tmux sessions."""
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    role = getattr(args, "role", None)
    roles = [role] if role else config.roles

    for r in roles:
        session = _session_name(r)
        if _session_exists(r):
            subprocess.run(["tmux", "kill-session", "-t", session])
            print(f"Stopped {session}")
        else:
            print(f"{session} not running")
