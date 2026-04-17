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

    If the session doesn't exist yet (e.g., the user /exit'd claude and
    tore down the tmux session), relaunch the role inline instead of
    erroring — saves a `moot up` round-trip. Requires the container to
    be up and claude credentials to already be warm; if not, point at
    `moot up` which handles cold-start cascade.

    Blocks until the user detaches. No post-exit output — tmux handles
    its own display.
    """
    role = getattr(args, "role")
    container_id = container_id_or_none(Path.cwd())
    if container_id is None:
        print("No devcontainer running for this workspace. Run 'moot up' first.")
        raise SystemExit(1)

    session = _session_name(role)
    if not _session_exists(container_id, role):
        # Auto-relaunch the role. Lazy import to avoid circularity
        # through lifecycle ← launch ← config dependency chain.
        from moot.config import find_config
        from moot.launch import _credentials_present, _launch_role

        config = find_config()
        if config is None:
            print("Error: no moot.toml found. Run 'moot init' first.")
            raise SystemExit(1)
        if role not in config.agents:
            print(
                f"Error: unknown role '{role}'. "
                f"Available: {', '.join(config.roles)}"
            )
            raise SystemExit(1)
        if not _credentials_present(container_id):
            print(
                "Error: claude credentials not yet present. Run `moot up` "
                "to complete first-time setup."
            )
            raise SystemExit(1)
        print(f"{session} not running — launching...")
        _launch_role(container_id, config, role, prompt_override=None)

    exec_interactive(
        container_id,
        ["tmux", "attach-session", "-t", session],
    )


def cmd_detach(args: object) -> None:
    """Detach any attached client from an agent's tmux session.

    Leaves claude running inside the session; only disconnects the
    terminal. Complements `moot attach` when the user can't press the
    tmux prefix from inside claude (claude intercepts Ctrl-B). The
    bundled .tmux.conf also rebinds the prefix to Ctrl-Space, so
    `<prefix> d` works from inside a session — this command is the
    external escape hatch.
    """
    role = getattr(args, "role")
    container_id = container_id_or_none(Path.cwd())
    if container_id is None:
        print("No devcontainer running for this workspace.")
        return

    session = _session_name(role)
    if not _session_exists(container_id, role):
        print(f"{session} not running")
        return

    exec_capture(
        container_id,
        ["tmux", "detach-client", "-s", session],
    )
    print(f"Detached all clients from {session}")
