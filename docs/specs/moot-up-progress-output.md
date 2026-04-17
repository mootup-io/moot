# moot up — stream devcontainer build output, surface failures, signal launch progress

**Run U.** UX patch on top of Run T's devcontainer orchestration. Branch: `spec/moot-up-progress-output` → `feat/moot-up-progress-output`. Target version: `0.2.1`.

## 1. Summary

`moot up` and `moot exec` go quiet for 1–3 minutes during a first-time `devcontainer up`, and on failure produce an opaque `DevcontainerError: devcontainer up failed: Command failed: …` with the actual stderr dropped on the floor. Both symptoms trace to Run T's `devcontainer.up()` capturing the subprocess with `--log-format json` so it could parse the final-line result object.

This run switches `devcontainer.up()` to text streaming (no capture), prints a pre-build hint on cold boots, looks up the container id after-the-fact via the existing `container_id_or_none()` helper, and adds a per-role / closing-summary line set in `cmd_up`. Failures now show their real stderr inline and raise with just an exit code.

Diff is ~60–90 LOC of source plus ~4 new tests; ~10 existing tests update.

## 2. Baseline (mootup-io/moot `feat/moot-up-progress-output` @ `b684dd6`)

Measured in `/workspaces/convo/mootup-io/moot/.worktrees/spec` with `uv sync --group test` applied.

- `uv run pytest` → **96 passed, 14 failed** in 2.67s. All 14 failures are pre-existing per Run T § 2 and out of scope:
  - 5 × `tests/test_example.py::*` — worktree-path-dependent; failing with `FileNotFoundError` on `moot.toml` / `devcontainer.json` / `post-create.sh` / runner scripts / `.gitignore` in the worktree root. Known issue (tests assume a scaffolded project layout the spec worktree doesn't have).
  - 9 × `tests/test_scaffold.py::test_init_*` — `respx.models.AllMockedAssertionError: … /api/actors/me/agents not mocked`. Backend added the `/api/actors/me/agents` call after Run T shipped; the respx stubs in `test_scaffold.py::_stub_backend` haven't been updated. Queued as task #57.
- `uv run pyright .` → **11 errors, 0 warnings, 0 informations**. All in `src/moot/adapters/mcp_adapter.py` (httpx `Timeout`/`Extensions` argument types + `str | None` passed where `str` expected). Pre-existing per Run T § 2.

Ship gates (must match at verify time): **pytest: ≥ 96 passed, = 14 failed** (with the same named-regression list above), **pyright: = 11 errors**.

## 3. Scope

### In

- Rewrite `src/moot/devcontainer.py::up()` to stream native text output; drop JSON parse path; lookup container id via `container_id_or_none()` after the subprocess exits.
- Emit a pre-build hint (`Building devcontainer in <workspace> (first launch can take 1-3 minutes)...`) **only when** `container_id_or_none(workspace)` returns `None` before the subprocess runs.
- Tighten `_launch_role` output in `src/moot/launch.py` — one line per role (`Launched <role> in moot-<role>` or `<role> already running in moot-<role>`), drop the container/wt-path trailing tuple (container id lands in the closing summary).
- Add a closing summary to `cmd_up` only (D4): `Started <N> agents in container <short-id>. Connect with 'moot attach <role>' or check 'moot status'.` Print it after the loop, suppress it on error paths.
- **PATH fix for the launched bash** (scope item 7, added by Product amendment 2026-04-16T22:59Z). Change `_launch_role`'s tmux-invocation exec from `["bash", "-c", tmux_cmd]` to `["bash", "-lc", tmux_cmd]` so `~/.profile` sources and prepends `~/.local/bin` to PATH — the directory where `claude install` (invoked in the bundled `.devcontainer/post-create.sh`) places the `claude` binary. Resolved as **D-PATH** → Option A; see § 4 and § 13 spike.
- **Test for the PATH fix** (scope item 8). Extend the existing `test_cmd_exec_launch_full_flow` assertion in `tests/test_launch.py` to demand `["bash", "-lc"]` as the leading pair of args on the tmux-invocation call (instead of the current `["bash", "-c"]`).
- Bump version `0.2.0` → `0.2.1` in `src/moot/__init__.py` and `pyproject.toml`.
- Update 3 existing tests in `tests/test_devcontainer.py` (the JSON-path ones become obsolete); add 3 new tests in `tests/test_devcontainer.py` (streaming happy-path, preamble gating cold/warm, exit-0-but-no-container) and 1 in `tests/test_launch.py` (closing-summary assertion), plus tighten 1 existing assertion (PATH-fix in `test_cmd_exec_launch_full_flow`). Net: +4 tests, −1 test, 1 in-place assertion tightening.

### Out

- No changes to bundled `.devcontainer/` template (`src/moot/templates/devcontainer/*`) or `post-create.sh`.
- No changes to `cmd_status` / `cmd_compact` / `cmd_attach` / `cmd_down` or to `lifecycle.py`.
- No retry / recovery logic for failed builds.
- No spinner or progress-bar overlay (D5).
- No code-level short-circuit when container already running (D3 spike: re-up is ~0.35s, well under 1s).
- No fix for the pre-existing 14 failures in § 2 — tracked out-of-band.

## 4. D-decisions (D1-D5 + D-UX-1/2/3 locked at draft; D-PATH added by Product amendment and resolved by Spec spike)

- **D1 (text format, not JSON).** Invoke `devcontainer up --workspace-folder <ws>` with default text log output; drop the `--log-format json` flag. The CLI's native output IS the progress signal.
- **D2 (no embedded stderr in exceptions).** On non-zero exit, raise `DevcontainerError(f"devcontainer up failed (exit code {proc.returncode})")`. User has already seen the real error inline; re-capturing + re-emitting is what got Run T into the silent-failure trap.
- **D3 (no code-level short-circuit).** Spec spike (§ 13) measured re-up at ~0.35s on an alpine test workspace — well under the 1s threshold in Product's kickoff. The preamble-gating check in § 6.1 stays (the 1-3 minute hint would be misleading on a re-up), but we do not bypass the CLI call. D3 is resolved = skip short-circuit.
- **D4 (closing summary on `cmd_up` only, not `cmd_exec`).** Single-role `cmd_exec` already produces its per-role line; a duplicate summary for N=1 is noise.
- **D5 (no spinner).** CLI's native text output is the progress signal.
- **D-UX-1 (per-role line wording).** Drop the `(container <cid>, <wt_path>)` suffix from `_launch_role`'s success/skip lines. The container id appears exactly once in the closing summary; the worktree path is derivable from repo root + role and is noise for a status line. Simpler per-role line = easier visual scan of which roles came up. Product wrote "something like `Launched <role> in moot-<role>`"; this is that, verbatim.
- **D-UX-2 (closing summary counts launched + already-running).** `N` in `Started N agents...` is the count of roles that made it past the config-lookup step, regardless of whether `_launch_role` fast-returned on `_session_exists`. Rationale: the user asked for N agents to be up; all N are up when the summary prints. We are reporting alive-count, not newly-started count.
- **D-UX-3 (no closing summary on partial failure).** If `_launch_role` raises `SystemExit(1)` on a single role (tmux launch rc != 0), the loop propagates the exit and the summary is never printed. That's correct: `Started N agents` with a prior error line above it would be a lie.
- **D-PATH (PATH fix = Option A / `bash -lc`).** Product's amendment offered three options: A (`bash -lc`), B (explicit `export PATH="$HOME/.local/bin:$PATH"` prepended to `tmux_cmd`), C (both). Spec spiked all three against `mcr.microsoft.com/devcontainers/javascript-node:22` (the bundled template's image). Results in § 13:
  - `bash -c` with `~/.local/bin/claude` pre-existing → `which claude` fails (no `~/.local/bin` on PATH).
  - `bash -lc` with `~/.local/bin/claude` pre-existing → `which claude` succeeds; PATH prepends `/home/node/.local/bin`.
  - Explicit export via `bash -c "export PATH=$HOME/.local/bin:$PATH; …"` → also succeeds.

  The image's stock `~/.profile` contains the standard `if [ -d "$HOME/.local/bin" ]; then PATH="$HOME/.local/bin:$PATH"; fi` snippet — behaves as documented, as long as the directory exists at login-shell init (which is always true in post-provisioned containers because `claude install` ran during `postCreateCommand`). Product's recommendation was A unless the spike shows `.profile` unreliable; spike shows `.profile` fully reliable, so **D-PATH = Option A**. `bash -lc` is one character of diff and leverages the base image's documented behavior. No need for belt-and-suspenders (Option C adds surface area for zero safety win).

  Scope is narrow: **only the tmux-invocation exec in `_launch_role`** changes (current `launch.py:113-116`). The `_ensure_worktree` `bash -c` call (current `launch.py:46-52`) stays `bash -c` — it only invokes `git`, which is on the standard PATH and doesn't depend on `~/.local/bin`. Minimising blast radius.

## 5. Files changed

```
src/moot/__init__.py               (1 LOC; version bump)
pyproject.toml                     (1 LOC; version bump)
src/moot/devcontainer.py           (~30 LOC; up() rewrite)
src/moot/launch.py                 (~16 LOC; _launch_role output + PATH fix, cmd_up summary)
tests/test_devcontainer.py         (drop 2 tests, rewrite 2, add 3)
tests/test_launch.py               (add 1 test; tighten 2 assertions — closing summary + bash -lc)
```

No new modules. No changes to lifecycle.py, config.py, scaffold.py, cli.py, or any template.

## 6. Full drop-in code

### 6.1 `src/moot/devcontainer.py::up()` — rewrite

Replace the existing `up()` function (lines 36–76 in current source) with the block below. Leave the surrounding module docstring, `DevcontainerError`, `ensure_cli`, `container_id_or_none`, `_env_args`, `exec_capture`, `exec_detached`, `exec_interactive` unchanged. Remove the now-unused `import json` at module top.

```python
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
```

### 6.2 `src/moot/launch.py::_launch_role` — output tightening + PATH fix

Inside `_launch_role`, make three edits. Function signature and all surrounding logic stay identical.

```python
# Edit 1 — replace line 74:
#   print(f"Session {session} already running in {container_id[:12]}")
# with:
print(f"{role} already running in {session}")

# Edit 2 — replace line 120:
#   print(f"Launched {role} in {session} (container {container_id[:12]}, {wt_path})")
# with:
print(f"Launched {role} in {session}")

# Edit 3 (D-PATH) — replace the list literal on line 114:
#   ["bash", "-c", tmux_cmd],
# with:
["bash", "-lc", tmux_cmd],
```

Edit 3 turns the inner bash into a login shell so `~/.profile` sources and prepends `~/.local/bin` to PATH (where `claude install` placed the `claude` binary during post-create). Do not change the `bash -c` in `_ensure_worktree` (line 47-48) — that call only runs `git`, which lives on the standard PATH; keeping it `-c` minimises blast radius.

The anchor strings `--dangerously-load-development-channels` and `server:convo-channel` stay exactly where they are (line 91 in `_launch_role`'s claude_cmd build AND in `cmd_exec`'s docstring). Do not touch them — `test_launch_includes_channel_flag` depends on both sites.

### 6.3 `src/moot/launch.py::cmd_up` — closing summary

Replace the existing `cmd_up` body (lines 146–161 in current source) with:

```python
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
```

Note: `_launch_role` on the already-running path fast-returns via `return` (see line 75 in current source after the § 6.2 edit), so the `alive += 1` runs for both newly-started and already-running roles — matches D-UX-2.

### 6.4 `src/moot/__init__.py`

```python
"""moot — CLI + MCP adapters for Moot agent teams."""
__version__ = "0.2.1"
```

### 6.5 `pyproject.toml`

Change line 3 from `version = "0.2.0"` to `version = "0.2.1"`. No other edits.

## 7. Tests

### 7.1 `tests/test_devcontainer.py` — update and add

**Drop** these two tests (the JSON parse path is gone):

- `test_up_empty_stdout_raises`
- `test_up_malformed_json_raises`

**Rewrite** `test_up_error_outcome_raises` → `test_up_nonzero_exit_raises`:

```python
def test_up_nonzero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero exit from `devcontainer up` raises DevcontainerError with
    the exit code embedded; stderr/stdout are NOT captured in the message
    (they already streamed to the user's terminal)."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc, "container_id_or_none", lambda _ws: None
    )
    monkeypatch.setattr(
        dc.subprocess, "run",
        lambda *a, **kw: _fake_run(returncode=137),
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "exit code 137" in str(exc.value)
```

**Rewrite** `test_up_parses_container_id` → `test_up_streams_then_looks_up_id`:

```python
def test_up_streams_then_looks_up_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Success path: no --log-format flag, output not captured, container
    id comes from the post-exit `container_id_or_none()` call."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    # container_id_or_none is called twice — before (returns None → cold)
    # and after (returns the id).
    lookups: list[Path] = []

    def fake_lookup(ws: Path) -> str | None:
        lookups.append(ws)
        return None if len(lookups) == 1 else "cid_from_lookup"

    monkeypatch.setattr(dc, "container_id_or_none", fake_lookup)

    captured: dict[str, object] = {}

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _fake_run(returncode=0)

    monkeypatch.setattr(dc.subprocess, "run", fake_run)

    result = up(Path("/tmp/workspace"))

    assert result == "cid_from_lookup"
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd == [
        "devcontainer", "up",
        "--workspace-folder", "/tmp/workspace",
    ]
    # No --log-format json, no capture_output=True
    assert "--log-format" not in cmd
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert not kwargs.get("capture_output")
    assert len(lookups) == 2
```

**Add** `test_up_prints_build_hint_when_cold`:

```python
def test_up_prints_build_hint_when_cold(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cold boot: no running container → preamble prints before the CLI call."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    lookups: list[Path] = []

    def fake_lookup(ws: Path) -> str | None:
        lookups.append(ws)
        return None if len(lookups) == 1 else "cidCold"

    monkeypatch.setattr(dc, "container_id_or_none", fake_lookup)
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(returncode=0)
    )

    up(Path("/tmp/workspace"))
    out = capsys.readouterr().out
    assert "Building devcontainer in /tmp/workspace" in out
    assert "1-3 minutes" in out
```

**Add** `test_up_skips_build_hint_when_warm`:

```python
def test_up_skips_build_hint_when_warm(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Re-up: container already running → preamble suppressed. CLI still runs
    (no code-level short-circuit per D3)."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(
        dc, "container_id_or_none", lambda _ws: "cidWarm"
    )
    ran: list[list[str]] = []

    def fake_run(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        ran.append(cmd)
        return _fake_run(returncode=0)

    monkeypatch.setattr(dc.subprocess, "run", fake_run)

    result = up(Path("/tmp/workspace"))
    assert result == "cidWarm"
    out = capsys.readouterr().out
    assert "Building devcontainer" not in out
    assert "1-3 minutes" not in out
    assert len(ran) == 1  # CLI still invoked; no short-circuit
```

**Add** `test_up_exit_0_but_no_container_raises`:

```python
def test_up_exit_0_but_no_container_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: if CLI exits 0 but no labelled container is found, raise
    rather than returning an empty string."""
    import moot.devcontainer as dc
    monkeypatch.setattr(dc.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(dc, "container_id_or_none", lambda _ws: None)
    monkeypatch.setattr(
        dc.subprocess, "run", lambda *a, **kw: _fake_run(returncode=0)
    )
    with pytest.raises(DevcontainerError) as exc:
        up(Path("/tmp/workspace"))
    assert "no running container" in str(exc.value).lower()
```

**Unchanged** in `tests/test_devcontainer.py`: `test_ensure_cli_missing_raises`, `test_ensure_cli_present_returns`, `test_container_id_or_none_found`, `test_container_id_or_none_empty`, all three `exec_*` tests. Keep the `_fake_run` helper at module level.

**Remove the `import json` at the top** of `tests/test_devcontainer.py` (no longer used after the rewrites above).

### 7.2 `tests/test_launch.py` — add closing summary test

**Update** `test_cmd_up_boots_once`: after `launch.cmd_up(ns)`, the test currently only asserts `len(up_calls) == 1`. Add one more line at the end to verify the summary now prints (no behavior change to what the test already exercises — just a new assertion):

```python
def test_cmd_up_boots_once(
    monkeypatch: pytest.MonkeyPatch,
    patch_config: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """cmd_up calls up() exactly once even when launching multiple roles
    and prints the closing summary naming the container."""
    import moot.launch as launch

    up_calls: list[Path] = []

    def fake_up(wd: Path) -> str:
        up_calls.append(wd)
        return "cidOnceAAAAAA"

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
    out = capsys.readouterr().out
    # 2 roles in FakeConfig (spec, impl), both already running
    assert "Started 2 agents in container cidOnceAAAAA" in out
    assert "moot attach" in out
    assert "moot status" in out
```

Note `cidOnceAAAAAA` is 12 chars when sliced `[:12]` (the existing `[:12]` slice in cmd_up produces `cidOnceAAAAA` — A-count: count the characters if in doubt; 3 + 9 = 12). No other tests in `test_launch.py` need changes.

**Update `test_cmd_exec_launch_full_flow`** (D-PATH scope item 8). Two adjustments inside the existing test body — do NOT add a new test, just tighten the existing one:

1. Change the `tmux_indices` comprehension from matching `["bash", "-c"]` to `["bash", "-lc"]`:

```python
# Replace (current lines 73-75 in tests/test_launch.py):
#   tmux_indices = [
#       i for i, a in enumerate(captured_args) if a[:2] == ["bash", "-c"]
#   ]
# with:
tmux_indices = [
    i for i, a in enumerate(captured_args) if a[:2] == ["bash", "-lc"]
]
```

2. Immediately after the existing `assert tmux_indices, ...` line, add one explicit PATH-fix assertion so the fix is visible at the top of the failure message when it regresses:

```python
# after: assert tmux_indices, "expected a bash -c ... call for tmux new-session"
# also update the message string:
assert tmux_indices, "expected a bash -lc ... call for tmux new-session"
tmux_call = captured_args[tmux_indices[-1]]
assert tmux_call[:2] == ["bash", "-lc"], (
    "tmux launch must use `bash -lc` to source ~/.profile and pick up ~/.local/bin"
)
```

The rest of the test (script assertions on `tmux new-session`, channel flag, `convo_key_spec` not in script, env dict checks) stays unchanged.

**Unchanged in `test_launch.py`**: `test_cmd_exec_session_already_running`, `test_cmd_exec_unknown_role`, `test_cmd_exec_no_moot_toml`, `test_cmd_down_stops_tmux_sessions`. In particular `test_cmd_exec_session_already_running` asserts only `"already running" in out`, which still holds with the D-UX-1 wording (`"spec already running in moot-spec"` contains "already running"). `test_cmd_exec_launch_full_flow` does not assert on the `Launched` line text, so tightening the per-role line wording is safe.

### 7.3 Anchor-string test (unchanged)

`tests/test_scaffold.py::test_launch_includes_channel_flag` (lines 460–467 in current source) uses `inspect.getsource(cmd_exec)`. The anchor strings remain in `cmd_exec`'s docstring per Run T § 6.2's dual-anchor pattern. **Do not touch this test.**

### 7.4 Suggested extra coverage (QA discretion)

- **Q-1 Grep invariant (≥ 1 hit each, ≤ expected max):** `grep -n "\-\-log-format json" src/moot/` should return 0 lines. `grep -n "json.loads\|json.JSONDecodeError" src/moot/devcontainer.py` should return 0 lines. These are the strongest signals that the JSON path was truly removed, not just bypassed.
- **Q-2 Grep invariant:** `grep -n "dangerously-load-development-channels" src/moot/launch.py` should return ≥ 2 hits (one in `cmd_exec`'s docstring, one in `_launch_role`'s `claude_cmd`). Run T retro flagged this phrasing ("present" vs. "exactly 1") — here, ≥ 2 is the correct gate because both sites are load-bearing.
- **Q-3 Smoke end-to-end (optional, requires docker):** `uv run moot up` in a temp workspace with a minimal `.devcontainer/devcontainer.json` (alpine image) should show the preamble line on first call, suppress it on second, and print the closing summary in both cases. Pat will run the real smoke against the bundled template; QA's is a sanity pass only.

## 8. Security considerations

- **No new auth surface.** `moot up` runs entirely on the host under the user's own uid; no HTTP endpoints change and no secrets are read or written.
- **No new input validation boundary.** The `--workspace-folder` argument we pass to `devcontainer up` is `str(Path.cwd())` — the user's own working directory, not attacker-controlled.
- **No secrets in error paths.** D2 drops the captured stderr; `DevcontainerError` messages are now `"devcontainer up failed (exit code N)"` with no command line, no env, no path beyond the workspace the user passed in themselves. A malicious `post-create.sh` that `echo $SECRET`s would leak to the user's own terminal (same as running it directly), never to logs or exception messages we serialize.
- **Tenant isolation.** Not applicable — `moot up` is a host-local CLI.
- **No `{@html}` / XSS surface.** Not applicable — terminal output only.

## 9. Open questions

None. Product pre-locked D1-D5 at kickoff. D3 resolved by Spec spike in § 13. D-UX-1/2/3 are cosmetic UX tie-ups Spec resolved in-draft per `feedback_spec_resolves_product_doc_silences.md` (per-role line wording, alive-count semantics, summary-suppression on error). Impl should flag a `message_type="question"` reply in the feature thread only if a D-UX tie-up proves wrong under hand-running.

## 10. Risks

- **Hidden dependency on `--log-format json` stdout.** Greps confirm no other call site reads `up()`'s JSON output — `up()` currently returns `str` and all callers in `src/` (launch.py:142, launch.py:156) use it as an opaque container id. Safe to drop.
- **`subprocess.run([...])` with no redirect inherits parent stdio.** On a terminal, that's exactly the streaming we want. Under pytest the fixture `capsys` captures `sys.stdout`, so tests must mock `subprocess.run` (which they do) and not actually spawn. Under CI without a TTY, the CLI's text output may be slightly different from interactive (e.g., no ANSI color); that is fine — this run does not assert on the streamed content.
- **Pyright on the new `up()`.** The `kwargs.get("capture_output")` branch in `test_up_streams_then_looks_up_id` reads a `dict[str, object]`. Pyright has previously flagged `object`-subscript patterns in test capture dicts (`feedback_pyright_object_subscript_in_test_captures.md`). The test above uses `captured["kwargs"]` with an explicit `isinstance` check and `.get()` — no subscript on `object`. Should pass clean.
- **Per-role line text drift.** `test_cmd_exec_session_already_running` asserts `"already running" in out`. The new wording (`"spec already running in moot-spec"`) still contains that substring. Verified.

## 11. Import audit

Module-level imports in each file after the edits:

- `src/moot/devcontainer.py` — **remove** `import json` (unused after `up()` rewrite). Keep `import shutil`, `import subprocess`, `from pathlib import Path`.
- `src/moot/launch.py` — no changes to imports. Still needs `shlex`, `Path`, `MootConfig`, `find_config`, `get_actor_key`, and the four `moot.devcontainer` names already imported.
- `src/moot/__init__.py` — no imports (docstring + `__version__` only).
- `tests/test_devcontainer.py` — **remove** `import json` (no longer constructing JSON payloads). Keep `subprocess`, `Path`, `pytest`, and the `moot.devcontainer` imports (still need `DevcontainerError`, `container_id_or_none`, `ensure_cli`, `exec_capture`, `exec_detached`, `exec_interactive`, `up`).
- `tests/test_launch.py` — no changes to imports. `capsys` is a pytest fixture and needs no import beyond the existing `import pytest`.

## 12. Cross-refs (recent memory that applies to this run)

- `feedback_dead_helper_half_draft.md` — no `NotImplementedError` stubs or half-drafted helpers; § 6 is drop-in code that compiles.
- `feedback_pyright_object_subscript_in_test_captures.md` — § 7 capture dicts are typed `dict[str, object]`; reads go through `isinstance` narrows or `.get()`, not bare subscript into `object`.
- `feedback_cross_module_monkeypatch_indirection.md` — tests patch `moot.devcontainer.subprocess` and `moot.devcontainer.container_id_or_none` directly on the `dc` module where `up()` reads them. No cross-module indirection in the new code.
- `feedback_no_skip_pipeline.md` — even ~60 LOC of UX patch goes through the standard pipeline.
- `feedback_cross_repo_first_run_baseline.md` — baseline remeasured at feat-tip in § 2 (not inherited from Run T).
- `feedback_spec_resolves_product_doc_silences.md` — three D-UX decisions resolved in-draft rather than escalated.
- `feedback_docker_pyproject_not_bind_mounted.md` — no new Python deps in this run, so no `docker cp` dance needed. Impl can edit source and run `uv run pytest` directly in the host venv.
- `feedback_verify_product_grounding_claims.md` — Product's "Need to check whether devcontainer CLI's idempotent-rerun path is fast enough" explicitly asked for verification. D3 spike (§ 13) is that verification.
- spec-checklist § 7 verification-gate wording — Q-1 / Q-2 greps use "≥ 1" framing (Q-2) and "= 0" for removal-checks (Q-1), not "exactly N".

## 13. Grounding (commands Spec ran at draft time)

All commands run in `/workspaces/convo/mootup-io/moot/.worktrees/spec` on `spec/moot-up-progress-output` branched from `feat/moot-up-progress-output` @ `b684dd6`.

```sh
# Baseline (§ 2)
uv sync --group test
uv run pytest                 # → 96 passed, 14 failed (§ 2 enumerates the 14)
uv run pyright .              # → 11 errors

# Blast radius for up() / container_id_or_none()
grep -rn "from moot.devcontainer\|container_id_or_none\|devcontainer.up" \
    src/ tests/ --include='*.py'
# Callers of up(): launch.py:142 (cmd_exec), launch.py:156 (cmd_up) — only.
# No other src/ module imports up() or container_id_or_none.

# D3 spike — time `devcontainer up` against a running container
TMPWS=$(mktemp -d /tmp/dc-spike-XXXX)
mkdir -p "$TMPWS/.devcontainer"
cat > "$TMPWS/.devcontainer/devcontainer.json" <<'EOF'
{"name":"dc-spike","image":"alpine:3.19","overrideCommand":true}
EOF
time devcontainer up --workspace-folder "$TMPWS"     # cold: 5.285s
time devcontainer up --workspace-folder "$TMPWS"     # warm: 0.352s
time devcontainer up --workspace-folder "$TMPWS"     # warm: 0.323s
CID=$(docker ps -q --filter "label=devcontainer.local_folder=$TMPWS")
docker rm -f "$CID"
rm -rf "$TMPWS"
# Conclusion: warm re-up is ~0.35s → well under 1s threshold → D3 = skip short-circuit.
```

Scope-in/scope-out contradiction grep (per `feedback_scope_in_out_contradiction_grep.md`): Scope (in) says "per-role launch feedback" and "tighten `_launch_role` output"; Scope (out) says no changes to `cmd_status`/`cmd_compact`/`cmd_attach`/`cmd_down`. No overlap — `_launch_role` lives in `launch.py` and is only called by `cmd_exec` and `cmd_up`. Clean.

### D-PATH spike (Product amendment, 2026-04-16T22:59Z)

Pulled the bundled template's base image once; ran six one-shot tests. Results verbatim:

```sh
IMAGE=mcr.microsoft.com/devcontainers/javascript-node:22

# 1. bash -c PATH
docker run --rm -u node $IMAGE bash -c 'echo $PATH'
# → /usr/local/share/nvm/current/bin:/usr/local/share/npm-global/bin:
#   /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# (no ~/.local/bin)

# 2. bash -lc PATH (no ~/.local/bin pre-created)
docker run --rm -u node $IMAGE bash -lc 'echo $PATH'
# → /usr/local/share/nvm/current/bin:/usr/local/share/npm-global/bin:
#   /usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games
# (still no ~/.local/bin, because the `.profile` snippet checks `-d $HOME/.local/bin`
#  at shell-init time and the dir doesn't exist yet)

# 3. ~/.profile content
docker run --rm -u node $IMAGE bash -c 'head -30 ~/.profile'
# ...
#   if [ -d "$HOME/.local/bin" ] ; then
#       PATH="$HOME/.local/bin:$PATH"
#   fi

# 4. pre-create ~/.local/bin THEN bash -lc → which finds it
docker run --rm -u node $IMAGE bash -c '
  mkdir -p ~/.local/bin && touch ~/.local/bin/real-claude
  && chmod +x ~/.local/bin/real-claude
  && bash -lc "which real-claude; echo PATH=\$PATH"'
# → /home/node/.local/bin/real-claude
#   PATH=/home/node/.local/bin:/usr/local/share/nvm/current/bin:...

# 5. pre-create ~/.local/bin THEN bash -c → which FAILS
docker run --rm -u node $IMAGE bash -c '
  mkdir -p ~/.local/bin && touch ~/.local/bin/real-claude
  && chmod +x ~/.local/bin/real-claude
  && bash -c "which real-claude; echo PATH=\$PATH"'
# → (empty; which returns 1)
#   PATH=/usr/local/share/nvm/current/bin:/usr/local/share/npm-global/bin:
#        /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# 6. explicit export in bash -c (Option B) → works
docker run --rm -u node $IMAGE bash -c '
  mkdir -p ~/.local/bin && touch ~/.local/bin/real-claude
  && chmod +x ~/.local/bin/real-claude
  && bash -c "export PATH=\$HOME/.local/bin:\$PATH; which real-claude"'
# → /home/node/.local/bin/real-claude
```

Conclusion: Option A (`bash -lc`) works because `~/.profile` (already shipped in the base image with the correct conditional append) picks up `~/.local/bin` at login-shell init, and by the time `moot up` runs, `claude install` has already created the directory via post-create.sh. Option C's explicit export is belt-and-suspenders; not needed. **D-PATH = Option A**.

## 14. Handoff (Impl guidance)

### Order of operations

1. Bump version in both `src/moot/__init__.py` and `pyproject.toml` (`0.2.0` → `0.2.1`).
2. Edit `src/moot/devcontainer.py`: apply § 6.1 `up()` rewrite; remove the now-unused `import json` at the module top.
3. Edit `src/moot/launch.py`: apply § 6.2 — three edits in `_launch_role` (two print strings + `bash -lc` PATH fix) — and § 6.3 (`cmd_up` closing summary). Do not touch `cmd_exec` or its docstring. Do not touch `_ensure_worktree`'s `bash -c` (only runs `git`; on standard PATH; minimises blast radius).
4. Edit `tests/test_devcontainer.py`: drop 2 tests, rewrite 2, add 3 (per § 7.1). Remove `import json`.
5. Edit `tests/test_launch.py`: update `test_cmd_up_boots_once` to add capsys assertion (per § 7.2); tighten `test_cmd_exec_launch_full_flow` to match `["bash", "-lc"]` (per § 7.2 D-PATH block — two small in-place changes, NOT a new test).
6. Run `uv run pytest tests/test_devcontainer.py tests/test_launch.py tests/test_scaffold.py -v` — should show the new tests passing, the anchor test still passing, and the 9 scaffold failures unchanged.
7. Run full `uv run pytest` — expect 99 passed (96 + 4 − 1), 14 failed (same pre-existing set).
8. Run `uv run pyright .` — expect 11 errors (unchanged). If any new error surfaces on `up()` or the test captures, fix before handing off.
9. Run `uv run moot --version` — should print `moot 0.2.1`.
10. Commit on `impl/moot-up-progress-output` and post `git_request` to Leader in the feature thread.

### Impl-specific gotchas (from recent memory)

- **SPEC-READY pre-draft encouraged.** Scope is fully specified; no OQs block you. Per `feedback_pre_draft_during_design_hold.md`, start drafting the edits while Spec waits for Leader's merge-ack.
- **Don't one-shot.** Per `feedback_incremental_carve.md`, edit `up()` first, run `uv run pytest tests/test_devcontainer.py -v`, get it green, then move to `launch.py`. Much easier to localise a regression.
- **Host worktree test pollution.** `uv sync --group test` will bump `mootup` in `uv.lock` from 0.1.6 to 0.2.1 — do not commit the `uv.lock` diff in this PR (Run T's `uv.lock` was deliberately left at 0.1.6 for the same reason; `git checkout -- uv.lock` before commit if it changes). If uv.lock tracking becomes load-bearing, that's a separate run.
- **Multi-edit hygiene.** When editing `devcontainer.py` and `launch.py` in the same session, mind `feedback_cross_worktree_git_mutations.md`: stay inside `/workspaces/convo/mootup-io/moot/.worktrees/spec` during `git add`/`git commit`; use `git -C` if you need to reach another worktree.
- **Subagent fan-out: not a fit here.** Sequential edits with intermediate test runs; single-worktree. Stay in the main session.

### SPEC-READY handoff (Spec → Leader)

Spec commits this spec on `spec/moot-up-progress-output`, posts `message_type="git_request"` in the feature thread asking Leader to merge `spec/moot-up-progress-output` → `feat/moot-up-progress-output`, then posts SPEC-READY (`message_type="status_update"`, reply in thread, mentions Implementation) with a one-line pointer to this file. Leader confirms merge; Impl pulls `feat/moot-up-progress-output` and begins.
