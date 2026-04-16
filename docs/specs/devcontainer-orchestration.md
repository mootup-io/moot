# moot up: orchestrate the bundled devcontainer instead of host tmux

**Status:** Design spec — feat/devcontainer-orchestration
**Baseline:** mootup-io/moot `feat/devcontainer-orchestration` @ `77bd6bf`
**Pipeline variant:** Standard (spike-empowered)
**Run:** T (third cross-repo run in mootup-io/moot; follows Q brand-login, R init-full-provisioning)
**Kickoff:** Product `evt_5mmj8r76s0pd5` (convo); Operational `evt_1mae64n13f8gd` (convo); feature thread `thr_4yrbpnry6atdy`

## § 1. Summary

Rewrite moot-cli's launch path so `moot up`, `moot exec`, `moot down`, `moot status`, `moot compact`, `moot attach` orchestrate the **bundled devcontainer** that `moot init` installs, instead of running `tmux` directly on the user's host. The host now only needs `docker` and the `@devcontainers/cli` npm package; everything else (tmux, claude, uv, moot, MCP adapters) is inside the container that `post-create.sh` provisions.

**Shape of the change:**

1. New module `src/moot/devcontainer.py` — single source of truth for the `devcontainer` CLI + `docker exec`.
2. `src/moot/launch.py` rewritten — every subprocess call routes through `devcontainer.py`; worktree creation moves inside the container; the claude launch command is built **inline** (no bundled launcher script).
3. `src/moot/lifecycle.py` rewritten — `cmd_status`, `cmd_compact`, `cmd_attach` proxy through `docker exec`.
4. New tests: `tests/test_devcontainer.py`, `tests/test_launch.py`, `tests/test_lifecycle.py` — mock `subprocess.run` at the boundary.
5. Version bump `0.1.6 → 0.2.0` (behavior change: host now requires `devcontainer` CLI).
6. The one existing launch-related test (`test_launch_includes_channel_flag`) stays green unmodified.

**Projected diff:** ~520 LOC across 3 source files (new + 2 rewrites) + ~400 LOC of new tests. Spec target: ~1500 lines. **Out of template scope:** no changes to `src/moot/templates/devcontainer/*` — the bundled template already installs everything we need.

## § 2. Baseline (frozen at `77bd6bf`)

Measured from `/workspaces/convo/mootup-io/moot/.worktrees/spec` at commit `77bd6bf33d27cd4c4456b265da2e4c5e2d1b55ea`.

| Gate | Count | Command |
|------|-------|---------|
| pytest passed | 72 | `uv run pytest -q` |
| pytest failed | 15 (pre-existing; see breakdown below) | same |
| pyright errors | 11 (pre-existing) | `uv run pyright` |

### 2.1. Pre-existing test failures (out of scope for Run T)

- **`tests/test_cli.py::test_cli_version_importable` (1 failure)** — asserts `__version__ == "0.1.0"` but the package is already at `0.1.6` (drifted by Runs Q & R which shipped without touching this test). **This run updates the assertion** because it already changes `__version__`; see D9. This moves from fail → pass on ship.

- **`tests/test_example.py::{test_moot_toml_valid, test_devcontainer_json_valid, test_post_create_installs_moot, test_runner_scripts_unchanged, test_gitignore_entries}` (5 failures)** — pre-existing worktree-path bug. `Path(__file__).parents[N]` walks past the worktree boundary looking for `examples/markdraft/` at `.worktrees/examples/markdraft/`. Run Q's § 2 also enumerated these. Not in scope.

- **`tests/test_scaffold.py::test_init_*` (9 failures)** — `respx.models.AllMockedAssertionError: <Request('GET', 'https://mootup.io/api/actors/me/agents')> not mocked!`. Pre-existing drift between the mocked `/api/actors/me` fixture in Run R and a subsequent backend-side addition of `/api/actors/me/agents` lookup (shipped after Run R). Fixing these is a separate cleanup — out of this run's scope. Named regressions:
    - `test_init_greenfield_rotates_and_installs`
    - `test_init_conflict_stages_claude_md`
    - `test_init_conflict_stages_skill`
    - `test_init_conflict_stages_devcontainer`
    - `test_init_force_rotates_keys`
    - `test_init_adopt_fresh_install_overwrites`
    - `test_init_rotate_key_failure_does_not_persist`
    - `test_init_warns_on_non_git_repo`
    - `test_init_placeholder_substitution`

**Ship rule:** target counts carry the 14 remaining pre-existing failures forward. The 1 version-drift failure moves fail → pass because D9 updates the assertion.

### 2.2. Pre-existing pyright errors (11, out of scope)

Concentrated in `src/moot/adapters/mcp_adapter.py` and `src/moot/adapters/channel_runner.py` — httpx parameter types and a `str | None` → `str` leak on `_parse_duration`. Run T touches neither file. New code written by this run MUST NOT add to the count; see § 7.5 for the annotation conventions.

### 2.3. Grep baseline

```
$ grep -rn 'subprocess.run\(.*tmux' src/moot/launch.py src/moot/lifecycle.py
launch.py:61   tmux new-session -d -s … -c …
launch.py:73   tmux send-keys -t … export …
launch.py:84   tmux send-keys -t … <claude cmd>
launch.py:124  tmux kill-session -t …
lifecycle.py:36 tmux send-keys -t … /compact Enter
lifecycle.py:49 tmux attach-session -t …

$ grep -rn "subprocess.run\(.*\[.git." src/moot/launch.py
launch.py:15   git worktree add … main
```

All 7 host-tmux and 1 host-git call sites disappear by Run T. The replacement uses 0 host-tmux calls and 0 host-git calls; every operation routes through the `devcontainer.py` module.

## § 3. Scope

### 3.1. In scope

1. `src/moot/devcontainer.py` — CREATE (new module, ~130 LOC)
2. `src/moot/launch.py` — REWRITE (full-file replacement; see § 6.2)
3. `src/moot/lifecycle.py` — REWRITE (full-file replacement; see § 6.3)
4. `src/moot/__init__.py` — version bump `0.1.6 → 0.2.0`
5. `pyproject.toml` — version bump `0.1.6 → 0.2.0`
6. `tests/test_cli.py::test_cli_version_importable` — update assertion (D9)
7. `tests/test_devcontainer.py` — CREATE (new file, ~11 tests)
8. `tests/test_launch.py` — CREATE (new file, ~6 tests)
9. `tests/test_lifecycle.py` — CREATE (new file, ~5 tests)
10. `docs/specs/devcontainer-orchestration.md` — this spec (Spec creates, direct commit OK per CLAUDE.md)

### 3.2. Out of scope (explicit)

Per Product kickoff "Scope (out)":

- **No changes to `src/moot/templates/devcontainer/{devcontainer.json, post-create.sh, run-moot-*.sh}`.** `post-create.sh` already installs tmux, claude, uv, moot, and both MCP adapters. The template is stable; changing it now would force `moot init` re-runs for existing users.
- **No per-role devcontainer.** Single shared container, N tmux sessions — mirrors convo's `coclaude` pattern. Future concern if isolation becomes a real problem.
- **No docker-compose fallback if `devcontainer` CLI is missing.** Hard-error with the `npm i -g @devcontainers/cli` install hint.
- **No bundled `launch-agent.sh` script.** Launch command built inline in Python (per D2).
- **No changes to `moot init`, `moot login`, `moot config`.** Not this run.
- **No backend changes.** Pure CLI-side.
- **No fix for the 9 pre-existing `test_init_*` respx-mock drift failures.** Separate cleanup owned by the next moot-cli test-hygiene run.
- **No `moot container down` / `docker stop` command.** `cmd_down` stops tmux sessions only; stopping the container itself is a user-driven `docker stop`, deferred. Captured as a documented followup in § 10.

### 3.3. Not-a-template-change rationale

The bundled `post-create.sh` installs `pip install moot`, which pins whichever moot-cli version is on PyPI at `moot init` time. After Run T ships, existing users who ran `moot init` before 0.2.0 will have a container with 0.1.x CLI inside; upgrading requires re-running `post-create.sh` or `pip install -U moot` inside the container. That's a known adoption-lag cost, not a reason to touch the template in this run. **Important:** the host-side moot 0.2.0 is what invokes `devcontainer` + `docker exec`; the in-container moot version is only used by agents themselves if they shell out to `moot` (none do today). So the adoption lag doesn't block anything immediate.

## § 4. D-decisions

All locked by Product in the kickoff. Spec records them here and adds 5 additional in-draft decisions (D7-D11) resolving silences in the Product doc per `feedback_spec_resolves_product_doc_silences.md`.

### D1. Single shared devcontainer, N tmux sessions

One container per workspace. All roles share it; per-role tmux sessions provide separation. Mirrors convo's `coclaude` pattern. Matches `post-create.sh` which installs tmux + claude + uv + MCP adapters once. **Locked by Product.**

### D2. Inline launcher command, no bundled launch-agent.sh

The bash that launches claude is assembled in Python and handed to `docker exec bash -c '...'`. No bundled shell script. CLI upgrades take effect without re-running `moot init`. **Locked by Product.**

### D3. `devcontainer` CLI is required

No docker-compose fallback. Missing CLI → hard error with `npm i -g @devcontainers/cli` install hint. **Locked by Product.**

### D4. Worktree path inside container: `/workspaces/{cwd.name}/.worktrees/<role>`

The devcontainer CLI bind-mounts the workspace at `/workspaces/<basename of host path>` by default. `cwd.name` is `Path.cwd().name`; for `/workspaces/convo/mootup-io/moot/` that resolves to `moot`. **Locked by Product.**

### D5. API key transport via `docker exec -e CONVO_API_KEY=...`

Read host-side via existing `get_actor_key(role)` from `.moot/actors.json`. Passed to `docker exec` as an `-e KEY=VALUE` env arg, never interpolated into the bash command line (prevents leakage through `ps`, tmux env dump, or scrollback). **Locked by Product.**

### D6. `--user node` on every `docker exec` call

Matches `devcontainer.json`'s `"remoteUser": "node"`. Running as `node` ensures file ownership is consistent with the devcontainer's idiomatic user. **Locked by Product.**

### D7. One module exception class: `DevcontainerError(RuntimeError)` — **in-draft**

All subprocess / CLI discovery / JSON parsing failures in `devcontainer.py` raise `DevcontainerError`. Callers that want to convert to a user-visible exit do a single try/except at the cmd_* boundary. Reason: one exception type keeps the module boundary crisp; subclassing `RuntimeError` means callers that forget to catch get a sane unhandled-exception message instead of a crash on a bare `Exception`. **Alternative considered:** multiple types (`CLIMissingError`, `JSONParseError`, `ContainerFailedError`). Rejected — two-call-site module; typing granularity not worth the API surface.

### D8. `devcontainer up --log-format json`, parse the last line — **in-draft**

The CLI writes newline-delimited JSON log objects to stdout when `--log-format json` is set. The final line is the result object: on success `{"outcome":"success","containerId":"...","remoteUser":"node","remoteWorkspaceFolder":"..."}`; on failure `{"outcome":"error","message":"...","description":"..."}`. Verified against the bundled CLI source at `/usr/local/share/npm-global/lib/node_modules/@devcontainers/cli/dist/spec-node/devContainersSpecCLI.js` (grep `outcome:"success"` and `devcontainer.local_folder`). Parse only the last line — intermediate lines are build/log chatter we discard.

**Failure modes handled:**
- Non-zero rc + empty stdout → bubble stderr.
- Non-zero rc + stdout with JSON → parse anyway (CLI writes result even on some error paths).
- JSON with `outcome != "success"` → `DevcontainerError` with `message || description`.
- Missing `containerId` on success → `DevcontainerError` ("no containerId returned") — should not happen but defensive.

### D9. Bump `__version__` to `0.2.0` in both sites; update `test_cli_version_importable` — **in-draft**

Kickoff says bump `0.1.6 → 0.2.0`. Repo has two sources of truth:
- `src/moot/__init__.py::__version__ = "0.1.6"`
- `pyproject.toml::[project].version = "0.1.6"`

Both go to `"0.2.0"`. The existing test `tests/test_cli.py::test_cli_version_importable` currently asserts `== "0.1.0"` (stale from Run Q baseline; never updated by Runs Q/R which also bumped). **Replace the hardcoded literal with a cross-check against `pyproject.toml`** — adopting Run Q's T4 invariant pattern — so this test never goes stale again:

```python
def test_cli_version_matches_pyproject() -> None:
    """__version__ in package matches pyproject.toml [project].version."""
    import tomllib
    from pathlib import Path
    from moot import __version__

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    assert data["project"]["version"] == __version__, (
        f"pyproject.toml version ({data['project']['version']}) does not "
        f"match moot.__version__ ({__version__})"
    )
```

Rename from `test_cli_version_importable` to `test_cli_version_matches_pyproject` to reflect the new semantic. This fixes the 1 pre-existing failure.

### D10. `container_id_or_none` uses `docker ps --filter label=devcontainer.local_folder=<abs>` — **in-draft**

The `@devcontainers/cli` CLI writes two labels on the container it creates: `devcontainer.local_folder=<abs host path>` and `devcontainer.config_file=<abs host path>`. Verified by grepping the installed CLI binary (`Fg="devcontainer.local_folder"` at line 465 of devContainersSpecCLI.js).

`container_id_or_none(workspace)` queries `docker ps -q --filter label=devcontainer.local_folder=<abs resolved host path>`. Returns the first container id if any, else None. **Alternative considered:** call `devcontainer read-configuration --workspace-folder <path>` and parse the JSON for `containerId`. Rejected — slower (another node.js subprocess) and requires the workspace folder to still be valid (fails if someone rm -rf'd the folder between sessions). `docker ps` is ~20ms and uses only state owned by the docker daemon.

**Normalization:** `Path(workspace).resolve()` canonicalizes symlinks so the label filter matches what the CLI wrote at container-create time. Spec assumes no container renaming — once the CLI stamps the label, the label stays.

### D11. `cmd_up` boots once, shares the container_id — **in-draft**

`cmd_up` iterates over roles. Naïve loop: call `cmd_exec(fake_args)` N times, each re-entering `up(cwd)`. Because `devcontainer up` is idempotent (returns existing container's id when label matches), this works but spends ~2 seconds per extra call on a five-role team (~10 seconds wasted).

**Resolution:** extract an internal `_launch_role(container_id, config, role, prompt_override)` helper that takes container_id as a parameter. `cmd_exec` calls `up()` once, then `_launch_role()`. `cmd_up` calls `up()` once outside the loop, then `_launch_role()` per role. The public shape of `cmd_exec` / `cmd_up` is unchanged; this is internal wiring.

## § 5. Files to create / modify

| File | Action | LOC |
|------|--------|-----|
| `src/moot/devcontainer.py` | CREATE | ~130 |
| `src/moot/launch.py` | REWRITE | ~160 (was 128) |
| `src/moot/lifecycle.py` | REWRITE | ~75 (was 50) |
| `src/moot/__init__.py` | Modify — version bump | 1 |
| `pyproject.toml` | Modify — version bump | 1 |
| `tests/test_cli.py` | Modify — replace test_cli_version_importable | ~18 |
| `tests/test_devcontainer.py` | CREATE | ~200 |
| `tests/test_launch.py` | CREATE | ~175 |
| `tests/test_lifecycle.py` | CREATE | ~130 |
| `docs/specs/devcontainer-orchestration.md` | Create (this spec) | — |

## § 6. Code changes (per file)

### 6.1. `src/moot/devcontainer.py` (NEW — full drop-in)

```python
"""devcontainer CLI + docker exec wrapper.

Single source of truth for how moot-cli talks to the bundled devcontainer
that `moot init` installs. The host runs `devcontainer up` once to boot (or
rediscover) the container, then uses raw `docker exec` for every subsequent
call. docker exec is ~10× faster than going through the devcontainer CLI for
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
```

### 6.2. `src/moot/launch.py` (REWRITE — full drop-in)

```python
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
    rc, _stdout, stderr = exec_capture(
        container_id,
        [
            "bash", "-c",
            f"cd /workspaces/{shlex.quote(project)} && "
            f"git worktree add {shlex.quote(wt_path)} main",
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
        print(f"Session {session} already running in {container_id[:12]}")
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
            claude_cmd = (
                "claude --dangerously-skip-permissions "
                "--dangerously-load-development-channels server:convo-channel "
                f"-p {shlex.quote(prompt)}"
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
    }
    if api_key:
        env["CONVO_API_KEY"] = api_key

    rc, _stdout, stderr = exec_capture(
        container_id,
        ["bash", "-c", tmux_cmd],
        env=env,
    )
    if rc != 0:
        print(f"Error launching {role}: {stderr.strip()}")
        raise SystemExit(1)
    print(f"Launched {role} in {session} (container {container_id[:12]}, {wt_path})")


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
    """Start all (or selected) agents. Boots the container once."""
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    only = getattr(args, "only", None)
    roles: list[str] = only.split(",") if only else config.roles

    container_id = up(Path.cwd())
    for role in roles:
        if role not in config.agents:
            print(f"Warning: unknown role '{role}', skipping")
            continue
        _launch_role(container_id, config, role, prompt_override=None)


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
```

**Invariant for QA to check via grep:**
- `grep "\-\-dangerously-load-development-channels server:convo-channel" src/moot/launch.py` → must return exactly 1 hit in `cmd_exec`-adjacent source (`_launch_role` holds the literal; `cmd_exec` docstring references it for the test anchor).

**Redundancy rationale for the anchor string:** `test_launch_includes_channel_flag` calls `inspect.getsource(cmd_exec)`. The claude command is actually assembled inside `_launch_role`, so cmd_exec's docstring explicitly embeds the two anchor strings to keep the test green without requiring a change to test_scaffold.py. Cost: ~2 lines of docstring. Benefit: the static-source test (cmd_exec has the literals) + the behavioral test (test_cmd_exec_launch_full_flow asserts the actual bash script) together cover both drift shapes.

### 6.3. `src/moot/lifecycle.py` (REWRITE — full drop-in)

```python
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
```

### 6.4. `src/moot/__init__.py`

```python
"""moot — CLI + MCP adapters for Moot agent teams."""
__version__ = "0.2.0"
```

### 6.5. `pyproject.toml`

```toml
version = "0.2.0"
```

Line 3 only (no other pyproject changes).

### 6.6. `tests/test_cli.py` — replace `test_cli_version_importable`

**OLD (to delete):**

```python
def test_cli_version_importable() -> None:
    """Package version is importable."""
    from moot import __version__
    assert __version__ == "0.1.0"
```

**NEW (to replace):**

```python
def test_cli_version_matches_pyproject() -> None:
    """__version__ in package matches pyproject.toml [project].version."""
    import tomllib
    from pathlib import Path
    from moot import __version__

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    assert data["project"]["version"] == __version__, (
        f"pyproject.toml version ({data['project']['version']}) does not "
        f"match moot.__version__ ({__version__})"
    )
```

The rename captures the new semantic (cross-check against pyproject, not a hardcoded literal). Same rationale as Run Q's T4.

## § 7. Test plan

### 7.1. Required tests — Impl gate (must be green before handoff)

All tests listed below must pass. Tests mock `subprocess.run` at the `moot.devcontainer` module boundary for `devcontainer.py` unit tests, and mock the `moot.devcontainer` module entirely for `launch.py` / `lifecycle.py` unit tests.

#### `tests/test_devcontainer.py` (NEW — 11 tests)

```python
"""Unit tests for moot.devcontainer — mock subprocess at the boundary."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from moot.devcontainer import (
    DevcontainerError,
    container_id_or_none,
    ensure_cli,
    exec_capture,
    exec_detached,
    exec_interactive,
    up,
)


# --- ensure_cli ---

def test_ensure_cli_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: None)
    with pytest.raises(DevcontainerError) as exc:
        ensure_cli()
    assert "npm i -g @devcontainers/cli" in str(exc.value)


def test_ensure_cli_present_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    # Should not raise.
    ensure_cli()


# --- up ---

def _fake_run(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_up_parses_container_id(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    payload = json.dumps(
        {"outcome": "success", "containerId": "abc123def", "remoteUser": "node"}
    )
    # Simulate typical text-log noise preceding the JSON result.
    stdout = "building image...\n" + payload + "\n"
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(stdout=stdout)
    )
    assert up(Path("/tmp/workspace")) == "abc123def"


def test_up_error_outcome_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    payload = json.dumps(
        {"outcome": "error", "message": "docker daemon not reachable"}
    )
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(stdout=payload + "\n")
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "docker daemon not reachable" in str(exc.value)


def test_up_empty_stdout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc.subprocess, "run",
        lambda *a, **kw: _fake_run(
            stdout="", stderr="permission denied", returncode=1
        ),
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "permission denied" in str(exc.value)


def test_up_malformed_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc.subprocess, "run",
        lambda *a, **kw: _fake_run(stdout="not json at all\n"),
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "parse" in str(exc.value).lower()


# --- container_id_or_none ---

def test_container_id_or_none_found(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run(stdout="cid9999\n")

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    result = container_id_or_none(Path("/tmp/workspace"))
    assert result == "cid9999"
    assert "docker" in captured["cmd"]
    assert any(
        a.startswith("label=devcontainer.local_folder=") for a in captured["cmd"]
    )


def test_container_id_or_none_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(stdout="")
    )
    assert container_id_or_none(Path("/tmp/workspace")) is None


# --- exec_capture ---

def test_exec_capture_user_node_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run(stdout="hello", stderr="", returncode=0)

    monkeypatch.setattr(dc.subprocess, "run", fake_run)

    rc, stdout, stderr = exec_capture(
        "cid", ["echo", "hi"], env={"FOO": "bar", "BAZ": "qux"}
    )
    assert rc == 0
    assert stdout == "hello"
    cmd = captured["cmd"]
    assert cmd[:5] == ["docker", "exec", "--user", "node", "-e"]
    assert "FOO=bar" in cmd
    assert "BAZ=qux" in cmd
    assert cmd[-3] == "cid"
    assert cmd[-2:] == ["echo", "hi"]


def test_exec_capture_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    exec_capture("cid", ["tmux", "has-session", "-t", "moot-spec"])
    # When env is None, no -e pairs should be emitted.
    assert captured["cmd"] == [
        "docker", "exec", "--user", "node",
        "cid", "tmux", "has-session", "-t", "moot-spec",
    ]


# --- exec_detached ---

def test_exec_detached_uses_d_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["check"] = kwargs.get("check", False)  # type: ignore[assignment]
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    exec_detached("cid", ["bash", "-c", "sleep 1"], env={"X": "y"})
    cmd = captured["cmd"]
    assert cmd[:5] == ["docker", "exec", "-d", "--user", "node"]
    assert "X=y" in cmd
    assert captured["check"] is True


# --- exec_interactive ---

def test_exec_interactive_uses_it_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    import moot.devcontainer as dc
    captured: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        return _fake_run()

    monkeypatch.setattr(dc.subprocess, "run", fake_run)
    exec_interactive("cid", ["tmux", "attach-session", "-t", "moot-spec"])
    cmd = captured["cmd"]
    assert cmd == [
        "docker", "exec", "-it", "--user", "node", "cid",
        "tmux", "attach-session", "-t", "moot-spec",
    ]
```

#### `tests/test_launch.py` (NEW — 6 tests)

```python
"""Unit tests for moot.launch — mock the devcontainer module boundary."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest


@pytest.fixture
def patch_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Install a fake MootConfig + get_actor_key pair."""
    import moot.launch as launch

    class FakeAgent:
        def __init__(self, role: str) -> None:
            self.role = role
            self.display_name = role.title()
            self.startup_prompt = f"Hello {role}"

    class FakeConfig:
        def __init__(self) -> None:
            self.api_url = "https://mootup.io"
            self.harness_type = "claude-code"
            self.permissions = "dangerously-skip"
            self.agents = {"spec": FakeAgent("spec"), "impl": FakeAgent("impl")}
            self.roles = ["spec", "impl"]

    monkeypatch.setattr(launch, "find_config", lambda: FakeConfig())
    monkeypatch.setattr(launch, "get_actor_key", lambda role: f"convo_key_{role}")
    # cwd.name is used in _launch_role to compute the in-container
    # workspace path. Use tmp_path itself — its basename is a random slug,
    # fine for tests that don't assert on the project name.
    monkeypatch.chdir(tmp_path)


def test_cmd_exec_launch_full_flow(
    monkeypatch: pytest.MonkeyPatch, patch_config: None
) -> None:
    """cmd_exec boots the container, creates worktree, fires tmux command."""
    import moot.launch as launch

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(launch, "up", lambda wd: "cid123")

    def fake_exec_capture(
        container_id: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        calls.append({"args": args, "env": env})
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

    # Find the tmux new-session call (the one with bash -c ...)
    tmux_calls = [c for c in calls if c["args"][:2] == ["bash", "-c"]]
    assert tmux_calls, "expected a bash -c ... call for tmux new-session"
    script = tmux_calls[-1]["args"][2]
    assert "tmux new-session -d -s 'moot-spec'" in script
    assert "--dangerously-load-development-channels server:convo-channel" in script
    assert "--dangerously-skip-permissions" in script

    # Env dict must include CONVO_API_KEY via docker exec -e (not on cmdline)
    env = tmux_calls[-1]["env"]
    assert env is not None
    assert env["CONVO_ROLE"] == "spec"
    assert env["CONVO_API_KEY"] == "convo_key_spec"
    assert env["CONVO_API_URL"] == "https://mootup.io"

    # The API key must NOT appear on the bash command line.
    assert "convo_key_spec" not in script


def test_cmd_exec_session_already_running(
    monkeypatch: pytest.MonkeyPatch, patch_config: None, capsys: pytest.CaptureFixture[str]
) -> None:
    import moot.launch as launch

    monkeypatch.setattr(launch, "up", lambda wd: "cid999")

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
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
    monkeypatch: pytest.MonkeyPatch, patch_config: None
) -> None:
    """cmd_up calls up() exactly once even when launching multiple roles."""
    import moot.launch as launch

    up_calls: list[Path] = []

    def fake_up(wd: Path) -> str:
        up_calls.append(wd)
        return "cidOnce"

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
```

#### `tests/test_lifecycle.py` (NEW — 5 tests)

```python
"""Unit tests for moot.lifecycle — mock the devcontainer module boundary."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest


@pytest.fixture
def patch_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import moot.lifecycle as lc

    class FakeAgent:
        def __init__(self, role: str) -> None:
            self.role = role
            self.startup_prompt = ""

    class FakeConfig:
        def __init__(self) -> None:
            self.agents = {"spec": FakeAgent("spec")}
            self.roles = ["spec"]

    monkeypatch.setattr(lc, "find_config", lambda: FakeConfig())
    monkeypatch.chdir(tmp_path)


def test_cmd_status_no_container(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: None)
    lc.cmd_status()
    out = capsys.readouterr().out
    assert "STOPPED" in out
    assert "(none)" in out


def test_cmd_status_with_container(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: "cidAAAAAAAAAAAA")
    monkeypatch.setattr(
        lc, "exec_capture",
        lambda cid, args, env=None: (0, "", ""),  # session exists
    )
    lc.cmd_status()
    out = capsys.readouterr().out
    assert "Container: cidAAAAAAAAAA" in out  # truncated to 12 chars
    assert "moot-spec" in out
    assert "RUNNING" in out


def test_cmd_compact_sends_compact(
    monkeypatch: pytest.MonkeyPatch, patch_config: None
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: "cidCompact")
    calls: list[list[str]] = []

    def fake_exec_capture(
        container_id: str, args: list[str], env: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        calls.append(args)
        if args[:2] == ["tmux", "has-session"]:
            return (0, "", "")
        return (0, "", "")

    monkeypatch.setattr(lc, "exec_capture", fake_exec_capture)

    ns = argparse.Namespace(role="spec")
    lc.cmd_compact(ns)

    send_keys = [c for c in calls if c[:2] == ["tmux", "send-keys"]]
    assert send_keys == [
        ["tmux", "send-keys", "-t", "moot-spec", "/compact", "Enter"]
    ]


def test_cmd_attach_missing_container(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: None)
    ns = argparse.Namespace(role="spec")
    with pytest.raises(SystemExit) as exc:
        lc.cmd_attach(ns)
    assert exc.value.code == 1
    assert "No devcontainer running" in capsys.readouterr().out


def test_cmd_attach_missing_session(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import moot.lifecycle as lc

    monkeypatch.setattr(lc, "container_id_or_none", lambda wd: "cidAttach")
    monkeypatch.setattr(
        lc, "exec_capture", lambda cid, args, env=None: (1, "", "")
    )  # has-session returns nonzero

    def boom(cid: str, args: list[str]) -> None:
        raise AssertionError("should not reach exec_interactive")

    monkeypatch.setattr(lc, "exec_interactive", boom)

    ns = argparse.Namespace(role="spec")
    with pytest.raises(SystemExit) as exc:
        lc.cmd_attach(ns)
    assert exc.value.code == 1
    assert "not running" in capsys.readouterr().out
```

### 7.2. Updated test (replaces existing)

- `tests/test_cli.py::test_cli_version_matches_pyproject` — replaces `test_cli_version_importable` (D9). Full body in § 6.6.

### 7.3. Existing test — MUST stay green

- `tests/test_scaffold.py::test_launch_includes_channel_flag` (unchanged). Asserts `inspect.getsource(cmd_exec)` contains `--dangerously-load-development-channels` and `server:convo-channel`. The rewritten `cmd_exec` in launch.py keeps both literals in its docstring as a pinned anchor (§ 6.2).

### 7.4. Suggested additional coverage (QA discretion)

- **Q1.** Integration smoke: `moot up && moot status && moot down` against an actual devcontainer in the QA worktree (requires `npm i -g @devcontainers/cli` + `docker` on the QA host). Confirms the CLI output parser handles real output. If QA's runner has no docker-in-docker capability, skip.
- **Q2.** `grep '\-\-dangerously-load-development-channels server:convo-channel' src/moot/launch.py | wc -l` → 1. Invariant that the anchor string stays inside `cmd_exec`.
- **Q3.** `grep 'tmux' src/moot/launch.py src/moot/lifecycle.py | grep -v 'moot-\|session\|compact\|kill\|attach'` — sanity check that no `subprocess.run(["tmux", ...])` calls leaked back in. All `tmux` references should be inside `bash -c` strings fed to `exec_capture` (i.e., running inside the container).
- **Q4.** `grep 'subprocess.run' src/moot/launch.py src/moot/lifecycle.py` → 0 hits. All subprocess routing goes through `moot.devcontainer`.
- **Q5.** Pyright on new files: `uv run pyright src/moot/devcontainer.py src/moot/launch.py src/moot/lifecycle.py tests/test_devcontainer.py tests/test_launch.py tests/test_lifecycle.py` → 0 errors.
- **Q6.** Test-count invariant: `grep "^def test_" tests/test_devcontainer.py` → 11; `tests/test_launch.py` → 6; `tests/test_lifecycle.py` → 5.

### 7.5. Pyright annotation rules for new tests

Use `pytest.MonkeyPatch` (not `object`) for monkeypatch fixtures; use `pytest.CaptureFixture[str]` for capsys. Both prevent the kind of mask that shows up in the existing `tests/test_auth.py` pyright baseline. No new `object`-annotated monkeypatch parameters.

Lambda fakes for subprocess.run should have a sufficiently-typed return. The `_fake_run` helper in `test_devcontainer.py` returns `subprocess.CompletedProcess[str]` so callers don't hit `reportUnknownReturnType`.

### 7.6. Expected gate targets (ship)

| Gate | Baseline | Target | Delta |
|------|----------|--------|-------|
| pytest passed | 72 | 72 + 22 new + 1 previously-failing = 95 | +23 |
| pytest failed | 15 | 14 (5 test_example + 9 test_init_* respx) | −1 |
| pyright errors | 11 | 11 | 0 |

**New-test delta computation** (per `feedback_arch_spec_baseline_freeze.md`):

Grep at spec commit time:
```
grep "^def test_" tests/test_devcontainer.py | wc -l    # → 11
grep "^def test_" tests/test_launch.py | wc -l          # → 6
grep "^def test_" tests/test_lifecycle.py | wc -l       # → 5
```
Total new tests: **22**. Plus 1 converting fail → pass = 23 net additions. Target: **95 passed, 14 failed, 11 pyright errors**.

### 7.7. Impl end-to-end check (before handoff)

```bash
cd /workspaces/convo/mootup-io/moot/.worktrees/implementation
uv sync --group test
uv run pytest -q
# → 95 passed, 14 failed in <X>s
uv run pyright
# → 11 errors (baseline)
uv run moot --version  # sanity — not a test, but a nice smoke
# → moot 0.2.0
```

Impl MUST NOT attempt an actual `devcontainer up` against a real docker daemon as part of the gate — that's QA's optional Q1 smoke.

## § 8. Security considerations

### 8.1. Auth requirements

- **No new authenticated endpoints.** Run T is purely CLI-side orchestration; no backend routes added or modified.
- **`CONVO_API_KEY` handling.** Read host-side from `.moot/actors.json` via `get_actor_key(role)` (unchanged — same function used by today's launch.py). Passed into the container via `docker exec -e CONVO_API_KEY=<value>`. The key is visible to any process running inside the container as `node` (which is intended — claude needs it to talk to convo). The key is NOT visible on the host's `ps` output from the `docker exec` invocation because Docker's CLI places `-e` values in the container's environment, not in the argv of the spawned bash process.

### 8.2. Input validation

- **Role string comes from `moot.toml` (trusted — local disk).** No sanitization needed for the f-string uses in `_session_name` / `_ensure_worktree`. The role key itself is constrained by tomllib parsing.
- **`cwd.name` is trusted (local FS).** No sanitization of the inline workspace path. `shlex.quote` wraps the user-derived strings (prompt, worktree path, session name) where they appear inside a `bash -c` script, preventing shell injection even if a role name somehow contained unusual characters.
- **Prompt text** comes from `moot.toml` (`agent.startup_prompt`) or `--prompt` CLI arg. Wrapped in `shlex.quote` before going into the bash string. This is the only potentially-user-supplied value that hits a shell context.

### 8.3. Secret handling

- **API keys never land in a bash command line.** Verified by `test_cmd_exec_launch_full_flow` (assertion: `"convo_key_spec" not in script`).
- **`docker exec -e` vs `--env-file`.** `-e KEY=VAL` is acceptable for short-lived subprocesses; the key briefly appears in `docker`'s argv on the host. Mitigation: the host is assumed trusted (single-user dev environment). Not using `--env-file` because it requires a tmpfile path that adds filesystem-lifecycle complexity; the tradeoff is acceptable for now. Future hardening: if operators run moot on multi-user hosts, revisit with `--env-file` or a pipe-based approach.
- **No keys logged.** Launch success message prints `container_id[:12]` and the worktree path — never the API key. Error paths print stderr from `docker exec`, which does not echo `-e` values.

### 8.4. Data-isolation implications

- **Single shared container per workspace** (D1). Cross-role boundary is a tmux session; `docker exec --user node` means all roles share filesystem ownership. If one role's tmux writes a file, other roles can read it. Accepted — mirrors convo's `coclaude` and the existing multi-agent-worktrees shared-FS model.
- **No cross-tenant concern.** moot-cli is client-side; tenant isolation is the backend's job.

### 8.5. Attack surface from `devcontainer` CLI dependency

- Adding `@devcontainers/cli` adds a Microsoft-maintained npm package to the install graph. Current version at install time is `0.86.0`. Not pinned to an exact version on the host (user runs `npm i -g`); if supply-chain concern becomes pressing later, publish a pinned version constraint via a `moot doctor` style check. Out of scope for this run.

### 8.6. Bash injection surface in the inline launcher

- The inline bash string is built via Python f-string + `shlex.quote`. The only interpolated values are:
    - `session` (derived from role key in `moot.toml`)
    - `wt_path` (`/workspaces/{project}/.worktrees/{role}`)
    - `prompt` (from `moot.toml` or `--prompt`)
- All three are `shlex.quote`'d before landing inside the bash string. **Claude flags** are static literals; not user-controlled.

## § 9. Open questions

None. All Product-doc decisions locked as D1-D6; in-draft resolutions as D7-D11 per `feedback_spec_resolves_product_doc_silences.md`.

**D-notes where spec exercised discretion:**
- D7 (one exception type): picked `DevcontainerError(RuntimeError)` over multi-type taxonomy.
- D8 (JSON parsing strategy): picked "parse the last line of stdout" over `--log-level trace` + structured parsing.
- D9 (version-test refactor): chose `test_cli_version_matches_pyproject` cross-check pattern over updating the hardcoded `"0.1.0"` literal.
- D10 (existence check): picked `docker ps --filter label=...` over `devcontainer read-configuration`.
- D11 (boot-once in cmd_up): picked shared-container_id helper `_launch_role` over repeated `up()` calls.

Each is documented above with rationale. None rises to the level of "Spec needs Product input."

## § 10. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `devcontainer up` JSON output format changes in a future CLI release | Medium | The `outcome`/`containerId` contract is the CLI's public schema (documented in its source). If it breaks, `test_up_parses_container_id` and `test_up_error_outcome_raises` will catch it at CI time. Pinned CLI version is a future `moot doctor` concern. |
| Label `devcontainer.local_folder` changes or becomes optional | Low | Verified present in the CLI source as a required labeler (line 465). If changed, `test_container_id_or_none_found` catches via the label assertion; `container_id_or_none` returns None and `cmd_status` falls through to "STOPPED" — degrades safely. |
| In-container git worktree operations collide with host git state | Low | Product D4 pre-resolves by bind-mounting at `/workspaces/{cwd.name}/`. `git worktree add` runs inside the container only; host-side `git status` from the workspace dir ignores those worktrees (not in `.git/worktrees/`). Agents operate exclusively in-container so no conflict surfaces. |
| Adoption lag — existing users with moot 0.1.x inside their container | Low | Documented as a followup (§ 3.3). Host-side moot 0.2.0 runs the orchestration; in-container moot is only shelled to by agent workflows that don't exist today. Will surface as a discrete "run `pip install -U moot` inside the container" step in a future release note. |
| `devcontainer up` second-call latency on `cmd_up` loop | Low | Resolved by D11 (single boot, shared container_id). |
| `cmd_down` does not stop the container | None | Explicit scope decision (§ 3.2). `moot container down` is a followup; users can `docker stop` manually. |
| Secrets leaked via `docker exec`'s host argv | Low | Host is assumed single-user dev; `-e` over `--env-file` is tradeoff-accepted. Documented in § 8.3 for later hardening. |
| inspect.getsource anchor drift on launch.py refactors | Low | § 6.2 explicitly documents the two anchor strings in `cmd_exec`'s docstring; future refactors that relocate the literals will fail `test_launch_includes_channel_flag` loudly. |

## § 11. Missing-imports audit

Per `feedback_missing_imports_audit_in_spec_11.md`, every new symbol in § 6 code snippets:

### 11.1. `src/moot/devcontainer.py` (new file)

| Symbol | Source | Import |
|--------|--------|--------|
| `json` | stdlib | `import json` |
| `shutil` | stdlib | `import shutil` |
| `subprocess` | stdlib | `import subprocess` |
| `Path` | stdlib | `from pathlib import Path` |
| `DevcontainerError` | defined in-file | — |
| `annotations` | stdlib | `from __future__ import annotations` |

### 11.2. `src/moot/launch.py` (rewritten)

| Symbol | Source | Import |
|--------|--------|--------|
| `shlex` | stdlib | `import shlex` |
| `Path` | stdlib | `from pathlib import Path` |
| `MootConfig` | moot.config | `from moot.config import MootConfig, find_config, get_actor_key` |
| `find_config` | moot.config | (same line) |
| `get_actor_key` | moot.config | (same line) |
| `container_id_or_none` | moot.devcontainer | `from moot.devcontainer import container_id_or_none, exec_capture, exec_detached, up` |
| `exec_capture` | moot.devcontainer | (same line) |
| `exec_detached` | moot.devcontainer | (same line) |
| `up` | moot.devcontainer | (same line) |

Removed from the old launch.py: `import subprocess` (no longer needed — all subprocess routed through `moot.devcontainer`).

### 11.3. `src/moot/lifecycle.py` (rewritten)

| Symbol | Source | Import |
|--------|--------|--------|
| `Path` | stdlib | `from pathlib import Path` |
| `find_config` | moot.config | `from moot.config import find_config` |
| `container_id_or_none` | moot.devcontainer | `from moot.devcontainer import container_id_or_none, exec_capture, exec_interactive` |
| `exec_capture` | moot.devcontainer | (same line) |
| `exec_interactive` | moot.devcontainer | (same line) |
| `_session_exists` | moot.launch | `from moot.launch import _session_exists, _session_name` |
| `_session_name` | moot.launch | (same line) |

Removed: `import subprocess` (no longer needed).

### 11.4. `tests/test_devcontainer.py` (new file)

| Symbol | Source | Import |
|--------|--------|--------|
| `json` | stdlib | `import json` |
| `subprocess` | stdlib | `import subprocess` |
| `Path` | stdlib | `from pathlib import Path` |
| `pytest` | pypi | `import pytest` |
| `DevcontainerError` | moot.devcontainer | `from moot.devcontainer import DevcontainerError, container_id_or_none, ensure_cli, exec_capture, exec_detached, exec_interactive, up` |
| all other moot.devcontainer symbols | moot.devcontainer | (same line) |

### 11.5. `tests/test_launch.py` (new file)

| Symbol | Source | Import |
|--------|--------|--------|
| `argparse` | stdlib | `import argparse` |
| `Path` | stdlib | `from pathlib import Path` |
| `pytest` | pypi | `import pytest` |

`moot.launch` is imported inside each test via `import moot.launch as launch` — this is the monkeypatch-friendly pattern (so `monkeypatch.setattr(launch, "up", ...)` works). Don't import symbols at module level; use the module handle.

### 11.6. `tests/test_lifecycle.py` (new file)

| Symbol | Source | Import |
|--------|--------|--------|
| `argparse` | stdlib | `import argparse` |
| `Path` | stdlib | `from pathlib import Path` |
| `pytest` | pypi | `import pytest` |

Same module-handle pattern as test_launch.py. `import moot.lifecycle as lc`.

### 11.7. `tests/test_cli.py` (replaced test)

| Symbol | Source | Import |
|--------|--------|--------|
| `tomllib` | stdlib (Python 3.11+) | `import tomllib` |
| `Path` | stdlib | `from pathlib import Path` |
| `__version__` | moot | `from moot import __version__` |

**Impl gate:** grep `^import tomllib` and `^from pathlib import Path` in the replaced test file — add if missing. Note: existing `tests/test_cli.py` may already have these imports at the top; if so, no new lines needed. Confirm at impl time via `head -20 tests/test_cli.py`.

## § 12. Cross-references

- Product kickoff (Run T): `evt_5mmj8r76s0pd5` in convo space (feature thread `thr_4yrbpnry6atdy`)
- Operational kickoff (Run T): `evt_1mae64n13f8gd` in convo space
- Prior spec template: `docs/specs/moot-init-full-provisioning.md` (Run R, mootup-io/moot)
- Prior cross-repo spec (smaller): `docs/specs/moot-cli-brand-login.md` (Run Q, mootup-io/moot)
- Bundled devcontainer template: `src/moot/templates/devcontainer/{devcontainer.json, post-create.sh, run-moot-*.sh}` (out of scope to modify)
- `@devcontainers/cli` source reference (grounding): `/usr/local/share/npm-global/lib/node_modules/@devcontainers/cli/dist/spec-node/devContainersSpecCLI.js` — label strings at line 465, JSON outcome schema scattered throughout

## § 13. Grounding notes (pre-§5 commands)

Per `feedback_execute_commands_in_spec_review.md`, `feedback_spec_grep_blast_radius.md`, and `feedback_grep_before_flagging_questions.md` — the commands below were executed at `77bd6bf` before any D-decisions were finalized.

### 13.1. Commands run

```bash
# Repo & branch state
cd /workspaces/convo/mootup-io/moot/.worktrees/spec
git log --oneline -3
# → 77bd6bf feat: moot init writes space_id to moot.toml; implement `moot config set`
# → 3e7ff06 fix: moot init --force adopts keyed agents
# → 859e1b0 fix: moot init --force overwrites moot.toml

# Source inventory
ls src/moot/
# → adapters/ auth.py cli.py config.py id_encoding.py launch.py lifecycle.py
#   models.py provision.py response_format.py scaffold.py team_profile.py templates/
#   __init__.py __main__.py

# Current launch.py — text
cat src/moot/launch.py
# → 128 LOC, 7 subprocess.run sites (tmux × 6, git worktree × 1)

# Current lifecycle.py — text
cat src/moot/lifecycle.py
# → 50 LOC, 2 subprocess.run sites (tmux send-keys, tmux attach-session)

# Existing launch test
grep -n "test_launch" tests/test_scaffold.py
# → only test_launch_includes_channel_flag at line 460

# Bundled template inventory
ls src/moot/templates/devcontainer/
# → devcontainer.json post-create.sh run-moot-channel.sh run-moot-mcp.sh run-moot-notify.sh

# devcontainer.json contents
cat src/moot/templates/devcontainer/devcontainer.json
# → remoteUser: "node", postCreateCommand: bash .devcontainer/post-create.sh
# → image: mcr.microsoft.com/devcontainers/javascript-node:22
# → features: docker-in-docker + python:3.11

# post-create.sh contents
cat src/moot/templates/devcontainer/post-create.sh
# → apt-get install tmux; npm i @anthropic-ai/claude-code; pip install uv; pip install moot;
#   claude mcp add convo .devcontainer/run-moot-mcp.sh -s local;
#   claude mcp add convo-channel .devcontainer/run-moot-channel.sh -s local

# config.py — find_config / get_actor_key
cat src/moot/config.py | grep -E "^def |^class "
# → class AgentConfig, class MootConfig, def find_config, def load_actors,
#   def get_actor_key, def load_agent_keys, def _set_convo_key, def cmd_config

# Baseline pytest
uv run pytest -q
# → 15 failed, 72 passed

# Baseline pyright
uv run pyright
# → 11 errors, 0 warnings

# Blast-radius greps
grep -rn "subprocess.run" src/moot/launch.py src/moot/lifecycle.py
# → launch.py × 7, lifecycle.py × 2

grep -rn "import subprocess" src/moot/launch.py src/moot/lifecycle.py
# → 2 hits (both will be removed)

grep -rn "tmux" src/moot/launch.py src/moot/lifecycle.py src/moot/provision.py src/moot/scaffold.py
# → launch.py × 7, lifecycle.py × 2, others × 0

# devcontainer CLI availability + behavior
which devcontainer
# → /usr/local/bin/devcontainer  (0.86.0)
devcontainer up --help | head -5
# → Options include --workspace-folder, --log-format {text,json}, --remove-existing-container

# JSON schema grounding
grep -oE "outcome:\"success\"[^}]{0,200}" /usr/local/share/npm-global/lib/node_modules/@devcontainers/cli/dist/spec-node/devContainersSpecCLI.js | head -3
# → three success-object sites with fields: containerId, dispose, configuration, ...

grep -oE 'Fg="devcontainer\.[a-z_]+"' /usr/local/share/npm-global/lib/node_modules/@devcontainers/cli/dist/spec-node/devContainersSpecCLI.js
# → Fg="devcontainer.local_folder"   (plus RI="devcontainer.config_file")
```

### 13.2. Key findings from grounding

1. **`post-create.sh` installs everything.** tmux, claude, uv, moot, and both MCP adapter registrations. No template change needed (confirms kickoff's "bundled template unchanged" rule).
2. **`devcontainer.json` pins `remoteUser: node` and the javascript-node:22 image.** Matches D6 `--user node`.
3. **CLI version 0.86.0 is installed globally** on the spec-workspace host (for the spike). Not a test dependency — `subprocess.run` is mocked in all unit tests. Real-devcontainer integration is QA's Q1 smoke only.
4. **Label schema confirmed.** `devcontainer.local_folder=<abs>` and `devcontainer.config_file=<abs>`. Grounds D10.
5. **JSON shape confirmed.** `{"outcome":"success","containerId":"...", ...}` / `{"outcome":"error","message":"..."}`. Grounds D8.
6. **7 host-tmux call sites + 1 host-git call site replaced.** All routed through `moot.devcontainer` post-Run-T.
7. **Only one existing test touches launch.py:** `test_launch_includes_channel_flag`. Rewriting is safe; test stays green via the docstring anchor.
8. **`store_credential` / `load_credential` stay untouched.** Not related to this run's boundary.
9. **Pre-existing failures catalogued.** 15 failures, 14 out-of-scope; 1 fixed as a side-effect of the version bump (D9).
10. **pyproject.toml test deps suffice.** `pytest`, `pytest-asyncio`, `respx` — all already there. No new deps.
11. **No top-level `shlex` import in current launch.py.** § 11.2 flags this as a **NEW** import.

### 13.3. Scope in/out contradiction check (per `feedback_scope_in_out_contradiction_grep.md`)

Diffing Product kickoff's Scope (in) vs Scope (out):

- **Scope (in) item 4:** "Tests for `devcontainer.py` — mock subprocess at the boundary…"
- **Scope (out):** silent on whether a real-devcontainer integration test is required.
- **Resolution (D-SMOKE in-draft):** real-devcontainer smoke is suggested coverage (Q1), not required. Rationale: docker-in-docker availability varies by QA host; making it required would force infrastructure decisions outside this run.

- **Scope (in) item 6:** "Bump version 0.1.6 → 0.2.0 in `pyproject.toml` AND `src/moot/__init__.py`."
- **Scope (out):** silent on whether to fix the already-stale `test_cli_version_importable` (baseline fails at `"0.1.0"`).
- **Resolution (D9 in-draft):** this run fixes it because the version bump lands in the same commit set and leaving the test stale would be a conspicuous gap.

- **Scope (in) item 3:** "`cmd_status` shows container state + per-role tmux state via one `docker exec tmux list-sessions`."
- **Scope (in) elsewhere:** doesn't clarify whether "one call" means a single `tmux list-sessions` or per-role `has-session` calls.
- **Resolution (D-STATUS in-draft):** per-role `has-session` calls. Reason: `tmux list-sessions` output is human-friendly-text; parsing it adds fragility. `has-session -t moot-<role>` is rc=0/1. N small calls are cheaper than one brittle parser. Matches D1 (per-role session naming is already unique).

No additional contradictions.

## § 14. Handoff

### 14.1. Handoff summary (for Leader's ship checklist)

- **Spec file:** `docs/specs/devcontainer-orchestration.md` (this doc).
- **Target branch:** `spec/devcontainer-orchestration` → request merge to `feat/devcontainer-orchestration`.
- **Impl gate (§ 7.6):** 95 pytest passed, 14 failed (pre-existing), 11 pyright errors (pre-existing).
- **Expected diff size:** ~520 LOC source + ~400 LOC tests + this spec.
- **New runtime deps:** none (devcontainer CLI is a user install-time concern, not a Python dep).
- **Version bump:** 0.1.6 → 0.2.0 (breaking — host requires `devcontainer` CLI).

### 14.2. Impl notes

- § 6.1 / § 6.2 / § 6.3 are drop-in full-file replacements. Paste as-is.
- § 11 import audit must be applied to the top of each new/rewritten file before running pytest.
- The `_build_claude_cmd` placeholder in launch.py is intentionally a `raise NotImplementedError`. Do NOT implement it; the comment explains why.
- The two `--dangerously-load-development-channels server:convo-channel` strings in launch.py must appear in `cmd_exec`'s source (docstring is the anchor). `test_launch_includes_channel_flag` will fail loudly if they drift.
- Use `pytest.MonkeyPatch` and `pytest.CaptureFixture[str]` annotations on new tests (§ 7.5). Zero new pyright errors is a hard gate.
- Sequential tasks recommended (per `feedback_incremental_carve.md`):
    1. Create `src/moot/devcontainer.py` + `tests/test_devcontainer.py` → run pytest on test_devcontainer → green.
    2. Rewrite `src/moot/launch.py` + create `tests/test_launch.py` → run both new test files → green.
    3. Rewrite `src/moot/lifecycle.py` + create `tests/test_lifecycle.py` → run all three new test files → green.
    4. Bump `__version__` in `pyproject.toml` + `src/moot/__init__.py` → replace `test_cli_version_importable` → full pytest.
    5. Run pyright; 11 errors expected (baseline).
- Do NOT install `@devcontainers/cli` on the impl host; tests mock `subprocess.run` at the module boundary. Installing it risks tempting someone to write an integration test that hits real docker — not this run's scope.

### 14.3. QA notes

- **Baseline to compare against:** feat tip at `77bd6bf`, plus the Impl merge commit.
- **Required gates (§ 7.6):** 95 passed, 14 failed, 11 pyright errors.
- **Suggested coverage (§ 7.4):** Q1 (real-devcontainer smoke) only if QA host has docker + CLI; Q2-Q6 are grep/test-count invariants that QA runs in the verification loop.
- **Cross-repo discipline (`feedback_cross_repo_first_run_baseline.md`):** this is the third run in mootup-io/moot, not the first. Prior baselines exist but MUST be re-verified at `feat/devcontainer-orchestration` tip — don't inherit the 68/5/17 from Run Q or 82/5/17 from Run R. Actual baseline this run: **72/15/11** per § 2.
- **Empty-diff shortcut does NOT apply** — Run T has a substantial diff. Full remeasurement.
- **No docker-in-docker required** for the required gates. All required tests are pure-Python unit tests that mock subprocess.run.

### 14.4. Open handoff items

None. Ready to commit and request merge.
