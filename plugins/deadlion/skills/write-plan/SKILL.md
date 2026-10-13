---
name: write-plan
description: "Turns approved product/design/architecture artifacts or a clear request into plan.md: small ordered tasks, each with exact files, a test written first and a verification command. Use before implementing anything larger than a one-file change."
---

# Write plan

Artifact contract (paths, `Status:` line, sections): `${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`.

## Inputs
Read whatever exists in `.dev-docs/features/<slug>/`: `product.md` (acceptance criteria),
`design.md` (screens, states), `arch.md` (components, interfaces). Use only artifacts with
`Status: approved`; if one is draft, show it and ask the user to approve first. With no
artifacts, plan from the request and read the code it touches.

## Rules
- Each task touches ≤1 component and ≤3 files. Bigger → split it.
- Task size: a reviewer can reject it while approving its neighbours; one sitting of work.
- When `.dev-docs/system.md` exists, each task's `Files:` lie inside one `projects/<name>/`
  (set `Project: <name>`). A contract change is one task touching `contracts/<c>.md` + the
  producer, followed by one task per consumer. Outside `projects/`, `Project: —`.
- Test first: every task names the test to write before the code, and what it asserts.
- No placeholders: no "TBD", "handle errors appropriately", "add tests", "etc.". Name the
  exact function, file, input and expected output.
- Every task has a `Verify:` command whose output proves the task works (a test selection,
  a CLI invocation with expected output, `dl-size` on the files). For `Project: <name>` it is
  `make -C projects/<name> test`, plus
  `${CLAUDE_SKILL_DIR}/../suckless-code/scripts/dl-budget projects/<name>` when SLOC grows.
  "Looks right" is not a check.
- Order tasks so the tree builds and existing tests pass after each one. Interfaces and
  data types before their callers; deletions of obsolete code in the same task that replaces it.
- Each acceptance criterion from `product.md` maps to at least one task's `Test:`.
- Prefer deleting or reusing code over adding it; say so in `Change:`.

## Format
Write `.dev-docs/features/<slug>/plan.md`:

```markdown
# <Feature> plan
Status: draft

### T1: <title>
Files: path/a.py, tests/test_a.py
Project: —
Change: <what changes, concretely>
Test: <test name> — asserts <behaviour>
Verify: pytest tests/test_a.py -q
Depends: —
- [ ] done
```

`Depends:` lists task ids or `—`. `build` flips `- [ ] done` to `- [x] done`.

## Finish
Show the task list (one line per task) and ask the user to approve. On approval set
`Status: approved`. For a one-file change the plan may stay inline in the conversation.
