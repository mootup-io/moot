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

import json
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

    Runs `devcontainer up --workspace-folder <workspace> --log-format json`.
    The CLI writes newline-delimited JSON to stdout; the final line is the
    result object (`{"outcome": "success", "containerId": "...", ...}` or
    `{"outcome": "error", "message": "..."}`). Idempotent — if the container
    already exists and is running, the CLI returns its id without rebooting.
    """
    ensure_cli()
    proc = subprocess.run(
        [
            "devcontainer", "up",
            "--workspace-folder", str(workspace),
            "--log-format", "json",
        ],
        capture_output=True,
        text=True,
    )
    lines = proc.stdout.strip().splitlines()
    if not lines:
        raise DevcontainerError(
            f"devcontainer up produced no output (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:500]}"
        )
    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as e:
        raise DevcontainerError(
            f"could not parse devcontainer up final line: {e}\n"
            f"line: {lines[-1][:500]}"
        )
    if result.get("outcome") != "success":
        msg = result.get("message") or result.get("description") or "unknown error"
        raise DevcontainerError(f"devcontainer up failed: {msg}")
    container_id = result.get("containerId")
    if not container_id:
        raise DevcontainerError(
            "devcontainer up reported success but returned no containerId"
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
    """
    cmd = ["docker", "exec", "-it", "--user", "node", container_id] + args
    subprocess.run(cmd, check=False)
