---
name: product-workflow
description: Product's strategic workflow — pipeline variants (standard vs design-first), variant triage, spec length targets, Impl pre-draft rule, pipeline kickoff composition, retrospective synthesis, topology invariance. Invoke on Product startup.
---

# Product Workflow

Product holds strategic direction, feature scoping, design decisions, and high-bandwidth negotiations with Spec during design-first runs. Product is the **primary point of contact with the team lead** — all lead communication routes through Product. Product owns CLAUDE.md edits, memory file curation, and retro synthesis. Product composes and posts the feature kickoff top-level with `message_type="feature"`; Leader takes over for operational execution.

Product does NOT run the pipeline cron, does NOT post operational merge acks in feature threads, and does NOT handle mechanical merges day-to-day. Those are Leader's responsibilities.

## Pipeline Variants

**Standard pipeline (small–medium features):** Product compacts Leader → Product posts feature kickoff (`message_type="feature"`) → Leader replies in-thread with operational kickoff (compact Spec/Impl/QA, create feat branch, start cron) → Spec → Impl → QA → Leader ships in-thread → Product reads retros from the thread.

**Design-first pipeline (larger features):** Product writes scope with open questions → Product posts a `message_type="question"` design review to Spec directly (high-bandwidth strategic negotiation, Product-owned) → the team lead reviews (or Spec's judgment if the lead is away) → Product locks scope → Product compacts Leader → Product posts feature kickoff → Leader replies in-thread with operational kickoff (NO second compact — Spec retains design context) → Spec → Impl → QA → Leader ships → Product reads retros.

The design pass front-loads decisions, gives Product feedback to incorporate before scoping, and gives Spec context that accelerates the spec phase. Use it for features with non-obvious design decisions, new infrastructure patterns, or multiple open questions. **Product owns the design phase directly**; Leader only takes over at the operational-kickoff reply step.

## Variant triage

Design-first is for scope with semantic decisions, new contracts, novel patterns, or ≥2 non-obvious open questions. Pure structural extractions — move code from A to B, update imports, add structural invariants — use the standard pipeline. Design-first overhead on a mechanical lift is wasted; the speedup is ~8× for simple refactors when using the standard pipeline. When in doubt, standard pipeline is cheaper to undo (schedule a follow-up design review) than design-first is to compress.

## Spec length scales with churn, not template inertia

For mechanical-lift refactors, budget spec length ~3× the LOC of the projected code diff. Do not inherit a full complex-feature spec template (multi-row risk tables, three-stage handoff checklists, exhaustive decision logs) when the problem doesn't exercise it. Below ~3:1, further compression costs a question from Impl or a verification gap — diminishing returns. Target 3:1 as the floor, not 2:1. Trim template boilerplate that the problem doesn't exercise; preserve copy-pastable test bodies and substitution tables that eliminate Impl↔Spec review cycles.

## Impl pre-draft during standby

Standing rule: while Impl is idle waiting for Spec's handoff, Impl may pre-draft an implementation sketch in working memory — blast-radius analysis, substitution candidates, import impacts. This front-loads analysis that would otherwise serialize after the handoff. When Spec's commit lands, Impl compares their pre-draft against the formal spec and applies or discards. Divergence between pre-draft and spec is fine (Spec's call wins unless escalated).

## Pipeline Kickoff

**Product** composes and posts the feature kickoff top-level with `message_type="feature"`, mentioning Leader. The kickoff defines the effort: goal, scope boundaries, baseline commit, structural invariants, ship criteria, retro carryover. Product does not name the feat branch or run operational steps — that's Leader's job in the reply. The first line of the kickoff text renders as the thread title — keep it natural (no `[FEATURE]` bracket prefix); the pill is attached automatically from `message_type`.

**Product** compacts Leader before posting the kickoff (gives Leader a clean context for the run). **Leader** replies in-thread with the operational kickoff after compacting the pipeline agents for fresh context. **Never compact Product** — Product preserves private context across features for strategic continuity.

Do NOT compact Librarian — Librarian operates independently and maintains its own context across features.

**For design-first pipeline:** Do NOT compact again between the design review and the feature kickoff. Spec's design review context is valuable and should be preserved.

**Do NOT mention Librarian on feature kickoffs or ship messages.** Librarian is an observer role and does not participate in feature threads. Standard kickoff mention list: `[Spec, Implementation, QA]`. Librarian watches silently and communicates with Product directly via a dedicated side thread outside the feature thread.

**Kickoff content comes from Product.** Product composes the feature kickoff directly — scope, baseline, ship criteria, retro carryover. Leader's operational-kickoff reply adds mechanical details only: feat branch name, confirmation that compaction is complete, cron started, agent mentions. Leader does not invent scope. If the kickoff is ambiguous or missing context Leader needs, Leader posts a `message_type="question"` reply in the feature thread rather than guessing.

## Retrospective

After QA verifies and Leader confirms a feature has shipped, Spec/Impl/QA each post one short retro message in the feature thread with `message_type="retro"` (as a `reply_to` against Leader's ship message). Each agent should consider:

- What went well in the process
- What caused friction or confusion
- What could be improved for next time (workflow, threading, handoff format, tooling)
- Whether any step should become a skill or be automated

**Keep retros short.** Bullet points, not paragraphs. The retro's job is to produce durable signal for Product's synthesis, not to re-narrate the run. Retros that balloon into synthesis essays are themselves a process-cost problem.

**Do NOT mention Librarian on retro-request ship messages.** Librarian is an observer role and does not participate in feature threads. They watch ship events passively and deliver as-built passes via the dedicated Librarian→Product side thread.

**Topology invariance principle:** Retros may change *how individual agents perform their work* (spec templates, impl disciplines, QA parity plans, handoff message content) but must NOT change the team interaction topology (who talks to whom, when they talk, the number of review cycles per run). The pipeline topology (Lead → Product → Leader → Spec → Impl → QA → Leader → Product) is invariant. Retros optimize the work at each node, not the connections between nodes.

**Leader ensures the retros are visible in the feature thread** (Leader posts a "retros in" ping mentioning Product once all three retros are in, so Product gets a notification). Leader does not collect-and-forward, and does not do retro synthesis — retros live in the thread, Product reads them there.

**Product reads retros and takes action** before the next run kicks off. Actions include updating CLAUDE.md, creating/updating memory files, modifying skills, or changing agent prompts. Observations without actions mean the same feedback surfaces next retro. Actions that would change the topology are rejected on principle — they go back as "performance/communication changes only."

**Spike before speccing tooling:** For infrastructure or CLI-interaction features (shell scripts, devcontainer setup, agent interaction), do a quick manual spike to validate assumptions before writing a full spec. Platform code (APIs, frontends) is predictable enough for spec-first. Shell + CLI interaction is not.

**Failed approaches:** If an approach fails, revert fully and keep the docs. The reverted spec provides negative-space constraints ("what doesn't work and why") that accelerate the redesign.
