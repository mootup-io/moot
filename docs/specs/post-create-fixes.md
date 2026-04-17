# moot-cli post-create.sh fixes — package-name typo + claude PATH + strict mode + publish doc

**Run V.** Template-bugfix run on `mootup-io/moot/src/moot/templates/devcontainer/post-create.sh`. Branch: `spec/post-create-fixes` → `feat/post-create-fixes`. Target version: `0.2.2`.

## 1. Summary

Bundled `post-create.sh` has two bugs that bite every new user running `moot init` → `moot up` on a fresh project:

1. **Wrong package name.** Line 15 says `pip install moot`; the PyPI distribution is `mootup`. Post-create fails with `ERROR: Could not find a version that satisfies the requirement moot (from versions: none)`.
2. **`claude install` removes the npm binary.** Line 9 runs `claude install` immediately after `npm install -g @anthropic-ai/claude-code`. `claude install` moves the native build to `~/.local/bin/claude` AND deletes the npm symlink at `/usr/local/share/npm-global/bin/claude`. Since `~/.local/bin` is not on the script's PATH (which is fixed at process start), lines 20–21 (`claude mcp add …`) fail with `claude: command not found`.

This run fixes both at source (item 1 = one-word edit; item 2 = drop `claude install` per D2 spike — the npm binary alone supports `--version`, `mcp add`, and `mcp list`). Also tightens shell strictness (`set -euo pipefail`) and adds a one-page `docs/publish.md` documenting the PyPI publish flow that the template hard-depends on.

Diff is ~5 line edits in `post-create.sh`, 1 in-place test-assertion tighten, 3 new tests in `tests/test_templates.py`, and ~1 new doc file (~60–100 LOC). Version bump `0.2.1` → `0.2.2`.

## 2. Baseline (mootup-io/moot `feat/post-create-fixes` @ `94b8b8d`, post Run U)

Measured in `/workspaces/convo/mootup-io/moot/.worktrees/spec` with `uv sync --group test` applied.

- `uv run pytest` → **97 passed, 14 failed** in 2.50s. All 14 failures are pre-existing per Run T § 2 and out of scope:
  - 5 × `tests/test_example.py::*` — worktree-path-dependent `FileNotFoundError` on `moot.toml`/`devcontainer.json`/`post-create.sh`/runner scripts/`.gitignore`.
  - 9 × `tests/test_scaffold.py::test_init_*` — `respx.models.AllMockedAssertionError: … /api/actors/me/agents not mocked` (queued as task #57).
- `uv run pyright .` → **11 errors, 0 warnings, 0 informations**. All in `src/moot/adapters/mcp_adapter.py` (pre-existing per Run T § 2).
- `moot --version` → `moot 0.2.1`.

Ship gates (must match at verify time): **pytest: drops −0, rewrites ±0, adds +3 → net +3 → ≥ 100 passed, = 14 failed** (with the same named-regression list); **pyright: = 11 errors** (unchanged — no source changes outside templates + tests); **`moot --version` → `moot 0.2.2`**; **`docs/publish.md` exists**.

## 3. Scope

### In

- Fix the package-name typo in `post-create.sh` line 15: `pip install moot` → `pip install mootup`. No version pin (per § 4 D-PIN).
- Drop `claude install` from `post-create.sh` line 9 (per § 4 D2 = Option B). The `npm install -g @anthropic-ai/claude-code` on line 8 is sufficient — leaves `claude` at `/usr/local/share/npm-global/bin/claude`, which is on PATH inside both `bash -c` and `bash -lc` under `docker exec`.
- Replace `set -e` on line 2 with `set -euo pipefail` (adds `-u` unbound-variable check + `-o pipefail` so a failing command in a pipeline propagates its exit code).
- Tighten the existing `tests/test_templates.py::test_post_create_no_convo_paths` assertion: change `"pip install moot" in content` → `"pip install mootup" in content`. In-place.
- Add 3 new tests to `tests/test_templates.py`:
  - `test_post_create_does_not_run_claude_install` — asserts `"claude install" not in content` (with a line-level grep, not substring, to avoid false positive if a comment uses the phrase).
  - `test_post_create_uses_strict_mode` — asserts the script starts with a `set -euo pipefail` line (either one line or equivalent combination of `set -e`, `set -u`, `set -o pipefail`).
  - `test_publish_doc_exists` — asserts `docs/publish.md` exists under the repo root and is non-empty.
- Add `docs/publish.md` (new file) — one-page runbook for publishing `mootup` to PyPI. Covers: prerequisites (PyPI account + twine credentials via `~/.pypirc` or `TWINE_*` env), build command (`python -m build` or `uv build`), upload command (`twine upload dist/*`), version-bump checklist (`src/moot/__init__.py`, `pyproject.toml`, git tag), post-publish smoke (`pip install 'mootup==<new>'` in a clean venv). Under 100 LOC.
- Bump version `0.2.1` → `0.2.2` in `src/moot/__init__.py` and `pyproject.toml`.

### Out

- No changes to `src/moot/` Python source (launch.py, devcontainer.py, lifecycle.py, cli.py, scaffold.py, config.py, adapters/, etc.). Run T/U territory; nothing here touches runtime code paths.
- No changes to other bundled template files (`devcontainer.json`, `run-moot-mcp.sh`, `run-moot-channel.sh`, `run-moot-notify.sh`).
- No shellcheck gate. Shellcheck is not present in the moot CI environment (verified: `which shellcheck` → not found in `spec` worktree). Product marked this nice-to-have, not a hard gate.
- No actual PyPI publish of 0.2.2. The doc describes the procedure; Pat runs the upload on their laptop.
- No version pin in `pip install mootup` (per D-PIN).
- No fix for the pre-existing 14 test failures.
- No replacement or reordering of `npm install -g @anthropic-ai/claude-code` (keep as-is; it's what provides `claude` on PATH after D2).
- No `uv.lock` commit (per Run T/U precedent; `uv sync --group test` bumps `mootup` version in lock, which is a local-only side effect).

## 4. D-decisions (D1–D3 from Product locked; D2 = Option B per Spec spike; D-PIN resolved by Spec)

- **D1 (separate run from U).** Locked by Product. `templates/devcontainer/post-create.sh` is a different file from `src/moot/launch.py` (which Run U rewrote). No shared test surface. Separate merge commit keeps blast radii clean.

- **D2 (drop `claude install`) — Option B.** Spec spike results in § 13. Three options offered by Product:
  - **A:** add `export PATH="$HOME/.local/bin:$PATH"` after `claude install`.
  - **B:** drop `claude install` entirely.
  - **C:** reorder (`claude install` then `npm install`).

  **Spike evidence.** Inside a fresh `mcr.microsoft.com/devcontainers/javascript-node:22` container running as `--user node`:
  - After `npm install -g @anthropic-ai/claude-code` alone: `which claude` → `/usr/local/share/npm-global/bin/claude`; `claude --version` → `2.1.112 (Claude Code)`; `claude mcp add test /bin/true -s local` → `Added stdio MCP server test`; `claude mcp list` → works. The npm binary supports every command post-create.sh invokes.
  - Running `claude install` afterwards **deletes** the npm symlink (`ls /usr/local/share/npm-global/bin/claude` → `No such file or directory`) AND places the native build at `~/.local/bin/claude`. Since `~/.local/bin` is not on the script's PATH (the installer itself warns: `Native installation exists but ~/.local/bin is not in your PATH`), `which claude` returns empty and subsequent invocations fail with `claude: command not found`. This is the live bug.

  **Option B is cleanest.** Drops the self-sabotaging binary swap; keeps one `claude` binary on PATH; eliminates the PATH-dance with no behavior loss (the native build is an optional speed optimization that moot doesn't depend on). Product's written preference: "Strong recommend Option B if the spike confirms claude-from-npm is sufficient — fewer moving parts, no PATH dance." Confirmed.

  **Option A rejected** — works but carries operational complexity (subshells or later PATH edits that truncate the export would silently regress to the bug). Option C rejected — `claude install` still removes the npm binary, so running `npm install` afterwards would restore it with the native binary also present but unused. Both the npm and native installs would exist; PATH-first-match wins; it's an ambiguous state with no clear benefit.

  **Interaction with Run U's `bash -lc` fix (launch.py).** Run U shipped `["bash", "-lc", tmux_cmd]` in `_launch_role` so the login-shell `.profile` would prepend `~/.local/bin` to PATH — necessary because `claude install` put the binary there. With Option B that binary is no longer there, so strictly the `-lc` login-shell behavior is no longer required for `claude` to resolve. **Keep Run U's `bash -lc` unchanged anyway.** The login shell is a strictly more-correct default (also picks up anything a user drops into their `.bashrc`/`.profile` later); `/usr/local/share/npm-global/bin` is on PATH in both `bash -c` and `bash -lc` under `docker exec` (verified in § 13 spike). Swapping back to `-c` would be a behavior change outside Run V's scope.

- **D3 (publish doc is in scope).** Locked by Product. The production bootstrap path (`pip install mootup` in post-create.sh after Run V) hard-depends on PyPI being current. One-page runbook closes the operational gap.

- **D-TESTFIX (strict-mode test token parsing) — resolved by Spec after Impl flag.** The initial § 7.2 test helper used naive substring checks (`"-u" in stripped`) to detect flags, which fails for the combined form `set -euo pipefail` — the literal substring `-u` is not present (the `-` appears only before `e`). Impl caught this during pre-draft (`evt_7vp1wny7f36aq`). Fix: split the `set` line into tokens and accumulate single-letter flags from each `-XYZ` token (skipping `-o`, which takes a named argument covered by the separate `"pipefail" in stripped` check). Accepts both combined (`set -euo pipefail`) and split (`set -e`/`set -u`/`set -o pipefail`) forms. Applied in § 7.2 `test_post_create_uses_strict_mode`.

- **D-PIN (no version pin on `pip install mootup`) — resolved by Spec.** Product left this decision open ("optionally add a version pin: `pip install 'mootup>=0.2.1'` once PyPI has a published 0.2.x release. If PyPI is still on 0.1.x at draft time, leave the version unpinned."). PyPI check at spec draft: `mootup` releases on PyPI are `[0.1.0, 0.1.1, 0.1.2, 0.1.3, 0.1.4, 0.2.0]` — 0.2.x IS published, so the Product-stated condition for pinning is met. **Still leave unpinned.** Reason: post-create.sh is bundled into every `moot init` output, and the floor version drifts every release (today's pin `>=0.2.1` is stale as soon as 0.3.0 ships and a user scaffolds a new project — they'd get 0.3.0 regardless, so the pin adds no floor guarantee in practice). Unpinned `pip install mootup` installs latest PyPI release, which matches user intent. Per `feedback_spec_resolves_product_doc_silences.md` — resolve in-draft, document as D-decision.

## 5. UX

No user-visible UX changes to `moot up`, `moot init`, or any CLI command. The three script changes affect only the devcontainer provisioning phase (bash output visible via `moot up`'s new streaming terminal, shipped in Run U):

- On the fix path, the failing lines (`pip install moot` → error, then `claude mcp add` → error) no longer appear. The `post-create` run reaches `echo "Setup complete. Next: moot login --token <key>, then moot config provision"` on first try.
- Under `set -u`, an unset variable reference anywhere in the script aborts with `unbound variable`. Current script references no variables, so `-u` is purely defensive. Under `set -o pipefail`, a failing command in any pipeline (none exist today) would propagate its exit. Both are future-proofing; zero effect on the current script's execution.

## 6. Source changes

Exact line-by-line edits. Anchor with surrounding context so Impl can grep cleanly.

### 6.1 `src/moot/templates/devcontainer/post-create.sh`

**Before (current, 24 lines):**
```bash
#!/bin/bash
set -e

# System packages
sudo apt-get update && sudo apt-get install -y tmux

# Claude Code CLI
npm install -g @anthropic-ai/claude-code
claude install

# Python tooling
pip install uv

# Install moot package
pip install moot

# Register MCP servers for Claude Code.
# The wrapper scripts read CONVO_ROLE and look up API keys from
# .agents.json at runtime — no keys needed here.
claude mcp add convo .devcontainer/run-moot-mcp.sh -s local
claude mcp add convo-channel .devcontainer/run-moot-channel.sh -s local

echo "Setup complete. Next: moot login --token <key>, then moot config provision"
```

**After (22 lines):**
```bash
#!/bin/bash
set -euo pipefail

# System packages
sudo apt-get update && sudo apt-get install -y tmux

# Claude Code CLI (npm-installed binary lands on PATH at
# /usr/local/share/npm-global/bin/claude; `claude install` would
# move the native build to ~/.local/bin and delete this symlink,
# breaking the `claude mcp add` lines below — see Run V).
npm install -g @anthropic-ai/claude-code

# Python tooling
pip install uv

# Install moot package
pip install mootup

# Register MCP servers for Claude Code.
# The wrapper scripts read CONVO_ROLE and look up API keys from
# .agents.json at runtime — no keys needed here.
claude mcp add convo .devcontainer/run-moot-mcp.sh -s local
claude mcp add convo-channel .devcontainer/run-moot-channel.sh -s local

echo "Setup complete. Next: moot login --token <key>, then moot config provision"
```

**Diff summary (3 line changes, 1 line deletion):**
- Line 2: `set -e` → `set -euo pipefail`.
- Line 7 comment updated (optional rewording; keep if you want the Run V context inline, drop to revert to the original two-line comment — no correctness impact).
- Line 9: `claude install` — **deleted**.
- Line 15: `pip install moot` → `pip install mootup`.

### 6.2 Version bump

- `src/moot/__init__.py`: `__version__ = "0.2.1"` → `__version__ = "0.2.2"`.
- `pyproject.toml`: `version = "0.2.1"` → `version = "0.2.2"`.

Both strings appear exactly once in each file (confirmed with `grep -n '"0.2.1"' src/moot/__init__.py pyproject.toml`).

### 6.3 `docs/publish.md` (new, target ~60–90 LOC)

One-page runbook. Required sections:

- **Prerequisites.** PyPI account on https://pypi.org; `twine` installed (`pip install twine` or `uv tool install twine`); `~/.pypirc` with an API token OR `TWINE_USERNAME=__token__` + `TWINE_PASSWORD=pypi-…` in env.
- **Version bump.** Update `src/moot/__init__.py::__version__` and `pyproject.toml::version` to matching new SemVer. Confirm no other site hard-codes the version: `grep -rn '0\.2\.' src/ pyproject.toml` (allow list: the two authoritative sites).
- **Build.** `rm -rf dist/ && python -m build` (or `uv build` if `uv` is installed). Produces `dist/mootup-<new>-py3-none-any.whl` + `dist/mootup-<new>.tar.gz`.
- **Upload.** `twine upload dist/*`. Twine prompts for credentials if not in env.
- **Smoke (post-publish).** In a clean venv: `python -m venv /tmp/smoke && source /tmp/smoke/bin/activate && pip install 'mootup==<new>' && moot --version`. Should print `moot <new>`.
- **Tag and push.** `git tag v<new> && git push origin v<new>` (optional; matches the version in the release).

Impl is free to expand with code blocks, troubleshooting, or reference commands as long as the file stays under 100 LOC. No new claims beyond the above bullets.

## 7. Tests

All test changes land in `tests/test_templates.py` (the existing location for bundled-template assertions).

### 7.1 Existing test impact

- `test_post_create_no_convo_paths` (`tests/test_templates.py:120-135`) asserts `"pip install moot" in content`. After Run V, the content is `"pip install mootup"` — the substring `"pip install moot"` is STILL present (prefix match), so the assertion would pass by accident. **Tighten in-place:** change the assertion to `"pip install mootup" in content` (and update the error message to match). Stronger regression guard against re-introducing the typo. **Test count delta: 0 (in-place tighten, no drop, no add).**

### 7.2 New tests

Add these three functions at the end of the "Devcontainer template tests" block in `tests/test_templates.py` (before the `TeamProfile` class at line 157).

```python
def test_post_create_does_not_run_claude_install() -> None:
    """post-create.sh does NOT invoke `claude install` — it deletes the npm binary.

    Regression guard for Run V: `claude install` replaces
    /usr/local/share/npm-global/bin/claude with ~/.local/bin/claude
    and ~/.local/bin is not on the script's PATH, so the subsequent
    `claude mcp add` lines fail with `claude: command not found`.
    """
    content = (DEVCONTAINER_TEMPLATE_DIR / "post-create.sh").read_text()
    # Match only the command invocation, not text inside comments.
    # Every non-comment line that starts with `claude install` (optionally
    # preceded by whitespace) counts.
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("claude install"), (
            "post-create.sh must not run `claude install` (deletes npm binary; "
            "breaks PATH for subsequent `claude mcp add` calls)"
        )


def test_post_create_uses_strict_mode() -> None:
    """post-create.sh enables errexit + nounset + pipefail.

    Accepts either a single `set -euo pipefail` line OR the equivalent
    split form (`set -e`, `set -u`, `set -o pipefail`) as long as all
    three are present before the first non-set, non-comment command.
    """
    content = (DEVCONTAINER_TEMPLATE_DIR / "post-create.sh").read_text()
    has_errexit = False
    has_nounset = False
    has_pipefail = False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("#!"):
            continue
        if stripped.startswith("set "):
            # Parse flag tokens so combined -euo counts as e+u+o. Substring
            # checks like `"-u" in "set -euo pipefail"` would miss nounset
            # because the `-` only appears once, before `e`.
            tokens = stripped.split()
            flag_chars = ""
            for tok in tokens[1:]:
                if tok.startswith("-") and not tok.startswith("--") and tok != "-o":
                    flag_chars += tok[1:]
            if "e" in flag_chars or "errexit" in stripped:
                has_errexit = True
            if "u" in flag_chars or "nounset" in stripped:
                has_nounset = True
            if "pipefail" in stripped:
                has_pipefail = True
        else:
            break  # first non-set command — stop checking
    assert has_errexit, "post-create.sh must enable errexit (set -e)"
    assert has_nounset, "post-create.sh must enable nounset (set -u)"
    assert has_pipefail, "post-create.sh must enable pipefail (set -o pipefail)"


def test_publish_doc_exists() -> None:
    """docs/publish.md exists and is non-empty — PyPI publish runbook.

    Product scope item 4 (Run V): the post-create.sh `pip install mootup`
    path hard-depends on PyPI being current. The publish procedure must
    be documented, not live only on Pat's laptop.
    """
    publish_doc = Path(__file__).parent.parent / "docs" / "publish.md"
    assert publish_doc.exists(), f"Expected {publish_doc} to exist"
    content = publish_doc.read_text()
    assert len(content) > 200, (
        f"docs/publish.md too short ({len(content)} bytes) — "
        "should be a one-page runbook"
    )
    # Sanity: mentions the core tools used
    for token in ("twine", "pypi", "mootup"):
        assert token.lower() in content.lower(), (
            f"docs/publish.md should reference {token!r}"
        )
```

**Test count delta:** **+3 adds, −0 drops, 0 rewrites (in-place tighten does not count as rewrite) → net +3.** Target: **100 passed, 14 failed**.

### 7.3 Regression tests (no change)

- All existing `test_devcontainer.py` tests (Run U's rewrite) unchanged.
- All existing `test_launch.py` tests (Run U's `bash -lc` assertion) unchanged.
- All existing `test_templates.py` tests unchanged except the in-place tighten in § 7.1.

## 8. Incremental order (for Impl, mirrors Run T/U discipline)

Stage the work so each commit can be reverted in isolation:

1. **Stage 1 — version bump.** `__init__.py` + `pyproject.toml`. Run `moot --version` → `moot 0.2.2`. Run `uv sync --group test` (expect the `mootup` version bump in the lock file — do not commit lockfile per § 3).
2. **Stage 2 — post-create.sh edits.** Apply all three script changes (`set -euo pipefail`, drop `claude install`, typo fix `moot` → `mootup`) as one commit. Run `bash -n src/moot/templates/devcontainer/post-create.sh` to syntax-check.
3. **Stage 3 — test updates.** Tighten the existing `test_post_create_no_convo_paths` assertion + add the three new tests. Run `uv run pytest tests/test_templates.py -n auto` — expect 21 passed (the existing 18 + 3 new). Run full `uv run pytest` — expect 100 passed / 14 failed.
4. **Stage 4 — publish doc.** Create `docs/publish.md`. Re-run `uv run pytest tests/test_templates.py::test_publish_doc_exists` — expect pass. Run full `uv run pytest` again — expect 100 passed / 14 failed.
5. **Stage 5 — final verification.** `uv run pyright .` → 11 errors (unchanged). `moot --version` → `moot 0.2.2`. Git-request to Leader.

Do not fold stages. If any stage regresses the ship gates, stop and escalate via `message_type="question"` in the feature thread.

## 9. Open questions

None. All D-decisions are locked (D1, D2, D3 by Product; D-PIN by Spec per `feedback_spec_resolves_product_doc_silences.md`).

## 10. Risk

- **Low.** Script-only edits + three file-content tests + one new doc file. No Python source changes, no runtime behavior drift.
- **Run U interaction:** Removing `claude install` means Run U's `bash -lc` fix is no longer load-bearing for `claude` resolution — but `/usr/local/share/npm-global/bin` is on PATH in both `bash -c` and `bash -lc` under `docker exec` (§ 13 spike), so `launch.py` continues to work. No regression.
- **PyPI-dependence:** post-create.sh still fails on a stale PyPI (same as before, now visible). The publish doc addresses the operational fragility but does not eliminate it. Pat must publish 0.2.2 before new users can `moot init` → `moot up` successfully.
- **`set -u` side effects:** If any future change references an unset variable, the script will abort. Current script has zero variable references, so today's behavior is identical. Defensive hardening.

## 11. Imports / dependencies

No new Python imports, no new runtime dependencies, no new dev dependencies. `tests/test_templates.py` already imports `Path` from `pathlib` (confirmed via file read) — no new imports needed for the three new tests.

## 12. Invariants / anchor hits

Impl/QA verify each with a `grep` on the shipped file(s):

- **Q-1 (typo gone):** `grep -n 'pip install moot\b' src/moot/templates/devcontainer/post-create.sh` → **0 hits** (use the `\b` word boundary to avoid matching `pip install mootup`). `grep -n 'pip install mootup' src/moot/templates/devcontainer/post-create.sh` → **1 hit** (line 15 or wherever the pip line now is).
- **Q-2 (claude install gone):** `grep -n '^\s*claude install' src/moot/templates/devcontainer/post-create.sh` → **0 hits** (anchor on line start to exclude comments).
- **Q-3 (strict mode):** `grep -n 'set -euo pipefail' src/moot/templates/devcontainer/post-create.sh` → **1 hit** OR equivalent split form (§ 7.2 test accepts either; the grep check is the one-line form; if split form is chosen, grep each part individually).
- **Q-4 (publish doc):** `test -f docs/publish.md && echo OK` → `OK`; `wc -l docs/publish.md` → ≥ 20 and ≤ 100.
- **Q-5 (version):** `moot --version` → `moot 0.2.2`; `grep -n '0.2.2' src/moot/__init__.py pyproject.toml` → exactly 1 hit per file.
- **Q-6 (Run U invariants preserved):** `grep -c 'bash.*-lc' src/moot/launch.py` → ≥ 1 (Run U's `bash -lc` in `_launch_role` untouched); `grep -c 'dangerously-load-development-channels' src/moot/launch.py` → ≥ 2 (Run U anchor hits preserved).

## 13. Grounding (spike output verbatim)

### 13.1 D2 spike — npm-only install of claude-code

```
$ docker run --rm --user node mcr.microsoft.com/devcontainers/javascript-node:22 bash -c '
  npm install -g @anthropic-ai/claude-code >/dev/null 2>&1
  echo "which:"; which claude
  echo "ls npm:"; ls -la /usr/local/share/npm-global/bin/claude
  echo "ls local:"; ls -la /home/node/.local/bin/claude 2>&1
  echo "version:"; claude --version
  echo "mcp-add:"; claude mcp add test /bin/true -s local
  echo "mcp-list:"; claude mcp list 2>&1 | head -5
'
which: /usr/local/share/npm-global/bin/claude
ls npm: lrwxrwxrwx 1 node npm 52 Apr 16 23:17 /usr/local/share/npm-global/bin/claude -> ../lib/node_modules/@anthropic-ai/claude-code/cli.js
ls local: ls: cannot access '/home/node/.local/bin/claude': No such file or directory
version: 2.1.112 (Claude Code)
mcp-add: Added stdio MCP server test with command: /bin/true  to local config
         File modified: /home/node/.claude.json [project: /]
mcp-list: Checking MCP server health…
          test: /bin/true  - ✗ Failed to connect
```

npm alone provides a working `claude` on the default image PATH. `~/.local/bin/claude` does not exist.

### 13.2 D2 spike — `claude install` deletes the npm binary

```
$ docker run --rm --user node mcr.microsoft.com/devcontainers/javascript-node:22 bash -c '
  npm install -g @anthropic-ai/claude-code >/dev/null 2>&1
  echo "before-install-npm:"; ls /usr/local/share/npm-global/bin/claude 2>&1
  yes "" | claude install >/tmp/ci.log 2>&1
  echo "install-rc: $?"
  echo "install-log:"; tail -5 /tmp/ci.log
  echo "after-install-npm:"; ls /usr/local/share/npm-global/bin/claude 2>&1
  echo "after-install-local:"; ls /home/node/.local/bin/claude 2>&1
  echo "which:"; which claude || echo "(empty)"
  echo "version-default-path:"; claude --version 2>&1 || echo "FAILED"
'
before-install-npm: /usr/local/share/npm-global/bin/claude
install-rc: 0
install-log: ⚠ Setup notes:
             • Native installation exists but ~/.local/bin is not in your PATH. Run:
             echo 'export PATH="$HOME/.local/bin:$PATH"' >> your shell config file && source your shell config file
after-install-npm: ls: cannot access '/usr/local/share/npm-global/bin/claude': No such file or directory
after-install-local: lrwxrwxrwx 1 node node 47 Apr 16 23:19 /home/node/.local/bin/claude -> /home/node/.local/share/claude/versions/2.1.112
which: (empty)
version-default-path: bash: line 11: claude: command not found
```

`claude install` exits rc=0 but **warns explicitly** that `~/.local/bin` is not on PATH, deletes the npm symlink, and leaves the user with no `claude` on the default PATH. This reproduces Pat's live bug exactly.

### 13.3 PATH verification under `docker exec` — both `-c` and `-lc` find npm-global claude

```
$ CID=$(docker run -d --user node mcr.microsoft.com/devcontainers/javascript-node:22 sleep 120)
$ docker exec --user node "$CID" bash -c 'npm install -g @anthropic-ai/claude-code >/dev/null 2>&1'
$ docker exec --user node "$CID" bash -c 'echo PATH=$PATH; which claude; claude --version'
PATH=/usr/local/share/nvm/current/bin:/usr/local/share/npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
/usr/local/share/npm-global/bin/claude
2.1.112 (Claude Code)
$ docker exec --user node "$CID" bash -lc 'echo PATH=$PATH; which claude; claude --version'
PATH=/usr/local/share/nvm/current/bin:/usr/local/share/npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games
/usr/local/share/npm-global/bin/claude
2.1.112 (Claude Code)
```

Both `bash -c` and `bash -lc` under `docker exec` find `/usr/local/share/npm-global/bin/claude`. Confirms Option B does not regress Run U's `_launch_role` — the `bash -lc` login shell continues to resolve `claude` via the npm-global directory that's baked into the image's default PATH regardless of login-shell status.

### 13.4 PyPI release check (D-PIN input)

```
$ curl -s https://pypi.org/pypi/mootup/json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["info"]["name"], d["info"]["version"]); print(sorted(d["releases"].keys()))'
mootup 0.2.0
['0.1.0', '0.1.1', '0.1.2', '0.1.3', '0.1.4', '0.2.0']
```

PyPI's latest published `mootup` is 0.2.0. Product's conditional "pin if 0.2.x is published" is met, but Spec still resolves D-PIN = unpinned (see § 4).

### 13.5 shellcheck availability

```
$ which shellcheck
(not found)
```

Shellcheck is not installed in the spec worktree. Product marked it a nice-to-have, not a hard gate. Spec chooses: no shellcheck assertion in § 7.

## 14. Ship gates

All gates measured at `feat/post-create-fixes` tip after Impl's final commit, before QA handoff.

| Gate | Target | Current (baseline) | Formula |
|---|---|---|---|
| `uv run pytest` passed | **≥ 100** | 97 | 97 + adds (+3) − drops (0) = 100 |
| `uv run pytest` failed | **= 14** | 14 | unchanged (same named regressions as Run T/U § 2) |
| `uv run pytest` rewrites | 0 | — | in-place assertion tighten is not a rewrite |
| `uv run pyright .` errors | **= 11** | 11 | no source changes outside templates + tests |
| `moot --version` | `moot 0.2.2` | `moot 0.2.1` | bump in `__init__.py` + `pyproject.toml` |
| `docs/publish.md` exists | yes | no | new file, ≥ 20 LOC, ≤ 100 LOC |
| Q-1 / Q-2 / Q-3 / Q-4 / Q-5 / Q-6 greps | all pass | — | § 12 |

Pytest-count arithmetic, per `feedback_spec_pytest_count_formula.md` (just shipped in Run U synthesis):

> **drops: −0, rewrites: ±0, adds: +3 → net: +3 → 97 + 3 = 100 passed.**

No rewrites counted — the one assertion tighten in `test_post_create_no_convo_paths` is an in-place edit to a pre-existing test, not a rewrite in the count-moving sense. The pre-existing test continues to exist and continues to pass.

---

**End of spec.** Branch: `spec/post-create-fixes`. Ready to commit + git_request.
