# SlopZero engineering recovery in OMP

Install or upgrade through OMP Marketplace. For a locally linked release, verify the archive with `sha256sum -c deadlion-studio-4.6.7.tar.gz.sha256`, extract it and link its `plugins/deadlion` directory with `omp plugin link`. Restart OMP after updating either installation. [OMP Marketplace instructions](../README.md#omp) · [4.6.7 downloads](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.7)

## OMP ownership and integration

OMP owns model turns, native Goals, permissions, cancellation and Autoresearch. SlopZero records a separate engineering verdict. An actionable failure supplies recovery context through OMP advisory continuation. A repeated failure with exhausted strategies yields `INCOMPLETE`. Verification setup failures leave native OMP tools available. Explicit cancellation and configured global budget limits still stop the run.

OMP controls when its Goals continue, including the RPC `goal.continuationModes` setting and the limit of eight advisory continuations. The agent runs `deadlion_verify` during the active turn to receive failures and advance campaigns. An unattended invocation that settles before a complete receipt returns a nonzero code. [OMP extension lifecycle](https://github.com/can1357/oh-my-pi/blob/v19.2.1/docs/extensions.md) · [OMP RPC goals and settlement](https://github.com/can1357/oh-my-pi/blob/v19.2.1/docs/rpc.md)

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

A repeated LSP failure can still produce an OMP continuation when the recovery strategy has an unused alternative. Repetition after the available strategies are exhausted and detected cycles defer the stage when independent work is available. Otherwise the engineering result stays incomplete. OMP still owns continuation, cancellation and the configured resource limits.

### Autonomous verification

The agent calls `deadlion_verify` before delivery. The tool returns failed checks, missing coverage and the receipt. The agent runs native tests and fixes failures within OMP's existing permissions. For production changes, functional acceptance uses an independent pinned check or workload oracle with matching scope. Ordinary shell test output supports diagnosis. Production and test changes may be split into independently verifiable stages when a changed test would otherwise be its own oracle.

For Python import-test grouping, the agent calls `deadlion_verify` with `action: "characterize_imports"`, the `path` of the test under `tests/` and, when relevant, its `ratchet` path. It runs the returned command through OMP's native Bash tool. The checker supports an existing `test_a_module_imports` parametrized on `MODULE_NAMES` and a grouped replacement that preserves the discovery code, imports each name in order and aggregates tracebacks at the end of the group. It compares the source with the original Git blob and initial snapshot, checks a 1,376-name trace with two injected failures and runs the full affected file in pytest. A passing receipt covers those exact files and the observed checkout. A different pattern or missing runner leaves the check pending.

### Scoped test evidence from another OMP run

When a functional scope is missing, `deadlion_verify` looks up the most recent eligible receipt for the current checkout fingerprint. The agent can attach a known receipt explicitly by calling the same tool with `action: "import_receipt"` and the absolute local `receipt` path. This also works for eligible 4.6.5 receipts created before automatic lookup was available. The active task keeps its ID, OMP session, policy and original baseline. The integration applies no new operator approval step.

Reuse requires both tasks to share the same checkout and evidence store. Deadlion checks the exact workspace fingerprint, receipt digest, donor task, pinned policy and recorded verifier inputs. The observed command must match the approved scope and show a nonempty test run without skips. A test-only edit can use a check recorded after the edit; production changes also require the same original baseline. Build and shared interface checks retain their existing coverage requirements. The active task still runs its applicable gates. A different worktree or changed verification inputs require a fresh check. The hashes detect stale evidence within the local user account and provide no isolation from other processes with the same OS permissions.

### Recovering from an LSP failure

Recovery tells the agent which file needs native `lsp` diagnostics and directs it to run `deadlion_verify` again in the active session. A complete diagnostic response from the required server can clear a recorded failure when the checkout fingerprint matches before and after the query. Incomplete responses and reports from other servers leave the semantic check unresolved. A later source edit requires fresh diagnostics. Functional coverage and the remaining checks still apply.

## Campaigns, independent work and replanning

The agent writes a Markdown DAG with `Status: active` and passes its project-relative `path` to `deadlion_verify` with `action: "campaign"` before implementation. The user's original goal and baseline are retained. The agent verifies each milestone with the same tool and receives the next ready stage. A campaign reaches `VERIFIED` when every required milestone and the final cumulative gate pass.

Campaign state carries the original goal, base snapshot, policy, content-hashed stage receipts, checkpoints, current plan and budget. Each stage has its own task ID and the same campaign ID. Per-stage checks run when they cover the stage or an affected interface. Named required checks still run. Unscoped checks and final cumulative checks remain applicable. Verified stages are immutable. The original overall baseline is preserved even when a new plan checkpoint is recorded.

After a recorded failure, the agent can use `action: "defer"` to select a ready independent stage at a clean checkpoint. Dependent stages wait for fresh verification. With unverified edits present, the agent can repair them, restore its own changes or use OMP's worktree workflow.

With a recorded failure the agent can use `action: "replan"` with the revised `plan` text and a `reason`. New prerequisites must stay within their parent scopes, preserve the goal, checks, dependencies and prior results, and pass cycle validation. The revision and cause are recorded against the checkpoint.

Use `/deadlion status` for the current task, goal, milestone, budget and recent recovery, and `/deadlion refactor status` for the DAG. `/deadlion report` exposes the receipt. State and history live with the original task or campaign under `$XDG_STATE_HOME/deadlion`, or `~/.local/state/deadlion`.

## Migration and limits

Existing tasks retain configured limits, policy, evidence and checkout baseline. Legacy `AWAITING_APPROVAL` tasks resume with the original ID. The agent receives the outstanding checks and continues through the standard verifier. Add `--seconds` to unattended `dl-omp` invocations.

### Resume after a plugin update

When the installed integration changes during a running OMP process, Deadlion records `AWAITING_RESTART · NOT VERIFIED` and leaves continuation to OMP. Authorized independent work can continue. Restart OMP and reopen the **same** session when ready to verify. Use `omp --resume SESSION_ID` or OMP's session picker. Keep the current checkout and its edits in place.

The restarted process runs the gate against the original baseline with the updated integration. A fresh receipt records both integration identities. The Core, analyzer executables, pinned policy and verification inputs must still match. If OMP restores a native Goal as paused, resume it with its native control. A campaign's final receipt must match the loaded verifier.

Recovery runs within an active OMP session and its existing permissions. Missing dependencies or unsatisfied requirements leave the result incomplete when available alternatives run out. Scripted transport validates this lifecycle and the evidence checks.

## Reproduce

```sh
node --test tests/test_*_omp.mjs
python3 tests/omp_recovery_smoke.py
python3 tests/omp_refactoring_smoke.py
python3 tests/omp_engineering_smoke.py
python3 tests/omp_task_input_smoke.py
```

The live recovery fixture uses OMP and scripted loopback transport. It asserts more than two productive corrections, cycle detection, operation timeout recovery, deferred and waiting stages, independent work, controlled decomposition and final verification, original baseline retention, budget extension, preservation of dirty worktrees and native Goal continuity. GitHub CI includes the recovery fixture for the two pinned OMP versions.

The import recovery fixture deliberately tries a grouping that drops failures, fixes it after the verifier rejects it, invalidates the first passing receipt with a source edit and reruns verification before delivery. The receipt-transfer fixture uses two actual OMP processes against one checkout. The Pyright recovery fixture continues after a repeated failure, repairs the file, verifies fresh diagnostics and checks that a subsequent source edit invalidates the result. The campaign fixture starts and advances stages through model tools. [Release test results](https://github.com/VolkovIlia/deadlion-studio/releases/tag/v4.6.7)
