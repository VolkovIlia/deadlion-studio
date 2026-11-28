# SlopZero engineering recovery in OMP

Use the tagged `v4.6.4` checkout or verify the release archive with `sha256sum -c deadlion-studio-4.6.4.tar.gz.sha256` before extraction. Link the `plugins/deadlion` directory with `omp plugin link` and restart OMP. [4.6.4 downloads](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.4)

## OMP ownership and integration

OMP owns model turns, native Goals, the task tool, subagents, cancellation, session continuation and Autoresearch. SlopZero records its engineering verdict separately. A local verification or strategy failure can settle with a stored `BLOCKED` verdict while OMP Goal stays active. The extension tracks the native goal ID to retain the same task and original baseline across follow-up turns. It uses OMP's documented `session_stop` decisions for a substantive recovery step or a ready campaign handoff. It settles when the same failure stalls, and does not call `ctx.abort()` for that condition. Only explicit stops, an exhausted approved budget and pre-dispatch admission failures use that cancellation path. The TUI still retains unsent text when the operator declines the 4.6.2 confirmation.

In OMP 19.2.1 the public TUI mode interface is unavailable in RPC. OMP RPC supports independent `goal` operations and controls automatic Goal continuation with `goal.continuationModes`. The extension does not create or replace native goals. OMP caps advisory stop continuations at eight. A blocking continuation is used when the gate has a new diagnosis, measured progress, a different strategy, or a legitimate next stage. A native Goal's status is separate from SlopZero's final receipt. [OMP extension lifecycle](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/docs/extensions.md) · [OMP RPC goals and settlement](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/docs/rpc.md)

## Execution policy and user controls

| Limit | Interactive default | Behavior |
| --- | --- | --- |
| Task elapsed time | Unlimited | A configured `seconds` limit stops the active run and retains the task. |
| Total engineering analysis | Unlimited | An explicit `analysisSeconds` budget is charged across the mission. |
| Task tokens | Unlimited | An explicit `tokens` budget is checked against reported usage, including identified children. Missing usage under a token cap stops the run. In-flight charges can cross the cap before the provider reports them. |
| Corrective attempts | No fixed number | Fresh evidence can continue. Old explicit `maxCorrections` remains a bound on automated corrections. |
| Technical operation timeout | 120 seconds per verifier subprocess | `operationSeconds` sets an approved finite bound. The inline stop hook has a short verification slice. Use the existing `deadlion_verify` tool for longer checks. |
| Unattended RPC invocation | Operator-specified | `dl-omp --seconds N` bounds one invocation and still validates the receipt and checkout. `--resume` reopens the original OMP session. |
| Evolution | Finite approved policy | The existing isolated evaluator still needs pinned training, holdout, iterations and wall time. It runs on demand and retains its own constraints. |
| Program resources | Approved contracts and gates | Recovery does not modify the approved thresholds, oracles, scopes or evaluator. |

Use `/deadlion budget` to inspect the remaining budget. To adjust it between runs, use `/deadlion budget seconds 900`, `analysisSeconds 240`, `tokens 50000` or `operationSeconds 180` with the same command prefix. `seconds` and `analysisSeconds` set new remaining time. `tokens` sets a cumulative ceiling. The operator may set task limits to `unlimited`; subprocess timeouts remain finite. Budget adjustments are recorded with the original task ID, baseline, usage and evidence. Use `/deadlion resume` when needed, or `dl-omp --resume ID --seconds N` in RPC. Use `/deadlion stop` or OMP cancellation to interrupt.

## Verification and recovery

The gate persists scoped check outcomes before choosing another action. The record includes the failure category, diagnosis, signature, recommendation, relevant checkout identity and receipt. Failure categories distinguish implementation, verification, performance, architecture, tools, environment, planning and resource interruptions. Recovery recommends correcting the defect, inspecting the environment or oracle, reconsidering the representation or workload, splitting the work, using the long-check tool, replanning or deferring. The main agent can use existing Computer Science, profiling, scaling and LSP tools, or delegate focused investigation through OMP. The independent evaluator and application contracts are unchanged.

A new passing check or an improved measured deficit relative to the recorded best counts as evidence. A first distinct diagnosis can justify investigation. Changed source bytes, reworded messages and alternating already-seen check outcomes cannot renew the same strategy. Normalized diagnostic signatures and a short history detect repeated states and A/B cycles. Bounded recent summaries keep sessions compact. Full gate receipts remain in the existing evidence store. Recovery derives its recommendations from the result and leaves the engineering choice to the agent. Scripted tests exercise the mechanism and do not evaluate a model's reasoning.

An expired technical verifier operation produces a local check failure with its actual command name and cause. It does not mark the result verified or expire the mission. The remaining analysis envelope and other applicable checks stay available. Mandatory coverage, structural ratchets, approval identity, performance contracts and final workspace fingerprints still apply.

### Verification approval

When the remaining verification issues require scope approval or independent review of a changed test, the task records `AWAITING_APPROVAL · NOT VERIFIED`. This status settles the current OMP turn without a corrective continuation or cancellation. Independent authorized diagnosis and implementation can continue under the same task ID and native Goal. An autonomous campaign can move a deferred milestone aside when the checkout matches its verified checkpoint. A failed approved check still follows the normal recovery flow.

For a standalone task, `/deadlion approve-tests <sha256> <file.json>` records an operator-reviewed addition. Supply the SHA-256 of the approval file. A `checks` array can add named `functional` checks using the existing `DL_ENGINEERING_POLICY` check format with explicit `argv` and `scope`. To approve an existing changed test separately, use a file such as `{"testRevision":{"tests/test_candidate.py":"<reviewed file sha256>"}}`. The test's current bytes must match that digest. Existing checks, the original baseline and the approved campaign policy remain in force. A fresh verifier run is required for acceptance. Shell output alone does not provide scoped evidence.

## Campaigns, independent work and replanning

Start with `/deadlion refactor start plan.md` and an approved DAG. Put an optional `Goal:` line above the milestone sections. Use `/deadlion refactor run` followed by an engineering prompt for native stop-time handoffs through that DAG. The existing `begin T1` selection remains available for explicit, single-milestone work. Its RPC result is marked with `scope: milestone`. A campaign-run RPC result is verified only after every mandatory milestone and the final cumulative gate pass.

Campaign state carries the original goal, base snapshot, policy, content-hashed stage receipts, checkpoints, current plan and budget. Each stage has its own task ID and the same campaign ID. Per-stage checks run when they cover the stage or an affected interface. Named required checks still run. Unscoped checks and final cumulative checks remain applicable. Verified stages are immutable. The original overall baseline is preserved even when a new plan checkpoint is recorded.

If recovery stalls and the working tree matches the verified checkpoint, the campaign can mark the current stage `DEFERRED` and continue a ready independent stage in the same OMP session. No dependency treats a deferred stage as complete. Reopen it with `/deadlion refactor begin ID` when its blocker is resolved. If failed candidate edits remain, the system records the blocker and retains those bytes. Review the candidate and restore only owned changes, or use OMP's isolated worktree workflow. The extension does not automatically rewrite a dirty checkout or remove operator edits.

An autonomous stage with a recorded diagnosis can call the existing `deadlion_verify` tool with `action: "replan"`, the proposed plan text and a rationale. The proposal may add independently verifiable prerequisites inside the preserved parent scope. It must preserve the goal and header, scopes, mandatory checks, existing dependencies and completed milestones. The checkout must match the verified checkpoint before the plan changes. The approved DAG is checked for cycles. The revision and reason are saved, and the next ready stage is selected. Repeating the same recorded cause cannot keep revising the plan. Use the existing operator review flow `/deadlion refactor revise` for changes beyond these technical permissions.

Use `/deadlion status` for the current task, goal, milestone, budget and recent recovery, and `/deadlion refactor status` for the DAG. `/deadlion report` exposes the receipt. State and history live with the original task or campaign under `$XDG_STATE_HOME/deadlion`, or `~/.local/state/deadlion`.

## Migration and limits

Existing tasks retain expressly configured limits. On restore, implicit 900-second, 120-second and two-correction defaults from 4.6.2 are removed. The original approved policy, checkout baseline and recorded evidence carry forward. Add `--seconds` to unattended `dl-omp` invocations and use existing OMP session controls for supervision. An existing campaign may continue using manual milestones or opt into `refactor run` after resolving any current reservation.

### Resume after a plugin update

When the installed integration changes during a running OMP process, Deadlion records `AWAITING_RESTART · NOT VERIFIED` and leaves continuation to OMP. Authorized independent work can continue. Restart OMP and reopen the **same** session when ready to verify. Use `omp --resume SESSION_ID` or OMP's session picker. Keep the current checkout and its edits in place.

The restarted process runs the gate against the original baseline with the updated integration. Task and goal IDs, policy, evidence history and budgets carry forward. A fresh receipt records the baseline integration and the integration used by the running verifier. The Core, analyzer executables, approved policy and verification inputs must still match. Pending functional scope and test-revision approvals follow the same task approval commands. A final campaign report whose receipt predates the loaded verifier needs another `/deadlion refactor verify`.

Recovery can choose independent work when the current checkout permits a safe handoff. Automated in-place rollback of dirty candidates, reopening verified milestones, multi-worktree integration, and autonomous execution after OMP exits remain outside this implementation. Recovery depends on the provider and the active OMP session. A scoped stage or a native goal's state does not certify the whole campaign. Advanced recovery for arbitrarily incompatible architecture changes still needs a recorded technical proposal or an operator decision.

## Reproduce

```sh
node --test tests/test_*_omp.mjs
python3 tests/omp_recovery_smoke.py
python3 tests/omp_refactoring_smoke.py
python3 tests/omp_engineering_smoke.py
python3 tests/omp_task_input_smoke.py
```

The live recovery fixture uses OMP and scripted loopback transport. It asserts more than two productive corrections, cycle detection, operation timeout recovery, deferred and waiting stages, independent work, controlled decomposition and final verification, original baseline retention, budget extension, preservation of dirty worktrees and native Goal continuity. GitHub CI includes the recovery fixture for the two pinned OMP versions.

On Fedora 44 all ten recovery scenarios passed with OMP 19.2.0 and 19.2.1. The verifier update fixtures retain an active native Goal, reject a cached PASS after an on-disk change, resume the original task after restarting OMP, and reject a later edit to an approved external oracle. The scope approval fixture invalidates acceptance after a subsequent test edit. [Hosted run and skipped scenarios for the tagged revision](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.4)
