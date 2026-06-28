"""Local process helpers for the in-devcontainer launcher.

The python launcher runs only *inside* the bundled devcontainer that
`moot init` installs: the host `@mootup/moot-cli` boots the devcontainer and
then execs `moot <cmd>` within it. Agent sessions are local tmux sessions in
this same container, so these helpers run their commands **locally** — there is
no `docker exec` and no container-id discovery. (The devcontainer is
docker-in-docker; from inside, `docker ps` sees only the inner daemon, never the
host container, so reflecting for "the container" cannot work and is not needed.)

`container_id` parameters are accepted for call compatibility and ignored; the
value is only used for display. API keys and secrets are passed via the `env`
parameter so they travel in the process environment, never on the command line
(ps, scrollback, tmux env dump).
"""
from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path


class DevcontainerError(RuntimeError):
    """Any failure resolving the container or running an agent command."""


def container_id_or_none(workspace: Path) -> str | None:
    """Return the id of the devcontainer this launcher runs inside.

    The launcher runs only inside the devcontainer, so this reports the
    *current* container — its hostname, which Docker sets to the short container
    id — rather than reflecting via `docker ps` (which from inside
    docker-in-docker sees the inner daemon, not the host container). The
    signature is kept as `str | None` for call compatibility; in practice it is
    always the current container. `workspace` is unused.
    """
    return socket.gethostname() or None


def up(workspace: Path) -> str:
    """Report the devcontainer this launcher runs inside (no management).

    The launcher runs only inside the devcontainer; the host `@mootup/moot-cli`
    is what boots it. `up` therefore performs no devcontainer bring-up or
    discovery — it returns the current container id for display, and the caller
    launches agent sessions locally.
    """
    return container_id_or_none(workspace) or "devcontainer"


def _local_env(env: dict[str, str] | None) -> dict[str, str]:
    """Layer `env` over the current process environment.

    Secrets travel in the process environment, never on the command line,
    preserving the guarantee the old `docker exec -e` plumbing gave now that
    commands run locally.
    """
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return merged


def exec_capture(
    container_id: str,
    args: list[str],
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run `args` locally, capturing output. Returns (returncode, stdout, stderr).

    Agent commands run as local subprocesses (the launcher is already inside the
    devcontainer). `container_id` is accepted for call compatibility and ignored.
    Does NOT raise on nonzero rc — the caller decides what a nonzero rc means
    (e.g. `tmux has-session` returns 1 when the session does not exist).
    """
    proc = subprocess.run(
        args, capture_output=True, text=True, env=_local_env(env)
    )
    return proc.returncode, proc.stdout, proc.stderr


def exec_detached(
    container_id: str,
    args: list[str],
    env: dict[str, str] | None = None,
) -> None:
    """Spawn `args` locally without waiting (fire-and-forget).

    Used for launching tmux `new-session -d` (the session persists after the
    call returns). `container_id` is accepted for call compatibility and ignored.
    """
    subprocess.Popen(args, env=_local_env(env))


def exec_interactive(container_id: str, args: list[str]) -> None:
    """Run `args` locally with inherited stdio (e.g. `tmux attach-session`).

    Blocks until the command exits; stdio is inherited so tmux attach works in
    the terminal the host `docker exec -it` provides. Does not raise on nonzero
    rc — interactive commands routinely exit nonzero on Ctrl-C / Ctrl-D.

    Pins TERM=xterm-256color + a UTF-8 LANG so tmux finds a usable terminfo
    entry (the container's terminfo DB is limited — `xterm-24bits`,
    `xterm-kitty`, etc. typically aren't present and tmux refuses to start with
    "missing or unsuitable terminal"). COLORTERM passes through from the current
    environment so truecolor TUIs still render. `container_id` is ignored.
    """
    env = _local_env({"TERM": "xterm-256color", "LANG": "C.UTF-8"})
    subprocess.run(args, check=False, env=env)
