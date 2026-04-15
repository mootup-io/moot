---
name: spec-checklist
description: Generate a prefilled verification checklist for writing a spec. Use at the start of spec work to ensure nothing is missed.
argument-hint: [feature scope or description]
---

Generate a verification checklist for writing a spec for the given feature.

## Feature

$ARGUMENTS

## Checklist

Work through each item before writing the spec. Check off as you go.

### API & Data Layer
- [ ] **Existing API endpoints:** Which endpoints are relevant? Do any already serve the data needed?
- [ ] **API gaps:** Are new endpoints needed? What request/response shapes?
- [ ] **Data model changes:** Any new fields, tables, or migrations?
- [ ] **Real-time events:** Does this feature need streaming / SSE / WebSocket updates? Are the right events already emitted?

### Frontend
- [ ] **Existing components:** Which components are affected? Read them before proposing changes.
- [ ] **Existing helpers:** Check shared utilities — is there code that already does part of this?
- [ ] **Framework compatibility:** Confirm patterns match the project's framework idioms (reactive state, effect model, component API).
- [ ] **Styling:** Document exact colors, sizes, and spacing using the existing palette.

### Dependencies
- [ ] **New libraries needed?** Confirm compatibility with the project's toolchain.
- [ ] **Bundle size impact:** Estimate size delta for any new frontend dependencies.
- [ ] **Security:** Does the library handle untrusted input safely? Do we need sanitization?

### Test Infrastructure
- [ ] **Test runners available?** Verify the test tooling exists before specifying tests.
- [ ] **Test plan:** Define test cases covering: happy path, edge cases, error cases, regressions.
- [ ] **Test data setup (UI features):** If the feature involves visual changes, include concrete setup steps (e.g. HTTP calls, fixtures) that create the right data shape for manual or e2e verification. Don't rely on code review alone for visual correctness.

### Interface Design
- [ ] **Hide internal topology from consumers.** If the spec requires the client to enumerate sources, manage subscriptions, or know the internal structure of the data, the abstraction is wrong. The server should aggregate.

### Cross-Cutting
- [ ] **Verify claims in the feature scope.** Don't trust Product's assumptions about what exists — check the code.
- [ ] **Accessibility:** Any ARIA labels, keyboard navigation, or screen reader concerns?
- [ ] **Performance:** Any large data sets, heavy computation, or expensive renders?
- [ ] **Security:** XSS, injection, auth boundaries?

### Spec Document
- [ ] **Reference code by function/class name + file path** — never use line numbers (they drift between commits)
- [ ] **Files to create/modify** — explicit table with file paths and actions
- [ ] **Open questions** — list anything that needs Product input
- [ ] **Out of scope** — confirm alignment with feature boundaries

### Baselines (§ 14 gates)
- [ ] **Empty-diff shortcut first.** Run `git diff <prior_ship>..<feat_tip> -- <source-dirs>`. If empty, inherit the prior ship's gate matrix verbatim — no re-running tests/typechecks/lints. Fall back to full re-measurement if the diff is non-empty or the run is a structural refactor where the diff-based check could miss a latent failure.
- [ ] **Cross-repo first run: empty-diff shortcut does NOT apply.** When the first pipeline run in a new repo kicks off, there is no prior ship to inherit from. Always remeasure from scratch at the feat tip: run the repo's test command, typecheck, and any project-specific baseline commands. Explicitly enumerate any pre-existing failures in § 2 so QA doesn't false-alarm on the delta.
- [ ] **Pytest count formula.** When your gate section projects a pytest delta, use the explicit formula `baseline + N new test functions = new total`. **Additive assertions inside existing test functions do NOT add to the count.** Check that the test-plan count matches the headline target.
- [ ] **Full re-measure if diff is non-empty.** Run baseline commands at the current `feat/<slug>` tip. Never inherit counts from a prior spec or memory of what the count was last run. Inter-run merges drift the numbers silently.
- [ ] **Paste literal output** — BASELINE-FROZEN blocks with the exact command and its output.
- [ ] **Prefer "≤ N" over "= N"** when the residual count lives in suppressed / unrelated files (scripts/, auto-generated).

### § 13 Draft-time Command Execution (NON-NEGOTIABLE)

**Run these commands BEFORE writing § 5 / § 11 / § 14, not as a review pass.** Reading commands is NOT the same as executing them. Executed commands routinely produce 1-2 spec amendments per run by surfacing stale assumptions.

**Position in the workflow:** § 13 commands are *grounding*, not *review*. Running them *first* produces correct imports, paths, and counts on first write — skipping that step forces mid-draft patches.

- [ ] **Execute § 13 commands at the START of spec drafting**, before writing § 5/§ 11/§ 14. The output drives what goes into those sections, not the other way around.
- [ ] **Every quoted count** in § 11 / § 14 / § 6 is the literal output of an executed command, not a hand-estimate.
- [ ] **Every file path** referenced in Product's doc has been verified with `ls` or `test -e`. Product docs drift; phantom paths get caught at spec time, not at Impl's first test run.
- [ ] **Every Product-enumerated implementation step** has been verified against current code. Product docs sometimes describe as "to do" steps that have already shipped, or describe as shipped steps that were never completed. Grep/read each step before writing § 5.

### § 11 Surprises for Impl — Missing-Imports Audit
For every new symbol referenced in § 5 code snippets (function calls, exception catches, type annotations), grep the target file for the import:

```
grep -n "^import <sym>\|^from [^ ]* import.*<sym>" <target-file>
```

If the grep returns empty, add a § 11 line: "**Missing import** — `<sym>` is not imported in `<target-file>`. Add `import <sym>` (or `from <module> import <sym>`) to the top of the file."

Common culprits:
- [ ] Stdlib modules newly introduced by § 5: `json`, `asyncio`, `re`, `uuid`, `time`, `os`, `sys`.
- [ ] New exception types in `except` clauses.
- [ ] New typing imports: `Any`, `Callable`, `Awaitable`.

**Test snippet imports must be self-contained.** Every symbol a § 7 test snippet calls must be explicitly imported inside that snippet (at the top of the test function or at the top of the test file). Do NOT assume `import foo as foo_mod` at the file top brings bare `foo_mod.cmd` into the test function's namespace — call sites that use the bare name will fail with `NameError` even if the alias import exists. Rule: for every symbol referenced by its bare name in a § 7 test snippet, grep the snippet for a matching `from <module> import <name>` or `import <name>` line. If absent, add it.

### Test Cleanup Fixtures
- [ ] **FK cascade enumeration.** If a test fixture deletes rows from a table with FK-dependent children, grep `REFERENCES <parent>(id)` in the schema files to find ALL child tables. Enumerate them in dependency order in the spec's test-infra section, OR specify `TRUNCATE ... CASCADE` as the default. Partial recipes silently fail when the schema grows new FKs.
- [ ] **Verify the fixture helper at the target line before prescribing additive assertions.** When the spec says "add `assert X` to test Y at line N," grep test Y for the fixture it uses to confirm the fixture matches what the assertion needs. Cheap check at spec-draft time, saves Impl the recast work.
- [ ] **Subprocess env forwarding under pytest-xdist.** If any test runs a subprocess that imports project config, the spec must list ALL mutated config vars to forward. In-memory config mutations don't cross process boundaries.

### Token / Secret Literals in § 7 Test Snippets
- [ ] **Never hard-code token prefix literals in § 7 test snippets.** Import from the project's token-constants module instead. Arch invariants that block raw literal usage in tests will trip the Impl gate — catch at spec-draft time.

### Protocol Cross-Reference
- [ ] **If any D-decision touches an inter-agent protocol** — mention lists on ship/kickoff/handoff messages, thread discipline, retros-in routing, token-ring mention rules, status-update discipline — scan CLAUDE.md's § Agent Workflow for the current live rule before freezing the spec decision. Live protocol evolves faster than spec templates; a spec that hard-codes a stale mention list forces Impl to either follow it blindly (wrong behavior) or deviate (compliance ambiguity).
- [ ] **Prefer live protocol references over inline protocol rules** in D-decisions.
