---
name: review
description: "Reviews a diff for correctness, suckless limits, limit-gaming tricks and Unix design: dispatches the reviewer subagent, then confirms each finding against the code and drops unconfirmed ones. Use when the user asks for a code review or before merging."
argument-hint: "[git range]"
---

# Review

## Range
1. `$ARGUMENTS` if given (e.g. `main..HEAD`).
2. Else `git diff HEAD`, if it is non-empty (uncommitted work).
3. Else `HEAD~1..HEAD`.

State the chosen range and `git diff --stat` for it in one line each.

## Dispatch
Dispatch the `deadlion:reviewer` subagent with the range and, if a feature is active, the
paths of its `arch.md` and `plan.md`. It returns lines
`BLOCKING|IMPORTANT|NIT path:line — finding — evidence` and `VERDICT: approve|changes`.

When the range touches more than one `projects/<name>/`, dispatch one reviewer per project,
plus one for `contracts/` if it changed, in parallel (≤3 at a time), each scoped to its
paths. Merge their lines before the Confirm step.

## Confirm
For every `BLOCKING` and `IMPORTANT` finding, read the cited lines yourself (`Read` with a
range around `path:line`). Keep a finding only if the code actually shows the problem.
Drop findings that cite wrong lines, misread the code, or describe style the project does
not use. Downgrade a finding whose severity is overstated. NITs are passed through unchecked.

Severity:
- `BLOCKING` — wrong behaviour, data loss, security hole, `dl-size` or `dl-budget` violation, limit-gaming trick, broken interface or contract.
- `IMPORTANT` — missing test for changed behaviour, unclear error path, design drift from `arch.md`.
- `NIT` — naming, comments, minor simplification.

## Output
Print only the confirmed findings, one per line, in this format, then the verdict:

```
BLOCKING src/sync.py:88 — dedupe drops records with equal keys but different payloads — `seen` keyed on id only
NIT src/cli.py:12 — unused import os — no references
VERDICT: changes
```

`VERDICT: approve` when no BLOCKING finding remains; perfection is not required.
Then add one line: how many findings were dropped as unconfirmed.

Write `.dev-docs/features/<slug>/review.md` (format in `${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`) only when a feature slug is
active; otherwise print only.
