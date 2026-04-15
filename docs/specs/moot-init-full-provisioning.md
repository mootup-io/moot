# `moot init` — Full Provisioning

**Status:** Spec — Run R (mootup-io/moot).
**Feature branch:** `feat/moot-init-full-provisioning` (rooted at `fa9b133`, main tip after Run Q ship).
**Product doc:** `/workspaces/convo/docs/product/moot-init.md` (561 lines, 9 D-decisions locked).
**Pipeline variant:** Standard. Product holds the semantic decisions; Spec translates to concrete code + tests. Open questions and product-doc silences are resolved in-draft with documented rationale (per `feedback_spec_resolves_product_doc_silences.md`), recommended defaults flagged for Product confirmation.
**Prerequisites:** Run Q shipped at `fa9b133` (brand sweep, `--version`, interactive `moot login`, `mootup_pat_` prefix). Convo-side pre-artifacts landed at `c85c431`: `/workspaces/convo/.claude/CLAUDE.md.mootup-template` and `/workspaces/convo/docs/ops/skill-release-transform-checklist.md`.

---

## § 1 Summary

Rewrite `src/moot/scaffold.py:cmd_init()` from the current local-only template scaffold into a one-shot bring-up that:

1. **Adopts** the user's default-space keyless agents by fetching them from the backend, rotating their keys, and persisting the `{role: {actor_id, api_key}}` map to `.moot/actors.json` (replacing `.agents.json`).
2. **Installs a bundled skills tree** at `.claude/skills/` (7 skills: product-workflow, spec-checklist, leader-workflow, librarian-workflow, handoff, verify, doc-curation), with per-skill conflict detection that routes colliding skills to `.moot/suggested-skills/<name>/`.
3. **Installs a bundled `CLAUDE.md`** with placeholder substitution, routing to `.moot/suggested-CLAUDE.md` if `<repo>/CLAUDE.md` already exists.
4. **Installs `.devcontainer/`** with the same conflict-staging pattern.
5. **Emits `.moot/init-report.md`** — a markdown report the user's AI coding agent reads to reconcile any staged suggestions.
6. **Adds CLI flags** to `moot init`: `--force`, `--update-suggestions`, `--adopt-fresh-install`, `--fresh`, `--yes`.
7. **Renames** `AGENTS_JSON = ".agents.json"` → `ACTORS_JSON = ".moot/actors.json"` (breaking) and updates every reader (`launch.py`, devcontainer runner shell scripts, tests, README).

The legacy `moot config provision` path stays functional (back-compat for any pipeline touching it), gets a new `--fresh` flag that maps cleanly onto today's behavior, and writes to the new location `.moot/agents-fresh.json` when `--fresh` is explicit.

---

## § 2 Baseline (frozen at `fa9b133`)

Re-measured from scratch in `/workspaces/convo/mootup-io/moot/.worktrees/spec/` (cross-repo first-run rule per `feedback_cross_repo_first_run_baseline.md` still applies — this is Run R's first measurement, inherited from Run Q's ship state).

**pytest** — 80 collected, **75 passed / 5 failed**:

```
$ uv sync --group test
$ uv run pytest -q
...............FFF.FF................................................... [ 90%]
........                                                                 [100%]
FAILED tests/test_example.py::test_moot_toml_valid
FAILED tests/test_example.py::test_devcontainer_json_valid
FAILED tests/test_example.py::test_post_create_installs_moot
FAILED tests/test_example.py::test_runner_scripts_unchanged
FAILED tests/test_example.py::test_gitignore_entries
5 failed, 75 passed in 1.74s
```

All 5 failures are **pre-existing** — same `Path(__file__).parents[N]` walking-past-worktree-boundary pattern documented in Run Q § 2. Impl/QA: carry forward unchanged, do not treat the delta as regressions.

**pyright** — **17 errors, 0 warnings, 0 informations**:

```
$ uv run pyright
...
17 errors, 0 warnings, 0 informations
```

Error distribution:
- `src/moot/adapters/mcp_adapter.py` — 11 errors (`object`/`None` narrowing in httpx + Protocol-typed methods; long-standing)
- `tests/test_scaffold.py` — 6 errors (`monkeypatch: object` annotation hygiene; should have been `pytest.MonkeyPatch` in Run Q but wasn't caught because test_scaffold.py wasn't in Run Q's test surface)

Impl target: **zero new errors**. New tests use `pytest.MonkeyPatch` per § 7.5 guardrail; existing `test_scaffold.py` tests that survive the rewrite get their annotations upgraded at the same time (net-negative on pyright count when the rewrite completes).

**Brand sweep** (Run Q regression guard):

```
$ grep -rn "Convo\|gemoot" src/moot/ README.md \
    | grep -v "src/moot/templates/" \
    | grep -v "src/moot/adapters/" \
    | grep -v "convo_key_\|convo_sess_\|convo-channel\|CONVO_\|\[convo\]" \
    | wc -l
0
```

(Run R's rewrite preserves the Run Q sweep — zero new user-facing `Convo`/`gemoot` strings, same preservation allowlist.)

**Tag baseline:** `fa9b133` == `feat/moot-init-full-provisioning` tip == `main` tip. Impl starts work here.

---

## § 3 Scope

### § 3.1 In scope

1. **`src/moot/scaffold.py`** — rewrite `cmd_init()` as async, implement adoption flow, conflict-aware installation, re-run semantics.
2. **`src/moot/config.py`** — rename constant, update reader API, bump schema reader to nested JSON.
3. **`src/moot/launch.py`** — update `cmd_exec` to use the new config reader.
4. **`src/moot/cli.py`** — add five flags to the `init` subparser; add `--fresh` flag to `config provision` subparser.
5. **`src/moot/provision.py`** — honor `args.fresh`; write to `.moot/agents-fresh.json`; otherwise default behavior is unchanged in Run R (see § 4 D-PROVISION).
6. **`src/moot/templates/skills/<name>/SKILL.md`** — **new directory**, seven transformed files created per § 6.7 (skill transform discipline).
7. **`src/moot/templates/CLAUDE.md`** — **new file**, one-shot copy from `/workspaces/convo/.claude/CLAUDE.md.mootup-template` (already transformed by Product + Librarian at convo `c85c431`).
8. **`src/moot/templates/devcontainer/run-moot-{mcp,channel,notify}.sh`** — rename sweep (`.agents.json` → `.moot/actors.json`), update the inline Python key-lookup to match the new nested JSON shape.
9. **`src/moot/templates/devcontainer/post-create.sh`** — no functional change; grep audit only.
10. **Tests** — rewrite `tests/test_scaffold.py` around the new adoption flow (respx HTTP mocking), refresh `tests/test_templates.py` / `tests/test_config.py` / `tests/test_security.py` / `tests/test_provision.py` for the new constants and shell-script content, add a smoke test over the transformed skill bundle.
11. **`README.md`** — update Quick Start prose to describe the new `moot init` flow, mention the new file locations, and keep the existing preservation-allowlist strings (`[convo]` TOML section header and the `convo_...` API-key prefix samples).

### § 3.2 Out of scope (explicit)

Everything in the kickoff's and product doc's "Out of scope" sections, plus the following spec-level clarifications:

- **No automatic merge of any kind** (CLAUDE.md, skills, devcontainer). Conflict = stage under `.moot/suggested-*/` and let the user's agent reconcile.
- **No JSON init-report.** Markdown only per product doc.
- **No backend schema changes.** Uses only existing `GET /api/actors/me`, `GET /api/spaces/{id}/participants`, `POST /api/actors/{id}/rotate-key`. The `X-Force-Rotate` header (from agent-connection-state, shipped at convo `011b51e`) is consumed by `moot init --force`.
- **No new backend endpoints.** The `POST /api/actors/{id}/release` endpoint is live but `moot release` (a future CLI subcommand mentioned in the product doc) is **NOT in Run R**. Only `moot init`'s flags ship here.
- **No `moot up` / `moot exec` / `moot status` / `moot attach` / `moot compact` behavior changes** beyond the `ACTORS_JSON` rename consequences. The new actors-file format plumbs through `launch.py` and the shell scripts, nothing else.
- **No `moot config provision` default-behavior changes** beyond adding the `--fresh` flag and relocating `agents-fresh.json` under `.moot/`. Per § 4 D-PROVISION, bare `moot config provision` keeps its legacy POST-per-role semantics in Run R. The product-doc D3 "default becomes alias for `moot init --update-actors-only`" clause is deferred — `--update-actors-only` is not in the product-doc D7 flag list, creating an internal inconsistency. Spec resolves in-draft toward the minimum-change interpretation.
- **No devcontainer template restructuring.** The only change to `templates/devcontainer/*.sh` is the `.agents.json` → `.moot/actors.json` rename sweep required to make the new actors file actually load at container startup.
- **No `moot-host` skill placeholder.** Per the product doc's "What Run R should do to leave room for it" section, we do NOT bundle a placeholder `moot-host/SKILL.md`. If/when that skill ships, it becomes an eighth bundled skill in a future run.
- **No auto-migration from `.agents.json` to `.moot/actors.json`.** Alpha users re-run `moot init --force --yes` per product doc D2. Existing `.agents.json` files are left untouched on disk; `.gitignore` gets `.moot/` added alongside the existing `.agents.json` entry.
- **Dev-facing preservation allowlist (inherited from Run Q D2):** `CONVO_*` env var names (CONVO_API_KEY, CONVO_API_URL, CONVO_SPACE_ID, CONVO_ROLE), `[convo]` TOML section header in `moot.toml`, `convo_key_` / `convo_sess_` key prefixes, `convo-channel` / `convo-lifecycle` script/MCP server names, logger names (`convo.*`), `adapters/` internal module names referencing Convo. Run R must NOT sweep any of these.

### § 3.3 Files touched — summary

Full table in § 5. Estimated total diff: ~550 LOC of code + ~650 LOC of tests + ~600 LOC of bundled release artifacts (7 transformed skills + CLAUDE.md template) + ~80 LOC of doc updates ≈ **~1900 LOC net**.

---

## § 4 Design decisions

D1–D9 are lifted from the product doc; D-TOML / D-SHELL / D-COLLISION / D-REPORT / D-LIBRARIAN / D-GITREPO / D-PROMPT / D-PROVISION are Spec-resolved in-draft.

### D1. Adopt, don't create (product doc D1)

`cmd_init()` performs the following sequence:

1. `GET /api/actors/me` → `{actor_id, display_name, default_space_id, ...}`
2. `GET /api/spaces/{default_space_id}/participants` → filter to `participant_type == "agent" AND api_key_prefix IS NULL`
3. For each keyless agent, `POST /api/actors/{actor_id}/rotate-key` → `{api_key}`
4. Build a `{role_display_name: {actor_id, api_key}}` map keyed by `display_name` from step 2
5. Persist to `.moot/actors.json` per D2

**No `POST /api/tenants/{tenant_id}/agents`** in the new code path. That endpoint lives exclusively in `moot config provision --fresh`.

**Role-name derivation:** `display_name` is the key. The backend returns participants with their display names (`"Product"`, `"Spec"`, `"Implementation"`, `"QA"`, optionally `"Librarian"`). These become the keys in `.moot/actors.json` AND the `[agents.<role>]` sections in the generated `moot.toml` (per D-TOML), lower-cased for moot.toml to match existing convention (`product`, `spec`, `implementation`, `qa`).

### D2. `.moot/actors.json` replaces `.agents.json` (product doc D2)

New file: `<repo>/.moot/actors.json`, permissions `0o600` (file) under a `0o700` parent directory (`.moot/`).

**JSON schema** (literal shape that `_write_actors_json()` produces and `config.load_actors()` consumes):

```json
{
  "space_id": "spc_1k2p9m4x6qy5a",
  "space_name": "Pat's Space",
  "api_url": "https://mootup.io",
  "actors": {
    "product": {
      "actor_id": "agt_abc123",
      "api_key": "convo_key_live_xxx",
      "display_name": "Product"
    },
    "spec": {
      "actor_id": "agt_def456",
      "api_key": "convo_key_live_yyy",
      "display_name": "Spec"
    },
    "implementation": { "actor_id": "agt_...", "api_key": "convo_key_...", "display_name": "Implementation" },
    "qa":             { "actor_id": "agt_...", "api_key": "convo_key_...", "display_name": "QA" }
  }
}
```

**Keys:** lower-cased role names (matches `moot.toml` `[agents.<key>]` sections). **`display_name`** preserves the backend's casing so `moot config show` and the CLAUDE.md template can round-trip it.

**`.gitignore`:** `.moot/` is added as a single line entry; do NOT remove the existing `.agents.json` entry (append-only, per Run Q discipline).

### D3. `moot config provision --fresh` escape hatch (product doc D3)

**Run R behavior** (see also D-PROVISION for what we are *not* changing):

- `moot config provision` (no flag) — **unchanged** from today. POSTs to `/api/tenants/{tenant_id}/agents` per role, writes `.agents.json` (legacy path, for back-compat).
- `moot config provision --fresh` — **new flag**. Same code path, but writes to `.moot/agents-fresh.json` (creating `.moot/` if missing). Distinct filename prevents confusion with `.moot/actors.json` (the adoption-flow file).

Users who want the new adoption flow use `moot init` explicitly. Users who've been running `moot config provision` see no behavior change; their muscle memory holds.

### D4. Skills bundled at release time (product doc D4)

**Bundled set** — 7 skills, exact paths listed in § 5:

| Role fit | Bundled skill | Convo source | Why bundle |
|---|---|---|---|
| Core role workflow | `product-workflow` | `/workspaces/convo/.claude/skills/product-workflow/SKILL.md` | Universal |
| Core role workflow | `leader-workflow` | `/workspaces/convo/.claude/skills/leader-workflow/SKILL.md` | Universal |
| Core role workflow | `librarian-workflow` | `/workspaces/convo/.claude/skills/librarian-workflow/SKILL.md` | Universal |
| Spec discipline | `spec-checklist` | `/workspaces/convo/.claude/skills/spec-checklist/SKILL.md` | Universal |
| Pipeline mechanic | `handoff` | `/workspaces/convo/.claude/skills/handoff/SKILL.md` | Universal |
| QA discipline | `verify` | `/workspaces/convo/.claude/skills/verify/SKILL.md` | Universal |
| Doc hygiene | `doc-curation` | `/workspaces/convo/.claude/skills/doc-curation/SKILL.md` | Universal |

**Excluded** (verified at draft time, matching product doc D4): `merge-to-main` (convo's multi-worktree-one-repo discipline doesn't generalize — other projects won't have `.worktrees/<role>/` or the same branch topology) and `stack-reset` (hard-codes `docker-compose.yml`, `convo-qa` project name, etc.).

Transform rules at § 6.7. Impl applies them to each skill on first landing.

### D5. CLAUDE.md template sourced from convo (product doc D5)

**Source:** `/workspaces/convo/.claude/CLAUDE.md.mootup-template` (235 lines, pre-transformed by Product + Librarian at convo `c85c431`). Already contains `{project_name}` etc. placeholders; already stripped of Pat / convo-specific paths / arch run history.

**Destination:** `src/moot/templates/CLAUDE.md` (new file, flat copy — no additional transform needed at spec time).

Impl: byte-copy the source file into the destination. Do NOT re-run the transform pass; the convo-side file is the release artifact.

**Placeholder set** (per D9):

| Placeholder | Filled from | Notes |
|---|---|---|
| `{project_name}` | `Path.cwd().name` (default) or `args.project_name` (future flag, not in Run R) | Literal substitution |
| `{space_id}` | step 1 response `default_space_id` | |
| `{space_name}` | step 1 response (added in the participant fetch, see D9) | |
| `{team_template}` | inferred from adopted role shape (see D9) | |
| `{api_url}` | `credential["api_url"]` | Typically `https://mootup.io` |

### D6. Conflict detection and `.moot/suggested-*/` staging (product doc D6)

**Detection (per target)** — Impl applies these checks inside `cmd_init()` before any write:

| Target | Conflict check |
|---|---|
| `<repo>/CLAUDE.md` | `Path("CLAUDE.md").exists()` |
| `<repo>/.claude/skills/<name>/` (per skill) | `Path(f".claude/skills/{name}").is_dir()` |
| `<repo>/.devcontainer/` | `Path(".devcontainer").is_dir()` |

**Staging layout:**

```
.moot/
  actors.json                                ← mechanical, always written
  init-report.md                             ← markdown report, always written
  suggested-CLAUDE.md                        ← only if CLAUDE.md exists
  suggested-skills/
    spec-checklist/
      SKILL.md                               ← only if that skill exists
    handoff/
      SKILL.md
    (one subdir per colliding skill)
  suggested-devcontainer/
    devcontainer.json                        ← only if .devcontainer/ exists
    post-create.sh
    run-moot-mcp.sh
    run-moot-channel.sh
    run-moot-notify.sh
```

**No auto-cleanup** of `.moot/suggested-*/` between runs. A subsequent `moot init --update-suggestions` overwrites prior staging. `.moot/actors.json` and `.moot/init-report.md` are always written.

### D7. Re-run flags (product doc D7)

| Flag | Behavior |
|---|---|
| `moot init` | **Default.** Refuses if `.moot/actors.json` exists. Prints a hint directing the user at `--force` (rotate) or `--update-suggestions` (just refresh staging). Exit 1. |
| `moot init --force` | Re-runs the adoption flow: fetches participants, loops `POST /api/actors/{id}/rotate-key` with header `X-Force-Rotate: true`, rewrites `.moot/actors.json`. Prompts once before proceeding unless `--yes`. Does NOT touch user-owned CLAUDE.md / skills / devcontainer content. |
| `moot init --update-suggestions` | Skips the adoption/rotate-key phase entirely. Regenerates `.moot/suggested-*/` from the current bundled templates. Non-destructive; no confirmation needed. Requires `.moot/actors.json` to already exist (otherwise suggests `moot init` first). |
| `moot init --adopt-fresh-install` | Overwrites user CLAUDE.md / skills / devcontainer with bundled content unconditionally (no staging). Runs the adoption flow like `--force`. Prompts twice (once for key rotation, once for file overwrite) unless `--yes`. |
| `moot init --fresh` | Short-circuits into the legacy path: invokes `cmd_provision` with `args.fresh=True`. Creates new agents via `POST /api/tenants/{id}/agents`, writes `.moot/agents-fresh.json`, does NOT install skills / CLAUDE.md / devcontainer. |
| `moot init --yes` | Skip all confirmation prompts. |

**Confirmation prompts (stdlib `input()`)**:

- Before `--force` rotate: `"This will rotate keys for N agents. Currently-connected agents will disconnect. Continue? [y/N] "`
- Before `--adopt-fresh-install` overwrite: `"This will overwrite CLAUDE.md, .claude/skills/, and .devcontainer/ with bundled content, potentially losing your local changes. Continue? [y/N] "`

Response handling: `input().strip().lower() not in ("y", "yes")` → exit 0 without side effects.

### D8. Rotate-key loop — not a batch endpoint (product doc D8)

The rotate-key loop is a for-loop over the keyless-agent list. 4 HTTP calls for loop-4, 5 for loop-5. No batching, no concurrency (sequential keeps error messages deterministic and matches the reference flow in the product doc).

**Error handling:**
- First failure stops the loop.
- Partial progress (keys already rotated on the backend for agents 1..k-1) is NOT persisted to `.moot/actors.json`. Print `"Error: rotate-key failed for {agent_name}: HTTP {status}"` and exit 1.
- Re-running `moot init --force` recovers cleanly: rotate-key is idempotent in practice (re-rotating produces a new key and invalidates the previous, which is fine since the first run didn't persist anything).

### D9. Template parameterization (product doc D9)

Placeholder substitution is `str.replace("{key}", value)` per key. Applied to the CLAUDE.md template contents before writing to either `<repo>/CLAUDE.md` or `<repo>/.moot/suggested-CLAUDE.md`.

**`{team_template}` inference** — pure string derivation:

```python
def _infer_team_template(roles: list[str]) -> str:
    lower = {r.lower() for r in roles}
    if {"product", "spec", "implementation", "qa", "librarian"} <= lower:
        return "loop-5"
    if {"product", "spec", "implementation", "qa"} <= lower:
        return "loop-4"
    return "custom"
```

---

### Spec-resolved decisions

### D-TOML. `moot init` continues to write `moot.toml`

**Problem:** The product doc's desired-flow stdout summary (§ Desired flow) does not mention writing `moot.toml`, but `moot up`, `moot exec`, `moot config show`, `cmd_down`, and the devcontainer shell scripts all call `find_config()` → `MootConfig(moot.toml)`. Removing `moot.toml` writes from `cmd_init()` would break every downstream command.

**Resolution:** `cmd_init()` writes `moot.toml` in both greenfield and conflict paths. Content is generated **inline from the adopted team data**, reusing `team_profile.generate_moot_toml()` against an in-memory `TeamProfile` built from the adopted roles (NOT from a bundled team template). The legacy `templates/teams/<name>/team.toml` files remain in place and are consumed only by `moot config provision --fresh` per D3.

**Inline builder sketch:**

```python
def _build_profile_from_adopted(
    team_template_name: str,
    adopted: dict[str, dict[str, str]],
) -> TeamProfile:
    """Build an in-memory TeamProfile from backend-adopted agents."""
    profile = TeamProfile(
        name=team_template_name,
        description=f"Adopted from default space",
        version="1.0",
        origin="moot-init-adoption",
    )
    for role_key, info in adopted.items():
        profile.roles.append(RoleProfile(
            name=role_key,
            display_name=info["display_name"],
            harness="claude-code",
        ))
    return profile
```

Pass this profile to `generate_moot_toml(profile, api_url)` — which already emits `[convo]`, `[agents.<role>]`, and `[harness]` sections — and write to `moot.toml` iff `!Path("moot.toml").exists()` (same idempotence as today).

**Why:** Smallest diff consistent with downstream commands working. Does not require changing `moot up` / `moot exec` / `MootConfig` / `find_config`. Spec flags this in § 9 for Product confirmation.

### D-SHELL. Devcontainer runner scripts are updated for the new actors-file shape

**Problem:** Kickoff § "Out of scope" says "No devcontainer template changes in Run R. `.devcontainer/` is staged on conflict, installed on greenfield, but the template content itself is unchanged." But the kickoff § "Key deliverables" item 3 also says "Update any adapter/reader code (`moot up`, channel adapter init) that reads the old path." The devcontainer shell scripts are exactly channel-adapter-init code, and they hard-code `.agents.json` plus a flat JSON parse (`keys.get('$ROLE', '')`). The new nested shape + new path breaks them.

**Resolution:** Apply the rename sweep to `run-moot-mcp.sh`, `run-moot-channel.sh`, and `run-moot-notify.sh`. Two textual changes per file: (1) `AGENTS_FILE=".agents.json"` → `ACTORS_FILE=".moot/actors.json"` + rename of the subsequent `$AGENTS_FILE` references; (2) the inline Python `print(keys.get('$ROLE', ''))` → `print(data.get('actors', {}).get('$ROLE', {}).get('api_key', ''))`. Treat this as "reader code update" rather than "template content change" — strongest-specific-wins reading of the kickoff, same pattern Run Q applied to the scaffold.py line-22 scope contradiction.

**Why:** Without this, greenfield `moot init` lands working `.moot/actors.json` but the container starts up and can't find any keys at runtime. Symptom is silent 401s in the channel. Undoing the rename later is more expensive than landing it correctly now. Spec flags this in § 9.

### D-COLLISION. Skill collision is directory-existence (not file-existence)

**Problem:** Product doc OQ: "`<repo>/.claude/skills/<name>/` directory exists (any contents)" vs "`<repo>/.claude/skills/<name>/SKILL.md` file exists specifically."

**Resolution:** Use `Path(f".claude/skills/{name}").is_dir()`. A partially-populated skill directory still counts as a collision (safer: a user with half-written content should not have it silently overwritten by `moot init` on first run).

### D-REPORT. `init-report.md` is written on every run

**Problem:** Product doc implies the report is primarily for conflict cases. Unclear whether greenfield runs also write it.

**Resolution:** `cmd_init()` always writes `.moot/init-report.md` at the end of a successful run, regardless of whether anything was staged. The "greenfield" report names the mechanical operations and points at `moot up`; the "conflict" report adds a section listing staged suggestions. Simpler code path, agent-friendly (report file always exists → `--update-suggestions` can always reference it).

### D-LIBRARIAN. Always install the Librarian skill regardless of adopted-team composition

**Problem:** Default space provisioning creates loop-4 (no Librarian). Should `moot init` skip the Librarian skill file when loop-4 is detected?

**Resolution:** Install all 7 bundled skills unconditionally. Per product doc "Out of scope / Per-role skill subsetting" — skill files are trivial filesystem cost and installing a Librarian skill into a loop-4 repo is harmless (it just never gets invoked). v2+ may subset; Run R does not.

### D-GITREPO. Warn on non-git repo, don't fail

**Problem:** Product doc OQ: "Should `moot init` refuse to run on a repo that doesn't look like a git repo?"

**Resolution:** Emit a warning to stdout (`"Warning: this doesn't look like a git repository; .moot/ and .claude/skills/ won't be versioned."`) but continue. Check: `Path(".git").exists()`. No fail, no prompt.

### D-PROMPT. `--force` prompt uses stdlib `input()`

**Problem:** Product doc is silent on prompt mechanism.

**Resolution:** `input()` (not `getpass`, not `click`, not a third-party prompt library). Prompt text exact per D7 table. `--yes` flag short-circuits.

### D-PROVISION. `moot config provision` default is unchanged in Run R

**Problem:** Product doc D3 says "default `moot config provision` becomes an alias for `moot init --update-actors-only`" but `--update-actors-only` is not in the D7 flag list. The product doc contradicts itself.

**Resolution (strongest-specific-wins):** Trust the D7 flag list. Bare `moot config provision` keeps its legacy POST-per-role semantics in Run R. Only the `--fresh` flag and the new `.moot/agents-fresh.json` location ship. Users who want the adoption flow invoke `moot init --force`.

This is the smallest change consistent with the kickoff's explicit scope for `cli.py` (only init-subparser flags are mentioned). Spec flags this in § 9 for Product confirmation.

---

## § 5 Files to create / modify

| # | File | Action | Approx LOC | Reason |
|---|---|---|---|---|
| 1 | `src/moot/scaffold.py` | **Rewrite** `cmd_init()` as async; add 9 private helpers (see § 6.3) | +240 / -80 | D1, D6, D7, D8, D9, D-TOML |
| 2 | `src/moot/config.py` | Rename `AGENTS_JSON` → `ACTORS_JSON`; update default value; add `load_actors()`, `get_actor_key()` functions; keep `load_agent_keys()` as a shim on top for backward compat during Run R (called only by legacy provision) | +30 / -10 | D2 |
| 3 | `src/moot/launch.py` | Import `get_actor_key` instead of `load_agent_keys`; update `cmd_exec` key lookup; change `os.environ["CONVO_API_KEY"]` line accordingly | +5 / -3 | D2 plumbing |
| 4 | `src/moot/cli.py` | Add 5 flags to `init_p` subparser + `--fresh` to `config provision` subparser; update dispatch to run `cmd_init` via `asyncio.run()` | +20 / -5 | D7 |
| 5 | `src/moot/provision.py` | Read `getattr(args, "fresh", False)`; write to `.moot/agents-fresh.json` when fresh; otherwise unchanged | +15 / -5 | D3, D-PROVISION |
| 6 | `src/moot/templates/CLAUDE.md` | **New file**, byte-copy from convo | +235 / -0 | D5 |
| 7 | `src/moot/templates/skills/product-workflow/SKILL.md` | **New file**, transform from convo source | +~75 | D4 |
| 8 | `src/moot/templates/skills/spec-checklist/SKILL.md` | **New file**, transform from convo source | +~95 | D4 |
| 9 | `src/moot/templates/skills/leader-workflow/SKILL.md` | **New file**, transform from convo source | +~140 | D4 |
| 10 | `src/moot/templates/skills/librarian-workflow/SKILL.md` | **New file**, transform from convo source | +~45 | D4 |
| 11 | `src/moot/templates/skills/handoff/SKILL.md` | **New file**, transform from convo source | +~40 | D4 |
| 12 | `src/moot/templates/skills/verify/SKILL.md` | **New file**, transform from convo source | +~65 | D4 |
| 13 | `src/moot/templates/skills/doc-curation/SKILL.md` | **New file**, transform from convo source | +~75 | D4 |
| 14 | `src/moot/templates/devcontainer/run-moot-mcp.sh` | Rename `AGENTS_FILE` constant, update Python key-lookup for nested shape | +5 / -5 | D-SHELL |
| 15 | `src/moot/templates/devcontainer/run-moot-channel.sh` | Same | +5 / -5 | D-SHELL |
| 16 | `src/moot/templates/devcontainer/run-moot-notify.sh` | Same | +5 / -5 | D-SHELL |
| 17 | `tests/test_scaffold.py` | **Rewrite.** Replace old template-flow tests with new adoption-flow tests (respx-mocked), conflict-aware tests, re-run-flag tests. Upgrade `monkeypatch` annotations to `pytest.MonkeyPatch` | +440 / -160 | § 7 |
| 18 | `tests/test_templates.py` | Update `test_runner_reads_agents_json` → `test_runner_reads_actors_json`; update `forbidden` patterns in `test_runner_scripts_no_convo_paths`; add skill-bundle smoke test | +60 / -30 | § 7 |
| 19 | `tests/test_config.py` | Add `test_actors_json_constant`, `test_load_actors_missing`, `test_load_actors_parses_schema`, `test_get_actor_key_returns_role_key` | +50 / -0 | § 7 |
| 20 | `tests/test_security.py` | Update `.gitignore` assertions from `.agents.json` to also accept `.moot/` | +8 / -4 | § 7 |
| 21 | `tests/test_provision.py` | Add `test_provision_fresh_writes_moot_agents_fresh_json` | +30 / -0 | § 7 |
| 22 | `README.md` | Update Quick Start prose (drop `moot config provision` as a required step, describe new adoption flow, mention `.moot/actors.json`); preserve Run Q allowlist strings | +30 / -20 | Doc hygiene |

**Total approx:** ~1200 LOC of authored content + ~700 LOC of bundled release artifacts = **~1900 LOC net**.

**Not modified** (explicitly verified to not need changes): `src/moot/auth.py`, `src/moot/lifecycle.py`, `src/moot/id_encoding.py`, `src/moot/models.py`, `src/moot/response_format.py`, `src/moot/team_profile.py`, `src/moot/adapters/*`, `pyproject.toml`, `src/moot/__init__.py`.

---

## § 6 Per-file code changes

### § 6.1 `src/moot/config.py`

Rename constant, add new readers, preserve legacy reader as a shim:

```python
"""moot.toml and .moot/actors.json loaders."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

MOOT_TOML = "moot.toml"
MOOT_DIR = ".moot"
ACTORS_JSON = f"{MOOT_DIR}/actors.json"


class AgentConfig:
    def __init__(self, role: str, data: dict[str, Any]) -> None:
        self.role = role
        self.display_name: str = data.get("display_name", role.title())
        self.profile: str = data.get("profile", "devcontainer")
        self.startup_prompt: str = data.get(
            "startup_prompt",
            f"Run your startup protocol from CLAUDE.md. You are the {role.title()} agent.",
        )


class MootConfig:
    def __init__(self, path: Path) -> None:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        convo = data.get("convo", {})
        self.api_url: str = convo.get("api_url", "https://mootup.io")
        self.space_id: str | None = convo.get("space_id")
        harness = data.get("harness", {})
        self.harness_type: str = harness.get("type", "claude-code")
        self.permissions: str = harness.get("permissions", "dangerously-skip")
        self.agents: dict[str, AgentConfig] = {}
        for role, agent_data in data.get("agents", {}).items():
            self.agents[role] = AgentConfig(role, agent_data)

    @property
    def roles(self) -> list[str]:
        return list(self.agents.keys())


def find_config() -> MootConfig | None:
    """Find and parse moot.toml in cwd or parents."""
    path = Path.cwd()
    while path != path.parent:
        toml_path = path / MOOT_TOML
        if toml_path.exists():
            return MootConfig(toml_path)
        path = path.parent
    return None


def load_actors() -> dict[str, Any] | None:
    """Load .moot/actors.json; returns None if missing."""
    path = Path(ACTORS_JSON)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def get_actor_key(role: str) -> str:
    """Return the API key for a role from .moot/actors.json, or ''."""
    data = load_actors()
    if not data:
        return ""
    actors = data.get("actors", {})
    entry = actors.get(role) or actors.get(role.lower()) or {}
    return entry.get("api_key", "")


def load_agent_keys() -> dict[str, str]:
    """Legacy shim: return {role: key} from .moot/actors.json OR .agents.json.

    Kept for the legacy provision path; the new adoption flow uses
    load_actors() / get_actor_key() directly.
    """
    new = load_actors()
    if new:
        return {k: v.get("api_key", "") for k, v in new.get("actors", {}).items()}
    legacy = Path(".agents.json")
    if legacy.exists():
        return json.loads(legacy.read_text())
    return {}


def cmd_config(args: object) -> None:
    """Handle `moot config show/set/focus`."""
    sub = getattr(args, "config_command", None)
    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)
    if sub == "show" or sub is None:
        print(f"API URL: {config.api_url}")
        print(f"Space ID: {config.space_id or '(not set)'}")
        print(f"Harness: {config.harness_type}")
        print(f"Roles: {', '.join(config.roles)}")
    elif sub == "set":
        key = getattr(args, "key")
        value = getattr(args, "value")
        print(f"TODO: set {key} = {value}")
    elif sub == "focus":
        space_id = getattr(args, "space_id")
        print(f"TODO: set focus space to {space_id}")
```

### § 6.2 `src/moot/launch.py`

One-line diff in `cmd_exec`:

```python
# BEFORE:
from moot.config import find_config, load_agent_keys
...
    keys = load_agent_keys()
    api_key = keys.get(role, "")

# AFTER:
from moot.config import find_config, get_actor_key
...
    api_key = get_actor_key(role)
```

No other changes in `launch.py`.

### § 6.3 `src/moot/scaffold.py` — full rewrite

Single-file replacement. The file ends up ~260 LOC. Impl pastes the following as the new `scaffold.py`:

```python
"""moot init — full provisioning flow.

Adopts the user's default-space keyless agents, rotates their keys,
writes .moot/actors.json, installs bundled skills / CLAUDE.md /
devcontainer with conflict-aware staging, and emits .moot/init-report.md.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from moot.auth import load_credential
from moot.config import ACTORS_JSON, MOOT_DIR
from moot.team_profile import (
    RoleProfile,
    TeamProfile,
    generate_moot_toml,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
DEVCONTAINER_TEMPLATE_DIR = TEMPLATES_DIR / "devcontainer"
SKILLS_TEMPLATE_DIR = TEMPLATES_DIR / "skills"
CLAUDE_MD_TEMPLATE = TEMPLATES_DIR / "CLAUDE.md"

GITIGNORE_ENTRIES = [".moot/", ".agents.json", ".env.local", ".worktrees/"]

BUNDLED_SKILLS = (
    "product-workflow",
    "spec-checklist",
    "leader-workflow",
    "librarian-workflow",
    "handoff",
    "verify",
    "doc-curation",
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def cmd_init(args: object) -> None:
    """Synchronous entry; delegates to async runner."""
    asyncio.run(_cmd_init_async(args))


async def _cmd_init_async(args: object) -> None:
    """Handle `moot init [--force|--update-suggestions|--adopt-fresh-install|--fresh]`."""
    # --fresh short-circuits to the legacy create-new-agents path
    if getattr(args, "fresh", False):
        from moot.provision import cmd_provision
        await cmd_provision(args)
        return

    force = getattr(args, "force", False)
    update_suggestions = getattr(args, "update_suggestions", False)
    adopt_fresh = getattr(args, "adopt_fresh_install", False)
    yes = getattr(args, "yes", False)

    # Warn if not in a git repo (D-GITREPO)
    if not Path(".git").exists():
        print(
            "Warning: this doesn't look like a git repository; "
            ".moot/ and .claude/skills/ won't be versioned."
        )

    # --update-suggestions: skip adoption, only refresh staged files
    if update_suggestions:
        await _update_suggestions_only()
        return

    actors_path = Path(ACTORS_JSON)
    if actors_path.exists() and not force and not adopt_fresh:
        print(
            f"Error: {actors_path} already exists.\n"
            f"Use `moot init --force` to rotate keys (invalidates the current set),\n"
            f"or `moot init --update-suggestions` to refresh staged suggestions only."
        )
        raise SystemExit(1)

    # Confirmation prompts (D-PROMPT)
    cred = load_credential()
    if not cred:
        print("Error: not logged in. Run 'moot login' first.")
        raise SystemExit(1)

    api_url = cred["api_url"]
    token = cred["token"]

    async with httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as client:
        # 1. Fetch actor + default space
        print(f"Using profile default (authenticated on {api_url})")
        actor, space_id, space_name = await _fetch_actor_and_space(client)
        print(f"Fetched your default space: {space_id} ({space_name})")

        # 2. Fetch keyless agents
        keyless = await _fetch_keyless_agents(client, space_id)
        if not keyless and not force:
            print(
                "Error: no keyless agents found in your default space.\n"
                "If you've run `moot init` before on this space, use "
                "`moot init --force` to rotate the existing keys."
            )
            raise SystemExit(1)

        print(f"Found {len(keyless)} keyless agents in default space:")
        for agent in keyless:
            print(f"  - {agent['display_name']:16s} ({agent['actor_id']})")

        if force and not yes:
            _prompt_or_exit(
                f"This will rotate keys for {len(keyless)} agents. "
                f"Currently-connected agents will disconnect. Continue? [y/N] "
            )
        if adopt_fresh and not yes:
            _prompt_or_exit(
                "This will overwrite CLAUDE.md, .claude/skills/, and "
                ".devcontainer/ with bundled content, potentially losing "
                "your local changes. Continue? [y/N] "
            )

        # 3. Rotate keys
        print("\nRotating keys for keyless agents...")
        adopted = await _rotate_keys(client, keyless, force=force)

    # 4. Persist actors.json
    _write_actors_json(
        space_id=space_id,
        space_name=space_name,
        api_url=api_url,
        adopted=adopted,
    )
    print(f"Wrote {ACTORS_JSON}              ({len(adopted)} agents, chmod 600)")

    # 5. Generate moot.toml from adopted team (D-TOML)
    _write_moot_toml_from_adopted(adopted=adopted, api_url=api_url)

    # 6. Update .gitignore
    _update_gitignore()

    # 7. Install skills, CLAUDE.md, devcontainer (with conflict staging or overwrite)
    conflicts = _install_bundles(
        adopted=adopted,
        space_id=space_id,
        space_name=space_name,
        api_url=api_url,
        overwrite=adopt_fresh,
    )

    # 8. Write init-report.md (D-REPORT)
    _write_init_report(
        space_id=space_id,
        space_name=space_name,
        api_url=api_url,
        adopted=adopted,
        conflicts=conflicts,
    )

    print("\nDone. See .moot/init-report.md for details and next steps.")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


async def _fetch_actor_and_space(
    client: httpx.AsyncClient,
) -> tuple[dict[str, Any], str, str]:
    """GET /api/actors/me → (actor_dict, default_space_id, default_space_name)."""
    resp = await client.get("/api/actors/me")
    if resp.status_code != 200:
        print(
            f"Error: could not fetch your account ({resp.status_code}). "
            f"Your credential may have expired — run `moot login` again."
        )
        raise SystemExit(1)
    actor = resp.json()
    space_id = actor.get("default_space_id")
    if not space_id:
        print("Error: your account has no default space. Contact support.")
        raise SystemExit(1)

    # Fetch space name (small convenience for the CLAUDE.md placeholder)
    space_resp = await client.get(f"/api/spaces/{space_id}")
    space_name = (
        space_resp.json().get("name", space_id)
        if space_resp.status_code == 200
        else space_id
    )
    return actor, space_id, space_name


async def _fetch_keyless_agents(
    client: httpx.AsyncClient, space_id: str
) -> list[dict[str, Any]]:
    """List participants and filter to keyless agents."""
    resp = await client.get(f"/api/spaces/{space_id}/participants")
    if resp.status_code != 200:
        print(f"Error: could not list participants ({resp.status_code})")
        raise SystemExit(1)
    participants = resp.json()
    if isinstance(participants, dict):
        participants = participants.get("participants", [])
    return [
        p
        for p in participants
        if p.get("participant_type") == "agent"
        and p.get("api_key_prefix") is None
    ]


async def _rotate_keys(
    client: httpx.AsyncClient,
    agents: list[dict[str, Any]],
    force: bool = False,
) -> dict[str, dict[str, str]]:
    """Rotate keys for each agent in order. Returns {role_lower: {...}}."""
    adopted: dict[str, dict[str, str]] = {}
    headers = {"X-Force-Rotate": "true"} if force else {}
    for agent in agents:
        actor_id = agent["actor_id"]
        display_name = agent["display_name"]
        role_key = display_name.lower().replace(" ", "_")
        resp = await client.post(
            f"/api/actors/{actor_id}/rotate-key",
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            print(
                f"\nError: rotate-key failed for {display_name} "
                f"({resp.status_code})"
            )
            raise SystemExit(1)
        data = resp.json()
        adopted[role_key] = {
            "actor_id": actor_id,
            "api_key": data.get("api_key", ""),
            "display_name": display_name,
        }
        print(f"  {display_name:16s} ✓")
    return adopted


# ---------------------------------------------------------------------------
# Filesystem writers
# ---------------------------------------------------------------------------


def _write_actors_json(
    *,
    space_id: str,
    space_name: str,
    api_url: str,
    adopted: dict[str, dict[str, str]],
) -> None:
    """Write .moot/actors.json with 0o600 perms under 0o700 parent."""
    moot_dir = Path(MOOT_DIR)
    moot_dir.mkdir(exist_ok=True)
    os.chmod(moot_dir, 0o700)

    content = {
        "space_id": space_id,
        "space_name": space_name,
        "api_url": api_url,
        "actors": adopted,
    }
    actors_path = Path(ACTORS_JSON)
    actors_path.write_text(json.dumps(content, indent=2))
    os.chmod(actors_path, 0o600)


def _write_moot_toml_from_adopted(
    *,
    adopted: dict[str, dict[str, str]],
    api_url: str,
) -> None:
    """Generate moot.toml from adopted team data (D-TOML)."""
    toml_path = Path("moot.toml")
    if toml_path.exists():
        return  # Idempotent — never overwrite an existing moot.toml
    team_name = _infer_team_template(list(adopted.keys()))
    profile = TeamProfile(
        name=team_name,
        description="Adopted from default space",
        version="1.0",
        origin="moot-init-adoption",
    )
    for role_key, info in adopted.items():
        profile.roles.append(
            RoleProfile(
                name=role_key,
                display_name=info["display_name"],
                harness="claude-code",
            )
        )
    content = generate_moot_toml(profile, api_url)
    toml_path.write_text(content)
    print(f"Wrote moot.toml                ({len(adopted)} roles, template={team_name})")


def _infer_team_template(roles: list[str]) -> str:
    """Infer team template name from the adopted role set (D9)."""
    lower = {r.lower() for r in roles}
    if {"product", "spec", "implementation", "qa", "librarian"} <= lower:
        return "loop-5"
    if {"product", "spec", "implementation", "qa"} <= lower:
        return "loop-4"
    return "custom"


def _update_gitignore() -> None:
    """Append .moot/ (and legacy entries) to .gitignore."""
    gitignore = Path(".gitignore")
    existing = gitignore.read_text() if gitignore.exists() else ""
    additions = [e for e in GITIGNORE_ENTRIES if e not in existing]
    if additions:
        with open(gitignore, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("# moot\n")
            for entry in additions:
                f.write(f"{entry}\n")
        print(f"Updated .gitignore             ({len(additions)} entries added)")


def _install_bundles(
    *,
    adopted: dict[str, dict[str, str]],
    space_id: str,
    space_name: str,
    api_url: str,
    overwrite: bool,
) -> dict[str, list[str]]:
    """Install skills, CLAUDE.md, devcontainer. Returns conflict map."""
    conflicts: dict[str, list[str]] = {"skills": [], "claude_md": [], "devcontainer": []}

    # Skills
    print("\nInstalling .claude/skills/:")
    for skill in BUNDLED_SKILLS:
        target_dir = Path(f".claude/skills/{skill}")
        src_dir = SKILLS_TEMPLATE_DIR / skill
        if target_dir.is_dir() and not overwrite:
            staged = Path(f"{MOOT_DIR}/suggested-skills/{skill}")
            staged.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_dir / "SKILL.md", staged / "SKILL.md")
            conflicts["skills"].append(skill)
            print(f"  {skill + '/':24s} ⚠ exists — staged at .moot/suggested-skills/{skill}/")
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_dir / "SKILL.md", target_dir / "SKILL.md")
            print(f"  {skill + '/':24s} ✓ {'overwritten' if target_dir.exists() and overwrite else 'new'}")

    # CLAUDE.md (with placeholder substitution)
    claude_path = Path("CLAUDE.md")
    placeholders = {
        "{project_name}": Path.cwd().name,
        "{space_id}": space_id,
        "{space_name}": space_name,
        "{team_template}": _infer_team_template(list(adopted.keys())),
        "{api_url}": api_url,
    }
    template_text = CLAUDE_MD_TEMPLATE.read_text()
    for k, v in placeholders.items():
        template_text = template_text.replace(k, v)

    if claude_path.exists() and not overwrite:
        staged = Path(f"{MOOT_DIR}/suggested-CLAUDE.md")
        staged.write_text(template_text)
        conflicts["claude_md"].append("CLAUDE.md")
        print("\nCLAUDE.md already exists — staged at .moot/suggested-CLAUDE.md")
    else:
        claude_path.write_text(template_text)
        print(f"\nInstalling CLAUDE.md           (parameterized: project_name → {placeholders['{project_name}']})")

    # Devcontainer
    devcontainer_dir = Path(".devcontainer")
    src_devcontainer = DEVCONTAINER_TEMPLATE_DIR
    if devcontainer_dir.exists() and not overwrite:
        staged = Path(f"{MOOT_DIR}/suggested-devcontainer")
        staged.mkdir(parents=True, exist_ok=True)
        for src_file in src_devcontainer.iterdir():
            dest = staged / src_file.name
            shutil.copy2(src_file, dest)
            if src_file.suffix == ".sh":
                dest.chmod(
                    dest.stat().st_mode
                    | stat.S_IEXEC
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
        conflicts["devcontainer"].append(".devcontainer/")
        print(".devcontainer/ already exists — staged at .moot/suggested-devcontainer/")
    else:
        devcontainer_dir.mkdir(exist_ok=True)
        for src_file in src_devcontainer.iterdir():
            dest = devcontainer_dir / src_file.name
            shutil.copy2(src_file, dest)
            if src_file.suffix == ".sh":
                dest.chmod(
                    dest.stat().st_mode
                    | stat.S_IEXEC
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
        print(f"Installing .devcontainer/      ({len(list(devcontainer_dir.iterdir()))} files)")

    return conflicts


def _write_init_report(
    *,
    space_id: str,
    space_name: str,
    api_url: str,
    adopted: dict[str, dict[str, str]],
    conflicts: dict[str, list[str]],
) -> None:
    """Write .moot/init-report.md (D-REPORT)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# moot init report",
        "",
        f"Generated {now}.",
        f"Default space: {space_id} ({space_name})",
        f"Backend: {api_url}",
        "",
        "## Mechanical setup (done)",
        "",
        f"- Rotated keys for {len(adopted)} agents: "
        f"{', '.join(a['display_name'] for a in adopted.values())}",
        f"- Wrote `{ACTORS_JSON}` (chmod 600)",
        "- Updated `.gitignore` with `.moot/` entry",
        "",
        "## Files ready to use directly",
        "",
    ]
    installed_skills = [s for s in BUNDLED_SKILLS if s not in conflicts["skills"]]
    for skill in installed_skills:
        lines.append(f"- `.claude/skills/{skill}/SKILL.md`")
    if not conflicts["claude_md"]:
        lines.append("- `CLAUDE.md`")
    if not conflicts["devcontainer"]:
        lines.append("- `.devcontainer/`")

    has_conflicts = any(conflicts.values())
    if has_conflicts:
        lines += [
            "",
            "## Files that need your agent's judgment (staged under .moot/suggested-*/)",
            "",
        ]
        if conflicts["claude_md"]:
            lines += [
                "### `.moot/suggested-CLAUDE.md`",
                "",
                "Your existing `CLAUDE.md` describes your project. The suggestion adds "
                "Moot-specific workflow discipline. Ask your agent to pick what to "
                "merge, what to put in a separate `.claude/MOOT.md`, and what to skip.",
                "",
            ]
        for skill in conflicts["skills"]:
            lines += [
                f"### `.moot/suggested-skills/{skill}/`",
                "",
                f"You already have a `.claude/skills/{skill}/` directory. The name "
                "collides but the content may not. Ask your agent to diff them and "
                "decide whether to merge or rename.",
                "",
            ]
        if conflicts["devcontainer"]:
            lines += [
                "### `.moot/suggested-devcontainer/`",
                "",
                "Your existing `.devcontainer/` reflects your dev environment. The "
                "suggestion is Moot's default devcontainer for running agents. Ask "
                "your agent whether to integrate.",
                "",
            ]

    lines += [
        "## Next step",
        "",
        (
            "Once your agent has reviewed any staged suggestions above, "
            "run `moot up` to bring your agent team online."
            if has_conflicts
            else "Run `moot up` to bring your agent team online."
        ),
        "",
    ]

    report_path = Path(f"{MOOT_DIR}/init-report.md")
    report_path.write_text("\n".join(lines))


async def _update_suggestions_only() -> None:
    """`moot init --update-suggestions`: refresh .moot/suggested-*/ only."""
    actors_path = Path(ACTORS_JSON)
    if not actors_path.exists():
        print(
            f"Error: {ACTORS_JSON} not found. Run `moot init` first."
        )
        raise SystemExit(1)
    data = json.loads(actors_path.read_text())
    conflicts = _install_bundles(
        adopted=data.get("actors", {}),
        space_id=data.get("space_id", ""),
        space_name=data.get("space_name", ""),
        api_url=data.get("api_url", ""),
        overwrite=False,
    )
    _write_init_report(
        space_id=data.get("space_id", ""),
        space_name=data.get("space_name", ""),
        api_url=data.get("api_url", ""),
        adopted=data.get("actors", {}),
        conflicts=conflicts,
    )
    print("\nDone. Staged suggestions refreshed.")


def _prompt_or_exit(prompt: str) -> None:
    """Print prompt, read one line; exit 0 if response is not y/yes."""
    try:
        response = input(prompt).strip().lower()
    except EOFError:
        response = ""
    if response not in ("y", "yes"):
        print("Aborted.")
        raise SystemExit(0)
```

### § 6.4 `src/moot/cli.py`

Add flags to the `init` subparser and the `config provision` subparser. Dispatch `init` through `asyncio.run()`:

```python
# BEFORE (lines 33-40):
init_p = sub.add_parser("init", help="Scaffold project for agent team")
init_p.add_argument("--api-url", default=None)
init_p.add_argument("--roles", default=None, help="Comma-separated roles")
init_p.add_argument(
    "--template", "-t",
    default=None,
    help="Team template name or path (default: loop-4). Built-in: loop-3, loop-4, loop-4-observer, loop-4-parallel, loop-4-split-leader",
)

# AFTER:
init_p = sub.add_parser("init", help="Provision agents and install Moot workflow bundles")
init_p.add_argument("--api-url", default=None, help="Moot API URL (overrides credential)")
init_p.add_argument(
    "--force",
    action="store_true",
    help="Rotate keys for already-adopted agents (destructive)",
)
init_p.add_argument(
    "--update-suggestions",
    action="store_true",
    help="Refresh .moot/suggested-*/ staged files from bundled templates; no key rotation",
)
init_p.add_argument(
    "--adopt-fresh-install",
    action="store_true",
    help="Overwrite CLAUDE.md / .claude/skills/ / .devcontainer/ unconditionally",
)
init_p.add_argument(
    "--fresh",
    action="store_true",
    help="Legacy path: create new agents in a new tenant (redirects to `moot config provision --fresh`)",
)
init_p.add_argument(
    "--yes", "-y",
    action="store_true",
    help="Skip all confirmation prompts",
)
# Legacy flags kept for the `moot init --fresh` path
init_p.add_argument("--roles", default=None, help="Comma-separated roles (--fresh only)")
init_p.add_argument(
    "--template", "-t",
    default=None,
    help="Team template name (--fresh only). Built-in: loop-3, loop-4, loop-4-observer, loop-4-parallel, loop-4-split-leader",
)
```

And in the `config provision` subparser (lines 42-50):

```python
# BEFORE:
config_sub.add_parser("provision", help="Register actors, write .agents.json")

# AFTER:
prov_p = config_sub.add_parser("provision", help="Register actors")
prov_p.add_argument(
    "--fresh",
    action="store_true",
    help="Create new agents in a new tenant (writes .moot/agents-fresh.json)",
)
```

And update the `init` dispatch to use `asyncio.run()`:

```python
# BEFORE (lines 80-82):
elif args.command == "init":
    from moot.scaffold import cmd_init
    cmd_init(args)

# AFTER:
elif args.command == "init":
    from moot.scaffold import cmd_init
    cmd_init(args)   # cmd_init wraps asyncio.run() internally
```

(The `cmd_init` sync wrapper in scaffold.py means the dispatcher doesn't need to change — kept intentionally so Impl can smoke-test without touching both files.)

### § 6.5 `src/moot/provision.py`

Honor `--fresh`, write to new location:

```python
"""moot config provision — legacy create-new-agents path."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

from moot.auth import load_credential
from moot.config import MOOT_DIR, find_config


async def cmd_provision(args: object) -> None:
    """Register agents and write the actors file.

    Default: writes .agents.json (legacy).
    --fresh:  writes .moot/agents-fresh.json (per D3).
    """
    cred = load_credential()
    if not cred:
        print("Error: not logged in. Run 'moot login' first.")
        raise SystemExit(1)

    config = find_config()
    if not config:
        print("Error: no moot.toml found. Run 'moot init' first.")
        raise SystemExit(1)

    fresh = getattr(args, "fresh", False)
    target_path = (
        Path(f"{MOOT_DIR}/agents-fresh.json") if fresh else Path(".agents.json")
    )
    if fresh:
        Path(MOOT_DIR).mkdir(exist_ok=True)

    api_url = config.api_url
    token = cred["token"]

    async with httpx.AsyncClient(
        base_url=api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    ) as client:
        me_resp = await client.get("/api/actors/me")
        if me_resp.status_code != 200:
            print(f"Error: could not get user info ({me_resp.status_code})")
            raise SystemExit(1)
        me = me_resp.json()
        tenant_id = me.get("tenant_id")
        if not tenant_id:
            print("Error: user has no tenant")
            raise SystemExit(1)

        agent_keys: dict[str, str] = {}
        for role, agent_config in config.agents.items():
            resp = await client.post(
                f"/api/tenants/{tenant_id}/agents",
                json={
                    "display_name": agent_config.display_name,
                    "agent_profile": agent_config.profile,
                },
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                agent_keys[role] = data.get("api_key", "")
                print(f"Provisioned {role}: {data.get('actor_id', '?')}")
            else:
                print(f"Warning: failed to provision {role} ({resp.status_code})")

        target_path.write_text(json.dumps(agent_keys, indent=2))
        print(f"Wrote {target_path} ({len(agent_keys)} agents)")
```

### § 6.6 Devcontainer runner scripts

Three files with near-identical edits. For `run-moot-mcp.sh`, the diff is:

```bash
# BEFORE:
ROLE="${CONVO_ROLE:-implementation}"
AGENTS_FILE=".agents.json"
...
# Read API key from .agents.json
if [ -f "$PROJECT_ROOT/$AGENTS_FILE" ]; then
    KEY=$(python3 -c "
import json, sys
with open('$PROJECT_ROOT/$AGENTS_FILE') as f:
    keys = json.load(f)
print(keys.get('$ROLE', ''))
" 2>/dev/null)
    if [ -n "$KEY" ]; then
        export CONVO_API_KEY="$KEY"
    else
        echo "WARNING: No API key for role '$ROLE' in $AGENTS_FILE" >&2
    fi
fi

# AFTER:
ROLE="${CONVO_ROLE:-implementation}"
ACTORS_FILE=".moot/actors.json"
...
# Read API key from .moot/actors.json (nested schema)
if [ -f "$PROJECT_ROOT/$ACTORS_FILE" ]; then
    KEY=$(python3 -c "
import json
with open('$PROJECT_ROOT/$ACTORS_FILE') as f:
    data = json.load(f)
entry = data.get('actors', {}).get('$ROLE', {})
print(entry.get('api_key', ''))
" 2>/dev/null)
    if [ -n "$KEY" ]; then
        export CONVO_API_KEY="$KEY"
    else
        echo "WARNING: No API key for role '$ROLE' in $ACTORS_FILE" >&2
    fi
fi
```

`run-moot-channel.sh` and `run-moot-notify.sh` take the same substitution block. Impl: apply the rename sweep to all three files in one commit. No other changes.

### § 6.7 Skill transform discipline

Impl transforms each of the 7 convo source files into a bundled artifact under `src/moot/templates/skills/<name>/SKILL.md`, applying the rules from `/workspaces/convo/docs/ops/skill-release-transform-checklist.md`. Short version of the rules:

**Strip categorically:**
- "Pat" → "the team lead" / "you" (never a substitute name)
- Convo-repo paths: `backend/`, `frontend/`, `docs/specs/<slug>.md`, `.claude/skills/`, `docker-compose.yml`, `convo-qa-backend-1` — replace with abstract equivalents or delete
- Arch run history: "Arch Run 8", "R5", "Phase 9.5 Run B" — strip the narrative, keep the rule the incident motivated
- Feature slugs: "frictionless-onboarding", "agent-connection-state", etc. — replace with abstract examples or delete
- Commit SHAs: `0770584`, `dc1589d`, etc. — strip
- `feedback_*.md` memory references — strip; if the rule is load-bearing, restate it inline
- Specific incidents with dates — strip narrative, keep rule
- Convo channel/space identifiers: `spc_*`, `agt_*`, `evt_*` — strip
- References to "Convo" the system / "the convo project" — replace with "Moot" / "your project" / "this project"

**Preserve carefully:**
- Workflow discipline (§ 13 pre-grounding, empty-diff baseline shortcut, retros-in handoff, FK cascade rule, schema version bump sweep)
- Role definitions at the abstract level (Product, Leader, Spec, Impl, QA, Librarian)
- Rule content AND rationale — when a rule has an embedded "why", keep both; strip only the convo-specific anecdote
- `message_type` taxonomy (10 values)
- Channel threading discipline
- MCP response profile guidance (`detail=minimal/standard/full`)

**Genericize (rewrite, don't delete):**
- Test access commands (convo's `docker exec convo-qa-backend-1 ...`) → abstract placeholder
- Tech stack section → TODO placeholder
- Running components section → TODO placeholder
- API endpoint references → strip or genericize

**Acceptance check** (Impl runs after each transform):

```bash
grep -n "Pat\|convo-\|/workspaces/convo\|feedback_\|agt_\|evt_\|spc_\|arch run\|R[0-9]\|docker compose\|convo_key_\|gemoot" src/moot/templates/skills/<name>/SKILL.md
```

Allowed hits: the literal string `convo_key_` is a user-facing artifact from the Run Q allowlist (appears in sample credential snippets); double-check each hit against the preservation table in § 3.2. Everything else should produce zero hits.

**Frontmatter:** each transformed file preserves the YAML frontmatter (`---\nname: ...\ndescription: ...\n---`) from the convo source, possibly with a description refresh if the original described convo-specific behavior.

**Size sanity:** transformed files will typically be shorter than their source (stripping outweighs rewriting). Rough targets:

| Skill | Source LOC | Target LOC (rough) |
|---|---|---|
| `product-workflow` | 79 | 65–75 |
| `spec-checklist` | 106 | 85–100 |
| `leader-workflow` | 150 | 120–140 |
| `librarian-workflow` | 50 | 40–50 |
| `handoff` | 46 | 40–46 |
| `verify` | 68 | 55–65 |
| `doc-curation` | 81 | 65–80 |

Impl treats these as orienteering only — do not pad or trim to hit a LOC number. The acceptance check is the real gate.

### § 6.8 `src/moot/templates/CLAUDE.md`

One-shot copy from `/workspaces/convo/.claude/CLAUDE.md.mootup-template` (pre-transformed, 235 lines at `c85c431`). Impl:

```bash
cp /workspaces/convo/.claude/CLAUDE.md.mootup-template \
   src/moot/templates/CLAUDE.md
```

No re-transform, no editorial pass. The source IS the release artifact.

### § 6.9 `README.md` update

Preserve Run Q allowlist strings (`[convo]` TOML section header, `convo_key_` / `convo_...` in the snippet samples). Replace the Quick Start block (lines 23–43) with:

```markdown
## Quick Start

```bash
# 1. Install and authenticate
pip install mootup
moot login
# Paste your personal access token when prompted.

# 2. Provision your default-space team in this repo
cd ~/src/my-project
moot init

# 3. Bring the agents online
moot up

# 4. Watch an agent work
moot attach product
```

After `moot init`:

- `.moot/actors.json` — your rotated agent keys (chmod 600, gitignored)
- `.moot/init-report.md` — what was installed, what needs your coding agent's review
- `CLAUDE.md`, `.claude/skills/`, `.devcontainer/` — installed directly if absent, staged under `.moot/suggested-*/` if pre-existing

If `CLAUDE.md` or `.claude/skills/` already exist, `moot init` routes the bundled content to `.moot/suggested-*/` and writes a report file for your AI coding agent to reconcile. Ask your agent: *"Read `.moot/init-report.md` and help me integrate the suggested files."*

Press `Ctrl+B D` to detach from tmux. `moot down` stops all agents.
```

Also update the lower table (line ~93 `| moot config provision |`):

```markdown
| `moot init`             | Adopt default-space agents, install skills + CLAUDE.md + devcontainer |
| `moot init --force`     | Re-rotate keys on an already-adopted repo                              |
| `moot init --update-suggestions` | Refresh `.moot/suggested-*/` without touching keys             |
| `moot init --adopt-fresh-install` | Overwrite user files with bundled content (escape hatch)      |
| `moot config provision --fresh`  | Legacy: create new agents in a new tenant                     |
```

And line ~146 (the `.agents.json` mention): replace with a note about `.moot/actors.json` and mention that `.agents.json` is legacy (only written by `moot config provision`).

---

## § 7 Test plan

Spec-required tests (Impl gate). QA extends at its discretion per `feedback_test_split.md`.

### § 7.1 Test dependencies

**Already present in `[dependency-groups].test`:** `pytest`, `pytest-asyncio` (mode=auto), `respx`, `tomli-w` (present? confirm below).

**Verify before starting:** open `pyproject.toml`; if `respx` is missing, Impl adds it under `[dependency-groups].test` and re-runs `uv sync --group test`. `respx` was already added for Run Q's interactive-login HTTP mocks, so it should be there.

**Annotation guardrail (reiterating Run Q § 7.5):** every new test function signature that takes `monkeypatch` uses `monkeypatch: pytest.MonkeyPatch` (NOT `monkeypatch: object`). `import pytest` at top of each test file. Run R does NOT inherit any of the 6 `test_scaffold.py` errors that survived Run Q.

### § 7.2 `tests/test_scaffold.py` — rewrite around the new flow

Replace the entire current file contents. The new file covers:

#### T-init-1. `test_init_greenfield_rotates_and_installs`

Mock backend with respx: `GET /api/actors/me`, `GET /api/spaces/{id}`, `GET /api/spaces/{id}/participants`, 4× `POST /api/actors/{id}/rotate-key`. Use tmp_path as cwd, empty git repo. Assert:
- `.moot/actors.json` exists, mode 0600, parent mode 0700
- JSON shape matches D2 schema, 4 actors keyed by lowercase role names, each entry has `actor_id` + `api_key` + `display_name`
- `moot.toml` generated from adopted data; parses; has `[convo]` + 4 `[agents.*]` sections
- `.claude/skills/<each>/SKILL.md` for all 7 skills
- `CLAUDE.md` exists, no `{project_name}` unfilled
- `.devcontainer/` exists with 5 files
- `.gitignore` contains `.moot/`
- `.moot/init-report.md` exists, contains "Mechanical setup (done)" section

```python
import json
import os
import stat
from pathlib import Path

import pytest
import respx
from httpx import Response

from moot.scaffold import cmd_init
from moot.config import ACTORS_JSON


def _stub_backend(respx_mock: respx.Router, api_url: str) -> None:
    """Stub the 4-call happy-path flow."""
    respx_mock.get(f"{api_url}/api/actors/me").mock(
        return_value=Response(
            200,
            json={
                "actor_id": "agt_user_1",
                "display_name": "Test User",
                "default_space_id": "spc_test_1",
            },
        )
    )
    respx_mock.get(f"{api_url}/api/spaces/spc_test_1").mock(
        return_value=Response(200, json={"space_id": "spc_test_1", "name": "Test Space"})
    )
    respx_mock.get(f"{api_url}/api/spaces/spc_test_1/participants").mock(
        return_value=Response(
            200,
            json=[
                {
                    "actor_id": f"agt_{role.lower()}_1",
                    "display_name": role,
                    "participant_type": "agent",
                    "api_key_prefix": None,
                }
                for role in ("Product", "Spec", "Implementation", "QA")
            ],
        )
    )
    for role in ("product", "spec", "implementation", "qa"):
        respx_mock.post(f"{api_url}/api/actors/agt_{role}_1/rotate-key").mock(
            return_value=Response(
                200,
                json={"api_key": f"convo_key_live_{role}"},
            )
        )


def _stub_credential(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import moot.auth as auth_mod

    cred_dir = tmp_path / ".moot-home"
    cred_file = cred_dir / "credentials"
    monkeypatch.setattr(auth_mod, "CRED_DIR", cred_dir)
    monkeypatch.setattr(auth_mod, "CRED_FILE", cred_file)
    auth_mod.store_credential(
        token="mootup_pat_test",
        api_url="https://mootup.io",
        user_id="agt_user_1",
    )


@respx.mock
def test_init_greenfield_rotates_and_installs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Greenfield moot init: 4 HTTP calls, skills + CLAUDE.md + devcontainer installed, actors.json written."""
    monkeypatch.chdir(tmp_path)
    Path(".git").mkdir()  # suppress the warning
    _stub_credential(monkeypatch, tmp_path)
    _stub_backend(respx.mock, "https://mootup.io")

    class Args:
        force = False
        update_suggestions = False
        adopt_fresh_install = False
        fresh = False
        yes = False

    cmd_init(Args())

    actors_path = tmp_path / ACTORS_JSON
    assert actors_path.exists()
    assert stat.S_IMODE(os.stat(actors_path).st_mode) == 0o600
    data = json.loads(actors_path.read_text())
    assert data["space_id"] == "spc_test_1"
    assert data["api_url"] == "https://mootup.io"
    assert set(data["actors"].keys()) == {"product", "spec", "implementation", "qa"}
    assert data["actors"]["product"]["api_key"] == "convo_key_live_product"
    assert data["actors"]["product"]["display_name"] == "Product"

    assert (tmp_path / "moot.toml").exists()
    for skill in (
        "product-workflow", "spec-checklist", "leader-workflow",
        "librarian-workflow", "handoff", "verify", "doc-curation",
    ):
        assert (tmp_path / ".claude" / "skills" / skill / "SKILL.md").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".devcontainer" / "devcontainer.json").exists()
    assert (tmp_path / ".gitignore").exists()
    assert ".moot/" in (tmp_path / ".gitignore").read_text()
    assert (tmp_path / ".moot" / "init-report.md").exists()
    report = (tmp_path / ".moot" / "init-report.md").read_text()
    assert "Mechanical setup (done)" in report
```

#### T-init-2. `test_init_conflict_stages_claude_md`

Pre-create `CLAUDE.md` with known content. Run moot init. Assert:
- `CLAUDE.md` bytes are unchanged from the pre-state
- `.moot/suggested-CLAUDE.md` exists and contains the bundled template (substituted)
- `.moot/init-report.md` contains `### .moot/suggested-CLAUDE.md` section
- other skills (which don't collide) still land directly at `.claude/skills/<name>/SKILL.md`

#### T-init-3. `test_init_conflict_stages_skill`

Pre-create `.claude/skills/spec-checklist/SKILL.md` with user content. Run moot init. Assert:
- `.claude/skills/spec-checklist/SKILL.md` bytes unchanged
- `.moot/suggested-skills/spec-checklist/SKILL.md` contains the bundled copy
- Other skills land directly (e.g. `.claude/skills/handoff/SKILL.md`)
- Conflict report section names `spec-checklist` specifically

#### T-init-4. `test_init_conflict_stages_devcontainer`

Pre-create `.devcontainer/devcontainer.json` with user content. Run moot init. Assert:
- user's `.devcontainer/` unchanged
- `.moot/suggested-devcontainer/` contains all 5 bundled files
- Conflict report section names `.devcontainer/`

#### T-init-5. `test_init_refuses_without_force_when_actors_exist`

Pre-create `.moot/actors.json` with dummy content. Run moot init (no flags). Assert:
- SystemExit with code 1
- `.moot/actors.json` byte-identical to pre-state
- No HTTP calls made (respx mock with `assert_all_called=False` confirms)

#### T-init-6. `test_init_force_rotates_keys`

Pre-create `.moot/actors.json`. Mock backend. Run with `force=True, yes=True`. Assert:
- `.moot/actors.json` rewritten with fresh keys
- `X-Force-Rotate: true` header was present on each rotate-key POST (respx route assertions)
- User-owned CLAUDE.md / skills / devcontainer content unchanged

#### T-init-7. `test_init_update_suggestions_no_network`

Pre-create `.moot/actors.json` with valid schema. Pre-create `CLAUDE.md`. Run with `update_suggestions=True`. Assert:
- No HTTP calls (respx mock assertion with zero routes configured)
- `.moot/suggested-CLAUDE.md` updated from the bundled template
- `.moot/actors.json` byte-identical
- `.moot/init-report.md` written

#### T-init-8. `test_init_adopt_fresh_install_overwrites`

Pre-create `CLAUDE.md` with user content. Run with `adopt_fresh_install=True, yes=True`. Mock backend. Assert:
- `CLAUDE.md` byte-matches the bundled template (user content gone)
- `.moot/suggested-CLAUDE.md` does NOT exist (no staging)
- `.moot/actors.json` written

#### T-init-9. `test_init_rotate_key_failure_does_not_persist`

Mock `GET /api/actors/me` OK, participant list with 4 agents, `POST rotate-key` for 1st agent returns 500. Run moot init. Assert:
- SystemExit with code 1
- `.moot/actors.json` does NOT exist on disk
- Error message names the failing role

#### T-init-10. `test_init_warns_on_non_git_repo`

Run moot init in a tmp_path without `.git/`. Capture stdout. Assert the warning line is present AND the rest of the flow still succeeds.

#### T-init-11. `test_init_placeholder_substitution`

After a successful greenfield init, read `CLAUDE.md` and assert no unfilled `{project_name}`, `{space_id}`, `{space_name}`, `{team_template}`, `{api_url}` placeholders. Also assert `{project_name}` was substituted to the cwd name.

#### T-init-12. `test_init_infer_team_template_loop4`

Unit test on `_infer_team_template(["product","spec","implementation","qa"])` → `"loop-4"`. And `"loop-5"` for the 5-role set. And `"custom"` for a mismatch.

### § 7.3 `tests/test_templates.py` — flip rename assertions

Update `test_runner_reads_agents_json` (current name is a misnomer after the rename) → rename to `test_runner_reads_actors_json`:

```python
def test_runner_reads_actors_json() -> None:
    """Runner scripts reference .moot/actors.json (nested shape), not .agents.json."""
    for script_name in ("run-moot-mcp.sh", "run-moot-channel.sh", "run-moot-notify.sh"):
        content = (DEVCONTAINER_TEMPLATE_DIR / script_name).read_text()
        assert ".moot/actors.json" in content, (
            f"{script_name} should reference .moot/actors.json"
        )
        assert ".agents.json" not in content, (
            f"{script_name} should not reference .agents.json (post-Run-R)"
        )
        assert "data.get('actors'" in content, (
            f"{script_name} should parse the nested actors.json schema"
        )
```

Update `test_runner_scripts_no_convo_paths` — `forbidden` list currently includes `.actors.json` which will be present in the new scripts. Remove `.actors.json` from `forbidden` (it's now required) and add `.agents.json` instead:

```python
forbidden = [
    "/workspaces/convo",
    "convo-venv",
    ".agents.json",  # post-Run-R: renamed to .moot/actors.json
    "gemoot.com",
]
```

Add a new test over the skills bundle:

```python
def test_skills_bundle_complete() -> None:
    """All 7 bundled skills exist under templates/skills/ after Run R install."""
    from moot.scaffold import SKILLS_TEMPLATE_DIR, BUNDLED_SKILLS
    for skill in BUNDLED_SKILLS:
        skill_md = SKILLS_TEMPLATE_DIR / skill / "SKILL.md"
        assert skill_md.exists(), f"{skill}/SKILL.md missing from bundle"
        content = skill_md.read_text()
        # Transform acceptance: no convo-specific strings
        forbidden = [
            "/workspaces/convo",
            "Pat",
            "feedback_",
            "Arch Run",
            "agt_",
            "evt_",
            "spc_",
            "docker exec convo-",
        ]
        for pattern in forbidden:
            assert pattern not in content, (
                f"{skill}/SKILL.md contains forbidden pattern: {pattern}"
            )
```

**Note on false positives:** the `convo_key_` literal may still appear in some bundled skills (e.g., if a skill shows a sample API key). That's part of the Run Q allowlist — do NOT add `convo_key_` to the forbidden list.

### § 7.4 `tests/test_config.py` — new loader tests

Add these four tests at the bottom of the existing file:

```python
def test_actors_json_constant() -> None:
    """ACTORS_JSON constant points at .moot/actors.json."""
    from moot.config import ACTORS_JSON
    assert ACTORS_JSON == ".moot/actors.json"


def test_load_actors_returns_none_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    from moot.config import load_actors
    assert load_actors() is None


def test_load_actors_parses_nested_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".moot").mkdir()
    (tmp_path / ".moot" / "actors.json").write_text(json.dumps({
        "space_id": "spc_1",
        "space_name": "Test",
        "api_url": "https://mootup.io",
        "actors": {
            "product": {
                "actor_id": "agt_1",
                "api_key": "convo_key_p",
                "display_name": "Product",
            }
        }
    }))
    from moot.config import load_actors
    data = load_actors()
    assert data is not None
    assert data["space_id"] == "spc_1"
    assert data["actors"]["product"]["api_key"] == "convo_key_p"


def test_get_actor_key_returns_role_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".moot").mkdir()
    (tmp_path / ".moot" / "actors.json").write_text(json.dumps({
        "space_id": "spc_1",
        "space_name": "",
        "api_url": "",
        "actors": {
            "product": {"actor_id": "a", "api_key": "convo_key_p", "display_name": "Product"},
            "qa": {"actor_id": "a", "api_key": "convo_key_q", "display_name": "QA"},
        }
    }))
    from moot.config import get_actor_key
    assert get_actor_key("product") == "convo_key_p"
    assert get_actor_key("qa") == "convo_key_q"
    assert get_actor_key("missing") == ""
```

(Add `import json`, `import pytest`, and `from pathlib import Path` imports at the top of `test_config.py` if not already present — see § 11.)

### § 7.5 `tests/test_security.py` — accept new gitignore entry

Update `test_init_adds_agents_json_to_gitignore` (or whatever the assertion is — Impl inspects the file and flips the expected value):

```python
# BEFORE (approximate):
assert ".agents.json" in gitignore, "Agent keys file must be gitignored"

# AFTER:
assert ".moot/" in gitignore, ".moot/ directory must be gitignored (contains actors.json with keys)"
assert ".agents.json" in gitignore, "legacy .agents.json still gitignored for --fresh path"
```

### § 7.6 `tests/test_provision.py` — new `--fresh` test

Add one test that runs `cmd_provision` with `args.fresh=True`, mocks the backend with respx (`GET /api/actors/me` returns `tenant_id`, `POST /api/tenants/{id}/agents` returns 4 dummy keys), and asserts the output file is `.moot/agents-fresh.json` (NOT `.agents.json`):

```python
@respx.mock
def test_provision_fresh_writes_moot_agents_fresh_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import moot.auth as auth_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(auth_mod, "CRED_DIR", tmp_path / ".cred")
    monkeypatch.setattr(auth_mod, "CRED_FILE", tmp_path / ".cred" / "credentials")
    auth_mod.store_credential(
        token="mootup_pat_test",
        api_url="https://mootup.io",
        user_id="agt_user",
    )
    # Minimal moot.toml
    (tmp_path / "moot.toml").write_text(
        '[convo]\napi_url = "https://mootup.io"\n'
        '[agents.product]\ndisplay_name = "Product"\n'
        '[harness]\ntype = "claude-code"\n'
    )

    respx.get("https://mootup.io/api/actors/me").mock(
        return_value=Response(200, json={"actor_id": "agt_u", "tenant_id": "ten_1"})
    )
    respx.post("https://mootup.io/api/tenants/ten_1/agents").mock(
        return_value=Response(201, json={"actor_id": "agt_p", "api_key": "convo_key_fresh"})
    )

    from moot.provision import cmd_provision

    class Args:
        fresh = True

    asyncio.run(cmd_provision(Args()))

    fresh_file = tmp_path / ".moot" / "agents-fresh.json"
    assert fresh_file.exists()
    data = json.loads(fresh_file.read_text())
    assert data["product"] == "convo_key_fresh"
    assert not (tmp_path / ".agents.json").exists()
```

### § 7.7 Target gate matrix

| Gate | Target | Baseline | Delta |
|---|---|---|---|
| pytest — total passed | **~95** | 75 | +20 (−5 test_scaffold deletions, +25 new) |
| pytest — failed | **5** (pre-existing `test_example.py` — unchanged) | 5 | 0 |
| pyright errors | **≤11** (the 11 `mcp_adapter.py` errors; the 6 `test_scaffold.py` errors go to zero after annotation rewrite) | 17 | −6 |

Exact count depends on Impl's final test decomposition, but the relationship holds: the rewrite **reduces** the pyright baseline because of the test_scaffold.py annotation cleanup. Impl: if pyright lands ≥ 17 after the rewrite, something regressed — diagnose, don't accept.

**End-to-end smoke tests** (Impl runs manually in the impl worktree once code lands, reports in the merge request body):

1. `uv run moot init --help` → help text includes `--force`, `--update-suggestions`, `--adopt-fresh-install`, `--fresh`, `--yes`
2. `uv run moot config provision --help` → help text includes `--fresh`
3. `uv run moot --version` → `moot 0.1.0` (Run Q regression guard)

No backend-connected smoke test is required — the respx-mocked unit tests cover the HTTP happy path.

---

## § 8 Security considerations

**Auth boundaries:**
- `cmd_init` is a client-side tool; all backend calls use the user's existing `~/.moot/credentials` token. No new authn surface.
- The rotate-key loop sends the user's PAT as `Authorization: Bearer ...`, which the backend scopes to the user's own actors. No privilege escalation surface — the backend enforces ownership on `POST /api/actors/{id}/rotate-key`.
- `X-Force-Rotate: true` is a user-originated header that the user can already send manually via curl. No new capability; only a convenience wrapper.

**Input validation:**
- `{project_name}` substitution uses `Path.cwd().name`, which is user-controlled. The placeholder is inserted into `CLAUDE.md` via literal `str.replace`; no shell, no templating engine, no eval. A cwd name containing `{api_url}` literal would cause a second-pass substitution mismatch, but that's cosmetic (produces a malformed CLAUDE.md, not an injection). Accept as a non-issue for Run R.
- No other user input beyond CLI flags (argparse) and credential-file contents (TOML, parsed by stdlib `tomllib`).

**Data isolation:**
- `.moot/actors.json` contains plaintext API keys. Mode `0o600` on the file, `0o700` on the parent `.moot/` directory. Matches the convention already established for `~/.moot/credentials` in Run Q.
- `.gitignore` gets `.moot/` appended so the actors file is never committed. The existing `.agents.json` entry is kept alongside so legacy files are also gitignored.
- `--force` rotates keys on the backend, invalidating any other installation with the old keys. This is a destructive cross-machine operation per the product doc's "Multi-machine double-install" section. The backend's `X-Force-Rotate` gate (shipped at `011b51e`) turns this from silent-clobber into explicit-opt-in; client side, we protect with a confirmation prompt before calling.

**Secrets handling:**
- Keys are never logged. stdout output names agents and their actor IDs but NEVER the key itself (rotate-key response is read into the actors map and written to disk; no `print(key)` anywhere in `cmd_init`).
- respx test mocks return fake keys (`convo_key_live_<role>`) and the tests assert on those values, so any future refactor that accidentally `print`s a key will fail the test (or will get caught because a stdout assertion lines up against the fake-key pattern).

**Transport:**
- `httpx.AsyncClient(base_url=api_url, ...)` respects the credential's stored URL (typically `https://mootup.io`). No HTTP downgrade. No cert pinning — relies on the system trust store.

**Confirmation prompts (D-PROMPT):**
- `--force` and `--adopt-fresh-install` require interactive confirmation by default. `--yes` bypasses. CI contexts use `--yes`; interactive users get a last-chance prompt before irreversible actions.

**Not covered (out of scope):**
- Multi-profile credentials (`moot login --profile work` plus `moot init --profile work`). v2+.
- Pre-flight health check. If the credential is stale, the first HTTP call 401s and the error message points at `moot login`. That's the whole recovery story.
- Encryption at rest for `.moot/actors.json`. Same posture as `~/.ssh/id_ed25519`: filesystem permissions are the defense.

---

## § 9 Open questions

Every OQ below has a recommended default that Spec has locked in-draft per `feedback_spec_resolves_product_doc_silences.md`. Product may override during spec review; Impl proceeds with the defaults otherwise.

1. **D-TOML: `cmd_init` writes `moot.toml` from adopted team data.** The product doc's desired-flow summary doesn't mention moot.toml, but every downstream command (`moot up`, `moot exec`, `moot config show`) requires it. Default in-draft resolution: generate inline from the adopted team via `generate_moot_toml()`; legacy `templates/teams/<name>/team.toml` path stays for `--fresh`. Product: confirm that's the intent, or override with "stop writing moot.toml and migrate downstream commands."

2. **D-SHELL: devcontainer runner scripts get the rename sweep.** Kickoff § Out of scope says "No devcontainer template changes"; § Key deliverables says "update any adapter/reader code." Strongest-specific-wins → apply the rename to the three runner scripts. Impl will also update `test_templates.py::test_runner_reads_actors_json` to match. Product: confirm, or override if you want the shell scripts to stay on `.agents.json` and provide a separate migration path.

3. **D-PROVISION: `moot config provision` default behavior is unchanged in Run R.** Product doc D3 ambiguity: "default becomes an alias for `moot init --update-actors-only`" vs D7's flag list (which has no `--update-actors-only`). Spec resolves in-draft to the minimum-change interpretation: only `--fresh` flag ships, bare `provision` stays on its legacy POST-per-role semantics. Product: confirm, or flag if the bare-provision redirect is actually required for Run R.

4. **Skill count is 7, as per product doc D4 / transform-checklist table.** Spec re-read each of the 9 convo skills at draft time; verdict matches the product-doc recommendation exactly (merge-to-main and stack-reset are convo-specific and don't generalize). No changes proposed.

5. **Placeholder substitution is exact literal match (`str.replace`).** No escape syntax for literal `{word}` strings in the template. Not a blocker — the current `.claude/CLAUDE.md.mootup-template` has no conflicting literals — but worth flagging if Product plans to add any in a future release.

---

## § 10 Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Skill transform pass produces convo-leakage in a bundled file | Medium | `test_skills_bundle_complete` (§ 7.3) grep-asserts against the forbidden-pattern list. Impl runs the grep after each skill transform and before commit. |
| `.moot/` directory collides with an existing user-created one containing unrelated content | Low | Product doc OQ resolution: `cmd_init` creates missing files inside an existing `.moot/`, does not delete existing files. `actors.json` presence triggers refuse-without-force. |
| Backend `/api/spaces/{id}/participants` shape is different from what `_fetch_keyless_agents` assumes | Medium | The helper tolerates both list-shape and dict-shape (`if isinstance(participants, dict): participants = participants.get("participants", [])`). Impl verifies against the live backend as part of the end-to-end smoke test. |
| `display_name` casing in the backend differs from what `_infer_team_template` expects (e.g. "product" vs "Product") | Low | `_infer_team_template` lower-cases internally; robust to either. |
| `asyncio.run()` called inside a test that already has an event loop (pytest-asyncio auto mode) | Medium | T-init tests are sync (decorated with `@respx.mock`, NOT `@pytest.mark.asyncio`). `cmd_init` is a sync wrapper that calls `asyncio.run()`; that's safe from sync test code. |
| `monkeypatch.chdir(tmp_path)` doesn't undo between tests, contaminating later tests | Low | pytest's built-in monkeypatch is function-scoped and undoes chdir on teardown. No extra handling needed. |
| Impl overlooks the `pytest.MonkeyPatch` annotation rule and inflates pyright baseline | Low | Called out explicitly in § 7.1 and § 7.7 target matrix. Post-Run-R pyright count should DROP from 17 → 11, not rise. |
| Bundled skill files are not actually shipped in the built wheel (missing from `[tool.hatch.build.targets.wheel]` package-data config) | Medium | `pyproject.toml` uses `src/moot/` layout; `[tool.hatch.build.targets.wheel].packages = ["src/moot"]` should already include everything under `src/moot/templates/skills/`. Impl verifies by running `uv build` and `unzip -l dist/mootup-0.1.0-*.whl | grep skills/` as a smoke step. |
| Shell script inline Python regex with `${PROJECT_ROOT}` interpolation produces wrong results when path contains special chars | Low | The existing scripts already have this pattern; Run R preserves the exact interpolation model, only changing file path + key-lookup shape. |
| `--update-suggestions` called before any prior init causes confusing error | Low | `_update_suggestions_only` checks `ACTORS_JSON` existence and prints a hint directing at plain `moot init`. |

---

## § 11 Missing-imports audit

For every bare symbol referenced in § 6 / § 7 code snippets, this section confirms the import path is correct. Pattern earning its keep across 4 consecutive runs per `feedback_missing_imports_audit_in_spec_11.md`. Impl: paste these imports directly.

### `src/moot/scaffold.py` (new)

```python
from __future__ import annotations

import asyncio                   # cmd_init sync wrapper
import json                      # actors.json write
import os                        # os.chmod on actors.json + .moot/
import shutil                    # shutil.copy2 for skill / devcontainer install
import stat                      # stat.S_IEXEC etc for shell script perms
from datetime import datetime, timezone   # init-report timestamp
from pathlib import Path
from typing import Any

import httpx

from moot.auth import load_credential
from moot.config import ACTORS_JSON, MOOT_DIR
from moot.team_profile import (
    RoleProfile,
    TeamProfile,
    generate_moot_toml,
)
```

Removed from the prior scaffold.py: `resolve_template`, `DEFAULT_TEMPLATE`, `generate_claude_md` (no longer needed; the new CLAUDE.md template is read directly from `TEMPLATES_DIR / "CLAUDE.md"` as a flat file).

### `src/moot/config.py` (edits)

Add: `import json` (was already present via the `load_agent_keys` implementation — verify). No other new imports.

### `src/moot/cli.py` (edits)

No new imports. `asyncio` is already imported at the top of the file. The new `init` dispatch still goes through the `cmd_init` sync wrapper, which internally calls `asyncio.run(_cmd_init_async(args))`.

### `src/moot/provision.py` (edits)

Add: `from moot.config import MOOT_DIR` — the `{MOOT_DIR}/agents-fresh.json` path needs it. `json`, `Path`, `httpx`, `load_credential`, `find_config` are already imported.

### `tests/test_scaffold.py` (rewrite)

```python
from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest
import respx
from httpx import Response

from moot.scaffold import cmd_init
from moot.config import ACTORS_JSON
```

(Impl: when writing T-init tests, the respx routes go inside each test function and use `respx.mock` as a decorator, NOT a context manager — matches Run Q pattern in `test_auth.py::test_login_interactive_prompt_accepts_valid_pat`.)

### `tests/test_templates.py` (edits)

No new imports needed for the assertion flip. For the new `test_skills_bundle_complete`:

```python
from moot.scaffold import SKILLS_TEMPLATE_DIR, BUNDLED_SKILLS
```

### `tests/test_config.py` (edits)

Add at the top if not present:

```python
import json
import pytest
```

(`Path` is already imported.)

### `tests/test_provision.py` (edits)

```python
import asyncio
import json
from pathlib import Path

import pytest
import respx
from httpx import Response
```

(`pytest` was already imported; others are new.)

### `tests/test_security.py` (edits)

No new imports for the gitignore assertion update.

---

## § 12 Cross-references

**Product:**
- `/workspaces/convo/docs/product/moot-init.md` — 561-line design doc (D1–D9, OQs, success criteria, tests, future directions)
- `/workspaces/convo/docs/product/local-installation.md` — parent series doc (Run P / Run Q / Run R umbrella)
- `/workspaces/convo/docs/product/agent-connection-state.md` — sibling doc (prerequisite for multi-machine `moot init --force`)

**Release-time transforms:**
- `/workspaces/convo/docs/ops/skill-release-transform-checklist.md` — strip/preserve/genericize rules Impl applies for the 7 transformed skills (§ 6.7)
- `/workspaces/convo/.claude/CLAUDE.md.mootup-template` — pre-transformed source for `src/moot/templates/CLAUDE.md` (D5)

**Convo skill sources (D4):**
- `/workspaces/convo/.claude/skills/product-workflow/SKILL.md`
- `/workspaces/convo/.claude/skills/spec-checklist/SKILL.md`
- `/workspaces/convo/.claude/skills/leader-workflow/SKILL.md`
- `/workspaces/convo/.claude/skills/librarian-workflow/SKILL.md`
- `/workspaces/convo/.claude/skills/handoff/SKILL.md`
- `/workspaces/convo/.claude/skills/verify/SKILL.md`
- `/workspaces/convo/.claude/skills/doc-curation/SKILL.md`

**Prior run retros referenced in this spec:**
- `feedback_cross_repo_first_run_baseline.md` — cross-repo baseline rule (§ 2)
- `feedback_missing_imports_audit_in_spec_11.md` — missing imports discipline (§ 11)
- `feedback_spec_resolves_product_doc_silences.md` — in-draft resolution of small silences (§ 9)
- `feedback_spec_length_scales_with_churn.md` — spec length for ~550 LOC code diff (§ 3.3)
- `feedback_verify_product_grounding_claims.md` — Spec independently verifies kickoff claims at grounding time
- Run Q spec §§ 6–7 — post-rename test patterns (`pytest.MonkeyPatch` annotation, respx HTTP mock structure)

**Mootup-io/moot shipping context:**
- `docs/specs/moot-cli-brand-login.md` — Run Q spec (this run's prior ship). Established the spec tree, added interactive `moot login`, brand-swept user-facing strings.

---

## § 13 Grounding notes (Spec's executed checks at draft time)

Executed against `/workspaces/convo/mootup-io/moot/.worktrees/spec/` at commit `fa9b133`:

```
$ git log --oneline -5
fa9b133 moot-cli brand sweep + interactive login + --version flag
3be4d9b gitignore: add .worktrees/, build artifacts, local env files
102d042 CI: bump GitHub Actions to Node 24 versions
03a7a1d Rename distribution to mootup, add PyPI trusted publishing workflow
154df51 Switch to sequence diagram for architecture

$ uv run pytest -q 2>&1 | tail -8
...
5 failed, 75 passed in 1.74s
(all 5 failures: tests/test_example.py — pre-existing Path(__file__).parents[N] walking past worktree boundary)

$ uv run pyright 2>&1 | tail -5
17 errors, 0 warnings, 0 informations
(11 in src/moot/adapters/mcp_adapter.py — long-standing; 6 in tests/test_scaffold.py monkeypatch annotation — to be cleaned up in the rewrite)

$ grep -rn "\\.agents\\.json\\|AGENTS_JSON\\|load_agent_keys" src/moot/ tests/ | wc -l
20  (all at paths enumerated in § 5, accounted for in D2/D-SHELL)

$ ls /workspaces/convo/.claude/skills/
doc-curation   handoff              librarian-workflow  product-workflow  stack-reset
leader-workflow  merge-to-main      spec-checklist      verify
(9 skills; 7 bundle per D4; 2 excluded — matches product doc)

$ wc -l /workspaces/convo/.claude/skills/*/SKILL.md
   79 product-workflow/SKILL.md
  106 spec-checklist/SKILL.md
  150 leader-workflow/SKILL.md
   50 librarian-workflow/SKILL.md
   46 handoff/SKILL.md
   68 verify/SKILL.md
   81 doc-curation/SKILL.md
(total ~580 LOC → expect ~450-500 post-transform)

$ wc -l /workspaces/convo/.claude/CLAUDE.md.mootup-template
234
(flat copy to src/moot/templates/CLAUDE.md — no re-transform needed; pre-transformed by Product + Librarian)
```

**Scope-contradiction resolutions recorded at draft time:**

| Contradiction | Location | Resolution |
|---|---|---|
| "No devcontainer template changes" (§ Out of scope) vs "Update any adapter/reader code" (§ Key deliverables) | Kickoff | Apply rename sweep to 3 runner shell scripts — D-SHELL. Strongest-specific-wins. |
| `cmd_init` must write moot.toml (desired-flow summary is silent; downstream commands require it) | Product doc § Desired flow vs `moot up` contract | `cmd_init` generates moot.toml inline from adopted team — D-TOML. |
| D3 "default provision becomes `--update-actors-only` alias" vs D7 (no such flag in init flag list) | Product doc | Resolve to minimum-change: bare `provision` unchanged in Run R — D-PROVISION. |

All three flagged in § 9 as resolved in-draft with Product confirmation requested during spec review.

**Run Q preservation allowlist reference (for the brand sweep regression check):**

Preserved (never to be swept):
- Environment variable names: `CONVO_API_KEY`, `CONVO_API_URL`, `CONVO_SPACE_ID`, `CONVO_ROLE`
- TOML section name: `[convo]` (in `moot.toml`)
- Key prefixes: `convo_key_`, `convo_sess_`
- Script / MCP server names: `convo-channel`, `convo-lifecycle`
- Logger names: `convo.*`
- Adapter module paths: `moot.adapters.*`

Run R preserves all of these unchanged. The grep regression check in § 2 excludes these paths.

---

## § 14 Handoff notes for Implementation and QA

### For Implementation

1. **Start from the feat tip** (`fa9b133`). Create `impl/moot-init-full-provisioning` in `/workspaces/convo/mootup-io/moot/.worktrees/implementation/`.
2. **Run the pre-edit baseline** before touching anything: `uv sync --group test && uv run pytest -q && uv run pyright`. Confirm 75p/5f/17 pyright. If anything differs, stop and flag via `message_type="question"` — the spec is off.
3. **Order of edits** (recommended to minimize test churn during intermediate runs):
   1. `src/moot/config.py` (new loader API + ACTORS_JSON rename)
   2. `src/moot/launch.py` (one-line import swap + `cmd_exec` key lookup)
   3. Devcontainer shell scripts (3 files, rename sweep — § 6.6)
   4. `src/moot/provision.py` (`--fresh` flag)
   5. `src/moot/cli.py` (new flags — § 6.4)
   6. `src/moot/scaffold.py` **full rewrite** (§ 6.3). This is the biggest change; save it until everything else compiles.
   7. `src/moot/templates/CLAUDE.md` (copy from convo — § 6.8, one `cp` command)
   8. `src/moot/templates/skills/<name>/SKILL.md` × 7 (transform pass per § 6.7)
   9. `tests/test_scaffold.py` (rewrite — § 7.2). Hardest part. Expect 1–2 iterations on the respx mocks before gates land.
   10. `tests/test_templates.py`, `tests/test_config.py`, `tests/test_security.py`, `tests/test_provision.py` (targeted updates — §§ 7.3–7.6)
   11. `README.md` prose update
4. **Test in stages.** After each of steps 1–6, run `uv run pytest -q tests/test_config.py tests/test_templates.py` to confirm no regressions in the unaffected areas. The big test rewrite (step 9) can temporarily inflate fails — use `pytest -q tests/test_scaffold.py` in isolation until it lands clean.
5. **Transform discipline for skills.** For each of the 7 skills (step 8), read the convo source AND the transform checklist side by side, apply the strip/preserve/genericize rules per § 6.7, save the result, then run the forbidden-pattern grep from § 7.3 over that one file. Repeat. Do NOT batch the 7 transforms into one commit — commit each skill individually if the transform was non-trivial, so review is reasonable.
6. **End-to-end smoke tests** (report in the merge request body):
   - `uv run moot init --help` → flags visible
   - `uv run moot config provision --help` → `--fresh` visible
   - `uv run moot --version` → `moot 0.1.0`
7. **Pre-draft during spec-hold.** This is a large run; per `feedback_pre_draft_during_design_hold.md`, Impl may use the SPEC-READY hold window to pre-analyze blast radius and substitution candidates. Sketch your edit plan, grep the affected symbols, think about test fixture setup. When Spec commits, compare your pre-draft against the final spec.

### For QA

1. **Pre-merge verification:**
   - `uv sync --group test && uv run pytest -q && uv run pyright` — target 95p/5f/≤11 pyright.
   - Confirm the 5 `test_example.py` failures are unchanged; if any of them flip pass/fail, note it (unexpected) but don't treat as a regression.
   - Confirm pyright dropped from 17 to ≤11. If it didn't, the test_scaffold.py annotation cleanup wasn't done — reject.
2. **Bundled artifact smoke:**
   - `ls src/moot/templates/skills/` → 7 directories.
   - For each skill: `grep -E "Pat|/workspaces/convo|feedback_|Arch Run|agt_|evt_|spc_|docker exec convo-" src/moot/templates/skills/<name>/SKILL.md` → zero hits.
   - `head -5 src/moot/templates/CLAUDE.md` → matches the convo source file.
3. **End-to-end smoke** (manual in QA worktree, after `git reset --hard` to feat tip):
   - Create a tempdir, `cd` into it, run `moot init` with a fake credential and respx-unstubbed backend → expect auth failure from the real backend (NOT a code crash). Confirm error message points at `moot login`.
   - `moot init --help` and `moot config provision --help` show the new flags.
   - `moot --version` → `moot 0.1.0`.
4. **Wheel build check** (light — not required but worthwhile for a release-artifact-heavy run): `uv build && unzip -l dist/mootup-*.whl | grep templates/skills/` should list all 7 SKILL.md files.
5. **Security checks:**
   - `moot init` on greenfield → `.moot/actors.json` has mode `0o600`, `.moot/` has mode `0o700`.
   - `grep -r "api_key" src/moot/scaffold.py` → no `print(key)` or `log.info(key)` anywhere; keys only written to the actors file.
   - `.gitignore` contains `.moot/`.
6. **Regression guards:**
   - Run Q user-facing brand sweep still holds (§ 2 grep).
   - `moot --version` → `moot 0.1.0`.
   - `moot login --token convo_key_fake` → exits 1 with friendly prefix error (Run Q D7).

### Shared notes

- **Branch:** Spec → `spec/moot-init-full-provisioning`; Impl → `impl/moot-init-full-provisioning`; QA → `qa/moot-init-full-provisioning` (if QA commits repairs).
- **Status-ping cadence (per Run Q Impl retro):** post a short status update after each logical gate clears — "source edits done", "tests green", "pyright clean", "e2e smoke done". 4 pings across the run. Don't silently work for 20+ minutes.
- **Platform instability rule:** one retry on transient backend errors, then `wait_for_health` / `sleep 30`, then pause. Do not poll.
