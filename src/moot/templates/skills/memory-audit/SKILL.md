---
name: memory-audit
description: Recurring audit of operator memory entries. Every fifth pipeline retro synthesis, the memory curator reviews accumulated feedback/project/reference entries and promotes team-generic rules to durable docs or skills, retires already-promoted entries, and keeps operator-specific state in memory. Invoked by the role that owns memory curation (typically Product).
---

# Memory Audit

## Purpose

Operator memory accumulates organically as pipeline retros land. Most entries are useful at the moment of capture but their durable home is uncertain — some describe team-generic rules that belong in CLAUDE.md or a workflow skill, some restate rules already documented elsewhere, and some are genuinely operator-specific state that should stay local. Without a recurring audit the memory directory drifts: promotion candidates go unpromoted, already-promoted entries become redundant, and staleness accumulates.

This skill is the steady-state cadence that keeps the memory layer in sync with the durable documentation layer.

## When to invoke

Every fifth pipeline retro synthesis, counted from the previous audit (or from the start of the repo's history if no audit has run yet).

The count is derived from the git log at invocation time; no counter state file is kept.

```bash
# Replace <repo> with the path to the repository (e.g. the main worktree).
LAST_AUDIT=$(git -C <repo> log main --grep="^memory audit:" -1 --format=%H 2>/dev/null)
if [ -n "$LAST_AUDIT" ]; then
    COUNT=$(git -C <repo> log "${LAST_AUDIT}..HEAD" main --grep="synthesis" --oneline | wc -l)
else
    COUNT=$(git -C <repo> log main --grep="synthesis" --oneline | wc -l)
fi
echo "retro-synthesis commits since last audit: $COUNT"
```

If `COUNT >= 5`, run the audit. Otherwise no-op.

The "synthesis" grep matches pipeline-run retrospective synthesis commits whose subject follows the convention `Run <label> synthesis — ...`. The audit-closing commit uses the subject prefix `memory audit: ...` so the next count cycle can find it.

## Who runs it

The role that owns memory curation. In the default team topology, that is Product (Product already owns retro synthesis and the durable-documentation layer). In a team topology without a Product role, the equivalent role — the one that edits CLAUDE.md and memory files — runs the audit.

## The three-criterion promotion rubric

A memory entry is a promotion candidate only if all three conditions hold:

1. **Validated across ≥3 pipeline runs.** A single-run observation is provisional; three runs establish that the rule is real and the failure mode recurs. Two-run entries stay in memory pending validation or refutation.
2. **Operator-agnostic.** The rule applies to any team running this pipeline topology, not just to this operator or this specific deployment. Test: would another operator running the same team template benefit from this rule? If yes, it's team-generic. If no, it's operator-specific and stays in memory.
3. **Describes a rule.** The entry is normative ("do X", "don't Y", "when X, then Y") not descriptive ("the current state is X" / "this commit fixed Y"). Descriptive entries are project state and belong in `project_*` memory regardless of how broadly applicable they might feel.

All three are required. Borderline entries stay in memory until the next audit cycle, when more data may resolve the ambiguity.

## Classification outcomes

Every entry falls into exactly one of four buckets:

- **(a) Already promoted — retire.** The rule exists verbatim or near-verbatim in CLAUDE.md, a workflow skill, or another durable artifact. Retire the memory entry (delete the file and remove the `MEMORY.md` index line).
- **(b) Needs promotion — draft and retire.** All three criteria hold and no durable home exists yet. Draft the promotion (new CLAUDE.md bullet, new skill section, or new checklist item) in a single commit; retire the memory entry in the same commit or the next one.
- **(c) Keep in memory.** At least one criterion fails (operator-specific, single-run, descriptive). Update the memory entry if needed; leave it in place.
- **(d) Retire unconditionally.** The entry is stale (documents a bug since fixed, references a subsystem no longer in the codebase) and no longer useful. Delete with no promotion.

## Execution recipe

1. **Resolve the count.** Run the git-log snippet above; confirm `COUNT >= 5`. If not, no-op and return.
2. **Enumerate entries.** Read `MEMORY.md`. For each file it links to, open the memory file and note its frontmatter `type` (user / feedback / project / reference).
3. **Classify.** For each entry, apply the three-criterion rubric and assign to (a), (b), (c), or (d).
4. **Confirm promotion targets.** For each (b) entry, identify the most-specific durable home: a workflow skill if the rule is role-specific; CLAUDE.md if the rule spans roles; a checklist item in spec-checklist if the rule is spec-authoring discipline; and so on. If no natural home exists, demote to (c) pending a future refactor that creates one.
5. **Draft promotions and retirements.** Edit durable artifacts to add the promoted text. Delete the corresponding memory files. Update `MEMORY.md` to remove the retired index lines.
6. **Write the audit report.** Create a product-facing doc under `docs/product/` named `memory-audit-<yyyy-mm-dd>.md` that enumerates the starting count, the classification of each entry, and the set of durable-doc edits made. The report is useful for future audits (diff vs prior report) and for operator review.
7. **Commit.** The commit message subject line MUST start with `memory audit:` so the next count cycle can anchor on it. Example: `memory audit: 2026-04-17 — retired 45 already-promoted, promoted 40, left 24 operator-specific`.

## What NOT to promote

- **Operator identity, deployment specifics, or local-environment constraints.** These are operator-specific by definition.
- **Historical session records.** `project_session_*` files are provenance, not rules.
- **Stale bug-fix memories.** If a memory documents a bug that has since been fixed, retire it with disposition (d) — don't try to promote the fix itself.
- **Workflow-topology changes.** Retros (and this audit's promotions) may change *how* individual roles perform their work but must NOT change the pipeline topology (who talks to whom). Topology changes go back as "performance/communication changes only."

## Audit-report ratcheting

Keep the most recent audit report. Delete audit reports older than three cycles — they're no longer actionable and the durable-doc state has moved on. The most-recent report provides the diff baseline for the next audit; older reports clutter `docs/product/` without adding value.

## What success looks like

A steady-state audit where the number of (a) entries (already-promoted-redundant) trends toward zero over several cycles. If (a) entries are persistently large, the retro-synthesis step is under-promoting during normal synthesis and the audit is compensating — flag this to the team via the next retro synthesis or a question message to the role that owns retro synthesis.

A steady-state audit where (b) entries are in the 0–5 range per cycle. Larger (b) sets suggest the retro-synthesis step is skipping promotion candidates entirely — same diagnosis and same fix.

A steady-state audit where (c) entries are the bulk of the memory file count: this is healthy. Operator-specific state is what memory is for.
