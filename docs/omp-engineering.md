# Engineering verification in OMP for Deadlion Studio 4.5.0

The package targets Fedora Linux, OMP 19.2.1 and Python 3.11+. The implementation starts from Deadlion 4.4.0 at `21d817529b25c55d3ecdcec9b80c1ca80024ea20`. Upstream tag `v19.2.1` resolves to `b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac`. A version match identifies the tested release. Runtime coverage depends on the active tools and project. [OMP source](https://github.com/can1357/oh-my-pi/tree/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac) · [4.4.0 evidence](scaling-verification.md)

For the 4.6.0 policy format, setup and compatibility matrix, see the [4.6.0 OMP guide](omp-4.6.md).

## Architecture and capability changes

| Area | Deadlion 4.4.0 | Native integration in this checkout |
|---|---|---|
| Design | Workflow, Unix design, plans, algorithm contracts and performance skills | Classifies requests, sets a minimum engineering mode, validates an approved contract and requires an initial executable measurement before implementation in contracted modes. |
| Diagnostics | Ruff, ast-grep, native analyzers and Infer Cost | Incremental tool feedback, native OMP LSP, optional Semgrep, source ranges, provenance and full reports. |
| Correctness and efficiency | Independent oracles, profiles, resource limits and scaling experiments | The verifier runs Core in the target scope and records results against a source fingerprint. |
| Completion | Performance-focused stop hook and separate CI gates | Parent-owned task gate, stale-evidence rejection, bounded explicit continuations, restart and RPC exit status. |
| Evolution | Isolated candidate editing, native Autoresearch, train/holdout verification and ledger | Operator-approved Evolution mode, frozen workloads, bounded launch and an accepted-commit check on the working tree. |
| Distribution | Skill export, individually loaded extensions | One native OMP package with skills, agents, commands and one model-facing verifier. Core remains callable from the CLI, Claude Code and Codex. |

The operator policy applies correctness, safety and agreed resource budgets before efficiency, implementation simplicity and maintainability. An operator can record a precise exception to the file-size policy and supply an executable check for the corresponding performance claim. The extension owns scheduling and evidence. Core owns algorithm validation, measurement and correctness checks. Algorithm contracts should name the input dimensions, distribution, alternatives, memory and time costs, update and preprocessing costs, invariant, oracle and experimental acceptance criteria. Read-only LSP actions are available during design through the native tool approval classifier. Take the initial measurement before saving in-tree design notes because it checks the entire original working tree. Successful schema validation establishes that the specified fields are present. The oracle, executable measurements and any independent proof establish their respective claims. Classification uses English and Russian prompt signals and the approved policy floor. Human review of design alternatives and proof obligations remains necessary.

## Installation

Use the `v4.5.0` checkout or extract the release archive and keep the resulting directory on disk. Run `omp plugin link /absolute/path/to/deadlion-studio/plugins/deadlion` with the path to that copy. The user link follows the directory. To update, switch the checkout to the desired release or link the newly extracted package, then restart OMP. Remove the link with `omp plugin uninstall deadlion-studio`.

For a project installation, run the following inside its Git checkout. Substitute the local Deadlion checkout containing the marketplace catalog.

```sh
omp plugin marketplace add /absolute/path/to/deadlion-studio
omp plugin install --scope project deadlion@deadlion-studio
omp
```

Update with `omp plugin upgrade --scope project deadlion@deadlion-studio`. Remove with `omp plugin uninstall --scope project deadlion@deadlion-studio`. OMP owns discovery of the extension, sibling skills and agent definitions. The link action uses the user plugin directory in this release. [OMP plugin loading](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/docs/extension-loading.md)

## Approved policy and operation

Set `DL_ENGINEERING_POLICY` to an operator-owned JSON file before starting OMP. Run project code, compiler plugins, profilers and test commands only in a trusted project or within an appropriate outer sandbox. An example for a trusted Python project follows.

```json
{
  "mode": "Standard",
  "tests": ["python3", "-m", "pytest", "-q"],
  "requireLsp": true,
  "seconds": 900,
  "analysisSeconds": 120,
  "maxCorrections": 2
}
```

| Setting | Effect |
|---|---|
| `mode` | Minimum of Standard, Performance, Research or Evolution. Prompt classification can raise the minimum. |
| `tests` | Approved argv executed at the project root. A code change needs functional verification or an applicable approved contract. |
| `checks` | Named executable steps in the approved plan, e.g. `[{"name":"golden output","argv":["./verify-golden"]}]`. Each must succeed and is recorded separately. Use `protectedPaths` for project-owned verification inputs. |
| `sizeExceptions` | Map an exact project-relative file to an approved justification. Size violations for that file produce a warning with the original tool output. Functional, static, contract and resource requirements still apply. |
| `native`, `requiredAnalyzers` | Opt into trusted project-native analysis and name required adapters, for example `["clang-tidy"]`. Use `DL_COMPILE_COMMANDS` for a compilation database in a custom build directory. |
| `trustProject` | Set true to permit discovery of a project test entry point from a Makefile, Cargo, Go, npm, Gradle, Maven or pytest project. Explicit `tests` takes precedence. |
| `protectedPaths` | Relative, existing files or directories for project-owned oracles, tests and build configuration whose alteration should block acceptance. |
| `projectVenv` | With `native`, prepend this trusted project environment's bin directory for the analyzer run. |
| `semgrepConfig` | Pinned local rules for the trusted CLI fallback. For an existing OMP Semgrep tool, omit this setting and require `semgrep` to use its result and scanned-file coverage. The MCP result format does not attest a separate CLI rule file. |
| `requireLsp` | Request fresh native semantic diagnostics for supported changed sources. Missing or partial required evidence prevents a successful verdict. |
| `profile` | Optional trusted profiling workload, e.g. `{"metric":"resources","argv":["./bench"],"max":{"peak_rss_kib":65536}}`. Use isolated contracts for untrusted candidates. |
| `seconds`, `analysisSeconds`, `maxCorrections` | Defaults are 900 seconds of elapsed time, 120 seconds of analysis and two corrective continuations. A repeated identical failure can stop earlier. |
| `tokens` | Optional foreground post-response accounting limit. Provider requests and auxiliary sessions can exceed the reported total. |
| `evolution` | For an explicit `/deadlion evolve` in Evolution mode, supply `goal`, `train`, `holdout`, `files`, `iterations` and `seconds`. The existing isolated launcher owns experiments, independent evaluation and the ledger. Candidate promotion remains an operator decision. |

For designated work, `DL_PERF_CONTRACT` names the approved contract and `DL_PERF_CANDIDATE_DIR` names the candidate. An in-project contract comes from the pinned commit. An external contract uses a dedicated trusted directory of regular fixtures. `DL_PERF_BASE` is resolved once on task creation. Higher modes select a sole baseline contract automatically. With multiple choices, designate one explicitly. For automatic selection in Standard mode, changed projects run the previously approved contracts under `.performance` conservatively. Newly written contracts require operator approval. Correctness checks and resource limits take precedence over the size policy. An operator must reconcile incompatible mandatory requirements before a task can pass.

Use `/deadlion doctor` for installation and live LSP client information. Use `status`, `mode` and `report` under the same command to inspect task state. `analyze` runs static checks on changed files. `verify` runs the gate. `scale` uses the approved scaling contract through the same Core gate. The registered `deadlion_verify` tool can take measurements within the longer task budget. The automatic stop pass reserves 20 seconds inside OMP's 30-second handler timeout. A full-check receipt can satisfy the subsequent stop pass after rechecking its source and tool identity.

For CI or other unattended callers, run the installed checkout's `plugins/deadlion/omp/dl-omp 'task'` from the target project. The launcher waits for OMP command discovery, prompt completion, session settlement and the task verdict. Exit 0 requires VERIFIED. The launcher checks the receipt digest, task ID, source fingerprint and PASS status before returning success. A missing receipt, cancellation or exhausted deadline produces a nonzero exit. `--seconds` limits supervisor time, `--offline` selects OMP offline behavior, and `--resume ID` reopens an unfinished session. Normal interactive OMP shows the engineering verdict as a notification.

## Evidence and change detection

A further prompt or process restart after a blocked task retains the original baseline, deadline and correction count. Separate work can start with a new native OMP session. A verified task can be followed by a new task in the same session. The extension records the task identity in OMP session entries. Reports live under `$XDG_STATE_HOME/deadlion/<task-id>`, defaulting to `~/.local/state/deadlion`. `baseline.json` records initial source fingerprints and index entries, including pre-existing changes. `task.json` records policy, mode, deadline, progress and evidence references. Gate receipts include the complete check outputs, source identity and changed paths. Incremental findings have separate full reports. Context summaries contain whole diagnostics and a report path.

For Git projects the final comparison includes tracked and unignored untracked files and index changes across commits. Opaque tools also trigger a throttled scan of Git changes. For non-Git projects, snapshots cover regular files and symlinks under the working directory, excluding `.git`, `.omp`, `__pycache__`, `node_modules`, `.venv`, `target` and `build`. Ignored artifacts, nested submodule contents and external services need explicit verification. Pre-existing findings on a subsequently edited file can still affect a whole-file or project-wide gate. The report identifies the verified scope without attributing authorship.

Ordinary sessions share the operator's OS identity. File permissions, digests and atomic writes support consistency and accident detection. A hostile process with the same host permissions can modify host evidence or settings. Use the independent candidate runner and trusted external CI for adversarial code. OMP's trust facade returns true unconditionally in this version. [Extension context](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/packages/coding-agent/src/extensibility/extensions/types.ts)

## OMP API audit

All rows refer to the tagged version above. The extension contracts live in `types.ts`, dispatch in `runner.ts`, and the stop/continuation policy in `agent-session.ts`. [Stop dispatch](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/packages/coding-agent/src/session/agent-session.ts#L6398) The smoke fixture installs a neighbouring extension to record lifecycle events and distinguish parent from child execution. [Live integration fixture](../tests/omp_engineering_smoke.py) · [Signatures](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/packages/coding-agent/src/extensibility/extensions/types.ts) · [Dispatch](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/packages/coding-agent/src/extensibility/extensions/runner.ts)

| API | Scope and limitation | Executable evidence |
|---|---|---|
| `before_agent_start`, `agent_start` | Per session. Preparation can replay. The task owns its baseline across calls. | RPC trace |
| `before_subagent_spawn`, `ctx.agent` | Parent spawn, then child-specific factories. An ambiguous parent lookup falls back to final disk comparison. | Task spawn and parent/child trace |
| `turn_start`, `turn_end`, `before_provider_request`, `context` | Per turn or provider request. Token usage availability depends on provider. | RPC trace |
| `tool_call`, `tool_result` | Pre-execution decision and post-execution result. Native edit results can include per-file diagnostics. | Ruff finding delivered to scripted provider, followed by correction |
| `agent_end` | Notification. Background work can resume. | RPC trace |
| `session_stop` | Main session only. Eight advisory continuations. An explicit block bypasses the advisory counter. | Actual extra request, correction, repeated failure and bounded terminal verdict |
| `registerCommand`, `registerTool`, `getActiveTools` | User command discovery, model-callable verifier, visibility of native LSP. | Launcher verifies a single command, fixture calls verifier and exercises clangd |
| `appendEntry`, `sessionManager.getBranch()` | Session-scoped pointer to task state. | Restart scenario |
| `user_bash`, `user_python` | User command interception, distinct from agent tool dispatch. Final diff is independent of the event. | Signatures audited. Direct interception NOT VERIFIED |
| `ctx.abort()`, `ctx.shutdown()` | Abort acts on the current operation. Shutdown closes a host session and has no engineering exit-code argument. | Bounded RPC abort exercised. Shutdown as a verdict carrier NOT VERIFIED |

The native `lsp` tool exposes diagnostics, hover, type definitions, definitions, references, implementations, symbols, code actions, status, capabilities and a raw request action. Call hierarchy requires support from the selected server. The extension API's `ctx.invokeTool` delegates only to the built-in with the same registered tool name. The version-specific bridge imports OMP's own `LspTool` and scoped settings for single-file diagnostics and targeted hover. In required-LSP projects a Python copy/sort hint with a resolvable target can carry a bounded hover result into the incremental report. It uses OMP's file synchronization and client pool. Server presence and a clean, fresh reply are recorded separately. Native clangd diagnostics after a Bash write were exercised. The observed diagnostic confirmed an undefined C identifier. In a Python fixture, native pylsp hover identified a list at the exact copy target. The evidence remained HEURISTIC and the summary carried the hover response. Type-directed algorithm conclusions, automatic call-hierarchy analysis and semantic coverage across all listed languages remain NOT VERIFIED. [Native tool](https://github.com/can1357/oh-my-pi/blob/b55cd1bb664d8ab46ddc77f2a34eb47555dbf1ac/packages/coding-agent/src/lsp/tool.ts) · [Local bridge](../plugins/deadlion/omp/lsp.mjs)

## Live scenario coverage

Each row names the fixture that exercises the installed binary. A provider request count comes from the scripted HTTP server. The gate and the tools still execute in OMP. The launcher asserts both the receipt and process exit. [Engineering RPC and PTY fixture](../tests/omp_engineering_smoke.py)

| Requested scenarios | Fixture | Observed result |
|---|---|---|
| 1–2. Native startup and discovery | `main`, `trial` | Linked and project-installed packages load on ordinary startup. RPC discovers the management command. The provider sees the plugin skill catalog and the native task tool runs the packaged `implementer` agent. |
| 3–4. Connected LSP and semantic error | `harness_scenarios` | An opaque Bash write introduced an undeclared identifier. The final report named clangd and failed. |
| 5–7. Inefficiency, agent feedback and correction | `incremental_scenarios` | The second provider request contained Ruff PERF102. The next edit cleared the issue and the gate verified the result. |
| 8–10. Bash, subagent and parallel writes | `harness_scenarios`, `parallel_eval`, `policy_scenarios` | The child trace includes a Bash call. The parent receipt includes its file. Two concurrent Bash writes and a subsequent commit preserved both paths. In a separate eval cell, two parallel workers wrote different files. The trace records separate child session IDs and the main gate includes both. |
| 11–13. Missing, failing and timed-out analyzer | `analyzer_failures` | Three distinct Ruff installations and an external writer exercised unavailable evidence, exit failure and forced timeout. |
| 14–15. User abort and stale receipt | `interrupted`, `incremental_scenarios` | RPC abort saved CANCELLED. Removing a required file after a passing verifier call invalidated that result. |
| 16–19. SLOC, allocations, runtime regression and oracle | `policy_scenarios`, `analyzer_failures`, `contract_scenarios` | The SLOC limit failed, trusted Memray measured allocations above zero, an isolated allocation metric remained unverified, a timing regression failed, and wrong candidate output prevented acceptance. |
| 20–23. Missing verification, real stop block, exhaustion and bounded retries | `required_and_simple`, `harness_scenarios`, `contract_scenarios` | New source without functional evidence was blocked. Resuming with “Finish” retained its task ID and failed on the same unverified file. The passing correction used three requests, the repeated failure finished after two, and zero correction budget added no retry. |
| 24–25. Moving HEAD and attempted relaxation | `policy_scenarios`, `contract_scenarios` | The original SHA remained in the receipt. Replacing an approved contract blocked completion. |
| 26–27. Simple task and restart | `required_and_simple`, `interrupted` | An unchanged Standard task ran no checks. After SIGKILL the resumed session kept the task ID and detected the pre-crash write. |
| 28–30. Extension coexistence, upgrade and uninstall | `neighbour`, `main` | A second extension observed events. Project startup succeeded after upgrade and uninstall preserved the neighbouring extension and byte-identical user configuration. |

`approved_checks` exercises an approved per-file size exception, fresh Ruff and ast-grep coverage, and a failing independent plan step. The optional `interactive` fixture starts the native TUI under a PTY and observes a final verdict. Print-mode startup and settlement run in the overhead fixture. `research_scenario` runs a small multidimensional workload before implementation and at verification. The provider receives the admissible observed models and a report path. `design_scenario` exercises native LSP inspection during design, the pre-implementation write block and the measured baseline.

## Analyzer coverage on Fedora

| Runtime or source | Live result | Project scope and cost |
|---|---|---|
| C and C++ | OMP clangd reported a semantic error. Clang-Tidy selected a translation unit in a nonstandard build directory. | Match the source entry in a compilation database. Build configuration and compiler options influence the result. |
| Rust | Clippy reported `clippy::iter_cloned_collect` in a workspace member. The regression asserts the full path. | Requires Cargo and the project's build dependencies. The toolchain was available outside the default PATH. |
| Go | Staticcheck reported SA6000. | Uses `go.mod` and scans the containing module. gopls was unavailable on the inspected PATH. |
| TypeScript and JavaScript | Project ESLint reported `@typescript-eslint/await-thenable`. A TypeScript language server was installed. | Runs the trusted project ESLint configuration. Separate TypeScript LSP evidence remains NOT VERIFIED. |
| Java and Kotlin | PMD and Detekt reported matching issues in a compiled mixed Gradle project. | PMD selects Java projects from Maven/Gradle markers. Detekt requires its configuration. No separate Java or Kotlin LSP was active in the test. Maven execution remains NOT VERIFIED. |
| Python | Live Ruff, ast-grep, a targeted native pylsp hover and a trusted allocation regression were exercised. With a partial multi-server reply the required semantic gate returned INCONCLUSIVE. | Fast AST checks run per change. A profile runs only for an approved workload. |
| Semgrep | The CLI adapter found `redundant-add` with a local rule and verified scanned-file coverage. | Approved rules and opt-in CLI execution, or the existing OMP tool result. There was no installed OMP Semgrep MCP to test. |
| Infer Cost | The earlier bounded Java probe is recorded in the 4.4.0 evidence. The current host probe returned NOT VERIFIED because `infer` was absent from PATH. | Requires an executable compiler/capture environment. |

A warm run of the Core entry point took 104 ms for the Cargo member, 259 ms for Go, 312 ms for the Clang database, 665 ms for typed ESLint and 1,890 ms for PMD and Detekt together. These are single observations under concurrent load. [Inputs, statuses, diagnostics and timings](omp-engineering-probes.json)

Timing distributions and tool availability depend on the checkout and toolchain. Historical Core measurements include native startup, PMU probes, latency, RSS and allocation metrics. Installed executables, configured servers, live clients and successful task checks appear separately in `/deadlion doctor`. The full per-server equivalence and per-language cost matrix remains incomplete. Native tools and LSP servers may report overlapping findings, especially with project-specific compiler plugins. [Core measurements](scaling-probes.json)

## Measurement and reproduction

Run these commands from a Git checkout of `v4.5.0`. The distribution archive contains the runtime, guides and saved measurements. The checkout also includes the test fixtures and requirements-dev.txt.

```sh
python -m pytest -q
node --test tests/test_performance_omp.mjs
DL_TEST_TUI=1 python tests/omp_engineering_smoke.py
python tests/omp_autoresearch_smoke.py --contracts
python tests/omp_engineering_evolution.py
python tests/omp_engineering_bench.py
```

The engineering smoke uses a local scripted transport, an isolated OMP profile, Ruff, clangd and the existing Linux candidate isolation prerequisites. Install ast-grep on PATH for full structural checks. Enable Memray on PATH to exercise the trusted allocation regression. The optional PTY scenario uses pexpect. The pylsp fixture enables its existing Python user-base installation inside the isolated profile. The baseline Autoresearch fixture separately exercises train/holdout evaluation, rejection, pause and resume.

On Fedora 44, five alternating-order repetitions compared the same linked profile with and without OMP’s `--no-extensions` flag. They measured the full print-mode process from startup through settlement for one scripted prompt. The projects contained 12 or 10,000 synthetic Python files. With 12 files the median was 271 ms without the extension and 465 ms with it. With 10,000 files the medians were 410 ms and 1,270 ms. Median serialized input messages grew from 13,779 to 14,727 characters. The first extension-enabled small-project run reached 16,303 characters. Warm filesystem caches, process startup and local transport are included. These counts describe serialized messages. Calibrated provider-token and monetary costs are unavailable. [Raw runs](omp-engineering-overhead.json) · [Benchmark](../tests/omp_engineering_bench.py)

The Core suite passed 173 tests with the installed Cargo toolchain on PATH. All four existing Node extension tests passed. The main live fixture produced 12 expected VERIFIED and 16 expected BLOCKED trial results. It also checked a retained block on resume, an actual user abort, crash recovery and the interactive terminal. The Evolution management fixture and the original native Autoresearch contract fixture passed independently. These live commands run outside pytest.

PMD 7.30.0 and Detekt 1.23.8 reported `UseStringBufferForStringAppends` and `detekt.performance.ForEachOnRange` on Java and Kotlin sources in one Gradle project. Gradle 9.4.1 completed clean compilation with Kotlin plugin 2.2.10 and OpenJDK 25 targeting JVM 24. The local Semgrep CLI was found outside PATH. The inspected OMP user MCP configuration listed `rea`. No Semgrep configuration was added. Historical Core probes cover additional runtimes and tool versions. [Core probe matrix](scaling-probes.json)

**Agent quality is NOT VERIFIED.** The installed Ollama and llama.cpp executables were found. No suitable weights were found in the inspected model stores, and local inference endpoints on ports 11434, 1234 and 8080 refused connections. No paid requests or new independent real-model generations were made. The intended arms are A (OMP), B (skills), C (4.4.0 adapter), D (native control plane), and E (control plane with budgeted Evolution). Within each model and task, hold tool permissions, workload, wall-clock and token budgets constant. Randomize arm order and include failed, timed-out and refused generations. Use unseen independent grading on search, graphs, parsing, numeric kernels, files, collections, memory, concurrency, SQL and concurrent I/O. Report pass rates and uncertainty, measured scaling, time, RSS, allocations, missed and false positives, corrective turns, cache reads/writes, uncached tokens and cost per correct result. Comparison across weaker and stronger models needs multiple independent generations per arm. All five arms currently have zero new real-model samples in this audit. Scripted transport and prior solution regrading do not supply these data.

## Remaining boundaries

- The parent gate verifies the final visible working tree and catches edits outside OMP. Live task subagents and parallel eval-created agents were exercised. Revived agents and mutating advisors were inspected at source level only. An advisor has a separate native tool session. The main disk scan covers visible output within its scope, and mutations arriving after verification require a new check. Child evidence has its own files and the parent recomputes its verdict. Attribution across unrelated writers remains inconclusive.
- Receipts are specific to the captured tree, configuration, approved inputs and local executable identities. The Core fast cache is limited to eligible Python checks. A native executable stat fingerprint does not describe all system libraries, ignored build outputs or environmental inputs. Use an independently pinned environment for reproducible claims.
- Static diagnostics keep evidence provenance. Known matching spans can coalesce corroboration. The adapter does not implement general cross-language semantic equivalence. Observed growth and hover information do not constitute a mathematical proof.
- Evolution keeps training, holdout, evaluator, candidate and provider boundaries from 4.4.0. Candidate processes remain isolated. The operator may inspect an accepted commit before importing its files. Foreground token accounting is post-response and auxiliary/provider costs are incomplete. A resumed OMP session executed `/deadlion evolve`, used its frozen holdout after the original fixture changed, and left the working candidate intact. After the fixture explicitly imported the accepted bytes, the original task verified the matching ledger commit. [Management command experiment](../tests/omp_engineering_evolution.py)
- A strict process exit requires the RPC launcher. OMP's interactive status and normal print exit are not independent CI verdicts. A session can change again after verification. An authorized operator or external CI owns final acceptance.

## Changed files

| Area | Files |
|---|---|
| User entry points | `README.md`, `plugins/deadlion/package.json`, `plugins/deadlion/skills/performance/references/commands.md` |
| OMP integration under `plugins/deadlion/omp/` | `performance.mjs`, `commands.mjs`, `gate.mjs`, `evidence.mjs`, `diagnostics.mjs`, `lsp.mjs`, `semgrep.mjs`, `process.mjs`, `workspace.py`, `approved.py`, `capabilities.py`, `experiment-result.py`, `dl-omp` |
| Existing Core scripts and report representation | `changed_contracts.py`, `dl-analyze`, `native_diagnostics.py`, `python_hints.py`, `diagnostic_report.py` under `plugins/deadlion/skills/performance/scripts/` |
| Verification | `tests/test_engineering_core.py`, `tests/omp_engineering_smoke.py`, `tests/omp_engineering_bench.py`, `tests/omp_autoresearch_smoke.py`, `tests/omp_engineering_evolution.py` |
| Audit | `docs/omp-engineering.md`, `docs/omp-engineering-overhead.json`, `docs/omp-engineering-probes.json` |
