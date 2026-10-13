---
name: verify
description: "Evidence before claims: before saying work is done, fixed or passing, run the proving command fresh, read its output and the git diff, and report VERIFIED and NOT VERIFIED items separately. Use before declaring any task complete and after any subagent reports success."
---

# Verify

No claim of done/fixed/passing without fresh evidence from this turn.

## Procedure
1. Identify the command that proves the claim: the task's `Verify:` line, the test that
   reproduces the bug, the acceptance criterion's check. If none exists, that is a
   NOT VERIFIED item.
2. Run it now. Earlier output, a subagent's pasted output, or "it should work" does not count.
3. Read the output: exit code, pass/fail counts, warnings. Skipped or zero collected tests
   are not a pass.
4. `git status --short && git diff --stat` — the changed files match what is claimed; no
   stray, missing or unintended files.
5. Run the linter if the project uses one, `dl-size` on changed files and `dl-budget` on
   changed programs (`${CLAUDE_SKILL_DIR}/../suckless-code/scripts/`), and `dl-contrast`
   on changed token files (`${CLAUDE_SKILL_DIR}/../ux-design/scripts/`).
6. Report.

## Report format
```
VERIFIED: <claim> — `<command>` → <observed result>
NOT VERIFIED: <claim> — <what was not exercised and why>
```
Put every VERIFIED line first, then every NOT VERIFIED line. If anything is NOT VERIFIED,
do not call the work complete.

## Honest reporting
Partial work reported honestly is acceptable. Partial work reported as complete is a
failure. When something cannot be verified, downgrade the claim; never round it up.

## Prohibited claims
- "Done", "fixed", "all tests pass" without command output from this turn.
- "All tests pass" when no test covers the changed lines.
- "Ready for review" without proof.
- Future tense as completion: "I'll update…", "Next I need to…".
- Accepting a subagent's success report without checking its diff and rerunning its check.
- Weakening a test, gate, threshold or verify command so it goes green.
- Reporting part of the work (backend done, frontend missing) as the whole.

## Claim → evidence
| Claim | Required evidence this turn | Not enough |
|---|---|---|
| tests pass | test command output, 0 failures, >0 collected | earlier run, "should pass", a subagent's paste |
| it builds | build command exit 0 | linter or type check passing |
| bug fixed | the repro test failed before the fix and passes after | "the code looks right" |
| program done | `make -C <dir> test` and `dl-budget <dir>` exit 0 | unit tests alone |
| contract honoured | producer output matches the contract example; consumer fixture test passes | reading the code |
| UI works | ui-verify PASS this turn: dl-tui blocks at 80×24 and 40×12 (terminal) or Playwright screenshots at 375/768/1280 (web), and dl-contrast exit 0 | "looks right", a description without a capture |
