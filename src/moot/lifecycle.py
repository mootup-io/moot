from __future__ import annotations

import subprocess

from moot.config import find_config
from moot.launch import _session_exists, _session_name


def cmd_status() -> None:
    """Show running agents."""
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    print(f"{'ROLE':<20} {'SESSION':<20} {'STATUS'}")
    for role in config.roles:
        session = _session_name(role)
        status = "RUNNING" if _session_exists(role) else "STOPPED"
        print(f"{role:<20} {session:<20} {status}")


def cmd_compact(args: object) -> None:
    """Inject /compact into agent sessions."""
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    role = getattr(args, "role", None)
    roles = [role] if role else config.roles

    for r in roles:
        session = _session_name(r)
        if _session_exists(r):
            subprocess.run(["tmux", "send-keys", "-t", session, "/compact", "Enter"])
            print(f"Sent /compact to {session}")
        else:
            print(f"{session} not running — skipping")


def cmd_attach(args: object) -> None:
    """Attach to an agent's tmux session."""
    role = getattr(args, "role")
    session = _session_name(role)
    if not _session_exists(role):
        print(f"Error: {session} not running")
        raise SystemExit(1)
    subprocess.run(["tmux", "attach-session", "-t", session])
