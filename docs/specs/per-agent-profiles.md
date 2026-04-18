# per-agent-profiles

**Status:** Design spec
**Author:** Spec
**Run:** AC (2026-04-18)
**Repo:** `mootup-io/moot`
**Feat branch:** `feat/per-agent-profiles` from `main` @ `31f7ade`
**Product scope:** `docs/product/per-agent-profiles.md` (Pat-resolved 2026-04-18)

## 1. Summary

Extend the `team.toml` → `moot.toml` → launcher schema with four per-role keys — `harness`, `model`, `effort`, `theme` — so operators can run a heterogeneous team (e.g. Leader/QA/Librarian on Sonnet while Product/Spec/Implementation stay on Opus). Per-role `harness` already exists at the template layer (`RoleProfile.harness`) but is collapsed to a global `[harness].type` in `moot.toml`; this run completes the plumbing so all four keys round-trip through the generator, config loader, validator, and launcher.

The feature is additive: a `moot.toml` that omits the new keys continues to boot a team correctly (defaults applied silently). Validation rejects unknown harness / model / effort values at `moot init` / `moot up` time with a helpful error (D4 from Product).

Standard pipeline. Six D-decisions from Product (D1-D6, all resolved 2026-04-18) plus ~11 D-* silences resolved in-draft below.

## 2. Baseline (cross-repo first run — remeasured at feat-tip `31f7ade`)

Empty-diff shortcut does NOT apply (first Run AC measure in `mootup-io/moot`). Remeasured from scratch in `/workspaces/convo/mootup-io/moot/.worktrees/spec/`:

```
$ uv run pytest tests/
119 passed, 1 skipped in 1.79s

Skipped: tests/test_templates.py::test_claude_template_matches_convo
  (CONVO_REPO_PATH not set — cross-repo parity check skipped in this worktree;
   not a regression)

$ uv run pyright src/moot/
11 errors, 0 warnings, 0 informations

Pre-existing errors (all in src/moot/adapters/mcp_adapter.py, NOT touched by this run):
  mcp_adapter.py:249  — 10 errors on httpx `.request()` kwargs (object-typed)
  mcp_adapter.py:1113 — 1 error on `_parse_duration(str | None)`
```

BASELINE-FROZEN: 119 passed, 1 skipped, 11 pyright (mcp_adapter.py). Target after this run: **119 + N adds passed, 1 skipped, 11 pyright (unchanged)**. N is derived in § 8.

Cross-repo test command: `uv run pytest` (no `-n auto` — `pytest-xdist` is not installed in `mootup-io/moot`). Confirmed: `mootup-io/moot/pyproject.toml` dev-group has no `pytest-xdist` dep.

## 3. Scope

### In scope

- Extend `RoleProfile` (and `team.toml` parser) with `model`, `effort`, `theme` fields (`harness` is already there).
- Extend `generate_moot_toml` so each `[agents.<role>]` block in the generated `moot.toml` emits the four keys when the `RoleProfile` has them set. Keys absent from the profile are NOT emitted (keeps generated files tidy and preserves "absence = use default" semantics at load time).
- Extend `AgentConfig` (the runtime per-role object read from `moot.toml`) with matching fields plus validation; unknown enum values raise `SystemExit(1)` with a pointer to valid values.
- Extend `MootConfig` global defaults: harness/model/effort read from `[harness]` (existing global) cascade into roles that don't set their own, matching today's behavior for `harness` and extending it to the new keys.
- Extend `_launch_role` in `launch.py` to:
  1. Read per-role `harness`, `model`, `effort`, `theme` from `AgentConfig`, falling back to the global defaults.
  2. For `harness == "claude-code"`, append `--model <model>` (when set) and `--effort <effort>` (when set) to the inline `claude` command. Non-set keys produce no flag, letting Claude Code's own defaults apply.
  3. After `tmux new-session`, chain `tmux set-option -t <session> pane-border-status top` and `tmux set-option -t <session> pane-border-style fg=<theme>` so operators see per-role color when they `moot attach <role>`. Skipped when `theme` is unset.
- Bake the D1 defaults (Product=Opus, Leader=Sonnet, Spec=Opus, Implementation=Opus, QA=Sonnet, Librarian=Sonnet) into all 5 bundled team templates under `src/moot/templates/teams/*/team.toml`. Per-role `theme` defaults baked into the same files: product=blue, leader=yellow, spec=magenta, implementation=cyan, qa=green, librarian=white. Effort defaults omitted in templates (Claude Code's own defaults apply).
- Extend `_write_moot_toml_from_adopted` in `scaffold.py` so the `RoleProfile` list it constructs during adoption also carries the D1 defaults keyed off role name, so operators running `moot init` get the same team defaults they'd get from a bundled template.
- Documentation: update the `src/moot/templates/teams/*/README.md` to mention the new fields and the model-assignment table. (One line per template, cross-referencing the schema.)
- Tests per § 7.

### Out of scope

- Web UI for editing profiles.
- Per-conversation profile overrides.
- Per-role skill subsetting (separate refactor; tracked elsewhere).
- Per-tenant or per-space templates.
- Full Cursor / Aider feature parity. Only `claude-code` is plumbed in `_launch_role`; `cursor` / `aider` remain as they are today (the existing dispatch already errors with "harness not yet supported" — unchanged by this run).
- Bundled theme packs (border + status line + active-pane + colors). D5 says simple per-role color only.

## 4. Design decisions

### From Product (all resolved 2026-04-18)

| ID | Decision |
|---|---|
| D1 | Per-role defaults: Product=Opus, Leader=Sonnet, Spec=Opus, Implementation=Opus, QA=Sonnet, Librarian=Sonnet. |
| D2 | Effort vocabulary follows Claude Code's CLI exactly — Spec confirms in § 13. |
| D3 | Defaults-only. No interactive prompt at init. |
| D4 | Invalid harness / model / effort values at load time → noisy failure (exit 1 with pointer). |
| D5 | Simple per-role color via tmux pane-border-style. Full theme bundle deferred. |
| D6 | Bake defaults into bundled templates; `moot.toml` overrides per-team. |

### Resolved in-draft (D-* silences)

| ID | Decision | Rationale |
|---|---|---|
| D-SCHEMA-KEY-LOCATION | New keys go **per-role** in `[[roles]]` (template) and `[agents.<role>]` (generated). No new top-level section. | Matches existing `harness` key placement; minimal schema churn. |
| D-NO-SCHEMA-VERSION | No `schema_version` key added to `moot.toml`. Absence = defaults apply silently. | Product scope § In-scope mandates silent migration; an explicit version bump would force a user-visible action that Product didn't ask for. Product doc § D4 mentioned `version = 2` in passing but scope body contradicts it ("defaults apply silently (no rotation needed)") — strongest-specific-wins → no version key. |
| D-HARNESS-ALLOWLIST | `{"claude-code", "cursor", "aider"}`. | The three values already referenced in codebase and scope. `cursor` / `aider` still error at launch (unchanged); allowlist just rejects obvious typos. |
| D-MODEL-ALLOWLIST | Validation regex: `^(opus\|sonnet\|haiku\|best\|default\|opusplan\|sonnet\[1m\]\|opus\[1m\]\|claude-[a-z0-9-]+)$`. | Per Claude Code CLI docs (verified § 13 Phase B): accepts short aliases AND full IDs like `claude-opus-4-7`. Allow both. Obvious typos (`"sonet"`, `"opsu"`) rejected; evolving model IDs (`claude-sonnet-4-7` in future) accepted via the `claude-*` passthrough. |
| D-EFFORT-ALLOWLIST | `{"low", "medium", "high", "xhigh", "max"}`. | Union of Claude Code's per-model-family effort strings (verified § 13 Phase B). `xhigh` is Opus 4.7-only; `max` is universal. Claude Code validates model-family compatibility at runtime, so our allowlist is a typo filter not an exact model-family check. |
| D-DEFAULT-EFFORT | No default in bundled templates (field omitted). Missing `effort` → no `--effort` flag emitted → Claude Code's account default applies. | Claude Code's per-model-family default (e.g., `xhigh` on Opus 4.7) is already correct. Setting `medium` globally would regress from Claude Code's sensible default. |
| D-THEME-COLOR-MAP | Per-role default colors (bundled template): product=blue, leader=yellow, spec=magenta, implementation=cyan, qa=green, librarian=white. | Standard tmux color names. Distinct at a glance. Librarian=white (dim / backdrop color for the observer). |
| D-THEME-TMUX-MECHANISM | After `tmux new-session`, chain two `tmux set-option -t <session>` calls: `pane-border-status top` + `pane-border-style fg=<color>`. | `pane-border-style` alone is invisible in single-pane sessions; turning on `pane-border-status top` makes the colored border show even with one pane. Keeps the feature operator-visible without a full status-line rewrite. |
| D-THEME-PASSTHROUGH | Theme string is passed verbatim to tmux's `fg=` argument — no Python-side color allowlist. Tmux validates (unknown color → tmux warning, session still launches). | Tmux supports 256-color names, hex codes (`"#ff00aa"`), and named colors. Allowlisting Python-side would force a maintenance burden for every new color operators want. Tmux's own rejection is acceptable UX for a cosmetic field. |
| D-CROSS-HARNESS-MODEL-EFFORT | `model` and `effort` only wired for `harness == "claude-code"` in `_launch_role`. `cursor` / `aider` ignore them (dispatch errors before reading). | Keeps scope honest with Product's "claude-code fully supported this run" stipulation. When `cursor` / `aider` dispatch lands, that run extends the switch branches. |
| D-VALIDATION-SITE | Validation runs in `AgentConfig.__init__` at `moot.toml` load time (i.e., at `moot init`, `moot up`, `moot exec`, `moot config show`) — any CLI entry point that calls `find_config()`. Not deferred to `_launch_role`. | Noisy failure at init time (D4) requires early validation. `find_config()` is the one chokepoint. |
| D-MIGRATION-SILENT | A v1 `moot.toml` without any of the four keys loads cleanly, falling back through: per-role → global `[harness]` → hardcoded defaults (`harness="claude-code"`, `model=None`, `effort=None`, `theme=None`). | Product § In-scope: "existing moot.toml files that lack the new keys continue to work (defaults apply silently; no rotation required)." |
| D-WRAPPER-SCRIPTS-UNCHANGED | No edits to `run-moot-mcp.sh`, `run-moot-channel.sh`, `run-moot-notify.sh`. | Product scope mentions these but grep confirms they read only `CONVO_ROLE` and actors.json. The four new keys flow through `launch.py` → `claude` CLI flags / tmux options, not through the MCP wrapper scripts. F-finding candidate noted. |
| D-DISPLAY-NAME-FALLBACK | When `scaffold._write_moot_toml_from_adopted` adopts from the default-space keyless flow, map `display_name.lower()` → D1 defaults (e.g., `"Product"` → opus, `"Leader"` → sonnet). Unknown role names → omit model/effort/theme from the emitted toml. | Keeps `moot init` yielding sensible defaults even on the adopt-fresh path. Unknown names fall through to Claude Code's own default model, which is still a working (if non-heterogeneous) team. |

## 5. Files to create/modify

| # | Path | Action | Scope |
|---|---|---|---|
| 1 | `src/moot/team_profile.py` | Modify | `RoleProfile` gains 3 fields; `from_toml` parses them; `generate_moot_toml` emits per-role `harness`/`model`/`effort`/`theme` when set. |
| 2 | `src/moot/config.py` | Modify | `AgentConfig` gains 4 fields + validation; `MootConfig` cascades globals. |
| 3 | `src/moot/launch.py` | Modify | `_launch_role` reads per-role keys; appends `--model`/`--effort` to `claude_cmd` when harness=claude-code; chains `tmux set-option` for theme. |
| 4 | `src/moot/scaffold.py` | Modify | `_write_moot_toml_from_adopted` applies D1 per-role defaults via `_role_defaults(display_name)` helper. |
| 5-9 | `src/moot/templates/teams/{loop-3,loop-4,loop-4-observer,loop-4-parallel,loop-4-split-leader}/team.toml` | Modify | Add `model`/`theme` to each `[[roles]]` block per D1 + D-THEME-COLOR-MAP. |
| 10 | `tests/test_templates.py` | Modify | New test class for per-role model/effort/theme parse + generation; extend existing `test_generate_moot_toml_from_loop4` with model assertion. |
| 11 | `tests/test_launch.py` | Modify | Extend `test_cmd_exec_launch_full_flow` to assert `--model`, `--effort`, and `pane-border-style` appear in the bash script when configured; new test `test_cmd_exec_launch_no_flags_when_unset`. |
| 12 | `tests/test_config.py` | Modify | New tests: per-role model/effort/harness/theme round-trip, global cascade, invalid value → SystemExit, migration (no keys → defaults). |

Estimated diff: ~180-220 LOC across source (10-15 LOC team_profile, 40-60 LOC config, 25-40 LOC launch, 15-25 LOC scaffold, 5×~20 LOC team.toml = 100 LOC template). Tests ~100-150 LOC. Total estimate: ~280-370 LOC.

## 6. Paste-and-go source

### 6.1 `src/moot/team_profile.py` — extend `RoleProfile` + parser + generator

**Add to `RoleProfile` dataclass** (after `harness: str = "claude-code"`):

```python
    model: str | None = None
    effort: str | None = None
    theme: str | None = None
```

**In `TeamProfile.from_toml`, extend the role-parse loop:**

```python
        # Parse roles (TOML array of tables)
        for role_data in data.get("roles", []):
            profile.roles.append(RoleProfile(
                name=role_data["name"],
                display_name=role_data.get("display_name", role_data["name"].title()),
                harness=role_data.get("harness", "claude-code"),
                responsibilities=role_data.get("responsibilities", "").strip(),
                startup_prompt=role_data.get("startup_prompt", "").strip(),
                model=role_data.get("model"),
                effort=role_data.get("effort"),
                theme=role_data.get("theme"),
            ))
```

**In `generate_moot_toml`, extend the `[agents.<role>]` block emission** (replace the existing for-role loop):

```python
    for role in profile.roles:
        lines.append(f"[agents.{role.name}]")
        lines.append(f'display_name = "{role.display_name}"')
        lines.append('profile = "devcontainer"')
        # Escape quotes in startup prompt, collapse to single line
        prompt = role.startup_prompt.replace("\n", " ").strip()
        prompt = prompt.replace('"', '\\"')
        lines.append(f'startup_prompt = "{prompt}"')
        # Per-role harness/model/effort/theme — emit only when set so
        # absent keys mean "fall through to global defaults".
        if role.harness and role.harness != "claude-code":
            lines.append(f'harness = "{role.harness}"')
        if role.model:
            lines.append(f'model = "{role.model}"')
        if role.effort:
            lines.append(f'effort = "{role.effort}"')
        if role.theme:
            lines.append(f'theme = "{role.theme}"')
        lines.append("")
```

Note the `role.harness != "claude-code"` guard: the bundled templates set every role to `claude-code` explicitly, but the generated `moot.toml` keeps its per-role sections minimal by omitting the default harness. A role with `harness = "cursor"` in `team.toml` DOES get a per-role `harness = "cursor"` line in `moot.toml`. This preserves the current generator behavior (tests `test_generate_moot_toml_from_loop4` assert only `data["harness"]["type"] == "claude-code"`, not per-role).

### 6.2 `src/moot/config.py` — `AgentConfig` + validation

**Add allowlists at module top (after `ACTORS_JSON = ...`):**

```python
import re

_HARNESS_ALLOWLIST = {"claude-code", "cursor", "aider"}
_MODEL_ALLOWLIST_RE = re.compile(
    r"^(opus|sonnet|haiku|best|default|opusplan|sonnet\[1m\]|opus\[1m\]|claude-[a-z0-9-]+)$"
)
_EFFORT_ALLOWLIST = {"low", "medium", "high", "xhigh", "max"}
```

**Replace `AgentConfig`:**

```python
class AgentConfig:
    def __init__(
        self,
        role: str,
        data: dict[str, Any],
        *,
        default_harness: str = "claude-code",
        default_model: str | None = None,
        default_effort: str | None = None,
    ) -> None:
        self.role = role
        self.display_name: str = data.get("display_name", role.title())
        self.profile: str = data.get("profile", "devcontainer")
        self.startup_prompt: str = data.get(
            "startup_prompt",
            (
                f"You are the {role.title()} agent. Call orientation() to "
                f"get your identity, focus space, and recent context in one "
                f"call. Then subscribe to the channel and post a "
                f"status_update confirming you are online."
            ),
        )
        self.harness: str = data.get("harness", default_harness)
        self.model: str | None = data.get("model", default_model)
        self.effort: str | None = data.get("effort", default_effort)
        self.theme: str | None = data.get("theme")
        self._validate()

    def _validate(self) -> None:
        if self.harness not in _HARNESS_ALLOWLIST:
            _config_error(
                f"agents.{self.role}.harness = {self.harness!r} is not one of "
                f"{sorted(_HARNESS_ALLOWLIST)}"
            )
        if self.model is not None and not _MODEL_ALLOWLIST_RE.match(self.model):
            _config_error(
                f"agents.{self.role}.model = {self.model!r} is not a recognized "
                f"Claude model alias or full ID. Valid aliases: opus, sonnet, "
                f"haiku, best, default, opusplan, sonnet[1m], opus[1m]. Full "
                f"IDs must match claude-<identifier>."
            )
        if self.effort is not None and self.effort not in _EFFORT_ALLOWLIST:
            _config_error(
                f"agents.{self.role}.effort = {self.effort!r} is not one of "
                f"{sorted(_EFFORT_ALLOWLIST)}"
            )


def _config_error(msg: str) -> None:
    print(f"Error: {msg}")
    raise SystemExit(1)
```

**Modify `MootConfig.__init__`** — extend the existing `harness` block and the agent-construction loop:

```python
        harness = data.get("harness", {})
        self.harness_type: str = harness.get("type", "claude-code")
        self.permissions: str = harness.get("permissions", "dangerously-skip")
        self.default_model: str | None = harness.get("model")
        self.default_effort: str | None = harness.get("effort")
        self.agents: dict[str, AgentConfig] = {}
        for role, agent_data in data.get("agents", {}).items():
            self.agents[role] = AgentConfig(
                role,
                agent_data,
                default_harness=self.harness_type,
                default_model=self.default_model,
                default_effort=self.default_effort,
            )
```

Note: validation of `[harness]` global `model` / `effort` is done transitively — when AgentConfig inherits the global default, `_validate()` runs on the inherited value. Invalid globals surface as "agents.<first-role>.model = ..." which is a slight error-message sharpening opportunity but acceptable for MVP.

### 6.3 `src/moot/launch.py` — per-role flags + theme

**Replace `_launch_role` body** (the `match config.harness_type` block and the tmux command construction):

```python
    agent_config = config.agents[role]
    prompt = prompt_override or agent_config.startup_prompt

    # Per-role harness selection. Falls back to the global default set
    # on AgentConfig at moot.toml-load time.
    harness = agent_config.harness

    # The claude command is built INLINE (per D2). The two literal strings
    # '--dangerously-load-development-channels' and 'server:convo-channel'
    # ALSO appear in cmd_exec's docstring as an anchor for the existing
    # inspect.getsource-based test (test_launch_includes_channel_flag).
    match harness:
        case "claude-code":
            # Per-role --model / --effort when set. Absent flags let
            # Claude Code's account defaults apply.
            model_flag = (
                f"--model {shlex.quote(agent_config.model)} "
                if agent_config.model
                else ""
            )
            effort_flag = (
                f"--effort {shlex.quote(agent_config.effort)} "
                if agent_config.effort
                else ""
            )
            claude_cmd = (
                "claude "
                "--dangerously-load-development-channels server:convo-channel "
                f"{model_flag}{effort_flag}"
                f"-- {shlex.quote(prompt)}"
            )
        case _:
            print(f"Error: harness '{harness}' not yet supported")
            raise SystemExit(1)
```

**Append per-role theme chain to the tmux command construction** (after the existing `tmux_cmd = f"tmux -u new-session -d ..."` assignment, BEFORE the `exec_capture`):

```python
    # Per-role tmux theme: turn on pane-border-status so the color is
    # visible even in single-pane sessions, then set the border color.
    # Theme is applied after new-session since new-session -d returns
    # immediately. Skipped when the role has no theme configured —
    # default tmux border style is preserved in that case.
    if agent_config.theme:
        theme_q = shlex.quote(agent_config.theme)
        session_q = shlex.quote(session)
        tmux_cmd += (
            f" && tmux set-option -t {session_q} pane-border-status top"
            f" && tmux set-option -t {session_q} pane-border-style fg={theme_q}"
        )
```

Using `&&` rather than `;` ensures theme failure doesn't mask a prior session-launch failure in the exit code (session-create errors still surface cleanly). Theme failure is cosmetic and would only occur if tmux doesn't recognize the color — the session is already running at that point, so the command's rc effectively signals "session launched, theme may or may not have applied."

### 6.4 `src/moot/scaffold.py` — per-role defaults in adoption

**Add a helper above `_write_moot_toml_from_adopted`:**

```python
# D1 defaults — mapping from adopted display_name (lowercased) to the
# recommended per-role model. Unknown roles fall through with no model
# set, which means Claude Code's account default applies. Theme map
# matches the bundled team templates for visual consistency.
_ADOPTED_ROLE_DEFAULTS: dict[str, dict[str, str]] = {
    "product":        {"model": "opus",   "theme": "blue"},
    "leader":         {"model": "sonnet", "theme": "yellow"},
    "spec":           {"model": "opus",   "theme": "magenta"},
    "implementation": {"model": "opus",   "theme": "cyan"},
    "qa":             {"model": "sonnet", "theme": "green"},
    "verifier":       {"model": "sonnet", "theme": "green"},  # loop-3 display_name
    "librarian":      {"model": "sonnet", "theme": "white"},
}
```

**In `_write_moot_toml_from_adopted`, extend the role loop** (replace the existing `for role_key, info in adopted.items():` body):

```python
    for role_key, info in adopted.items():
        defaults = _ADOPTED_ROLE_DEFAULTS.get(info["display_name"].lower(), {})
        profile.roles.append(
            RoleProfile(
                name=role_key,
                display_name=info["display_name"],
                harness="claude-code",
                model=defaults.get("model"),
                theme=defaults.get("theme"),
            )
        )
```

### 6.5 `src/moot/templates/teams/*/team.toml` — bake defaults

**For each of the 5 bundled templates, add `model` and `theme` keys under each `[[roles]]` block** per D1 + D-THEME-COLOR-MAP. Example diff for `loop-4/team.toml` (apply the same pattern to all 5):

```diff
 [[roles]]
 name = "product"
 display_name = "Product"
 harness = "claude-code"
+model = "opus"
+theme = "blue"
 responsibilities = """
 ...
```

Full per-template map:

| Template | Roles affected (name → model, theme) |
|---|---|
| `loop-3` | `leader→sonnet,yellow`; `implementation→opus,cyan`; `qa→sonnet,green` |
| `loop-4` | `product→opus,blue`; `spec→opus,magenta`; `implementation→opus,cyan`; `qa→sonnet,green` |
| `loop-4-observer` | `product→opus,blue`; `spec→opus,magenta`; `implementation→opus,cyan`; `qa→sonnet,green`; `librarian→sonnet,white` |
| `loop-4-parallel` | `product→opus,blue`; `spec→opus,magenta`; `implementation_a→opus,cyan`; `implementation_b→opus,cyan`; `qa→sonnet,green` |
| `loop-4-split-leader` | `product→opus,blue`; `lead→sonnet,yellow`; `implementation→opus,cyan`; `qa→sonnet,green` |

(Implementation: use the existing `loop-4/team.toml` ordering for placement — after `harness = "claude-code"`, before `responsibilities = """`.)

## 7. Test plan

### 7.1 Required (Implementation) — Impl writes before handoff

**`tests/test_config.py` — 4 new tests, all under a new `class TestAgentProfiles`:**

- `test_per_role_profile_round_trip` — moot.toml with `[agents.spec]` setting `harness`, `model="opus"`, `effort="high"`, `theme="magenta"`; assert `config.agents["spec"]` reflects all four values.
- `test_global_defaults_cascade_to_agent` — moot.toml with `[harness] model="sonnet" effort="medium"` and an agent that sets neither; assert the agent inherits `"sonnet"` / `"medium"`.
- `test_invalid_model_rejects_at_load` — moot.toml with `[agents.spec] model="sonet"` (typo); assert `MootConfig(path)` raises `SystemExit(1)` and the stderr/stdout mentions the role and the valid-values pointer.
- `test_migration_v1_toml_still_loads` — moot.toml with the pre-run schema (no `harness.model`, no per-agent `model`/`effort`/`theme`); assert `MootConfig(path)` loads without raising, all agents have `model=None`, `effort=None`, `theme=None`.

**`tests/test_launch.py` — 2 edits + 1 new test:**

- Extend `test_cmd_exec_launch_full_flow`: make the fake `AgentConfig` set `model="opus"`, `effort="high"`, `theme="cyan"`, `harness="claude-code"`. Assert the captured bash script contains all three of:
  - `"--model opus"`
  - `"--effort high"`
  - `"pane-border-style fg=cyan"` (exact substring)
- New test `test_cmd_exec_launch_no_flags_when_unset`: fake `AgentConfig` sets `model=None`, `effort=None`, `theme=None`; assert the bash script contains **none** of `"--model"`, `"--effort"`, `"pane-border-status"`, `"pane-border-style"`.
- Existing `test_cmd_exec_session_already_running`, `test_cmd_exec_unknown_role`, `test_cmd_up_*` — leave unchanged (they don't assert on model/effort/theme).

**`tests/test_templates.py` — 2 new tests + 1 edit:**

- New `test_team_toml_models_match_D1_defaults` — iterate all 5 templates, for every role with a `display_name` in `_expected_models` (the D1 map), assert `RoleProfile.model` equals the expected value. `_expected_models` is a test-local constant copying D1. This is the structural invariant that catches drift if a template file is edited without the map.
- New `test_generate_moot_toml_emits_per_role_model_and_theme` — generate moot.toml from loop-4, parse with `tomllib`, assert each agent section has a `model` string AND a `theme` string; spot-check `agents["product"]["model"] == "opus"` and `agents["product"]["theme"] == "blue"`.
- Edit `test_parse_loop4_team_toml` — add assertions that `[r.model for r in profile.roles if r.name == "product"][0] == "opus"` and similar for spec/impl/qa (keeps the existing test green AND documents the D1 baked-in defaults).

### 7.2 Suggested (QA) — QA's discretion

- Per-template generation fuzz: parse each of the 5 templates, generate moot.toml, re-parse with `MootConfig`, assert no validation errors. (Covers the "every bundled template is actually a valid operator-facing team.toml" invariant.)
- Regex sanity: `_MODEL_ALLOWLIST_RE` matches known-good strings (`opus`, `claude-opus-4-7`, `sonnet[1m]`) and rejects known-bad (`"opsu"`, `""`, `"claude-"`, `"opus "`, whitespace-only).
- `_launch_role` with `harness="cursor"` still errors cleanly with "harness 'cursor' not yet supported" (unchanged behavior; regression guard).
- tmux command ordering: assert `set-option pane-border-status` appears BEFORE `set-option pane-border-style` in the emitted script (wrong order → border-style silently ignored in some tmux versions).

**Test responsibility split:** Required tier covers the feature's common-case behavior (per-role round-trip, global cascade, validation, migration path, launcher flag plumbing, template baked defaults). Suggested tier covers edge cases and operator-protection invariants.

## 8. Expected pytest delta

Baseline: 119 passed, 1 skipped.

- Drops: 0 (migration test ensures no existing behavior is broken)
- Rewrites: 0 (existing tests extended in-place, not renamed or deleted — extended tests' names are unchanged)
- Adds: 4 + 1 + 2 = **7** Required tests (§ 7.1)

**Target after Impl:** `119 + 7 = 126 passed, 1 skipped` in `uv run pytest`. QA's suggested tests land as +3–4 additional passing tests; QA-run target: `129-130 passed, 1 skipped`. Leader should report the Impl-gate count (`126p/1s`); QA's run-time count floats upward as QA adds discretionary coverage.

Pyright: **11 errors unchanged** (all in `mcp_adapter.py`, none in touched files). If the new code introduces any pyright diagnostic in `team_profile.py`, `config.py`, `launch.py`, or `scaffold.py`, it is a regression and must be fixed in-Impl before handoff.

## 9. Security considerations

**Auth requirements.** None of the new code adds endpoints or changes authenticated surfaces. Per-role `model` / `effort` / `theme` / `harness` values flow: operator-edited `moot.toml` → `MootConfig` (local file read) → `_launch_role` → `tmux` / `claude` CLI. No network ingress, no cross-user surfaces.

**Input validation boundaries.** The operator controls `moot.toml`. The four new fields are string values that reach:

1. `claude --model <value>` — passed through `shlex.quote()` so a malicious string can't break out of the claude-CLI argv. Claude Code itself rejects unknown models.
2. `claude --effort <value>` — same `shlex.quote()` protection.
3. `tmux set-option pane-border-style fg=<value>` — `shlex.quote()` applied. Tmux rejects unknown colors but doesn't interpret the string as shell.
4. `tmux new-session -s <session>` — unchanged from today; session names derive from role names which are TOML keys (restricted character set).

All four string-valued fields go through `shlex.quote()` before entering any shell or tmux context. The `&&`-chained `tmux set-option` calls use the same `shlex.quote(session)` that the original `new-session` call uses, so the per-session targeting is injection-safe.

**Data isolation.** The four new keys are per-role, written to `moot.toml` (the operator's checked-in config). No cross-tenant or cross-space implications — this is a local-launcher feature.

**Secrets handling.** None of the four fields is a secret. The existing `.moot/actors.json` API key flow is untouched.

**Sandbox / tmux server env inheritance.** The per-pane env via `tmux new-session -e` (already in place for `CONVO_ROLE`) is unchanged. The two new `tmux set-option -t <session>` calls only affect pane-border rendering and don't set any env vars.

## 10. Invariants

- Every `[[roles]]` block in every bundled `team.toml` emits a parseable `RoleProfile` with the D1 model set (structural test catches drift).
- Every `[agents.<role>]` block in a generated `moot.toml` reconstructs an `AgentConfig` whose validation passes (generation fuzz test catches drift).
- `_launch_role` emits `--model` iff `agent_config.model is not None`; `--effort` iff `agent_config.effort is not None`; `pane-border-*` set-option calls iff `agent_config.theme is not None` (positive AND negative tests both required).
- A v1 `moot.toml` (no new keys anywhere) loads cleanly and launches every agent with `model=None`, `effort=None`, `theme=None` (migration test catches drift).

## 11. Open questions

None. All six Product OQs (D1-D6) are resolved.

## 12. Out-of-scope findings (F-*)

**F1 — Product scope references wrapper-script edits that aren't needed.**
The Product doc § In-scope says "Plumbing through the wrapper scripts (`run-moot-mcp.sh`, `run-moot-channel.sh`) and `launch.py` cmd_up". Grounding in § 13 Phase B confirms the three wrapper scripts read only `CONVO_ROLE` and `actors.json` — they don't participate in model/effort/theme plumbing. Disposition: D-WRAPPER-SCRIPTS-UNCHANGED resolves in-draft, no edit needed. Product follow-up: refresh the scope doc post-ship so the next run that references this doc doesn't also assume wrapper-script involvement.

**F2 — `config.py::cmd_config`'s `show` subcommand doesn't surface the new per-role fields.**
Today `moot config show` prints only `api_url`, `space_id`, `harness_type`, and role names — it doesn't display per-role model/effort/theme. A user running `moot config show` to inspect their profile state will not see the new fields. Disposition: deferred to Product follow-up. Not in scope for this run (Product scope doesn't mention extending `moot config show`). Could become a quick add in a follow-up run; could also become a larger `moot config profiles` subcommand. Noted for retro.

## 13. Grounding log

**Phase A — Dep versions and lock-file tentpole check.**
Per the Run AB carry-forward: "grep lock files for any existing native support before designing a new code branch."

- `mootup-io/moot/pyproject.toml`: depends on Python 3.11+ (stdlib `tomllib`), `pydantic`, `httpx`, `redis`, `fastmcp`. No Claude-Code-adjacent SDK — all claude CLI integration is shell-level via `subprocess`/tmux.
- `uv.lock` inspection: no lockfile-native support for model/effort mapping. This is pure additive plumbing, not dep-native. (This is explicitly NOT a Run-AB-style tentpole where a dep does the work for us — the code additions in § 6 are load-bearing.)
- `pytest-xdist` is NOT in the dev group; cross-repo rule applies: `uv run pytest` without `-n auto`. Confirmed.

**Phase B — Claude Code CLI vocabulary verification.**
Consulted Anthropic's Claude Code CLI reference (https://code.claude.com/docs/en/cli-reference.md) via the `claude-code-guide` subagent (per Run AA carryover "docs-first via claude-code-guide, not a tmux spike"):

- `--model` flag accepts: `opus`, `sonnet`, `haiku`, `best`, `default`, `opusplan`, `sonnet[1m]`, `opus[1m]`, plus full IDs like `claude-opus-4-7`. Both alias AND full-ID are accepted.
- `--effort` flag accepts per-model-family: Opus 4.7 = `{low, medium, high, xhigh, max}`; Opus 4.6 / Sonnet 4.6 = `{low, medium, high, max}`. Default depends on model family (Claude Code picks a sensible per-family default — that's why D-DEFAULT-EFFORT omits a default here).
- `--model` and `--effort` are orthogonal to `--dangerously-skip-permissions` and `--dangerously-load-development-channels` — no interaction.
- Precedence: CLI flags > settings.json. Our bundled `.claude/settings.json` sets only `permissions.defaultMode = "bypassPermissions"` and `hooks.*` — no `model` field, so CLI `--model` is unambiguous.

**Phase C — Env-propagation trace (bidirectional, per Run AB carry-forward).**
New env vars introduced by this run: **none**. The four new keys flow through TOML → Python config → shlex-quoted CLI flags / tmux options, NOT through env vars. Therefore the "where SET vs where UNSET" bidirectional grep has no subjects.

Confirmed: `grep -rn "subprocess\|Popen\|_run_wrapper" /workspaces/convo/mootup-io/moot/.worktrees/spec/tests/` returns zero matches. No subprocess-forwarding traps in `mootup-io/moot`'s test suite today — the test_launch tests mock `exec_capture` directly.

**Phase D — Scope in/out contradiction grep.**
Product scope § In-scope vs § Out-of-scope:

- In: "Plumbing through the wrapper scripts (`run-moot-mcp.sh`, `run-moot-channel.sh`) and `launch.py` cmd_up" → F1 above; resolved via D-WRAPPER-SCRIPTS-UNCHANGED.
- In: "A test exercising a representative profile (e.g., Leader = Sonnet) and asserting the right model flag reaches the harness invocation" → § 7.1 `test_cmd_exec_launch_full_flow` extension covers this; the explicit "Leader = Sonnet" spot-check is implicit in the template-model map test.
- Out: "Full Cursor / Aider feature parity" vs In: "`harness` … one of `claude-code` (default), `cursor`, `aider`" → no contradiction — the harness allowlist accepts all three; only claude-code has full plumbing (D-CROSS-HARNESS-MODEL-EFFORT). cursor/aider dispatch errors are unchanged.
- Out: "Full theme bundles" vs In: "`theme` — string used as tmux pane-border color" → no contradiction — simple color is in, full bundles are out.

No other contradictions found.

**Phase E — Structural-invariant test coverage.**
Two structural invariants added in § 7.1 / § 10:

1. `test_team_toml_models_match_D1_defaults` — drift catches if a template file drops or renames a `model` key.
2. `test_generate_moot_toml_emits_per_role_model_and_theme` — drift catches if the generator forgets to emit per-role fields.

Both are single-value assertions keyed to D1 — cheap to maintain, loud when they break.

**Phase F — No-half-drafts grep.**
Drafted § 6 source blocks grepped for `NotImplementedError`, `TODO`, `FIXME`, `placeholder`, `XXX`: zero hits.

## 14. QA verification gates (Q1–Q11)

For QA to run on `feat/per-agent-profiles` at Impl ship-ready commit:

| Q | Gate | Expected |
|---|---|---|
| Q1 | `cd /workspaces/convo/mootup-io/moot/.worktrees/qa && uv run pyright src/moot/` | 11 errors, 0 warnings (unchanged baseline) |
| Q2 | `uv run pytest` | 126+ passed, 1 skipped (119 + 7 Required adds; QA's own suggested tests push upward) |
| Q3 | `grep -c 'model = "' src/moot/templates/teams/loop-4/team.toml` | ≥ 4 (one per role) |
| Q4 | `grep -c 'theme = "' src/moot/templates/teams/loop-4/team.toml` | ≥ 4 (one per role) |
| Q5 | `grep -c 'model\|theme' src/moot/templates/teams/loop-4-observer/team.toml` | ≥ 10 (5 roles × 2 keys) |
| Q6 | `uv run python -c "from moot.team_profile import TeamProfile; from pathlib import Path; p = TeamProfile.from_toml(Path('src/moot/templates/teams/loop-4/team.toml')); print([(r.name, r.model, r.theme) for r in p.roles])"` | Prints `[('product', 'opus', 'blue'), ('spec', 'opus', 'magenta'), ('implementation', 'opus', 'cyan'), ('qa', 'sonnet', 'green')]` |
| Q7 | `uv run python -c "from moot.team_profile import TeamProfile, generate_moot_toml; from pathlib import Path; p = TeamProfile.from_toml(Path('src/moot/templates/teams/loop-4/team.toml')); print(generate_moot_toml(p, 'https://x'))"` | Output includes `model = "opus"` under `[agents.product]` AND `theme = "blue"` under same |
| Q8 | Invalid-model rejection: create a temp `moot.toml` with `[agents.spec]\nmodel = "sonet"`; run `uv run python -c "from moot.config import MootConfig; MootConfig(Path('/tmp/bad.toml'))"` | Exits with code 1, stderr/stdout includes "not a recognized Claude model alias" and the role name "spec" |
| Q9 | Drift-inject: comment out the `--model` flag emission in `_launch_role` (one-line removal); rerun `test_cmd_exec_launch_full_flow` | Test FAILS with "expected `--model opus` in script, not found" or similar. Restore; test PASSES. |
| Q10 | Migration: create a temp `moot.toml` with only the v1 schema (no harness.model, no per-agent model/effort/theme); run `MootConfig(path)` | No SystemExit raised; all agents have `.model is None`, `.effort is None`, `.theme is None`. |
| Q11 | tmux order: in the launch script emitted by `test_cmd_exec_launch_full_flow`, assert `pane-border-status` appears before `pane-border-style` | Confirmed — see § 6.3 ordering. |

Q9 (drift-inject) is the load-bearing QA gate per Run AB's drift-gate rule: actively proving the gate bites is more trustworthy than just confirming it passes today.

## 15. Retro carryover applied

- ✅ Cross-repo first-run baseline: remeasured from scratch (§ 2); empty-diff shortcut skipped.
- ✅ Cross-repo `uv run pytest` without `-n auto` (pytest-xdist not in moot-cli dev group).
- ✅ Docs-first via `claude-code-guide` for Claude Code CLI flags (§ 13 Phase B), not a tmux spike.
- ✅ Env-propagation trace bidirectional (§ 13 Phase C): new run adds NO env vars, trace reduces to "no subjects" — documented explicitly.
- ✅ Lock-file tentpole check (§ 13 Phase A): no dep-native support available — this run's code additions are load-bearing.
- ✅ Scope-in/out contradiction grep (§ 13 Phase D): one contradiction surfaced (F1 wrapper scripts), resolved in-draft.
- ✅ Structural-invariant tests (§ 10, § 7.1): two drift-catchers added.
- ✅ No half-drafts (§ 13 Phase F): grep clean.

## 16. Impl guidance

- Touch order: `team_profile.py` first (foundation), then `config.py` (depends on team_profile's model for validation symmetry), then `launch.py` (depends on AgentConfig's new fields), then `scaffold.py`, then templates × 5, then tests × 3.
- Templates × 5 = ideal subagent fan-out per the CLAUDE.md "Independent-files-same-rule fan-out (N ≥ 4)" rule. Each template gets the same rule applied to different role sets. Brief subagents with: (a) the per-template role→model,theme map from § 6.5, (b) the exact placement (after `harness = "claude-code"` line, before `responsibilities = """` line), (c) the byte pattern to inject. Fire 5 in parallel with byte-identical briefings except for the template name + role map.
- Tests: `tests/test_config.py`, `tests/test_launch.py`, `tests/test_templates.py` are each localized — no fan-out needed, keep in main session.
- Pre-existing pyright errors in `mcp_adapter.py:249` and `:1113` are NOT to be touched — different file, pre-baseline.

## 17. Ship criteria

- `uv run pytest` green (126+ passed, 1 skipped) ✓
- `uv run pyright src/moot/` 11 errors unchanged ✓
- All 11 Q-gates pass in QA ✓
- Generated `moot.toml` for each of 5 templates parses back to a `MootConfig` with no validation error ✓
- `_launch_role` for `harness="cursor"` / `"aider"` still errors "harness not yet supported" (regression guard) ✓
