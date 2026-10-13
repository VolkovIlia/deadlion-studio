---
name: build
description: "Executes plan.md task by task: dispatches the implementer subagent with only that task and the artifact paths, checks the diff and the task's verify command itself, then dispatches the reviewer subagent; marks tasks done in plan.md. Use when the user asks to implement or execute an approved plan."
argument-hint: "<slug>"
---

# Build

Artifact contract: `${CLAUDE_SKILL_DIR}/../workflow/references/artifacts.md`.

## Start
1. Slug = `$ARGUMENTS`; if empty, use the only directory in `.dev-docs/features/`, or ask.
2. Read `.dev-docs/features/<slug>/plan.md`. If `Status:` is not `approved`, show it and ask
   the user to approve. Never build a draft.
3. Run the project's test command once to record the baseline. Pre-existing failures are
   noted, not fixed silently.

## Loop — for each task with `- [ ] done` whose `Depends:` are all done
Tasks with different `Project:` values (not `—`) may be dispatched in parallel, at most 3
at once. Tasks in the same project, with `Project: —`, or touching `contracts/` run alone.

1. **Implement.** Dispatch the `deadlion:implementer` subagent. The prompt contains only:
   the task block verbatim, the artifact paths (`product.md`, `design.md`, `arch.md`,
   `plan.md` that exist) and any reviewer findings from the previous round. Never the
   conversation history.
2. **Check it yourself.** On `BLOCKED:` go to step 4 with the reason. On `DONE`:
   - `git diff --stat` — changed files must match the task's `Files:`; unexplained extra files are a finding.
   - Run the task's `Verify:` and, for `Project: <p>`, `make -C projects/<p> test` and
     `${CLAUDE_SKILL_DIR}/../suckless-code/scripts/dl-budget projects/<p>` fresh (rules:
     verify skill).
3. **Review.** Dispatch the `deadlion:reviewer` subagent with the task block and the diff
   scope (`git diff` of the task's files). It returns finding lines and `VERDICT:`.
4. **Repair.** If verify failed or any `BLOCKING` finding exists, re-dispatch the
   implementer with the failure output / findings. After 2 failed repair rounds on the same
   task, stop and report to the user: task id, what fails, the evidence. Do not continue to
   dependent tasks.
5. **Mark done.** Flip the task's line to `- [x] done` in `plan.md`. `IMPORTANT`/`NIT`
   findings that were not fixed are listed in the final report.

## Finish
- After the last task, run the root `make test` when a root Makefile exists, then invoke
  the `verify` skill for the whole feature.
- Report: tasks done, tasks blocked, open IMPORTANT/NIT findings, verify result.
- If the feature has UI and a `design.md`, suggest `ui-verify`.

## Never
- Never commit. Commits go through the `commit` skill, only on user request.
- Never edit code yourself to "finish" a task; send it back to the implementer.
- Never weaken a test, gate or `Verify:` command to make it pass.
