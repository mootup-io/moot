"""Launch Claude agents in tmux sessions inside the bundled devcontainer."""
from __future__ import annotations

import shlex
import sys
import time
from pathlib import Path

from moot.config import MootConfig, find_config
from moot.devcontainer import (
    container_id_or_none,
    exec_capture,
    exec_detached,
    up,
)


CREDENTIALS_PATH = "/home/node/.claude/.credentials.json"
SETTINGS_PATH = "/home/node/.claude/settings.json"
AUTH_POLL_INTERVAL_S = 5.0
# Short grace period after first-run state has fully landed on disk.
# Claude writes credentials + settings incrementally during the theme +
# login flow; a second of slack ensures the last write has flushed
# before we spawn siblings that read those files.
AUTH_SETTLE_S = 2.0


def _session_name(role: str) -> str:
    return f"moot-{role}"


def _credentials_present(container_id: str) -> bool:
    """True if claude's host-side credentials file exists in the container."""
    rc, _stdout, _stderr = exec_capture(
        container_id,
        ["test", "-s", CREDENTIALS_PATH],
    )
    return rc == 0


def _first_run_ready(container_id: str) -> bool:
    """True if both credentials AND settings.json exist.

    settings.json is written by claude after the user dismisses the
    theme picker (a per-user choice that follows /login in the first-run
    flow). Waiting for both signals that the user has finished the
    user-scope portion of onboarding, so sibling agents launched after
    this point won't re-hit the theme prompt. Per-worktree prompts
    (dev-use approval, workspace trust) are unavoidable — each agent
    must go through those regardless.
    """
    rc, _stdout, _stderr = exec_capture(
        container_id,
        [
            "bash", "-c",
            f"test -s {CREDENTIALS_PATH} && test -s {SETTINGS_PATH}",
        ],
    )
    return rc == 0


def _wait_for_credentials(container_id: str, human_interface: str) -> None:
    """Block until claude first-run setup is complete in the container.

    Called on cold-start after launching the human-interface role so the
    user can `moot attach <role>`, complete /login + theme + any other
    first-run prompts, then detach. Polls until both credentials and
    settings.json are present, plus a short settle to let the final
    writes flush. Ctrl-C cancels the cascade; the human-interface
    session keeps running so the user can rerun `moot up` later.
    """
    print(
        f"\nFirst-time setup: claude authentication required.\n"
        f"  1. In another terminal: moot attach {human_interface}\n"
        f"  2. Complete /login, pick a theme, approve the dev-use "
        f"notice, and reach the claude prompt.\n"
        f"  3. Detach (Ctrl-Space d or /detach).\n"
    )
    print("Waiting for first-run setup ", end="", flush=True)
    try:
        while not _first_run_ready(container_id):
            time.sleep(AUTH_POLL_INTERVAL_S)
            print(".", end="", flush=True)
    except KeyboardInterrupt:
        print(
            f"\nAborted. {human_interface} is still running; rerun `moot up` "
            f"after finishing first-run setup to launch the rest of the team."
        )
        sys.exit(130)
    print(" ✓")
    time.sleep(AUTH_SETTLE_S)


DEV_USE_PROMPT_DELAY_S = 5.0


def _auto_dismiss_dev_use_prompt(
    container_id: str, roles: list[str]
) -> None:
    """Send Enter to each freshly-launched agent to dismiss the per-
    workspace 'I am using this for development use only' disclaimer.

    The disclaimer is per-claude-workspace; each worktree hits it on
    first start. On cold-start cascade, every sibling agent starts in
    a fresh worktree and would otherwise require a manual `moot attach`
    + Enter per role to reach the prompt. We dismiss it automatically
    so the team is fully online after `moot up` returns.

    The human-interface role is excluded because the user has already
    dismissed its prompt manually during the login/theme setup pass.
    """
    print(f"Dismissing dev-use disclaimer on {len(roles)} agent(s)...")
    time.sleep(DEV_USE_PROMPT_DELAY_S)
    for role in roles:
        session = _session_name(role)
        exec_capture(
            container_id,
            ["tmux", "send-keys", "-t", session, "Enter"],
        )


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

    # Per-role env that MUST override the tmux server's env. Tmux sessions
    # created inside an existing server inherit the SERVER's env (set when
    # the server started, from the FIRST role launched), not the env of
    # the shell that invoked `new-session`. So every per-role value has
    # to go through `tmux new-session -e` — otherwise spec/impl/qa all
    # run with product's CONVO_ROLE and connect to convo as Product.
    #
    # CONVO_API_KEY is deliberately NOT included: the convo MCP wrapper
    # scripts look it up from .moot/actors.json at runtime using
    # CONVO_ROLE. Keeping it out of env also keeps the secret off every
    # tmux / ps command line.
    pane_env: dict[str, str] = {
        "CONVO_ROLE": role,
        "CONVO_API_URL": config.api_url,
    }
    tmux_e_flags = " ".join(
        f"-e {shlex.quote(f'{k}={v}')}" for k, v in pane_env.items()
    )

    tmux_cmd = (
        f"tmux -u new-session -d -s {shlex.quote(session)} "
        f"{tmux_e_flags} "
        f"-c {shlex.quote(wt_path)} "
        f"-- {claude_cmd}"
    )

    # docker exec env: shared settings that become the tmux SERVER env on
    # first launch and are inherited by all subsequent sessions (since
    # they don't vary per role). TERM/LANG/COLORTERM keep claude's TUI
    # rendering correct; TMUX_TMPDIR pins the socket path for /detach.
    env: dict[str, str] = {
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMUX_TMPDIR": "/tmp",
    }

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
    if not _credentials_present(container_id):
        print(
            f"Error: claude credentials not yet present in container. "
            f"Run `moot up` first (it launches {config.human_interface} so you "
            f"can complete /login)."
        )
        raise SystemExit(1)
    _launch_role(container_id, config, role, prompt_override)


def cmd_up(args: object) -> None:
    """Start all (or selected) agents. Boots the container once.

    Cold-start cascade: if claude's credentials file is not yet present
    inside the container, launch ONLY the human-interface role first,
    block until the user completes /login (poll for the credentials file),
    then launch the remaining roles. This matches the coclaude one-login
    UX without dropping the user into a standalone claude instance — they
    log in through their actual product session.

    Warm-start: credentials already exist, launch all requested roles in
    parallel (subsecond).

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

    cold_start = not _credentials_present(container_id)
    if cold_start:
        hi = config.human_interface
        if hi not in roles:
            print(
                f"Error: cold start requires the human-interface role "
                f"'{hi}' to be in the launch set (got: {', '.join(roles)}). "
                f"Omit --only or include {hi} so first-time /login can run."
            )
            raise SystemExit(1)
        if hi not in config.agents:
            print(
                f"Error: human_interface = '{hi}' in moot.toml, but no such "
                f"agent is configured. Fix [harness].human_interface."
            )
            raise SystemExit(1)
        _launch_role(container_id, config, hi, prompt_override=None)
        _wait_for_credentials(container_id, hi)
        roles = [r for r in roles if r != hi]

    alive = 1 if cold_start else 0
    cascaded_roles: list[str] = []
    for role in roles:
        if role not in config.agents:
            print(f"Warning: unknown role '{role}', skipping")
            continue
        _launch_role(container_id, config, role, prompt_override=None)
        cascaded_roles.append(role)
        alive += 1

    if cold_start and cascaded_roles:
        _auto_dismiss_dev_use_prompt(container_id, cascaded_roles)

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
