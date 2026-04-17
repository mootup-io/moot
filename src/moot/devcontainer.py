"""devcontainer CLI + docker exec wrapper.

Single source of truth for how moot-cli talks to the bundled devcontainer
that `moot init` installs. The host runs `devcontainer up` once to boot (or
rediscover) the container, then uses raw `docker exec` for every subsequent
call. docker exec is ~10x faster than going through the devcontainer CLI for
each command, supports -e for env, -d for detached, -it for interactive, and
--user to pin the container user.

All exec calls run as --user node (matching devcontainer.json's remoteUser).
API keys and secrets MUST be passed via the `env` parameter so they never
appear on the bash command line (ps, scrollback, tmux env dump).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class DevcontainerError(RuntimeError):
    """Any failure talking to the devcontainer CLI or to docker exec."""


def ensure_cli() -> None:
    """Assert `devcontainer` is on PATH. Raise with install hint if not."""
    if shutil.which("devcontainer") is None:
        raise DevcontainerError(
            "devcontainer CLI not found on PATH.\n"
            "Install with: npm i -g @devcontainers/cli\n"
            "Docs: https://containers.dev/supporting#devcontainer-cli"
        )


def up(workspace: Path) -> str:
    """Boot (or rediscover) the devcontainer for `workspace`; return its id.

    Runs `devcontainer up --workspace-folder <workspace>` in default text
    log format and streams stdout/stderr to the user's terminal. After the
    subprocess exits, looks up the running container id via
    `container_id_or_none()` (which queries the `devcontainer.local_folder`
    label). On non-zero exit, raises `DevcontainerError` with the exit
    code — the actual error output is already on the user's terminal, so
    we don't re-embed it in the exception message.

    Prints a pre-build hint only when no container is currently running
    for this workspace. The CLI's idempotent re-up path is ~0.35s, so
    we don't short-circuit; we just suppress the "can take 1-3 minutes"
    line that would be misleading on a re-up.
    """
    ensure_cli()
    already_running = container_id_or_none(workspace) is not None
    if not already_running:
        print(
            f"Building devcontainer in {workspace} "
            "(first launch can take 1-3 minutes)..."
        )
    proc = subprocess.run(
        ["devcontainer", "up", "--workspace-folder", str(workspace)],
    )
    if proc.returncode != 0:
        raise DevcontainerError(
            f"devcontainer up failed (exit code {proc.returncode})"
        )
    container_id = container_id_or_none(workspace)
    if not container_id:
        raise DevcontainerError(
            f"devcontainer up exited 0 but no running container was found "
            f"for {workspace}"
        )
    return container_id


def container_id_or_none(workspace: Path) -> str | None:
    """Return the running container id for `workspace`, or None if not running.

    Queries `docker ps` by the `devcontainer.local_folder` label that the
    devcontainer CLI stamps on every container it creates. Uses
    Path.resolve() so the label filter matches the absolute path the CLI
    wrote at creation time.
    """
    abs_path = str(Path(workspace).resolve())
    proc = subprocess.run(
        [
            "docker", "ps", "-q",
            "--filter", f"label=devcontainer.local_folder={abs_path}",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    ids = proc.stdout.strip().splitlines()
    return ids[0] if ids else None


def _env_args(env: dict[str, str] | None) -> list[str]:
    """Build `-e KEY=VALUE` pairs for docker exec; empty list if env is None."""
    if not env:
        return []
    args: list[str] = []
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    return args


def exec_capture(
    container_id: str,
    args: list[str],
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run `docker exec --user node [-e ...] <cid> <args...>`, capture output.

    Returns (returncode, stdout, stderr). Does NOT raise on nonzero rc — the
    caller decides what a nonzero rc means (e.g. `tmux has-session` returns 1
    when the session does not exist, which is a success signal to the caller).
    """
    cmd = ["docker", "exec", "--user", "node"] + _env_args(env) + [container_id] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def exec_detached(
    container_id: str,
    args: list[str],
    env: dict[str, str] | None = None,
) -> None:
    """Run `docker exec -d --user node [-e ...] <cid> <args...>`.

    Fire-and-forget — docker exec returns immediately once the command is
    spawned inside the container. Used for launching tmux new-session (the
    session persists after docker exec returns). Raises CalledProcessError
    on nonzero rc from `docker exec` itself (rare; typically indicates the
    container stopped between check and spawn).
    """
    cmd = (
        ["docker", "exec", "-d", "--user", "node"]
        + _env_args(env)
        + [container_id]
        + args
    )
    subprocess.run(cmd, check=True)


def exec_interactive(container_id: str, args: list[str]) -> None:
    """Run `docker exec -it --user node <cid> <args...>`.

    Blocks until the user exits. stdio is inherited from the parent, so
    tmux attach-session (or any interactive command) works naturally.
    Does not raise on nonzero rc — interactive commands routinely exit
    nonzero on Ctrl-C or Ctrl-D and that is not an error to surface.

    Sets TERM=xterm-256color + a UTF-8 LANG inside the container so the
    tmux client has a terminfo entry it can find (the container's
    terminfo DB is limited — `xterm-24bits`, `xterm-kitty`, `alacritty`
    and other host-specific entries typically aren't present and tmux
    refuses to start with "missing or unsuitable terminal"). Propagates
    COLORTERM through from the host so modern TUIs still pick up
    truecolor. These together are what keep claude's TUI logo, borders,
    and colors rendering correctly across host terminals.
    """
    import os

    term_env = [
        "-e", "TERM=xterm-256color",
        "-e", "LANG=C.UTF-8",
    ]
    colorterm = os.environ.get("COLORTERM")
    if colorterm:
        term_env += ["-e", f"COLORTERM={colorterm}"]

    cmd = (
        ["docker", "exec", "-it", "--user", "node"]
        + term_env
        + [container_id]
        + args
    )
    subprocess.run(cmd, check=False)
