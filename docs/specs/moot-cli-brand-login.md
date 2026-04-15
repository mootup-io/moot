# moot-cli brand sweep + interactive login + --version flag

**Status:** Design spec — feat/moot-cli-brand-login
**Baseline:** mootup-io/moot `feat/moot-cli-brand-login` @ `3be4d9b`
**Pipeline variant:** Standard
**Run:** Q (first cross-repo run in mootup-io/moot)
**Kickoff:** Product `evt_7zeg7e5gc2d22` (convo)

## § 1. Summary

Three concurrent mechanical changes to moot-cli:

1. **`--version` flag** on the root `moot` parser.
2. **Brand sweep** through user-facing CLI strings and README — user-visible "Convo" / "gemoot.com" → "Moot" / "mootup.io". Developer identifiers (`convo_key_`, `CONVO_API_URL`, logger names, TOML section names, template bodies) stay.
3. **`moot login` interactive mode** — `--token` becomes optional; when absent, prompt for the PAT via `getpass.getpass`. Validate the `mootup_pat_` prefix before sending to the server.

All three land in a single spec/impl/QA run. No backend changes. No new dependencies. ~120 LOC diff over 6 source files + 2 test files.

## § 2. Baseline (frozen at `3be4d9b`)

Measured from `/workspaces/convo/mootup-io/moot/.worktrees/spec` at commit `3be4d9b`.

| Gate | Count | Command |
|------|-------|---------|
| pytest passed | 68 | `uv run pytest -q` |
| pytest failed | 5 (pre-existing) | same |
| pyright errors | 17 (pre-existing) | `uv run pyright` |

**Pre-existing test failures (out of scope):** `tests/test_example.py::{test_moot_toml_valid, test_devcontainer_json_valid, test_post_create_installs_moot, test_runner_scripts_unchanged, test_gitignore_entries}` — all 5 fail because `Path(__file__).parents[N]` walks up past the worktree boundary looking for `examples/markdraft/` at `.worktrees/examples/markdraft/`. This is a pre-existing worktree-unaware pattern that this run does not touch. Ship target counts carry the 5 forward unchanged.

**Pre-existing pyright errors (out of scope):** 17 errors across `tests/test_auth.py`, `tests/test_scaffold.py`, etc. — almost all are `monkeypatch: object` parameter type annotations that block attribute-access checking on `monkeypatch.setattr` and `monkeypatch.chdir`. Fixing the annotation style is orthogonal to this run. New tests added in § 7 SHOULD avoid introducing new instances by using `pytest.MonkeyPatch` as the annotation; see § 7.5.

**Convo grep baseline** (this is the floor the sweep must reduce):

```
$ grep -rn "Convo\|convo\|gemoot" src/moot/ README.md | wc -l
~55 lines total across src/moot/ + README.md
```

The intentionally-preserved dev-facing sites (out of this sweep by design) are enumerated in § 3.2 below. The in-sweep sites are enumerated in § 6.

## § 3. Scope

### 3.1. In scope

1. `src/moot/cli.py` — module docstring, parser `description`, `login` subparser help, `--api-url` help, `--version` flag
2. `src/moot/auth.py` — default `api_url` string, `cmd_login` refactored to support optional `--token`, interactive prompt, prefix validation
3. `src/moot/__init__.py` — module docstring (the `__version__` constant already exists at `0.1.0`)
4. `src/moot/scaffold.py` — one line: default `api_url` string at line 22 (NO other changes to scaffold.py)
5. `README.md` — user-facing prose (top banner, quickstart, commands table, architecture section, footer links)
6. `pyproject.toml` — `[project].description` field
7. `tests/test_cli.py` — update `test_cli_help_text` to match new description; add `test_cli_version_flag`
8. `tests/test_auth.py` — add 4 new tests for PAT prefix validation, interactive prompt, brand regression (see § 7)

### 3.2. Out of scope (dev-facing identifiers — deliberately preserved)

Per Pat's branding rule (kickoff § "Brand sweep scope"), the following sites stay as `convo*` because they're developer-facing identifiers and changing them would break wire/config compatibility:

| File | Site | Why preserved |
|------|------|---------------|
| `src/moot/launch.py:80` | `server:convo-channel` MCP server name in claude invocation | Matches registered MCP server identifier; breaking change to end-users |
| `src/moot/id_encoding.py:3` | `"Convo uses random BIGINT primary keys..."` module docstring | Internal implementation detail; no user-visible surface |
| `src/moot/config.py:27-29` | `[convo]` TOML section name read from `moot.toml` | Wire format; breaking change to all existing `moot.toml` files |
| `src/moot/response_format.py:17` | `logging.getLogger("convo.response_format")` | Logger namespace; consumers filter on this name |
| `src/moot/team_profile.py:159` | `generate_moot_toml` emits `"[convo]"` section header | Wire format (ties to config.py above) |
| `src/moot/adapters/*` | logger names, `convo-channel` MCP server name, tmux session prefixes (`convo-{role}`), env var names (`CONVO_API_URL`, `CONVO_API_KEY`, `CONVO_TMUX_SESSION`, `CONVO_ROLE`) | All dev-facing wire/config identifiers |
| `src/moot/templates/devcontainer/*.sh` | Inline python that reads `.get('convo', {})` from TOML | Matches config.py `[convo]` section |
| `src/moot/templates/teams/*/CLAUDE.md` | Body text referring to "Convo shared context server" | **Run R scope** — per Product's "Do NOT change templates" rule; these are user-visible but owned by the templates rework |
| `src/moot/templates/teams/*/team.toml` | `origin = "Observed from Convo project's..."` metadata | **Run R scope** — template bodies |
| `src/moot/models.py:1, 14` | Module + class docstring "Convo REST API" | Internal developer docs only; cost/benefit below the bar for this run — **documented followup, not an omission** |
| `src/moot/adapters/channel_runner.py:1, 10-15` + `adapters/notify_runner.py:4-13` | `CONVO_API_URL=https://gemoot.com:8443` fallback URLs and docstrings | **Explicitly excluded** by kickoff: "Don't touch those two files." Deferred sweep. |

### 3.3. Explicit deferrals (Run R, not Run Q)

- `moot init` orchestration rework — Run R
- `.actors.json` → `.moot/actors.json` rename — Run R
- Bundled skills tree under `src/moot/templates/skills/` — Run R
- `CLAUDE.md.mootup-template` source file — Run R (authored in convo)
- Templates brand sweep — Run R (tied to templates rework)
- PAT creation UI wording change on the web (already shipped Run P)

## § 4. D-decisions

### D1. `__version__` source: import from `moot/__init__.py`

Use the existing `moot/__init__.py::__version__ = "0.1.0"` constant directly. Do NOT introduce `importlib.metadata.version("mootup")` — one extra stdlib call per CLI invocation for zero benefit, and it adds a runtime coupling to package metadata installation state (editable vs wheel install edge cases). The `__init__.py` constant is already the single source of truth.

```python
# src/moot/cli.py
from moot import __version__
...
parser.add_argument(
    "--version",
    action="version",
    version=f"%(prog)s {__version__}",
)
```

**No version bump.** `pyproject.toml` and `__init__.py` both stay at `0.1.0` for this run. Bumping to `0.1.1` is a separate release call, not a brand-sweep concern.

**Invariant:** `pyproject.toml::version` and `src/moot/__init__.py::__version__` must match. Added as a § 7 regression test.

### D2. Parser description rewrite

`"Scaffold and run Convo agent teams"` → `"Scaffold and run Moot agent teams"`

Simplest rebrand. Verbatim per kickoff.

### D3. Login subparser help: "Authenticate against mootup.io"

`"Authenticate with Convo API"` → `"Authenticate against mootup.io"`

Kickoff left the wording as spec's call between "Authenticate with Moot API" and "Authenticate against mootup.io". Picking the second because (a) it names the actual destination the user is authenticating against, (b) it's the wording that appears in `moot login` first-run guidance, giving the user a continuity of reference ("I'm authenticating against mootup.io"), and (c) avoids the tautological "Authenticate with Moot API" (the command is `moot login`, so "Moot" is redundant).

### D4. `--api-url` help: "Moot API URL"

`"Convo API URL"` → `"Moot API URL"`

One-for-one rebrand.

### D5. Default API URL: `https://mootup.io`

Both sites (`src/moot/auth.py:55` and `src/moot/scaffold.py:22`) go from `"https://gemoot.com:8443"` → `"https://mootup.io"`.

- **No port.** `mootup.io` serves on default 443. Drop `:8443`.
- **No trailing slash.** `httpx.AsyncClient(base_url=url)` and the run-time path join pattern work with or without; the existing code is trailing-slash-free. Keep it consistent.

Both files ship the same literal string. If a future refactor wants a single constant, that's a Run R concern (scaffold.py is Run R's domain).

### D6. Interactive login: `getpass.getpass` with leading guidance

```python
# src/moot/auth.py (new interactive branch in cmd_login)
if not token:
    print(
        "Create a personal access token at "
        "https://mootup.io/settings/api-keys"
    )
    import getpass
    token = getpass.getpass("Paste your token: ")
```

- **`getpass.getpass`, not `input`.** PATs are long opaque secrets; showing them on stdout is a shoulder-surfing hazard and some terminals log scrollback. The stdlib warns "Warning: Password input may be echoed" on non-TTY stdin but still reads from it — this gracefully handles `moot login <<< "mootup_pat_..."` scripted form.
- **Guidance line first, then prompt.** Single-line URL before the prompt, not interleaved. Matches the product doc § D3 example.
- **`import getpass` inside the function**, not at module level. `getpass` imports `termios` on POSIX and triggers `DeprecationWarning` noise in some CI setups; defer until actually used.
- **`if not token` check**, not `if token is None`. Catches both `--token` absent (None) and `--token ""` (user accidentally passed an empty literal). Simpler, same result.

### D7. PAT prefix validation

After token is resolved (either from `--token` or prompt), validate it starts with `mootup_pat_`. On mismatch, print a friendly two-line error and exit 1.

```python
# src/moot/auth.py
if not token.startswith("mootup_pat_"):
    print(
        "That doesn't look like a Moot personal access token.\n"
        "Tokens start with 'mootup_pat_' — did you paste an agent "
        "API key (convo_key_...) by mistake?"
    )
    raise SystemExit(1)
```

- **Prefix literal as string constant in-function.** Not hoisted to a module-level constant. One call site, one match; hoisting adds naming overhead without reuse benefit.
- **Validation happens before the HTTP call.** Fail fast — no network round-trip for a clearly-wrong token shape.
- **`raise SystemExit(1)`** matches the existing `cmd_login` error path (line 65 uses the same pattern).
- **Exit code 1.** Distinct non-zero code is not needed; argparse and other failure modes already use 1.
- **No case normalization.** PATs are case-sensitive secrets; `mootup_PAT_...` is a different (invalid) string. Strict prefix match only.

### D8. Module docstrings: user-facing strings rebranded

| File | Old | New |
|------|-----|-----|
| `src/moot/cli.py:1` | `"""moot CLI — scaffold and run Convo agent teams."""` | `"""moot CLI — scaffold and run Moot agent teams."""` |
| `src/moot/__init__.py:1` | `"""moot — CLI + MCP adapters for Convo agent teams."""` | `"""moot — CLI + MCP adapters for Moot agent teams."""` |

Package-level docstrings surface in help tooling, IDE hover, `pydoc moot`, and the wheel metadata. User-adjacent.

### D9. `pyproject.toml` description

`description = "CLI + MCP adapters for Convo agent teams"` → `description = "CLI + MCP adapters for Moot agent teams"`

This string appears on PyPI's package page and in `pip show mootup`. User-facing by PyPI definition.

### D10. README.md rewrite scope

Rewrite user-visible prose; preserve code fences that show `[convo]` config schema.

Specific edits (see § 6.5 for the full patch list):

- Line 3: `CLI and MCP adapters for [Convo](https://mootup.io)` → `CLI and MCP adapters for the [Moot](https://mootup.io) agent platform`
- Line 5: `the Convo shared context server` → `the Moot shared context server`
- Line 29: `Edit moot.toml with your Convo server URL` → `Edit moot.toml with your Moot server URL`
- Line 32: `Authenticate with your Convo server` → `Authenticate with mootup.io` (matches the login subparser help)
- Line 57: `connecting it to the Convo API` → `connecting it to the Moot API`
- Line 61: `Convo space` → `Moot space`
- Line 92: `Authenticate with a Convo server` → `Authenticate with mootup.io` (commands table)
- Line 107-112: Mermaid diagram `participant Convo as Convo Server` → `participant Moot as Moot Server`, all `Convo->>` / `->>Convo` → `Moot->>` / `->>Moot`
- Line 116: `The **MCP adapter** exposes Convo's API` → `The **MCP adapter** exposes Moot's API`
- Line 125: `[convo]` code block **preserved** — this shows the wire-format TOML schema the user pastes into `moot.toml`
- Lines 152-154: `convo_...` sample actor keys **preserved** — these match the real `convo_key_` agent identifier prefix (developer-facing)
- Line 197: `A Convo server ([mootup.io]...)` → `A Moot server ([mootup.io]...)`
- Line 206: `[Convo Platform](https://mootup.io)` → `[Moot Platform](https://mootup.io)`

### D11. Test description update

`tests/test_cli.py::test_cli_help_text` asserts `"Scaffold and run Convo agent teams" in result.stdout`. Update to `"Scaffold and run Moot agent teams"`.

### D12. Brand regression test lives in `tests/test_cli.py`

Not `tests/test_security.py` or a new file. `test_cli.py` already owns CLI help-text assertions; the brand regression fits naturally there as a sibling of `test_cli_help_text`.

```python
def test_cli_help_no_convo_branding() -> None:
    """User-facing help text does not contain 'Convo' (the old brand)."""
    result = subprocess.run(
        [sys.executable, "-m", "moot", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # Case-sensitive match on the brand word — dev identifiers like
    # 'convo_key_' are lowercase and excluded by the word boundary.
    assert "Convo" not in result.stdout, (
        f"Expected 'Convo' to be absent from --help; got:\n{result.stdout}"
    )
```

**Why case-sensitive `"Convo"` and not a regex:** the user-visible brand name is capitalized. Lowercase `convo_*` identifiers never appear in help output anyway (they're wire-format strings), so the simple substring check doesn't risk a false positive on dev identifiers. Simpler than `re.search(r'\bConvo\b', ...)`.

## § 5. Files to create / modify

| File | Action | LOC |
|------|--------|-----|
| `src/moot/cli.py` | Modify — rebrand + `--version` | ~10 |
| `src/moot/auth.py` | Modify — rebrand URL + interactive + validation | ~25 |
| `src/moot/__init__.py` | Modify — docstring only | 1 |
| `src/moot/scaffold.py` | Modify — ONE LINE (default URL) | 1 |
| `README.md` | Modify — user-facing prose | ~15 |
| `pyproject.toml` | Modify — description field | 1 |
| `tests/test_cli.py` | Modify — update assertion, add 2 tests | ~40 |
| `tests/test_auth.py` | Modify — add 4 tests | ~90 |
| `docs/specs/moot-cli-brand-login.md` | Create (this spec) | — |

## § 6. Code changes (per file)

### 6.1. `src/moot/cli.py`

```python
"""moot CLI — scaffold and run Moot agent teams."""
from __future__ import annotations

import argparse
import asyncio
import sys

from moot import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="moot",
        description="Scaffold and run Moot agent teams",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    # moot login
    login_p = sub.add_parser("login", help="Authenticate against mootup.io")
    login_p.add_argument(
        "--token",
        default=None,
        help="Personal access token (prompts interactively if omitted)",
    )
    login_p.add_argument("--api-url", default=None, help="Moot API URL")

    # ... rest of parser setup unchanged ...
```

**Changes:**
1. Line 1 docstring: `Convo` → `Moot`
2. Line 8: Add `from moot import __version__`
3. Line 12: description string rebrand
4. Lines 14-18: add `--version` argument block immediately after `parser = ...`
5. Line 17: login subparser help string rebrand
6. Line 18: `required=True` → `default=None`, help text rebranded
7. Line 19: `--api-url` help string rebrand

**`--version` placement rationale:** Before `sub = parser.add_subparsers(...)` so that `moot --version` parses before any subcommand requirement kicks in. argparse `action="version"` short-circuits — it prints and exits with code 0 regardless of what else is on the command line.

**`--token` help rewording:** The old help was just `"API key"`. The new wording explicitly covers both modes ("Personal access token (prompts interactively if omitted)"). Future-proofs the UX for users who run `moot login --help` to discover the interactive form.

### 6.2. `src/moot/auth.py`

```python
from __future__ import annotations

import os
from pathlib import Path

import httpx

CRED_DIR = Path.home() / ".moot"
CRED_FILE = CRED_DIR / "credentials"

PAT_PREFIX = "mootup_pat_"
DEFAULT_API_URL = "https://mootup.io"


def load_credential(profile: str = "default") -> dict[str, str] | None:
    # ... unchanged ...


def store_credential(
    token: str,
    api_url: str,
    user_id: str,
    profile: str = "default",
) -> None:
    # ... unchanged ...


async def cmd_login(args: object) -> None:
    """Handle `moot login [--token <pat>]`."""
    token: str | None = getattr(args, "token", None)
    api_url: str = getattr(args, "api_url", None) or DEFAULT_API_URL

    if not token:
        print(
            "Create a personal access token at "
            "https://mootup.io/settings/api-keys"
        )
        import getpass
        token = getpass.getpass("Paste your token: ")

    if not token.startswith(PAT_PREFIX):
        print(
            "That doesn't look like a Moot personal access token.\n"
            "Tokens start with 'mootup_pat_' — did you paste an agent "
            "API key (convo_key_...) by mistake?"
        )
        raise SystemExit(1)

    async with httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    ) as client:
        resp = await client.get("/api/actors/me")
        if resp.status_code != 200:
            print(f"Error: authentication failed ({resp.status_code})")
            raise SystemExit(1)
        actor = resp.json()

    user_id = actor["actor_id"]
    name = actor["display_name"]
    store_credential(token=token, api_url=api_url, user_id=user_id)
    print(f"Authenticated as {name} ({user_id}) on {api_url}")
```

**Changes:**
1. Add `PAT_PREFIX = "mootup_pat_"` module constant (one use site, but exported for test reuse)
2. Add `DEFAULT_API_URL = "https://mootup.io"` module constant (replaces inline literal)
3. `cmd_login`: `token` is now `str | None` (was `str`)
4. `api_url` uses `DEFAULT_API_URL` constant, not inline literal
5. Add interactive branch: if `not token`, print guidance + `getpass.getpass`
6. Add prefix validation: if not prefixed, print error + `raise SystemExit(1)`
7. Docstring updated: `"""Handle \`moot login [--token <pat>]\`."""`

**No signature change to `store_credential` or `load_credential`.** D3 (`~/.moot/credentials` TOML format) already shipped per the existing `auth.py` code — confirmed by reading lines 22-49.

**`getattr(args, "token", None)`** (with the default fallback) instead of plain `getattr(args, "token")` to gracefully handle the case where the login subparser wasn't even hit (defensive — shouldn't happen in practice, but avoids an AttributeError from surfacing in an unexpected code path).

### 6.3. `src/moot/__init__.py`

```python
"""moot — CLI + MCP adapters for Moot agent teams."""
__version__ = "0.1.0"
```

One-character intent: rebrand the module docstring. `__version__` stays at `0.1.0`.

### 6.4. `src/moot/scaffold.py`

```python
    api_url = getattr(args, "api_url", None) or "https://mootup.io"
```

Line 22 only. Nothing else in scaffold.py changes.

### 6.5. `README.md`

See § D10 for the line-by-line patch list. Code blocks showing `[convo]` TOML sections and `convo_...` sample actor keys are **preserved** — those are the wire-format contents the user pastes.

### 6.6. `pyproject.toml`

```toml
description = "CLI + MCP adapters for Moot agent teams"
```

Line 4 only.

## § 7. Test plan

### 7.1. Required tests (Impl gate — must be green before handoff)

#### T1. `tests/test_cli.py::test_cli_help_text` (UPDATE)

Change the asserted substring from `"Scaffold and run Convo agent teams"` to `"Scaffold and run Moot agent teams"`.

#### T2. `tests/test_cli.py::test_cli_version_flag` (NEW)

```python
def test_cli_version_flag() -> None:
    """moot --version prints 'mootup 0.1.0' and exits 0."""
    from moot import __version__
    result = subprocess.run(
        [sys.executable, "-m", "moot", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # argparse writes `%(prog)s <version>` — prog is "moot".
    assert f"moot {__version__}" in result.stdout
```

**Why `in` not `==`:** argparse tacks on a trailing newline, and on some platforms writes version output to stdout vs stderr inconsistently; substring match is resilient to both.

**Why import `__version__` in the test:** keeps the test self-updating when the version bumps. A hardcoded `"0.1.0"` in the test would go stale on every release.

#### T3. `tests/test_cli.py::test_cli_help_no_convo_branding` (NEW)

See § D12 for the body.

#### T4. `tests/test_cli.py::test_version_consistency` (NEW — D1 invariant)

```python
def test_version_consistency() -> None:
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

**Why:** argparse `--version` reads from `__version__`; users run `pip show mootup` which reads `pyproject.toml`. If the two drift, one of the two surfaces is wrong. A one-line invariant test catches the drift at CI time.

**`Path(__file__).parent.parent`** — `tests/test_cli.py` is one directory below the repo root; `.parent.parent` resolves to the repo root where `pyproject.toml` lives. This is **not** susceptible to the `.worktrees/examples/markdraft/` walking bug that test_example.py hits (that bug uses `.parents[N]` with N walking past the worktree boundary; `.parent.parent` stays inside the worktree).

#### T5. `tests/test_auth.py::test_login_rejects_non_pat_prefix` (NEW)

```python
def test_login_rejects_non_pat_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """moot login --token convo_key_xxx exits 1 with a friendly error."""
    import argparse
    import asyncio
    from moot.auth import cmd_login

    args = argparse.Namespace(token="convo_key_fake_12345", api_url=None)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(cmd_login(args))
    assert exc_info.value.code == 1
```

**No respx mock needed** — validation fails before any HTTP call, so no network is made.

**`pytest.MonkeyPatch` annotation** — avoids introducing a new `monkeypatch: object` site (see § 2 pyright note).

#### T6. `tests/test_auth.py::test_login_rejects_empty_token` (NEW)

```python
def test_login_rejects_empty_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """moot login with empty interactive input exits 1 (falls through to prefix check)."""
    import argparse
    import asyncio
    import getpass
    from moot.auth import cmd_login

    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "")

    args = argparse.Namespace(token=None, api_url=None)

    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(cmd_login(args))
    assert exc_info.value.code == 1
```

**Why this test matters:** An empty string passes the `not token` check into the interactive branch, receives an empty response, then hits the prefix validation and bails. Confirms there's no path where an empty token reaches the HTTP call.

#### T7. `tests/test_auth.py::test_login_interactive_prompt_accepts_valid_pat` (NEW)

```python
def test_login_interactive_prompt_accepts_valid_pat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """moot login (no --token) prompts via getpass, validates prefix, calls API."""
    import argparse
    import asyncio
    import getpass
    import respx
    import moot.auth as auth_mod

    # Redirect cred file to tmp
    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    # Inject fake getpass response
    fake_token = "mootup_pat_" + "a" * 32
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": fake_token)

    args = argparse.Namespace(token=None, api_url="https://mootup.io")

    with respx.mock(base_url="https://mootup.io") as mock:
        mock.get("/api/actors/me").respond(
            200,
            json={"actor_id": "usr_test", "display_name": "Test User"},
        )
        asyncio.run(cmd_login(args))

    assert cred_file.exists()
    content = cred_file.read_text()
    assert fake_token in content
```

**`respx.mock` is already a dep** (per `pyproject.toml [dependency-groups] test`). Pattern matches existing `tests/test_auth.py` fixtures that use `monkeypatch.setattr(auth_mod, "CRED_DIR", ...)`.

#### T8. `tests/test_auth.py::test_login_token_flag_bypasses_prompt` (NEW)

```python
def test_login_token_flag_bypasses_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """moot login --token mootup_pat_... skips the interactive prompt."""
    import argparse
    import asyncio
    import getpass
    import respx
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)

    # getpass should NOT be called — make it raise if it is
    def boom(prompt: str = "") -> str:
        raise AssertionError("getpass.getpass should not be called in --token mode")
    monkeypatch.setattr(getpass, "getpass", boom)

    fake_token = "mootup_pat_" + "b" * 32
    args = argparse.Namespace(token=fake_token, api_url="https://mootup.io")

    with respx.mock(base_url="https://mootup.io") as mock:
        mock.get("/api/actors/me").respond(
            200,
            json={"actor_id": "usr_bypass", "display_name": "Bypass User"},
        )
        asyncio.run(cmd_login(args))

    assert cred_file.exists()
```

**Why the boom getpass:** gives a readable failure message if a refactor accidentally routes `--token` mode through the prompt. Cheap regression guard.

### 7.2. Suggested additional coverage (QA discretion)

- **T-sweep-1:** grep-based scan of `src/moot/cli.py`, `src/moot/auth.py`, `src/moot/__init__.py`, `src/moot/scaffold.py`, `pyproject.toml`, `README.md` for the case-sensitive substring `Convo` — asserting an allowlist of preserved sites (code fences, `convo_...` sample strings). QA call on whether this is worth the maintenance cost of an allowlist; the `--help` regression test in T3 covers the behavioral surface.
- **T-sweep-2:** confirm `moot login --help` does not contain `Convo`. Folds into T3's scan if QA generalizes it across subcommand help outputs.
- **T-url-1:** assert `DEFAULT_API_URL` constant equals `"https://mootup.io"` (compile-time regression on the literal itself).
- **T-scaffold-1:** `tests/test_scaffold.py` — existing tests may reference the old `gemoot.com` default URL. Run `grep gemoot tests/` — if present, QA updates the literal. Spec has not read every test; this is a QA judgment.

### 7.3. Expected gate targets

| Gate | Baseline | Target |
|------|----------|--------|
| pytest passed | 68 | 73 (+5 = T2, T3, T4, T5, T6, T7, T8 new − T1 is an update not a new test = +6 new; check) |
| pytest failed | 5 (pre-existing) | 5 (unchanged) |
| pyright errors | 17 (pre-existing) | 17 (unchanged; new tests use `pytest.MonkeyPatch` annotation) |

Let me recount the new-test delta:
- T1 updates `test_cli_help_text` (already counted in 68)
- T2, T3, T4 are new in `test_cli.py` (+3)
- T5, T6, T7, T8 are new in `test_auth.py` (+4)
- **Total new:** 7

**Target: 75 passed, 5 failed, 17 pyright errors.**

If QA adds T-sweep-1 / T-sweep-2 / T-url-1 / T-scaffold-1, target floats up accordingly.

### 7.4. Impl gate: verify `moot --version` end-to-end

Before handoff, Impl must run the installed CLI form:

```bash
cd /workspaces/convo/mootup-io/moot/.worktrees/implementation
uv run moot --version
# Expected: moot 0.1.0
```

**Why the end-to-end check:** `argparse action="version"` semantics are slightly subtle (it writes to stdout on Python 3.4+ but stderr on older versions, and interacts with subparser parsing order). Running the actual CLI once catches any surprise before QA.

### 7.5. Annotation note for new tests

Use `pytest.MonkeyPatch` as the parameter annotation, not `object`:

```python
import pytest

def test_foo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(...)  # works without type: ignore
```

The existing `object` annotations in `test_auth.py` line 9 etc. are why pyright reports 17 errors at baseline. New tests must not add to that count — use `pytest.MonkeyPatch`.

## § 8. Security considerations

### 8.1. Auth boundaries

- **No new authenticated endpoints.** All changes are client-side on moot-cli. The `/api/actors/me` endpoint the login flow calls already exists and already accepts PAT bearer tokens (shipped Run P).
- **Bearer header construction is unchanged.** `Authorization: Bearer <token>` with the user-supplied PAT. No auth logic in moot-cli — the token is opaque to it.

### 8.2. Input validation

- **PAT prefix validation is defense-in-depth, not a security boundary.** The backend is the authoritative validator. Client-side prefix check protects the user from accidentally sending an agent API key to a server that would either reject it (best case) or accept it if the server supports both formats on that endpoint (second-best case — but the mootup.io backend does not).
- **No regex, no ReDoS risk.** Plain `str.startswith` — constant time in the prefix length.

### 8.3. Secret handling

- **`getpass.getpass` for interactive input.** Prevents terminal echo; avoids leaking the PAT into shell scrollback or process lists (no `argv` exposure since the token is never on the command line in interactive mode).
- **File permissions unchanged.** `store_credential` already does `os.chmod(CRED_FILE, 0o600)` at line 49 of existing `auth.py`. No change needed — already correct.
- **Credential file parent directory is `~/.moot/`.** Created with `mkdir(parents=True, exist_ok=True)` which inherits the umask. **Not a regression introduced by this run**, but worth noting for future tightening: the parent dir is not explicitly chmod 700. Product doc D3 says chmod 700 on `.moot/`. This is a pre-existing gap, left for Run R's `moot init` rework (which is the one creating `.moot/` in the repo-local case).
- **No PAT logging.** The success message prints the user's display name and actor_id but not the token. The error path (authentication failed) prints only the HTTP status code. Confirmed by reading existing `cmd_login` flow.

### 8.4. XSS / injection surface

- **None.** moot-cli is a command-line tool; no HTML rendering, no shell interpolation of user input, no eval. The PAT is passed as a header value to httpx which handles the quoting.

### 8.5. Tenant isolation

- **N/A.** Client-side tool; tenant isolation is the backend's concern.

### 8.6. Brand sweep does not widen attack surface

- No new endpoints, no new headers, no new URL schemes. The only URL change (`gemoot.com:8443` → `mootup.io`) is a default value, still overridable via `--api-url` or a saved credential profile. Users pointing at staging / self-hosted instances are unaffected.

## § 9. Open questions

None. All decisions resolved in-draft per `feedback_spec_resolves_product_doc_silences.md`.

**D-notes where the kickoff left spec discretion:**
- D1 (`__version__` source): picked `from moot import __version__` over `importlib.metadata`
- D3 (login help wording): picked "Authenticate against mootup.io"
- D6 (interactive): picked `getpass.getpass`, function-local import
- D7 (prefix validation): chose `if not token.startswith(PAT_PREFIX)` over regex

Each is documented above with reasoning. None rises to the level of "Spec needs Product input."

## § 10. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `--version` flag conflicts with a subparser having its own `--version` | Low | None of the existing subparsers define `--version`; added at root-parser level before `sub.add_subparsers`, so argparse's "version action short-circuits" semantics apply cleanly |
| Changing default `api_url` breaks existing saved credentials | None | Saved credentials in `~/.moot/credentials` store the `api_url` explicitly; the default is only consulted when neither `--api-url` nor a stored profile exist. Existing users are unaffected. |
| `getpass.getpass` behavior on non-TTY stdin | Low | Stdlib handles this by printing a warning and reading from stdin; scripted usage like `echo $TOKEN \| moot login` still works |
| Pre-existing test_example.py failures mask new failures | Low | Target counts explicitly include the 5 pre-existing failures; Impl/QA know to check "+0 new failures" not "0 total failures" |
| README line-number drift during Impl edits | None | Per `feedback_spec_line_refs.md`, this spec references prose content by substring, not line number. The D10 table uses line numbers as a reading aid but the authoritative match is the "old string" column. |
| Pyright new errors from new test code | Low | § 7.5 prescribes `pytest.MonkeyPatch` annotation for all new test functions; pre-existing `object` sites are out of scope |

## § 11. Missing-imports audit

Per `feedback_missing_imports_audit_in_spec_11.md`, every new symbol in § 6 code snippets:

| Symbol | File | Import needed | Status |
|--------|------|---------------|--------|
| `__version__` | `src/moot/cli.py` | `from moot import __version__` | **NEW** — add to cli.py imports |
| `getpass` | `src/moot/auth.py` | `import getpass` | **NEW** — function-local inside `cmd_login` (per D6) |
| `PAT_PREFIX` | `src/moot/auth.py` | — | Module-level constant defined in same file |
| `DEFAULT_API_URL` | `src/moot/auth.py` | — | Module-level constant defined in same file |
| `pytest` | `tests/test_auth.py` | `import pytest` | **NEW** — add to test file imports for `pytest.MonkeyPatch` + `pytest.raises` |
| `pytest` | `tests/test_cli.py` | (not needed) | existing file uses plain `assert` + `subprocess`; T2/T3/T4 don't need pytest.raises |
| `respx` | `tests/test_auth.py` | `import respx` | **NEW** — T7, T8 need it (already a test dep in pyproject.toml) |
| `tomllib` | `tests/test_cli.py` | `import tomllib` | **NEW** — T4 needs it (stdlib on Python ≥3.11, already the pyproject target) |
| `argparse` | `tests/test_auth.py` | `import argparse` | **NEW** — T5, T6, T7, T8 need `argparse.Namespace` |
| `asyncio` | `tests/test_auth.py` | `import asyncio` | **NEW** — T5, T6, T7, T8 need `asyncio.run` |
| `Path` | `tests/test_cli.py` | `from pathlib import Path` | **NEW** — T4 needs it |

**Impl gate:** every import above must be at the top of the target file (or function-local where noted). Grep `^import <sym>` / `^from .* import <sym>` in each target file and add missing lines before implementation.

## § 12. Cross-references

- Product kickoff: `evt_7zeg7e5gc2d22` in convo space
- Operational kickoff: `evt_6r80hbbcwpqr0` in convo space
- Product doc: `docs/product/local-installation.md` (in convo, not mootup-io/moot) — §§ D1, D2, D3 define the PAT primitive and login flow
- Related product doc: `docs/product/moot-init.md` (in convo) — Run R scope, context for why Run Q is surgical
- Convo repo feature that shipped the backend PAT primitive: Run P (Phase 9.6, `dc1589d`)
- moot-cli existing login implementation: `src/moot/auth.py::cmd_login` (rewritten by this spec)

## § 13. Grounding notes (pre-§5 commands)

Per `feedback_execute_commands_in_spec_review.md` and `feedback_grep_before_flagging_questions.md`, the commands below were executed against `3be4d9b` before any D-decisions were finalized.

### 13.1. Commands run

```bash
# Repo state
cd /workspaces/convo/mootup-io/moot/.worktrees/spec
git log --oneline -5
# → 3be4d9b gitignore: add .worktrees/, build artifacts, local env files [tip]

# Source tree inventory
ls src/moot/
# → adapters, auth.py, cli.py, config.py, id_encoding.py, launch.py, lifecycle.py,
#   models.py, provision.py, response_format.py, scaffold.py, team_profile.py, templates,
#   __init__.py, __main__.py

# Full brand sweep grep
grep -rn "Convo\|convo\|gemoot" src/moot/ README.md
# → ~55 hits, enumerated in § 3.2

# Existing login implementation
cat src/moot/auth.py
# → 72 lines; cmd_login has --token as positional required; store_credential
#   already writes ~/.moot/credentials with chmod 600 (D3 shipped)

# Existing CLI parser
cat src/moot/cli.py
# → 97 lines; no --version, login has required=True on --token, description
#   says "Convo", login help says "Convo API"

# __version__ location
cat src/moot/__init__.py
# → """moot — CLI + MCP adapters for Convo agent teams."""
#   __version__ = "0.1.0"

# pyproject.toml
cat pyproject.toml
# → version = "0.1.0", description = "CLI + MCP adapters for Convo agent teams"
#   test deps include pytest-asyncio, respx

# Test inventory
ls tests/
# → test_adapters/, test_auth.py, test_cli.py, test_config.py, test_example.py,
#   test_models.py, test_package.py, test_provision.py, test_response_format.py,
#   test_scaffold.py, test_security.py, test_templates.py

# Baseline pytest
uv run pytest -q
# → 5 failed, 68 passed in 1.65s
# → 5 failures all in test_example.py (pre-existing worktree path bug)

# Baseline pyright
uv run pyright
# → 17 errors, 0 warnings, 0 informations
# → All in tests/ — `monkeypatch: object` annotation mask
```

### 13.2. Key findings

1. **D3 is already shipped.** `src/moot/auth.py::store_credential` already writes TOML to `~/.moot/credentials` with chmod 600. Product doc says "D3 already shipped per the existing auth.py reading" — confirmed. No change needed to storage code.
2. **`__version__` already exists.** Kickoff said "write that constant if it doesn't exist" — grounding finds it already at `src/moot/__init__.py:2`. Saves creating it; D1 consumes the existing constant.
3. **`required=True` on `--token` is the hard block.** Making the flag optional is a one-character change (`required=True` → `default=None`) plus refactored `cmd_login` body.
4. **test_example.py baseline failures are a known worktree-path bug**, not a regression. § 2 calls them out to prevent QA false alarms.
5. **Pyright's 17 errors are 100% `monkeypatch: object` annotation hygiene.** None are real bugs. New tests must use `pytest.MonkeyPatch` annotation to avoid adding to the count (§ 7.5).
6. **pytest-asyncio auto mode** is configured in `pyproject.toml::[tool.pytest.ini_options]::asyncio_mode = "auto"`. Async tests (T5, T6, T7, T8 use `asyncio.run` instead of an async test function — simpler, no fixture interaction required).
7. **respx is already a test dep.** T7 and T8 can use it without adding dependencies.
8. **No docs/ directory exists in mootup-io/moot.** This spec creates `docs/specs/moot-cli-brand-login.md` — the first spec in a new directory. A `docs/specs/README.md` index is not in scope for Run Q; Librarian can add one when a second spec lands.
9. **scaffold.py is one line of brand sweep.** The kickoff's explicit call-out of `scaffold.py:22` is the ONLY site in scaffold.py this run touches — everything else in scaffold.py is Run R's init rework scope. D5 / § 6.4 confine the change to that single line.
10. **channel_runner.py + notify_runner.py are hard-excluded** by the kickoff. Confirmed via grep — their `CONVO_API_URL` references are in the out-of-scope set.

### 13.3. Grounding-time question resolved in draft

**"Should the spec include the templates brand sweep?"** No — kickoff's Scope (out) rules it Run R scope. The `src/moot/templates/teams/*/CLAUDE.md` files contain user-visible "Convo shared context server" references that WILL need rebranding, but those land when Run R rewrites the templates anyway. Touching them in Run Q would double the edit surface and overlap with Run R's rewrites. Resolved as "out of scope, documented followup."

## § 14. Handoff

Spec complete. Ready to commit `spec/moot-cli-brand-login` and request merge to `feat/moot-cli-brand-login`.

**Impl notes:**
- § 6 has drop-in-ready code blocks for all 4 source files + pyproject.toml
- § 7 has 7 new tests with full bodies (T2–T8)
- § 11 has the full missing-imports audit — grep before adding
- Expected gates: 75 passed, 5 failed (pre-existing), 17 pyright errors (pre-existing) at feat tip
- Use `pytest.MonkeyPatch` annotation on all new test functions (§ 7.5)

**QA notes:**
- Baseline is mootup-io/moot, not convo — all commands run from `/workspaces/convo/mootup-io/moot/.worktrees/qa/`
- Test runner: `uv run pytest -q` (no pytest-xdist — small suite, serial is fine)
- Pyright: `uv run pyright` from worktree root
- Brand sweep verification: `grep -rn "Convo\|gemoot" src/moot/ README.md` — compare against § 3.2 allowlist
- End-to-end version check: `uv run moot --version` → should print `moot 0.1.0`
- End-to-end login prefix check: `uv run moot login --token convo_key_fake` → should exit 1 with friendly message
