# Deadlion Studio 4.4.0 verification

The 4.4.0 measurements were collected on 2026-11-28 on Fedora Linux with an Intel Core i7-12700K. The audit starts at the tagged 4.3.0 revision. Each result below identifies the fixture, command or saved evidence used to obtain it. [Baseline revision](https://github.com/VolkovIlia/deadlion-studio/commit/fc1bc6955d2556626369d539ded965c32d2093e3)

## 1. Starting state

`git ls-remote origin HEAD` returned `fc1bc6955d2556626369d539ded965c32d2093e3`, the local HEAD and the requested audit revision. The existing contract control, Pareto frontier, optional profilers, AST corpus and OMP Autoresearch were retained. At that revision 21 performance-tool tests and three Node adapter tests passed.

## 2. Findings

The old PR job loaded approved fixtures from the base commit and executed the PR's evaluator. The OMP launcher exposed a writable host root to the harness. Fixed stdout hashes excluded numeric and observable-state oracles. Fast Python analysis skipped Deadlion's structural hints. During implementation, a 50 MiB allocation exposed an additional measurement error. Waiting only for Bubblewrap's immediate PID missed work attributed to its reparented descendants. The Linux worker now adopts those descendants, accumulates CPU and context switches and takes the largest process RSS. A regression test checks both CPU work and an allocation of known size. All saved resource measurements were repeated after that change. [Baseline CI](https://github.com/VolkovIlia/deadlion-studio/blob/fc1bc69/.github/workflows/ci.yml) · [Runner](../plugins/deadlion/skills/performance/scripts/candidate_runner.py) · [Regression tests](../tests/test_scaling.py)

## 3. Methods and upstream tools

The investigation covers benchmarking libraries, language-native checkers, empirical modeling, symbolic cost, evolutionary search and external agent tasks. ESA and Extra-P were exercised on exact data. Extra-P also read the exported measured sort cohort. The core CLI has no numerical-library dependency. [Research, source revisions, licenses and probe results](scaling-research.md)

## 4. Mathematical model

For each implementation, distribution and metric, fit a nonnegative `a + b f(x)` on training coordinates. The slope is a median of pairwise slopes. A negative intercept triggers a through-origin fit. Power and exponential families select their parameter from a documented finite grid using training errors. Explicit formulas allow other exponents, bases and combinations of dimensions. The output reports the fitted expression. Validation uses every third coordinate in lexicographic order plus the last coordinate, with all repeats of a coordinate held out together. This evaluates prediction on designated points in the sampled design.

A model remains admissible if its predicted relative error band intersects the user-specified tolerance at each holdout point. A unique family receives EMPIRICALLY CONSISTENT only when its predictions also satisfy tolerance throughout those observed median intervals. The intervals describe holdout medians, conditional on the fitted training model. They are pointwise sign intervals, subject to independence and stationarity. They do not give a posterior probability for a family. Ambiguity, insufficient repetitions and poor prediction yield INCONCLUSIVE.

Absolute median limits and growth ratios use distribution-free intervals with multiplicity adjustments within each requirement family. Comparisons preserve paired instances and use simultaneous intervals across reported pairs and points. A crossover requires resolved opposite signs at measured points on one axis. A piecewise log-slope observation requires improved held-out prediction on both sides. Profiling is necessary to assign a hardware cause. [Model selection](../plugins/deadlion/skills/performance/scripts/growth_models.py) · [Decision logic](../plugins/deadlion/skills/performance/scripts/scale_report.py)

The proof boundary has a concrete example. For the BFS counter fixture, assume all vertices are reachable, one constant-cost visit per dequeue and one per scanned adjacency entry. Each vertex is marked before enqueue, so it is dequeued exactly once. Its adjacency list is scanned once. Summing those list lengths gives E. The exact count V+E is **PROVEN under that model**. Infer Cost separately emits STATICALLY BOUNDED for supported symbolic results under its capture assumptions. Neither status can be emitted by the curve fitter. A quantitative limit can be CONTRADICTED on its specified workload. [Counted BFS](../plugins/deadlion/evals/scaling-holdout/grade.py) · [Infer probe](scaling-probes.json)

## 5. Architecture

`dl-perf scale` extends the existing CLI. The trusted generator produces one byte sequence per seed and coordinate. Every implementation in the block receives those bytes. An evaluator verifies output independently, then analyzes confirmation samples. Optional exploration adapts repetitions before a fresh fixed confirmation batch. Geometric ranges, explicit sizes, bounded grids, fixed-axis sweeps and adaptive single-axis steps share the same runner. Separate instrumented commands can report operation counts with a checked result. Candidate-reported counters are descriptive. Only independent metrics enter quantitative gates. The same Pareto calculation serves the existing frontier command and observed wall-time/RSS cohorts.

## 6. Implemented tools

- **dl-contract** validates the scaling section, units expressed by metric names, candidate argv, design size, oracle and model expressions.
- **dl-perf scale** emits concise output, JSON, CSV, replay and Extra-P JSON Lines. Reports preserve seeds, data and implementation hashes, raw samples, model alternatives, residuals, paired intervals, limits, anomaly observations and stop reasons.
- **dl-perf / dl-perf-gate** share exact, decimal tolerance and external oracles. An external verifier can test reference results, properties and declared state files. Optional determinism repeats check bytes and state. Gates include absolute, relative, allocation, CPU, latency, throughput, PMU and scaling criteria.
- **dl-analyze** includes post-edit Python copy/sort checks, full ast-grep review, native Clippy, Staticcheck, Clang-Tidy, PMD, Detekt and configured ESLint adapters. The explicit Infer Cost capture mode reads bounds for selected Java sources. The report identifies applicable native tools and missing installations. LSP remains owned by the harness. The native probes produced Clippy iter_cloned_collect, Clang-Tidy performance-for-range-copy, PMD UseStringBufferForStringAppends, Detekt ForEachOnRange, Staticcheck SA6000, typed ESLint await-thenable and Infer Cost's polynomial. [Probe output](scaling-probes.json)

## 7. OMP integration

OMP 19.2.1 exercised its native Autoresearch with a local scripted model transport. Candidate shell commands see the approved editable files. User systemd enforces a shared transient slice for the controller, external evaluator service and separately isolated trials. Foreground token usage remains post-response accounting. A keep requires fresh evidence for the same candidate, plus the protected holdout in contract mode. Training emits a measured primary cost, using the worst paired median time ratio across declared points/comparators for a scaling contract. The holdout evaluator rejects reused training inputs. The simple data-verifier mode remains available.

`python tests/omp_autoresearch_smoke.py` exercises keep, pause, resume, rejection and discard. Its `--contracts` variant runs the training and holdout evaluators outside OMP using separate socket requests. `node tests/test_performance_omp.mjs` checks the edit and stop adapters. A designated performance task uses DL_PERF_CONTRACT to require fresh evidence at session stop. For committed .performance contracts the stop hook also selects changed declared inputs and evaluates against files archived from DL_PERF_BASE (default HEAD). Standard edits outside those inputs take the local diagnostic path. [OMP experiment test](../tests/omp_autoresearch_smoke.py) · [External evaluator](../plugins/deadlion/omp/contract_evaluator.py)

## 8. Known algorithms

A separately runnable corpus counts actual comparisons, iterations, recursive calls and graph visits, then applies the analyzer. Among 11 labelled cases it gave five unique correct decisions, six abstentions and zero unique wrong decisions. The unique decisions covered linear traversal, quadratic pairs, cubic loops, recursive Fibonacci in the specified candidate set and BFS with independent V/E. Binary search, random sort and memoized recursion illustrate the effect of finite sizes and model constants. The corpus is small and authored within this project. [Fixture definitions](../plugins/deadlion/evals/scaling-holdout/grade.py) · [Every outcome](../plugins/deadlion/evals/scaling-holdout/results.json)

## 9. Measured programs and system workloads

| Experiment | Measurements | Result on this machine |
|---|---:|---|
| Membership scan versus building a set and querying it | 528 confirmed runs, 12 independent n/q combinations, two distributions | The scan on uniform inputs was consistent with n*q among the five specified models. At n=8192, q=1024, the indexed/scan median time ratio was 0.467 with interval [0.436, 0.512]. On duplicate-heavy inputs it was 0.287 [0.255, 0.345]. Construction, parsing and process startup are included. Multiple time models remained admissible for the indexed version. [Measurements](../plugins/deadlion/evals/scaling-membership/measurements.json) |
| GNU sort -n versus CPython sorted on signed integer records | 252 uninstrumented runs and 126 separate Python comparison-count runs | On uniform inputs the measured Python comparison count was consistent with n log n. Both linear and linearithmic time predictions remained admissible for GNU sort. Seven pairs per coordinate were insufficient for simultaneous crossover intervals over the full design. [Measurements](../plugins/deadlion/evals/scaling-sort/measurements.json) |
| Allocation/reuse, working-set traversal, data layout, lock contention and sequential/concurrent tmpfs I/O | 120 checksummed runs plus two pinned C counter runs | Both variants produced the exact mathematical checksum. The two C runs produced 2,000,000 increments each. These are descriptive system observations. The tmpfs case measures the buffered file API on this host. [Driver](../plugins/deadlion/evals/scaling-systems/run.py) · [Measurements](../plugins/deadlion/evals/scaling-systems/measurements.json) |

## 10. Accuracy and limitations

Results apply to the specified model set, process boundary, distributions and sampled ranges. Free-parameter searches have finite resolution. Lexicographic holdout can provide uneven coverage of a multidimensional space. Training-set uncertainty, autocorrelation and model search affect interpretation. The splitter does not diagnose cache capacity. Reported process peak RSS measures the largest process high-water mark and includes launcher overhead. The service memory ceiling limits aggregate charged memory. Small timing differences can be dominated by startup. Unit tests cover a true crossover, ambiguous curves, sparse inputs, outliers, a change of slope, huge fixed overhead and missing confidence intervals. [Tests](../tests/test_scaling.py)

## 11. Security verification

Tests used benign markers to check private environment, filesystem and network views, read-only inputs, state transfer, deadlines, output caps and memory exhaustion. The runner checks effective cgroup v2 CPU, memory, swap and task limits before launching a candidate. Candidate files and approved artifacts have separate mounts. The controller owns attempt slots and the usage ledger. Restart tests include consumed iterations and persisted decisions. A verifier executing candidate code inside its own address space cannot establish independent correctness. Use external contract evaluation for executable candidates. This is a tested Linux configuration, with no claim of kernel-level containment assurance on arbitrary hosts.

The PR workflow uses the base-controlled event, a read-only token, no repository secrets, pinned actions and an ephemeral hosted runner. It fetches Git objects and extracts only approved regular file blobs by object ID. The only checkout is the base evaluator. An absent approved contract yields NOT VERIFIED. Every verdict is saved with both SHAs. The local staging/control test ran the working-tree evaluator against blobs from fc1bc69. GitHub reported `protected: false` for main and an empty effective branch rules list. Enforced review and merge protection remain an administrator deployment item. The existing CODEOWNERS assigns review to the maintainer. [Workflow](../.github/workflows/performance.yml) · [Evaluator entry](../scripts/approved-performance) · [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use)

## 12. Gate results

All 26 membership resource/growth checks verified. A second execution through dl-perf-gate passed both the fixed comparison and all criteria on 528 fresh scaling observations. [Independent gate run](../plugins/deadlion/evals/scaling-membership/release-gate.json) Increasing n from 2048 to 8192 with q=1024 produced an indexed median time ratio interval [0.885, 1.108] on uniform data against a declared ceiling of 4. Memray observed 95 allocations and 1,004,032 bytes in the fixed control. A ceiling of zero rejected the run. The p99/throughput probe collected 1,000 responses and passed its fixture budgets. Relative RSS passed. PMU was NOT VERIFIED with perf missing and VERIFIED when perf 7.3.6 was supplied, including isolated execution. These ceilings belong to fixtures. The release evidence includes the raw observations or profiler totals used for each decision. [Gate probes](scaling-probes.json) · [Membership checks](../plugins/deadlion/evals/scaling-membership/measurements.json)

On a variable hosted runner, preserve INCONCLUSIVE and both SHAs. Recheck on a controlled project runner with the same inputs, oracle and build. A base contract may explicitly mark inconclusive evidence advisory through `ci_inconclusive: advisory`. Required missing evidence remains unverified. A new required gate should be enabled after its evaluator has reached the protected base and the target runner has demonstrated the necessary controllers.

## 13. Coding-agent comparison

The agreed budget was a local pilot without paid provider calls. No running local Ollama service or suitable local weights were found in the inspected model locations. The archived repeat solutions were regraded under the original grader in four separate isolated services in order C, A, D, B. Each passed 8/8. These letters retain their historical meanings. There are no new agent generations in this dataset. The scripted OMP transport measures workflow behavior. Systematic differences between 4.4.0 and the other arms remain NOT VERIFIED. [Regraded results](../plugins/deadlion/evals/agent-performance/repeat/regrade-4.4.json) · [Original treatment definitions](../plugins/deadlion/evals/agent-performance/README.md)

For a powered comparison, block by task and model, including a weak and a medium local model. Within each block balance the five treatments A without Deadlion, B at 02aa71c, C at fc1bc69, D at the frozen 4.4.0 revision and E at the same revision with Evolution. Use fresh independent sessions, identical prompts, tool permissions, model versions and resource envelopes. Retain failures and budget exhaustion in the denominator. Freeze graders and unseen input generators before sampling. Estimate paired task-level variance in a separate pilot, define the smallest meaningful effect, then select task and generation counts by resampling whole tasks at the preregistered power. Report per-task intervals and aggregate uncertainty with tasks as the independent units. No power estimate can be derived from regrading four saved solutions.

## 14. Tokens and resources

The old repeat recorded 17,796 / 157,773 / 129,767 / 258,221 input tokens including cached inputs. No new provider cost or token reduction was measured for 4.4.0. The OMP edit adapter caps its response at five findings and 4,096 characters. Full results go to files. On this host the first clean cached Python invocation took 30.6 ms and the median of eight subsequent invocations was 25.9 ms. Across 11 true-command probes, median direct launch was 0.45 ms, sandboxed execution 4.53 ms and parent-observed service dispatch plus execution 49.93 ms. Batching operations inside a workload can improve resolution if the oracle covers the whole batch. [Raw resource probes](scaling-probes.json) · [Historical usage](../plugins/deadlion/evals/agent-performance/repeat/usage.json)

## 15. Installation and use

Use Python 3.11+, Bubblewrap, a user systemd manager and functioning cgroup v2 CPU, memory and pids controllers on Linux. Install only the native analyzers required by the project. ast-grep 0.51.3 is used for full structural review. Run the following commands from the repository root.

```sh
tools=plugins/deadlion/skills/performance/scripts
contract=plugins/deadlion/evals/scaling-membership/contract.json
"$tools/dl-contract" "$contract"
"$tools/dl-perf" scale "$contract" --output /tmp/scale.json --csv /tmp/samples.csv
"$tools/dl-perf" scale "$contract" --replay /tmp/scale.json --extrap /tmp/scale.jsonl
"$tools/dl-perf-gate" "$contract" --isolated
```

The command reference describes the generator, state and numerical oracles, adaptive designs, optional operation counts, native project diagnostics and OMP activation. [CLI and OMP reference](../plugins/deadlion/skills/performance/references/commands.md)

## 16. Changed files

| Directory | Files |
|---|---|
| `.claude-plugin` | `marketplace.json` |
| `.github/workflows` | `ci.yml`, `performance.yml` |
| `.` | `CHANGELOG.md`, `README.md` |
| `docs` | `scaling-probes.json`, `scaling-research.md`, `scaling-verification.md` |
| `plugins/deadlion/.claude-plugin` | `plugin.json` |
| `plugins/deadlion/evals/agent-performance/repeat` | `regrade-4.4.json` |
| `plugins/deadlion/evals/scaling-holdout` | `grade.py`, `results.json` |
| `plugins/deadlion/evals/scaling-membership` | `contract.json`, `expected`, `generate.py`, `indexed.py`, `input`, `measurements.json`, `release-gate.json`, `scan.py` |
| `plugins/deadlion/evals/scaling-sort` | `contract.json`, `expected`, `generate.py`, `input`, `measurements.json`, `sort.py` |
| `plugins/deadlion/evals/scaling-systems` | `measurements.json`, `run.py`, `work.py` |
| `plugins/deadlion/evals` | `verify-scaling-release.py` |
| `plugins/deadlion/omp` | `candidate.py`, `contract_evaluator.py`, `dl-evolve`, `evolution.mjs`, `experiment-rpc.py`, `experiment_budget.py`, `performance.mjs` |
| `plugins/deadlion/skills/performance` | `SKILL.md` |
| `plugins/deadlion/skills/performance/references` | `commands.md` |
| `plugins/deadlion/skills/performance/scripts` | `candidate_runner.py`, `changed_contracts.py`, `correctness.py`, `dl-analyze`, `dl-contract`, `dl-perf`, `dl-perf-gate`, `growth_models.py`, `native_diagnostics.py`, `pareto.py`, `python_hints.py`, `scale_contract.py`, `scale_report.py`, `scaling.py` |
| `plugins/deadlion/skills/verify` | `SKILL.md` |
| `scripts` | `approved-performance` |
| `tests` | `omp_autoresearch_smoke.py`, `test_performance_omp.mjs`, `test_scaling.py` |

## 17. Verdicts

The local acceptance run passed 168 pytest cases, four Node adapter tests, 19 ast-grep rule fixtures, the skill export test and strict Claude plugin validation. Both native OMP smoke modes completed. GitNexus found medium aggregate change risk, including the Main → Git smoke-test path. Extensionless command bodies do not have complete symbol coverage in the baseline index.

- **VERIFIED locally** — CLI measurement and replay, exact/numeric/external-state verification, the observed system fixtures, resource gating, source-blob staging, OMP's native lifecycle, AST post-edit coverage, native diagnostics on Rust, C++, Go, Java, Kotlin and TypeScript fixtures and Infer Cost on one Java fixture.
- **INCONCLUSIVE** — several time and RSS model families on the sampled inputs, and hardware explanations for observed slopes.
- **NOT VERIFIED** — live hosted PR enforcement, independent replication on another machine, universal classification accuracy, general sandbox security, quality improvements for newly generated agent solutions, token savings and paid-provider budgets.

## 18. Remaining work and boundaries

Hosted runner support must be confirmed on an actual PR after deployment. Repository protection and required checks need maintainer configuration. The native probes used PMD 7.30.0, Detekt 1.23.8, typescript-eslint 8.74.0 and Staticcheck 2026.2.2. Monorepo build layouts and other tool versions require their own compatibility checks. Untrusted Memray in-process counters cannot satisfy an isolated gate. An external proof or symbolic result requires its own assumptions and provenance. Separate phase workloads are needed for preprocessing-only and update-only conclusions. The scaling examples measure whole invocations. The per-project lock/contention and crossover conclusions require representative production distributions and repeatable hardware.
