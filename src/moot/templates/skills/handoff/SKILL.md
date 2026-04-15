---
name: handoff
description: Post a structured handoff message to the next agent in the pipeline. Use after completing your work on a feature, before requesting a merge.
argument-hint: [summary of what was done]
---

Post a structured handoff message to the next agent in the Moot channel.

## Pipeline Order

- **Product** hands off to **Spec**
- **Spec** hands off to **Implementation**
- **Implementation** hands off to **QA**
- **QA** hands off to **Product** (verification complete)

## Steps

1. Determine which agent is next based on your role (check `whoami` if unsure).
2. Commit all work to your branch (e.g., `spec/<slug>`, `impl/<slug>`).
3. Get the current branch name and list of files changed:
   ```
   git branch --show-current
   git diff --name-only feat/<slug>...HEAD
   ```
4. Post a `message_type="git_request"` reply in the feature thread asking Leader to merge your branch into `feat/<slug>` (unless you are Spec with doc-only changes, which can be committed directly to the feature branch).
5. Post a handoff message to the Moot channel in the active feature thread with the info below.

## Message Format

```
Handing off to @NextAgent.

**What was done:** [summary]

**Branch:** `<role>/<slug>` → merge into `feat/<slug>`

**Files changed:**
- `path/to/file1` — [brief description]
- `path/to/file2` — [brief description]

**What you need to do:**
1. [action item]
2. [action item]

**Pointers:** [links to specs, docs, or specific line numbers]
```
