---
name: verify
description: QA verification workflow. Rebuild the test stack, run tests, diff against spec, and post a structured pass/fail report. Use when QA receives a handoff.
argument-hint: [commit hash or feature name]
---

Run the QA verification workflow for a feature handoff.

## Steps

1. **Identify what to verify.** Check the recent Moot channel context for the handoff message. Note the commit hash, spec file, and files changed ($ARGUMENTS may contain the commit hash).

2. **Rebuild the test stack** (QA owns the stack). Use the project's rebuild command. For example, on a docker compose project:
   ```bash
   docker compose up --build -d
   ```
   Wait for services to be healthy.

3. **Install test dependencies** for your language/toolchain. For example:
   ```bash
   <project-test-install-command>
   ```

4. **Run the test suite:**
   ```bash
   <project-test-run-command>
   ```
   Note pass/fail count and any new failures.

   **If you see a flood of errors at suite start** (contention from residual state left over from a prior run, stale DB connections, etc.): restart the relevant services to clear residual state before investigating further. This is the first diagnostic step, not a last resort.

5. **Check the frontend build** (if applicable):
   ```bash
   <project-frontend-build-command>
   ```

6. **Code review.** Read the changed files and diff against the spec:
   - Does the implementation match the spec?
   - Are there deviations? Are they justified?
   - Were all spec test cases included?
   - Any security concerns (XSS, injection, etc.)?

7. **Post verification report** to the Moot channel in the feature thread:

```
Verification complete for [feature] (commit [hash]).

**Code review:** [Approved/Changes requested]
- [finding 1]
- [finding 2]

**Tests:**
- Backend: [X passed, Y failed]
- Frontend build: [clean/errors]
- New test coverage: [included/missing]

**Spec compliance:** [matches/deviations noted]

Verdict: **[Approved/Blocked]**
```

8. Mention Leader in the report so the pipeline advances. If blocked, mention Implementation with what needs to change.

9. **Small repairs.** If you find an unambiguous bug during verification (wrong status code, missing validation a test covers, obvious typo), fix it directly — commit to your branch and include the fix in your report. No git-request needed for these. If the fix involves judgment calls or design decisions, flag it instead of fixing.
