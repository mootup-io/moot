"""Lifecycle commands: status, compact, attach — all routed through docker exec."""
from __future__ import annotations

from pathlib import Path

from moot.config import find_config
from moot.devcontainer import (
    container_id_or_none,
    exec_capture,
    exec_interactive,
)
from moot.launch import _session_exists, _session_name


def cmd_status() -> None:
    """Show the devcontainer and tmux session statuses for this workspace."""
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    container_id = container_id_or_none(Path.cwd())
    if container_id is None:
        print(f"{'CONTAINER':<12} STATUS")
        print(f"{'(none)':<12} STOPPED")
        return

    print(f"Container: {container_id[:12]}")
    print(f"{'ROLE':<20} {'SESSION':<20} {'STATUS'}")
    for role in config.roles:
        session = _session_name(role)
        status = "RUNNING" if _session_exists(container_id, role) else "STOPPED"
        print(f"{role:<20} {session:<20} {status}")


def cmd_compact(args: object) -> None:
    """Inject /compact into one or all agent tmux sessions."""
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
            exec_capture(
                container_id,
                ["tmux", "send-keys", "-t", session, "/compact", "Enter"],
            )
            print(f"Sent /compact to {session}")
        else:
            print(f"{session} not running — skipping")


def cmd_attach(args: object) -> None:
    """Attach to an agent's tmux session via `docker exec -it`.

    Blocks until the user detaches. No post-exit output — tmux handles
    its own display. If the session or container is missing, exits 1
    with an error.
    """
    role = getattr(args, "role")
    container_id = container_id_or_none(Path.cwd())
    if container_id is None:
        print("No devcontainer running for this workspace. Run 'moot up' first.")
        raise SystemExit(1)

    session = _session_name(role)
    if not _session_exists(container_id, role):
        print(f"Error: {session} not running")
        raise SystemExit(1)

    exec_interactive(
        container_id,
        ["tmux", "attach-session", "-t", session],
    )
