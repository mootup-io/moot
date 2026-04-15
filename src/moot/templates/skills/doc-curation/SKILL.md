---
name: doc-curation
description: Curate repository documentation for agent use. Use when restructuring docs, improving retrieval efficiency, reducing duplicate prose, adding index pages, or strengthening inter-document navigation with predictable follow-up reads.
---

# Doc Curation

Curate docs for fast agent retrieval and reliable human orientation.

## Default stance

- Keep canonical linear entry points: overview docs, spec indexes, runbooks.
- Prefer one coherent subject per document.
- Use headings as retrieval boundaries.
- Use inter-document references to guide the next read when one document is not enough.
- Optimize for fewer read round-trips and lower reconstruction effort.

## When to use this skill

Use this skill when you are:

- reorganizing docs or specs
- adding or updating README index pages
- reducing repeated explanations across docs
- deciding whether to split or merge documents
- making docs easier for agents to scan in a large context window

## Workflow

1. Identify the current entry points.
   - Find the main overview, setup, spec index, and runbook docs.
   - Preserve or improve those before introducing new structure.

2. Map the document types.
   - Overview: "what is this system?"
   - Subject docs: "how does this area work?"
   - Specs/runbooks: "what should we build?" / "how do we operate it?"
   - Reference: canonical facts, API shapes, protocol copies

3. Check for agent-friction smells.
   - The same concept is re-explained in many docs.
   - A doc is so broad that agents must scan the whole file to answer a narrow question.
   - A concept is fragmented across too many docs, forcing multiple reads to reconstruct one answer.
   - There is no clear "read this first" path.
   - References exist, but they do not tell the reader what to open next or why.

4. Choose the retrieval unit.
   - Default to a subject-oriented doc with a short summary and scoped headings.
   - Split only when sections are weakly related or maintained by different workflows.
   - Prefer one document that answers a common question in one read over multiple documents that must be stitched together.

5. Edit for retrieval.
   - Put a 1-3 sentence summary near the top.
   - Use descriptive headings that match likely queries.
   - Move repeated background into one canonical subject doc and reference it from related docs.
   - Add explicit inter-document references such as "For auth boundaries, read `docs/specs/auth-hardening.md`" when a second read is likely.
   - Keep "See also" or "Related subjects" sections short and action-oriented.

6. Verify the result.
   - Can an agent answer the common question from one read?
   - If a second read is needed, is the next doc obvious?
   - Did token cost go down by reducing duplicate prose or pointless hops?

## Heuristics

- Good primary doc size: usually a few hundred to low-thousand tokens.
- Good split: "auth model" and "invite flow" are different subjects.
- Bad split: one coherent subject scattered across several weakly differentiated docs.
- Prefer one strong README/MOC per doc area over many weak index notes.
- For cross-cutting topics, use one canonical subject doc and reference it from specs and overviews.

## Output expectations

When proposing or making changes, explain:

- the entry points you preserved or added
- which docs became canonical for repeated concepts
- which duplicates were removed or reduced
- which inter-document references were added or clarified
- whether the change reduces round-trips for agents
